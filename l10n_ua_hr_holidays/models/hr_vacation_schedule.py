from datetime import date
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrVacationSchedule(models.Model):
    _name = 'hr.vacation.schedule'
    _description = 'Vacation Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year + 1,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    line_ids = fields.One2many(
        'hr.vacation.schedule.line',
        'schedule_id',
        string='Schedule Lines'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
    ], string='Status', default='draft', tracking=True)
    
    approval_date = fields.Date(string='Approval Date')
    approved_by = fields.Many2one('res.users', string='Approved By')
    
    notes = fields.Text(string='Notes')

    @api.depends('year', 'company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = f'Графік відпусток {rec.year} - {rec.company_id.name}'

    def action_generate_lines(self):
        """Generate schedule lines for all employees"""
        self.ensure_one()
        self.line_ids.unlink()
        
        domain = [('company_id', '=', self.company_id.id)]
        if 'contract_id' in self.env['hr.employee']._fields:
            domain.append(('contract_id.state', '=', 'open'))
        
        employees = self.env['hr.employee'].search(domain)
       
        # Annual vacation types the schedule plans for. Each may accrue on a
        # work year or a calendar year, so its balance is resolved per
        # period_type (see _find_period_balance).
        annual_types = self.env['hr.leave.type'].search([
            ('ua_leave_category', 'in', ['annual_basic', 'annual_additional']),
            ('company_id', 'in', [self.company_id.id, False]),
        ])
        default_type = annual_types.filtered(
            lambda t: t.ua_leave_category == 'annual_basic')[:1]
        annual_category = ['annual_basic', 'annual_additional']

        year_start = fields.Date.from_string(f'{self.year}-01-01')
        year_end = fields.Date.from_string(f'{self.year}-12-31')

        Line = self.env['hr.vacation.schedule.line']
        for employee in employees:
            # One row per planned annual leave that STARTS in the schedule's
            # calendar year, so an employee with several vacations shows up on
            # several rows (each with its own type, period and dates).
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('state', 'not in', ('cancel', 'refuse')),
                ('holiday_status_id.ua_leave_category', 'in', annual_category),
                ('request_date_from', '>=', year_start),
                ('request_date_from', '<=', year_end),
            ], order='request_date_from')

            # Balances already represented by a leave row (or the entitlement
            # row) — never re-list them as a "past unused" period below.
            shown_balance_ids = set()

            if leaves:
                for leave in leaves:
                    Line.create({
                        'schedule_id': self.id,
                        'employee_id': employee.id,
                        'department_id': employee.department_id.id,
                        'leave_id': leave.id,
                        'leave_type_id': leave.holiday_status_id.id,
                        'vacation_balance_id': leave.vacation_balance_id.id,
                        'planned_days': leave.calendar_days,
                    })
                    if leave.vacation_balance_id:
                        shown_balance_ids.add(leave.vacation_balance_id.id)
            else:
                # No planned leave yet: keep the employee on the schedule with a
                # single row carrying the entitlement so the gap is visible.
                balances = self.env['hr.vacation.balance']
                for leave_type in annual_types:
                    balances |= self._find_period_balance(employee, leave_type)
                if balances:
                    days = sum(balances.mapped('total_available'))
                else:
                    days = default_type.annual_days if default_type else 24
                main_balance = (self._find_period_balance(employee, default_type)
                                if default_type
                                else self.env['hr.vacation.balance'])
                Line.create({
                    'schedule_id': self.id,
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'leave_type_id': default_type.id if default_type else False,
                    'vacation_balance_id': main_balance.id if main_balance else False,
                    'planned_days': days,
                })
                shown_balance_ids.update(balances.ids)
                if main_balance:
                    shown_balance_ids.add(main_balance.id)

            # Past accounting periods that still have unused days: one row each,
            # so outstanding vacation carried from previous periods is visible
            # in the schedule. "Past" = the period STARTED before the schedule
            # year began (a Jun–May work year that ends inside the schedule
            # year still counts as a previous period). Skip any period already
            # shown as a leave/entitlement row above.
            past_balances = self.env['hr.vacation.balance'].search([
                ('employee_id', '=', employee.id),
                ('leave_type_id', 'in', annual_types.ids),
                ('period_start', '<', year_start),
                ('remaining_days', '>', 0),
                ('id', 'not in', list(shown_balance_ids)),
            ], order='period_start')
            for bal in past_balances:
                # Days that period's OWN entitlement left unused (entitled minus
                # used, excluding carry-over) so periods are not double-counted.
                # Only list a period that actually has unused days.
                unused = (bal.entitled_days or 0) - (bal.used_days or 0)
                if unused <= 0:
                    continue
                Line.create({
                    'schedule_id': self.id,
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'leave_type_id': bal.leave_type_id.id,
                    'vacation_balance_id': bal.id,
                    'planned_days': int(round(bal.remaining_days)),
                })

        return True

    def _find_period_balance(self, employee, leave_type):
        """Return the vacation balance matching this schedule's year for the
        given leave type, resolved by its accounting period, or an empty
        recordset when none exists.

        * work year: the period is anchored to the employee's hire date, so
          mid-year (Jul 1) of the schedule year is used to pick the work year
          that overlaps it, then matched by period_start.
        * calendar year: matched directly by the balance's year.
        """
        self.ensure_one()
        Balance = self.env['hr.vacation.balance']
        if leave_type.period_type == 'work':
            start, _end, _index = employee._get_work_year_for_date(
                date(self.year, 7, 1))
            if not start:
                return Balance.browse()
            return Balance.search([
                ('employee_id', '=', employee.id),
                ('leave_type_id', '=', leave_type.id),
                ('period_start', '=', start),
            ], limit=1)
        return Balance.search([
            ('employee_id', '=', employee.id),
            ('leave_type_id', '=', leave_type.id),
            ('year', '=', self.year),
        ], limit=1)


    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approval_date': fields.Date.today(),
            'approved_by': self.env.uid,
        })

    def action_draft(self):
        self.write({'state': 'draft'})

    def _report_generation_date(self):
        """Today's date for the PDF in Ukrainian long form (e.g.
        '"21" липня 2026 р.'), reusing the l10n_ua_hr_documents formatter so no
        extra module dependency is needed."""
        return self.env['hr.order.template.wizard']._format_date_ua(
            fields.Date.context_today(self))

    def _report_lines_grouped(self):
        """Group the schedule lines for the PDF report so the QWeb table can
        merge cells with rowspan.

        Returns a list, one entry per employee (ordered by name):
            {
                'employee': record,
                'total': <number of leave rows for the employee>,
                'type_groups': [
                    {'leave_type': record, 'lines': recordset}, ...
                ],
            }

        'total' drives the rowspan of the employee-level cells (№, name, job
        position, signature — shown once per employee); each type_group's
        line count drives the rowspan of the "Leave Type" cell, so consecutive
        rows of the same leave type are merged.
        """
        self.ensure_one()
        # Sort by employee, then keep same-type rows adjacent within the
        # employee so consecutive-type grouping below is exact.
        ordered = self.line_ids.sorted(
            key=lambda l: ((l.employee_id.name or '').lower(),
                           l.leave_type_id.id or 0, l.id))
        emp_order = []
        emp_lines = {}
        for line in ordered:
            key = line.employee_id.id
            if key not in emp_lines:
                emp_lines[key] = []
                emp_order.append(key)
            emp_lines[key].append(line)

        result = []
        for key in emp_order:
            lines = emp_lines[key]
            type_groups = []
            for line in lines:
                if (type_groups
                        and type_groups[-1]['leave_type'] == line.leave_type_id):
                    type_groups[-1]['lines'] |= line
                else:
                    type_groups.append({
                        'leave_type': line.leave_type_id,
                        'lines': line,
                    })
            result.append({
                'employee': lines[0].employee_id,
                'total': len(lines),
                'type_groups': type_groups,
            })
        return result

    _unique_year_company_id = models.Constraint(
        'unique(year, company_id)',
        'Vacation schedule for this year and company already exists!',
    )


class HrVacationScheduleLine(models.Model):
    _name = 'hr.vacation.schedule.line'
    _description = 'Vacation Schedule Line'
    _order = 'employee_id'
    _rec_name = 'display_name'

    display_name = fields.Char(
        string='Name',
        compute='_compute_display_name',
        store=True
    )

    schedule_id = fields.Many2one(
        'hr.vacation.schedule',
        string='Schedule',
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
        store=True,
        readonly=False
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        related='employee_id.job_id',
        store=True,
    )
    leave_id = fields.Many2one(
        'hr.leave',
        string='Leave',
        ondelete='set null',
        help='Planned annual leave this row represents. One row is generated '
             'per leave; empty when the employee has no leave planned yet for '
             'the schedule year.',
    )
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        help='Annual leave type this scheduled line plans for.',
    )
    vacation_balance_id = fields.Many2one(
        'hr.vacation.balance',
        string='Vacation Period',
        help='Accounting period the planned annual leave is charged against.',
    )
    vacation_period_display = fields.Char(
        string='Vacation Dates',
        compute='_compute_vacation_period_display',
        store=True,
        help="Dates of the linked leave (dd.mm.yyyy - dd.mm.yyyy), taken from "
             "hr.leave request_date_from / request_date_to.",
    )

    planned_days = fields.Integer(string='Planned Days')

    period_1_start = fields.Date(string='Period 1 Start')
    period_1_end = fields.Date(string='Period 1 End')
    period_1_days = fields.Integer(
        string='Period 1 Days',
        compute='_compute_period_days',
        store=True
    )
    
    total_planned = fields.Integer(
        string='Total Planned',
        compute='_compute_period_days',
        store=True
    )
    
    actual_days = fields.Integer(
        string='Actual Days',
        compute='_compute_actual_days',
        store=True
    )
    
    notes = fields.Char(string='Notes')

    @api.depends('employee_id', 'planned_days')
    def _compute_display_name(self):
        for line in self:
            if line.employee_id:
                line.display_name = f"{line.employee_id.name} ({line.planned_days} дн.)"
            else:
                line.display_name = "Новий запис"

    @api.depends('period_1_start', 'period_1_end')

    def _compute_period_days(self):
        for line in self:
            days1 = 0
            
            if line.period_1_start and line.period_1_end:
                days1 = (line.period_1_end - line.period_1_start).days + 1
            
            line.period_1_days = days1
            line.total_planned = days1 

    @api.depends('leave_id', 'leave_id.request_date_from',
                 'leave_id.request_date_to')
    def _compute_vacation_period_display(self):
        """Show the linked leave's dates as "dd.mm.yyyy - dd.mm.yyyy"
        (hr.leave request_date_from / request_date_to). Empty for a row with
        no linked leave (employee with no leave planned yet)."""
        for line in self:
            leave = line.leave_id
            if leave and leave.request_date_from:
                end = leave.request_date_to or leave.request_date_from
                line.vacation_period_display = '%s - %s' % (
                    leave.request_date_from.strftime('%d.%m.%Y'),
                    end.strftime('%d.%m.%Y'))
            else:
                line.vacation_period_display = ''

    @api.depends('leave_id', 'leave_id.state', 'leave_id.calendar_days')
    def _compute_actual_days(self):
        """Actual days of the linked leave: its calendar days once approved
        (state 'validate'), 0 while still planned or without a linked leave."""
        for line in self:
            leave = line.leave_id
            line.actual_days = (
                leave.calendar_days if leave and leave.state == 'validate'
                else 0)

    @api.constrains('period_1_start', 'period_1_end')
    def _check_periods(self):
        for line in self:
            if line.period_1_start and line.period_1_end and line.period_1_start > line.period_1_end:
                raise ValidationError('Period 1: Start date must be before end date.')
