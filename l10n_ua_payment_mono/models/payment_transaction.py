from werkzeug.urls import url_encode

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import urls

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.l10n_ua_payment_mono import const
from odoo.addons.l10n_ua_payment_mono.controllers.main import MonoController

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # What monobank was actually asked to charge. It differs from `amount`/`currency_id` when the
    # provider converts to UAH, and is what the paid invoice is checked against.
    mono_amount = fields.Integer(string="monobank Amount (minor units)", readonly=True, copy=False)
    mono_currency_id = fields.Many2one(
        'res.currency', string="monobank Currency", readonly=True, copy=False)

    def _get_specific_rendering_values(self, processing_values):
        if self.provider_code != 'mono':
            return super()._get_specific_rendering_values(processing_values)

        payload = self._mono_prepare_invoice_payload()
        try:
            invoice = self._send_api_request('POST', 'invoice/create', json=payload)
        except ValidationError as error:
            self._set_error(str(error))
            return {}
        self.provider_reference = invoice.get('invoiceId')
        return {'api_url': invoice['pageUrl']}

    def _mono_prepare_invoice_payload(self):
        currency, amount = self.currency_id, self.amount
        if self.provider_id.mono_charge_currency == 'uah' and currency.name != 'UAH':
            uah = self.env.ref('base.UAH')
            amount = currency._convert(amount, uah, self.company_id, fields.Date.today())
            currency = uah
        self.mono_currency_id = currency
        self.mono_amount = round(amount * 100)

        base_url = self.provider_id.get_base_url()
        query = url_encode({'ref': self.reference})
        return {
            'amount': self.mono_amount,
            'ccy': currency.iso_numeric,
            'merchantPaymInfo': {
                'reference': self.reference,
                'destination': _("Payment for order %s", self.reference),
            },
            'redirectUrl': f"{urls.urljoin(base_url, MonoController._return_url)}?{query}",
            'webHookUrl': f"{urls.urljoin(base_url, MonoController._webhook_url)}?{query}",
            'validity': const.INVOICE_VALIDITY,
            'paymentType': 'debit',
        }

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != 'mono':
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('ref') or payment_data.get('reference')

    def _extract_amount_data(self, payment_data):
        if self.provider_code != 'mono':
            return super()._extract_amount_data(payment_data)

        charged = self.env['res.currency'].with_context(active_test=False).search(
            [('iso_numeric', '=', payment_data.get('ccy'))], limit=1)
        if payment_data.get('amount') == self.mono_amount and charged == self.mono_currency_id:
            # monobank confirms exactly what was invoiced, i.e. the order total (possibly
            # expressed in UAH), so report it in the transaction's own terms.
            return {'amount': self.amount, 'currency_code': self.currency_id.name}
        return {
            'amount': (payment_data.get('amount') or 0) / 100,
            'currency_code': charged.name,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != 'mono':
            return super()._apply_updates(payment_data)

        status = payment_data.get('status')
        if status in const.STATUS_MAPPING['pending']:
            self._set_pending()
        elif status in const.STATUS_MAPPING['authorized']:
            self._set_authorized()
        elif status in const.STATUS_MAPPING['done']:
            self._set_done()
        elif status in const.STATUS_MAPPING['cancel']:
            self._set_canceled(_("monobank invoice status: %s", status))
        elif status in const.STATUS_MAPPING['error']:
            self._set_error(_(
                "The payment was declined: %s",
                payment_data.get('failureReason') or payment_data.get('errCode') or status))
        else:
            _logger.warning("unknown monobank status %s for %s", status, self.reference)
            self._set_error(_("Received data with invalid payment status: %s.", status))
