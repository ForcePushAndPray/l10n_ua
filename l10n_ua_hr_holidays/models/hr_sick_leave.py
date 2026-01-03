from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrSickLeave(models.Model):
    _name = 'hr.sick.leave'
    _description = 'Sick Leave'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc'

    name = fields.Char(
        string='Reference',
        required=True,
        default='New',
        tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    sick_leave_number = fields.Char(
        string='Sick Leave Number',
        tracking=True
    )
    is_electronic = fields.Boolean(
        string='Electronic (e-TVN)',
        default=True
    )
    e_sick_leave_id = fields.Char(
        string='e-TVN ID',
        help='Electronic sick leave ID from PFU system'
    )
    
    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        tracking=True
    )
    calendar_days = fields.Integer(
        string='Calendar Days',
        compute='_compute_calendar_days',
        store=True
    )
    
    sick_leave_type = fields.Selection([
        ('illness', 'Illness'),
        ('injury', 'Injury'),
        ('child_care', 'Child Care'),
        ('pregnancy', 'Pregnancy and Childbirth'),
        ('quarantine', 'Quarantine'),
        ('prosthetics', 'Prosthetics'),
        ('sanatorium', 'Sanatorium Treatment'),
    ], string='Type', required=True, default='illness', tracking=True)
    
    diagnosis_code = fields.Char(string='Diagnosis Code (ICD-10)')
    
    insurance_experience_years = fields.Float(
        string='Insurance Experience (years)',
        help='Insurance experience for payment calculation'
    )
    payment_percent = fields.Float(
        string='Payment Percent',
        compute='_compute_payment_percent',
        store=True,
        help='50%, 60%, 70% or 100% based on experience'
    )
    
    average_daily_salary = fields.Float(
        string='Average Daily Salary',
        digits=(16, 2)
    )
    
    employer_days = fields.Integer(
        string='Employer Days',
        default=5,
        help='First 5 days paid by employer'
    )
    employer_amount = fields.Float(
        string='Employer Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    fss_days = fields.Integer(
        string='FSS Days',
        compute='_compute_fss_days',
        store=True
    )
    fss_amount = fields.Float(
        string='FSS Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    total_amount = fields.Float(
        string='Total Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    leave_id = fields.Many2one(
        'hr.leave',
        string='Related Leave'
    )
    
    notes = fields.Text(string='Notes')

    @api.depends('date_from', 'date_to')
    def _compute_calendar_days(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.calendar_days = (rec.date_to - rec.date_from).days + 1
            else:
                rec.calendar_days = 0

    @api.depends('insurance_experience_years', 'sick_leave_type')
    def _compute_payment_percent(self):
        for rec in self:
            if rec.sick_leave_type == 'pregnancy':
                rec.payment_percent = 100.0
            elif rec.insurance_experience_years < 3:
                rec.payment_percent = 50.0
            elif rec.insurance_experience_years < 5:
                rec.payment_percent = 60.0
            elif rec.insurance_experience_years < 8:
                rec.payment_percent = 70.0
            else:
                rec.payment_percent = 100.0

    @api.depends('calendar_days', 'employer_days')
    def _compute_fss_days(self):
        for rec in self:
            if rec.sick_leave_type == 'pregnancy':
                rec.fss_days = rec.calendar_days
            else:
                rec.fss_days = max(0, rec.calendar_days - rec.employer_days)

    @api.depends('calendar_days', 'employer_days', 'fss_days', 
                 'average_daily_salary', 'payment_percent', 'sick_leave_type')
    def _compute_amounts(self):
        for rec in self:
            daily_rate = (rec.average_daily_salary or 0) * (rec.payment_percent or 0) / 100
            
            if rec.sick_leave_type == 'pregnancy':
                rec.employer_amount = 0.0
                rec.fss_amount = daily_rate * rec.calendar_days
            else:
                actual_employer_days = min(rec.employer_days, rec.calendar_days)
                rec.employer_amount = daily_rate * actual_employer_days
                rec.fss_amount = daily_rate * rec.fss_days
            
            rec.total_amount = rec.employer_amount + rec.fss_amount

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError('Start date must be before end date.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.sick.leave') or 'New'
        return super().create(vals_list)

    def action_calculate(self):
        """Calculate sick leave payment"""
        for rec in self:
            if not rec.employee_id:
                continue
            
            # Get insurance experience
            employee = rec.employee_id
            rec.insurance_experience_years = employee.insurance_experience or 0
            
            # Calculate average daily salary
            rec.average_daily_salary = rec._calculate_average_salary()
        return True

    def _calculate_average_salary(self):
        """Calculate average daily salary for sick leave
        Based on earnings in billing period
        """
        self.ensure_one()
        
        # Billing period: 12 calendar months before sick leave
        from dateutil.relativedelta import relativedelta
        
        date_to = self.date_from.replace(day=1) - relativedelta(days=1)
        date_from = (date_to - relativedelta(months=11)).replace(day=1)
        
        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', '=', 'done'),
        ])
        
        if not payslips:
            return 0.0
        
        total_earnings = sum(payslips.mapped('gross_salary'))
        total_days = sum(payslips.mapped('worked_days'))
        
        if total_days > 0:
            return round(total_earnings / total_days, 2)
        return 0.0

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_pay(self):
        self.write({'state': 'paid'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})
