import pprint

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class MonoController(http.Controller):
    _return_url = '/payment/mono/return'
    _webhook_url = '/payment/mono/webhook'

    @http.route(_return_url, type='http', auth='public', methods=['GET'], save_session=False)
    def mono_return_from_checkout(self, **data):
        _logger.info("handling redirection from monobank with data:\n%s", pprint.pformat(data))
        self._verify_and_process(data)
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def mono_webhook(self, **data):
        """Acknowledge a status notification from monobank.

        The body is only used as a wake-up call: nothing in it is trusted. The transaction is
        found by the reference we put in the webhook URL and its state is re-read from the
        monobank API with our own token, so a forged notification cannot mark an order as paid.
        """
        _logger.info("notification received from monobank for %s", data.get('ref'))
        self._verify_and_process(data)
        return ''  # monobank retries until it gets a 200

    @staticmethod
    def _verify_and_process(data):
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('mono', data)
        if not tx_sudo or not tx_sudo.provider_reference:
            return
        try:
            verified_data = tx_sudo._send_api_request(
                'GET', 'invoice/status', params={'invoiceId': tx_sudo.provider_reference})
        except ValidationError:
            _logger.error("unable to fetch the monobank invoice of %s", tx_sudo.reference)
        else:
            tx_sudo._process('mono', verified_data)
