from collections import defaultdict

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrStaffingTable(models.Model):
    _name = 'hr.staffing.table'
    _description = 'Staffing Table'
    _order = 'date_from desc, department_id, job_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company)
    department_id = fields.Many2one(
        'hr.department', string='Department',
        required=True, index=True)
    job_id = fields.Many2one(
        'hr.job', string='Position',
        required=True, index=True)
    units = fields.Float(
        string='Staff Units', default=1.0,
        help='Number of staff units (e.g., 0.5, 1.0, 2.0)')
    filled_units = fields.Float(
        string='Filled Units', compute='_compute_filled_units', store=True)
    vacant_units = fields.Float(
        string='Vacant Units', compute='_compute_vacant_units', store=True)
    salary = fields.Monetary(
        string='Salary', currency_field='currency_id',
        required=True,
        help='Standard salary for this position')
    salary_min = fields.Monetary(
        string='Minimum Salary', currency_field='currency_id',
        help='Minimum salary for this position (salary range)')
    salary_max = fields.Monetary(
        string='Maximum Salary', currency_field='currency_id',
        help='Maximum salary for this position (salary range)')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    total_salary_fund = fields.Monetary(
        string='Total Salary Fund', currency_field='currency_id',
        compute='_compute_total_salary_fund', store=True)
    date_from = fields.Date(
        string='Effective From', required=True,
        default=fields.Date.context_today)
    date_to = fields.Date(string='Effective Until')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', tracking=True)
    order_number = fields.Char(string='Order Number')
    order_date = fields.Date(string='Order Date')
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.department_id and self.department_id.company_id \
                and self.department_id.company_id != self.company_id:
            self.department_id = False
        if self.job_id and self.job_id.company_id \
                and self.job_id.company_id != self.company_id:
            self.job_id = False

    @api.depends('department_id', 'job_id')
    def _compute_name(self):
        for record in self:
            dept = record.department_id.name or ''
            job = record.job_id.name or ''
            record.name = f"{dept} / {job}"

    @api.depends('units', 'salary')
    def _compute_total_salary_fund(self):
        for record in self:
            record.total_salary_fund = record.units * record.salary

    @api.depends(
        'department_id', 
        'job_id', 
        'state',
        'job_id.employee_ids',
        'job_id.employee_ids.department_id',
        'job_id.employee_ids.active',
        'job_id.employee_ids.current_version_id'
    )
    def _compute_filled_units(self):
        for record in self:
            if record.state == 'approved' and record.department_id and record.job_id:
                employees = self.env['hr.employee'].search([
                    ('department_id', '=', record.department_id.id),
                    ('job_id', '=', record.job_id.id),
                    ('active', '=', True),
                ])
                # Sum work_rate for all employees (0.5 for part-time, 1.0 for full-time)
                total_rate = 0.0
                for emp in employees:
                    version = emp.current_version_id
                    # `work_rate` додає l10n_ua_hr_contract, який залежить
                    # від цього модуля, а не навпаки — тож поля може не бути.
                    if version and 'work_rate' in version._fields and version.work_rate:
                        total_rate += version.work_rate
                    else:
                        total_rate += 1.0  # Default full-time
                # Суміщення (сумісництво) споживає свою частку штатної одиниці
                # цієї посади нарівні з основними працівниками (#149).
                Combining = self.env.get('hr.job.combining')
                if Combining is not None:
                    combinings = Combining.search([
                        ('combined_department_id', '=', record.department_id.id),
                        ('combined_job_id', '=', record.job_id.id),
                        ('state', '=', 'active'),
                    ])
                    total_rate += sum(
                        c.combined_rate or 0.0 for c in combinings)
                record.filled_units = total_rate
            else:
                record.filled_units = 0.0

    @api.depends('units', 'filled_units')
    def _compute_vacant_units(self):
        for record in self:
            record.vacant_units = max(0.0, record.units - record.filled_units)

    # === Resolution ===
    # A position is identified by (company, department, job); which line of the
    # staffing table applies is then a question of date. Everything that needs
    # "the staffing line of this employee" goes through here, so the rule lives
    # in one place.

    @api.model
    def _resolve(self, company, department, job, ref_date):
        """Approved line in force for this position on `ref_date`.

        Returns an empty recordset when the position is not covered by the
        staffing table — a legitimate state, not an error: keeping a staffing
        table is a choice, and civil-law contracts never occupy a staff unit.
        """
        if not (company and department and job and ref_date):
            return self.browse()
        key = (company.id, department.id, job.id, ref_date)
        return self._resolve_batch([key]).get(key, self.browse())

    @api.model
    def _resolve_batch(self, keys):
        """Resolve many positions at once: {(company, department, job, date): line}.

        Keys carry ids, not recordsets, so they stay hashable. One query serves
        the whole batch — the callers are computed fields read over a list view,
        where a query per record would be felt immediately.
        """
        keys = [key for key in keys if all(key)]
        if not keys:
            return {}
        lines = self.search([
            ('company_id', 'in', list({key[0] for key in keys})),
            ('department_id', 'in', list({key[1] for key in keys})),
            ('job_id', 'in', list({key[2] for key in keys})),
            ('state', '=', 'approved'),
        ], order='date_from desc')

        by_position = defaultdict(list)
        for line in lines:
            by_position[(
                line.company_id.id, line.department_id.id, line.job_id.id,
            )].append(line)

        resolved = {}
        for key in keys:
            ref_date = key[3]
            for line in by_position.get(key[:3], ()):
                # Ordered by date_from desc, so the first line whose period
                # covers the date is the one in force. Overlapping approved
                # periods are a data defect; picking the latest start keeps the
                # outcome deterministic until they are cleaned up.
                if line.date_from <= ref_date and (
                        not line.date_to or line.date_to >= ref_date):
                    resolved[key] = line
                    break
        return resolved

    @api.constrains('units')
    def _check_units(self):
        for record in self:
            if record.units <= 0:
                raise ValidationError('Staff units must be greater than 0!')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError('End date must be after start date!')

    @api.constrains('salary', 'salary_min', 'salary_max')
    def _check_salary_range(self):
        for record in self:
            if record.salary_min and record.salary_max:
                if record.salary_min > record.salary_max:
                    raise ValidationError('Minimum salary cannot exceed maximum salary!')
            if record.salary:
                if record.salary_min and record.salary < record.salary_min:
                    raise ValidationError('Standard salary cannot be below minimum salary!')
                if record.salary_max and record.salary > record.salary_max:
                    raise ValidationError('Standard salary cannot exceed maximum salary!')

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_draft(self):
        self.write({'state': 'draft'})
