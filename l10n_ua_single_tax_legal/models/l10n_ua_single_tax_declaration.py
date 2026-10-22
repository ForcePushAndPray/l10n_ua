"""Декларація платника єдиного податку третьої групи (юридичної особи), J0103509.

Форма — наказ Мінфіну від 19.06.2015 № 578 у редакції наказу від 31.01.2025 № 57;
структура — XSD з пакета СКЗ ДПС (``tests/schemas``). Період — квартал наростаючим
підсумком з початку року; суми з копійками (DGdecimal2).

Графа 3 — ставка 3 % (платник ПДВ), графа 4 — 5 %. Розділ V (військовий збір, 1 %
доходу з 2025 року) — ті самі графи: 3 — платник ПДВ, 4 — неплатник.

Дохід — касовим методом (п. 292.6 ПКУ): надходження від покупців на банківські й
касові рахунки за період, за вирахуванням повернень. У платника ПДВ (ставка 3 %) до
доходу не входить ПДВ (п. 292.3): його частку беремо з оплачених рахунків, а для
авансів — зі ставки податку на продаж компанії. Інші доходи (позареалізаційні) —
окремим полем вручну.

Не формуються: уточнююча декларація (розділи IV і рядки 22–25), додаток з
мінімального податкового зобов'язання (HD1, рядок 11 — лише для власників і
користувачів сільськогосподарських земель).
"""
import base64
import re
from calendar import monthrange
from datetime import date
from xml.sax.saxutils import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_round

from odoo.addons.l10n_ua_tax_cabinet.models.l10n_ua_dps_submit_mixin import dps_standard_filename

SOFTWARE = 'Odoo l10n_ua'
FORM = ('J01', '035', '9')

# Звітний період → (PERIOD_TYPE, PERIOD_MONTH, маркер періоду в тілі).
PERIODS = {
    'q1': ('2', 3, 'H1KV'),
    'h1': ('3', 6, 'HHY'),
    '9m': ('4', 9, 'H3KV'),
    'year': ('5', 12, 'HY'),
}

# Граничний обсяг доходу третьої групи — 1167 мінімальних зарплат на 1 січня
# (пп. 3 п. 291.4 ПКУ).
INCOME_LIMIT_MIN_WAGES = 1167
# Військовий збір платників ЄП третьої групи — з 01.01.2025, 1 % доходу
# (пп. 1.2 п. 16¹ підрозд. 10 розд. XX ПКУ).
MILITARY_FROM_YEAR = 2025
MILITARY_RATE = 1.0

# Рядки декларації в порядку XSD: (номер рядка, поле, чи писати нуль).
ROWS = [
    (1, 'line_1', True), (2, 'line_2', False), (3, 'line_3', False),
    (4, 'line_4', False), (5, 'line_5', True), (6, 'line_6', True),
    (7, 'line_7', False), (8, 'line_8', True), (9, 'line_9', False),
    (10, 'line_10', True), (12, 'line_12', True),
    (19, 'line_19', True), (20, 'line_20', False), (21, 'line_21', True),
]

LOCKED_STATES = ('submitted', 'accepted')
LOCKED_FIELDS = frozenset({
    'year', 'period', 'company_id', 'rate', 'income_accounting', 'income_vat',
    'income_other', 'line_3', 'line_4', 'line_9', 'line_20', 'xml_file',
    'xml_filename', 'submission_date', 'signatory_name', 'signatory_rnokpp',
    'accountant_name', 'accountant_rnokpp', 'dps_submission_id',
})
UNLOCK_CTX = 'l10n_ua_single_tax_declaration_unlock'


def _dec2(value):
    return '%.2f' % float_round(value or 0.0, precision_digits=2)


class L10nUaSingleTaxDeclaration(models.Model):
    _name = 'l10n_ua.single.tax.declaration'
    _description = 'Декларація платника єдиного податку третьої групи (юридичної особи)'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'l10n_ua.dps.submit.mixin']
    _order = 'year desc, period desc'

    name = fields.Char(string='Назва', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Компанія', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    year = fields.Integer(
        string='Рік', required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).year)
    period = fields.Selection(
        [('q1', 'I квартал'), ('h1', 'Півріччя'), ('9m', '9 місяців'), ('year', 'Рік')],
        string='Звітний період', required=True, tracking=True)
    rate = fields.Selection(
        [('3', '3 % (платник ПДВ)'), ('5', '5 % (неплатник ПДВ)')],
        string='Ставка ЄП', required=True, tracking=True,
        default=lambda self: self._default_rate(),
        help='Від ставки залежить графа декларації: 3 — ставка 3 %, 4 — ставка 5 %. '
             'Так само для військового збору: графа 3 — платник ПДВ, 4 — неплатник.')
    state = fields.Selection(
        [('draft', 'Чернетка'), ('calculated', 'Розраховано'),
         ('submitted', 'Подано'), ('accepted', 'Прийнято')],
        string='Статус', default='draft', tracking=True, copy=False)

    # --- дохід
    income_accounting = fields.Monetary(
        string='Надходження від покупців', copy=False,
        help='Оплати покупців на банківські й касові рахунки з початку року до кінця '
             'звітного періоду за вирахуванням повернень (касовий метод, п. 292.6 ПКУ). '
             'Заповнюється кнопкою «Розрахувати».')
    income_vat = fields.Monetary(
        string='ПДВ у надходженнях', copy=False,
        help='Для ставки 3 %: ПДВ, що не входить до доходу (п. 292.3 ПКУ) — з оплачених '
             'рахунків, для авансів — за ставкою податку на продаж компанії.')
    income_other = fields.Monetary(
        string='Інші доходи', copy=False,
        help='Доходи, що не пройшли як оплати покупців: позареалізаційні, безоплатно '
             'отримане, списана кредиторська заборгованість тощо (п. 292.1 ПКУ). '
             'Наростаючим підсумком з початку року.')
    income_total = fields.Monetary(
        string='Дохід з початку року', compute='_compute_lines', store=True)
    income_limit = fields.Monetary(
        string='Граничний обсяг доходу', compute='_compute_income_limit', store=True,
        help='1167 мінімальних заробітних плат на 1 січня року (пп. 3 п. 291.4 ПКУ).')

    # --- рядки декларації
    line_1 = fields.Monetary(string='1. Дохід за звітний період', compute='_compute_lines', store=True)
    line_2 = fields.Monetary(string='2. Дохід понад граничний обсяг', compute='_compute_lines', store=True)
    line_3 = fields.Monetary(
        string='3. Дохід, отриманий іншим способом розрахунків', copy=False,
        help='Дохід, отриманий при застосуванні способу розрахунків, не передбаченого '
             'п. 291.6 ПКУ (подвійна ставка).')
    line_4 = fields.Monetary(
        string='4. Дохід від діяльності, що не дає права на спрощену систему', copy=False)
    line_5 = fields.Monetary(string='5. Загальна сума доходу', compute='_compute_lines', store=True)
    line_6 = fields.Monetary(string='6. Сума єдиного податку', compute='_compute_lines', store=True)
    line_7 = fields.Monetary(string='7. Єдиний податок за подвійною ставкою', compute='_compute_lines', store=True)
    line_8 = fields.Monetary(string='8. Нараховано за звітний період', compute='_compute_lines', store=True)
    line_9 = fields.Monetary(
        string='9. Нараховано за минулий звітний період', copy=False,
        help='Рядок 8 поданої декларації за попередній період року — заповнюється '
             'кнопкою «Розрахувати».')
    line_10 = fields.Monetary(string='10. До сплати за звітний квартал', compute='_compute_lines', store=True)
    line_12 = fields.Monetary(string='12. Загальна сума до сплати', compute='_compute_lines', store=True)
    line_19 = fields.Monetary(string='19. Військовий збір за звітний період', compute='_compute_lines', store=True)
    line_20 = fields.Monetary(
        string='20. Військовий збір за минулий звітний період', copy=False)
    line_21 = fields.Monetary(string='21. Військовий збір до сплати', compute='_compute_lines', store=True)

    # --- подання
    signatory_name = fields.Char(
        string='Керівник', compute='_compute_signatory', store=True, readonly=False,
        help='Власне ім\'я ПРІЗВИЩЕ керівника (уповноваженої особи) для підпису декларації')
    signatory_rnokpp = fields.Char(
        string='РНОКПП керівника', compute='_compute_signatory', store=True, readonly=False)
    accountant_name = fields.Char(string='Головний бухгалтер')
    accountant_rnokpp = fields.Char(string='РНОКПП головного бухгалтера')
    xml_file = fields.Binary(string='XML файл', attachment=True, copy=False)
    xml_filename = fields.Char(string='Ім\'я файлу', copy=False)
    submission_date = fields.Date(string='Дата подання', copy=False)
    dps_submission_id = fields.Char(
        string='ID подання в ДПС', copy=False, readonly=True,
        help='Ідентифікатор, який кабінет ДПС повернув при поданні; на нього '
             'посилаються квитанції.')

    _unique_declaration = models.Constraint(
        'unique(company_id, year, period)',
        'Декларація за цей період уже існує!',
    )

    @api.model
    def _default_rate(self):
        company = self.env.company
        if 'l10n_ua_is_vat_payer' in company._fields and company.l10n_ua_is_vat_payer:
            return '3'
        return '3' if company.l10n_ua_tax_rate == 3.0 else '5'

    @api.depends('year', 'period')
    def _compute_name(self):
        labels = dict(self._fields['period'].selection)
        for rec in self:
            rec.name = _('Декларація ЄП %(period)s %(year)s',
                         period=labels.get(rec.period, ''), year=rec.year or '')

    @api.depends('company_id')
    def _compute_signatory(self):
        """Керівник — з картки компанії, якщо встановлено кадровий модуль (director_id)."""
        for rec in self:
            director = (rec.company_id.director_id
                        if 'director_id' in rec.company_id._fields else False)
            if director and not rec.signatory_name:
                rec.signatory_name = director.name
                rec.signatory_rnokpp = getattr(director, 'rnokpp', False) or False

    @api.depends('year')
    def _compute_income_limit(self):
        MinWage = self.env['l10n_ua.min.wage']
        for rec in self:
            wage = MinWage._get_amount(date(rec.year, 1, 1)) if rec.year else 0.0
            rec.income_limit = wage * INCOME_LIMIT_MIN_WAGES

    @api.depends('income_accounting', 'income_vat', 'income_other', 'income_limit',
                 'line_3', 'line_4', 'line_9', 'line_20', 'rate', 'year')
    def _compute_lines(self):
        for rec in self:
            rate = float(rec.rate or 0) / 100
            income = rec.income_accounting - rec.income_vat + rec.income_other
            rec.income_total = income
            # Дохід понад граничний обсяг оподатковується подвійною ставкою (рядок 2).
            excess = max(income - rec.income_limit, 0.0) if rec.income_limit else 0.0
            rec.line_1 = income - excess
            rec.line_2 = excess
            rec.line_5 = rec.line_1 + rec.line_2 + rec.line_3 + rec.line_4
            rec.line_6 = float_round(rec.line_1 * rate, precision_digits=2)
            rec.line_7 = float_round((rec.line_2 + rec.line_3 + rec.line_4) * rate * 2,
                                     precision_digits=2)
            rec.line_8 = rec.line_6 + rec.line_7
            rec.line_10 = rec.line_8 - rec.line_9
            rec.line_12 = rec.line_10
            military = rec.year and rec.year >= MILITARY_FROM_YEAR
            rec.line_19 = float_round(rec.line_5 * MILITARY_RATE / 100, precision_digits=2) \
                if military else 0.0
            rec.line_21 = rec.line_19 - rec.line_20

    # ------------------------------------------------------------------ розрахунок

    def _period_bounds(self):
        self.ensure_one()
        month = PERIODS[self.period][1]
        return date(self.year, 1, 1), date(self.year, month, monthrange(self.year, month)[1])

    def _vat_share(self, line):
        """Частка ПДВ в оплаті: з оплачених нею рахунків, інакше — ставка продажу."""
        invoices = (line.matched_debit_ids.debit_move_id.move_id
                    | line.matched_credit_ids.credit_move_id.move_id).filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.amount_total)
        if invoices:
            return sum(invoices.mapped('amount_tax')) / sum(invoices.mapped('amount_total'))
        tax = line.company_id.account_sale_tax_id
        if tax and tax.amount_type == 'percent' and tax.amount:
            return tax.amount / (100 + tax.amount)
        return 0.0

    def _income_from_accounting(self):
        """(надходження, ПДВ у них) — оплати покупців з початку року до кінця періоду."""
        self.ensure_one()
        date_from, date_to = self._period_bounds()
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('journal_id.type', 'in', ('bank', 'cash')),
        ])
        received = vat = 0.0
        for line in lines:
            amount = line.credit - line.debit
            received += amount
            if self.rate == '3':
                vat += amount * self._vat_share(line)
        return (float_round(received, precision_digits=2),
                float_round(vat, precision_digits=2))

    def _previous_declaration(self):
        """Подана декларація того ж року за попередній (коротший) період."""
        self.ensure_one()
        month = PERIODS[self.period][1]
        earlier = [p for p, spec in PERIODS.items() if spec[1] < month]
        if not earlier:
            return self.browse()
        return self.search([
            ('company_id', '=', self.company_id.id),
            ('year', '=', self.year),
            ('period', 'in', earlier),
            ('state', 'in', LOCKED_STATES),
            ('id', '!=', self.id),
        ]).sorted(lambda d: PERIODS[d.period][1])[-1:]

    def action_calculate(self):
        for rec in self:
            if rec.state not in ('draft', 'calculated'):
                raise UserError(_('Подану декларацію не перераховують.'))
            if rec.company_id.l10n_ua_is_fop:
                raise UserError(_(
                    'Компанія — ФОП: декларацію ЄП ФОП ведуть у «Деклараціях ЄП ФОП».'))
            self.env.add_to_compute(rec._fields['income_limit'], rec)
            if not rec.income_limit:
                raise UserError(_(
                    'У довіднику немає мінімальної заробітної плати на 1 січня %s року — '
                    'від неї рахується граничний обсяг доходу. Додайте її: Taxes UA → '
                    'Configuration → Мінімальна заробітна плата.') % rec.year)
            received, vat = rec._income_from_accounting()
            previous = rec._previous_declaration()
            rec.write({
                'income_accounting': received,
                'income_vat': vat,
                'line_9': previous.line_8 if previous else 0.0,
                'line_20': previous.line_19 if previous else 0.0,
                'state': 'calculated',
                'xml_file': False,
                'xml_filename': False,
            })
        return True

    def action_draft(self):
        if self.filtered(lambda d: d.state == 'accepted'):
            raise UserError(_(
                'Декларацію прийнято ДПС — змінити її можна лише уточнюючою декларацією.'))
        for rec in self.filtered(lambda d: d.state == 'submitted'):
            rec.message_post(body=_('Подану декларацію повернуто в чернетку (наприклад, '
                                    'ДПС її не прийняла).'))
        self.with_context(**{UNLOCK_CTX: True}).write(
            {'state': 'draft', 'submission_date': False})

    def action_accept(self):
        self.filtered(lambda d: d.state == 'submitted').with_context(
            **{UNLOCK_CTX: True}).write({'state': 'accepted'})

    def write(self, vals):
        if not self.env.context.get(UNLOCK_CTX):
            locked = self.filtered(lambda d: d.state in LOCKED_STATES)
            changed = sorted(LOCKED_FIELDS.intersection(vals))
            if locked and (changed or 'state' in vals):
                fields_desc = ', '.join(self._fields[f].string for f in changed) or _('статус')
                raise UserError(_(
                    'Декларацію «%(name)s» подано до ДПС — %(fields)s не змінюються. '
                    'Помилку виправляють уточнюючою декларацією.',
                    name=locked[0].name, fields=fields_desc))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_filed(self):
        if self.filtered(lambda d: d.state in LOCKED_STATES):
            raise UserError(_('Подану до ДПС декларацію видалити не можна.'))

    # ------------------------------------------------------------------ XML

    def _office_code(self):
        company = self.company_id
        office = company.l10n_ua_tax_office_id
        return re.sub(r'\D', '', (office.code if office else '') or company.tax_office_code or '')

    def _kved(self):
        company = self.company_id
        links = company.l10n_ua_kved_ids.sorted(lambda k: (not k.is_primary, k.sequence))
        return (links[:1].code or company.kved_main or '').strip()

    def _address(self):
        company = self.company_id
        return ', '.join(filter(None, [company.zip, company.state_id.name, company.city,
                                       company.street, company.street2]))

    def _check_xml_ready(self):
        """Помилки до формування — усе, чого бракує, одним повідомленням."""
        self.ensure_one()
        company = self.company_id
        problems = []
        if self.state == 'draft':
            problems.append(_('спершу розрахуйте декларацію'))
        if not re.fullmatch(r'\d{8}', re.sub(r'\D', '', company.edrpou or company.company_registry or '')):
            problems.append(_('код ЄДРПОУ компанії (8 цифр)'))
        if not re.fullmatch(r'\d{4}', self._office_code()):
            problems.append(_('податкова інспекція компанії (4-значний код ДПІ)'))
        if not company.l10n_ua_tax_office_id:
            problems.append(_('податковий орган компанії (назва ДПС у декларації)'))
        if not re.fullmatch(r'\d{2}\.\d{1,2}(\.\d)?', self._kved()):
            problems.append(_('основний КВЕД компанії'))
        if not (company.city or company.street):
            problems.append(_('адреса компанії'))
        if not self.signatory_name or not re.fullmatch(r'\d{10}', self.signatory_rnokpp or ''):
            problems.append(_('керівник і його РНОКПП (вкладка «Подання»)'))
        if self.accountant_rnokpp and not re.fullmatch(r'\d{10}', self.accountant_rnokpp):
            problems.append(_('РНОКПП головного бухгалтера (10 цифр)'))
        if problems:
            raise UserError(_('Неможливо сформувати XML декларації ЄП:\n• %s')
                            % '\n• '.join(problems))

    def _sequence_in_year(self):
        """Порядковий № декларації за рік: скільки декларацій цього року вже подано + 1."""
        self.ensure_one()
        filed = self.search_count([
            ('company_id', '=', self.company_id.id),
            ('year', '=', self.year),
            ('state', 'in', LOCKED_STATES),
            ('id', '!=', self.id),
        ])
        return filed + 1

    def _render_xml(self):
        self.ensure_one()
        company = self.company_id
        office = self._office_code()
        tin = re.sub(r'\D', '', company.edrpou or company.company_registry or '')
        period_type, period_month, marker = PERIODS[self.period]
        column = 'G3' if self.rate == '3' else 'G4'

        head = (
            '<DECLARHEAD>'
            f'<TIN>{tin}</TIN><C_DOC>{FORM[0]}</C_DOC><C_DOC_SUB>{FORM[1]}</C_DOC_SUB>'
            f'<C_DOC_VER>{FORM[2]}</C_DOC_VER><C_DOC_TYPE>0</C_DOC_TYPE>'
            f'<C_DOC_CNT>1</C_DOC_CNT><C_REG>{office[:2]}</C_REG><C_RAJ>{office[2:4]}</C_RAJ>'
            f'<PERIOD_MONTH>{period_month}</PERIOD_MONTH><PERIOD_TYPE>{period_type}</PERIOD_TYPE>'
            f'<PERIOD_YEAR>{self.year}</PERIOD_YEAR><C_STI_ORIG>{office}</C_STI_ORIG>'
            '<C_DOC_STAN>1</C_DOC_STAN><LINKED_DOCS xsi:nil="true"/>'
            f'<D_FILL>{date.today():%d%m%Y}</D_FILL><SOFTWARE>{SOFTWARE}</SOFTWARE>'
            '</DECLARHEAD>')

        body = [
            f'<HNY>{self._sequence_in_year()}</HNY><HZ>1</HZ>',
            f'<{marker}>1</{marker}><HZY>{self.year}</HZY>',
            f'<HNAME>{escape(company._l10n_ua_dps_name())}</HNAME><HTIN>{tin}</HTIN>',
            f'<HKVED>{self._kved()}</HKVED><HLOC>{escape(self._address())}</HLOC>',
        ]
        if re.fullmatch(r'\d{5}', company.zip or ''):
            body.append(f'<HZIP>{company.zip}</HZIP>')
        phone = re.sub(r'[^0-9 ()\-+.,;]', '', company.phone or '')
        if len(phone) >= 4:
            body.append(f'<HTEL>{phone}</HTEL>')
        if re.fullmatch(r'[^@\s]+@[^@\s]+', company.email or ''):
            body.append(f'<HEMAIL>{escape(company.email)}</HEMAIL>')
        # Назва ДПІ — українською, хоч би якою мовою працює користувач (якщо мову встановлено).
        office = company.l10n_ua_tax_office_id
        if 'uk_UA' in dict(self.env['res.lang'].get_installed()):
            office = office.with_context(lang='uk_UA')
        office_name = office.name
        body.append(f'<HSTI>{escape(office_name)}</HSTI>')
        for number, field, always in ROWS:
            value = self[field]
            if always or float_round(value or 0.0, precision_digits=2):
                tag = 'R%03d%s' % (number, column)
                body.append(f'<{tag}>{_dec2(value)}</{tag}>')
        body.append('<HFILL>%s</HFILL><HBOS>%s</HBOS><HKBOS>%s</HKBOS>' % (
            date.today().strftime('%d%m%Y'), escape(self.signatory_name),
            self.signatory_rnokpp))
        if self.accountant_name and self.accountant_rnokpp:
            body.append('<HBUH>%s</HBUH><HKBUH>%s</HKBUH>' % (
                escape(self.accountant_name), self.accountant_rnokpp))

        xml = ('<?xml version="1.0" encoding="windows-1251"?>'
               '<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
               f'xsi:noNamespaceSchemaLocation="{"".join(FORM)}.xsd">'
               f'{head}<DECLARBODY>{"".join(body)}</DECLARBODY></DECLAR>')
        return xml.encode('windows-1251', errors='xmlcharrefreplace')

    def action_generate_xml(self):
        for rec in self:
            rec._check_xml_ready()
            xml = rec._render_xml()
            rec.write({'xml_file': base64.b64encode(xml),
                       'xml_filename': dps_standard_filename(xml)})
        return True

    # ------------------------------------------------- контракт dps.submit.mixin

    def action_submit(self):
        """Підписати КЕП у браузері й подати декларацію до ДПС."""
        return self.action_kep_submit()

    def _dps_check_can_submit(self):
        for rec in self:
            if rec.state != 'calculated':
                raise UserError(_('Подати можна тільки розраховану декларацію.'))

    def _dps_ensure_xml(self):
        self.ensure_one()
        self.action_generate_xml()

    def _dps_submit_label(self):
        return _('Подати декларацію ЄП до ДПС')

    def _dps_store_receipts(self, result):
        # id подання — на нього посилаються квитанції ДПС (codRegdocRef).
        for item in result if isinstance(result, list) else [result]:
            if isinstance(item, dict) and item.get('id'):
                self.with_context(**{UNLOCK_CTX: True}).dps_submission_id = str(item['id'])
                break
        return super()._dps_store_receipts(result)

    def _dps_on_submitted(self, receipt):
        self.with_context(**{UNLOCK_CTX: True}).write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })
        self.message_post(body=_('Подано до ДПС. Квитанція: %s') % (receipt or '—'))
