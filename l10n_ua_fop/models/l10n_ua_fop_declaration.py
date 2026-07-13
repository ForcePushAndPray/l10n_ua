import base64

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


PERIOD_QUARTERS = {
    'q1': ['1'],
    'h1': ['1', '2'],
    '9m': ['1', '2', '3'],
    'year': ['1', '2', '3', '4'],
}

# Reporting period → (PERIOD_TYPE code, PERIOD_MONTH, quarter marker tag) for F0103309.
# The single-tax declaration is cumulative, so the marker follows the last covered quarter.
PERIOD_F0103309 = {
    'q1': ('2', '3', 'H1KV'),
    'h1': ('3', '6', 'H2KV'),
    '9m': ('4', '9', 'H3KV'),
    'year': ('5', '12', 'H4KV'),
}

# Military levy (військовий збір) rate for FOP single-tax payers, %.
FOP_MILITARY_RATE = 1.0

PERIOD_MONTHS = {
    'q1': 3,
    'h1': 6,
    '9m': 9,
    'year': 12,
}


class L10nUaFopDeclaration(models.Model):
    _name = 'l10n_ua.fop.declaration'
    _description = 'Декларація платника єдиного податку'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, period desc'

    name = fields.Char(
        string='Назва',
        compute='_compute_name',
        store=True,
    )
    year = fields.Integer(
        string='Рік',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
        tracking=True,
    )
    period = fields.Selection(
        selection=[
            ('q1', 'I квартал'),
            ('h1', 'Півріччя'),
            ('9m', '9 місяців'),
            ('year', 'Рік'),
        ],
        string='Звітний період',
        required=True,
        tracking=True,
    )
    fop_group_id = fields.Many2one(
        'l10n_ua.fop.group',
        string='Група ЄП',
        required=True,
        tracking=True,
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

    # Income from books
    income_book_ids = fields.Many2many(
        'l10n_ua.fop.income.book',
        string='Книги обліку доходів',
        compute='_compute_income_books',
    )
    total_income = fields.Monetary(
        string='Загальний дохід',
        currency_field='currency_id',
        tracking=True,
    )
    income_limit = fields.Monetary(
        string='Ліміт доходу',
        related='fop_group_id.income_limit',
        currency_field='currency_id',
    )
    income_limit_exceeded = fields.Boolean(
        string='Ліміт перевищено',
        compute='_compute_income_limit_exceeded',
        store=True,
    )

    # Single tax
    tax_rate = fields.Float(
        string='Ставка ЄП (%)',
        related='fop_group_id.tax_rate',
    )
    monthly_tax_amount = fields.Monetary(
        string='Місячна сума ЄП',
        currency_field='currency_id',
        help='Для груп 1 та 2 — фіксована місячна сума єдиного податку',
    )
    single_tax = fields.Monetary(
        string='Єдиний податок',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )

    # ESV
    min_wage = fields.Monetary(
        string='Мінімальна зарплата',
        currency_field='currency_id',
        help='Мінімальна заробітна плата для розрахунку ЄСВ',
    )
    esv_rate = fields.Float(
        string='Ставка ЄСВ (%)',
        default=22.0,
    )
    esv_months = fields.Integer(
        string='Кількість місяців',
        compute='_compute_esv_months',
    )
    esv_base = fields.Monetary(
        string='База нарахування ЄСВ',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )
    esv_amount = fields.Monetary(
        string='Сума ЄСВ',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )

    # Totals
    total_payable = fields.Monetary(
        string='Всього до сплати',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Чернетка'),
            ('calculated', 'Розраховано'),
            ('submitted', 'Подано'),
            ('accepted', 'Прийнято'),
        ],
        string='Статус',
        default='draft',
        tracking=True,
    )
    submission_date = fields.Date(
        string='Дата подання',
    )
    notes = fields.Html(
        string='Примітки',
    )
    xml_file = fields.Binary(
        string='XML файл',
    )
    xml_filename = fields.Char(
        string='Ім\'я файлу',
    )

    _unique_declaration = models.Constraint(
        'unique(year, period, fop_group_id, company_id)',
        'Декларація за цей період та групу вже існує!',
    )

    @api.depends('year', 'period', 'fop_group_id')
    def _compute_name(self):
        period_names = {
            'q1': 'I кв.',
            'h1': 'Півріччя',
            '9m': '9 міс.',
            'year': 'Рік',
        }
        for rec in self:
            period_name = period_names.get(rec.period, '')
            group_name = rec.fop_group_id.name if rec.fop_group_id else ''
            rec.name = f'Декларація ЄП {period_name} {rec.year} ({group_name})'

    @api.depends('year', 'period', 'fop_group_id', 'company_id')
    def _compute_income_books(self):
        for rec in self:
            if rec.year and rec.period and rec.fop_group_id:
                quarters = PERIOD_QUARTERS.get(rec.period, [])
                books = self.env['l10n_ua.fop.income.book'].search([
                    ('year', '=', rec.year),
                    ('quarter', 'in', quarters),
                    ('fop_group_id', '=', rec.fop_group_id.id),
                    ('company_id', '=', rec.company_id.id),
                ])
                rec.income_book_ids = books
            else:
                rec.income_book_ids = False

    @api.depends('total_income', 'income_limit')
    def _compute_income_limit_exceeded(self):
        for rec in self:
            rec.income_limit_exceeded = (
                rec.income_limit > 0 and rec.total_income > rec.income_limit
            )

    @api.depends('period')
    def _compute_esv_months(self):
        for rec in self:
            rec.esv_months = PERIOD_MONTHS.get(rec.period, 0)

    @api.depends(
        'total_income', 'tax_rate', 'monthly_tax_amount',
        'min_wage', 'esv_rate', 'period', 'fop_group_id',
    )
    def _compute_taxes(self):
        for rec in self:
            months = PERIOD_MONTHS.get(rec.period, 0)
            group_code = rec.fop_group_id.code if rec.fop_group_id else ''

            # Single tax: groups 1,2 — fixed monthly; group 3 — % of income
            if group_code in ('1', '2'):
                rec.single_tax = rec.monthly_tax_amount * months
            else:
                rec.single_tax = (
                    rec.total_income * (rec.tax_rate / 100)
                    if rec.tax_rate else 0
                )

            # ESV: min_wage × months × rate
            rec.esv_base = rec.min_wage * months
            rec.esv_amount = (
                rec.esv_base * (rec.esv_rate / 100) if rec.esv_base else 0
            )

            rec.total_payable = rec.single_tax + rec.esv_amount

    def action_calculate(self):
        """Розрахувати декларацію на основі книг обліку доходів."""
        for rec in self:
            if not rec.period or not rec.fop_group_id:
                raise UserError(
                    'Вкажіть звітний період та групу ЄП перед розрахунком.'
                )

            # Find matching income books
            quarters = PERIOD_QUARTERS.get(rec.period, [])
            books = self.env['l10n_ua.fop.income.book'].search([
                ('year', '=', rec.year),
                ('quarter', 'in', quarters),
                ('fop_group_id', '=', rec.fop_group_id.id),
                ('company_id', '=', rec.company_id.id),
                ('state', '=', 'confirmed'),
            ])

            if not books:
                raise UserError(
                    f'Не знайдено підтверджених книг обліку доходів '
                    f'за {rec.year} рік, квартали: '
                    f'{", ".join(quarters)}.\n'
                    f'Створіть та підтвердіть книги обліку перед розрахунком.'
                )

            total_income = sum(books.mapped('total_income'))

            vals = {
                'total_income': total_income,
                'state': 'calculated',
            }

            # Set default min_wage if not set
            if not rec.min_wage:
                # Use 8000 as default 2025 min wage, user should update
                vals['min_wage'] = 8000.0

            rec.write(vals)

            # Check income limit
            if rec.income_limit_exceeded:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Увага!',
                        'message': (
                            f'Дохід {rec.total_income:,.2f} грн перевищує '
                            f'ліміт {rec.income_limit:,.2f} грн для '
                            f'{rec.fop_group_id.name}!'
                        ),
                        'type': 'warning',
                        'sticky': True,
                    },
                }

    def action_submit(self):
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })

    def action_accept(self):
        self.write({'state': 'accepted'})

    def action_draft(self):
        self.write({
            'state': 'draft',
            'submission_date': False,
        })

    def action_view_income_books(self):
        """Відкрити пов'язані книги обліку доходів."""
        self.ensure_one()
        books = self.income_book_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Книги обліку доходів',
            'res_model': 'l10n_ua.fop.income.book',
            'view_mode': 'list,form',
            'domain': [('id', 'in', books.ids)],
        }
        if len(books) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = books.id
        return action

    def action_generate_xml(self):
        """Згенерувати XML декларації ЄП (форма F0103309) для подання до ДПС.

        Делегує рендеринг до єдиного канонічного генератора з
        l10n_ua_tax_F0103309, щоб не дублювати шаблон декларації.
        """
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(
                'Спершу розрахуйте декларацію (кнопка «Розрахувати»), '
                'потім формуйте XML.'
            )

        period_type, period_month, quarter_marker = PERIOD_F0103309.get(
            self.period, ('5', '12', 'H4KV'))

        company = self.company_id
        tax_office = company.l10n_ua_tax_office_id
        activities = [
            (link.kved_id.code, link.kved_id.name)
            for link in company.l10n_ua_kved_ids
        ]

        # Військовий збір: 1% доходу (декларація не веде авансів, тож весь до сплати).
        military_amount = self.total_income * FOP_MILITARY_RATE / 100

        vals = {
            'taxpayer_tin': company.vat or company.company_registry or '',
            'taxpayer_name': company.name or '',
            'taxpayer_address': self.env['l10n_ua.tax.document.wizard']
                ._format_company_address(company),
            'taxpayer_email': company.email or '',
            'taxpayer_phone': company.phone or '',
            'declaration_type': '0',  # Звітна
            'tax_office_code': tax_office.code if tax_office else '',
            'tax_office_name': tax_office.name if tax_office else '',
            'quarter_marker': quarter_marker,
            'period_type': period_type,
            'period_month': period_month,
            'year': self.year,
            'employee_count': 0,
            'activities': activities,
            'income_total': self.total_income,
            'tax_amount': self.single_tax,
            'tax_paid_prev': 0.0,
            'tax_to_pay': self.single_tax,
            'military_amount': military_amount,
            'military_paid_prev': 0.0,
            'military_to_pay': military_amount,
        }

        xml = self.env['l10n_ua.tax.document.wizard']._render_F0103309_xml(vals)
        self.xml_filename = (
            f"{vals['taxpayer_tin']}_{self.year}_{period_month}_F0103309.xml"
        )
        self.xml_file = base64.b64encode(xml.encode('windows-1251'))
        return True
