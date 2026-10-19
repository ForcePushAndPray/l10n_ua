from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Підтверджена книга — первинний регістр, з якого рахується декларація: її реквізити
# й записи змінюються лише після повернення в чернетку.
BOOK_LOCKED_FIELDS = frozenset({'year', 'quarter', 'fop_group_id', 'company_id', 'line_ids'})


class L10nUaFopIncomeBook(models.Model):
    _name = 'l10n_ua.fop.income.book'
    _description = 'Книга обліку доходів ФОП'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, quarter desc'

    name = fields.Char(
        string='Назва',
        compute='_compute_name',
        store=True,
    )
    year = fields.Integer(
        string='Рік',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    quarter = fields.Selection(
        selection=[
            ('1', 'I квартал'),
            ('2', 'II квартал'),
            ('3', 'III квартал'),
            ('4', 'IV квартал'),
        ],
        string='Квартал',
        required=True,
    )
    fop_group_id = fields.Many2one(
        'l10n_ua.fop.group',
        string='Група ЄП',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    line_ids = fields.One2many(
        'l10n_ua.fop.income.book.line',
        'book_id',
        string='Записи',
    )
    total_income = fields.Monetary(
        string='Загальний дохід',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    line_count = fields.Integer(
        string='Кількість записів',
        compute='_compute_totals',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Чернетка'),
            ('confirmed', 'Підтверджено'),
        ],
        string='Статус',
        default='draft',
        tracking=True,
    )

    _unique_book = models.Constraint(
        'unique(year, quarter, fop_group_id, company_id)',
        'Книга обліку за цей квартал та групу вже існує!',
    )

    @api.depends('year', 'quarter')
    def _compute_name(self):
        quarter_names = {
            '1': 'I кв.', '2': 'II кв.', '3': 'III кв.', '4': 'IV кв.',
        }
        for rec in self:
            qname = quarter_names.get(rec.quarter, '')
            rec.name = f'Книга доходів {qname} {rec.year}'

    @api.depends('line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_income = sum(rec.line_ids.mapped('amount'))
            rec.line_count = len(rec.line_ids)

    def write(self, vals):
        if BOOK_LOCKED_FIELDS.intersection(vals):
            self._check_not_confirmed()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        self._check_not_confirmed()

    def _check_not_confirmed(self):
        confirmed = self.filtered(lambda b: b.state == 'confirmed')
        if confirmed:
            raise UserError(_(
                'Книгу «%s» підтверджено — її не можна змінювати. Щоб виправити, '
                'поверніть її в чернетку.') % confirmed[0].name)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print_income_book(self):
        """Друк книги обліку доходів."""
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_fop.action_report_income_book'
        ).report_action(self)


class L10nUaFopIncomeBookLine(models.Model):
    _name = 'l10n_ua.fop.income.book.line'
    _description = 'Запис книги обліку доходів'
    _order = 'date, id'

    book_id = fields.Many2one(
        'l10n_ua.fop.income.book',
        string='Книга доходів',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Дата',
        required=True,
    )
    document_number = fields.Char(
        string='№ документа',
    )
    description = fields.Char(
        string='Опис операції',
    )
    income_type = fields.Selection(
        selection=[
            ('cash', 'Готівка'),
            ('bank', 'Безготівковий'),
            ('card', 'Картка'),
        ],
        string='Вид доходу',
        default='bank',
    )
    amount = fields.Monetary(
        string='Сума, грн',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='book_id.currency_id',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Контрагент',
    )
    bank_statement_line_id = fields.Many2one(
        'account.bank.statement.line',
        string='Рядок банківської виписки',
    )

    @api.model_create_multi
    def create(self, vals_list):
        book_ids = {vals.get('book_id') for vals in vals_list if vals.get('book_id')}
        self.env['l10n_ua.fop.income.book'].browse(book_ids)._check_not_confirmed()
        return super().create(vals_list)

    def write(self, vals):
        self.book_id._check_not_confirmed()
        if vals.get('book_id'):
            self.env['l10n_ua.fop.income.book'].browse(vals['book_id'])._check_not_confirmed()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed_book(self):
        self.book_id._check_not_confirmed()

