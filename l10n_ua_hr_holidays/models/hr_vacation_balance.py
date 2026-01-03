from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


class HrVacationBalance(models.Model):
    _name = 'hr.vacation.balance'
    _description = 'Vacation Balance'
    _order = 'year desc, employee_id'
    _rec_name = 'display_name'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        index=True
    )
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True,
        domain="[('ua_leave_category', 'in', ['annual_basic', 'annual_additional'])]"
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    entitled_days = fields.Float(
        string='Entitled Days',
        help='Days entitled for the year'
    )
    carried_over = fields.Float(
        string='Carried Over',
        help='Days carried from previous year'
    )
    total_available = fields.Float(
        string='Total Available',
        compute='_compute_totals',
        store=True
    )
    
    used_days = fields.Float(
        string='Used Days',
        compute='_compute_used_days',
        store=True
    )
    planned_days = fields.Float(
        string='Planned Days',
        compute='_compute_used_days',
        store=True
    )
    remaining_days = fields.Float(
        string='Remaining Days',
        compute='_compute_totals',
        store=True
    )
    
    display_name = fields.Char(
        string='Name',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('entitled_days', 'carried_over', 'used_days')
    def _compute_totals(self):
        for rec in self:
            rec.total_available = (rec.entitled_days or 0) + (rec.carried_over or 0)
            rec.remaining_days = rec.total_available - (rec.used_days or 0)

    @api.depends('employee_id', 'leave_type_id', 'year')
    def _compute_used_days(self):
        for rec in self:
            if not rec.employee_id or not rec.leave_type_id or not rec.year:
                rec.used_days = 0
                rec.planned_days = 0
                continue
            
            year_start = fields.Date.from_string(f'{rec.year}-01-01')
            year_end = fields.Date.from_string(f'{rec.year}-12-31')
            
            # Approved leaves
            approved_leaves = self.env['hr.leave'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('holiday_status_id', '=', rec.leave_type_id.id),
                ('state', '=', 'validate'),
                ('date_from', '>=', year_start),
                ('date_to', '<=', year_end),
            ])
            rec.used_days = sum(approved_leaves.mapped('number_of_days'))
            
            # Planned (not yet approved)
            planned_leaves = self.env['hr.leave'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('holiday_status_id', '=', rec.leave_type_id.id),
                ('state', 'in', ['draft', 'confirm']),
                ('date_from', '>=', year_start),
                ('date_to', '<=', year_end),
            ])
            rec.planned_days = sum(planned_leaves.mapped('number_of_days'))

    @api.depends('employee_id', 'year')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.employee_id.name} - {rec.year}'

    @api.model
    def generate_balances(self, year=None):
        """Generate vacation balances for all employees"""
        if year is None:
            year = fields.Date.today().year
        
        employees = self.env['hr.employee'].search([
            ('contract_ids.state', '=', 'open'),
        ])
        
        annual_leave_type = self.env['hr.leave.type'].search([
            ('ua_leave_category', '=', 'annual_basic'),
        ], limit=1)
        
        if not annual_leave_type:
            return
        
        for employee in employees:
            existing = self.search([
                ('employee_id', '=', employee.id),
                ('leave_type_id', '=', annual_leave_type.id),
                ('year', '=', year),
            ])
            
            if existing:
                continue
            
            # Get previous year balance
            prev_balance = self.search([
                ('employee_id', '=', employee.id),
                ('leave_type_id', '=', annual_leave_type.id),
                ('year', '=', year - 1),
            ], limit=1)
            
            carried = prev_balance.remaining_days if prev_balance else 0
            
            self.create({
                'employee_id': employee.id,
                'leave_type_id': annual_leave_type.id,
                'year': year,
                'entitled_days': annual_leave_type.annual_days,
                'carried_over': carried,
            })

    _sql_constraints = [
        ('employee_type_year_uniq', 'unique(employee_id, leave_type_id, year)',
         'Balance for this employee, leave type and year already exists!'),
    ]
