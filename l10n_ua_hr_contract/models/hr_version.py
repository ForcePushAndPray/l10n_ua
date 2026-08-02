from odoo import models, fields, api
from odoo.exceptions import ValidationError
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
        groups="hr.group_hr_user"
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
            version.total_wage = version.wage + version.total_allowances

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

    @api.onchange('staffing_line_id')
    def _onchange_staffing_line_id(self):
        """Suggest wage from staffing table based on company setting"""
        if not self.staffing_line_id:
            return

        company = self.env.company
        setting = company.wage_from_staffing if hasattr(company, 'wage_from_staffing') else 'both'

        if setting in ('suggest', 'both'):
            staffing = self.staffing_line_id
            if staffing.salary and (not self.wage or self.wage == 0):
                self.wage = staffing.salary

    @api.constrains('work_rate')
    def _check_work_rate(self):
        for version in self:
            if version.work_rate and (version.work_rate <= 0 or version.work_rate > 2):
                raise ValidationError('Work rate must be between 0 and 2.')

    @api.constrains('wage', 'staffing_line_id')
    def _check_wage_in_salary_range(self):
        for version in self:
            if version.staffing_line_id and version.wage:
                staffing = version.staffing_line_id
                if staffing.salary_min and version.wage < staffing.salary_min:
                    raise ValidationError(
                        'Salary %.2f is below position minimum %.2f for %s' %
                        (version.wage, staffing.salary_min, staffing.name)
                    )
                if staffing.salary_max and version.wage > staffing.salary_max:
                    raise ValidationError(
                        'Salary %.2f exceeds position maximum %.2f for %s' %
                        (version.wage, staffing.salary_max, staffing.name)
                    )
