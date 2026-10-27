from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date
from dateutil.relativedelta import relativedelta



# Назви місяців для назви табеля («Табель за жовтень 2026 — …»)
MONTHS_UK = {
    '1': 'січень', '2': 'лютий', '3': 'березень', '4': 'квітень', '5': 'травень', '6': 'червень',
    '7': 'липень', '8': 'серпень', '9': 'вересень', '10': 'жовтень', '11': 'листопад', '12': 'грудень',
}

class HrTimesheet(models.Model):
    _name = 'hr.timesheet'
    _description = 'Timesheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
        tracking=True
    )
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', required=True, tracking=True)
    
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    line_ids = fields.One2many(
        'hr.timesheet.line',
        'timesheet_id',
        string='Timesheet Lines'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
    ], string='Status', default='draft', tracking=True)
    
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user
    )
    
    total_employees = fields.Integer(
        string='Total Employees',
        compute='_compute_totals',
        store=True
    )
    total_worked_days = fields.Integer(
        string='Total Worked Days',
        compute='_compute_totals',
        store=True
    )
    total_worked_hours = fields.Float(
        string='Total Worked Hours',
        compute='_compute_totals',
        store=True
    )
    
    notes = fields.Text(string='Notes')

    partial_approval_date = fields.Date(
        string='Partially Approved Until',
        readonly=True,
        copy=False,
        tracking=True,
        help='The days of the sheet up to this date are approved and locked. '
             'Empty when the sheet has no partial approval.'
    )
    partial_approval_user_id = fields.Many2one(
        'res.users',
        string='Partially Approved By',
        readonly=True,
        copy=False,
        tracking=True
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.department_id and self.department_id.company_id \
                and self.department_id.company_id != self.company_id:
            self.department_id = False

    @api.depends('year', 'month', 'department_id')
    def _compute_name(self):
        for rec in self:
            dept = rec.department_id.name if rec.department_id else 'усі підрозділи'
            rec.name = f'Табель за {MONTHS_UK.get(rec.month, "")} {rec.year} — {dept}'

    @api.depends('line_ids.worked_days', 'line_ids.worked_hours')
    def _compute_totals(self):
        for rec in self:
            rec.total_employees = len(rec.line_ids)
            rec.total_worked_days = sum(rec.line_ids.mapped('worked_days'))
            rec.total_worked_hours = sum(rec.line_ids.mapped('worked_hours'))

    def _l10n_ua_month_bounds(self):
        """The first and the last day of the month of the sheet."""
        self.ensure_one()
        date_from = date(self.year, int(self.month), 1)
        return date_from, date_from + relativedelta(months=1, days=-1)

    def _check_no_partial_approval(self):
        """Refuse what would rebuild or move the days of a partially
        approved sheet: the approved days must stay as they were approved."""
        locked = self.filtered('partial_approval_date')
        if locked:
            raise UserError(_(
                'Timesheet "%(sheet)s" is partially approved until %(date)s. '
                'Set it back to draft first.',
                sheet=locked[0].display_name,
                date=format_date(self.env, locked[0].partial_approval_date)))

    def write(self, vals):
        if 'year' in vals or 'month' in vals:
            self._check_no_partial_approval()
        return super().write(vals)

    def unlink(self):
        self._check_no_partial_approval()
        return super().unlink()

    def action_generate_lines(self):
        """Generate timesheet lines for all employees"""
        self.ensure_one()
        self._check_no_partial_approval()
        self.line_ids.unlink()
        
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        
        employees = self.env['hr.employee'].search(domain)
        
        for employee in employees:
            # Check if employee has active contract via hr.version
            version = employee.current_version_id
            if version and version.contract_date_start and not version.is_in_contract:
                continue

            line = self.env['hr.timesheet.line'].create({
                'timesheet_id': self.id,
                'employee_id': employee.id,
            })
            line.action_generate_days()
        
        return True

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_draft(self):
        self.write({
            'state': 'draft',
            'partial_approval_date': False,
            'partial_approval_user_id': False,
        })

    def action_partial_approve(self):
        """Open the wizard that approves the days up to a chosen date."""
        self.ensure_one()
        if self.state != 'draft' or self.partial_approval_date:
            raise UserError(_(
                'Only a draft timesheet without a partial approval can be '
                'partially approved.'))
        return {
            'name': _('Partial Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.timesheet.partial.approval',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_timesheet_id': self.id},
        }

    _unique_year_month_department_id_company_id = models.Constraint(
        'unique(year, month, department_id, company_id)',
        'Timesheet for this period already exists!',
    )


class HrTimesheetLine(models.Model):
    _name = 'hr.timesheet.line'
    _description = 'Timesheet Line'
    _order = 'employee_id'

    timesheet_id = fields.Many2one(
        'hr.timesheet',
        string='Timesheet',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        related='employee_id.job_id',
        store=True
    )
    
    day_ids = fields.One2many(
        'hr.timesheet.day',
        'line_id',
        string='Days'
    )
    
    scheduled_days = fields.Integer(
        string='Scheduled Days',
        compute='_compute_totals',
        store=True
    )
    worked_days = fields.Integer(
        string='Worked Days',
        compute='_compute_totals',
        store=True
    )
    worked_hours = fields.Float(
        string='Worked Hours',
        compute='_compute_totals',
        store=True
    )
    overtime_hours = fields.Float(
        string='Overtime Hours',
        compute='_compute_totals',
        store=True
    )
    night_hours = fields.Float(
        string='Night Hours',
        compute='_compute_totals',
        store=True
    )
    partial_approval_date = fields.Date(
        related='timesheet_id.partial_approval_date',
    )
    holiday_hours = fields.Float(
        string='Holiday Hours',
        compute='_compute_totals',
        store=True,
        help='Години роботи у святкові/неробочі дні (для доплати ×2).'
    )
    absence_days = fields.Integer(
        string='Absence Days',
        compute='_compute_totals',
        store=True
    )
    vacation_days = fields.Integer(
        string='Vacation Days',
        compute='_compute_totals',
        store=True
    )
    sick_days = fields.Integer(
        string='Sick Days',
        compute='_compute_totals',
        store=True
    )
    norm_hours = fields.Float(
        string='Norm Hours',
        compute='_compute_totals',
        store=True,
        help='Hours the working schedule plans for the month: the sum of the '
             'norm of its days.'
    )
    overtime_diff = fields.Float(
        string='Hours Above Norm',
        compute='_compute_totals',
        store=True,
        help='Hours worked minus the norm. Overtime is paid only by an order '
             'and is entered in the Overtime column by hand.'
    )

    @api.depends('day_ids.code_id', 'day_ids.hours', 'day_ids.overtime_hours',
                 'day_ids.night_hours', 'day_ids.norm_hours')
    def _compute_totals(self):
        for line in self:
            days = line.day_ids
            line.scheduled_days = len(days.filtered(lambda d: d.code_id.code_type == 'work' or d.is_scheduled))
            line.worked_days = len(days.filtered(lambda d: d.code_id.is_worked))
            line.worked_hours = sum(days.mapped('hours'))
            line.overtime_hours = sum(days.mapped('overtime_hours'))
            line.night_hours = sum(days.mapped('night_hours'))
            line.holiday_hours = sum(
                days.filtered(lambda d: d.code_id.code_type == 'holiday').mapped('hours'))
            line.absence_days = len(days.filtered(lambda d: d.code_id.code_type == 'absence'))
            line.vacation_days = len(days.filtered(lambda d: d.code_id.code_type == 'leave'))
            line.sick_days = len(days.filtered(lambda d: d.code_id.code_type == 'sick'))
            line.norm_hours = sum(days.mapped('norm_hours'))
            line.overtime_diff = line.worked_hours - line.norm_hours

    def write(self, vals):
        # Moving a line would carry its approved days to another employee
        # or into another sheet.
        if 'employee_id' in vals or 'timesheet_id' in vals:
            self.timesheet_id._check_no_partial_approval()
            if vals.get('timesheet_id'):
                self.env['hr.timesheet'].browse(
                    vals['timesheet_id'])._check_no_partial_approval()
        return super().write(vals)

    def unlink(self):
        self.timesheet_id._check_no_partial_approval()
        return super().unlink()

    def action_generate_days(self):
        """Generate day entries for the month"""
        self.ensure_one()
        self.timesheet_id._check_no_partial_approval()
        self.day_ids.unlink()
        self.env['hr.timesheet.day'].create([
            dict(day, line_id=self.id, norm_hours=day['hours'])
            for day in self._l10n_ua_plan_days()
        ])
        return True

    def _l10n_ua_plan_days(self):
        """The days of the month as the working schedule plans them: a list
        of {date, day_number, code_id, hours, is_scheduled}.

        Each day is read by the rules the payslip counts a month without a
        timesheet by — the working days of the company, the version in force
        that day, the contract periods, the public holidays — so a timesheet
        left as generated pays what the payslip would pay without one.

        A public holiday inside a time off is not part of it: the time off is
        shortened by it. It is read like any day outside the time off — a
        holiday where the production calendar has it as one, a working day
        where there is no calendar to say so.

        On a shift or summarized schedule the hours are not a roster: the
        days the shifts fall on are unknown, and the plan spreads the norm
        over the working days of the company.
        """
        self.ensure_one()
        company = self.timesheet_id.company_id
        employee = self.employee_id
        date_from = date(self.timesheet_id.year, int(self.timesheet_id.month), 1)
        date_to = date_from + relativedelta(months=1, days=-1)

        Code = self.env['hr.timesheet.code']
        work_code = Code.search([('code', '=', 'Я')], limit=1)
        weekend_code = Code.search([('code', '=', 'В')], limit=1)
        holiday_code = Code.search([('code', '=', 'СВ')], limit=1)
        vacation_code = Code.search([('code', '=', 'ВД')], limit=1)
        sick_code = Code.search([('code', '=', 'ТН')], limit=1)
        # Code for days before contract start or after contract end
        not_employed_code = Code.search([('code', '=', 'НР')], limit=1) \
            or Code.search([('code', '=', 'ІН')], limit=1) or weekend_code

        working = company._l10n_ua_working_dates(date_from, date_to)
        public_holidays = company._l10n_ua_public_holiday_dates(date_from, date_to)
        calendar_days = company._l10n_ua_production_calendar_days(date_from, date_to)
        # By the dates of the request, as the payslip reads them: the moments
        # of the time off are in UTC and would put its first or last day on
        # the day before, or miss a time off starting on the last day.
        # Only the time off counted in days takes the whole day, as the
        # payslip reads it: an hour or a half day off leaves the day worked.
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.request_unit', '=', 'day'),
            ('request_date_from', '<=', date_to),
            ('request_date_to', '>=', date_from),
        ])
        sick_leaves = self.env['hr.sick.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', 'in', ['confirmed', 'paid']),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
        ])

        days, current = [], date_from
        while current <= date_to:
            code, hours = weekend_code, 0.0
            if not employee._l10n_ua_employed_on(current):
                code = not_employed_code
            elif any(s.date_from <= current <= s.date_to for s in sick_leaves):
                code = sick_code
            elif current not in public_holidays and any(
                    l.request_date_from <= current <= l.request_date_to for l in leaves):
                code = vacation_code
            elif current in working:
                code = work_code
                version = employee._l10n_ua_version_on(current) \
                    or employee.current_version_id
                hours = version._l10n_ua_scheduled_hours(company, working[current]) \
                    if version else working[current]
            elif current in calendar_days \
                    and calendar_days[current].day_type == 'holiday':
                code = holiday_code
            days.append({
                'date': current,
                'day_number': current.day,
                'code_id': code.id if code else False,
                'hours': hours,
                'is_scheduled': code == work_code,
            })
            current += relativedelta(days=1)
        return days


class HrTimesheetDay(models.Model):
    _name = 'hr.timesheet.day'
    _description = 'Timesheet Day'
    _order = 'day_number'

    line_id = fields.Many2one(
        'hr.timesheet.line',
        string='Timesheet Line',
        required=True,
        ondelete='cascade'
    )
    date = fields.Date(string='Date', required=True)
    day_number = fields.Integer(string='Day')
    
    code_id = fields.Many2one(
        'hr.timesheet.code',
        string='Code',
        required=True
    )
    hours = fields.Float(string='Hours', default=0)
    norm_hours = fields.Float(
        string='Norm Hours',
        readonly=True,
        help='Hours the working schedule plans for this day. Set when the days '
             'are generated; the hours worked are entered separately.'
    )
    overtime_hours = fields.Float(string='Overtime')
    night_hours = fields.Float(string='Night Hours')
    
    is_scheduled = fields.Boolean(string='Scheduled')
    notes = fields.Char(string='Notes')

    def _check_partial_approval_lock(self, line, day):
        """Refuse a change to a day the partial approval of its sheet covers."""
        locked_until = line.timesheet_id.partial_approval_date
        if locked_until and day and day <= locked_until:
            raise UserError(_(
                'The days of timesheet "%(sheet)s" up to %(date)s are '
                'partially approved and cannot be changed. Set the timesheet '
                'back to draft first.',
                sheet=line.timesheet_id.display_name,
                date=format_date(self.env, locked_until)))

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env['hr.timesheet.line']
        for vals in vals_list:
            if vals.get('line_id') and vals.get('date'):
                self._check_partial_approval_lock(
                    Line.browse(vals['line_id']),
                    fields.Date.to_date(vals['date']))
        return super().create(vals_list)

    def write(self, vals):
        for day in self:
            self._check_partial_approval_lock(day.line_id, day.date)
            if 'date' in vals or 'line_id' in vals:
                self._check_partial_approval_lock(
                    self.env['hr.timesheet.line'].browse(
                        vals.get('line_id', day.line_id.id)),
                    fields.Date.to_date(vals.get('date', day.date)))
        return super().write(vals)

    def unlink(self):
        for day in self:
            self._check_partial_approval_lock(day.line_id, day.date)
        return super().unlink()
