import json
import logging
import re
import requests
from datetime import datetime, timezone

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PROM_API_URL = 'https://my.prom.ua/api/v1'

# API приймає не більше 100 позицій за один виклик /products/edit
PROM_BATCH_LIMIT = 100
# Максимум записів у відповіді /orders/list і /products/list
PROM_LIST_LIMIT = 100

# Причини скасування замовлення — enum з офіційної специфікації
# (public-api.docs.prom.ua, Orders/schemas/PostOrdersStatusRequestBody.yaml)
PROM_CANCEL_REASONS = [
    ('not_available', 'Немає в наявності'),
    ('no_product_variants', 'Немає різновиду товару'),
    ('payment_not_received', 'Оплата не надійшла'),
    ('buyers_request', 'На прохання покупця'),
    ('duplicate', 'Замовлення-дублікат'),
    ('invalid_phone_number', 'Не вдається додзвонитись'),
    ('another', 'Інше'),
]

# Причина скасування в Odoo -> причина в Prom.ua
PROM_CANCEL_REASON_MAP = {
    'customer_request': 'buyers_request',
    'out_of_stock': 'not_available',
    'pricing_error': 'another',
    'duplicate_order': 'duplicate',
    'fraud_suspicion': 'another',
    'delivery_issue': 'another',
    'other': 'another',
}

# Статус Prom.ua -> стан marketplace.order
PROM_STATUS_MAP = {
    'pending': 'new',
    'draft': 'new',
    'received': 'confirmed',
    'paid': 'processing',
    'delivered': 'delivered',
    'canceled': 'cancelled',
}

# Стан marketplace.order -> статус Prom.ua (enum /orders/set_status)
PROM_STATUS_MAP_OUT = {
    'confirmed': 'received',
    'processing': 'received',
    'shipped': 'delivered',
    'delivered': 'delivered',
    'cancelled': 'canceled',
}


class MarketplaceBackendProm(models.Model):
    _inherit = 'marketplace.backend'

    # === Prom.ua Specific Fields ===
    prom_company_id = fields.Char(
        string='Company ID',
        help='Your Prom.ua Company ID',
    )

    @api.model
    def _selection_marketplace_type(self):
        """Add prom to available marketplace types."""
        res = super()._selection_marketplace_type()
        if ('prom', 'Prom.ua') not in res:
            res.append(('prom', 'Prom.ua'))
        return res

    @api.onchange('marketplace_type')
    def _onchange_marketplace_type_prom(self):
        """Set default API URL for Prom.ua."""
        if self.marketplace_type == 'prom' and not self.api_url:
            self.api_url = PROM_API_URL

    # === Helpers ===
    @staticmethod
    def _prom_parse_amount(value):
        """Привести суму Prom.ua до float.

        API віддає суми рядком разом з валютою: «324 грн», «22 400 грн»,
        «1 250,50 грн» — прямий float() на такому рядку падає.
        """
        if value in (None, False, ''):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r'[^\d,.-]', '', str(value)).replace(',', '.')
        # якщо крапок кілька (роздільник тисяч), лишаємо тільки останню
        if cleaned.count('.') > 1:
            head, _sep, tail = cleaned.rpartition('.')
            cleaned = head.replace('.', '') + '.' + tail
        try:
            return float(cleaned)
        except ValueError:
            _logger.warning("Prom.ua: не вдалось розібрати суму %r", value)
            return 0.0

    @staticmethod
    def _prom_parse_datetime(value):
        """Розібрати дату Prom.ua (ISO 8601 з таймзоною) у naive UTC для Odoo."""
        if not value:
            return fields.Datetime.now()
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (ValueError, AttributeError, TypeError):
            return fields.Datetime.now()
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    # === API Request Helper ===
    def _prom_api_request(self, method, endpoint, data=None, params=None):
        """Make authenticated request to Prom.ua API."""
        self.ensure_one()
        url = f'{(self.api_url or PROM_API_URL).rstrip("/")}{endpoint}'

        headers = {
            'Authorization': f'Bearer {self.sudo().api_key}',
            'Content-Type': 'application/json',
            'X-LANGUAGE': 'uk',
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=60,
            )

            if response.status_code == 401:
                raise UserError(_('Prom.ua API authentication failed. Check your API key.'))

            response.raise_for_status()

            if not response.content:
                return {}

            result = response.json()

        except requests.exceptions.RequestException as e:
            _logger.error(f"Prom.ua API error: {e}")
            raise UserError(_('Prom.ua API error: %s') % str(e))
        except ValueError as e:
            _logger.error(f"Prom.ua API returned non-JSON response: {e}")
            raise UserError(_('Prom.ua API returned an unexpected response.'))

        # Prom.ua може віддати 200 з описом помилки в тілі
        if isinstance(result, dict):
            error = result.get('error') or result.get('errors')
            if error:
                raise UserError(_('Prom.ua API error: %s') % error)

        return result

    # === Connection Test ===
    def action_test_connection(self):
        """Test Prom.ua API connection."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super().action_test_connection()

        try:
            # Найлегший ендпоінт, доступний будь-якому токену.
            # Ендпоінта з інформацією про компанію Prom.ua не має.
            self._prom_api_request('GET', '/groups/list', params={'limit': 1})

            self._clear_error()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully connected to Prom.ua API.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self._set_error(str(e))
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

    def _api_authenticate(self):
        """Prom.ua uses static API token, no refresh needed."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_authenticate()
        # Prom uses static Bearer token, no auth flow needed
        return self.sudo().api_key

    def action_refresh_token(self):
        """Prom.ua uses static token."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super().action_refresh_token()
        # No token refresh for Prom
        return True

    # === Pagination Helper ===
    def _prom_fetch_all(self, endpoint, result_key, params=None):
        """Вичитати весь список посторінково.

        Prom.ua гортає списки курсором `last_id` (вибірка записів з id не вище
        вказаного, сортування — за спаданням id). Параметра `offset` в API немає:
        з ним кожна ітерація повертала б ту саму першу сторінку.
        """
        self.ensure_one()
        query = dict(params or {})
        query['limit'] = PROM_LIST_LIMIT

        records = []
        seen_ids = set()

        while True:
            page = self._prom_api_request('GET', endpoint, params=query).get(result_key) or []
            if not page:
                break

            page_ids = [rec.get('id') for rec in page if rec.get('id') is not None]
            fresh = [rec for rec in page if rec.get('id') not in seen_ids]
            if not fresh:
                break

            records.extend(fresh)
            seen_ids.update(page_ids)

            if len(page) < PROM_LIST_LIMIT or not page_ids:
                break

            query['last_id'] = min(page_ids) - 1

        return records

    # === Order Import ===
    def _api_get_orders(self, from_date=None):
        """Get orders from Prom.ua API."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_get_orders(from_date)

        params = {}
        date_from = from_date or self.import_orders_from_date
        if date_from:
            params['date_from'] = fields.Datetime.to_datetime(date_from).strftime('%Y-%m-%dT%H:%M:%S')

        return self._prom_fetch_all('/orders/list', 'orders', params=params)

    def _import_orders(self):
        """Import orders from Prom.ua."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._import_orders()

        from_date = self.import_orders_last or self.import_orders_from_date
        orders_data = self._api_get_orders(from_date)

        count = 0
        Order = self.env['marketplace.order']

        for order_data in orders_data:
            external_id = str(order_data.get('id'))

            existing = Order.search([
                ('backend_id', '=', self.id),
                ('external_id', '=', external_id),
            ], limit=1)

            if existing:
                existing._update_from_prom(order_data)
                continue

            order_vals = self._prepare_prom_order_vals(order_data)
            order = Order.create(order_vals)
            order._create_lines_from_prom(order_data.get('products', []))
            count += 1

            if self.auto_create_sale_order:
                try:
                    order.action_create_sale_order()
                    if self.auto_confirm_sale_order and order.sale_order_id:
                        order.sale_order_id.action_confirm()
                except Exception as e:
                    _logger.warning(f"Failed to create sale order: {e}")

        self.import_orders_last = fields.Datetime.now()
        _logger.info(f"Imported {count} orders from Prom.ua for {self.name}")
        return count

    def _prepare_prom_order_vals(self, data):
        """Prepare order values from Prom.ua data."""
        delivery = data.get('delivery_option') or {}
        provider = data.get('delivery_provider_data') or {}
        recipient = provider.get('recipient_address') or {}
        client = data.get('client') or {}
        payment = data.get('payment_option') or {}
        payment_data = data.get('payment_data') or {}

        # Ім'я приходить і всередині client, і полями верхнього рівня
        name_parts = [
            client.get('last_name') or data.get('client_last_name'),
            client.get('first_name') or data.get('client_first_name'),
            client.get('second_name') or data.get('client_second_name'),
        ]
        customer_name = ' '.join(part for part in name_parts if part).strip()

        status = data.get('status')

        return {
            'backend_id': self.id,
            'external_id': str(data.get('id')),
            'name': f"PROM-{data.get('id')}",
            'order_date': self._prom_parse_datetime(data.get('date_created')),
            'marketplace_state': data.get('status_name') or status,
            'marketplace_state_code': status,
            'state': PROM_STATUS_MAP.get(status, 'new'),
            # amount_total — stored compute з рядків замовлення, тут лише доставка
            'amount_delivery': self._prom_parse_amount(data.get('delivery_cost')),
            'customer_name': customer_name,
            'customer_phone': data.get('phone') or client.get('phone'),
            'customer_email': data.get('email') or client.get('email'),
            'customer_comment': data.get('client_notes'),
            'delivery_method': delivery.get('name'),
            'delivery_carrier_name': delivery.get('shipping_service') or provider.get('provider'),
            'delivery_city': recipient.get('city_name'),
            'delivery_address': data.get('delivery_address'),
            'delivery_warehouse': recipient.get('warehouse_id'),
            'tracking_number': provider.get('declaration_number'),
            'payment_method': payment.get('name') or payment_data.get('type'),
            'is_paid': payment_data.get('status') == 'paid' or status == 'paid',
            'raw_data': json.dumps(data, ensure_ascii=False, indent=2),
        }

    # === Order Status Update ===
    def _prom_set_order_status(self, order, prom_status, cancel_reason=None, cancel_comment=None):
        """Викликати POST /orders/set_status.

        Статус міняється списком ідентифікаторів: окремого ендпоінта
        на одне замовлення в API немає.
        """
        self.ensure_one()
        payload = {
            'status': prom_status,
            'ids': [int(order.external_id)],
        }
        if cancel_reason:
            payload['cancellation_reason'] = cancel_reason
            # для причини «another» текст обов'язковий
            if cancel_reason == 'another' and not cancel_comment:
                cancel_comment = _('Cancelled in Odoo')
        if cancel_comment:
            payload['cancellation_text'] = cancel_comment

        return self._prom_api_request('POST', '/orders/set_status', data=payload)

    def _api_update_order_status(self, order, status, tracking=None):
        """Update order status on Prom.ua."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_update_order_status(order, status, tracking)

        prom_status = self._get_marketplace_code(status) or PROM_STATUS_MAP_OUT.get(status)
        if not prom_status:
            return False

        try:
            self._prom_set_order_status(order, prom_status)
        except Exception as e:
            _logger.error(f"Failed to update Prom.ua order status: {e}")
            return False

        # ТТН передається окремим ендпоінтом служби доставки
        if tracking and status == 'shipped':
            try:
                self._prom_api_request(
                    'POST',
                    '/delivery/save_declaration_id',
                    data={
                        'order_id': int(order.external_id),
                        'declaration_id': tracking,
                    },
                )
            except Exception as e:
                _logger.warning(f"Failed to save Prom.ua declaration id: {e}")

        return True

    # === Stock & Price Sync ===
    def _prom_edit_products(self, products_data):
        """POST /products/edit — редагування списку товарів, до 100 за виклик."""
        self.ensure_one()
        for index in range(0, len(products_data), PROM_BATCH_LIMIT):
            chunk = products_data[index:index + PROM_BATCH_LIMIT]
            self._prom_api_request('POST', '/products/edit', data=chunk)

    @staticmethod
    def _prom_stock_payload(item):
        return {
            'id': int(item.external_id),
            'presence': 'available' if item.qty_to_publish > 0 else 'not_available',
            'quantity_in_stock': int(item.qty_to_publish),
        }

    @staticmethod
    def _prom_price_payload(item):
        payload = {
            'id': int(item.external_id),
            'price': item.price,
        }
        # знижка рахується як різниця старої і поточної ціни
        if item.price_original and item.price_original > item.price:
            payload['oldprice'] = item.price_original
        return payload

    def _api_sync_stock_batch(self, items):
        """Batch stock update via Prom.ua API."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_sync_stock_batch(items)

        if not items:
            return

        try:
            self._prom_edit_products([self._prom_stock_payload(item) for item in items])
            items.write({
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            _logger.info(f"Batch stock sync: updated {len(items)} items on Prom.ua")

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Batch stock sync failed: {error_msg}")

            if self.sync_error_handling == 'retry':
                # той самий ендпоінт, але поштучно — щоб відсіяти проблемні позиції
                for item in items:
                    try:
                        self._prom_edit_products([self._prom_stock_payload(item)])
                        item.write({'last_sync': fields.Datetime.now(), 'sync_error': False})
                    except Exception as item_error:
                        item.write({'sync_error': str(item_error)})
            elif self.sync_error_handling == 'stop':
                items.write({'sync_error': error_msg})
                raise
            else:  # continue
                items.write({'sync_error': error_msg})

    def _api_sync_prices_batch(self, items):
        """Batch price update via Prom.ua API."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_sync_prices_batch(items)

        if not items:
            return

        try:
            self._prom_edit_products([self._prom_price_payload(item) for item in items])
            items.write({
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
            })
            _logger.info(f"Batch price sync: updated {len(items)} items on Prom.ua")

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Batch price sync failed: {error_msg}")

            if self.sync_error_handling == 'retry':
                for item in items:
                    try:
                        self._prom_edit_products([self._prom_price_payload(item)])
                        item.write({'last_sync': fields.Datetime.now(), 'sync_error': False})
                    except Exception as item_error:
                        item.write({'sync_error': str(item_error)})
            elif self.sync_error_handling == 'stop':
                items.write({'sync_error': error_msg})
                raise
            else:  # continue
                items.write({'sync_error': error_msg})

    # === Status Mapping Sync ===
    def action_sync_statuses(self):
        """Sync order statuses from Prom.ua API."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super().action_sync_statuses()

        # Базові статуси Prom.ua з enum /orders/set_status
        prom_statuses = [
            ('pending', 'Нове', 'new'),
            ('received', 'Прийнято', 'confirmed'),
            ('paid', 'Оплачено', 'processing'),
            ('delivered', 'Виконано', 'delivered'),
            ('canceled', 'Скасовано', 'cancelled'),
            ('draft', 'Чернетка', 'new'),
        ]

        # Кабінет може мати ще й власні статуси — доливаємо їх з API
        try:
            custom = self._prom_api_request('GET', '/order_status_options/list')
            known = [status[0] for status in prom_statuses]
            for option in custom.get('order_status_options') or []:
                code = option.get('name') or str(option.get('id'))
                if code and code not in known:
                    prom_statuses.append((
                        code,
                        option.get('title') or code,
                        PROM_STATUS_MAP.get(code, 'processing'),
                    ))
        except Exception as e:
            _logger.warning(f"Prom.ua: не вдалось прочитати кастомні статуси: {e}")

        StatusMapping = self.env['marketplace.status.mapping']
        count = 0

        for external_code, external_name, internal_state in prom_statuses:
            existing = StatusMapping.search([
                ('backend_id', '=', self.id),
                ('external_code', '=', external_code),
            ], limit=1)

            if not existing:
                StatusMapping.create({
                    'backend_id': self.id,
                    'external_code': external_code,
                    'external_name': external_name,
                    'internal_state': internal_state,
                    'sync_to_marketplace': True,
                    'sync_from_marketplace': True,
                })
                count += 1
            else:
                existing.write({
                    'external_name': external_name,
                    'internal_state': internal_state,
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Status Mapping'),
                'message': _('%d status mappings created/updated for Prom.ua.') % count,
                'type': 'success',
                'sticky': False,
            }
        }

    # === Order Cancellation ===
    def _api_cancel_order(self, order, reason=None, comment=None):
        """Cancel order on Prom.ua."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._api_cancel_order(order, reason, comment)

        try:
            self._prom_set_order_status(
                order,
                'canceled',
                cancel_reason=PROM_CANCEL_REASON_MAP.get(reason, 'another'),
                cancel_comment=comment,
            )
            _logger.info(f"Order {order.name} cancelled on Prom.ua")
            return True
        except Exception as e:
            _logger.error(f"Failed to cancel order {order.name} on Prom.ua: {e}")
            raise UserError(_('Failed to cancel order on Prom.ua: %s') % str(e))

    # === Product Import from Prom ===
    def action_import_products(self):
        """Import products from Prom.ua to pricelist items."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super().action_import_products()

        all_products = self._prom_fetch_all('/products/list', 'products')

        # Find or create pricelist
        pricelist = self.feed_pricelist_id
        if not pricelist:
            pricelist = self.env['marketplace.pricelist'].create({
                'name': f'{self.name} - Products',
                'backend_id': self.id,
            })
            self.feed_pricelist_id = pricelist

        count = 0
        skipped = 0
        Item = self.env['marketplace.pricelist.item']
        Template = self.env['product.template']

        for prod_data in all_products:
            external_id = str(prod_data.get('id'))

            existing = Item.search([
                ('pricelist_id', '=', pricelist.id),
                ('external_id', '=', external_id),
            ], limit=1)

            if existing:
                continue

            # Позиція прайс-листа прив'язується до товару Odoo (product_tmpl_id
            # обов'язковий), тому без збігу за артикулом рядок не створюємо
            sku = prod_data.get('sku')
            product = Template.search([('default_code', '=', sku)], limit=1) if sku else Template

            if not product:
                skipped += 1
                continue

            if Item.search_count([
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
                'name_override': prod_data.get('name'),
                'price': self._prom_parse_amount(prod_data.get('price')),
                'qty_available': float(prod_data.get('quantity_in_stock') or 0),
                'state': 'published' if prod_data.get('presence') == 'available' else 'draft',
            })
            count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Products Imported'),
                'message': _(
                    '%(count)d products imported from Prom.ua, %(skipped)d skipped '
                    '(no Odoo product with such internal reference).',
                    count=count, skipped=skipped,
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    # === Webhook Handling ===
    def _process_webhook(self, data, headers=None):
        """Process incoming Prom.ua webhook."""
        self.ensure_one()
        if self.marketplace_type != 'prom':
            return super()._process_webhook(data, headers)

        event_type = data.get('event_type') or data.get('event')
        order_data = data.get('order') or data.get('data') or {}
        if not order_data:
            return False

        external_id = str(order_data.get('id'))
        order = self.env['marketplace.order'].search([
            ('backend_id', '=', self.id),
            ('external_id', '=', external_id),
        ], limit=1)

        if event_type in ('order_created', 'new_order', 'order.created'):
            if order:
                return True
            order = self.env['marketplace.order'].create(self._prepare_prom_order_vals(order_data))
            order._create_lines_from_prom(order_data.get('products', []))

            if self.auto_create_sale_order:
                try:
                    order.action_create_sale_order()
                    if self.auto_confirm_sale_order and order.sale_order_id:
                        order.sale_order_id.action_confirm()
                except Exception as e:
                    _logger.warning(f"Failed to create sale order: {e}")
            return True

        if event_type in ('order_status_changed', 'status_changed', 'order.status_changed'):
            if order:
                order._update_from_prom(order_data)
                return True

        return False


class MarketplaceOrderProm(models.Model):
    _inherit = 'marketplace.order'

    def _update_from_prom(self, data):
        """Update order from Prom.ua data."""
        self.ensure_one()

        status = data.get('status')
        payment_data = data.get('payment_data') or {}

        vals = {
            'marketplace_state': data.get('status_name') or status,
            'marketplace_state_code': status,
            'state': PROM_STATUS_MAP.get(status, self.state),
        }

        if payment_data.get('status') == 'paid' or status == 'paid':
            vals['is_paid'] = True

        declaration = (data.get('delivery_provider_data') or {}).get('declaration_number')
        if declaration:
            vals['tracking_number'] = declaration

        self.write(vals)

    def _create_lines_from_prom(self, products_data):
        """Create order lines from Prom.ua products data."""
        self.ensure_one()
        Line = self.env['marketplace.order.line']
        Backend = self.env['marketplace.backend']

        for item in products_data:
            product = None
            sku = item.get('sku') or item.get('external_id')

            if sku:
                product = self.env['product.product'].search([
                    '|',
                    ('default_code', '=', sku),
                    ('barcode', '=', sku),
                ], limit=1)

            Line.create({
                'order_id': self.id,
                'external_product_id': str(item.get('id') or ''),
                'product_id': product.id if product else False,
                'sku': sku,
                'name': item.get('name') or _('Unknown Product'),
                'quantity': float(item.get('quantity') or 1),
                # ціни Prom.ua приходять рядком разом з валютою
                'price_unit': Backend._prom_parse_amount(item.get('price')),
                'discount': float(item.get('discount') or 0),
            })


class MarketplaceOrderCancelWizardProm(models.TransientModel):
    """Extend cancel wizard with Prom-specific cancel reasons."""
    _inherit = 'marketplace.order.cancel.wizard'

    @api.model
    def _get_cancel_reasons(self):
        """Override to add Prom-specific cancel reasons when applicable."""
        reasons = super()._get_cancel_reasons()

        # Check if any order is from Prom.ua
        order_ids = self.env.context.get('default_order_ids')
        if order_ids:
            orders = self.env['marketplace.order'].browse(
                order_ids[0][2] if isinstance(order_ids[0], (list, tuple)) else order_ids
            )
            if any(o.marketplace_type == 'prom' for o in orders):
                # Return Prom-specific reasons
                return PROM_CANCEL_REASONS

        return reasons
