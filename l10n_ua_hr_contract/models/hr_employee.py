from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Related fields from current_version_id for form display
    contract_type_ua = fields.Selection(
        related='current_version_id.contract_type_ua',
        readonly=False
    )
    is_main_workplace = fields.Boolean(
        related='current_version_id.is_main_workplace',
        readonly=False
    )
    is_part_time = fields.Boolean(
        related='current_version_id.is_part_time',
        readonly=False
    )
    part_time_type = fields.Selection(
        related='current_version_id.part_time_type',
        readonly=False
    )
    work_mode = fields.Selection(
        related='current_version_id.work_mode',
        readonly=False
    )
    work_rate = fields.Float(
        related='current_version_id.work_rate',
        readonly=False
    )
    # Derived from department_id + job_id, so no longer writable from the card:
    # the position is entered once, in the native "Job Position" field.
    staffing_line_id = fields.Many2one(
        related='current_version_id.staffing_line_id'
    )
    # Details of that line, shown next to the position on the Work tab. No
    # explicit strings — the labels come from hr.staffing.table, where they are
    # already translated.
    staffing_date_from = fields.Date(
        related='current_version_id.staffing_line_id.date_from')
    staffing_state = fields.Selection(
        related='current_version_id.staffing_line_id.state')
    staffing_currency_id = fields.Many2one(
        related='current_version_id.staffing_line_id.currency_id')
    staffing_salary = fields.Monetary(
        related='current_version_id.staffing_line_id.salary',
        currency_field='staffing_currency_id')
    staffing_salary_min = fields.Monetary(
        related='current_version_id.staffing_line_id.salary_min',
        currency_field='staffing_currency_id')
    staffing_salary_max = fields.Monetary(
        related='current_version_id.staffing_line_id.salary_max',
        currency_field='staffing_currency_id')
    tariff_grade_id = fields.Many2one(
        related='current_version_id.tariff_grade_id',
        readonly=False
    )
    work_conditions = fields.Selection(
        related='current_version_id.work_conditions',
        readonly=False
    )
    work_conditions_class = fields.Integer(
        related='current_version_id.work_conditions_class',
        readonly=False
    )
    work_conditions_subclass = fields.Integer(
        related='current_version_id.work_conditions_subclass',
        readonly=False
    )
    additional_vacation_days = fields.Integer(
        related='current_version_id.additional_vacation_days',
        readonly=False
    )
    diia_city_employee = fields.Boolean(
        related='current_version_id.diia_city_employee',
        readonly=False
    )
    hire_order_number = fields.Char(
        related='current_version_id.hire_order_number',
        readonly=False
    )
    hire_order_date = fields.Date(
        related='current_version_id.hire_order_date',
        readonly=False
    )
    termination_order_number = fields.Char(
        related='current_version_id.termination_order_number',
        readonly=False
    )
    termination_order_date = fields.Date(
        related='current_version_id.termination_order_date',
        readonly=False
    )
    termination_reason_ua_id = fields.Many2one(
        related='current_version_id.termination_reason_ua_id',
        readonly=False
    )
    probation_period_days = fields.Integer(
        related='current_version_id.probation_period_days',
        readonly=False
    )
    probation_end_date = fields.Date(
        related='current_version_id.probation_end_date',
        readonly=False
    )

    # One2many fields through current version
    allowance_ids = fields.One2many(
        related='current_version_id.allowance_ids',
        readonly=False
    )
    salary_change_ids = fields.One2many(
        related='current_version_id.salary_change_ids',
        readonly=False
    )
    amendment_ids = fields.One2many(
        related='current_version_id.amendment_ids',
        readonly=False
    )

    job_combining_ids = fields.One2many(
        'hr.job.combining',
        'employee_id',
        string='Job Combining',
        groups="hr.group_hr_user"
    )
    job_combining_count = fields.Integer(
        string='Job Combining Count',
        compute='_compute_job_combining_count',
        groups="hr.group_hr_user"
    )

    def _compute_job_combining_count(self):
        for employee in self:
            employee.job_combining_count = len(employee.job_combining_ids)

    def action_open_job_combining(self):
        self.ensure_one()
        return {
            'name': 'Job Combining',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.job.combining',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
