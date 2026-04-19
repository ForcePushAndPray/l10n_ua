from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta


class HrSalaryAdvanceRun(models.Model):
    _name = 'hr.salary.advance.run'
    _description = 'Salary Advance Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    date = fields.Date(string='Payment Date', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', tracking=True)

    advance_ids = fields.One2many(
        'hr.salary.advance', 'advance_run_id', string='Advances')
    advance_count = fields.Integer(
        compute='_compute_advance_count')
    total_amount = fields.Monetary(
        compute='_compute_total_amount', currency_field='currency_id')
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id')
    notes = fields.Text(string='Notes')
    wage_percent = fields.Float(
        string='Відсоток від окладу',
        default=50.0,
        tracking=True,
    )

    @api.depends('advance_ids')
    def _compute_advance_count(self):
        for run in self:
            run.advance_count = len(run.advance_ids)

    @api.depends('advance_ids.amount')
    def _compute_total_amount(self):
        for run in self:
            run.total_amount = sum(run.advance_ids.mapped('amount'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.today()
        res.update({
            'date': today.replace(day=15),
            'name': _('Advance for %s') % today.strftime('%B %Y'),
        })
        return res

    def _get_employee_wage(self, employee):
        version = employee.current_version_id
        if not version:
            return 0.0
        wage = version.wage or 0.0
        if not wage and hasattr(version, 'staffing_line_id') and version.staffing_line_id:
            wage = version.staffing_line_id.salary or 0.0
        return wage

    def action_generate_advances(self):
        """Generate wage advances for all active employees."""
        self.ensure_one()
        employees = self.env['hr.employee'].search([
            ('company_id', '=', self.company_id.id),
            ('version_ids.contract_date_start', '!=', False),
        ])
        for employee in employees:
            if self.advance_ids.filtered(lambda a: a.employee_id == employee):
                continue
            wage = self._get_employee_wage(employee)
            if not wage:
                continue
            self.env['hr.salary.advance'].create({
                'employee_id': employee.id,
                'date': self.date,
                'amount': round(wage * self.wage_percent / 100, 2),
                'advance_run_id': self.id,
                'company_id': self.company_id.id,
                'wage_percent': self.wage_percent,
            })
        return True

    def action_confirm_all(self):
        self.ensure_one()
        self.advance_ids.filtered(lambda a: a.state == 'draft').action_confirm()
        self.write({'state': 'confirmed'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.advance_ids.filtered(lambda a: a.state == 'confirmed').action_draft()
        self.write({'state': 'draft'})

    def action_open_advances(self):
        return {
            'name': _('Advances'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.advance',
            'view_mode': 'list,form',
            'domain': [('advance_run_id', '=', self.id)],
            'context': {'default_advance_run_id': self.id, 'default_date': self.date},
        }

