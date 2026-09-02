from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import format_date, formatLang
from dateutil.relativedelta import relativedelta


class HrVersion(models.Model):
    _inherit = 'hr.version'

    # === Ukrainian Contract Types ===
    contract_type_ua = fields.Selection([
        ('permanent', 'Permanent (Indefinite)'),
        ('fixed_term', 'Fixed Term'),
        ('contract', 'Contract'),
        ('civil', 'Civil Law Contract'),
        ('gig', 'Gig Contract (Diia.City)'),
        ('author', 'Author Contract'),
        ('seasonal', 'Seasonal Work'),
        ('temporary', 'Temporary Work'),
    ], string='Contract Type (UA)', default='permanent', tracking=True,
       groups="hr.group_hr_user")

    # === Workplace Configuration ===
    is_main_workplace = fields.Boolean(
        string='Main Workplace',
        default=True,
        tracking=True,
        groups="hr.group_hr_user"
    )
    is_part_time = fields.Boolean(
        string='Part-time Work',
        tracking=True,
        groups="hr.group_hr_user"
    )
    part_time_type = fields.Selection([
        ('internal', 'Internal Part-time'),
        ('external', 'External Part-time'),
    ], string='Part-time Type', groups="hr.group_hr_user")

    # === Work Mode ===
    work_mode = fields.Selection([
        ('full_time', 'Full-time'),
        ('part_time', 'Part-time'),
        ('flexible', 'Flexible Schedule'),
        ('remote', 'Remote Work'),
        ('hybrid', 'Hybrid'),
    ], string='Work Mode', default='full_time', tracking=True,
       groups="hr.group_hr_user")

    work_rate = fields.Float(
        string='Work Rate',
        default=1.0,
        help='1.0 = full rate, 0.5 = half rate, etc.',
        groups="hr.group_hr_user"
    )
    scheduled_hours_week = fields.Float(
        string='Норма годин/тиждень',
        compute='_compute_scheduled_norm',
        store=True,
        groups="hr.group_hr_user",
        help='Норма робочого часу на тиждень з урахуванням ставки зайнятості '
             '(work_rate): 0.5 ставки → 20 год при 40-годинному тижні.'
    )
    scheduled_hours_day = fields.Float(
        string='Норма годин/день',
        compute='_compute_scheduled_norm',
        store=True,
        groups="hr.group_hr_user",
        help='Норма робочого часу на день з урахуванням ставки зайнятості '
             '(work_rate): 0.5 ставки → 4 год при 8-годинному дні.'
    )

    # === Probation ===
    probation_period_days = fields.Integer(
        string='Probation Period (days)',
        groups="hr.group_hr_user"
    )
    probation_end_date = fields.Date(
        string='Probation End Date',
        compute='_compute_probation_end_date',
        store=True,
        groups="hr.group_hr_user"
    )

    # === Staffing & Tariff ===
    staffing_line_id = fields.Many2one(
        'hr.staffing.table',
        string='Staffing Position',
        compute='_compute_staffing_line_id',
        compute_sudo=True,
        groups="hr.group_hr_user",
        help='Staffing table line matching the department and the job of this '
             'version on the date it is in force. Not filled in by hand: the '
             'position is entered once, in the native Job Position field, and '
             'the staffing line follows from it.'
    )
    tariff_grade_id = fields.Many2one(
        'hr.tariff.grade',
        string='Tariff Grade',
        groups="hr.group_hr_user"
    )

    # === Allowances ===
    allowance_ids = fields.One2many(
        'hr.version.allowance',
        'version_id',
        string='Allowances',
        groups="hr.group_hr_user"
    )
    total_allowances = fields.Monetary(
        string='Total Allowances',
        compute='_compute_total_allowances',
        store=True,
        groups="hr.group_hr_manager"
    )
    total_wage = fields.Monetary(
        string='Total Wage',
        compute='_compute_total_wage',
        store=True,
        groups="hr.group_hr_manager"
    )

    # === Termination (UA) ===
    termination_reason_ua_id = fields.Many2one(
        'hr.termination.reason',
        string='Termination Reason (UA)',
        groups="hr.group_hr_user"
    )

    # === Orders ===
    hire_order_number = fields.Char(
        string='Hire Order Number',
        groups="hr.group_hr_user"
    )
    hire_order_date = fields.Date(
        string='Hire Order Date',
        groups="hr.group_hr_user"
    )
    termination_order_number = fields.Char(
        string='Termination Order Number',
        groups="hr.group_hr_user"
    )
    termination_order_date = fields.Date(
        string='Termination Order Date',
        groups="hr.group_hr_user"
    )

    # === Diia.City ===
    diia_city_employee = fields.Boolean(
        string='Diia.City Employee',
        help='Employee under Diia.City special tax regime',
        groups="hr.group_hr_user"
    )

    # === Work Conditions ===
    work_conditions = fields.Selection([
        ('normal', 'Normal'),
        ('hazardous', 'Hazardous (Шкідливі)'),
        ('heavy', 'Heavy (Важкі)'),
        ('underground', 'Underground Work'),
    ], string='Work Conditions', default='normal', tracking=True,
       groups="hr.group_hr_user")

    work_conditions_class = fields.Integer(
        string='Hazard Class (1-4)',
        help='Hazard classification class according to DSTU',
        groups="hr.group_hr_user"
    )
    work_conditions_subclass = fields.Integer(
        string='Hazard Subclass',
        help='Hazard subclass within the class',
        groups="hr.group_hr_user"
    )

    additional_vacation_days = fields.Integer(
        string='Additional Vacation Days',
        compute='_compute_additional_vacation_days',
        store=True,
        help='Additional vacation days based on work conditions',
        groups="hr.group_hr_user"
    )

    # === Related Records ===
    salary_change_ids = fields.One2many(
        'hr.version.salary.change',
        'version_id',
        string='Salary Changes',
        groups="hr.group_hr_user"
    )
    amendment_ids = fields.One2many(
        'hr.version.amendment',
        'version_id',
        string='Amendments',
        groups="hr.group_hr_user"
    )
    job_combining_ids = fields.One2many(
        'hr.job.combining',
        'version_id',
        string='Job Combining',
        groups="hr.group_hr_user"
    )

    @api.depends('contract_date_start', 'probation_period_days')
    def _compute_probation_end_date(self):
        for version in self:
            if version.contract_date_start and version.probation_period_days:
                version.probation_end_date = version.contract_date_start + relativedelta(days=version.probation_period_days)
            else:
                version.probation_end_date = False

    @api.depends('allowance_ids.calculated_amount')
    def _compute_total_allowances(self):
        for version in self:
            version.total_allowances = sum(
                a.calculated_amount for a in version.allowance_ids.filtered('is_active')
            )

    @api.depends('wage', 'total_allowances')
    def _compute_total_wage(self):
        for version in self:
            # Надбавки гривневі, оклад може бути у валюті — без перерахунку
            # це сума різних валют під однією гривневою міткою.
            try:
                wage = version._l10n_ua_wage_in_company_currency(
                    version.date_version)
            except UserError:
                # Курсу немає — беремо оклад як є, тим самим фолбеком, що й
                # надбавка. Обнуляти не можна: у картці договору вийшло б,
                # що підсумок менший за самі надбавки.
                wage = version.wage or 0.0
            version.total_wage = wage + version.total_allowances

    @api.depends('work_rate',
                 'resource_calendar_id.hours_per_week',
                 'resource_calendar_id.hours_per_day')
    def _compute_scheduled_norm(self):
        """Норма годин пропорційна ставці зайнятості (work_rate).

        Базова норма береться зі штатного календаря версії
        (resource_calendar_id) — того самого, з якого списують відпустки, тож
        зарплата й відпустки більше не можуть розійтися (#213).

        Календар без рядків присутності дав би нульову норму, тому лишається
        запобіжник на 40-годинний тиждень: краще типова норма, ніж мовчазний
        нуль у розрахунку зарплати. Передвизначені змінні графіки цього
        запобіжника не потребують — у них норма задана явно.
        """
        for version in self:
            rate = version.work_rate if version.work_rate else 1.0
            calendar = version.resource_calendar_id
            week = calendar.hours_per_week if calendar else 0.0
            day = calendar.hours_per_day if calendar else 0.0
            if not week:
                week = 40.0
            if not day:
                day = week / 5.0
            version.scheduled_hours_week = week * rate
            version.scheduled_hours_day = day * rate

    @api.depends('work_conditions', 'work_conditions_class')
    def _compute_additional_vacation_days(self):
        for version in self:
            days = 0
            if version.work_conditions == 'hazardous':
                if version.work_conditions_class:
                    days = min(35, version.work_conditions_class * 7)
                else:
                    days = 4
            elif version.work_conditions == 'heavy':
                if version.work_conditions_class:
                    days = min(35, version.work_conditions_class * 7)
                else:
                    days = 4
            elif version.work_conditions == 'underground':
                days = 7
            version.additional_vacation_days = days

    # === Staffing line resolution ===

    @api.depends('company_id', 'department_id', 'job_id', 'date_version',
                 'contract_date_start', 'contract_date_end',
                 'employee_id.version_ids.date_version')
    def _compute_staffing_line_id(self):
        """Staffing line of the position, as of the date this version is in force.

        A superseded version resolves against the staffing table as it stood at
        the end of its own period; the current, open-ended version resolves
        against today. That second half is what makes the field usable for the
        ordinary Ukrainian case — a permanent contract whose salary is revised
        every year without a new version ever being created.
        """
        today = fields.Date.context_today(self)
        sibling_dates = defaultdict(list)
        employees = self.employee_id
        if employees:
            for version in self.env['hr.version'].search(
                    [('employee_id', 'in', employees.ids)]):
                sibling_dates[version.employee_id.id].append(version.date_version)

        keys = {}
        for version in self:
            ref_date = version._staffing_ref_date(
                sibling_dates.get(version.employee_id.id, ()), today)
            keys[version.id] = (
                version.company_id.id, version.department_id.id,
                version.job_id.id, ref_date,
            )
        resolved = self.env['hr.staffing.table']._resolve_batch(list(keys.values()))
        for version in self:
            version.staffing_line_id = resolved.get(keys[version.id], False)

    def _staffing_ref_date(self, sibling_dates, today):
        """Date this version is read against — see `_reference_date`.

        The rule itself lives on `hr.staffing.table`, because the employee card
        asks the same question about fields it is still editing.
        """
        self.ensure_one()
        return self.env['hr.staffing.table']._reference_date(
            self.date_version, self.contract_date_start,
            self.contract_date_end, sibling_dates, today)

    @api.onchange('job_id', 'department_id')
    def _onchange_job_suggest_wage(self):
        """Suggest wage from staffing table based on company setting.

        Triggered by the position rather than by `staffing_line_id`: the latter
        is a computed field now, and an onchange on a computed field is not a
        trigger worth depending on.
        """
        if not self.staffing_line_id:
            return

        company = self.env.company
        setting = company.wage_from_staffing or 'both'

        if setting in ('suggest', 'both'):
            staffing = self.staffing_line_id
            if staffing.salary and (not self.wage or self.wage == 0):
                self.wage = staffing.salary

    @api.constrains('work_rate')
    def _check_work_rate(self):
        for version in self:
            if version.work_rate and (version.work_rate <= 0 or version.work_rate > 2):
                raise ValidationError('Work rate must be between 0 and 2.')

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._warn_wage_out_of_staffing_range()
        return versions

    def write(self, vals):
        if 'wage' not in vals:
            return super().write(vals)
        # Only versions whose wage actually moves deserve a note: saving the
        # same form twice must not post the same warning twice.
        changed = self.filtered(lambda version: version.wage != vals['wage'])
        result = super().write(vals)
        changed._warn_wage_out_of_staffing_range()
        return result

    def _warn_wage_out_of_staffing_range(self):
        """Note in the employee's chatter when the wage leaves the staffing range.

        Deliberately not a constraint. Ukrainian salaries — and the ranges
        themselves — are revised far more often than the staffing table is
        rewritten, so a blocking check would reliably stop the very operation
        that must not be stopped: a pay rise. The numbers are stated, the
        decision stays with the HR officer.
        """
        today = fields.Date.context_today(self)
        for version in self:
            employee = version.employee_id
            if not (employee and version.wage):
                continue
            line = version.sudo().staffing_line_id
            if not line or not (line.salary_min or line.salary_max):
                continue
            wage = version._staffing_comparable_wage(line, today)
            below = line.salary_min and wage < line.salary_min
            above = line.salary_max and wage > line.salary_max
            if not (below or above):
                continue
            employee.message_post(body=_(
                'Wage %(wage)s is outside the staffing table range: the line '
                'of %(date)s "%(position)s" provides for %(range)s. '
                'Please review the staffing table.',
                wage=formatLang(self.env, wage, currency_obj=line.currency_id),
                date=format_date(self.env, line.date_from),
                position=line.name,
                range=version._staffing_range_label(line),
            ))

    def _staffing_range_label(self, line):
        """Human-readable salary range of a staffing line ("16 000 - 22 000")."""
        low = formatLang(self.env, line.salary_min, currency_obj=line.currency_id)
        high = formatLang(self.env, line.salary_max, currency_obj=line.currency_id)
        if line.salary_min and line.salary_max:
            return '%s - %s' % (low, high)
        if line.salary_min:
            return _('at least %s', low)
        return _('at most %s', high)

    def _staffing_comparable_wage(self, line, today):
        """The wage expressed in the currency of the staffing line.

        The range is denominated in the line's currency while the wage may be
        set in another one (foreign-currency contracts, Diia.City gigs).
        Comparing the raw numbers would report a wage of 1 000 USD as falling
        below a minimum of 16 000 UAH. The conversion is the shared one from
        l10n_ua_hr_base, so the figure quoted in the note is the figure payroll
        will work with.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        date = self.date_version or today
        try:
            wage = self._l10n_ua_wage_in_company_currency(date)
        except UserError:
            # No rate for that day. A note is not a blocking check, so the raw
            # figure beats silence: the wage may well be out of range, and the
            # missing rate is already reported where it does block - payroll.
            return self.wage
        if line.currency_id and line.currency_id != company.currency_id:
            return company.currency_id._convert(
                wage, line.currency_id, company, date)
        return wage
