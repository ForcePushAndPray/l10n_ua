import re

from odoo import api, models

from odoo.addons.l10n_ua_account_base.tools.formatters import (
    amount_to_words_ua,
    format_date_ua,
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_ua_report_lines(self):
        """Return product lines only: no sections, subsections or notes."""
        return self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

    def _get_ua_doc_date(self):
        """Document date: invoice date, for drafts without it the accounting date."""
        return self.invoice_date or self.date

    def _get_ua_date_formatted(self, dt=None):
        """Format date in Ukrainian long format: «15» січня 2026 р."""
        text = format_date_ua(dt or self._get_ua_doc_date())
        return re.sub(r'^"(\d+)"', r'«\1»', text)

    def _get_ua_date_short(self, dt):
        """Format date as 15.01.2026, empty string for no date."""
        return format_date_ua(dt, 'short')

    def _get_ua_tax_amount_words(self):
        """Amount in words for VAT portion."""
        if self.amount_tax and self.currency_id.name == 'UAH':
            return amount_to_words_ua(self.amount_tax)
        return ''

    def _get_ua_report_lang(self):
        """Ukrainian documents are printed in Ukrainian whenever it is installed."""
        if 'uk_UA' in dict(self.env['res.lang'].get_installed()):
            return 'uk_UA'
        return self.partner_id.lang or self.env.lang

    def _get_ua_bank_account(self):
        """Company bank account to print: the one chosen on the invoice,
        otherwise the first company account in the invoice currency
        (an account without currency is in the company currency)."""
        self.ensure_one()
        if self.partner_bank_id:
            return self.partner_bank_id
        company_currency = self.company_id.currency_id
        accounts = self.company_id.partner_id.bank_ids
        return accounts.filtered(
            lambda a: (a.currency_id or company_currency) == self.currency_id
        )[:1] or accounts[:1]

    def _get_ua_bank_mfo(self, partner_bank):
        """MFO of the bank. `res.bank.bic` holds the SWIFT code, so the MFO
        comes from `ua_mfo` (l10n_ua_bank_sync) or from the UA IBAN itself,
        where positions 5-10 are the bank MFO."""
        bank = partner_bank.bank_id
        if bank and 'ua_mfo' in bank._fields and bank.ua_mfo:
            return bank.ua_mfo
        iban = re.sub(r'\s', '', partner_bank.acc_number or '').upper()
        if len(iban) == 29 and iban.startswith('UA'):
            return iban[4:10]
        return ''

    def _get_ua_bank_line(self, partner_bank):
        """'в банку АТ «Тестовий банк», МФО 123456'"""
        parts = []
        if partner_bank.bank_id:
            parts.append('в банку %s' % partner_bank.bank_id.name)
        mfo = self._get_ua_bank_mfo(partner_bank)
        if mfo:
            parts.append('МФО %s' % mfo)
        return ', '.join(parts)

    def _get_ua_partner_address(self, partner):
        """Legal address, falling back to the regular partner address."""
        if partner.l10n_ua_legal_address:
            return partner.l10n_ua_legal_address
        parts = [
            partner.street, partner.street2, partner.zip, partner.city,
            partner.state_id.name, partner.country_id.name,
        ]
        return ', '.join(p for p in parts if p)

    def _get_ua_partner_codes(self, partner, show_vat_payer=False):
        """'ЄДРПОУ: 12345678, ІПН: 1234567899, платник ПДВ'"""
        parts = []
        if partner.edrpou:
            parts.append('ЄДРПОУ: %s' % partner.edrpou)
        if partner.ipn:
            parts.append('ІПН: %s' % partner.ipn)
        if show_vat_payer and partner.is_vat_payer:
            parts.append('платник ПДВ')
        return ', '.join(parts)

    @api.model
    def _ua_format_number(self, value, digits=2):
        """1234567.5 -> '1 234 567,50' (non-breaking space between thousands)."""
        return f'{value or 0.0:,.{digits}f}'.replace(',', '\u00a0').replace('.', ',')

    @api.model
    def _ua_format_quantity(self, value):
        """79.75 -> '79,75', 2.0 -> '2'."""
        return self._ua_format_number(value, 3).rstrip('0').rstrip(',')

    @api.model
    def _ua_format_price(self, value):
        """Unit price with the 'Product Price' precision, at least 2 decimals."""
        digits = max(self.env['decimal.precision'].precision_get('Product Price'), 2)
        text = self._ua_format_number(value, digits)
        while digits > 2 and text.endswith('0'):
            text = text[:-1]
            digits -= 1
        return text

    def _get_ua_line_price_unit_excl(self, line):
        """Unit price without VAT (before discount), also for taxes included in price.

        `compute_all` rounds the base to the currency, so a price kept with
        the 'Product Price' precision (3-4 decimals) would come out cut to
        kopecks (#365). The price is taken for a quantity scaling that
        rounding down to the price precision and divided back.
        """
        if not line.tax_ids:
            return line.price_unit
        digits = self.env['decimal.precision'].precision_get('Product Price')
        scale = 10 ** max(digits - line.currency_id.decimal_places, 0)
        taxes = line.tax_ids.compute_all(
            line.price_unit, currency=line.currency_id, quantity=scale,
            product=line.product_id, partner=line.partner_id,
        )
        return taxes['total_excluded'] / scale
