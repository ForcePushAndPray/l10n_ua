import contextlib
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

import pytz
import requests
from lxml import etree

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module

_logger = logging.getLogger(__name__)

# API бізнес-кабінету NovaPay (SOAP 1.1).
NOVAPAY_API_URL = 'https://business.novapay.ua/Services/ClientAPIService.svc'
NOVAPAY_API_URL_PARAM = 'l10n_ua_bank_novapay.api_url'
NOVAPAY_SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
NOVAPAY_TEM_NS = 'http://tempuri.org/'
NOVAPAY_ACTION_BASE = 'http://tempuri.org/IClientAPIService/'
NOVAPAY_TIMEOUT = 60
# Дати в запитах і у виписці — дд.мм.рррр.
NOVAPAY_DATE_FORMAT = '%d.%m.%Y'
# Час дії JWT приходить без часового поясу; вважаємо його київським — це
# обережніше припущення (для UTC токен просто оновиться раніше).
NOVAPAY_TZ = 'Europe/Kyiv'
NOVAPAY_EXPIRATION_FORMATS = (
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d.%m.%Y %H:%M:%S')
# Запас до закінчення дії JWT, щоб не почати виписку з майже простроченим.
NOVAPAY_JWT_MARGIN = timedelta(minutes=5)


class L10nUaBankSyncConfig(models.Model):
    """Провайдер NovaPay: виписки через API бізнес-кабінету.

    Авторизація — JWT (`UserAuthenticationJWT`) за логіном, refresh-токеном і
    відкритим сертифікатом, згенерованими в кабінеті (Система → Налаштування →
    API). Refresh-токен одноразовий: кожна авторизація повертає нову пару
    токен/сертифікат, яку зберігає `l10n_ua.bank.novapay.session`.
    """
    _inherit = 'l10n_ua.bank.sync.config'

    provider = fields.Selection(
        selection_add=[('novapay', 'NovaPay')],
        ondelete={'novapay': 'set default'},
    )

    novapay_login = fields.Char(
        string='Login',
        help='Login of the NovaPay Business cabinet user (business.novapay.ua).',
    )
    novapay_refresh_token = fields.Char(
        string='Refresh Token',
        groups='l10n_ua_account_base.group_ua_manager',
        help='Generated in the cabinet: System → Settings → API. The token '
             'is single-use: after the first connection the module keeps '
             'the renewed token itself. Paste a new one here only after '
             'generating it again in the cabinet.',
    )
    novapay_public_certificate = fields.Text(
        string='Public Certificate',
        groups='l10n_ua_account_base.group_ua_manager',
        help='Public certificate generated together with the refresh token.',
    )
    novapay_client_id = fields.Char(
        string='Client ID',
        help='NovaPay identifier of the company (optional, fetched '
             'automatically by the IBAN of the journal).',
    )
    novapay_account_id = fields.Char(
        string='Account ID',
        help='NovaPay identifier of the account (optional, fetched '
             'automatically by the IBAN of the journal).',
    )

    # ------------------------------------------------------------------
    # SOAP-транспорт
    # ------------------------------------------------------------------
    @staticmethod
    def _novapay_norm_iban(value):
        return (value or '').replace(' ', '').upper()

    def _novapay_iban(self):
        self.ensure_one()
        return self._novapay_norm_iban(self.bank_account_id.acc_number)

    def _novapay_api_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            NOVAPAY_API_URL_PARAM) or NOVAPAY_API_URL

    @staticmethod
    def _novapay_envelope(method, params):
        body = ''.join(
            '<tem:%s>%s</tem:%s>' % (key, escape(str(value)), key)
            for key, value in params.items()
            if value not in (None, False, ''))
        return (
            '<soapenv:Envelope xmlns:soapenv="%s" xmlns:tem="%s">'
            '<soapenv:Header/><soapenv:Body>'
            '<tem:%s><tem:request>%s</tem:request></tem:%s>'
            '</soapenv:Body></soapenv:Envelope>'
        ) % (NOVAPAY_SOAP_NS, NOVAPAY_TEM_NS, method, body, method)

    @staticmethod
    def _novapay_xml(text):
        """Розібрати XML без зовнішніх сутностей і звернень у мережу."""
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        if isinstance(text, str):
            text = text.encode('utf-8')
        return etree.fromstring(text, parser)

    @staticmethod
    def _novapay_tag(node):
        return etree.QName(node).localname if isinstance(node.tag, str) else ''

    def _novapay_node_value(self, node):
        """Вузол → текст або словник; однойменні сусіди збираються у список."""
        children = [child for child in node if isinstance(child.tag, str)]
        if not children:
            return (node.text or '').strip()
        result = {}
        for child in children:
            name = self._novapay_tag(child)
            value = self._novapay_node_value(child)
            if name in result:
                if not isinstance(result[name], list):
                    result[name] = [result[name]]
                result[name].append(value)
            else:
                result[name] = value
        return result

    @staticmethod
    def _novapay_error_text(error):
        if isinstance(error, dict):
            return error.get('title') or error.get('status') or str(error)
        return str(error or '')

    def _novapay_call(self, method, params):
        """Викликати метод API і повернути вміст `<Method>Result` словником."""
        payload = dict(params)
        payload.setdefault('request_ref', str(uuid.uuid4()))
        envelope = self._novapay_envelope(method, payload)
        _logger.info('NovaPay: calling %s', method)
        try:
            response = requests.post(
                self._novapay_api_url(),
                data=envelope.encode('utf-8'),
                headers={
                    'Content-Type': 'text/xml; charset=utf-8',
                    'SOAPAction': NOVAPAY_ACTION_BASE + method,
                },
                timeout=NOVAPAY_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise UserError(_('NovaPay connection failed: %s') % e)

        try:
            root = self._novapay_xml(response.content)
        except etree.XMLSyntaxError:
            raise UserError(_(
                'NovaPay API returned an unexpected response (HTTP %(code)s): '
                '%(text)s', code=response.status_code,
                text=(response.text or '')[:300]))

        result = None
        fault = None
        for node in root.iter():
            name = self._novapay_tag(node)
            if name == method + 'Result':
                result = node
                break
            if name == 'faultstring':
                fault = (node.text or '').strip()
        if result is None:
            raise UserError(_(
                'NovaPay API error (HTTP %(code)s): %(text)s',
                code=response.status_code,
                text=fault or (response.text or '')[:300]))

        data = self._novapay_node_value(result)
        if not isinstance(data, dict):
            data = {}
        # Вкладений XML (виписка) приходить текстом/CDATA; якщо сервер віддав
        # його дочірніми вузлами — повертаємо їх так само рядком.
        for child in result:
            if self._novapay_tag(child) == 'extract' and len(child):
                data['extract'] = etree.tostring(child[0], encoding='unicode')
        if data.get('error') or data.get('result') == 'error':
            raise UserError(_(
                'NovaPay API error in %(method)s: %(text)s', method=method,
                text=self._novapay_error_text(data.get('error')) or _('unknown error')))
        return data

    # ------------------------------------------------------------------
    # Авторизація (JWT + ротація refresh-токена)
    # ------------------------------------------------------------------
    @contextlib.contextmanager
    def _novapay_session_env(self):
        """Середовище з власним курсором для стану авторизації.

        Комміт окремо від основної транзакції зберігає оновлений токен навіть
        тоді, коли синхронізація далі впаде й відкотиться. У тестах окремий
        курсор не бачить незакомічених записів, тож працюємо в основному.
        """
        if odoo_module.current_test:
            yield self.env
            return
        with self.env.registry.cursor() as cr:
            yield self.env(cr=cr)

    @staticmethod
    def _novapay_parse_expiration(value):
        """Час дії JWT → naive UTC або False, якщо формат без часу/невідомий."""
        value = (value or '').strip()
        for fmt in NOVAPAY_EXPIRATION_FORMATS:
            try:
                local = datetime.strptime(value[:19], fmt)
            except ValueError:
                continue
            return (pytz.timezone(NOVAPAY_TZ).localize(local)
                    .astimezone(pytz.utc).replace(tzinfo=None))
        return False

    def _novapay_jwt(self, force=False):
        """Повернути (jwt, cached): чинний JWT із кешу або нова авторизація."""
        self.ensure_one()
        config = self.sudo()
        if not config.novapay_login:
            raise UserError(_('Please configure NovaPay login'))
        seed = config.novapay_refresh_token
        if not seed or not config.novapay_public_certificate:
            raise UserError(_(
                'Please configure NovaPay refresh token and public certificate '
                '(cabinet: System → Settings → API)'))

        with self._novapay_session_env() as env:
            Session = env['l10n_ua.bank.novapay.session'].sudo()
            # Блокування рядка: одноразовий токен не можна витратити двічі
            # з паралельних синхронізацій.
            env.cr.execute(
                'SELECT id FROM l10n_ua_bank_novapay_session '
                'WHERE config_id = %s FOR UPDATE', [self.id])
            row = env.cr.fetchone()
            session = Session.browse(row[0]) if row else Session
            # Користувач вставив новий токен — починаємо ланцюжок заново.
            chained = bool(session) and session.seed_token == seed

            if (chained and not force and session.jwt and session.jwt_expiration
                    and session.jwt_expiration > fields.Datetime.now() + NOVAPAY_JWT_MARGIN):
                return session.jwt, True

            try:
                data = self._novapay_call('UserAuthenticationJWT', {
                    'refresh_token': session.refresh_token if chained else seed,
                    'login': config.novapay_login,
                    'public_certificate': (
                        session.public_certificate if chained
                        else config.novapay_public_certificate),
                })
            except UserError as e:
                raise UserError(_(
                    '%s\n\nIf the refresh token is no longer valid, generate '
                    'a new token and certificate in the NovaPay cabinet '
                    '(System → Settings → API) and paste them into the '
                    'connection.') % e)
            jwt = data.get('jwt')
            if not jwt or not isinstance(jwt, str):
                raise UserError(_('NovaPay API did not return a JWT token'))
            vals = {
                'seed_token': seed,
                'refresh_token': data.get('refresh_token') or False,
                'public_certificate': data.get('public_certificate') or False,
                'jwt': jwt,
                'jwt_expiration': self._novapay_parse_expiration(
                    data.get('expiration')),
            }
            if session:
                session.write(vals)
            else:
                Session.create(dict(vals, config_id=self.id))
            return jwt, False

    def _novapay_api(self, method, params=None):
        """Виклик методу з JWT; прострочений кешований JWT оновлюється раз."""
        self.ensure_one()
        jwt, cached = self._novapay_jwt()
        try:
            return self._novapay_call(method, dict(params or {}, jwt=jwt))
        except UserError:
            if not cached:
                raise
            jwt, _cached = self._novapay_jwt(force=True)
            return self._novapay_call(method, dict(params or {}, jwt=jwt))

    # ------------------------------------------------------------------
    # Рахунки
    # ------------------------------------------------------------------
    @staticmethod
    def _novapay_items(data, wrapper, item):
        """Колекція `<wrapper><item>…</item>…</wrapper>` → список словників."""
        items = (data.get(wrapper) or {})
        items = items.get(item) if isinstance(items, dict) else None
        if isinstance(items, dict):
            return [items]
        return [i for i in (items or []) if isinstance(i, dict)]

    def _novapay_list_accounts(self):
        """Усі рахунки всіх підприємств користувача."""
        self.ensure_one()
        accounts = []
        clients = self._novapay_items(
            self._novapay_api('GetClientsList'), 'clients', 'Clients')
        for client in clients:
            data = self._novapay_api(
                'GetAccountsList', {'client_id': client.get('id')})
            for account in self._novapay_items(data, 'accounts', 'Accounts'):
                accounts.append({
                    'client_id': str(client.get('id') or ''),
                    'client_name': client.get('name') or '',
                    'account_id': str(account.get('id') or ''),
                    'iban': self._novapay_norm_iban(account.get('IBAN')),
                    'currency': account.get('currency') or '',
                    'status': account.get('statuscode') or '',
                })
        return accounts

    def _novapay_resolve_account(self):
        """ID рахунку NovaPay: збережений або знайдений за IBAN журналу."""
        self.ensure_one()
        if self.novapay_account_id:
            return self.novapay_account_id
        iban = self._novapay_iban()
        if not iban:
            raise UserError(_(
                'Set the IBAN on the bank journal or fill in the NovaPay '
                'Account ID manually'))
        accounts = self._novapay_list_accounts()
        match = next((a for a in accounts if a['iban'] == iban), None)
        if not match:
            raise UserError(_(
                'Account %(iban)s is not among NovaPay accounts: %(list)s',
                iban=iban,
                list=', '.join(a['iban'] for a in accounts) or '-'))
        self.write({
            'novapay_client_id': match['client_id'],
            'novapay_account_id': match['account_id'],
        })
        return match['account_id']

    # ------------------------------------------------------------------
    # Виписка
    # ------------------------------------------------------------------
    def _fetch_from_bank(self, date_from, date_to):
        """Виписка рахунку (GetAccountExtract) та обороти за період."""
        self.ensure_one()

        if self.provider != 'novapay':
            return super()._fetch_from_bank(date_from, date_to)

        account_id = self._novapay_resolve_account()
        period = {
            'account_id': account_id,
            'date_from': date_from.strftime(NOVAPAY_DATE_FORMAT),
            'date_to': date_to.strftime(NOVAPAY_DATE_FORMAT),
        }
        data = self._novapay_api('GetAccountExtract', period)
        extract = data.get('extract')

        # Залишки на початок/кінець беремо з оборотів; без них виписка
        # сформується з виведеним (не звіреним) кінцевим балансом.
        turns = []
        try:
            turns = self._novapay_items(
                self._novapay_api('GetAccountTurns', period), 'turns', 'Turns')
        except UserError as e:
            _logger.warning('NovaPay: account turns unavailable: %s', e)

        return {
            'api_type': 'extract',
            'account_id': account_id,
            'iban': self._novapay_iban(),
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'extract': extract if isinstance(extract, str) else '',
            'turns': turns,
        }

    @staticmethod
    def _novapay_amount(value):
        """Сума: число або рядок ('1250.00', '1 250,5')."""
        if isinstance(value, (int, float)):
            return float(value)
        text = (str(value or '').replace(' ', '').replace('\xa0', '')
                .replace(',', '.'))
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _novapay_date(value):
        try:
            return datetime.strptime(
                (value or '').strip()[:10], NOVAPAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _novapay_extract_docs(self, raw_data):
        """XML виписки → (IBAN рахунку, список документів-словників)."""
        extract = (raw_data or {}).get('extract')
        if not extract:
            return '', []
        try:
            root = self._novapay_xml(extract)
        except etree.XMLSyntaxError as e:
            raise UserError(_('Cannot parse NovaPay statement XML: %s') % e)
        iban = ''
        docs = []
        for node in root.iter():
            name = self._novapay_tag(node)
            if name == 'IBAN' and not iban:
                iban = self._novapay_norm_iban(node.text)
            elif name == 'Docs':
                doc = dict(node.attrib)
                for child in node:
                    if isinstance(child.tag, str):
                        doc[self._novapay_tag(child)] = (child.text or '').strip()
                docs.append(doc)
        return iban, docs

    def _parse_transactions(self, raw_data):
        """Документи виписки NovaPay → словники транзакцій (Кт +, Дт −)."""
        self.ensure_one()

        if self.provider != 'novapay':
            return super()._parse_transactions(raw_data)

        head_iban, docs = self._novapay_extract_docs(raw_data)
        own_iban = head_iban or self._novapay_norm_iban(
            (raw_data or {}).get('iban')) or self._novapay_iban()
        own_code = (self.company_id.partner_id.edrpou or '').strip()

        transactions = []
        seen = {}
        for doc in docs:
            amount = self._novapay_amount(doc.get('Amount'))
            if not amount:
                continue
            debit_iban = self._novapay_norm_iban(doc.get('DebitCodeIBAN'))
            credit_iban = self._novapay_norm_iban(doc.get('CreditCodeIBAN'))
            debit_code = (doc.get('DebitStateCode') or '').strip()
            credit_code = (doc.get('CreditStateCode') or '').strip()
            # У виписці сума без знака: напрям визначає сторона, на якій
            # стоїть наш рахунок (за IBAN, запасний варіант — за ЄДРПОУ).
            if own_iban and own_iban in (debit_iban, credit_iban) \
                    and debit_iban != credit_iban:
                outgoing = debit_iban == own_iban
            elif own_code and own_code in (debit_code, credit_code) \
                    and debit_code != credit_code:
                outgoing = debit_code == own_code
            else:
                raise UserError(_(
                    'Cannot determine the direction of NovaPay document '
                    '%(code)s dated %(date)s: neither side matches account '
                    '%(iban)s. Check the IBAN of the bank journal.',
                    code=doc.get('Code') or '-',
                    date=doc.get('PayDate') or doc.get('OrgDate') or '-',
                    iban=own_iban or '-'))

            date = (self._novapay_date(doc.get('PayDate'))
                    or self._novapay_date(doc.get('OrgDate')))
            date = date.isoformat() if date else ''
            code = (doc.get('Code') or '').strip()
            purpose = doc.get('Purpose') or ''
            # У документа немає унікального ID: ключ дедуплікації складаємо
            # з реквізитів, однакові документи одного дня нумеруємо.
            key = '|'.join([code, date, '%.2f' % amount, debit_iban,
                            credit_iban, purpose])
            index = seen.get(key, 0)
            seen[key] = index + 1
            uid = 'NP-' + hashlib.sha1(
                ('%s|%d' % (key, index)).encode('utf-8')).hexdigest()[:24]

            side = 'Credit' if outgoing else 'Debit'
            transactions.append({
                'id': uid,
                'date': date,
                'amount': -abs(amount) if outgoing else abs(amount),
                'description': purpose,
                'partner_name': doc.get(side + 'Name') or '',
                'partner_iban': credit_iban if outgoing else debit_iban,
                'partner_edrpou': credit_code if outgoing else debit_code,
            })
        return transactions

    def _extract_balances(self, raw_data):
        """Залишки з оборотів: вхідний першого дня, вихідний останнього."""
        if self.provider != 'novapay':
            return super()._extract_balances(raw_data)

        rows = []
        for turn in (raw_data or {}).get('turns') or []:
            date = self._novapay_date(turn.get('date'))
            opening = self._novapay_amount(turn.get('InRest'))
            closing = self._novapay_amount(turn.get('CrncyRest'))
            if date and opening is not None and closing is not None:
                rows.append((date, opening, closing))
        if not rows:
            return (None, None)
        rows.sort(key=lambda row: row[0])
        return (rows[0][1], rows[-1][2])

    # ------------------------------------------------------------------
    # Дії користувача
    # ------------------------------------------------------------------
    @staticmethod
    def _novapay_notify(title, message, kind, sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': kind,
                'sticky': sticky,
            },
        }

    def action_test_connection(self):
        """Перевірити авторизацію NovaPay і показати доступні підприємства."""
        self.ensure_one()

        if self.provider != 'novapay':
            return super().action_test_connection()

        clients = self._novapay_items(
            self._novapay_api('GetClientsList'), 'clients', 'Clients')
        names = ', '.join(c.get('name') or '' for c in clients) or '-'
        return self._novapay_notify(
            _('Success'),
            _('Connected to NovaPay. Companies: %s') % names,
            'success')

    def action_novapay_fetch_accounts(self):
        """Показати рахунки NovaPay і запам'ятати рахунок журналу за IBAN."""
        self.ensure_one()
        accounts = self._novapay_list_accounts()
        iban = self._novapay_iban()
        match = next((a for a in accounts if iban and a['iban'] == iban), None)
        if match:
            self.write({
                'novapay_client_id': match['client_id'],
                'novapay_account_id': match['account_id'],
            })
        lines = [
            '%s | %s | %s | ID: %s%s' % (
                a['iban'], a['currency'], a['status'], a['account_id'],
                ' ✓' if a is match else '')
            for a in accounts
        ]
        return self._novapay_notify(
            _('Available Accounts'),
            '\n'.join(lines) or _('No accounts found'),
            'info', sticky=True)
