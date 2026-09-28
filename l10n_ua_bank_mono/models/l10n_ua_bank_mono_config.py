import logging
import requests
from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# monobank API base URL
MONO_API_URL = "https://api.monobank.ua"
# Corporate API for legal entities: https://corp-api.monobank.ua/
MONO_CORP_API_URL = "https://corp-api.monobank.ua"
# The corporate statement returns 10 items unless asked for more; 500 is the cap.
MONO_CORP_PAGE_SIZE = 500
# A runaway loop guard: 200 pages is 100 000 operations in one period.
MONO_CORP_MAX_PAGES = 200
KYIV_TZ = ZoneInfo('Europe/Kyiv')


class L10nUaBankSyncConfig(models.Model):
    """Extend base config with monobank provider."""
    _inherit = 'l10n_ua.bank.sync.config'

    provider = fields.Selection(
        selection_add=[('mono', 'monobank')],
        ondelete={'mono': 'set default'},
    )

    mono_api_type = fields.Selection(
        [
            ('personal', 'Personal API (individual entrepreneur)'),
            ('corporate', 'Corporate API (legal entity)'),
        ],
        string='API Type',
        default='personal',
        tracking=True,
        help='Personal API (api.monobank.ua) serves individuals and individual '
             'entrepreneurs, with a token from the monobank app. Corporate API '
             '(corp-api.monobank.ua) serves legal entities, with a token issued '
             'for the company in the monobank web cabinet.',
    )

    # monobank API Credentials
    mono_api_token = fields.Char(
        string='API Token',
        help='Personal API: token from monobank settings (Настройки → API). '
             'Corporate API: company token from web.monobank.ua.',
    )
    mono_account_id = fields.Char(
        string='Account ID',
        help='Personal API: monobank account ID (optional, fetched '
             'automatically). Corporate API: account IBAN (optional, the IBAN '
             'of the journal bank account is used by default).',
    )

    # Webhook
    mono_webhook_url = fields.Char(
        string='Webhook URL',
        compute='_compute_mono_webhook_url',
    )
    mono_webhook_active = fields.Boolean(
        string='Webhook Active',
        default=False,
    )

    @api.depends_context('company')
    def _compute_mono_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.mono_webhook_url = f'{base_url}/l10n_ua_bank_mono/webhook/{record.id}'

    def _fetch_from_bank(self, date_from, date_to):
        """Fetch statements from monobank API."""
        self.ensure_one()

        if self.provider != 'mono':
            return super()._fetch_from_bank(date_from, date_to)

        if not self.mono_api_token:
            raise UserError(_("Please configure monobank API Token"))

        # monobank API limits to 31 days
        days_diff = (date_to - date_from).days
        if days_diff > 31:
            raise UserError(_("monobank API allows maximum 31 days per request"))

        if self.mono_api_type == 'corporate':
            return self._mono_corp_fetch_statement(date_from, date_to)

        # Get account ID if not set
        account_id = self.mono_account_id
        if not account_id:
            account_id = self._mono_get_default_account()
            if account_id:
                self.mono_account_id = account_id

        if not account_id:
            raise UserError(_("Could not determine monobank account ID"))

        # Convert dates to timestamps
        from_ts = int(datetime.combine(date_from, datetime.min.time()).timestamp())
        to_ts = int(datetime.combine(date_to, datetime.max.time()).timestamp())

        url = f"{MONO_API_URL}/personal/statement/{account_id}/{from_ts}/{to_ts}"

        headers = {
            'X-Token': self.mono_api_token,
        }

        _logger.info("monobank: Fetching %s", url)

        response = requests.get(url, headers=headers, timeout=60)

        _logger.info("monobank: Response status %s", response.status_code)

        if response.status_code == 429:
            raise UserError(_("monobank API rate limit exceeded. Please wait 60 seconds."))

        if response.status_code != 200:
            raise UserError(_("monobank API error: %s") % response.text)

        data = response.json()

        return {
            'api_type': 'statement',
            'account_id': account_id,
            'from_ts': from_ts,
            'to_ts': to_ts,
            'response': data,
        }

    def _mono_get_default_account(self):
        """Get default (first UAH) account from client info."""
        url = f"{MONO_API_URL}/personal/client-info"
        headers = {'X-Token': self.mono_api_token}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                accounts = data.get('accounts', [])
                # Find UAH account (currency code 980)
                for acc in accounts:
                    if acc.get('currencyCode') == 980:
                        return acc.get('id')
                # Fallback to first account
                if accounts:
                    return accounts[0].get('id')
        except Exception as e:
            _logger.error("monobank: Failed to get client info: %s", str(e))

        return None

    def _parse_transactions(self, raw_data):
        """Parse monobank API response into transaction list."""
        self.ensure_one()

        if self.provider != 'mono':
            return super()._parse_transactions(raw_data)

        if raw_data.get('api_type') == 'corp_statement':
            return self._mono_corp_parse(raw_data)

        transactions = []
        items = raw_data.get('response', [])

        if not isinstance(items, list):
            return []

        for item in items:
            # monobank amounts are in kopeks (cents) and already signed:
            # - Positive = incoming (credit to account, Кт)
            # - Negative = outgoing (debit from account, Дт)
            amount = item.get('amount', 0) / 100.0

            # Get transaction time
            trans_time = item.get('time', 0)
            if trans_time:
                trans_date = datetime.fromtimestamp(trans_time).strftime('%Y-%m-%d')
            else:
                trans_date = ''

            trans = {
                'id': item.get('id', ''),
                'date': trans_date,
                'amount': amount,
                'description': item.get('description', ''),
                'partner_name': item.get('counterName', ''),
                'partner_iban': item.get('counterIban', ''),
                'partner_edrpou': item.get('counterEdrpou', ''),
            }
            transactions.append(trans)

        return transactions

    def action_test_connection(self):
        """Test monobank API connection."""
        self.ensure_one()

        if self.provider != 'mono':
            return super().action_test_connection()

        if not self.mono_api_token:
            raise UserError(_("Please configure API Token"))

        if self.mono_api_type == 'corporate':
            return self._mono_corp_test_connection()

        try:
            url = f"{MONO_API_URL}/personal/client-info"
            headers = {'X-Token': self.mono_api_token}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                client_name = data.get('name', 'Unknown')
                accounts_count = len(data.get('accounts', []))

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connected to monobank. Client: %s, Accounts: %d') % (client_name, accounts_count),
                        'type': 'success',
                    }
                }
            elif response.status_code == 429:
                raise UserError(_("Rate limit exceeded. Please wait 60 seconds."))
            else:
                raise UserError(_("API returned error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            raise UserError(_("Connection failed: %s") % str(e))

    def action_fetch_accounts(self):
        """Fetch available accounts from monobank."""
        self.ensure_one()

        if not self.mono_api_token:
            raise UserError(_("Please configure API Token"))

        if self.mono_api_type == 'corporate':
            return self._mono_corp_fetch_accounts()

        url = f"{MONO_API_URL}/personal/client-info"
        headers = {'X-Token': self.mono_api_token}

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            raise UserError(_("Failed to fetch accounts: %s") % response.text)

        data = response.json()
        accounts = data.get('accounts', [])

        # Format account list for display
        account_info = []
        for acc in accounts:
            currency = acc.get('currencyCode', 0)
            currency_name = 'UAH' if currency == 980 else str(currency)
            balance = acc.get('balance', 0) / 100.0
            account_info.append(f"ID: {acc.get('id')} | {currency_name} | Balance: {balance:.2f}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Available Accounts'),
                'message': '\n'.join(account_info) or _('No accounts found'),
                'type': 'info',
                'sticky': True,
            }
        }

    # --- Corporate API (legal entities) ---

    def _mono_corp_request(self, path, params=None):
        """GET a Corporate API resource and return its decoded JSON."""
        self.ensure_one()
        url = f"{MONO_CORP_API_URL}{path}"
        headers = {
            'x-token': self.mono_api_token,
            'accept': 'application/json',
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
        except requests.exceptions.RequestException as e:
            raise UserError(_("Connection failed: %s") % str(e))

        _logger.info("monobank corporate: %s -> %s", path, response.status_code)

        if response.status_code == 429:
            # Limits are per company; the bank says when the next call may go.
            retry_after = response.headers.get('x-rate-limit-retry-after-seconds')
            raise UserError(_(
                "monobank API rate limit exceeded. Retry in %s seconds."
            ) % (retry_after or 60))

        if response.status_code != 200:
            try:
                error = response.json()
                message = error.get('errorDescription') or error.get('errorCode')
            except ValueError:
                message = None
            raise UserError(_("monobank API error: %s") % (message or response.text))

        return response.json()

    def _mono_corp_iban(self):
        """IBAN of the account to read: set explicitly, or the journal's."""
        self.ensure_one()
        iban = (self.mono_account_id or self.bank_account_id.acc_number or '')
        iban = iban.replace(' ', '').upper()
        if not iban:
            raise UserError(_(
                "Set the account IBAN or a bank account on the journal to read "
                "the monobank corporate statement."))
        return iban

    def _mono_corp_fetch_statement(self, date_from, date_to):
        """Read the whole period, page by page.

        A page holds at most 500 operations. The bank's day is the Kyiv one,
        so the period bounds are taken in Kyiv time, whatever the server's
        timezone is.
        """
        iban = self._mono_corp_iban()
        from_ts = int(datetime.combine(date_from, time.min, tzinfo=KYIV_TZ).timestamp())
        to_ts = int(datetime.combine(date_to, time.max, tzinfo=KYIV_TZ).timestamp())

        items, seen = [], set()
        low, high = from_ts, to_ts
        for _page in range(MONO_CORP_MAX_PAGES):
            page = self._mono_corp_request(
                f"/ext/v1/statement/{iban}/{low}/{high}",
                params={'limit': MONO_CORP_PAGE_SIZE})
            if not isinstance(page, list):
                raise UserError(_("monobank API error: %s") % page)
            new = [item for item in page if item.get('id') not in seen]
            for item in new:
                seen.add(item.get('id'))
                items.append(item)
            if len(page) < MONO_CORP_PAGE_SIZE or not new:
                break
            # Operations come ordered by time. Continue past the last one
            # received, from whichever end of the period the page started;
            # the ones sharing its second come again and are dropped above.
            first, last = page[0].get('time') or 0, page[-1].get('time') or 0
            if first <= last:
                low = last
            else:
                high = last
        else:
            raise UserError(_(
                "monobank statement for %s has more than %s pages; shorten the "
                "period.") % (iban, MONO_CORP_MAX_PAGES))

        return {
            'api_type': 'corp_statement',
            'account_id': iban,
            'from_ts': from_ts,
            'to_ts': to_ts,
            'response': items,
        }

    def _mono_corp_parse(self, raw_data):
        """Corporate statement items into the bank_sync transaction dicts."""
        transactions = []
        for item in raw_data.get('response') or []:
            # PENDING is not booked yet and DECLINED never will be. A pending
            # operation is picked up by a later sync once it is DONE: lines are
            # deduplicated by id, so overlapping periods are safe.
            if item.get('status', 'DONE') != 'DONE':
                continue
            booked = item.get('completedTime') or item.get('time')
            transactions.append({
                'id': item.get('id', ''),
                'date': (datetime.fromtimestamp(booked, KYIV_TZ).strftime('%Y-%m-%d')
                         if booked else ''),
                # Signed kopecks: positive is incoming, negative outgoing.
                'amount': (item.get('amount') or 0) / 100.0,
                'description': item.get('description', ''),
                'partner_name': item.get('counterName', ''),
                'partner_iban': item.get('counterIban', ''),
                'partner_edrpou': item.get('counterEdrpou', ''),
            })
        return transactions

    def _mono_corp_currency_name(self, code):
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('iso_numeric', '=', int(code or 0))], limit=1)
        return currency.name or str(code)

    def _mono_corp_test_connection(self):
        accounts = self._mono_corp_request('/ext/v1/accounts')
        ibans = [acc.get('iban') for acc in accounts]
        own = (self.mono_account_id or self.bank_account_id.acc_number or '')
        own = own.replace(' ', '').upper()
        if own and own not in ibans:
            message = _(
                "Connected to monobank corporate API, but account %(iban)s is "
                "not among the company's %(count)d accounts.",
                iban=own, count=len(accounts))
            kind = 'warning'
        else:
            message = _(
                "Connected to monobank corporate API. Accounts: %d",
                len(accounts))
            kind = 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success') if kind == 'success' else _('Warning'),
                'message': message,
                'type': kind,
            }
        }

    def _mono_corp_fetch_accounts(self):
        accounts = self._mono_corp_request('/ext/v1/accounts')
        # Corporate balances come in currency units, not in kopecks.
        account_info = [
            f"IBAN: {acc.get('iban')} | "
            f"{self._mono_corp_currency_name(acc.get('currency'))} | "
            f"Balance: {float(acc.get('balance') or 0):.2f}"
            for acc in accounts
        ]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Available Accounts'),
                'message': '\n'.join(account_info) or _('No accounts found'),
                'type': 'info',
                'sticky': True,
            }
        }
