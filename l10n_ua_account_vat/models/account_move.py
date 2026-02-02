from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_ids = fields.One2many(
        'l10n_ua.tax.invoice',
        'move_id',
        string='Податкові накладні',
    )
    tax_invoice_count = fields.Integer(
        string='Кількість ПН',
        compute='_compute_tax_invoice_count',
    )

    @api.depends('tax_invoice_ids')
    def _compute_tax_invoice_count(self):
        for move in self:
            move.tax_invoice_count = len(move.tax_invoice_ids)

    def action_create_tax_invoice(self):
        """Create a tax invoice (ПН) from customer/vendor invoice."""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('Створити ПН можна тільки для проведеного документа.'))

        if self.move_type in ('out_invoice', 'out_refund'):
            invoice_type = 'issued'
        elif self.move_type in ('in_invoice', 'in_refund'):
            invoice_type = 'received'
        else:
            raise UserError(_('ПН можна створити тільки для рахунків.'))

        is_refund = self.move_type in ('out_refund', 'in_refund')

        # Build lines from invoice lines
        line_vals = []
        seq = 10
        for iline in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            # Determine VAT rate from tax
            vat_rate = '20'
            vat_amount = 0.0
            for tax in iline.tax_ids:
                if tax.amount == 20:
                    vat_rate = '20'
                elif tax.amount == 14:
                    vat_rate = '14'
                elif tax.amount == 7:
                    vat_rate = '7'
                elif tax.amount == 0:
                    vat_rate = '0'
            # Calculate VAT
            rates = {'20': 0.20, '14': 0.14, '7': 0.07, '0': 0.0}
            base = iline.price_subtotal
            vat_amount = base * rates.get(vat_rate, 0.20)

            line_vals.append((0, 0, {
                'sequence': seq,
                'product_id': iline.product_id.id if iline.product_id else False,
                'name': iline.name or iline.product_id.display_name or '',
                'uktzed_code': iline.product_id.l10n_ua_uktzed if hasattr(iline.product_id, 'l10n_ua_uktzed') else '',
                'quantity': iline.quantity,
                'uom_id': iline.product_uom_id.id if iline.product_uom_id else False,
                'price_unit': iline.price_unit,
                'vat_rate': vat_rate,
            }))
            seq += 10

        # Get next number
        seq_code = f'l10n_ua.tax.invoice.{invoice_type}'
        number = self.env['ir.sequence'].next_by_code(seq_code) or _('Новий')

        vals = {
            'invoice_type': invoice_type,
            'doc_type': 'rk' if is_refund else 'pn',
            'number': number,
            'date': fields.Date.context_today(self),
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'move_id': self.id,
            'line_ids': line_vals,
        }

        tax_invoice = self.env['l10n_ua.tax.invoice'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.tax.invoice',
            'res_id': tax_invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_tax_invoices(self):
        """Open related tax invoices."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Податкові накладні'),
            'res_model': 'l10n_ua.tax.invoice',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }
        if self.tax_invoice_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.tax_invoice_ids[0].id
        return action
