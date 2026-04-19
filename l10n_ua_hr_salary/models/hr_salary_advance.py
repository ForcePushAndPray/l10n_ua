from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrSalaryAdvance(models.Model):
    _name = 'hr.salary.advance'
    _description = 'Salary Advance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        index=True,
    )
    date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary( 
        string='Amount',
        compute='_compute_amount',
        store=True,
        tracking=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
    ], string='Status',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )
    notes = fields.Text(string='Notes')
    advance_run_id = fields.Many2one(
        'hr.salary.advance.run',
        string='Advance Batch',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        readonly=True,
        copy=False,
        help='Payslip from which this advance was deducted',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    wage_percent = fields.Float(
        string='Percentage from wage',
        default=50.0,
        tracking=True,
    )

    @api.depends('employee_id', 'wage_percent')
    def _compute_amount(self):
        for advance in self:
            wage = 0.0
            if advance.employee_id:
                version = advance.employee_id.current_version_id
                if version:
                    wage = version.wage or 0.0
                    if not wage and hasattr(version, 'staffing_line_id') and version.staffing_line_id:
                        wage = version.staffing_line_id.salary or 0.0
            advance.amount = round(wage * advance.wage_percent / 100, 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.salary.advance') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for advance in self:
            if advance.state != 'draft':
                raise UserError(_('Only draft advances can be confirmed.'))
        self.write({'state': 'confirmed'})

    def action_draft(self):
        for advance in self:
            if advance.state == 'paid':
                raise UserError(_('Paid advances cannot be reset to draft.'))
        self.write({'state': 'draft', 'payslip_id': False})

    def unlink(self):
        for advance in self:
            if advance.state == 'paid':
                raise UserError(_('Cannot delete paid advances.'))
        return super().unlink()

