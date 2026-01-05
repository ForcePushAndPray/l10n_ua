from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrStaffingTable(models.Model):
    _name = 'hr.staffing.table'
    _description = 'Staffing Table'
    _order = 'date_from desc, department_id, job_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company)
    department_id = fields.Many2one(
        'hr.department', string='Department',
        required=True, index=True)
    job_id = fields.Many2one(
        'hr.job', string='Position',
        required=True, index=True)
    units = fields.Float(
        string='Staff Units', default=1.0,
        help='Number of staff units (e.g., 0.5, 1.0, 2.0)')
    filled_units = fields.Float(
        string='Filled Units', compute='_compute_filled_units', store=True)
    vacant_units = fields.Float(
        string='Vacant Units', compute='_compute_vacant_units', store=True)
    salary = fields.Monetary(
        string='Salary', currency_field='currency_id',
        required=True,
        help='Standard salary for this position')
    salary_min = fields.Monetary(
        string='Minimum Salary', currency_field='currency_id',
        help='Minimum salary for this position (salary range)')
    salary_max = fields.Monetary(
        string='Maximum Salary', currency_field='currency_id',
        help='Maximum salary for this position (salary range)')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    total_salary_fund = fields.Monetary(
        string='Total Salary Fund', currency_field='currency_id',
        compute='_compute_total_salary_fund', store=True)
    date_from = fields.Date(
        string='Effective From', required=True,
        default=fields.Date.context_today)
    date_to = fields.Date(string='Effective Until')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', tracking=True)
    order_number = fields.Char(string='Order Number')
    order_date = fields.Date(string='Order Date')
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    @api.depends('department_id', 'job_id')
    def _compute_name(self):
        for record in self:
            dept = record.department_id.name or ''
            job = record.job_id.name or ''
            record.name = f"{dept} / {job}"

    @api.depends('units', 'salary')
    def _compute_total_salary_fund(self):
        for record in self:
            record.total_salary_fund = record.units * record.salary

    @api.depends('department_id', 'job_id', 'state')
    def _compute_filled_units(self):
        for record in self:
            if record.state == 'approved' and record.department_id and record.job_id:
                employees = self.env['hr.employee'].search_count([
                    ('department_id', '=', record.department_id.id),
                    ('job_id', '=', record.job_id.id),
                    ('active', '=', True),
                ])
                record.filled_units = float(employees)
            else:
                record.filled_units = 0.0

    @api.depends('units', 'filled_units')
    def _compute_vacant_units(self):
        for record in self:
            record.vacant_units = max(0.0, record.units - record.filled_units)

    @api.constrains('units')
    def _check_units(self):
        for record in self:
            if record.units <= 0:
                raise ValidationError('Staff units must be greater than 0!')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError('End date must be after start date!')

    @api.constrains('salary', 'salary_min', 'salary_max')
    def _check_salary_range(self):
        for record in self:
            if record.salary_min and record.salary_max:
                if record.salary_min > record.salary_max:
                    raise ValidationError('Minimum salary cannot exceed maximum salary!')
            if record.salary:
                if record.salary_min and record.salary < record.salary_min:
                    raise ValidationError('Standard salary cannot be below minimum salary!')
                if record.salary_max and record.salary > record.salary_max:
                    raise ValidationError('Standard salary cannot exceed maximum salary!')

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_draft(self):
        self.write({'state': 'draft'})
