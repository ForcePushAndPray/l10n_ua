from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


STATE_SELECTION = [
    ('draft', 'Чернетка'),
    ('approved', 'Затверджено'),
    ('paid', 'Виплачено'),
    ('cancelled', 'Скасовано'),
]


class L10nUaScholarshipPayment(models.Model):
    """Відомість виплати стипендій за звітний місяць.

    Один документ → багато рядків (по членах контингенту). При проведенні
    (`action_pay`) можна генерувати account.move з аналітикою КЕКВ/Фонд/КПКВК
    для подальшого контролю ліміту через l10n_ua_budget_treasury.
    """
    _name = 'l10n_ua.scholarship.payment'
    _description = 'Відомість виплати стипендії'
    _order = 'period_year desc, period_month desc, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Номер', required=True, copy=False, default='Нова',
                       tracking=True)
    state = fields.Selection(STATE_SELECTION, default='draft', required=True,
                              tracking=True, copy=False)
    company_id = fields.Many2one('res.company', required=True,
                                  default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id',
                                    store=True, readonly=True)
    scholarship_type_id = fields.Many2one(
        'l10n_ua.scholarship.type', string='Тип стипендії', required=True,
        tracking=True)
    period_year = fields.Integer(string='Рік', required=True, tracking=True,
                                  default=lambda self: fields.Date.today().year)
    period_month = fields.Selection([
        ('1', 'Січень'), ('2', 'Лютий'), ('3', 'Березень'),
        ('4', 'Квітень'), ('5', 'Травень'), ('6', 'Червень'),
        ('7', 'Липень'), ('8', 'Серпень'), ('9', 'Вересень'),
        ('10', 'Жовтень'), ('11', 'Листопад'), ('12', 'Грудень'),
    ], string='Місяць', required=True, tracking=True,
       default=lambda self: str(fields.Date.today().month))
    payment_date = fields.Date(string='Дата виплати', tracking=True,
                                default=fields.Date.context_today)
    academic_year_id = fields.Many2one(
        'l10n_ua.education.academic.year', string='Навчальний рік')
    kekv_id = fields.Many2one(
        'l10n_ua.kekv', string='КЕКВ',
        domain="[('child_ids', '=', False)]",
        compute='_compute_default_kekv', store=True, readonly=False)
    fund_type = fields.Selection([
        ('general', 'Загальний фонд'),
        ('special', 'Спеціальний фонд'),
    ], string='Фонд', required=True, default='general', tracking=True)
    kpkvk_id = fields.Many2one('l10n_ua.kpkvk', string='КПКВК')
    notes = fields.Html(string='Примітки')
    line_ids = fields.One2many(
        'l10n_ua.scholarship.payment.line', 'payment_id',
        string='Рядки виплати', copy=True)
    total_amount = fields.Monetary(string='Усього', currency_field='currency_id',
                                    compute='_compute_total', store=True)
    line_count = fields.Integer(compute='_compute_total', store=True)

    @api.depends('scholarship_type_id')
    def _compute_default_kekv(self):
        for rec in self:
            if rec.scholarship_type_id and not rec.kekv_id:
                rec.kekv_id = rec.scholarship_type_id.default_kekv_id

    @api.depends('line_ids.amount')
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))
            rec.line_count = len(rec.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Нова') == 'Нова':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'l10n_ua.scholarship.payment') or 'Нова'
        return super().create(vals_list)

    # === State machine ===

    def action_approve(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Затверджувати можна лише чернетку.'))
            if not rec.line_ids:
                raise UserError(_('Не можна затвердити порожню відомість.'))
            rec.state = 'approved'

    def action_pay(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('Виплачувати можна лише затверджену відомість.'))
            rec.state = 'paid'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_('Виплачену відомість не можна скасувати — лише сторнувати окремою операцією.'))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('approved', 'cancelled'):
                raise UserError(_('Повернути в чернетку можна лише затверджену або скасовану відомість.'))
            rec.state = 'draft'


class L10nUaScholarshipPaymentLine(models.Model):
    _name = 'l10n_ua.scholarship.payment.line'
    _description = 'Рядок виплати стипендії'
    _order = 'payment_id, member_id'

    payment_id = fields.Many2one('l10n_ua.scholarship.payment', required=True,
                                   ondelete='cascade', index=True)
    company_id = fields.Many2one(related='payment_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='payment_id.currency_id', store=True, readonly=True)
    state = fields.Selection(related='payment_id.state', store=True, readonly=True)
    member_id = fields.Many2one(
        'l10n_ua.education.contingent.member', string='Учень / Студент',
        required=True, ondelete='restrict', index=True,
        domain="[('state', 'in', ('enrolled', 'studying'))]")
    partner_id = fields.Many2one(related='member_id.partner_id', store=True, readonly=True)
    group_id = fields.Many2one(related='member_id.group_id', store=True, readonly=True)
    amount = fields.Monetary(string='Сума', currency_field='currency_id',
                              compute='_compute_amount', store=True, readonly=False,
                              required=True)
    note = fields.Char(string='Примітка')

    @api.depends('payment_id.scholarship_type_id')
    def _compute_amount(self):
        for line in self:
            if not line.amount and line.payment_id.scholarship_type_id:
                line.amount = line.payment_id.scholarship_type_id.monthly_amount

    @api.constrains('amount')
    def _check_non_negative(self):
        for line in self:
            if line.amount < 0:
                raise ValidationError(_('Сума стипендії не може бути від\'ємною.'))

    _member_payment_uniq = models.Constraint(
        'unique(payment_id, member_id)',
        'Один член контингенту не може мати кілька рядків в одній відомості!',
    )
