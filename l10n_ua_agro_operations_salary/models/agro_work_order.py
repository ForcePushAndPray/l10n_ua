from odoo import fields, models
from odoo.exceptions import UserError


class HrPieceWorkEntry(models.Model):
    _inherit = 'hr.piece.work.entry'

    l10n_ua_agro_worker_id = fields.Many2one(
        'l10n_ua.agro.work.order.worker', string='Field Work Order Line',
        index='btree_not_null', ondelete='set null', readonly=True)


class AgroWorkOrder(models.Model):
    _inherit = 'l10n_ua.agro.work.order'

    def action_done(self):
        drafts = self.filtered(lambda o: o.state == 'draft')
        res = super().action_done()
        drafts.filtered(lambda o: o.state == 'done')._create_piece_work_entries()
        return res

    def _create_piece_work_entries(self):
        entries = []
        for order in self:
            for worker in order.worker_ids.filtered('amount'):
                entries.append({
                    'name': '%s: %s, %s' % (order.name, order.operation_type_id.name,
                                            order.field_id.display_name),
                    'employee_id': worker.employee_id.id,
                    'date': order.date,
                    'quantity': worker.volume,
                    'unit_rate': worker.rate,
                    'company_id': order.company_id.id,
                    'l10n_ua_agro_worker_id': worker.id,
                })
        self.env['hr.piece.work.entry'].sudo().create(entries)

    def action_cancel(self):
        entries = self.env['hr.piece.work.entry'].sudo().search([
            ('l10n_ua_agro_worker_id.order_id', 'in', self.ids)])
        for entry in entries:
            payslip = self.env['hr.payslip'].sudo().search([
                ('employee_id', '=', entry.employee_id.id),
                ('date_from', '<=', entry.date),
                ('date_to', '>=', entry.date),
                ('state', '=', 'done'),
            ], limit=1)
            if payslip:
                raise UserError(self.env._(
                    'The pay of %(employee)s for %(date)s is already in the validated payslip '
                    '%(payslip)s: cancel the payslip first.',
                    employee=entry.employee_id.name, date=entry.date, payslip=payslip.display_name))
        entries.unlink()
        return super().action_cancel()
