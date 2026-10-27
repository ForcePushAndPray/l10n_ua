from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date


class HrTimesheetPartialApproval(models.TransientModel):
    """Approve the days of a draft timesheet up to a date.

    The sheet stays in draft: the payslip still reads confirmed and approved
    sheets only. The approved days are locked, which is what the advance for
    the first part of the month is computed from.
    """
    _name = 'hr.timesheet.partial.approval'
    _description = 'Timesheet Partial Approval'

    timesheet_id = fields.Many2one(
        'hr.timesheet', string='Timesheet', required=True, readonly=True,
        ondelete='cascade')
    date = fields.Date(
        string='Approve Until', required=True,
        help='The days of the timesheet from the 1st of the month up to this '
             'date, inclusive, are approved and locked.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        timesheet = self.env['hr.timesheet'].browse(
            res.get('timesheet_id') or self.env.context.get('default_timesheet_id'))
        if 'date' in fields_list and timesheet.exists() \
                and timesheet.year and timesheet.month:
            date_from, _date_to = timesheet._l10n_ua_month_bounds()
            res['date'] = date_from.replace(day=15)
        return res

    def action_approve(self):
        self.ensure_one()
        timesheet = self.timesheet_id
        if timesheet.state != 'draft' or timesheet.partial_approval_date:
            raise UserError(_(
                'Only a draft timesheet without a partial approval can be '
                'partially approved.'))
        date_from, date_to = timesheet._l10n_ua_month_bounds()
        if not date_from <= self.date <= date_to:
            raise ValidationError(_(
                'The approval date must be within the month of the timesheet: '
                'from %(date_from)s to %(date_to)s.',
                date_from=format_date(self.env, date_from),
                date_to=format_date(self.env, date_to)))
        timesheet.write({
            'partial_approval_date': self.date,
            'partial_approval_user_id': self.env.user.id,
        })
        return {'type': 'ir.actions.act_window_close'}
