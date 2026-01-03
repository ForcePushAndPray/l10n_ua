from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    calendar_days = fields.Integer(
        string='Calendar Days',
        compute='_compute_calendar_days',
        store=True
    )
    working_days = fields.Integer(
        string='Working Days',
        compute='_compute_working_days',
        store=True
    )
    
    average_daily_salary = fields.Float(
        string='Average Daily Salary',
        digits=(16, 2)
    )
    vacation_pay_amount = fields.Float(
        string='Vacation Pay Amount',
        compute='_compute_vacation_pay',
        store=True,
        digits=(16, 2)
    )
    
    order_number = fields.Char(string='Order Number')
    order_date = fields.Date(string='Order Date')
    
    remaining_days_before = fields.Float(
        string='Balance Before',
        help='Vacation balance before this leave'
    )
    remaining_days_after = fields.Float(
        string='Balance After',
        compute='_compute_remaining_after',
        store=True
    )
    
    vacation_year = fields.Integer(
        string='Vacation Year',
        help='Year for which vacation is taken'
    )

    @api.depends('date_from', 'date_to')
    def _compute_calendar_days(self):
        for leave in self:
            if leave.date_from and leave.date_to:
                delta = leave.date_to.date() - leave.date_from.date()
                leave.calendar_days = delta.days + 1
            else:
                leave.calendar_days = 0

    @api.depends('date_from', 'date_to')
    def _compute_working_days(self):
        for leave in self:
            if leave.date_from and leave.date_to:
                count = 0
                current = leave.date_from.date()
                end = leave.date_to.date()
                while current <= end:
                    if current.weekday() < 5:
                        count += 1
                    current += relativedelta(days=1)
                leave.working_days = count
            else:
                leave.working_days = 0

    @api.depends('calendar_days', 'average_daily_salary', 'holiday_status_id.is_paid')
    def _compute_vacation_pay(self):
        for leave in self:
            if leave.holiday_status_id.is_paid and leave.average_daily_salary:
                leave.vacation_pay_amount = leave.calendar_days * leave.average_daily_salary
            else:
                leave.vacation_pay_amount = 0.0

    @api.depends('remaining_days_before', 'number_of_days')
    def _compute_remaining_after(self):
        for leave in self:
            leave.remaining_days_after = (leave.remaining_days_before or 0) - (leave.number_of_days or 0)

    def action_calculate_vacation_pay(self):
        """Calculate average daily salary and vacation pay"""
        for leave in self:
            if not leave.employee_id or not leave.date_from:
                continue
            
            avg_salary = leave._calculate_average_salary()
            leave.average_daily_salary = avg_salary
        return True

    def _calculate_average_salary(self):
        """Calculate average daily salary for vacation pay
        Based on last 12 months earnings divided by calendar days
        """
        self.ensure_one()
        
        date_to = self.date_from.date() - relativedelta(days=1)
        date_from = date_to - relativedelta(months=12) + relativedelta(days=1)
        
        # Get payslips for the period
        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('state', '=', 'done'),
        ])
        
        if not payslips:
            return 0.0
        
        total_earnings = sum(payslips.mapped('gross_salary'))
        
        # Calculate calendar days in period (excluding holidays)
        calendar_days = (date_to - date_from).days + 1
        
        if calendar_days > 0:
            return round(total_earnings / calendar_days, 2)
        return 0.0
