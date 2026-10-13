from odoo import fields, models, service
from odoo.tools import urls

from odoo.addons.l10n_ua_payment_mono import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('mono', "monobank")], ondelete={'mono': 'set default'})
    mono_token = fields.Char(
        string="monobank Token",
        help="X-Token of the merchant: the test token in test mode, the live one otherwise.",
        required_if_provider='mono', copy=False, groups='base.group_system')
    mono_charge_currency = fields.Selection(
        [('order', "Order currency"), ('uah', "Convert to UAH")],
        string="Charge In", default='order', required=True,
        help="Order currency: the invoice is issued in the currency of the order (UAH, USD or "
             "EUR).\nConvert to UAH: the order total is converted at the Odoo rate of the day "
             "and the card is charged in hryvnias.")

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'mono' and self.mono_charge_currency == 'order':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES)
        return supported_currencies

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != 'mono':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _build_request_url(self, endpoint, **kwargs):
        if self.code != 'mono':
            return super()._build_request_url(endpoint, **kwargs)
        return urls.urljoin(const.API_URL, endpoint.strip('/'))

    def _build_request_headers(self, *args, **kwargs):
        if self.code != 'mono':
            return super()._build_request_headers(*args, **kwargs)
        return {
            'X-Token': self.mono_token,
            'X-Cms': 'odoo',
            'X-Cms-Version': service.common.exp_version()['server_version'],
        }

    def _parse_response_error(self, response):
        if self.code != 'mono':
            return super()._parse_response_error(response)
        content = response.json()
        return content.get('errText') or content.get('errCode') or response.text
