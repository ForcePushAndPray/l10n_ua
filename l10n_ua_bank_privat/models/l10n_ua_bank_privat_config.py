import logging
import requests
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nUaBankSyncConfig(models.Model):
    """Extend base config with PrivatBank provider."""
    _inherit = 'l10n_ua.bank.sync.config'

    provider = fields.Selection(
        selection_add=[('privat', 'PrivatBank')],
        ondelete={'privat': 'set default'},
    )

    # PrivatBank API Credentials
    privat_api_token = fields.Char(
        string='API Token',
        help='Token from Privat24 Business Autoclient',
    )
    privat_account_iban = fields.Char(
        string='Account IBAN',
        help='Account IBAN (UA + 27 digits)',
    )

    # Legacy Merchant API
    privat_merchant_id = fields.Char(
        string='Merchant ID',
        help='Legacy merchant ID (for old API)',
    )
    privat_merchant_password = fields.Char(
        string='Merchant Password',
        help='Legacy merchant password (for old API)',
    )
    privat_card_number = fields.Char(
        string='Card Number',
        help='Card number for statement retrieval (16 digits)',
    )

    def _fetch_from_bank(self, date_from, date_to):
        """Fetch statements from PrivatBank API."""
        self.ensure_one()

        if self.provider != 'privat':
            return super()._fetch_from_bank(date_from, date_to)

        if self.privat_api_token:
            return self._privat_fetch_autoclient(date_from, date_to)
        elif self.privat_merchant_id:
            return self._privat_fetch_merchant(date_from, date_to)
        else:
            raise UserError(_("Please configure PrivatBank API Token or Merchant credentials"))

    def _privat_fetch_autoclient(self, date_from, date_to):
        """Fetch via Autoclient API (token-based)."""
        _logger.info("PrivatBank: Using Autoclient API")

        url = "https://acp.privatbank.ua/api/statements/transactions"

        headers = {
            'Content-Type': 'application/json',
            'token': self.privat_api_token,
        }

        params = {
            'startDate': date_from.strftime('%d-%m-%Y'),
            'endDate': date_to.strftime('%d-%m-%Y'),
        }

        if self.privat_account_iban:
            params['acc'] = self.privat_account_iban

        _logger.info("PrivatBank: Fetching %s with params %s", url, params)

        response = requests.get(url, headers=headers, params=params, timeout=60)

        _logger.info("PrivatBank: Response status %s", response.status_code)

        if response.status_code != 200:
            raise UserError(_("PrivatBank API error: %s") % response.text)

        data = response.json()

        # Return full response for storage
        return {
            'api_type': 'autoclient',
            'url': url,
            'params': params,
            'response': data,
        }

    def _privat_fetch_merchant(self, date_from, date_to):
        """Fetch via legacy Merchant API."""
        _logger.info("PrivatBank: Using Merchant API")

        if not self.privat_card_number:
            raise UserError(_("Card number is required for Merchant API"))

        url = "https://api.privatbank.ua/p24api/rest_fiz"

        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <request version="1.0">
            <merchant>
                <id>{self.privat_merchant_id}</id>
                <signature></signature>
            </merchant>
            <data>
                <oper>cmt</oper>
                <wait>0</wait>
                <test>0</test>
                <payment id="">
                    <prop name="sd" value="{date_from.strftime('%d.%m.%Y')}"/>
                    <prop name="ed" value="{date_to.strftime('%d.%m.%Y')}"/>
                    <prop name="card" value="{self.privat_card_number}"/>
                </payment>
            </data>
        </request>"""

        response = requests.post(url, data=xml_data, timeout=60)

        if response.status_code != 200:
            raise UserError(_("PrivatBank Merchant API error"))

        return {
            'api_type': 'merchant',
            'url': url,
            'response_text': response.text,
        }

    def _parse_transactions(self, raw_data):
        """Parse PrivatBank API response into transaction list."""
        self.ensure_one()

        if self.provider != 'privat':
            return super()._parse_transactions(raw_data)

        api_type = raw_data.get('api_type')

        if api_type == 'autoclient':
            return self._privat_parse_autoclient(raw_data.get('response', {}))
        elif api_type == 'merchant':
            return self._privat_parse_merchant(raw_data.get('response_text', ''))
        else:
            return []

    def _privat_parse_autoclient(self, data):
        """Parse Autoclient API response."""
        transactions = []

        # Handle different response formats
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get('transactions', []) or data.get('statements', []) or []
        else:
            return []

        for item in items:
            trans = {
                'id': item.get('ID') or item.get('REF') or item.get('id', ''),
                'date': item.get('DATE_TIME_DAT_OD_TIM_P') or item.get('TRANDATE') or item.get('date', ''),
                'amount': self._privat_parse_amount(item),
                'description': item.get('OSND') or item.get('purpose') or item.get('description', ''),
                'partner_name': item.get('CNTR_NAME') or item.get('AUT_CNTR_NAM', ''),
                'partner_iban': item.get('CNTR_ACC') or item.get('AUT_CNTR_ACC', ''),
                'partner_edrpou': item.get('CNTR_CRF') or item.get('AUT_CNTR_CRF', ''),
            }
            transactions.append(trans)

        return transactions

    def _privat_parse_merchant(self, xml_text):
        """Parse Merchant API XML response."""
        import xml.etree.ElementTree as ET

        transactions = []

        try:
            root = ET.fromstring(xml_text)

            for statement in root.findall('.//statement'):
                amount_str = statement.get('cardamount', '0')
                amount = self._privat_clean_amount(amount_str)

                trans = {
                    'id': statement.get('refp', ''),
                    'date': statement.get('trandate', ''),
                    'amount': amount,
                    'description': statement.get('description', ''),
                    'partner_name': '',
                    'partner_iban': '',
                    'partner_edrpou': '',
                }
                transactions.append(trans)

        except ET.ParseError as e:
            _logger.error("PrivatBank: XML parse error: %s", str(e))

        return transactions

    def _privat_parse_amount(self, item):
        """
        Parse amount from API response item.

        Returns signed amount:
        - Positive = incoming (credit to account, Кт)
        - Negative = outgoing (debit from account, Дт)

        PrivatBank Autoclient API uses TRANTYPE field:
        - TRANTYPE: "C" = Credit (incoming)
        - TRANTYPE: "D" = Debit (outgoing)
        """
        # Try different field names for amount
        amount_str = (
            item.get('SUM') or
            item.get('SUMA') or
            item.get('SUM_E') or
            item.get('amount') or
            item.get('cardamount') or
            '0'
        )
        amount = self._privat_clean_amount(amount_str)

        # Determine direction (debit/credit)

        # Method 1: Check TRANTYPE field (PrivatBank Autoclient API)
        # "C" = Credit (incoming), "D" = Debit (outgoing)
        trantype = str(item.get('TRANTYPE', '')).upper()
        if trantype == 'D':
            return -abs(amount)  # Debit = outgoing = negative
        elif trantype == 'C':
            return abs(amount)   # Credit = incoming = positive

        # Method 2: Check DEBIT flag (1 = outgoing/debit, 0 = incoming/credit)
        debit_flag = item.get('DEBIT')
        if debit_flag is not None:
            if str(debit_flag) == '1':
                return -abs(amount)  # Outgoing = negative
            else:
                return abs(amount)   # Incoming = positive

        # Method 3: Check BPL field ("D" = debit, "C" = credit)
        bpl = item.get('BPL', '').upper()
        if bpl == 'D':
            return -abs(amount)  # Debit = outgoing = negative
        elif bpl == 'C':
            return abs(amount)   # Credit = incoming = positive

        # Method 4: Check if amount string already has sign
        # (some API responses include "-" for outgoing)
        if isinstance(amount_str, str) and amount_str.strip().startswith('-'):
            return -abs(amount)

        # Method 5: Compare accounts - if MY_ACC is sender, it's outgoing
        my_acc = item.get('AUT_MY_ACC', '')
        # If OSND (description) contains patterns indicating outgoing
        osnd = str(item.get('OSND', '')).lower()
        if any(pattern in osnd for pattern in ['комісія', 'списання', 'оплата', 'переказ']):
            # Check if it's not an incoming transfer
            if 'зарахування' not in osnd and 'надходження' not in osnd:
                return -abs(amount)

        # Default: return positive (assume incoming if unknown)
        return abs(amount)

    def _privat_clean_amount(self, amount_str):
        """Clean and convert amount string to float."""
        if isinstance(amount_str, (int, float)):
            return float(amount_str)

        # Remove spaces, currency suffixes, convert comma to dot
        amount_str = str(amount_str).replace(' ', '').replace(',', '.')
        # Remove non-numeric characters except minus and dot
        cleaned = ''.join(c for c in amount_str if c.isdigit() or c in '.-')

        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def action_test_connection(self):
        """Test PrivatBank API connection."""
        self.ensure_one()

        if self.provider != 'privat':
            return super().action_test_connection() if hasattr(super(), 'action_test_connection') else None

        if not self.privat_api_token:
            raise UserError(_("Please configure API Token"))

        try:
            # Use balance endpoint with today's date
            url = "https://acp.privatbank.ua/api/statements/balance"
            headers = {
                'Content-Type': 'application/json',
                'token': self.privat_api_token,
            }
            today = datetime.now().strftime('%d-%m-%Y')
            params = {
                'startDate': today,
                'endDate': today,
            }
            if self.privat_account_iban:
                params['acc'] = self.privat_account_iban

            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                # Try to get account info from response
                balances = data.get('balances', [])
                if balances:
                    acc_info = balances[0]
                    message = _('Connected! Account: %s, Balance: %s %s') % (
                        acc_info.get('acc', 'N/A'),
                        acc_info.get('balanceOut', 'N/A'),
                        acc_info.get('currency', 'UAH'),
                    )
                else:
                    message = _('Connection to PrivatBank API successful!')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': message,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("API returned error: %s") % response.text)

        except requests.exceptions.RequestException as e:
            raise UserError(_("Connection failed: %s") % str(e))
