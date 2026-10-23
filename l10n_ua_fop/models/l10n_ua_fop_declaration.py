import base64
import logging
import os
import re
from datetime import datetime

from lxml import etree

from odoo import api, fields, models, _
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

# Групи з фіксованими ЄП і військовим збором (1, 2); F0103309 — декларація 3 групи.
FIXED_TAX_GROUPS = ('1', '2')
# Військовий збір платників ЄП діє з 01.01.2025:
# 3 група — % доходу; 1–2 групи — % мінімальної зарплати щомісяця.
FOP_MILITARY_FROM_YEAR = 2025
FOP_MILITARY_RATE = 1.0
FOP_MILITARY_MIN_WAGE_SHARE = 10.0

# Зворотний бік: XML поданої декларації (з кабінету) → звітний період.
F0103309_PERIOD_TYPES = {'2': 'q1', '3': 'h1', '4': '9m', '5': 'year'}
F0103309_BODY_MARKERS = {'H1KV': 'q1', 'HHY': 'h1', 'H3KV': '9m', 'HY': 'year'}

_logger = logging.getLogger(__name__)

# Подана до ДПС декларація — документ, що вже в податковій: її суми й реквізити
# змінюються лише уточнюючою декларацією, не правкою запису.
LOCKED_STATES = ('submitted', 'accepted')
LOCKED_FIELDS = frozenset({
    'year', 'period', 'fop_group_id', 'company_id', 'total_income',
    'monthly_tax_amount', 'esv_rate', 'esv_annex', 'xml_file', 'xml_filename', 'submission_date',
    'notes', 'tax_document_id', 'kvt2_document_id', 'dps_submission_id',
})
# Контекст для службових змін стану й даних поданої декларації (подання, прийняття,
# імпорт з кабінету) — користувацькі правки його не мають.
UNLOCK_CTX = 'l10n_ua_fop_declaration_unlock'

F0103309_CODE = 'F0103309'
# Річна декларація ФОП 1–2 груп — та сама форма, лише за рік (#331).
F0103407_CODE = 'F0103407'
DECLARATION_CODES = (F0103309_CODE, F0103407_CODE)
# Квитанція № 2 у вхідних кабінету: «Квитанцiя № 2[J1499202]» (i буває латинська).
KVT2_RE = re.compile(r'квитанц[iі]я\s*№\s*2', re.IGNORECASE)
KVT2_REJECTED_RE = re.compile(r'не\s+прийнят|вiдмов|відмов', re.IGNORECASE)


def _decode_kvt(data_b64):
    if not data_b64:
        return ''
    raw = base64.b64decode(data_b64)
    for encoding in ('utf-8', 'windows-1251'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


PERIOD_MONTHS = {
    'q1': 3,
    'h1': 6,
    '9m': 9,
    'year': 12,
}


class L10nUaFopDeclaration(models.Model):
    _name = 'l10n_ua.fop.declaration'
    _description = 'Декларація платника єдиного податку'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'l10n_ua.dps.submit.mixin']
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
        compute='_compute_income_limit',
        store=True,
        currency_field='currency_id',
        help='Граничний дохід групи: множник групи × мінімальна заробітна плата '
             'на 1 січня року декларації (п. 291.4 ПКУ).',
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
        compute='_compute_min_wage',
        store=True,
        currency_field='currency_id',
        help='Мінімальна заробітна плата на кінець звітного періоду (довідник '
             '«Мінімальна заробітна плата»). ЄСВ рахується від мінімальної '
             'зарплати кожного місяця періоду.',
    )
    esv_annex = fields.Boolean(
        string='Додаток 1 (ЄСВ)',
        tracking=True,
        help='ЄСВ ФОП звітує додатком 1 до декларації — щомісяця, щокварталу чи раз на '
             'рік, як обрано. Без додатка ЄСВ у декларації не рахується й не входить у '
             '«Всього до сплати». Для декларацій з кабінету — за ознакою HD1 поданого XML.',
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

    # Military levy
    military_levy = fields.Monetary(
        string='Військовий збір',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
        help='З 2025 року: 1–2 групи — 10 % мінімальної заробітної плати за кожен '
             'місяць періоду; 3 група — 1 % доходу.',
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
    dps_submission_id = fields.Char(
        string='ID подання в ДПС',
        copy=False,
        readonly=True,
        help='Ідентифікатор, який кабінет ДПС повернув при поданні; на нього '
             'посилаються квитанції.',
    )
    kvt2_document_id = fields.Many2one(
        'l10n_ua.tax.document',
        string='Квитанція № 2',
        copy=False,
        readonly=True,
        ondelete='set null',
        help='Квитанція ДПС про реєстрацію (або неприйняття) поданої декларації — '
             'з вхідної кореспонденції Електронного кабінету.',
    )
    tax_document_id = fields.Many2one(
        'l10n_ua.tax.document',
        string='Поданий документ',
        copy=False,
        readonly=True,
        index='btree_not_null',
        ondelete='set null',
        help='Запис журналу «Усі подані документи», з якого імпортовано декларацію '
             '(XML і PDF з Електронного кабінету, реєстраційний номер).',
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

    def _period_month_min_wages(self):
        """Мінімальна зарплата кожного місяця звітного періоду (від січня).

        Нуль на місці місяця означає, що на цей рік довідник ще не заповнено.
        """
        self.ensure_one()
        if not self.year or not self.period:
            return []
        MinWage = self.env['l10n_ua.min.wage']
        return [
            MinWage._get_amount(f'{self.year}-{month:02d}-01')
            for month in range(1, PERIOD_MONTHS.get(self.period, 0) + 1)
        ]

    @api.depends('year', 'fop_group_id.limit_min_wages')
    def _compute_income_limit(self):
        for rec in self:
            rec.income_limit = (
                rec.fop_group_id._get_income_limit(rec.year)
                if rec.fop_group_id and rec.year else 0.0
            )

    @api.depends('total_income', 'income_limit')
    def _compute_income_limit_exceeded(self):
        for rec in self:
            rec.income_limit_exceeded = (
                rec.income_limit > 0 and rec.total_income > rec.income_limit
            )

    @api.depends('year', 'period')
    def _compute_min_wage(self):
        for rec in self:
            month_wages = rec._period_month_min_wages()
            rec.min_wage = month_wages[-1] if month_wages else 0.0

    @api.depends('period')
    def _compute_esv_months(self):
        for rec in self:
            rec.esv_months = PERIOD_MONTHS.get(rec.period, 0)

    @api.depends(
        'total_income', 'tax_rate', 'monthly_tax_amount',
        'year', 'esv_rate', 'esv_annex', 'period', 'fop_group_id',
    )
    def _compute_taxes(self):
        for rec in self:
            months = PERIOD_MONTHS.get(rec.period, 0)
            group_code = rec.fop_group_id.code if rec.fop_group_id else ''
            month_wages = rec._period_month_min_wages()

            # Single tax: groups 1,2 — fixed monthly; group 3 — % of income
            if group_code in FIXED_TAX_GROUPS:
                rec.single_tax = rec.monthly_tax_amount * months
            else:
                rec.single_tax = (
                    rec.total_income * (rec.tax_rate / 100)
                    if rec.tax_rate else 0
                )

            # ESV: мінімальний внесок щомісяця — від мінзарплати цього місяця
            # (у 2024 вона змінилась з квітня, тож «одна сума × місяці» хибна).
            # Лише якщо до декларації додається додаток 1 (ЄСВ).
            rec.esv_base = sum(month_wages) if rec.esv_annex else 0.0
            rec.esv_amount = (
                rec.esv_base * (rec.esv_rate / 100) if rec.esv_base else 0
            )

            if not rec.year or rec.year < FOP_MILITARY_FROM_YEAR:
                rec.military_levy = 0.0
            elif group_code in FIXED_TAX_GROUPS:
                # 10 % мінімальної зарплати, встановленої на 1 січня року, за кожен
                # місяць (пп. 16¹.4 п. 16¹ підрозд. 10 розд. XX ПКУ; рядок 22 форми).
                rec.military_levy = round(
                    month_wages[0] * FOP_MILITARY_MIN_WAGE_SHARE / 100 * months, 2
                ) if month_wages else 0.0
            else:
                rec.military_levy = round(
                    rec.total_income * FOP_MILITARY_RATE / 100, 2)

            rec.total_payable = rec.single_tax + rec.esv_amount + rec.military_levy

    def action_calculate(self):
        """Розрахувати декларацію на основі книг обліку доходів."""
        for rec in self:
            if not rec.period or not rec.fop_group_id:
                raise UserError(
                    'Вкажіть звітний період та групу ЄП перед розрахунком.'
                )

            # Довідник мінзарплати міг змінитися вже після створення декларації
            # (додали новий рік) — збережені суми треба перерахувати.
            for fname in ('min_wage', 'income_limit', 'income_limit_exceeded',
                          'esv_base', 'esv_amount', 'military_levy', 'total_payable'):
                self.env.add_to_compute(rec._fields[fname], rec)

            if not all(rec._period_month_min_wages()):
                raise UserError(_(
                    'У довіднику немає мінімальної заробітної плати на %s рік — '
                    'від неї рахуються ЄСВ і ліміт доходу групи. Додайте розмір: '
                    'Taxes UA → Configuration → Мінімальна заробітна плата.'
                ) % rec.year)

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

            rec.write({
                'total_income': total_income,
                'state': 'calculated',
            })

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
        """Відкрити КЕП-підпис і подання декларації ЄП до ДПС."""
        return self.action_kep_submit()

    def _declaration_code(self):
        """Електронна форма: F0103309 (3 група, квартал) чи F0103407 (1–2 групи, рік)."""
        self.ensure_one()
        return F0103407_CODE if self.fop_group_id.code in FIXED_TAX_GROUPS else F0103309_CODE

    def _check_f0103309_group(self):
        """1–2 групи звітують раз на рік (п. 296.2 ПКУ) — формою F0103407."""
        for rec in self:
            if rec.fop_group_id.code in FIXED_TAX_GROUPS and rec.period != 'year':
                raise UserError(_(
                    'ФОП %s групи подає декларацію лише за рік (F0103407). Створіть '
                    'декларацію з періодом «Рік».') % rec.fop_group_id.code)

    # --- контракт l10n_ua.dps.submit.mixin ---

    def _dps_check_can_submit(self):
        self._check_f0103309_group()
        for rec in self:
            if rec.state == 'draft':
                raise UserError(_(
                    'Спершу розрахуйте декларацію (кнопка «Розрахувати»).'))

    def _dps_ensure_xml(self):
        self.ensure_one()
        if not self.xml_file:
            self.action_generate_xml()

    def _dps_submit_label(self):
        return _('Подати декларацію ЄП до ДПС')

    def _dps_on_submitted(self, receipt):
        self.with_context(**{UNLOCK_CTX: True}).write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })
        self.message_post(body=_('Подано до ДПС. Квитанція: %s') % (receipt or '—'))

    def action_accept(self):
        self.filtered(lambda d: d.state == 'submitted').with_context(
            **{UNLOCK_CTX: True}).write({'state': 'accepted'})

    def action_check_dps(self):
        """Перевірити в кабінеті ДПС, чи зареєстровано подану декларацію.

        Підпис коду платника — у браузері (діалог КЕП, режим ``check``); далі
        ``kep_submit_signed`` синхронізує подані звіти за звітний період і
        прив'язує знайдений документ до декларації.
        """
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('Перевірити в ДПС можна лише подану декларацію.'))
        self._dps_config()
        return self.action_kep_sign(mode='check')

    def _check_dps_registration(self, auth_signature):
        """Забрати з кабінету подані звіти за звітний період і знайти цю декларацію."""
        self.ensure_one()
        config = self._dps_config()
        TaxDocument = self.env['l10n_ua.tax.document']
        # Кабінет групує подані звіти за звітним періодом: 9 міс. 2026 — місяць 09.2026.
        TaxDocument._sync_reported_documents(
            config, self.year, PERIOD_MONTHS[self.period], auth_signature=auth_signature)
        if self.state == 'submitted':
            # Документ могли забрати синхронізацією раніше, ніж декларацію подали з Odoo:
            # повторна синхронізація його пропускає, тож прив'язуємо тут.
            linked = self.search([('tax_document_id', '!=', False)]).tax_document_id
            for doc in TaxDocument.search([
                ('document_type_id.code', 'in', DECLARATION_CODES),
                ('company_id', '=', self.company_id.id),
                ('file_xml', '!=', False),
                ('id', 'not in', linked.ids),
            ]):
                data = self._parse_f0103309(base64.b64decode(doc.file_xml))
                if data and (data['year'], data['period']) == (self.year, self.period) \
                        and not data['correction']:
                    self._import_from_tax_document(doc)
                    break
        if self.state == 'accepted' and self.tax_document_id:
            number = self.tax_document_id.document_number
            return _('ДПС зареєструвала декларацію%s. Статус — «Прийнято».') % (
                _(', реєстраційний № %s') % number if number else '')
        if self.state == 'submitted':
            # До «Перегляду звітності» документ потрапляє із затримкою, а квитанція № 2
            # приходить одразу — у вхідну кореспонденцію.
            receipt = self._check_dps_kvt2(config, auth_signature)
            if receipt:
                return receipt
        return _('У кабінеті ДПС декларації за цей період ще немає: квитанції № 2 '
                 '(реєстрації) поки не надійшло. Перевірте пізніше.')

    def _check_dps_kvt2(self, config, auth_signature):
        """Квитанція № 2 на цю декларацію у вхідних кабінету → стан і вкладення.

        Квитанцію впізнаємо за посиланням на id подання (``codRegdocRef``) або за
        ім'ям файлу декларації, яке ДПС повторює в тексті квитанції.
        """
        self.ensure_one()
        data = config._api_get_incoming_documents(0, auth_signature=auth_signature)
        items = data.get('content', []) if isinstance(data, dict) else data or []
        fname = os.path.splitext(self._dps_filename())[0].upper()
        for item in items:
            name = str(item.get('name') or '')
            if not KVT2_RE.search(name):
                continue
            ref = str(item.get('codRegdocRef') or '')
            year = item.get('periodYear') or self.year
            xml = config._api_download_document_xml(
                year, item.get('id'), 'incoming', auth_signature=auth_signature)
            text = _decode_kvt(xml)
            if not (self.dps_submission_id and ref == self.dps_submission_id) \
                    and fname not in text.upper():
                continue
            return self._receive_kvt2(config, item, xml, auth_signature)
        return None

    def _receive_kvt2(self, config, item, xml, auth_signature):
        """Квитанцію № 2 — у журнал податкових документів і до декларації."""
        self.ensure_one()
        TaxDocument = self.env['l10n_ua.tax.document']
        domain = [('external_id', '=', str(item.get('id'))), ('source', '=', 'cabinet')]
        doc = TaxDocument.search(domain, limit=1)
        if not doc:
            # Імпорт сам викликає _l10n_ua_after_import → _link_kvt2_document.
            TaxDocument._process_api_documents(
                config, [item], 'incoming', item.get('periodYear') or self.year,
                auth_signature=auth_signature)
            doc = TaxDocument.search(domain, limit=1)
        if doc and not doc.file_xml and xml:
            doc.write({'file_xml': xml, 'file_xml_name': '%s.xml' % doc.external_id})
        if doc and doc.file_xml:
            self._link_kvt2_document(doc)
        if self.state == 'accepted':
            number = self._kvt2_info().get('number')
            return _('ДПС прийняла декларацію%s (квитанція № 2). Статус — «Прийнято». '
                     'Поданий документ прив\'яжеться, щойно з\'явиться в «Перегляді '
                     'звітності».') % (_(', реєстраційний № %s') % number if number else '')
        if self.kvt2_document_id:
            return _('ДПС не прийняла декларацію — див. квитанцію № 2. '
                     'Виправте декларацію (кнопка «В чернетку») і подайте ще раз.')
        return None

    def _kvt2_info(self):
        doc = self.kvt2_document_id
        return self._parse_kvt2(base64.b64decode(doc.file_xml)) or {} if doc.file_xml else {}

    @api.model
    def _parse_kvt2(self, xml_bytes):
        """Квитанція № 2 (J1499202): на який документ, результат, реєстраційний номер."""
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            return None
        head = root.find('DECLARHEAD')
        body = root.find('DECLARBODY')
        if head is None or body is None:
            return None

        def text(node, tag):
            el = node.find(tag)
            return (el.text or '').strip() if el is not None and el.text else ''

        if (text(head, 'C_DOC') + text(head, 'C_DOC_SUB')) != 'J14992':
            return None
        result = text(body, 'HRESULT')
        return {
            'doc_code': text(body, 'HDOCKOD'),
            'fname': os.path.splitext(text(body, 'HFILENAME'))[0].upper(),
            'year': int(text(head, 'PERIOD_YEAR') or text(body, 'HZY') or 0),
            'period': F0103309_PERIOD_TYPES.get(text(head, 'PERIOD_TYPE')),
            'result': result,
            'rejected': bool(KVT2_REJECTED_RE.search(result + ' ' + text(body, 'TEXT'))),
            'number': text(body, 'HNUMREG'),
        }

    @api.model
    def _link_kvt2_document(self, doc):
        """Квитанція № 2 з журналу → її декларація ЄП (за періодом і ім'ям файлу).

        Подану декларацію квитанція переводить у «Прийнято» (або повідомляє про
        неприйняття). Повторний виклик нічого не дублює.
        """
        info = self._parse_kvt2(base64.b64decode(doc.file_xml))
        if not info or info['doc_code'] not in DECLARATION_CODES or not info['period']:
            return self.browse()
        declaration = self.search([
            ('year', '=', info['year']),
            ('period', '=', info['period']),
            ('company_id', '=', doc.company_id.id),
        ]).filtered(lambda d: os.path.splitext(d._dps_filename())[0].upper() == info['fname'])[:1]
        if not declaration:
            return declaration
        is_new = declaration.kvt2_document_id != doc
        vals = {'kvt2_document_id': doc.id}
        accept = declaration.state == 'submitted' and not info['rejected']
        if accept:
            vals['state'] = 'accepted'
        declaration.with_context(**{UNLOCK_CTX: True}).write(vals)
        if accept:
            reg = _(', реєстраційний № %s') % info['number'] if info['number'] else ''
            declaration.message_post(body=_(
                'Квитанція № 2: декларацію прийнято ДПС%s.') % reg)
        elif info['rejected'] and is_new and declaration.state == 'submitted':
            declaration.message_post(body=_(
                'Квитанція № 2: ДПС не прийняла декларацію — %s') % info['result'])
        return declaration

    def _dps_store_receipts(self, result):
        # id подання — на нього посилаються квитанції ДПС (codRegdocRef).
        for item in result if isinstance(result, list) else [result]:
            if isinstance(item, dict) and item.get('id'):
                self.dps_submission_id = str(item['id'])
                break
        return super()._dps_store_receipts(result)

    def kep_prepare_signing(self):
        if self.env.context.get('kep_mode') != 'check':
            return super().kep_prepare_signing()
        self.ensure_one()
        config = self._dps_config()
        return {
            'auth_subject': config.taxpayer_code or '',
            'submit_label': _('Перевірити в ДПС'),
            'description': _('Пошук «%s» серед поданих документів у Електронному кабінеті '
                             'та прив\'язка до неї документа ДПС.') % self.name,
            'documents': [],
        }

    def kep_submit_signed(self, signed, auth_signature=None):
        if self.env.context.get('kep_mode') != 'check':
            return super().kep_submit_signed(signed, auth_signature)
        return {'receipt': self._check_dps_registration(auth_signature)}

    def action_draft(self):
        """Повернути в чернетку; прийнята ДПС декларація не повертається."""
        if self.filtered(lambda d: d.state == 'accepted'):
            raise UserError(_(
                'Декларацію прийнято ДПС — змінити її можна лише уточнюючою декларацією '
                '(подайте її в Електронному кабінеті, після синхронізації вона з\'явиться '
                'в журналі поданих документів).'))
        for rec in self.filtered(lambda d: d.state == 'submitted'):
            rec.message_post(body=_('Подану декларацію повернуто в чернетку (наприклад, '
                                    'ДПС її не прийняла).'))
        self.with_context(**{UNLOCK_CTX: True}).write({
            'state': 'draft',
            'submission_date': False,
        })

    def write(self, vals):
        if not self.env.context.get(UNLOCK_CTX):
            locked = self.filtered(lambda d: d.state in LOCKED_STATES)
            changed = sorted(LOCKED_FIELDS.intersection(vals))
            if locked and (changed or 'state' in vals):
                fields_desc = ', '.join(self._fields[f].string for f in changed) or _('статус')
                raise UserError(_(
                    'Декларацію «%(name)s» подано до ДПС — %(fields)s не змінюються. '
                    'Помилку у прийнятій декларації виправляють уточнюючою декларацією.',
                    name=locked[0].name, fields=fields_desc))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_filed(self):
        if self.filtered(lambda d: d.state in LOCKED_STATES):
            raise UserError(_('Подану до ДПС декларацію видалити не можна.'))

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
        self._check_f0103309_group()
        if self.esv_annex:
            raise UserError(_(
                'Додаток 1 (ЄСВ) Odoo ще не формує. Подайте декларацію з додатком в '
                'Електронному кабінеті — після синхронізації вона з\'явиться тут, — або '
                'зніміть галочку «Додаток 1 (ЄСВ)», якщо ЄСВ цього разу не подається.'))
        if self.state == 'draft':
            raise UserError(
                'Спершу розрахуйте декларацію (кнопка «Розрахувати»), '
                'потім формуйте XML.'
            )
        if self.fop_group_id.code in FIXED_TAX_GROUPS:
            return self._generate_f0103407_xml()

        period_type, period_month, quarter_marker = PERIOD_F0103309.get(
            self.period, ('5', '12', 'H4KV'))
        # Декларація наростаюча: R013/R024 — нараховане в попередньому періоді року,
        # до сплати — лише різниця. Без цього півріччя вимагало б увесь податок знову.
        previous = self._previous_declaration()
        tax_prev = previous.single_tax if previous else 0.0
        military_prev = previous.military_levy if previous else 0.0

        company = self.company_id
        tax_office = company.l10n_ua_tax_office_id
        activities = [
            (link.kved_id.code, link.kved_id.name)
            for link in company.l10n_ua_kved_ids
        ]

        vals = {
            'taxpayer_tin': company.vat or company.company_registry or '',
            'taxpayer_name': company._l10n_ua_dps_name(),
            'taxpayer_address': self.env['l10n_ua.tax.document.wizard']
                ._format_company_address(company),
            'taxpayer_email': company.email or '',
            'taxpayer_phone': company.phone or '',
            'declaration_type': '0',  # Звітна
            'tax_office_code': tax_office.code if tax_office else '',
            # Назва ДПІ — українською, хоч би якою мовою працює користувач.
            'tax_office_name': tax_office.with_context(lang='uk_UA').name if tax_office else '',
            'quarter_marker': quarter_marker,
            'period_type': period_type,
            'period_month': period_month,
            'year': self.year,
            'employee_count': 0,
            'activities': activities,
            'income_total': self.total_income,
            'tax_amount': self.single_tax,
            'tax_paid_prev': tax_prev,
            'tax_to_pay': max(self.single_tax - tax_prev, 0.0),
            'military_amount': self.military_levy,
            'military_paid_prev': military_prev,
            'military_to_pay': max(self.military_levy - military_prev, 0.0),
        }

        xml = self.env['l10n_ua.tax.document.wizard']._render_F0103309_xml(vals)
        self.xml_filename = (
            f"{vals['taxpayer_tin']}_{self.year}_{period_month}_F0103309.xml"
        )
        self.xml_file = base64.b64encode(xml.encode('windows-1251'))
        return True

    def _taxpayer_vals(self):
        """Реквізити платника й ДПІ — спільні для F0103309 і F0103407."""
        company = self.company_id
        tax_office = company.l10n_ua_tax_office_id
        if tax_office and 'uk_UA' in dict(self.env['res.lang'].get_installed()):
            tax_office = tax_office.with_context(lang='uk_UA')
        return {
            'taxpayer_tin': company.vat or company.company_registry or '',
            'taxpayer_name': company._l10n_ua_dps_name(),
            'taxpayer_address': self.env['l10n_ua.tax.document.wizard']
                ._format_company_address(company),
            'taxpayer_email': company.email or '',
            'taxpayer_phone': company.phone or '',
            'declaration_type': '0',  # Звітна
            'tax_office_code': tax_office.code if tax_office else '',
            'tax_office_name': tax_office.name if tax_office else '',
            'year': self.year,
            'employee_count': 0,
            'activities': [(link.kved_id.code, link.kved_id.name)
                           for link in company.l10n_ua_kved_ids],
        }

    def _generate_f0103407_xml(self):
        """Річна декларація 1–2 груп: щоквартальні авансові внески ЄП, дохід за рік,
        військовий збір за кожен місяць."""
        vals = dict(
            self._taxpayer_vals(),
            group=self.fop_group_id.code,
            quarterly_tax=[self.monthly_tax_amount * 3] * 4,
            income_total=self.total_income,
            military_months=(range(1, 13) if self.military_levy else []),
            military_amount=self.military_levy,
        )
        xml = self.env['l10n_ua.tax.document.wizard']._render_F0103407_xml(vals)
        self.xml_filename = f"{vals['taxpayer_tin']}_{self.year}_12_F0103407.xml"
        self.xml_file = base64.b64encode(xml.encode('windows-1251'))
        return True

    def _previous_declaration(self):
        """Подана декларація того ж року й групи за попередній (коротший) період."""
        self.ensure_one()
        months = PERIOD_MONTHS.get(self.period, 0)
        earlier = [p for p, m in PERIOD_MONTHS.items() if m < months]
        if not earlier:
            return self.browse()
        candidates = self.search([
            ('company_id', '=', self.company_id.id),
            ('fop_group_id', '=', self.fop_group_id.id),
            ('year', '=', self.year),
            ('period', 'in', earlier),
            ('state', 'in', ('submitted', 'accepted')),
            ('id', '!=', self.id),
        ])
        return candidates.sorted(lambda d: PERIOD_MONTHS[d.period])[-1:]

    # --- імпорт поданої декларації (XML з Електронного кабінету) ---

    @api.model
    def _parse_f0103309(self, xml_bytes):
        """Головне з XML F0103309: період, вид, суми розділу 3 групи (G3)."""
        root = etree.fromstring(xml_bytes)
        head = root.find('DECLARHEAD')
        body = root.find('DECLARBODY')
        if head is None or body is None:
            return None

        def text(node, tag):
            el = node.find(tag)
            return (el.text or '').strip() if el is not None and el.text else ''

        def amount(tag):
            value = text(body, tag)
            return float(value) if value else 0.0

        annual = (text(head, 'C_DOC') + text(head, 'C_DOC_SUB')) == 'F01034'
        period = F0103309_PERIOD_TYPES.get(text(head, 'PERIOD_TYPE'))
        if not period:
            period = next((p for tag, p in F0103309_BODY_MARKERS.items()
                           if text(body, tag) == '1'), None)
        filled = text(head, 'D_FILL') or text(body, 'HFILL')
        try:
            filled = datetime.strptime(filled, '%d%m%Y').date() if filled else None
        except ValueError:
            filled = None
        if annual:
            # F0103407: розділ II (R02, R001) — перша група, III (R03, R003) — друга.
            first = any(text(body, tag) for tag in ('R001G3', 'R02G1', 'R02G2', 'R02G3', 'R02G4'))
            prefix = 'R02' if first else 'R03'
            return {
                'year': int(text(head, 'PERIOD_YEAR') or text(body, 'HZY') or 0),
                'period': 'year',
                'correction': text(body, 'HZU') == '1',
                'group_code': '1' if first else '2',
                'income': amount('R008G3') or amount('R001G3' if first else 'R003G3'),
                'taxable_income': 0.0,
                'single_tax': sum(amount('%sG%d' % (prefix, q)) for q in range(1, 5)),
                'monthly_tax': amount('%sG1' % prefix) / 3,
                'military_levy': amount('R022G3'),
                'filled': filled,
                'esv_annex': text(body, 'HD1') == '1' or bool(head.findall('LINKED_DOCS/DOC')),
            }
        return {
            'year': int(text(head, 'PERIOD_YEAR') or text(body, 'HZY') or 0),
            'period': period,
            # HZ — звітна, HZN — нова звітна, HZU — уточнююча.
            'correction': text(body, 'HZU') == '1',
            'income': amount('R006G3'),
            'taxable_income': amount('R008G3'),
            'single_tax': amount('R011G3'),
            'military_levy': amount('R023G3'),
            'filled': filled,
            # Додаток 1 (ЄСВ): ознака HD1 у тілі або пов'язаний документ у заголовку.
            'esv_annex': text(body, 'HD1') == '1' or bool(head.findall('LINKED_DOCS/DOC')),
        }

    @api.model
    def _group_for_rate(self, taxable_income, single_tax):
        """3 група: 5 % без ПДВ, 3 % — платник ПДВ; ставку видно з сум декларації."""
        Group = self.env['l10n_ua.fop.group']
        groups = Group.search([('code', 'in', ('3', '3_vat'))])
        if taxable_income and single_tax and groups:
            rate = single_tax / taxable_income * 100
            return min(groups, key=lambda g: abs(g.tax_rate - rate))
        return groups.filtered(lambda g: g.code == '3')[:1] or groups[:1]

    @api.model
    def _import_from_tax_document(self, doc):
        """Подана в кабінеті декларація ЄП → запис «Декларації ЄП» (стан «Прийнято»).

        Наявну декларацію за той самий період і групу не дублюємо: лише
        прив'язуємо до поданого документа й фіксуємо стан «Прийнято».
        """
        data = self._parse_f0103309(base64.b64decode(doc.file_xml))
        if not data or not data['year'] or not data['period']:
            _logger.warning("F0103309 %s: не вдалося визначити період", doc.display_name)
            return self.browse()
        if data['correction']:
            # Уточнююча змінює вже подану; суми звітної не перезаписуємо.
            return self.browse()
        if data.get('group_code'):
            group = self.env['l10n_ua.fop.group'].search(
                [('code', '=', data['group_code'])], limit=1)
        else:
            group = self._group_for_rate(data['taxable_income'], data['single_tax'])
        if not group:
            return self.browse()
        company = doc.company_id or self.env.company
        reg = doc.document_number and _(' № %s') % doc.document_number or ''
        declaration = self.search([
            ('year', '=', data['year']),
            ('period', '=', data['period']),
            ('fop_group_id', '=', group.id),
            ('company_id', '=', company.id),
        ], limit=1)
        accepted = {
            'state': 'accepted',
            'submission_date': data['filled'] or doc.document_date,
            'tax_document_id': doc.id,
            'esv_annex': data['esv_annex'],
        }
        if declaration:
            vals = dict(accepted)
            if declaration.state in ('draft', 'calculated'):
                # Подане — первинне: суми беремо з декларації, прийнятої ДПС.
                vals['total_income'] = data['income']
                if data.get('monthly_tax'):
                    vals['monthly_tax_amount'] = data['monthly_tax']
            if not declaration.xml_file:
                vals.update(xml_file=doc.file_xml, xml_filename=doc.file_xml_name)
            declaration.with_context(**{UNLOCK_CTX: True}).write(vals)
            declaration.message_post(body=_(
                'Пов\'язано з декларацією, поданою в Електронному кабінеті%s.') % reg)
        else:
            declaration = self.create({
                'year': data['year'],
                'period': data['period'],
                'fop_group_id': group.id,
                'company_id': company.id,
                'total_income': data['income'],
                'monthly_tax_amount': data.get('monthly_tax') or 0.0,
                'xml_file': doc.file_xml,
                'xml_filename': doc.file_xml_name,
                **accepted,
            })
            declaration.message_post(body=_(
                'Імпортовано з Електронного кабінету: декларацію подано й '
                'зареєстровано в ДПС%s.') % reg)
        # Розрахунок Odoo має збігтися з поданим; розбіжність — привід перевірити.
        if abs(declaration.single_tax - data['single_tax']) > 0.01 or \
                abs(declaration.military_levy - data['military_levy']) > 0.01:
            declaration.message_post(body=_(
                'Увага: у поданій декларації єдиний податок %(tax).2f і військовий '
                'збір %(mil).2f, а за розрахунком Odoo — %(otax).2f і %(omil).2f.',
                tax=data['single_tax'], mil=data['military_levy'],
                otax=declaration.single_tax, omil=declaration.military_levy))
        return declaration
