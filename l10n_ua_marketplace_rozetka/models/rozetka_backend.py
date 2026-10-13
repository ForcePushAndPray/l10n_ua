import hashlib
import hmac
import json
import logging
import re
import pytz
import requests
from base64 import b64encode
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ROZETKA_API_URL = 'https://api-seller.rozetka.com.ua'
# кабінет і API Rozetka віддають час київський
ROZETKA_TZ = pytz.timezone('Europe/Kyiv')

# Токен Rozetka живе 24 години; оновлюємо трохи раніше
ROZETKA_TOKEN_HOURS = 23
# /items/mass-update приймає товари пачками
ROZETKA_BATCH_LIMIT = 100

# Rozetka specific cancel reasons
ROZETKA_CANCEL_REASONS = [
    ('out_of_stock', 'Out of Stock'),
    ('price_error', 'Price Error'),
    ('customer_request', 'Customer Request'),
    ('duplicate', 'Duplicate Order'),
    ('cannot_deliver', 'Cannot Deliver'),
    ('defective_product', 'Defective Product'),
    ('other', 'Other'),
]

# Статуси Rozetka звірені з живим кабінетом (GET /order-statuses/search, вересень 2026):
# 86 кодів у чотирьох групах — поле status_group замовлення: 1 — в обробці,
# 2 — успішно завершені, 3 — неуспішно завершені (скасування), 4 — повернення в дорозі.
# Групи дають основний розподіл, набори нижче уточнюють стани всередині групи 1 і винятки.
ROZETKA_NEW = {1, 52, 53}
ROZETKA_CONFIRMED = {2, 61, 80, 81}
ROZETKA_SHIPPED = {3, 4, 5, 56, 57, 58, 59, 60, 62, 63, 64, 65, 66, 67, 69, 73, 74, 76, 78, 82}
ROZETKA_DELIVERED = {6, 68, 87}
ROZETKA_RETURNED = {12, 19, 71, 72, 85, 86, 92}

# Стан marketplace.order -> код Rozetka. Лише канонічні статуси з прямим змістом:
# «Комплектується. Дані підтверджені», «Передано до служби доставки» (потребує ТТН),
# «Замовлення виконано». Скасування сюди свідомо не входить — див. нижче.
ROZETKA_STATUS_MAP_OUT = {
    'confirmed': 2,
    'shipped': 3,
    'delivered': 6,
}

# Загального «скасовано продавцем» у Rozetka немає: скасування — це один із двох десятків
# статусів-причин, і з кожного стану дозволені лише певні з них. Тому код обирається за причиною.
# Ключі — причини з майстра скасування (і базового модуля, і Rozetka).
ROZETKA_CANCEL_CODES = {
    'customer_request': 40,   # Клієнт передумав
    'out_of_stock': 42,       # Немає в наявності
    'pricing_error': 29,      # Ціна змінилася
    'price_error': 29,
    'duplicate_order': 49,    # Повторне замовлення (Rozetka вимагає duplicate_order_id)
    'duplicate': 49,
    'delivery_issue': 33,     # Умови доставки не влаштовують
    'cannot_deliver': 33,
    'fraud_suspicion': 28,    # Неправильні контактні дані
    'defective_product': 43,  # Брак
}


def rozetka_state_from_code(code, group=None):
    """Код статусу Rozetka (і його група) -> стан marketplace.order."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return 'new'
    try:
        group = int(group) if group not in (None, False, '') else None
    except (TypeError, ValueError):
        group = None
    if code in ROZETKA_NEW:
        return 'new'
    if code in ROZETKA_CONFIRMED:
        return 'confirmed'
    if code in ROZETKA_SHIPPED:
        return 'shipped'
    if code in ROZETKA_DELIVERED:
        return 'delivered'
    if code in ROZETKA_RETURNED:
        return 'returned'
    if group == 3:
        return 'cancelled'
    if group == 4:
        return 'returned'
    if group == 2:
        return 'delivered'
    # решта групи 1: обробляється менеджером, очікує оплати, повторний дзвінок…
    return 'processing'


class MarketplaceBackendRozetka(models.Model):
    _inherit = 'marketplace.backend'

    # === Rozetka Specific Fields ===
    rozetka_seller_id = fields.Char(
        string='Seller ID',
        help='Your Rozetka Seller ID',
    )
    rozetka_client_id = fields.Char(
        string='Client ID',
        groups='base.group_system',
    )
    rozetka_username = fields.Char(
        string='Username',
        help='Login for Rozetka Seller Portal',
    )
    rozetka_password = fields.Char(
        string='Password',
        groups='base.group_system',
    )

    @api.model
    def _selection_marketplace_type(self):
        """Add rozetka to available marketplace types."""
        res = super()._selection_marketplace_type()
        if ('rozetka', 'Rozetka') not in res:
            res.append(('rozetka', 'Rozetka'))
        return res

    # === API Authentication ===
    def _rozetka_static_token(self):
        """API-токен, згенерований у кабінеті продавця (Налаштування → Безпека API).

        Такий токен не прострочується за часом: Rozetka вимикає його лише після
        24 годин без жодного запиту. Він має пріоритет над логіном і паролем.
        """
        self.ensure_one()
        return (self.sudo().api_key or '').strip()

    def _api_authenticate(self):
        """Authenticate with Rozetka API and get access token."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_authenticate()

        static_token = self._rozetka_static_token()
        if static_token:
            return static_token

        backend = self.sudo()
        username = backend.rozetka_username
        password = backend.rozetka_password or backend.api_secret

        if not username or not password:
            raise UserError(_(
                'Rozetka needs either an API token generated in the seller portal '
                '(Settings → API Security → Generate API token) or the portal login and password.'
            ))

        url = f'{(self.api_url or ROZETKA_API_URL).rstrip("/")}/sites'

        # Rozetka чекає пароль, закодований у Base64
        payload = {
            'username': username,
            'password': b64encode(password.encode('utf-8')).decode('utf-8'),
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        except requests.exceptions.RequestException as e:
            self._set_error(str(e))
            raise UserError(_('Rozetka API connection error: %s') % str(e))
        except ValueError:
            self._set_error('Non-JSON response from /sites')
            raise UserError(_('Rozetka API returned an unexpected response.'))

        token = (data.get('content') or {}).get('access_token')
        if not data.get('success') or not token:
            error_msg = self._rozetka_error_message(data)
            self._set_error(error_msg)
            raise UserError(_('Rozetka authentication failed: %s') % error_msg)

        backend.write({
            'api_token': token,
            'api_token_expiry': fields.Datetime.now() + timedelta(hours=ROZETKA_TOKEN_HOURS),
        })
        self._clear_error()
        return token

    @staticmethod
    def _rozetka_error_message(data):
        """Витягти текст помилки з відповіді Rozetka."""
        errors = (data or {}).get('errors')
        if isinstance(errors, dict):
            return errors.get('message') or json.dumps(errors, ensure_ascii=False)
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return first.get('message') or json.dumps(first, ensure_ascii=False)
            return str(first)
        if errors:
            return str(errors)
        return _('Unknown error')

    def _get_rozetka_headers(self):
        """Get headers for Rozetka API requests."""
        self.ensure_one()
        static_token = self._rozetka_static_token()
        if static_token:
            token = static_token
        else:
            backend = self.sudo()
            if not backend.api_token or (self.api_token_expiry and self.api_token_expiry < fields.Datetime.now()):
                self._api_authenticate()
            token = self.sudo().api_token
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def _rozetka_api_request(self, method, endpoint, data=None, params=None):
        """Make authenticated request to Rozetka API."""
        self.ensure_one()
        url = f'{(self.api_url or ROZETKA_API_URL).rstrip("/")}{endpoint}'
        headers = self._get_rozetka_headers()

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=60,
            )

            # Handle token expiration
            if response.status_code == 401 and self._rozetka_static_token():
                message = _(
                    'Rozetka rejected the API token. It is either revoked or became inactive: '
                    'Rozetka disables a token that has not been used for more than 24 hours. '
                    'Generate a new one in the seller portal: Settings → API Security.'
                )
                self._set_error(message)
                raise UserError(message)
            if response.status_code == 401:
                self._api_authenticate()
                headers = self._get_rozetka_headers()
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=60,
                )

            response.raise_for_status()
            result = response.json()

        except requests.exceptions.RequestException as e:
            _logger.error(f"Rozetka API error: {e}")
            raise UserError(_('Rozetka API error: %s') % str(e))
        except ValueError:
            _logger.error("Rozetka API returned non-JSON response")
            raise UserError(_('Rozetka API returned an unexpected response.'))

        # Rozetka віддає 200 навіть на помилку — ознака в полі success.
        # Недійсний токен теж приходить так, а не кодом 401.
        if isinstance(result, dict) and result.get('success') is False:
            error = self._rozetka_error_message(result)
            if error == 'incorrect_access_token' and self._rozetka_static_token():
                message = _(
                    'Rozetka rejected the API token: it is wrong, revoked or became inactive '
                    '(Rozetka disables a token that has not been used for more than 24 hours). '
                    'Generate a new one in the seller portal: Settings → API Security.'
                )
                self._set_error(message)
                raise UserError(message)
            if error == 'access_denied':
                raise UserError(_(
                    'Rozetka: the token has no rights for this action. Tokens are tied to a manager role — '
                    'generate one under a role with access to orders and goods.'
                ))
            raise UserError(_('Rozetka API error: %s') % error)

        return result

    # === Connection Test ===
    def action_test_connection(self):
        """Test Rozetka API connection."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super().action_test_connection()

        try:
            if not self._rozetka_static_token():
                self._api_authenticate()
            # перевіряємо, що токеном реально можна читати дані
            self._rozetka_api_request('GET', '/orders/counts')
            self._clear_error()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to Rozetka Seller API.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_refresh_token(self):
        """Refresh Rozetka API token."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super().action_refresh_token()
        if self._rozetka_static_token():
            # статичний токен не оновлюється — його лише треба регулярно вживати
            self._rozetka_api_request('GET', '/orders/counts')
            return True
        return self._api_authenticate()

    @api.model
    def _cron_refresh_tokens(self):
        """Крім оновлення тимчасових токенів — «розбудити» статичні токени Rozetka.

        Rozetka вимикає API-токен після 24 годин без запитів. Доки синхронізації
        вимкнені (а вони вимкнені, поки майстер залишків — KeyCRM), по токену
        ніхто не ходить. Крон біжить раз на 12 годин, тож одного легкого запиту досить.
        """
        super()._cron_refresh_tokens()
        backends = self.search([
            ('marketplace_type', '=', 'rozetka'),
            ('state', 'in', ('active', 'error')),
        ])
        for backend in backends.filtered(lambda b: b._rozetka_static_token()):
            try:
                backend._rozetka_api_request('GET', '/orders/counts')
            except Exception as e:
                _logger.warning("Rozetka keep-alive failed for %s: %s", backend.name, e)

    # === Helpers ===
    def _rozetka_internal_state(self, code, default='new', group=None):
        """Код статусу Rozetka -> стан marketplace.order.

        Спершу мапінг статусів бекенда (його можна поправити руками),
        потім — розподіл за кодом і групою статусу.
        """
        self.ensure_one()
        if code in (None, False, ''):
            return default
        mapping = self.env['marketplace.status.mapping'].search([
            ('backend_id', '=', self.id),
            ('external_code', '=', str(code)),
            ('sync_from_marketplace', '=', True),
            ('active', '=', True),
        ], limit=1)
        if mapping:
            return mapping.internal_state
        return rozetka_state_from_code(code, group)

    @staticmethod
    def _rozetka_parse_amount(value):
        """Суми Rozetka приходять рядком («4013.43»)."""
        if value in (None, False, ''):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _rozetka_parse_datetime(value):
        """Дати Rozetka — «2026-09-18 13:50:36» київським часом; Odoo зберігає UTC.

        Без перерахунку всі замовлення зсувались би на 2–3 години (літній/зимовий час).
        """
        if not value:
            return False
        try:
            local = datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            try:
                return fields.Datetime.to_datetime(value)
            except (TypeError, ValueError):
                return False
        return ROZETKA_TZ.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    # === Order Import ===
    def _api_get_orders(self, from_date=None):
        """Get orders from Rozetka API.

        types=1 — обов'язково: без нього /orders/search віддає лише замовлення в обробці,
        і те, що перейшло у «виконано» чи «скасовано», просто зникає з видачі.
        Після першого імпорту беремо changed_from, щоб бачити зміни статусів старих
        замовлень, а не лише нові.
        """
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_get_orders(from_date)

        params = {
            'types': 1,
            'expand': 'purchases,user,delivery',
        }
        if self.import_orders_last:
            # запас у кілька годин: час кабінету київський, а мітка в Odoo — UTC;
            # повторно отримані замовлення лише оновлюються
            since = pytz.utc.localize(self.import_orders_last - timedelta(hours=4))
            params['changed_from'] = since.astimezone(ROZETKA_TZ).strftime('%Y-%m-%d %H:%M:%S')
        else:
            date_from = from_date or self.import_orders_from_date
            if date_from:
                params['created_from'] = fields.Datetime.to_datetime(date_from).strftime('%Y-%m-%d')

        all_orders = []
        page = 1

        while True:
            params['page'] = page
            result = self._rozetka_api_request('GET', '/orders/search', params=params)

            content = result.get('content') or {}
            orders = content.get('orders') or []
            if not orders:
                break

            all_orders.extend(orders)

            meta = content.get('_meta') or {}
            if page >= (meta.get('pageCount') or 1):
                break
            page += 1

        return all_orders

    def _rozetka_get_order_details(self, order_ref):
        """Деталі замовлення разом з товарами, покупцем і доставкою."""
        self.ensure_one()
        result = self._rozetka_api_request(
            'GET',
            f'/orders/{order_ref}',
            params={'expand': 'purchases,user,delivery'},
        )
        return result.get('content') or {}

    def _import_orders(self):
        """Import orders from Rozetka."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._import_orders()

        from_date = self.import_orders_last or self.import_orders_from_date
        orders_data = self._api_get_orders(from_date)

        count = 0
        Order = self.env['marketplace.order']

        for order_data in orders_data:
            external_id = str(order_data.get('id'))

            # Check if order already exists
            existing = Order.search([
                ('backend_id', '=', self.id),
                ('external_id', '=', external_id),
            ], limit=1)

            if existing:
                # Update status if changed
                existing._update_from_rozetka(order_data)
                continue

            # У видачі пошуку товарів може не бути — добираємо деталі
            if not order_data.get('purchases'):
                order_data = self._rozetka_get_order_details(external_id) or order_data

            order_vals = self._prepare_rozetka_order_vals(order_data)
            order = Order.create(order_vals)
            order._create_lines_from_rozetka(order_data.get('purchases') or [])
            count += 1

            # Auto create sale order if configured
            if self.auto_create_sale_order:
                try:
                    order.action_create_sale_order()
                    if self.auto_confirm_sale_order and order.sale_order_id:
                        order.sale_order_id.action_confirm()
                except Exception as e:
                    _logger.warning(f"Failed to create sale order: {e}")

        self.import_orders_last = fields.Datetime.now()
        _logger.info(f"Imported {count} orders from Rozetka for {self.name}")
        return count

    def _prepare_rozetka_order_vals(self, data):
        """Prepare order values from Rozetka data."""
        delivery = data.get('delivery') or {}
        user_info = data.get('user') or {}
        # ПІБ покупця і отримувача приходять окремими структурами
        user_title = data.get('user_title') or {}
        recipient_title = data.get('recipient_title') or {}

        customer_name = (
            recipient_title.get('full_name')
            or user_title.get('full_name')
            or ' '.join(filter(None, [
                user_info.get('last_name'),
                user_info.get('first_name'),
            ])).strip()
        )

        status = data.get('status')

        return {
            'backend_id': self.id,
            'external_id': str(data.get('id')),
            'name': f"RZ-{data.get('id')}",
            'order_date': self._rozetka_parse_datetime(data.get('created')),
            'marketplace_state': data.get('status_name') or (str(status) if status else False),
            'marketplace_state_code': str(status) if status is not None else False,
            'state': self._rozetka_internal_state(status, group=data.get('status_group')),
            # amount_total — stored compute з рядків замовлення
            'amount_delivery': self._rozetka_parse_amount(delivery.get('cost')),
            'customer_name': customer_name,
            'customer_phone': data.get('recipient_phone') or data.get('user_phone') or user_info.get('phone'),
            'customer_email': user_info.get('email') or delivery.get('email') or False,
            'commission_amount': sum(
                self._rozetka_parse_amount((p.get('item') or {}).get('commission_sum'))
                for p in (data.get('purchases') or [])
            ),
            'customer_comment': data.get('comment'),
            'delivery_method': delivery.get('delivery_service_name') or delivery.get('name'),
            'delivery_carrier_name': delivery.get('delivery_service_name'),
            'delivery_city': self._rozetka_city_name(delivery.get('city')),
            'delivery_address': ', '.join(filter(None, [
                delivery.get('place_street'), delivery.get('place_house'), delivery.get('place_flat'),
            ])) or False,
            'delivery_warehouse': delivery.get('place_number'),
            'tracking_number': data.get('ttn') or delivery.get('ttn'),
            'payment_method': data.get('payment_type_name') or data.get('payment_type'),
            'is_paid': bool(data.get('is_paid')),
            'raw_data': json.dumps(data, ensure_ascii=False, indent=2),
        }

    @staticmethod
    def _rozetka_city_name(city):
        """Місто доставки українською: у city.name Rozetka віддає російську назву."""
        if isinstance(city, dict):
            return city.get('name_ua') or city.get('city_name') or city.get('title') or city.get('name')
        return city or False

    # === Order Status Update ===
    def _api_update_order_status(self, order, status, tracking=None):
        """Update order status on Rozetka."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_update_order_status(order, status, tracking)

        if status == 'cancelled':
            # скасування має свій шлях — з причиною, див. _api_cancel_order
            return False
        rozetka_status = ROZETKA_STATUS_MAP_OUT.get(status)
        if not rozetka_status:
            return False

        data = {
            'status': int(rozetka_status),
        }

        if tracking:
            data['ttn'] = tracking

        try:
            # Редагування замовлення (статус, ТТН, коментар продавця)
            result = self._rozetka_api_request(
                'PUT',
                f'/orders/{order.external_id}',
                data=data,
            )
            return result.get('success', False)
        except Exception as e:
            _logger.error(f"Failed to update Rozetka order status: {e}")
            return False

    # === Stock & Price Sync ===
    def _rozetka_mass_update(self, items_payload):
        """PUT /items/mass-update — масова зміна ціни й наявності товарів."""
        self.ensure_one()
        for index in range(0, len(items_payload), ROZETKA_BATCH_LIMIT):
            chunk = items_payload[index:index + ROZETKA_BATCH_LIMIT]
            self._rozetka_api_request(
                'PUT',
                '/items/mass-update',
                data={'isIgnoreCheck': 0, 'items': chunk},
            )

    @staticmethod
    def _rozetka_stock_payload(item):
        return {
            'item_rz_id': int(item.external_id),
            'stock_quantity': int(item.qty_to_publish),
        }

    @staticmethod
    def _rozetka_price_payload(item):
        payload = {
            'item_rz_id': int(item.external_id),
            'price': item.price,
        }
        if item.price_promo and item.price_promo > 0:
            payload['price_promo'] = item.price_promo
        return payload

    def _api_sync_stock_batch(self, items):
        """Batch stock update via Rozetka API."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_sync_stock_batch(items)

        if not items:
            return

        try:
            self._rozetka_mass_update([self._rozetka_stock_payload(item) for item in items])
            items.write({
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            _logger.info(f"Batch stock sync: updated {len(items)} items on Rozetka")

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Batch stock sync failed: {error_msg}")

            if self.sync_error_handling == 'retry':
                for item in items:
                    try:
                        self._rozetka_mass_update([self._rozetka_stock_payload(item)])
                        item.write({'last_sync': fields.Datetime.now(), 'sync_error': False})
                    except Exception as item_error:
                        item.write({'sync_error': str(item_error)})
            elif self.sync_error_handling == 'stop':
                items.write({'sync_error': error_msg})
                raise
            else:  # continue
                items.write({'sync_error': error_msg})

    def _api_sync_prices_batch(self, items):
        """Batch price update via Rozetka API."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_sync_prices_batch(items)

        if not items:
            return

        try:
            self._rozetka_mass_update([self._rozetka_price_payload(item) for item in items])
            items.write({
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            _logger.info(f"Batch price sync: updated {len(items)} items on Rozetka")

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Batch price sync failed: {error_msg}")

            if self.sync_error_handling == 'retry':
                for item in items:
                    try:
                        self._rozetka_mass_update([self._rozetka_price_payload(item)])
                        item.write({'last_sync': fields.Datetime.now(), 'sync_error': False})
                    except Exception as item_error:
                        item.write({'sync_error': str(item_error)})
            elif self.sync_error_handling == 'stop':
                items.write({'sync_error': error_msg})
                raise
            else:  # continue
                items.write({'sync_error': error_msg})

    # === Product Import from Rozetka ===
    def action_import_products(self):
        """Витягти товари кабінету, щоб мати rz_item_id для синхронізації."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super().action_import_products()

        pricelist = self.feed_pricelist_id
        if not pricelist:
            pricelist = self.env['marketplace.pricelist'].create({
                'name': f'{self.name} - Products',
                'backend_id': self.id,
            })
            self.feed_pricelist_id = pricelist

        Item = self.env['marketplace.pricelist.item']
        Template = self.env['product.template']
        count = 0
        skipped = 0
        page = 1

        while True:
            result = self._rozetka_api_request(
                'GET',
                '/goods/all',
                params={'item_active': 1, 'page': page},
            )
            content = result.get('content') or {}
            goods = content.get('items') or []
            if not goods:
                break

            for data in goods:
                external_id = str(data.get('rz_item_id'))

                existing = Item.search([
                    ('pricelist_id', '=', pricelist.id),
                    ('external_id', '=', external_id),
                ], limit=1)
                if existing:
                    continue

                # article — артикул продавця, price_offer_id — id у прайсі
                sku = data.get('article') or data.get('price_offer_id')
                product = Template.search([('default_code', '=', sku)], limit=1) if sku else Template

                # product_tmpl_id обов'язковий: без збігу за артикулом пропускаємо
                if not product or Item.search_count([
                    ('pricelist_id', '=', pricelist.id),
                    ('product_tmpl_id', '=', product.id),
                ]):
                    skipped += 1
                    continue

                Item.create({
                    'pricelist_id': pricelist.id,
                    'external_id': external_id,
                    'product_tmpl_id': product.id,
                    'sku': sku,
                    'name_override': data.get('name_ua') or data.get('name'),
                    'price': self._rozetka_parse_amount(data.get('price')),
                    'qty_available': float(data.get('stock_quantity') or 0),
                    'state': 'published' if data.get('available') else 'draft',
                })
                count += 1

            meta = content.get('_meta') or {}
            if page >= (meta.get('pageCount') or 1):
                break
            page += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Products Imported'),
                'message': _(
                    '%(count)d products imported from Rozetka, %(skipped)d skipped '
                    '(no Odoo product with such internal reference).',
                    count=count, skipped=skipped,
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    # === Status Mapping Sync ===
    def action_sync_statuses(self):
        """Sync order statuses from Rozetka API."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super().action_sync_statuses()

        rozetka_statuses = []
        page = 1

        while True:
            result = self._rozetka_api_request(
                'GET',
                '/order-statuses/search',
                params={'page': page},
            )
            content = result.get('content') or {}
            statuses = content.get('orderStatuses') or []
            if not statuses:
                break

            for status in statuses:
                code = status.get('id')
                rozetka_statuses.append((
                    str(code),
                    status.get('title') or str(code),
                    rozetka_state_from_code(code, status.get('status_group')),
                ))

            meta = content.get('_meta') or {}
            if page >= (meta.get('pageCount') or 1):
                break
            page += 1

        StatusMapping = self.env['marketplace.status.mapping']
        count = 0

        for external_code, external_name, internal_state in rozetka_statuses:
            existing = StatusMapping.search([
                ('backend_id', '=', self.id),
                ('external_code', '=', external_code),
            ], limit=1)

            # Назад у Rozetka відправляємо лише канонічні коди: інакше на запит
            # «який код ставити для стану X» відповів би перший-ліпший із кількох
            # десятків, наприклад «Відправлення протерміновано» замість «виконано».
            to_marketplace = int(external_code) in ROZETKA_STATUS_MAP_OUT.values()
            if not existing:
                StatusMapping.create({
                    'backend_id': self.id,
                    'external_code': external_code,
                    'external_name': external_name,
                    'internal_state': internal_state,
                    'sync_to_marketplace': to_marketplace,
                    'sync_from_marketplace': True,
                })
                count += 1
            else:
                # назву оновлюємо завжди, стан — лише якщо його ще не правили руками
                existing.write({'external_name': external_name,
                                'sync_to_marketplace': to_marketplace})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Status Mapping'),
                'message': _('%d status mappings created/updated for Rozetka.') % count,
                'type': 'success',
                'sticky': False,
            }
        }

    # === Order Cancellation ===
    def _api_cancel_order(self, order, reason=None, comment=None):
        """Cancel order on Rozetka."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._api_cancel_order(order, reason, comment)

        cancel_status = ROZETKA_CANCEL_CODES.get(reason)
        if not cancel_status:
            raise UserError(_(
                'Rozetka has no generic "cancelled by seller" status — each cancellation is a specific reason. '
                'Choose a concrete reason (out of stock, customer changed their mind, price changed, '
                'duplicate, delivery conditions, defect).'
            ))

        data = {
            'status': cancel_status,
        }
        if comment:
            data['seller_comment'] = comment

        if cancel_status == 49:
            # «Повторне замовлення» Rozetka приймає лише з номером оригіналу
            match = re.search(r'\d{6,}', comment or '')
            if not match:
                raise UserError(_(
                    'To cancel a duplicate Rozetka requires the number of the original order. '
                    'Put it into the cancellation comment.'
                ))
            data['duplicate_order_id'] = int(match.group(0))

        try:
            result = self._rozetka_api_request(
                'PUT',
                f'/orders/{order.external_id}',
                data=data,
            )
            if result.get('success'):
                _logger.info(f"Order {order.name} cancelled on Rozetka")
                return True
            raise UserError(_('Failed to cancel order on Rozetka: %s') % self._rozetka_error_message(result))
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Failed to cancel order {order.name} on Rozetka: {e}")
            raise UserError(_('Failed to cancel order on Rozetka: %s') % str(e))

    # === Webhook Handling ===
    def _verify_rozetka_webhook(self, data, signature):
        """Verify Rozetka webhook signature."""
        self.ensure_one()
        if not self.sudo().webhook_secret:
            return True

        expected = hmac.new(
            self.sudo().webhook_secret.encode(),
            json.dumps(data, separators=(',', ':')).encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature or '')

    def _process_webhook(self, data, headers=None):
        """Process incoming Rozetka webhook."""
        self.ensure_one()
        if self.marketplace_type != 'rozetka':
            return super()._process_webhook(data, headers)

        event_type = data.get('event')

        if event_type == 'order.created':
            # Import new order
            order_data = data.get('data', {})
            if order_data:
                self._import_single_order(order_data)
                return True

        elif event_type == 'order.status_changed':
            # Update order status
            order_data = data.get('data', {})
            external_id = str(order_data.get('id'))
            order = self.env['marketplace.order'].search([
                ('backend_id', '=', self.id),
                ('external_id', '=', external_id),
            ], limit=1)
            if order:
                order._update_from_rozetka(order_data)
                return True

        return False

    def _import_single_order(self, order_data):
        """Import a single order from webhook data."""
        self.ensure_one()
        external_id = str(order_data.get('id'))

        existing = self.env['marketplace.order'].search([
            ('backend_id', '=', self.id),
            ('external_id', '=', external_id),
        ], limit=1)

        if existing:
            return existing

        if not order_data.get('purchases'):
            order_data = self._rozetka_get_order_details(external_id) or order_data

        order_vals = self._prepare_rozetka_order_vals(order_data)
        order = self.env['marketplace.order'].create(order_vals)
        order._create_lines_from_rozetka(order_data.get('purchases') or [])

        if self.auto_create_sale_order:
            try:
                order.action_create_sale_order()
                if self.auto_confirm_sale_order and order.sale_order_id:
                    order.sale_order_id.action_confirm()
            except Exception as e:
                _logger.warning(f"Failed to create sale order: {e}")

        return order


class MarketplaceOrderRozetka(models.Model):
    _inherit = 'marketplace.order'

    def _update_from_rozetka(self, data):
        """Update order from Rozetka data."""
        self.ensure_one()

        status = data.get('status')
        vals = {
            'marketplace_state': data.get('status_name') or (str(status) if status else False),
            'marketplace_state_code': str(status) if status is not None else False,
            'state': self.backend_id._rozetka_internal_state(
                status, default=self.state, group=data.get('status_group')),
        }

        delivery = data.get('delivery') or {}
        ttn = data.get('ttn') or delivery.get('ttn')
        if ttn:
            vals['tracking_number'] = ttn

        if data.get('is_paid'):
            vals['is_paid'] = True

        self.write(vals)

    def _create_lines_from_rozetka(self, items_data):
        """Create order lines from Rozetka purchases data.

        Артикул продавця лежить у вкладеному purchases[].item.article; item_id —
        це номер товару в Rozetka, за ним товар Odoo не знайти.
        """
        self.ensure_one()
        Line = self.env['marketplace.order.line']
        Product = self.env['product.product']
        backend = self.backend_id

        for purchase in items_data:
            item = purchase.get('item') or {}
            sku = item.get('article') or item.get('price_offer_id') or False
            product = Product.search([('default_code', '=', sku)], limit=1) if sku else Product
            if not product and sku:
                product = Product.search([('barcode', '=', sku)], limit=1)

            Line.create({
                'order_id': self.id,
                'external_product_id': str(purchase.get('item_id') or item.get('id') or ''),
                'product_id': product.id if product else False,
                'sku': sku,
                'name': purchase.get('item_name') or item.get('name_ua') or item.get('name') or _('Unknown Product'),
                'quantity': float(purchase.get('quantity') or 1),
                'price_unit': backend._rozetka_parse_amount(
                    purchase.get('price_with_discount') or purchase.get('price')
                ),
            })


class MarketplaceOrderCancelWizardRozetka(models.TransientModel):
    """Extend cancel wizard with Rozetka-specific cancel reasons."""
    _inherit = 'marketplace.order.cancel.wizard'

    @api.model
    def _get_cancel_reasons(self):
        """Override to add Rozetka-specific cancel reasons when applicable."""
        reasons = super()._get_cancel_reasons()

        # Check if any order is from Rozetka
        order_ids = self.env.context.get('default_order_ids')
        if order_ids:
            orders = self.env['marketplace.order'].browse(
                order_ids[0][2] if isinstance(order_ids[0], (list, tuple)) else order_ids
            )
            if any(o.marketplace_type == 'rozetka' for o in orders):
                # Return Rozetka-specific reasons
                return ROZETKA_CANCEL_REASONS

        return reasons
