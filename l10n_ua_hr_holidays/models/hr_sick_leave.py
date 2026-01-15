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
        compute='_compute_employer_days',
        store=True,
        help='First 5 days paid by employer (0 for pregnancy)'
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

    @api.depends('sick_leave_type', 'calendar_days')
    def _compute_employer_days(self):
        for rec in self:
            if rec.sick_leave_type == 'pregnancy':
                rec.employer_days = 0
            else:
                rec.employer_days = min(5, rec.calendar_days)

    @api.depends('calendar_days', 'employer_days')
    def _compute_fss_days(self):
        for rec in self:
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
        """Calculate average daily salary for sick leave.

        Based on earnings in billing period (12 months before sick leave).
        According to the Law of Ukraine on Compulsory Social Insurance.
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
            # Fallback to contract wage
            contract = self.employee_id.contract_id
            if contract and contract.wage:
                # Average days in month for fallback calculation
                return round(contract.wage / 30.44, 2)
            return 0.0

        # Calculate total earnings from payslip lines
        total_earnings = 0.0
        total_calendar_days = 0

        for payslip in payslips:
            # Calculate calendar days in payslip period
            payslip_days = (payslip.date_to - payslip.date_from).days + 1
            total_calendar_days += payslip_days

            # Check if payslip has line_ids (Odoo payroll module structure)
            if hasattr(payslip, 'line_ids') and payslip.line_ids:
                for line in payslip.line_ids:
                    # Check if salary rule has is_basic_salary attribute
                    if hasattr(line, 'salary_rule_id') and line.salary_rule_id:
                        rule = line.salary_rule_id
                        # Include if marked as basic salary or if it's a base category
                        if getattr(rule, 'is_basic_salary', False) or \
                           getattr(rule, 'category_id', False) and \
                           rule.category_id.code in ('BASIC', 'ALW', 'GROSS'):
                            total_earnings += line.total or 0
                    else:
                        # Fallback: include all positive lines
                        total_earnings += max(0, line.total or 0)
            else:
                # Fallback: use gross_salary if available, else net
                if hasattr(payslip, 'gross_salary'):
                    total_earnings += payslip.gross_salary or 0
                elif hasattr(payslip, 'net_wage'):
                    total_earnings += payslip.net_wage or 0

        if total_calendar_days > 0:
            return round(total_earnings / total_calendar_days, 2)
        return 0.0

    def action_confirm(self):
        """Confirm sick leave and create hr.leave record."""
        for rec in self:
            if not rec.leave_id:
                # Find sick leave type
                leave_type = self.env['hr.leave.type'].search([
                    ('ua_leave_category', '=', 'sick')
                ], limit=1)

                if leave_type:
                    # Create hr.leave record
                    leave_vals = {
                        'employee_id': rec.employee_id.id,
                        'holiday_status_id': leave_type.id,
                        'date_from': rec.date_from,
                        'date_to': rec.date_to,
                        'request_date_from': rec.date_from,
                        'request_date_to': rec.date_to,
                        'name': f'Sick Leave {rec.name}',
                    }
                    leave = self.env['hr.leave'].create(leave_vals)
                    rec.leave_id = leave.id

                    # Auto-approve the leave if in draft state
                    if leave.state == 'draft':
                        leave.action_confirm()
                    if leave.state == 'confirm':
                        leave.action_approve()

        self.write({'state': 'confirmed'})

    def action_pay(self):
        self.write({'state': 'paid'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})
