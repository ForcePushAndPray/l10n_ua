from collections import OrderedDict

from odoo import fields, models
from odoo.exceptions import UserError


class AgroRentPayment(models.Model):
    """ПДВ з орендної плати натурою: постачання продукції орендодавцям
    (пп. 14.1.191 ПКУ) у платника ПДВ — зобов'язання і ПН неплатнику."""
    _inherit = 'l10n_ua.agro.rent.payment'

    vat_move_id = fields.Many2one('account.move', string='VAT Entry', readonly=True, copy=False)
    tax_invoice_ids = fields.Many2many(
        'l10n_ua.tax.invoice', 'l10n_ua_agro_rent_payment_tax_invoice_rel', 'payment_id', 'tax_invoice_id',
        string='Tax Invoices', readonly=True, copy=False)
    tax_invoice_count = fields.Integer(compute='_compute_tax_invoice_count')
    vat_amount = fields.Monetary(string='VAT', readonly=True, copy=False)

    def _compute_tax_invoice_count(self):
        for payment in self:
            payment.tax_invoice_count = len(payment.tax_invoice_ids)

    def action_post(self):
        drafts = self.filtered(lambda p: p.state == 'draft')
        res = super().action_post()
        for payment in drafts.filtered(lambda p: p.state == 'posted' and p.payment_form == 'in_kind'
                                       and p.company_id.l10n_ua_is_vat_payer):
            payment.sudo()._l10n_ua_post_in_kind_vat()
        return res

    def _l10n_ua_vat_tax(self):
        self.ensure_one()
        taxes = self.product_id.taxes_id.filtered(lambda t: t.company_id == self.company_id)
        rate_code = self.env['account.move']._l10n_ua_vat_rate_from_taxes(taxes)
        tax = taxes.filtered(lambda t: t.amount_type == 'percent')[:1]
        return tax, rate_code

    def _l10n_ua_post_in_kind_vat(self):
        self.ensure_one()
        tax, rate_code = self._l10n_ua_vat_tax()
        if rate_code in ('exempt', '0'):
            return
        rate = float(rate_code) / 100.0
        company = self.company_id
        currency = self.currency_id
        included = company.l10n_ua_agro_in_kind_vat_included
        vat_account = tax.invoice_repartition_line_ids.filtered(
            lambda l: l.repartition_type == 'tax').account_id[:1]
        if not vat_account:
            vat_account = self.env['account.account'].search([
                ('code', '=like', '6412%'), ('company_ids', 'in', company.id)], order='code', limit=1)
        if included:
            debit_account = self.income_account_id
        else:
            debit_account = company.l10n_ua_agro_in_kind_vat_expense_account_id or self.env['account.account'].search(
                [('code', '=like', '94%'), ('company_ids', 'in', company.id)], order='code', limit=1)
        if not vat_account or not debit_account:
            raise UserError(self.env._(
                'Set the VAT account of the sales tax of %s and the in-kind rent VAT expense account.',
                self.product_id.display_name))

        by_lessor = OrderedDict()
        for line in self.line_ids:
            data = by_lessor.setdefault(line.lessor_id, {'amount': 0.0, 'quantity': 0.0})
            data['amount'] += line.amount
            data['quantity'] += line.quantity
        move_lines = []
        invoices = self.env['l10n_ua.tax.invoice']
        total_vat = 0.0
        for lessor, data in by_lessor.items():
            if included:
                base = currency.round(data['amount'] / (1.0 + rate))
                vat = currency.round(data['amount'] - base)
            else:
                base = currency.round(data['amount'])
                vat = currency.round(base * rate)
            if currency.is_zero(vat):
                continue
            total_vat += vat
            label = self.env._('VAT on in-kind land rent, %(lessor)s, %(payment)s',
                               lessor=lessor.name, payment=self.name)
            move_lines += [
                (0, 0, {'name': label, 'account_id': debit_account.id, 'partner_id': lessor.id, 'debit': vat}),
                (0, 0, {'name': label, 'account_id': vat_account.id, 'partner_id': lessor.id, 'credit': vat}),
            ]
            invoices |= self.env['l10n_ua.tax.invoice'].create({
                'invoice_type': 'issued',
                'doc_type': 'pn',
                'number': self.env['ir.sequence'].next_by_code('l10n_ua.tax.invoice.issued') or '/',
                'date': self.date,
                'vat_method': 'first_event',
                'partner_id': lessor.id,
                'company_id': company.id,
                'non_payer_reason': '02',
                'line_ids': [(0, 0, {
                    'sequence': 10,
                    'product_id': self.product_id.id,
                    'name': self.product_id.display_name,
                    **self.product_id._l10n_ua_product_codes(),
                    'quantity': data['quantity'],
                    'uom_id': self.product_id.uom_id.id,
                    'price_unit': base / data['quantity'] if data['quantity'] else base,
                    'vat_rate': rate_code,
                })],
            })
        if not move_lines:
            return
        journal = self.journal_id
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': journal.id, 'date': self.date,
            'ref': self.env._('VAT %s', self.name), 'company_id': company.id, 'line_ids': move_lines,
        })
        move.action_post()
        self.write({'vat_move_id': move.id, 'tax_invoice_ids': [(6, 0, invoices.ids)], 'vat_amount': total_vat})

    def action_cancel(self):
        for payment in self:
            registered = payment.tax_invoice_ids.filtered(lambda t: t.state not in ('draft', 'cancelled'))
            if registered:
                raise UserError(self.env._(
                    'Tax invoices %s are already registered: issue adjustment calculations before '
                    'cancelling the payment.', ', '.join(registered.mapped('number'))))
        res = super().action_cancel()
        for payment in self:
            payment.tax_invoice_ids.filtered(lambda t: t.state == 'draft').action_cancel()
            if payment.vat_move_id and payment.vat_move_id.state == 'posted':
                payment.vat_move_id._reverse_moves(
                    [{'date': payment.vat_move_id.date,
                      'ref': self.env._('Reversal of %s', payment.vat_move_id.ref)}], cancel=True)
        return res

    def action_view_tax_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.tax.invoice',
            'name': self.env._('Tax Invoices'),
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.tax_invoice_ids.ids)],
        }
