from odoo import models, api


class HrOrder(models.Model):
    """Vacation-order behaviour that needs the leave types this module adds.

    hr.order lives in l10n_ua_hr_documents, which cannot reach ua_is_default —
    the dependency runs the other way — so the default-type preselection is
    contributed from here.
    """
    _inherit = 'hr.order'

    @api.onchange('order_type')
    def _onchange_order_type_default_leave_type(self):
        """Preselect the company's default vacation type as soon as the order
        becomes a vacation order, the same default the leave form applies.
        An explicit choice is never overwritten."""
        if self.order_type != 'vacation' or self.holiday_status_id:
            return
        company = self.company_id or self.env.company
        default_lt = self.env['hr.leave.type'].search([
            ('ua_is_default', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if default_lt:
            self.holiday_status_id = default_lt

