from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

class HrVacationBalance(models.Model):
    _name = 'hr.vacation.balance'
    _description = 'Vacation Balance'
    _order = 'period_start desc, employee_id'

    # Record name is the period range. Odoo's base display_name is computed
    # from _rec_name on the fly, so there is no stored display_name to keep
    # in sync (and no employee name to leak into the label).
    _rec_name = 'period_label'


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
        domain="[('ua_leave_category', '!=', False)]"
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
    
    @api.model
    def _get_period_for(self, employee, leave_type, ref_date):
        """Return (period_start, period_end, period_index) of the accounting
        period containing ref_date for the given employee and leave type.

        Work-year types delegate to hr.employee._get_work_year_for_date;
        calendar types return Jan 1 – Dec 31 with period_index = year.
        Returns (False, False, 0) for work types without a hire anchor, or
        for any period that ends before the employee's hire date (no leave
        or balance can exist before the person was hired).
        """
        if leave_type.period_type == 'work':
            return employee._get_work_year_for_date(ref_date)
        hire = self._employee_hire_anchor(employee)
        if hire and date(ref_date.year, 12, 31) < hire:
            # The whole calendar year precedes the hire date.
            return (False, False, 0)
        return (date(ref_date.year, 1, 1), date(ref_date.year, 12, 31), ref_date.year)

    @api.model
    def _get_or_create_period(self, employee, leave_type, ref_date):
        """Return the accounting period (hr.vacation.balance) that contains
        ref_date for this employee/leave type, creating it if it does not
        exist yet. A newly created period inherits its carried_over days from
        the previous period in the chain. Returns an empty recordset when the
        period cannot be resolved (e.g. a work-year type without a hire
        anchor), so callers can leave the leave unlinked in that edge case."""
        if not employee or not leave_type or not ref_date:
            return self.browse()
        start, end, index = self._get_period_for(employee, leave_type, ref_date)
        if not start:
            return self.browse()
        balance = self.search([
            ('employee_id', '=', employee.id),
            ('leave_type_id', '=', leave_type.id),
            ('period_start', '=', start),
        ], limit=1)
        if balance:
            return balance
        prev = self.search([
            ('employee_id', '=', employee.id),
            ('leave_type_id', '=', leave_type.id),
            ('period_index', '=', index - 1),
        ], limit=1)
        return self.create({
            'employee_id': employee.id,
            'leave_type_id': leave_type.id,
            'period_start': start,
            'period_end': end,
            'period_index': index,
            'entitled_days': leave_type.annual_days,
            'carried_over': prev.remaining_days if prev else 0,
            'company_id': employee.company_id.id or self.env.company.id,
        })

    @api.model
    def _employee_hire_anchor(self, employee):
        """Explicit hire date used to bound accounting periods and to block
        pre-hire leaves/periods. Only employee.hire_date (the UA-managed
        field) is used here — the work-year anchor keeps its own
        contract_date_start fallback in hr.employee._get_work_year_for_date,
        but the hard block relies on the value HR actually maintains."""
        return employee.hire_date if employee else False

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

    @api.model
    def default_get(self, fields_list):
        """Prefill the balance from the leave form's context.

        The Vacation Period field on hr.leave passes default_employee_id,
        default_leave_type_id and default_period_year; from those we can
        resolve the whole accounting period (dates, index, company) up
        front, so the "create period" dialog opens fully populated.
        """
        res = super().default_get(fields_list)
        ctx = self.env.context
        emp_id = res.get('employee_id') or ctx.get('default_employee_id')
        lt_id = res.get('leave_type_id') or ctx.get('default_leave_type_id')
        if emp_id and lt_id and not res.get('period_start'):
            employee = self.env['hr.employee'].browse(emp_id)
            leave_type = self.env['hr.leave.type'].browse(lt_id)
            ref_year = ctx.get('default_period_year') or fields.Date.today().year
            start, end, index = self._get_period_for(
                employee, leave_type, self._ref_date_for_year(ref_year))
            if not start:
                # Work-year type without a hire anchor: calendar fallback
                start, end, index = (
                    date(ref_year, 1, 1), date(ref_year, 12, 31), ref_year)
            res.setdefault('period_start', start)
            res.setdefault('period_end', end)
            res.setdefault('period_index', index)
            if 'company_id' in fields_list and not res.get('company_id'):
                res['company_id'] = employee.company_id.id or self.env.company.id
        return res

    @api.onchange('company_id')
    def _onchange_company_id(self):
        # Only clear a now-incompatible employee/type on a genuine company
        # switch — never wipe values prefilled from the leave form.
        if (self.employee_id and self.employee_id.company_id
                and self.company_id
                and self.employee_id.company_id != self.company_id):
            self.employee_id = False
        if (self.leave_type_id and self.leave_type_id.company_id
                and self.company_id
                and self.leave_type_id.company_id != self.company_id):
            self.leave_type_id = False

    @api.onchange('employee_id', 'leave_type_id')
    def _onchange_period_defaults(self):
        """Prefill the accounting period once employee and type are chosen."""
        for rec in self:
            if not rec.employee_id or not rec.leave_type_id or rec.period_start:
                continue
            ref_year = self.env.context.get('default_period_year')
            ref_date = (self._ref_date_for_year(ref_year) if ref_year
                        else fields.Date.context_today(self))
            start, end, index = self._get_period_for(
                rec.employee_id, rec.leave_type_id, ref_date)
            if not start:
                # Work-year type without hire anchor: calendar fallback
                start, end, index = (
                    date(ref_date.year, 1, 1), date(ref_date.year, 12, 31),
                    ref_date.year)
            rec.period_start = start
            rec.period_end = end
            rec.period_index = index

    @api.constrains('period_start', 'period_end')
    def _check_period_bounds(self):
        for rec in self:
            if rec.period_start and rec.period_end and rec.period_start > rec.period_end:
                raise ValidationError(_('Period start must be before period end.'))

    @api.constrains('period_end', 'employee_id', 'leave_type_id')
    def _check_period_after_hire(self):
        """No accounting period may end before the employee was hired."""
        for rec in self:
            if not rec.employee_id or not rec.period_end:
                continue
            hire = self._employee_hire_anchor(rec.employee_id)
            if hire and rec.period_end < hire:
                raise ValidationError(_(
                    'The accounting period (ending %(end)s) precedes the hire '
                    'date of %(employee)s (%(hire)s). A vacation period cannot '
                    'start before the employee was hired.',
                    end=rec.period_end.strftime('%d.%m.%Y'),
                    employee=rec.employee_id.name,
                    hire=hire.strftime('%d.%m.%Y'),
                ))

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
            # legacy leaves whose START date falls inside this period.
            # A leave belongs to the single period containing its start
            # date — matching on vacation_year instead would lump leaves
            # from other work years that merely share a calendar year with
            # this period's start (e.g. a Feb-2026 leave of the 2025/26
            # work year vs the 2026/27 work year, both year == 2026).
            base_domain = [
                ('employee_id', '=', rec.employee_id.id),
                ('holiday_status_id', '=', rec.leave_type_id.id),
                '|',
                    ('vacation_balance_id', '=', rec.id),
                    '&', '&',
                        ('vacation_balance_id', '=', False),
                        ('request_date_from', '>=', rec.period_start),
                        ('request_date_from', '<=', rec.period_end),
            ]

            used_leaves = HrLeave.search(base_domain + [('state', '=', 'validate')])
            rec.used_days = sum(used_leaves.mapped('calendar_days'))

            planned_leaves = HrLeave.search(base_domain + [
                ('state', 'in', ('draft', 'confirm', 'validate1')),
            ])
            rec.planned_days = sum(planned_leaves.mapped('calendar_days'))

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

    def _recompute_carryover_chain(self):
        """Propagate carry-over across each (employee, leave_type) period
        chain: every period after the first inherits the previous period's
        remaining days.

        Lets a back-dated period feed its unused days into the following
        periods (e.g. a leave entered late for last year updates this
        year's Carried Over). The first period keeps its own (possibly
        manual) carried_over untouched.
        """
        seen = set()
        for rec in self:
            if not rec.employee_id or not rec.leave_type_id:
                continue
            key = (rec.employee_id.id, rec.leave_type_id.id)
            if key in seen:
                continue
            seen.add(key)
            chain = self.search([
                ('employee_id', '=', rec.employee_id.id),
                ('leave_type_id', '=', rec.leave_type_id.id),
            ], order='period_start')
            prev = None
            for bal in chain:
                if prev is not None and bal.carried_over != prev.remaining_days:
                    bal.carried_over = prev.remaining_days
                prev = bal

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
                          '&', ('request_date_from', '>=', balance.period_start),
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
        # Attach pre-existing leaves, then refresh rollups so used_days
        # reflects them before the carry-over is propagated.
        balances._link_related_leaves()
        balances.invalidate_recordset([
            'used_days', 'planned_days', 'total_available', 'remaining_days',
        ])
        balances._compute_used_days()
        balances._compute_totals()
        balances._recompute_related_leaves()
        # A new (possibly back-dated) period may change carry-over downstream.
        balances._recompute_carryover_chain()
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

    def _reanchor_period(self):
        """Fix work-year bounds that don't match the employee's hire
        anniversary — e.g. a balance created or migrated while the
        employee had no hire anchor yet (calendar fallback applied), or
        whose hire_date was corrected afterwards.
        Keeps the row's original start year as the anniversary year so
        `year` and year-based reports stay stable. Skips silently when
        no anchor is available or the target period already exists.
        """
        self.ensure_one()
        if self.period_type != 'work' or not self.employee_id:
            return
        anchor = self.employee_id.hire_date
        if not anchor:
            version = self.employee_id.current_version_id
            anchor = version.contract_date_start if version else False
        if not anchor:
            return
        index = (self.year or anchor.year) - anchor.year + 1
        if index < 1:
            return
        start = anchor + relativedelta(years=index - 1)
        end = anchor + relativedelta(years=index) - relativedelta(days=1)
        if start == self.period_start:
            return
        conflict = self.search_count([
            ('employee_id', '=', self.employee_id.id),
            ('leave_type_id', '=', self.leave_type_id.id),
            ('period_start', '=', start),
            ('id', '!=', self.id),
        ])
        if conflict:
            return
        self.write({
            'period_start': start,
            'period_end': end,
            'period_index': index,
        })

    def action_recalculate(self):
        for rec in self:
            rec._reanchor_period()
            if rec.leave_type_id and not rec.entitled_days:
                rec.entitled_days = rec.leave_type_id.annual_days or 0
        self.invalidate_recordset([
            'used_days', 'planned_days', 'total_available', 'remaining_days',
        ])
        self._compute_used_days()
        self._compute_totals()
        self._recompute_carryover_chain()
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
