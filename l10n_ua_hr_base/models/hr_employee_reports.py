import base64
import csv
import io
from datetime import date

from odoo import models, fields, api, _

def _was_employed_on(employee, as_of):
    """Return True if employee (active or archived) was employed on as_of date.

    Employment is detected per-version: at least one contract version has a
    start date <= as_of AND either no end date or an end date >= as_of.
    This handles rehires correctly — e.g. a fixed-term version that ended
    in 2023 followed by an open-ended version starting in 2024 keeps the
    employee 'employed' in 2025 via the second version, even though the
    first version's end date is earlier than as_of.

    The day of departure is included on purpose (end >= as_of): the last
    working day still counts as employed. This snapshot semantics differs
    from headcount reports that use strict > to count active days only.

    Falls back to employee-level hire_date / departure_date when no contract
    version carries dates. Reading uses active_test=False so archived
    employees' versions stay visible.
    """
    if not as_of:
        return True

    employee = employee.with_context(active_test=False)

    def has(rec, name):
        return name in rec._fields

    has_any_version_date = False
    for v in employee.version_ids:
        starts = [v.contract_date_start]
        if has(v, 'date_start'):
            starts.append(v.date_start)
        if has(v, 'date_version'):
            starts.append(v.date_version)
        ends = [v.contract_date_end]
        if has(v, 'date_end'):
            ends.append(v.date_end)

        version_starts = [d for d in starts if d]
        version_ends = [d for d in ends if d]
        if version_starts or version_ends:
            has_any_version_date = True
        if not any(s <= as_of for s in version_starts):
            continue
        if not version_ends or max(version_ends) >= as_of:
            return True

    if has_any_version_date:
        return False

    hire_candidates = [employee.hire_date]
    if has(employee, 'first_contract_date'):
        hire_candidates.append(employee.first_contract_date)
    if not any(d and d <= as_of for d in hire_candidates):
        return False

    departure = employee.departure_date if has(employee, 'departure_date') else False
    return not departure or departure >= as_of

class HrEmployeeListReport(models.Model):
    """Employee List Report (Список працівників).

    Snapshot of active employees as of a specific date. Saved and
    reusable; can be regenerated and printed to PDF.
    """
    _name = 'hr.employee.list.report'
    _description = 'Employee List Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    employee_count = fields.Integer(
        string='Total',
        compute='_compute_employee_count',
        store=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('generated', 'Generated')],
        default='draft',
        tracking=True,
    )
    notes = fields.Text()

    @api.depends('date')
    def _compute_name(self):
        for rec in self:
            if rec.date:
                rec.name = f"Список працівників станом на {rec.date.strftime('%d.%m.%Y')}"
            else:
                rec.name = 'Список працівників'

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.with_context(active_test=False).employee_ids)

    def _domain_employees(self):
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
        ]

    def action_generate(self):
        for rec in self:
            candidates = rec.env['hr.employee'].with_context(
                active_test=False).search(rec._domain_employees())
            as_of = rec.date
            # Keep only employees (active or archived) employed on the date.
            employees = candidates.filtered(
                lambda e: _was_employed_on(e, as_of))

            rec.write({
                'employee_ids': [(6, 0, employees.ids)],
                'state': 'generated',
            })
        return True

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_hr_base.action_report_hr_employee_list'
        ).report_action(self)


class HrEmployeeMilitaryReport(models.Model):
    """Military Personnel Report (Військовозобов'язані)."""
    _name = 'hr.employee.military.report'
    _description = 'Military Personnel Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    employee_count = fields.Integer(
        string='Total',
        compute='_compute_employee_count',
        store=True,
    )
    reserved_count = fields.Integer(
        string='Reserved',
        compute='_compute_employee_count',
        store=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('generated', 'Generated')],
        default='draft',
        tracking=True,
    )
    notes = fields.Text()

    @api.depends('date')
    def _compute_name(self):
        for rec in self:
            if rec.date:
                rec.name = f"Військовозобов'язані станом на {rec.date.strftime('%d.%m.%Y')}"
            else:
                rec.name = "Військовозобов'язані"

    @api.depends('employee_ids', 'employee_ids.military_reservation')
    def _compute_employee_count(self):
        for rec in self:
            employees = rec.with_context(active_test=False).employee_ids
            rec.employee_count = len(employees)
            rec.reserved_count = len(employees.filtered('military_reservation'))


    def action_generate(self):
        for rec in self:
            candidates = rec.env['hr.employee'].with_context(active_test=False).search([
                ('company_id', '=', rec.company_id.id),
                ('military_register_category', 'in',
                    ['conscript', 'liable', 'reservist']),
            ])
            as_of = rec.date
            employees = candidates.filtered(
                lambda e: _was_employed_on(e, as_of))
            rec.write({
                'employee_ids': [(6, 0, employees.ids)],
                'state': 'generated',
            })
        return True

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_hr_base.action_report_hr_employee_military'
        ).report_action(self)

    # --- Експорт списку персонального військового обліку для ТЦК (#156) ---
    export_data = fields.Binary(string='Export File', readonly=True, copy=False)
    export_filename = fields.Char(string='Export File Name', readonly=True, copy=False)

    def action_export_csv(self):
        """Сформувати CSV-список персонального військового обліку для ТЦК.

        Склад даних — за Постановою КМУ № 1487 (персональний облік): РНОКПП,
        ПІБ, дата народження, категорія обліку, ВОС, звання, ТЦК, документ,
        бронювання. Файл — windows-1251 (для держсистем/Excel UA).
        """
        self.ensure_one()
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=';')
        writer.writerow([
            'РНОКПП', 'ПІБ', 'Дата народження', 'Категорія обліку',
            'ВОС', 'Звання', 'ТЦК та СП', 'Військовий документ',
            'Заброньований', 'Бронювання до'])
        for emp in self.with_context(active_test=False).employee_ids:
            writer.writerow([
                emp.rnokpp or '',
                emp.name or '',
                emp.birthday.strftime('%d.%m.%Y') if emp.birthday else '',
                dict(emp._fields['military_register_category'].selection).get(
                    emp.military_register_category, ''),
                emp.military_specialty or '',
                emp.military_rank_id.name or '',
                emp.military_tcc_id.name or '',
                emp.military_document_number or '',
                'так' if emp.military_reservation else 'ні',
                emp.military_reservation_until.strftime('%d.%m.%Y')
                if emp.military_reservation_until else '',
            ])
        content = buf.getvalue().encode('cp1251', 'replace')
        self.export_data = base64.b64encode(content)
        self.export_filename = 'vijskovyj_oblik_%s.csv' % (
            self.date.strftime('%Y_%m_%d') if self.date else 'list')
        return True


class HrMilitaryNotification(models.Model):
    """Повідомлення до ТЦК та СП про зміни у військовозобов'язаних (#156).

    Аудит-журнал повідомлень про прийняття / звільнення / зміну облікових
    даних (Постанова КМУ № 1487). На підтвердженні знімає snapshot ключових
    реквізитів і формує CSV-файл повідомлення для подання.
    """
    _name = 'hr.military.notification'
    _description = 'Military Notification to TCC'
    _inherit = ['mail.thread']
    _order = 'event_date desc, id desc'

    name = fields.Char(string='Reference', default='New', copy=False)
    notification_type = fields.Selection([
        ('hire', 'Прийняття на роботу'),
        ('dismissal', 'Звільнення'),
        ('data_change', 'Зміна облікових даних'),
    ], string='Type', required=True, default='hire', tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)
    event_date = fields.Date(
        string='Event Date', required=True,
        default=fields.Date.context_today, tracking=True)
    military_tcc_id = fields.Many2one(
        'hr.military.tcc', related='employee_id.military_tcc_id',
        string='TCC', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ], string='Status', default='draft', tracking=True)
    submitted_date = fields.Date(string='Submitted On', readonly=True)
    # Snapshot реквізитів на момент подання (аудит).
    snapshot_rnokpp = fields.Char(string='RNOKPP (snapshot)', readonly=True)
    snapshot_data = fields.Text(string='Data (snapshot)', readonly=True)
    export_data = fields.Binary(string='Notification File', readonly=True, copy=False)
    export_filename = fields.Char(readonly=True, copy=False)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.military.notification') or 'New'
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            emp = rec.employee_id
            rec.snapshot_rnokpp = emp.rnokpp or ''
            rec.snapshot_data = (
                '%s; %s; ВОС %s; ТЦК %s; док. %s' % (
                    emp.name or '',
                    emp.birthday.strftime('%d.%m.%Y') if emp.birthday else '',
                    emp.military_specialty or '',
                    emp.military_tcc_id.name or '',
                    emp.military_document_number or ''))
            rec._build_export()
            rec.write({
                'state': 'submitted',
                'submitted_date': fields.Date.context_today(rec),
            })
        return True

    def _build_export(self):
        self.ensure_one()
        emp = self.employee_id
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=';')
        type_label = dict(self._fields['notification_type'].selection).get(
            self.notification_type, '')
        writer.writerow(['Тип повідомлення', 'РНОКПП', 'ПІБ',
                         'Дата народження', 'ВОС', 'ТЦК та СП',
                         'Військовий документ', 'Дата події'])
        writer.writerow([
            type_label, emp.rnokpp or '', emp.name or '',
            emp.birthday.strftime('%d.%m.%Y') if emp.birthday else '',
            emp.military_specialty or '', emp.military_tcc_id.name or '',
            emp.military_document_number or '',
            self.event_date.strftime('%d.%m.%Y') if self.event_date else '',
        ])
        content = buf.getvalue().encode('cp1251', 'replace')
        self.export_data = base64.b64encode(content)
        self.export_filename = 'tcc_notification_%s.csv' % (self.name or '').replace(
            '/', '_')


class HrEmployeeMilitaryOperationalReport(models.Model):
    """Відомість оперативного військового обліку — журнал змін за період (ПКМУ № 1487).

    Tracks military-related events during a date range: hires, dismissals,
    register_category changes, reservation changes. Source data comes from
    mail.message tracking values on hr.employee (military_* fields are tracked
    automatically by Odoo's mail.thread when @tracking is set on the model).
    """
    _name = 'hr.employee.military.operational.report'
    _description = 'Військовий облік: відомість оперативного обліку'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    date_from = fields.Date(
        string='Період з',
        required=True,
        default=lambda self: date.today().replace(day=1),
        tracking=True,
    )
    date_to = fields.Date(
        string='Період до',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    line_ids = fields.One2many(
        'hr.employee.military.operational.report.line',
        'report_id',
        string='Записи журналу',
    )
    line_count = fields.Integer(
        compute='_compute_line_count', store=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('generated', 'Generated')],
        default='draft',
        tracking=True,
    )

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.name = (
                    f"Оперативний облік {rec.date_from.strftime('%d.%m.%Y')} – "
                    f"{rec.date_to.strftime('%d.%m.%Y')}"
                )
            else:
                rec.name = "Оперативний військовий облік"

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def action_generate(self):
        """Build journal from hr.order events + employee tracking changes."""
        self.ensure_one()
        self.line_ids.unlink()
        lines = []
        Order = self.env.get('hr.order')

        # 1) Hires + dismissals from hr.order (if l10n_ua_hr_documents installed)
        if Order is not None:
            orders = Order.search([
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('order_type', 'in', ['hiring', 'dismissal']),
                ('company_id', '=', self.company_id.id),
                ('state', '!=', 'cancelled'),
            ])
            for order in orders:
                if not order.employee_id or order.employee_id.military_register_category == 'not_applicable':
                    continue
                event = 'Прийом на роботу' if order.order_type == 'hiring' else 'Звільнення'
                lines.append((0, 0, {
                    'date': order.date,
                    'employee_id': order.employee_id.id,
                    'event_type': order.order_type,
                    'description': f'{event} (наказ № {order.name})',
                }))

        # 2) Tracked field changes from mail.message
        domain = [
            ('model', '=', 'hr.employee'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        messages = self.env['mail.message'].search(domain)
        tracked_fields = (
            'military_register_category', 'military_fitness',
            'military_reservation', 'military_reservation_until',
            'military_medical_category',
        )
        for msg in messages:
            for tracking in msg.tracking_value_ids:
                if tracking.field_id.name not in tracked_fields:
                    continue
                employee = self.env['hr.employee'].browse(msg.res_id)
                if not employee.exists() or employee.company_id != self.company_id:
                    continue
                lines.append((0, 0, {
                    'date': msg.date.date(),
                    'employee_id': employee.id,
                    'event_type': 'change',
                    'description': (
                        f'{tracking.field_id.field_description}: '
                        f'{tracking.old_value_char or tracking.old_value_text or "—"} → '
                        f'{tracking.new_value_char or tracking.new_value_text or "—"}'
                    ),
                }))

        self.write({
            'line_ids': lines,
            'state': 'generated',
        })
        return True

    def action_draft(self):
        self.line_ids.unlink()
        self.write({'state': 'draft'})


class HrEmployeeMilitaryOperationalReportLine(models.Model):
    _name = 'hr.employee.military.operational.report.line'
    _description = 'Запис журналу оперативного обліку'
    _order = 'date, id'

    report_id = fields.Many2one(
        'hr.employee.military.operational.report',
        required=True, ondelete='cascade', index=True,
    )
    date = fields.Date(required=True)
    employee_id = fields.Many2one('hr.employee', required=True)
    event_type = fields.Selection([
        ('hiring', 'Прийом на роботу'),
        ('dismissal', 'Звільнення'),
        ('change', 'Зміна стану'),
    ], required=True)
    description = fields.Char()


class HrEmployeeBenefitsReport(models.Model):
    """Employees with Benefits Report (Працівники з пільгами)."""
    _name = 'hr.employee.benefits.report'
    _description = 'Employees with Benefits Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    employee_count = fields.Integer(
        string='Total',
        compute='_compute_employee_count',
        store=True,
    )
    disabled_count = fields.Integer(
        string='With Disability',
        compute='_compute_employee_count',
        store=True,
    )
    chornobyl_count = fields.Integer(
        string='Chornobyl',
        compute='_compute_employee_count',
        store=True,
    )
    veteran_count = fields.Integer(
        string='Veterans',
        compute='_compute_employee_count',
        store=True,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('generated', 'Generated')],
        default='draft',
        tracking=True,
    )
    notes = fields.Text()

    @api.depends('date')
    def _compute_name(self):
        for rec in self:
            if rec.date:
                rec.name = f"Працівники з пільгами станом на {rec.date.strftime('%d.%m.%Y')}"
            else:
                rec.name = 'Працівники з пільгами'

    @api.depends('employee_ids', 'employee_ids.disability_group',
                 'employee_ids.chornobyl_category', 'employee_ids.veteran_status')
    def _compute_employee_count(self):
        for rec in self:
            employees = rec.with_context(active_test=False).employee_ids
            rec.employee_count = len(employees)
            rec.disabled_count = len(employees.filtered(
                lambda e: e.disability_group and e.disability_group != 'none'))
            rec.chornobyl_count = len(employees.filtered(
                lambda e: e.chornobyl_category and e.chornobyl_category != 'none'))
            rec.veteran_count = len(employees.filtered(
                lambda e: e.veteran_status and e.veteran_status != 'none'))

    def action_generate(self):
        for rec in self:
            candidates = rec.env['hr.employee'].with_context(active_test=False).search([
                ('company_id', '=', rec.company_id.id),
                '|', '|', '|',
                ('disability_group', 'not in', [False, 'none']),
                ('chornobyl_category', 'not in', [False, 'none']),
                ('veteran_status', 'not in', [False, 'none']),
                ('benefit_ids', '!=', False),
            ])
            as_of = rec.date
            employees = candidates.filtered(
                lambda e: _was_employed_on(e, as_of))
            rec.write({
                'employee_ids': [(6, 0, employees.ids)],
                'state': 'generated',
            })
        return True

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_hr_base.action_report_hr_employee_benefits'
        ).report_action(self)
