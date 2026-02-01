import base64
import io
import logging
import time

import requests
from base64 import urlsafe_b64encode

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    nbu_payment_link = fields.Char(
        string="Посилання для оплати (НБУ QR)",
        compute='_compute_nbu_payment_link',
    )
    mono_payment_link = fields.Char(
        string="Посилання Monobank",
        readonly=True,
        tracking=True,
    )
    mono_invoice_id = fields.Char(
        string="Monobank Invoice ID",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # NBU QR
    # ------------------------------------------------------------------

    @api.depends('amount_residual', 'company_id', 'name', 'invoice_date')
    def _compute_nbu_payment_link(self):
        template_raw = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('l10n_ua.nbu_qr_template', '')
        )
        template = template_raw.replace('\\n', '\n').replace('\\r', '\r')
        for move in self:
            link = False
            if (
                template
                and move.move_type == 'out_invoice'
                and move.amount_residual > 0
            ):
                company_partner = move.company_id.partner_id
                bank = company_partner.bank_ids[:1]
                if bank:
                    try:
                        data = template.format(
                            name=company_partner.name or '',
                            account=bank.sanitized_acc_number or bank.acc_number or '',
                            currency='UAH',
                            amount=move.amount_residual,
                            edrpou=company_partner.edrpou or '',
                            number=move.name or '',
                            date=move.invoice_date or '',
                        )
                        encoded = urlsafe_b64encode(data.encode('utf-8')).decode('utf-8')
                        link = f"https://bank.gov.ua/qr/{encoded}"
                    except Exception:
                        _logger.warning(
                            "NBU QR link build failed for %s", move.name, exc_info=True
                        )
            move.nbu_payment_link = link

    @staticmethod
    def _make_qr_data_uri(value):
        """Generate QR code as data:image/svg+xml;base64 URI."""
        if not value:
            return False
        try:
            import qrcode
            import qrcode.image.svg
            qr = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage)
            buf = io.BytesIO()
            qr.save(buf)
            return 'data:image/svg+xml;base64,' + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            _logger.warning("QR code generation failed", exc_info=True)
            return False

    def _get_nbu_qr_barcode_url(self, width=200, height=200):
        self.ensure_one()
        return self._make_qr_data_uri(self.nbu_payment_link)

    def _get_mono_qr_barcode_url(self):
        self.ensure_one()
        return self._make_qr_data_uri(self.mono_payment_link)

    # ------------------------------------------------------------------
    # Monobank Acquiring
    # ------------------------------------------------------------------

    def _get_mono_acquiring_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('mono_acquiring_token', '!=', False),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(
                "Не знайдено банківський журнал з токеном Monobank Acquiring. "
                "Налаштуйте токен у Бухгалтерія → Налаштування → Журнали."
            )
        return journal

    def action_create_mono_link(self):
        self.ensure_one()
        if self.move_type != 'out_invoice':
            raise UserError("Посилання на оплату можна створити лише для рахунку клієнту.")
        if self.amount_residual <= 0:
            raise UserError("Рахунок вже оплачено.")

        journal = self._get_mono_acquiring_journal()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
        basket = []
        for line in lines:
            code = (
                line.product_id.default_code
                or line.product_id.barcode
                or str(line.product_id.id)
            )
            qty = line.quantity or 1
            basket.append({
                'name': line.name or line.product_id.name,
                'qty': qty,
                'sum': int(line.price_subtotal / qty * 100),
                'unit': line.product_uom_id.name or 'шт.',
                'code': code,
                'icon': (
                    f"{base_url}/web/image?model=product.template"
                    f"&field=image_128&id={line.product_id.product_tmpl_id.id}"
                    f"&unique={int(time.time() * 1000)}"
                ),
            })

        payload = {
            'amount': int(self.amount_residual * 100),
            'ccy': 980,
            'webHookUrl': f"{base_url}/l10n_ua_payment_link/mono/webhook",
            'merchantPaymInfo': {
                'reference': self.name,
                'destination': f"Оплата за рахунком {self.name}",
                'basketOrder': basket,
            },
            'paymentType': 'debit',
        }

        resp = requests.post(
            'https://api.monobank.ua/api/merchant/invoice/create',
            json=payload,
            headers={
                'X-Token': journal.mono_acquiring_token,
                'X-Cms': 'odoo',
                'X-Cms-Version': '19.0',
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise UserError(f"Monobank API помилка {resp.status_code}: {resp.text}")

        result = resp.json()
        self.write({
            'mono_payment_link': result.get('pageUrl'),
            'mono_invoice_id': result.get('invoiceId'),
        })
