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
        """Calculate average daily salary for vacation pay.

        According to Resolution of CMU No. 100 from 08.02.1995:
        Formula: Total earnings / Calendar days in period

        Include:
        - Base salary
        - Bonuses marked as is_basic_salary
        - Allowances marked as is_basic_salary

        Exclude periods:
        - Sick leave
        - Unpaid leave
        - Idle time
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
            # Fallback to contract wage
            contract = self.employee_id.contract_id
            if contract and contract.wage:
                # Average days in month for fallback calculation
                return round(contract.wage / 29.3, 2)
            return 0.0

        # Calculate total earnings from payslip lines
        total_earnings = 0.0
        excluded_days = 0

        for payslip in payslips:
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

        # Calculate excluded days from sick leave and unpaid leave in the period
        sick_leave_type = self.env['hr.leave.type'].search([
            ('ua_leave_category', '=', 'sick')
        ], limit=1)
        unpaid_leave_type = self.env['hr.leave.type'].search([
            ('ua_leave_category', '=', 'unpaid')
        ])

        excluded_leave_types = sick_leave_type.ids + unpaid_leave_type.ids
        if excluded_leave_types:
            excluded_leaves = self.env['hr.leave'].search([
                ('employee_id', '=', self.employee_id.id),
                ('holiday_status_id', 'in', excluded_leave_types),
                ('state', '=', 'validate'),
                ('date_from', '>=', date_from),
                ('date_to', '<=', date_to),
            ])
            excluded_days = sum(excluded_leaves.mapped('number_of_days'))

        # Calculate calendar days in period
        calendar_days = (date_to - date_from).days + 1 - excluded_days

        if calendar_days > 0:
            return round(total_earnings / calendar_days, 2)
        return 0.0
