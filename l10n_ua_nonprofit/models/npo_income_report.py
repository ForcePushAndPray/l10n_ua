"""Report on the use of income (profits) of a non-profit organization (#374).

Форма — наказ Мінфіну від 17.06.2016 № 553 (зареєстровано в Мін'юсті
07.07.2016 за № 932/29062) у редакції наказу Мінфіну від 28.04.2017 № 469
(z0653-17). Електронна форма ДПС — J0101911 (додатки ГД — J0119711,
ВП — J0119811), за Реєстром форм звітності ДПС.

Доходи й видатки формуються за правилами бухобліку в момент їх виникнення:
дохід — за НП(С)БО 15 «Дохід», видатки — за НП(С)БО 16 «Витрати». Тому
частина І заповнюється з оборотів рахунків доходів (клас 7, крім 79) і
витрат (рахунки програм, клас 8/9) за період — без проводок закриття
періоду. Цільові надходження на 48 до визнання доходом у звіт не потрапляють.

Розподіл за рядками:

* обороти з аналітикою цільової програми — в рядок, указаний у програмі
  (дохід: 1.4–1.11; видатки: 2.3/2.4.x/2.6);
* дохід без програми: 72x/73x — 1.9 «пасивні доходи», 718/745 — 1.6
  «безповоротна фінансова допомога, добровільні пожертвування», решта —
  1.11 «інші доходи»;
* видатки без програми — 2.3 «утримання організації, статутна діяльність».

Частина ІІ (нецільове використання, розподіл доходів) та виправлення
помилок (рядки 7–10) заповнюються вручну.
"""

from calendar import monthrange
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .npo_program import EXPENSE_ROWS, INCOME_ROWS, RESULT_PREFIX, analytic_share

MONTHS = [(str(m), str(m)) for m in range(1, 13)]

# row code → field name
ROW_FIELDS = {
    '1.1': 'r1_1', '1.2': 'r1_2', '1.3': 'r1_3', '1.4': 'r1_4', '1.5': 'r1_5',
    '1.6': 'r1_6_own', '1.6.1': 'r1_6_1', '1.6.2': 'r1_6_2', '1.6.3': 'r1_6_3',
    '1.7': 'r1_7', '1.8': 'r1_8', '1.9': 'r1_9', '1.10': 'r1_10', '1.11': 'r1_11',
    '2.1': 'r2_1', '2.2': 'r2_2', '2.3': 'r2_3',
    '2.4': 'r2_4_own', '2.4.1': 'r2_4_1', '2.4.2': 'r2_4_2', '2.4.3': 'r2_4_3',
    '2.5': 'r2_5', '2.6': 'r2_6',
}
ROWS = INCOME_ROWS + EXPENSE_ROWS
ROW_ORDER = {code: index for index, (code, _label) in enumerate(ROWS)}

# Рядки 1.6.3 і 2.4.3 форми мають однаковий текст.
ROW_DEFENCE_TEXT = (
    'суми коштів або вартості спеціальних засобів індивідуального захисту '
    '(касок, бронежилетів, виготовлених відповідно до військових стандартів), '
    'технічних засобів спостереження, лікарських засобів та медичних виробів, '
    'засобів особистої гігієни, продуктів харчування, предметів речового '
    'забезпечення, а також інших товарів, виконаних робіт, наданих послуг за '
    'переліком, що визначається Кабінетом Міністрів України, які добровільно '
    'перераховані (передані) Збройним Силам України, Національній гвардії '
    'України, Службі безпеки України, Службі зовнішньої розвідки України, '
    'Державній прикордонній службі України, Міністерству внутрішніх справ '
    'України, Управлінню державної охорони України, Державній службі '
    'спеціального зв’язку та захисту інформації України, іншим утвореним '
    'відповідно до законів України військовим формуванням, їх з’єднанням, '
    'військовим частинам, підрозділам, установам або організаціям, що '
    'утримуються за рахунок коштів державного бюджету, для потреб забезпечення '
    'проведення антитерористичної операції'
)

# Базова ставка податку на прибуток — п. 136.1 ПКУ.
PROFIT_TAX_RATE = 18.0


# Тексти рядків друкуються з форми (наказ Мінфіну № 553 у ред. № 469)
# дослівно (рядки 7–9 — скорочено, без посилань на додаток ВП) і не
# перекладаються: це регламентована форма.
PRINT_ROWS_PART1 = [
    ('Доходи неприбуткової організації (сума рядків 1.1 – 1.11)', '1', 'r1', 0),
    ('фактично одержане фінансування бюджетної установи (організації) за '
     'загальним фондом', '1.1', 'r1_1', 1),
    ('залишки коштів бюджетної установи (організації) на спеціальних '
     'рахунках, що перейшли з попереднього року', '1.2', 'r1_2', 1),
    ('доходи, одержані бюджетною установою (організацією), що зараховані на '
     'рахунки спеціального фонду цієї установи (організації) згідно із '
     'затвердженим у встановленому порядку кошторисом', '1.3', 'r1_3', 1),
    ('дотації (субсидії), фінансування, отримані з державного або місцевого '
     'бюджетів, державних цільових фондів або у межах технічної допомоги',
     '1.4', 'r1_4', 1),
    ('вартість активів (коштів або майна), вартість товарів (робіт, послуг), '
     'отриманих для реалізації мети (цілей, завдань) та напрямів діяльності, '
     'визначених установчими документами, та/або для здійснення '
     'неприбуткової (добродійної) діяльності, передбаченої законом для '
     'релігійних організацій', '1.5', 'r1_5', 1),
    ('надходження у вигляді безповоротної фінансової допомоги, добровільних '
     'пожертвувань, милосердя тощо, у тому числі:', '1.6', 'r1_6', 1),
    ('благодійна допомога', '1.6.1', 'r1_6_1', 2),
    ('гуманітарна допомога', '1.6.2 ГД', 'r1_6_2', 2),
    (ROW_DEFENCE_TEXT, '1.6.3', 'r1_6_3', 2),
    ('разові, періодичні, цільові внески та відрахування засновників і членів',
     '1.7', 'r1_7', 1),
    ('сума коштів, які надходять до пенсійних фондів у вигляді внесків на '
     'недержавне пенсійне забезпечення', '1.8', 'r1_8', 1),
    ('пасивні доходи', '1.9', 'r1_9', 1),
    ('вартість активів, отриманих у разі припинення юридичної особи (у '
     'результаті її ліквідації, злиття, поділу, приєднання або '
     'перетворення)', '1.10', 'r1_10', 1),
    ('інші доходи', '1.11', 'r1_11', 1),
    ('Видатки (витрати) неприбуткової організації (сума рядків 2.1 – 2.6)',
     '2', 'r2', 0),
    ('сума видатків (витрат) бюджетної установи (організації) за загальним '
     'фондом відповідно до затверджених в установленому порядку кошторисів',
     '2.1', 'r2_1', 1),
    ('сума видатків (витрат) бюджетної установи (організації) за '
     'спеціальним фондом відповідно до затверджених в установленому порядку '
     'кошторисів', '2.2', 'r2_2', 1),
    ('вартість активів (коштів або майна), вартість товарів (робіт, послуг), '
     'використаних (переданих) для фінансування видатків на утримання '
     'неприбуткової організації, реалізації мети (цілей, завдань) та '
     'напрямів діяльності, визначених її установчими документами, та/або '
     'для здійснення неприбуткової (добродійної) діяльності, передбаченої '
     'законом для релігійних організацій', '2.3', 'r2_3', 1),
    ('безповоротна фінансова допомога, добровільні пожертвування, милосердя '
     'тощо, у тому числі:', '2.4', 'r2_4', 1),
    ('благодійна допомога', '2.4.1', 'r2_4_1', 2),
    ('гуманітарна допомога', '2.4.2 ГД', 'r2_4_2', 2),
    (ROW_DEFENCE_TEXT, '2.4.3', 'r2_4_3', 2),
    ('вартість активів, переданих іншим неприбутковим організаціям або '
     'зарахованих до бюджету в результаті ліквідації (злиття, поділу, '
     'приєднання або перетворення)', '2.5', 'r2_5', 1),
    ('інші видатки (витрати)', '2.6', 'r2_6', 1),
]


def _default_income_row(code):
    if code.startswith(('72', '73')):
        return '1.9'
    if code.startswith(('718', '745')):
        return '1.6'
    return '1.11'


class L10nUaNpoIncomeReport(models.Model):
    _name = 'l10n_ua.npo.income.report'
    _description = 'Report on the Use of Income of a Non-profit Organization'
    _inherit = ['mail.thread']
    _order = 'date_to desc, id desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done')],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.context_today(self).year - 1,
    )
    period_type = fields.Selection(
        [('year', 'Year'), ('month', 'Month (breach of para. 133.4)')],
        string='Period',
        required=True,
        default='year',
        help='The report is filed for the year. A monthly report is filed '
             'only when the requirements of para. 133.4 of the Tax Code were '
             'breached; it covers the period from the start of the year to '
             'the end of that month.',
    )
    month = fields.Selection(MONTHS, string='Month')
    date_from = fields.Date(string='From', compute='_compute_dates', store=True)
    date_to = fields.Date(string='To', compute='_compute_dates', store=True)
    report_kind = fields.Selection(
        [('normal', 'Reporting'), ('new', 'New Reporting'),
         ('clarifying', 'Clarifying')],
        string='Report Type',
        required=True,
        default='normal',
    )
    clarified_year = fields.Integer(string='Clarified Year')
    clarified_month = fields.Selection(MONTHS, string='Clarified Month')

    # --- header (fields 4-9 of the form) ---
    company_edrpou = fields.Char(string='EDRPOU', compute='_compute_header')
    nonprofit_code = fields.Selection(
        related='company_id.l10n_ua_nonprofit_code', string='Non-profit Attribute')
    register_date = fields.Date(
        related='company_id.l10n_ua_nonprofit_register_date', string='Register Decision Date')
    register_number = fields.Char(
        related='company_id.l10n_ua_nonprofit_register_number', string='Register Decision No.')
    tax_office_id = fields.Many2one(
        related='company_id.l10n_ua_tax_office_id', string='Tax Office')
    submission_date = fields.Date(string='Submission Date')
    director_name = fields.Char(
        string='Head',
        default=lambda self: self.env.company.partner_id.l10n_ua_chief_name)
    accountant_name = fields.Char(
        string='Chief Accountant',
        default=lambda self: self.env.company.partner_id.l10n_ua_accountant_name)

    # --- Part I: income ---
    r1 = fields.Monetary(string='1 Income (1.1-1.11)', compute='_compute_totals', store=True)
    r1_1 = fields.Monetary(string='1.1')
    r1_2 = fields.Monetary(string='1.2')
    r1_3 = fields.Monetary(string='1.3')
    r1_4 = fields.Monetary(string='1.4')
    r1_5 = fields.Monetary(string='1.5')
    r1_6_own = fields.Monetary(
        string='1.6 (not in 1.6.1-1.6.3)',
        help='Gratuitous aid and donations not shown in rows 1.6.1-1.6.3.')
    r1_6 = fields.Monetary(string='1.6', compute='_compute_totals', store=True)
    r1_6_1 = fields.Monetary(string='1.6.1')
    r1_6_2 = fields.Monetary(string='1.6.2 HD')
    r1_6_3 = fields.Monetary(string='1.6.3')
    r1_7 = fields.Monetary(string='1.7')
    r1_8 = fields.Monetary(string='1.8')
    r1_9 = fields.Monetary(string='1.9')
    r1_10 = fields.Monetary(string='1.10')
    r1_11 = fields.Monetary(string='1.11')
    # --- Part I: expenses ---
    r2 = fields.Monetary(string='2 Expenses (2.1-2.6)', compute='_compute_totals', store=True)
    r2_1 = fields.Monetary(string='2.1')
    r2_2 = fields.Monetary(string='2.2')
    r2_3 = fields.Monetary(string='2.3')
    r2_4_own = fields.Monetary(
        string='2.4 (not in 2.4.1-2.4.3)',
        help='Aid and donations given that are not shown in rows 2.4.1-2.4.3.')
    r2_4 = fields.Monetary(string='2.4', compute='_compute_totals', store=True)
    r2_4_1 = fields.Monetary(string='2.4.1')
    r2_4_2 = fields.Monetary(string='2.4.2 HD')
    r2_4_3 = fields.Monetary(string='2.4.3')
    r2_5 = fields.Monetary(string='2.5')
    r2_6 = fields.Monetary(string='2.6')
    # --- Part II ---
    r3 = fields.Monetary(string='3 Non-target use of assets', compute='_compute_totals', store=True)
    r3_1 = fields.Monetary(string='3.1 HD')
    r3_2 = fields.Monetary(string='3.2')
    r4 = fields.Monetary(
        string='4 Income distributed',
        help='Income (profit) or its part distributed among founders, members, '
             'employees (except salary and SSC), management and related persons.')
    r5 = fields.Monetary(string='5 Tax object (3 + 4)', compute='_compute_totals', store=True)
    profit_tax_rate = fields.Float(
        string='Profit Tax Rate (%)', default=PROFIT_TAX_RATE,
        help='Base profit tax rate, para. 136.1 of the Tax Code.')
    r6 = fields.Monetary(string='6 Profit tax liability', compute='_compute_totals', store=True)
    r7 = fields.Monetary(string='7 Correction of the liability (+/-)')
    r8 = fields.Monetary(string='8 Fine 5%')
    r9 = fields.Monetary(string='9 Penalty')
    r10 = fields.Monetary(
        string='10 Fine 3%', compute='_compute_r10', store=True, readonly=False)

    # --- attachments ---
    has_annex_hd = fields.Boolean(
        string='Annex HD',
        help='Information on operations with humanitarian aid.')
    has_annex_vp = fields.Boolean(
        string='Annex VP',
        help='Calculation of tax liabilities for the period in which errors '
             'were found.')
    has_annex_fs = fields.Boolean(string='Financial Statements Attached', default=True)
    fs_kind = fields.Selection(
        [('full', 'Full (Balance, P&L, Cash Flow, Equity, Notes)'),
         ('small', 'Financial statement of a small enterprise'),
         ('simplified', 'Simplified financial statement of a small enterprise'),
         ('budget', 'Budget institution (Balance, Report on financial results)')],
        string='Financial Statements',
        default='small',
        help='Financial statements are an integral annex of the report '
             '(para. 46.2 of the Tax Code).',
    )

    line_ids = fields.One2many(
        'l10n_ua.npo.income.report.line',
        'report_id',
        string='Breakdown',
    )

    @api.depends('year', 'period_type', 'month')
    def _compute_name(self):
        for rec in self:
            if rec.period_type == 'month' and rec.month:
                rec.name = _('Non-profit income report %(month)s.%(year)s',
                             month=rec.month.zfill(2), year=rec.year)
            else:
                rec.name = _('Non-profit income report %s', rec.year)

    @api.depends('year', 'period_type', 'month')
    def _compute_dates(self):
        for rec in self:
            if not rec.year or rec.year < 1990:
                rec.date_from = rec.date_to = False
                continue
            rec.date_from = date(rec.year, 1, 1)
            month = int(rec.month) if rec.period_type == 'month' and rec.month else 12
            rec.date_to = date(rec.year, month, monthrange(rec.year, month)[1])

    @api.depends('company_id')
    def _compute_header(self):
        for rec in self:
            company = rec.company_id
            rec.company_edrpou = company.edrpou or company.company_registry \
                or company.partner_id.edrpou or ''

    @api.depends(*ROW_FIELDS.values(), 'r3_1', 'r3_2', 'r4', 'profit_tax_rate')
    def _compute_totals(self):
        for rec in self:
            rec.r1_6 = rec.r1_6_own + rec.r1_6_1 + rec.r1_6_2 + rec.r1_6_3
            rec.r1 = (rec.r1_1 + rec.r1_2 + rec.r1_3 + rec.r1_4 + rec.r1_5
                      + rec.r1_6 + rec.r1_7 + rec.r1_8 + rec.r1_9 + rec.r1_10
                      + rec.r1_11)
            rec.r2_4 = rec.r2_4_own + rec.r2_4_1 + rec.r2_4_2 + rec.r2_4_3
            rec.r2 = (rec.r2_1 + rec.r2_2 + rec.r2_3 + rec.r2_4 + rec.r2_5
                      + rec.r2_6)
            rec.r3 = rec.r3_1 + rec.r3_2
            rec.r5 = rec.r3 + rec.r4
            rec.r6 = rec.currency_id.round(rec.r5 * rec.profit_tax_rate / 100.0)

    @api.depends('r7', 'report_kind')
    def _compute_r10(self):
        for rec in self:
            rec.r10 = rec.currency_id.round(rec.r7 * 0.03) \
                if rec.report_kind == 'clarifying' and rec.r7 > 0 else 0.0

    @api.constrains('period_type', 'month')
    def _check_month(self):
        for rec in self:
            if rec.period_type == 'month' and not rec.month:
                raise ValidationError(_('Choose the month of the monthly report.'))

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------
    def _get_breakdown(self):
        """Turnover of income and expense accounts for the period by row.

        :returns: dict ``{(row, program_id, account_id): amount}``
        """
        self.ensure_one()
        company = self.company_id
        Program = self.env['l10n_ua.npo.program']
        programs = Program.with_context(active_test=False).search([
            ('company_id', '=', company.id),
            ('analytic_account_id', '!=', False),
        ])
        by_analytic = {str(p.analytic_account_id.id): p for p in programs}
        expense_prefixes = company._l10n_ua_npo_expense_prefixes()
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id', 'not in', Program._get_closing_moves(company).ids),
        ])
        breakdown = {}

        def add(row, program, account, amount):
            key = (row, program.id or False, account.id)
            breakdown[key] = breakdown.get(key, 0.0) + amount

        for line in lines:
            code = line.account_id.with_company(company).code or ''
            if code.startswith(RESULT_PREFIX):
                continue
            if code.startswith('7'):
                amount = line.credit - line.debit
                is_income = True
            elif expense_prefixes and code.startswith(expense_prefixes):
                amount = line.debit - line.credit
                is_income = False
            else:
                continue
            assigned = 0.0
            analytic_ids = {
                analytic_id
                for key in (line.analytic_distribution or {})
                for analytic_id in str(key).split(',')
            }
            for analytic_id in analytic_ids:
                program = by_analytic.get(analytic_id)
                if not program:
                    continue
                share = analytic_share(line, analytic_id)
                assigned += share
                row = program.income_row if is_income else program.expense_row
                add(row, program, line.account_id, amount * share)
            rest = 1.0 - assigned
            if rest > 0.000001:
                row = _default_income_row(code) if is_income else '2.3'
                add(row, Program, line.account_id, amount * rest)
        return breakdown

    def action_compute(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only a draft report can be recomputed.'))
            breakdown = rec._get_breakdown()
            vals = dict.fromkeys(ROW_FIELDS.values(), 0.0)
            line_cmds = [(5, 0, 0)]
            for (row, program_id, account_id), amount in sorted(
                    breakdown.items(),
                    key=lambda kv: (ROW_ORDER[kv[0][0]], kv[0][1] or 0, kv[0][2])):
                amount = rec.currency_id.round(amount)
                if rec.currency_id.is_zero(amount):
                    continue
                vals[ROW_FIELDS[row]] += amount
                line_cmds.append((0, 0, {
                    'sequence': ROW_ORDER[row],
                    'row': row,
                    'program_id': program_id,
                    'account_id': account_id,
                    'amount': amount,
                }))
            vals['line_ids'] = line_cmds
            vals['has_annex_hd'] = bool(vals['r1_6_2'] or vals['r2_4_2'])
            rec.write(vals)
        return True

    def action_done(self):
        self.write({'state': 'done'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        return self.env.ref(
            'l10n_ua_nonprofit.action_report_npo_income').report_action(self)

    # ------------------------------------------------------------------
    # Printing helpers
    # ------------------------------------------------------------------
    @api.model
    def _format_amount(self, value):
        """Amount as printed in the form: 1 234 567.89, empty for zero."""
        if not value:
            return ''
        return '{:,.2f}'.format(value).replace(',', '\u00a0')

    def _get_print_rows(self):
        """Rows of Part I of the printed form: (label, code, field, level)."""
        return PRINT_ROWS_PART1

    def _get_print_rows_part2(self):
        """Rows of Part II and corrections: (label, code, field, level)."""
        self.ensure_one()
        rate = ('%g' % self.profit_tax_rate) if self.profit_tax_rate else '___'
        return [
            ('Сума операції (операцій) нецільового використання активів, у тому '
             'числі:', '3', 'r3', 0),
            ('гуманітарна допомога', '3.1 ГД', 'r3_1', 1),
            ('вартість активів (коштів або майна), вартість товарів (робіт, '
             'послуг), які використані на цілі інші, ніж фінансування видатків на '
             'утримання неприбуткової організації, реалізації мети (цілей, '
             'завдань) та напрямів діяльності, визначених установчими '
             'документами, та/або для здійснення неприбуткової (добродійної) '
             'діяльності, передбаченої законом для релігійних організацій',
             '3.2', 'r3_2', 1),
            ('Доходи (прибутки) або їх частини, що розподілені серед засновників '
             '(учасників), членів неприбуткової організації, працівників (крім '
             'оплати їхньої праці, нарахування єдиного соціального внеску), членів '
             'органів управління та інших пов’язаних з ними осіб', '4', 'r4', 0),
            ('Об’єкт оподаткування (рядок 3 + рядок 4)', '5', 'r5', 0),
            ('Податкове зобов’язання з податку на прибуток підприємств '
             '(рядок 5 х %s/100)' % rate, '6', 'r6', 0),
            ('Збільшення (зменшення) податкового зобов’язання звітного '
             '(податкового) періоду, що уточнюється (+, -)', '7', 'r7', 0),
            ('Сума штрафу (5 %) при відображенні недоплати у складі Звіту, який '
             'подається за звітний (податковий) період, що настає за періодом, у '
             'якому виявлено факт заниження податкового зобов’язання', '8', 'r8', 0),
            ('Пеня, нарахована на виконання вимог підпункту 129.1.3 пункту 129.1 '
             'статті 129 глави 12 розділу ІІ Податкового кодексу України', '9', 'r9', 0),
            ('Сума штрафу (3 %) при відображенні недоплати в уточнюючому Звіті '
             '(рядок 7 х 3 %)', '10', 'r10', 0),
        ]


class L10nUaNpoIncomeReportLine(models.Model):
    _name = 'l10n_ua.npo.income.report.line'
    _description = 'Non-profit Income Report Breakdown'
    _order = 'report_id, sequence, id'

    report_id = fields.Many2one(
        'l10n_ua.npo.income.report',
        string='Report',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(related='report_id.company_id', store=True)
    currency_id = fields.Many2one(related='report_id.currency_id')
    sequence = fields.Integer(string='Sequence')
    row = fields.Selection(ROWS, string='Row', required=True)
    program_id = fields.Many2one('l10n_ua.npo.program', string='Program')
    account_id = fields.Many2one('account.account', string='Account')
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
