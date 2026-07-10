from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date

class HrVacationBalance(models.Model):
    _name = 'hr.vacation.balance'
    _description = 'Vacation Balance'
    _order = 'period_start desc, employee_id'

    _rec_name = 'display_name'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        index=True,
        check_company=True
    )
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True,
        domain="[('ua_leave_category', 'in', ['annual_basic', 'annual_additional',"
               " 'annual_hazardous', 'annual_special', 'annual_irregular'])]"
    )
    period_type = fields.Selection(
        related='leave_type_id.period_type',
        store=True,
        index=True,
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
        index=True,
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
    )
    period_index = fields.Integer(
        string='Period #',
        help='Calendar year for calendar periods; sequential work-year '
             'number from hire date for work periods.'
    )
    period_label = fields.Char(
        string='Period',
        compute='_compute_period_label',
        store=True,
    )
    year = fields.Integer(
        string='Year',
        compute='_compute_year',
        store=True,
        index=True,
        help='Start year of the accounting period. Kept for backward '
             'compatibility with year-based filters and reports.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    entitled_days = fields.Float(
        string='Entitled Days',
        compute='_compute_entitled_days',
        store=True,
        readonly=False,
        precompute=True,
        help='Days entitled for the year. Defaults to leave type annual_days; '
             'can be overridden manually (e.g. proportional for mid-year hires).'
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

    @api.model
    def _get_period_for(self, employee, leave_type, ref_date):
        """Return (period_start, period_end, period_index) of the accounting
        period containing ref_date for the given employee and leave type.

        Work-year types delegate to hr.employee._get_work_year_for_date;
        calendar types return Jan 1 – Dec 31 with period_index = year.
        Returns (False, False, 0) for work types without a hire anchor.
        """
        if leave_type.period_type == 'work':
            return employee._get_work_year_for_date(ref_date)
        return (date(ref_date.year, 1, 1), date(ref_date.year, 12, 31), ref_date.year)

    @api.model
    def _ref_date_for_year(self, year):
        """Pick a reference date inside the requested year to resolve
        the accounting period: today when generating for the current year,
        end of year for past years, start of year for future years."""
        today = fields.Date.today()
        if year == today.year:
            return today
        if year < today.year:
            return date(year, 12, 31)
        return date(year, 1, 1)

    @api.depends('period_start')
    def _compute_year(self):
        for rec in self:
            rec.year = rec.period_start.year if rec.period_start else 0

    @api.depends('period_start', 'period_end')
    def _compute_period_label(self):
        # Date range only, for both work and calendar periods
        # (e.g. "01.07.2025 – 30.06.2026").
        for rec in self:
            if rec.period_start and rec.period_end:
                rec.period_label = '%s – %s' % (
                    rec.period_start.strftime('%d.%m.%Y'),
                    rec.period_end.strftime('%d.%m.%Y'),
                )
            else:
                rec.period_label = ''

    @api.depends('leave_type_id', 'period_start', 'period_end')
    def _compute_entitled_days(self):
        for rec in self:
            if not rec.leave_type_id or rec.entitled_days:
                continue
            annual = rec.leave_type_id.annual_days or 0
            entitled = annual
            # Shortened period (e.g. termination mid work-year): prorate.
            if rec.period_start and rec.period_end:
                span_days = (rec.period_end - rec.period_start).days + 1
                if span_days < 365:
                    entitled = round(annual * span_days / 365.0, 2)
            rec.entitled_days = entitled

    @api.onchange('company_id')
    def _onchange_company_id(self):
        self.employee_id = False
        self.leave_type_id = False

    @api.onchange('employee_id', 'leave_type_id')
    def _onchange_period_defaults(self):
        """Prefill the accounting period once employee and type are chosen."""
        for rec in self:
            if not rec.employee_id or not rec.leave_type_id or rec.period_start:
                continue
            today = fields.Date.context_today(self)
            start, end, index = self._get_period_for(
                rec.employee_id, rec.leave_type_id, today)
            if not start:
                # Work-year type without hire anchor: calendar fallback
                start, end, index = (
                    date(today.year, 1, 1), date(today.year, 12, 31), today.year)
            rec.period_start = start
            rec.period_end = end
            rec.period_index = index

    @api.constrains('period_start', 'period_end')
    def _check_period_bounds(self):
        for rec in self:
            if rec.period_start and rec.period_end and rec.period_start > rec.period_end:
                raise ValidationError(_('Period start must be before period end.'))

    @api.depends('entitled_days', 'carried_over', 'used_days')
    def _compute_totals(self):
        for rec in self:
            rec.total_available = (rec.entitled_days or 0) + (rec.carried_over or 0)
            rec.remaining_days = rec.total_available - (rec.used_days or 0)

    @api.depends('employee_id', 'leave_type_id', 'period_start', 'period_end')
    def _compute_used_days(self):
        HrLeave = self.env['hr.leave']
        for rec in self:
            if (not rec.employee_id or not rec.leave_type_id
                    or not rec.period_start or not rec.period_end):
                rec.used_days = 0
                rec.planned_days = 0
                continue

            # Leaves explicitly linked to this balance, plus unlinked
            # legacy leaves matched by vacation_year or by date overlap
            # with the accounting period.
            base_domain = [
                ('employee_id', '=', rec.employee_id.id),
                ('holiday_status_id', '=', rec.leave_type_id.id),
                '|',
                    ('vacation_balance_id', '=', rec.id),
                    '&',
                        ('vacation_balance_id', '=', False),
                        '|',
                            ('vacation_year', '=', rec.year),
                            '&', '&',
                                ('vacation_year', 'in', [False, 0]),
                                ('request_date_from', '<=', rec.period_end),
                                ('request_date_to', '>=', rec.period_start),
            ]

            used_leaves = HrLeave.search(base_domain + [('state', '=', 'validate')])
            rec.used_days = sum(used_leaves.mapped('calendar_days'))

            planned_leaves = HrLeave.search(base_domain + [
                ('state', 'in', ('draft', 'confirm', 'validate1')),
            ])
            rec.planned_days = sum(planned_leaves.mapped('calendar_days'))

    @api.depends('employee_id', 'period_type', 'period_label', 'year')
    def _compute_display_name(self):
        for rec in self:
            if rec.period_type == 'work' and rec.period_label:
                rec.display_name = f'{rec.employee_id.name} - {rec.period_label}'
            else:
                rec.display_name = f'{rec.employee_id.name} - {rec.year}'

    @api.model
    def generate_balances(self, year=None, leave_types=None):
        """Generate vacation balances for all employees.

        Calendar-period types get a Jan 1 – Dec 31 balance for the
        requested year; work-period types get the work year (anchored to
        hire_date) containing the reference date of that year. Employees
        without a hire anchor are skipped for work-period types.
        """
        if year is None:
            year = fields.Date.today().year
        ref_date = self._ref_date_for_year(year)
        
        domain = []
        if 'contract_id' in self.env['hr.employee']._fields:
            domain.append(('contract_id.state', '=', 'open'))
        
        employees = self.env['hr.employee'].search(domain)
        
        if leave_types is None:
            leave_types = self.env['hr.leave.type'].search([
                ('ua_leave_category', '=', 'annual_basic'),
            ], limit=1)

        for leave_type in leave_types:
            for employee in employees:
                start, end, index = self._get_period_for(
                    employee, leave_type, ref_date)
                if not start:
                    # Work-year type and no hire anchor — cannot resolve
                    # the period for this employee.
                    continue

                existing = self.search([
                    ('employee_id', '=', employee.id),
                    ('leave_type_id', '=', leave_type.id),
                    ('period_start', '=', start),
                ])
                if existing:
                    continue

                # Carry over from the immediately preceding period
                prev_balance = self.search([
                    ('employee_id', '=', employee.id),
                    ('leave_type_id', '=', leave_type.id),
                    ('period_index', '=', index - 1),
                ], limit=1)
                carried = prev_balance.remaining_days if prev_balance else 0

                self.create({
                    'employee_id': employee.id,
                    'leave_type_id': leave_type.id,
                    'period_start': start,
                    'period_end': end,
                    'period_index': index,
                    'entitled_days': leave_type.annual_days,
                    'carried_over': carried,
                })

    def _link_related_leaves(self):
        """Attach unlinked leaves that fall into this balance's period.

        When a balance row appears after its leaves (manual creation,
        generate_balances), the leaves' vacation_balance_id was computed
        to False — recompute it now so rollups and per-leave chains see
        the new period.
        """
        Leave = self.env['hr.leave']
        for balance in self:
            leaves = Leave.search([
                ('employee_id', '=', balance.employee_id.id),
                ('holiday_status_id', '=', balance.leave_type_id.id),
                ('vacation_balance_id', '=', False),
                ('request_date_from', '>=', balance.period_start),
                ('request_date_from', '<=', balance.period_end),
            ])
            if leaves:
                leaves._compute_vacation_balance()
                leaves.flush_recordset(['vacation_balance_id'])

    def _recompute_related_leaves(self):
        """
        Helper method to force recomputation of remaining days for all leaves
        associated with this balance record.
        """
        for balance in self:
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', balance.employee_id.id),
                ('holiday_status_id', '=', balance.leave_type_id.id),
                '|', ('vacation_balance_id', '=', balance.id),
                     '&', ('vacation_balance_id', '=', False),
                          '&', ('request_date_from', '>=',balance.period_start),
                               ('request_date_from', '<=', balance.period_end), 
            ])
            if leaves:
                # Sort chronologically to ensure cascading subtraction is correct
                sorted_leaves = leaves.sorted(key=lambda l: l.request_date_from or fields.Date.today())
                sorted_leaves._compute_remaining_before()
                sorted_leaves._compute_remaining_after()

    @api.model_create_multi
    def create(self, vals_list):
        # Backward-compat: derive the accounting period when the caller
        # still passes only 'year' (transfer wizard, legacy code, tests).
        for vals in vals_list:
            if vals.get('period_start') and vals.get('period_end'):
                continue
            employee = self.env['hr.employee'].browse(vals.get('employee_id'))
            leave_type = self.env['hr.leave.type'].browse(vals.get('leave_type_id'))
            year = vals.get('year') or fields.Date.today().year
            ref_date = self._ref_date_for_year(year)
            start, end, index = self._get_period_for(employee, leave_type, ref_date)
            if not start:
                # Work-year type without hire anchor: calendar fallback
                start, end, index = (
                    date(year, 1, 1), date(year, 12, 31), year)
            vals.setdefault('period_start', start)
            vals.setdefault('period_end', end)
            vals.setdefault('period_index', index)
        balances = super().create(vals_list)
        # Attach pre-existing leaves, then refresh their chains and rollups
        balances._link_related_leaves()
        balances._recompute_related_leaves()
        return balances

    def write(self, vals):
        res = super().write(vals)
        # Trigger recomputation only when base days or the period are modified
        if any(field in vals for field in [
                'entitled_days', 'carried_over', 'period_start', 'period_end',
                'employee_id', 'leave_type_id']):
            self._recompute_related_leaves()
        return res

    _unique_employee_id_leave_type_id_period_start = models.Constraint(
        'unique(employee_id, leave_type_id, period_start)',
        'Balance for this employee, leave type and period already exists!',
    )

    @api.constrains('carried_over', 'period_index', 'employee_id', 'leave_type_id')
    def _check_carryover_limit(self):
        """Check that vacation is not carried over for more than max_carryover_years.
        Ukrainian law requires that vacation must be used within 2 years.
        Periods are compared by period_index, which is sequential for both
        calendar years and work years.
        """
        for rec in self:
            if not rec.carried_over or rec.carried_over <= 0:
                continue
            
            max_years = rec.leave_type_id.max_carryover_years or 2
            oldest_allowed_index = (rec.period_index or rec.year) - max_years
            old_balances = self.search([
                ('employee_id', '=', rec.employee_id.id),
                ('leave_type_id', '=', rec.leave_type_id.id),
                ('period_index', '<=', oldest_allowed_index),
                ('remaining_days', '>', 0),
            ])

            if old_balances:
                raise ValidationError(_(
                    'Employee %(employee)s has unused vacation days from period %(period)s or earlier. '
                    'According to Ukrainian law, vacation must be used within %(max_years)s years.',
                    employee=rec.employee_id.name,
                    period=old_balances[0].period_label or oldest_allowed_index,
                    max_years=max_years,
                ))

    def calculate_compensation(self, termination_date=None, is_termination=True):
        """Calculate compensation for unused vacation.

        Args:
            termination_date: Date of termination/calculation (defaults to today)
            is_termination: If True, compensate all unused days (on termination).
                           If False, only compensate days over 24 (without termination).

        Returns:
            float: Compensation amount for unused vacation days
            
        Per Ukrainian law:
        - On termination: all unused days are compensated
        - Without termination: only days over 24 can be compensated,
          and employee must have used at least 24 days in current year
        """
        self.ensure_one()

        if not self.employee_id or not self.remaining_days:
            return 0.0

        if termination_date is None:
            termination_date = fields.Date.today()

        compensable_days = self.remaining_days
        
        if not is_termination:
            min_annual_days = self.leave_type_id.annual_days or 24
            if self.used_days < min_annual_days:
                return 0.0
            compensable_days = max(0, self.remaining_days - min_annual_days)
            if compensable_days <= 0:
                return 0.0

        # Get average daily salary using hr.leave calculation
        leave = self.env['hr.leave'].new({
            'employee_id': self.employee_id.id,
            'date_from': termination_date,
        })
        avg_salary = leave._calculate_average_salary()

        if avg_salary <= 0:
            return 0.0

        compensation = compensable_days * avg_salary
        return round(compensation, 2)

    def action_calculate_compensation(self):
        """Action to calculate and display compensation amount."""
        self.ensure_one()
        compensation = self.calculate_compensation()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Vacation Compensation'),
                'message': _('Compensation for %(days)s unused days: %(amount).2f UAH', days=self.remaining_days, amount=compensation),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_recalculate(self):
        for rec in self:
            if rec.leave_type_id and not rec.entitled_days:
                rec.entitled_days = rec.leave_type_id.annual_days or 0
        self.invalidate_recordset([
            'used_days', 'planned_days', 'total_available', 'remaining_days',
        ])
        self._compute_used_days()
        self._compute_totals()
        return True

    def action_recalculate_all(self):
        """
        Recalculate or generate vacation balances for the current year
        for all active employees.
        """
        current_year = fields.Date.today().year
        self.generate_balances(year=current_year)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recalculation Complete'),
                'message': _('Vacation balances for %s have been updated for all active employees.', current_year),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
