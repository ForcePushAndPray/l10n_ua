"""Декларація платника єдиного податку четвертої групи (юридичної особи).

Форма J0103806 з додатками J0138106 (відомості про наявність земельних
ділянок) і J0138306 (розрахунок загального мінімального податкового
зобов'язання) — наказ Мінфіну № 578 у редакції наказу № 57 від 31.01.2025.
Структуру й порядок елементів звірено з XSD пакета СКЗ 1.34.0.0
(tests/schemas).

Подається загальна декларація — за місцем реєстрації платника, і звітні —
за кожною громадою (КАТОТТГ), де розташовані ділянки; до кожної — додатки 1
і 3 у частині відповідних ділянок.
"""
import base64
import re
from calendar import monthrange
from collections import OrderedDict
from datetime import date
from xml.sax.saxutils import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_round

from odoo.addons.l10n_ua_agro_base.models.agro_field import LAND_TYPES
from odoo.addons.l10n_ua_tax_cabinet.models.l10n_ua_dps_submit_mixin import dps_standard_filename

SOFTWARE = 'Odoo l10n_ua'
MAIN_FORM = ('J01', '038', '6')
ANNEX1_FORM = ('J01', '381', '6')
ANNEX3_FORM = ('J01', '383', '6')

# Частки річної суми по кварталах (п. 295.1 ПКУ): 10 / 10 / 50 / 30 %.
QUARTER_SHARES = (10.0, 10.0, 50.0, 30.0)
# Таблиці розрахункової частини / додатка 1 за видом угідь.
TABLES = OrderedDict([
    ('T11', ('arable', 'fallow')),
    ('T12', ('hayfield',)),
    ('T13', ('pasture',)),
    ('T14', ('perennial',)),
])
CATEGORY_NAMES = {
    'arable': 'рілля', 'fallow': 'рілля (перелоги)', 'hayfield': 'сіножаті',
    'pasture': 'пасовища', 'perennial': 'багаторічні насадження',
}
# Коефіцієнт К мінімального податкового зобов'язання: 0,05 (пп. 38¹.1.1 ПКУ),
# на час воєнного стану з 2025 року — 0,057 (п. 67¹ підрозд. 10 розд. XX ПКУ).
MPZ_K_DEFAULT = 0.057
# Нижня межа МПЗ, грн з 1 га: 1400 — якщо частка ріллі не менше 50 %, інакше 700.
MPZ_FLOOR_ARABLE = 1400.0
MPZ_FLOOR_OTHER = 700.0
AGRI_SHARE_MIN = 75.0

LOCKED_STATES = ('submitted', 'accepted')


def _dec(value, digits=2):
    return ('%.' + str(digits) + 'f') % float_round(value or 0.0, precision_digits=digits)


def _overlap_days(start, end, date_from, date_to):
    start = max(start, date_from)
    end = min(end, date_to)
    return (end - start).days + 1 if end >= start else 0


class L10nUaTax4Declaration(models.Model):
    _name = 'l10n_ua.tax4.declaration'
    _description = 'Декларація платника єдиного податку четвертої групи'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'l10n_ua.dps.submit.mixin']
    _order = 'year desc, declaration_type, katottg'

    name = fields.Char(string='Назва', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Компанія', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    year = fields.Integer(string='Рік', required=True, tracking=True,
                          default=lambda self: fields.Date.context_today(self).year,
                          help='Рік, за який нараховується податок (декларація подається до 20 лютого цього року).')
    declaration_type = fields.Selection(
        [('general', 'Загальна'), ('reporting', 'Звітна (за громадою)')],
        string='Вид', required=True, default='general', tracking=True)
    parent_id = fields.Many2one('l10n_ua.tax4.declaration', string='Загальна декларація',
                                ondelete='cascade', index=True)
    child_ids = fields.One2many('l10n_ua.tax4.declaration', 'parent_id', string='Звітні декларації')
    katottg = fields.Char(string='КАТОТТГ',
                          help='Громада, за місцем розташування ділянок якої подається звітна декларація; '
                               'для загальної — громада місцезнаходження платника.')
    tax_office_id = fields.Many2one(
        'l10n_ua.tax.office', string='Контролюючий орган',
        help='Загальна — за основним місцем обліку; звітна — за місцем розташування ділянок.')
    sequence_number = fields.Integer(string='Порядковий № за рік', default=1)
    state = fields.Selection(
        [('draft', 'Чернетка'), ('calculated', 'Розраховано'),
         ('submitted', 'Подано'), ('accepted', 'Прийнято')],
        string='Статус', default='draft', tracking=True, copy=False)
    ngo_index = fields.Float(
        string='Коефіцієнт індексації НГО', digits=(6, 3), default=1.0,
        help='Множник до НГО ділянок, якщо НГО в картках ще не проіндексовано на 1 січня року.')

    line_ids = fields.One2many('l10n_ua.tax4.declaration.line', 'declaration_id',
                               string='Розрахунок податку', copy=False)
    mpz_line_ids = fields.One2many('l10n_ua.tax4.mpz.line', 'declaration_id',
                                   string='МПЗ за ділянками', copy=False)

    # --- розрахункова частина (рядки 3–5)
    tax_annual = fields.Monetary(string='Нараховано на рік', compute='_compute_totals', store=True)
    tax_q1 = fields.Monetary(string='I квартал', compute='_compute_totals', store=True)
    tax_q2 = fields.Monetary(string='II квартал', compute='_compute_totals', store=True)
    tax_q3 = fields.Monetary(string='III квартал', compute='_compute_totals', store=True)
    tax_q4 = fields.Monetary(string='IV квартал', compute='_compute_totals', store=True)
    mpz_difference = fields.Monetary(
        string='Різниця МПЗ (рядок 4)', compute='_compute_mpz_difference', store=True,
        help='Позитивна різниця між загальним МПЗ і сплаченими податками за минулий рік — '
             'сплачується разом з податком за I квартал.')
    total_annual = fields.Monetary(string='Загальні зобов\'язання (рядок 5)', compute='_compute_mpz_difference', store=True)
    total_q1 = fields.Monetary(string='До сплати за I квартал', compute='_compute_mpz_difference', store=True)

    # --- додаток 3, розділ II (за минулий рік)
    mpz_total = fields.Monetary(string='Загальне МПЗ (рядок 01)', compute='_compute_totals', store=True)
    rent20_total = fields.Monetary(string='20 % орендної плати (рядок 03)', compute='_compute_totals', store=True)
    paid_single_tax = fields.Monetary(string='02.1 Єдиний податок')
    paid_profit_tax = fields.Monetary(string='02.2 Податок на прибуток')
    paid_pdfo = fields.Monetary(string='02.3 ПДФО')
    paid_military = fields.Monetary(string='02.4 Військовий збір')
    paid_pdfo_employees = fields.Monetary(string='02.5 ПДФО з доходів працівників')
    paid_military_employees = fields.Monetary(string='02.6 ВЗ з доходів працівників')
    paid_pdfo_rent = fields.Monetary(string='02.7 ПДФО з доходів за договорами оренди')
    paid_military_rent = fields.Monetary(string='02.8 ВЗ з доходів за договорами оренди')
    paid_land_tax = fields.Monetary(string='02.9 Земельний податок')
    paid_water_rent = fields.Monetary(string='02.10 Рентна плата за воду')
    paid_total = fields.Monetary(string='Сплачено податків (рядок 02)', compute='_compute_totals', store=True)
    mpz_balance = fields.Monetary(string='Різниця (рядок 04)', compute='_compute_totals', store=True)

    # --- частка сільськогосподарського товаровиробництва (минулий рік)
    agri_income = fields.Monetary(string='Дохід від реалізації власної с/г продукції')
    total_income = fields.Monetary(string='Загальний дохід')
    agri_share = fields.Float(string='Частка с/г товаровиробництва, %', digits=(5, 2),
                              compute='_compute_agri_share', store=True)

    # --- підписанти, файли, подання
    signatory_name = fields.Char(string='Керівник', compute='_compute_signatory', store=True, readonly=False,
                                 help='Власне ім\'я ПРІЗВИЩЕ керівника (уповноваженої особи)')
    signatory_rnokpp = fields.Char(string='РНОКПП керівника', compute='_compute_signatory', store=True,
                                   readonly=False)
    accountant_name = fields.Char(string='Головний бухгалтер')
    accountant_rnokpp = fields.Char(string='РНОКПП головного бухгалтера')
    xml_file = fields.Binary(string='XML декларації', attachment=True, copy=False)
    xml_filename = fields.Char(copy=False)
    annex1_xml_file = fields.Binary(string='XML додатка 1', attachment=True, copy=False)
    annex1_xml_filename = fields.Char(copy=False)
    annex3_xml_file = fields.Binary(string='XML додатка 3', attachment=True, copy=False)
    annex3_xml_filename = fields.Char(copy=False)
    submission_date = fields.Date(string='Дата подання', copy=False)
    accrual_move_ids = fields.Many2many('account.move', string='Нарахування', copy=False, readonly=True)

    _unique_declaration = models.Constraint(
        'unique(company_id, year, declaration_type, katottg)',
        'Декларація ЄП 4 групи за цей рік і громаду вже існує!',
    )

    # ------------------------------------------------------------------ computes

    @api.depends('year', 'declaration_type', 'katottg')
    def _compute_name(self):
        for rec in self:
            if rec.declaration_type == 'general':
                rec.name = _('Декларація ЄП 4 групи %(year)s (загальна)', year=rec.year or '')
            else:
                rec.name = _('Декларація ЄП 4 групи %(year)s, %(katottg)s', year=rec.year or '',
                             katottg=rec.katottg or '')

    @api.depends('company_id')
    def _compute_signatory(self):
        for rec in self:
            director = rec.company_id.director_id if 'director_id' in rec.company_id._fields else False
            if director and not rec.signatory_name:
                rec.signatory_name = director.name
                rec.signatory_rnokpp = getattr(director, 'rnokpp', False) or False

    @api.depends('line_ids.annual_tax', 'line_ids.q1', 'line_ids.q2', 'line_ids.q3', 'line_ids.q4',
                 'mpz_line_ids.mpz_ngo', 'mpz_line_ids.mpz_region', 'mpz_line_ids.rent20',
                 'paid_single_tax', 'paid_profit_tax', 'paid_pdfo', 'paid_military', 'paid_pdfo_employees',
                 'paid_military_employees', 'paid_pdfo_rent', 'paid_military_rent', 'paid_land_tax',
                 'paid_water_rent')
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.tax_annual = sum(lines.mapped('annual_tax'))
            rec.tax_q1 = sum(lines.mapped('q1'))
            rec.tax_q2 = sum(lines.mapped('q2'))
            rec.tax_q3 = sum(lines.mapped('q3'))
            rec.tax_q4 = sum(lines.mapped('q4'))
            mpz = rec.mpz_line_ids
            rec.mpz_total = sum(mpz.mapped('mpz_ngo')) + sum(mpz.mapped('mpz_region'))
            rec.rent20_total = sum(mpz.mapped('rent20'))
            rec.paid_total = sum(rec[f] for f in (
                'paid_single_tax', 'paid_profit_tax', 'paid_pdfo', 'paid_military', 'paid_pdfo_employees',
                'paid_military_employees', 'paid_pdfo_rent', 'paid_military_rent', 'paid_land_tax',
                'paid_water_rent'))
            rec.mpz_balance = rec.mpz_total - rec.paid_total - rec.rent20_total

    # Окремо від _compute_totals: звітна читає mpz_balance загальної, а в одному
    # методі він для неї ще не перерахований (записи того самого обчислення).
    @api.depends('mpz_balance', 'tax_annual', 'tax_q1', 'parent_id.mpz_balance', 'line_ids.area',
                 'parent_id.line_ids.area', 'declaration_type')
    def _compute_mpz_difference(self):
        for rec in self:
            if rec.declaration_type == 'general':
                difference = max(rec.mpz_balance, 0.0)
            else:
                # Збільшення розподіляється між громадами пропорційно площі ділянок
                # (п. 297¹.7 ПКУ).
                parent = rec.parent_id
                total_area = sum(parent.line_ids.mapped('area')) if parent else 0.0
                share = sum(rec.line_ids.mapped('area')) / total_area if total_area else 0.0
                difference = rec.currency_id.round(max(parent.mpz_balance, 0.0) * share) if parent else 0.0
            rec.mpz_difference = difference
            rec.total_annual = rec.tax_annual + difference
            rec.total_q1 = rec.tax_q1 + difference

    @api.depends('agri_income', 'total_income')
    def _compute_agri_share(self):
        for rec in self:
            rec.agri_share = rec.agri_income / rec.total_income * 100.0 if rec.total_income else 0.0

    # ------------------------------------------------------------------ розрахунок

    def _plots(self):
        """Ділянки, що використовуються платником у році: власні й орендовані."""
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('l10n_ua_tax4_excluded', '=', False)]
        if self.declaration_type == 'reporting':
            domain.append(('katottg', '=', self.katottg))
        return self.env['l10n_ua.agro.land.plot'].search(domain, order='land_type, cadastral_number')

    def _use_periods(self, plot, date_from, date_to):
        """Періоди володіння / користування ділянкою в межах [date_from, date_to]."""
        if plot.ownership == 'company':
            return [(date_from, date_to)]
        periods = []
        for lease in plot.lease_ids.filtered(lambda l: l.state in ('active', 'expired', 'terminated')
                                             and l.company_id == self.company_id):
            start = max(lease.date_start, date_from)
            end = min(lease.date_end or date_to, date_to)
            if end >= start:
                periods.append((start, end))
        return periods

    def action_calculate(self):
        for rec in self:
            if rec.state in LOCKED_STATES:
                raise UserError(_('Подану декларацію не можна перерахувати.'))
            rec.line_ids.unlink()
            rec.mpz_line_ids.unlink()
            rec._calculate_tax()
            rec._calculate_mpz()
            if rec.declaration_type == 'general':
                rec._prefill_paid_taxes()
                rec._compute_agri_income()
                if not rec.katottg:
                    rec.katottg = rec.company_id.katottg
                if not rec.tax_office_id:
                    rec.tax_office_id = rec.company_id.l10n_ua_tax_office_id
            rec.state = 'calculated'
        return True

    def _calculate_tax(self):
        self.ensure_one()
        year = self.year
        Rate = self.env['l10n_ua.tax4.rate']
        quarters = [(date(year, m, 1), date(year, m + 2, monthrange(year, m + 2)[1])) for m in (1, 4, 7, 10)]
        vals = []
        for plot in self._plots():
            periods = self._use_periods(plot, date(year, 1, 1), date(year, 12, 31))
            if not periods:
                continue
            rate = Rate._get_rate(plot.land_type, plot.l10n_ua_tax4_mountain_zone)
            ngo_ha = plot.ngo_value * self.ngo_index / plot.area if plot.area else 0.0
            ngo_ha = float_round(ngo_ha, precision_digits=2)
            annual = float_round(plot.area * ngo_ha * rate / 100.0, precision_digits=2)
            line = {
                'declaration_id': self.id, 'plot_id': plot.id, 'land_type': plot.land_type,
                'katottg': plot.katottg, 'area': plot.area, 'ngo_ha': ngo_ha, 'rate': rate,
                'annual_tax': annual,
            }
            full_year = True
            for index, (q_from, q_to) in enumerate(quarters):
                q_days = (q_to - q_from).days + 1
                used = min(sum(_overlap_days(start, end, q_from, q_to) for start, end in periods), q_days)
                full_year = full_year and used == q_days
                line['q%d' % (index + 1)] = float_round(
                    annual * QUARTER_SHARES[index] / 100.0 / q_days * used, precision_digits=2)
            if full_year:
                # копійчаний залишок — у IV квартал, щоб квартали дали річну суму
                line['q4'] = float_round(annual - line['q1'] - line['q2'] - line['q3'], precision_digits=2)
            vals.append(line)
        self.env['l10n_ua.tax4.declaration.line'].create(vals)

    def _calculate_mpz(self):
        """Додаток 3: МПЗ за минулий рік за кожною ділянкою (ПКУ ст. 38¹)."""
        self.ensure_one()
        prev = self.year - 1
        y_from, y_to = date(prev, 1, 1), date(prev, 12, 31)
        company = self.company_id
        k = MPZ_K_DEFAULT
        vals = []
        for plot in self._plots():
            if plot.land_type not in ('arable', 'fallow', 'hayfield', 'pasture', 'perennial'):
                continue
            periods = self._use_periods(plot, y_from, y_to)
            months = len({(d.year, d.month) for start, end in periods
                          for d in (date(start.year, m, 1) for m in range(start.month, end.month + 1))})
            if not months:
                continue
            owned = plot.ownership == 'company'
            arable = plot.l10n_ua_tax4_arable_share
            floor_ha = MPZ_FLOOR_ARABLE if arable >= 50.0 else MPZ_FLOOR_OTHER
            floor = floor_ha * plot.area * months / 12.0
            line = {
                'declaration_id': self.id, 'plot_id': plot.id, 'k': k, 'months': min(months, 12),
                'own_area': plot.area if owned else 0.0, 'own_arable': arable if owned else 0.0,
                'leased_area': 0.0 if owned else plot.area, 'leased_arable': 0.0 if owned else arable,
            }
            if plot.l10n_ua_tax4_ngo_done:
                line['ngo_done'] = plot.ngo_value
                line['mpz_ngo'] = float_round(max(plot.ngo_value * k * months / 12.0, floor), precision_digits=2)
            else:
                line['ngo_region'] = company.l10n_ua_tax4_region_ngo
                line['mpz_region'] = float_round(
                    max(company.l10n_ua_tax4_region_ngo * plot.area * k * months / 12.0, floor), precision_digits=2)
            line['rent20'] = float_round(0.2 * self._rent_paid(plot, y_from, y_to), precision_digits=2)
            vals.append(line)
        self.env['l10n_ua.tax4.mpz.line'].create(vals)

    def _rent_paid(self, plot, date_from, date_to):
        """Орендна плата, сплачена за ділянку орендодавцю-юрособі або за землю
        державної / комунальної власності (абз. 8 п. 297¹.5 ПКУ)."""
        if plot.ownership == 'company':
            return 0.0
        lines = self.env['l10n_ua.agro.rent.payment.line'].search([
            ('state', '=', 'posted'), ('date', '>=', date_from), ('date', '<=', date_to),
            ('lease_id.plot_ids', 'in', plot.ids), ('company_id', '=', self.company_id.id)])
        lines = lines.filtered(lambda l: l.lessor_id.is_company or plot.ownership in ('state', 'communal'))
        total = 0.0
        for line in lines:
            lease = line.lease_id
            share = plot.area / lease.plots_area if lease.plots_area else 0.0
            total += line.amount * share
        return total

    def _prefill_paid_taxes(self):
        """ПДФО і ВЗ, утримані з орендної плати фізособам за минулий рік."""
        self.ensure_one()
        prev = self.year - 1
        lines = self.env['l10n_ua.agro.rent.accrual.line'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('date', '>=', date(prev, 1, 1)), ('date', '<=', date(prev, 12, 31))])
        if not self.paid_pdfo_rent:
            self.paid_pdfo_rent = sum(lines.mapped('pdfo_amount'))
        if not self.paid_military_rent:
            self.paid_military_rent = sum(lines.mapped('military_amount'))
        if not self.paid_single_tax:
            previous = self.search([('company_id', '=', self.company_id.id), ('year', '=', prev),
                                    ('declaration_type', '=', 'general'), ('state', 'in', LOCKED_STATES)], limit=1)
            self.paid_single_tax = previous.total_annual

    def _compute_agri_income(self):
        """Дохід за минулий рік: від реалізації продукції культур (довідник
        культур) — і загальний (рахунки доходів)."""
        self.ensure_one()
        prev = self.year - 1
        products = self.env['l10n_ua.agro.crop'].search([]).product_id
        products |= self.env['l10n_ua.agro.crop'].search([]).byproduct_id
        aml = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('date', '>=', date(prev, 1, 1)), ('date', '<=', date(prev, 12, 31)),
            ('account_id.account_type', 'in', ('income', 'income_other'))])
        self.total_income = -sum(aml.mapped('balance'))
        self.agri_income = -sum(aml.filtered(lambda l: l.product_id in products).mapped('balance'))

    def action_create_reporting(self):
        """Звітні декларації — за кожною громадою, де розташовані ділянки."""
        self.ensure_one()
        if self.declaration_type != 'general':
            raise UserError(_('Звітні декларації створюються із загальної.'))
        if not self.line_ids:
            self.action_calculate()
        existing = set(self.child_ids.mapped('katottg'))
        for katottg in sorted(set(self.line_ids.mapped('katottg')) - existing - {False}):
            child = self.create({
                'company_id': self.company_id.id, 'year': self.year, 'declaration_type': 'reporting',
                'parent_id': self.id, 'katottg': katottg, 'ngo_index': self.ngo_index,
                'signatory_name': self.signatory_name, 'signatory_rnokpp': self.signatory_rnokpp,
                'accountant_name': self.accountant_name, 'accountant_rnokpp': self.accountant_rnokpp,
            })
            child.action_calculate()
        missing = self.line_ids.filtered(lambda l: not l.katottg).plot_id
        if missing:
            self.message_post(body=_('Без КАТОТТГ (не потрапили у звітні): %s')
                              % ', '.join(missing.mapped('cadastral_number')))
        return True

    # ------------------------------------------------------------------ нарахування

    def action_post_accruals(self):
        """Квартальні нарахування ЄП (рядок 5): Дт витрат — Кт 641, на останній день кварталу."""
        for rec in self:
            if rec.declaration_type != 'general':
                raise UserError(_('Нарахування проводяться за загальною декларацією.'))
            if rec.accrual_move_ids.filtered(lambda m: m.state == 'posted'):
                raise UserError(_('Нарахування за %s уже проведено.', rec.year))
            company = rec.company_id
            expense = company.l10n_ua_tax4_expense_account_id or self.env['account.account'].search(
                [('code', '=like', '231%'), ('company_ids', 'in', company.id)], order='code', limit=1)
            payable = company.l10n_ua_tax4_payable_account_id or self.env['account.account'].search(
                [('code', '=like', '641%'), ('company_ids', 'in', company.id)], order='code', limit=1)
            if not expense or not payable:
                raise UserError(_('Вкажіть рахунки витрат і розрахунків за ЄП 4 групи в налаштуваннях компанії.'))
            journal = self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
            moves = self.env['account.move']
            amounts = (rec.total_q1, rec.tax_q2, rec.tax_q3, rec.tax_q4)
            for index, amount in enumerate(amounts):
                if rec.currency_id.is_zero(amount):
                    continue
                month = (index + 1) * 3
                label = _('Єдиний податок 4 групи, %(q)s квартал %(year)s', q=index + 1, year=rec.year)
                moves |= self.env['account.move'].create({
                    'move_type': 'entry', 'journal_id': journal.id, 'company_id': company.id,
                    'date': date(rec.year, month, monthrange(rec.year, month)[1]),
                    'ref': rec.name,
                    'line_ids': [(0, 0, {'name': label, 'account_id': expense.id, 'debit': amount}),
                                 (0, 0, {'name': label, 'account_id': payable.id, 'credit': amount})],
                })
            moves.action_post()
            rec.accrual_move_ids = moves
        return True

    def payment_schedule(self):
        """Строки сплати: протягом 30 календарних днів після кварталу."""
        self.ensure_one()
        year = self.year
        return [
            (_('I квартал'), date(year, 4, 30), self.total_q1),
            (_('II квартал'), date(year, 7, 30), self.tax_q2),
            (_('III квартал'), date(year, 10, 30), self.tax_q3),
            (_('IV квартал'), date(year + 1, 1, 30), self.tax_q4),
        ]

    # ------------------------------------------------------------------ XML

    def _office_code(self):
        office = self.tax_office_id or self.company_id.l10n_ua_tax_office_id
        return re.sub(r'\D', '', (office.code if office else '') or self.company_id.tax_office_code or '')

    def _tin(self):
        company = self.company_id
        return re.sub(r'\D', '', company.edrpou or company.company_registry or '')

    def _check_xml_ready(self):
        self.ensure_one()
        company = self.company_id
        problems = []
        if self.state == 'draft':
            problems.append(_('розрахуйте декларацію'))
        if not re.fullmatch(r'\d{8}', self._tin()):
            problems.append(_('код ЄДРПОУ компанії (8 цифр)'))
        if not re.fullmatch(r'\d{4}', self._office_code()):
            problems.append(_('контролюючий орган (код ДПІ з 4 цифр)'))
        if not re.fullmatch(r'UA\d{17}', self.katottg or ''):
            problems.append(_('КАТОТТГ декларації (UA + 17 цифр)'))
        if not re.fullmatch(r'\d{2}\.\d{1,2}(\.\d)?', (company.kved_main or '').strip()):
            problems.append(_('основний КВЕД компанії'))
        if not self.signatory_name or not re.fullmatch(r'\d{10}', self.signatory_rnokpp or ''):
            problems.append(_('керівник і його РНОКПП (10 цифр)'))
        bad = self.line_ids.filtered(lambda l: not re.fullmatch(r'UA\d{17}', l.katottg or ''))
        if bad:
            problems.append(_('КАТОТТГ ділянок %s') % ', '.join(bad.plot_id.mapped('cadastral_number')))
        if problems:
            raise UserError(_('Неможливо сформувати XML декларації ЄП 4 групи:\n• %s') % '\n• '.join(problems))

    def _head(self, form, linked):
        office = self._office_code()
        if linked:
            docs = ''.join(
                '<DOC NUM="%d" TYPE="%s"><C_DOC>%s</C_DOC><C_DOC_SUB>%s</C_DOC_SUB><C_DOC_VER>%s</C_DOC_VER>'
                '<C_DOC_TYPE>0</C_DOC_TYPE><C_DOC_CNT>1</C_DOC_CNT><C_DOC_STAN>1</C_DOC_STAN>'
                '<FILENAME>%s</FILENAME></DOC>' % (num, link_type, f[0], f[1], f[2], fname)
                for num, (link_type, f, fname) in enumerate(linked, 1))
            linked_xml = '<LINKED_DOCS>%s</LINKED_DOCS>' % docs
        else:
            linked_xml = '<LINKED_DOCS xsi:nil="true"/>'
        return (
            '<DECLARHEAD>'
            f'<TIN>{self._tin()}</TIN><C_DOC>{form[0]}</C_DOC><C_DOC_SUB>{form[1]}</C_DOC_SUB>'
            f'<C_DOC_VER>{form[2]}</C_DOC_VER><C_DOC_TYPE>0</C_DOC_TYPE><C_DOC_CNT>1</C_DOC_CNT>'
            f'<C_REG>{office[:2]}</C_REG><C_RAJ>{office[2:4]}</C_RAJ>'
            f'<PERIOD_MONTH>12</PERIOD_MONTH><PERIOD_TYPE>5</PERIOD_TYPE><PERIOD_YEAR>{self.year}</PERIOD_YEAR>'
            f'<C_STI_ORIG>{office}</C_STI_ORIG><C_DOC_STAN>1</C_DOC_STAN>{linked_xml}'
            f'<D_FILL>{date.today():%d%m%Y}</D_FILL><SOFTWARE>{SOFTWARE}</SOFTWARE>'
            '</DECLARHEAD>')

    def _kind_marks(self):
        return ('<HZG>1</HZG><HZ>1</HZ>' if self.declaration_type == 'general' else '<HZ>1</HZ>')

    def _signers(self):
        xml = '<HFILL>%s</HFILL><HBOS>%s</HBOS><HKBOS>%s</HKBOS>' % (
            date.today().strftime('%d%m%Y'), escape(self.signatory_name), self.signatory_rnokpp)
        if self.accountant_name and re.fullmatch(r'\d{10}', self.accountant_rnokpp or ''):
            xml += '<HBUH>%s</HBUH><HKBUH>%s</HKBUH>' % (escape(self.accountant_name), self.accountant_rnokpp)
        return xml

    @staticmethod
    def _wrap(form, head, body):
        xml = ('<?xml version="1.0" encoding="windows-1251"?>'
               '<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
               f'xsi:noNamespaceSchemaLocation="{"".join(form)}.xsd">'
               f'{head}<DECLARBODY>{body}</DECLARBODY></DECLAR>')
        return xml.encode('windows-1251', errors='xmlcharrefreplace')

    @staticmethod
    def _columns(prefix, rows, columns):
        """Табличні елементи XSD ідуть стовпцями: усі рядки G3, потім усі G4…"""
        out = []
        for col, key, fmt in columns:
            for num, row in enumerate(rows, 1):
                value = row.get(key)
                if value in (None, '', False):
                    continue
                out.append('<%sRXXXX%s ROWNUM="%d">%s</%sRXXXX%s>' % (prefix, col, num, fmt(value), prefix, col))
        return ''.join(out)

    def _tax_rows(self, land_types):
        """Рядки розрахункової частини: групи за НГО 1 га і ставкою."""
        groups = OrderedDict()
        for line in self.line_ids.filtered(lambda l: l.land_type in land_types):
            row = groups.setdefault((line.ngo_ha, line.rate), {
                'area': 0.0, 'ngo_ha': line.ngo_ha, 'rate': line.rate,
                'annual': 0.0, 'q1': 0.0, 'q2': 0.0, 'q3': 0.0, 'q4': 0.0})
            row['area'] += line.area
            for key, field in (('annual', 'annual_tax'), ('q1', 'q1'), ('q2', 'q2'), ('q3', 'q3'), ('q4', 'q4')):
                row[key] += line[field]
        return list(groups.values())

    def _render_main(self, head):
        company = self.company_id
        office = self.tax_office_id or company.l10n_ua_tax_office_id
        if 'uk_UA' in dict(self.env['res.lang'].get_installed()):
            office = office.with_context(lang='uk_UA')
        address = ', '.join(filter(None, [company.zip, company.state_id.name, company.city,
                                          company.street, company.street2]))
        body = [
            f'<HNY>{self.sequence_number}</HNY>{self._kind_marks()}<HZY>{self.year}</HZY>',
            f'<HNAME>{escape(company._l10n_ua_dps_name())}</HNAME><HTIN>{self._tin()}</HTIN>',
            f'<HKVED>{(company.kved_main or "").strip()}</HKVED>',
        ]
        if re.fullmatch(r'\d{5}', company.zip or ''):
            body.append(f'<HZIP>{company.zip}</HZIP>')
        phone = re.sub(r'[^0-9 ()\-+.,;]', '', company.phone or '')
        if len(phone) >= 4:
            body.append(f'<HTEL>{phone}</HTEL>')
        body.append(f'<HLOC>{escape(address or company.name)}</HLOC>')
        if re.fullmatch(r'[^@\s]+@[^@\s]+', company.email or ''):
            body.append(f'<HEMAIL>{escape(company.email)}</HEMAIL>')
        if office:
            body.append(f'<HSTI>{escape(office.name)}</HSTI>')
        body.append(f'<HKATOTTG>{self.katottg}</HKATOTTG>')
        columns = [('G3', 'area', lambda v: _dec(v, 4)), ('G4', 'ngo_ha', _dec), ('G5', 'rate', _dec),
                   ('G6', 'annual', _dec), ('G7', 'q1', _dec), ('G8', 'q2', _dec), ('G9', 'q3', _dec),
                   ('G10', 'q4', _dec)]
        for table, land_types in TABLES.items():
            body.append(self._columns(table, self._tax_rows(land_types), columns))
        body.append(f'<R03G2>{self.year}</R03G2>')
        for col, value in (('G6', self.tax_annual), ('G7', self.tax_q1), ('G8', self.tax_q2),
                           ('G9', self.tax_q3), ('G10', self.tax_q4)):
            body.append(f'<R03{col}>{_dec(value)}</R03{col}>')
        if self.mpz_difference:
            body.append(f'<R04G7>{_dec(self.mpz_difference)}</R04G7>')
        for col, value in (('G6', self.total_annual), ('G7', self.total_q1), ('G8', self.tax_q2),
                           ('G9', self.tax_q3), ('G10', self.tax_q4)):
            body.append(f'<R05{col}>{_dec(value)}</R05{col}>')
        body.append('<HD1>1</HD1>')
        if self.mpz_line_ids:
            body.append('<HD3>1</HD3>')
        body.append(self._signers())
        return self._wrap(MAIN_FORM, head, ''.join(body))

    def _annex1_rows(self, land_types):
        lines = self.line_ids.filtered(lambda l: l.land_type in land_types)
        if self.declaration_type == 'general':
            # У загальній — рядки за кодами КАТОТТГ без реквізитів ділянок.
            by_code = OrderedDict()
            for line in lines:
                by_code.setdefault(line.katottg, 0.0)
                by_code[line.katottg] += line.area
            return [{'category': CATEGORY_NAMES[land_types[0]], 'katottg': code, 'area': area}
                    for code, area in by_code.items()]
        rows = []
        for line in lines:
            plot = line.plot_id
            lease = plot.lease_ids.filtered(lambda l: l.state == 'active')[:1] if plot.ownership != 'company' else False
            rows.append({
                'category': CATEGORY_NAMES[line.land_type],
                'lease_number': lease.name if lease else None,
                'lease_date': (lease.date or lease.date_start) if lease else None,
                'ownership_doc': None,
                'reg_date': lease.registration_date if lease else None,
                'reg_number': lease.registration_number if lease else None,
                'cadastral': plot.cadastral_number,
                'region': int(plot.cadastral_number[:2]) if plot.cadastral_number[:2].isdigit() else None,
                'katottg': line.katottg,
                'area': line.area,
            })
        return rows

    def _render_annex1(self, head):
        body = [f'<HNY>{self.sequence_number}</HNY><HNUM>1</HNUM>{self._kind_marks()}']
        string = lambda v: escape(str(v))
        columns = [('G2S', 'category', string), ('G3S', 'lease_number', string),
                   ('G4D', 'lease_date', lambda d: d.strftime('%d%m%Y')),
                   ('G5S', 'ownership_doc', string), ('G6D', 'reg_date', lambda d: d.strftime('%d%m%Y')),
                   ('G7S', 'reg_number', string), ('G8S', 'cadastral', string), ('G9', 'region', str),
                   ('G10S', 'katottg', string), ('G11', 'area', lambda v: _dec(v, 4))]
        for table, land_types in TABLES.items():
            rows = self._annex1_rows(land_types)
            body.append(self._columns(table, rows, columns))
            if rows:
                # підсумок таблиці: T11 → R011G11, T12 → R012G11 …
                tag = 'R0%sG11' % table[1:]
                body.append('<%s>%s</%s>' % (tag, _dec(sum(r['area'] for r in rows), 4), tag))
        body.append(self._signers())
        return self._wrap(ANNEX1_FORM, head, ''.join(body))

    def _render_annex3(self, head):
        body = [f'<HNY>{self.sequence_number}</HNY><HNUM>1</HNUM>{self._kind_marks()}<HZY1>{self.year - 1}</HZY1>']
        rows = [{
            'cadastral': line.plot_id.cadastral_number,
            'own_area': line.own_area or None, 'own_arable': line.own_arable if line.own_area else None,
            'leased_area': line.leased_area or None,
            'leased_arable': line.leased_arable if line.leased_area else None,
            'ngo_done': line.ngo_done or None, 'ngo_region': line.ngo_region or None,
            'k': line.k, 'months': line.months,
            'mpz_ngo': line.mpz_ngo or None, 'mpz_region': line.mpz_region or None,
            'rent20': line.rent20 or None,
        } for line in self.mpz_line_ids]
        columns = [('G2S', 'cadastral', escape), ('G3', 'own_area', lambda v: _dec(v, 4)),
                   ('G4', 'own_arable', _dec), ('G5', 'leased_area', lambda v: _dec(v, 4)),
                   ('G6', 'leased_arable', _dec), ('G7', 'ngo_done', _dec), ('G8', 'ngo_region', _dec),
                   ('G9', 'k', lambda v: _dec(v, 3)), ('G10', 'months', str), ('G11', 'mpz_ngo', _dec),
                   ('G12', 'mpz_region', _dec), ('G14', 'rent20', _dec)]
        body.append(self._columns('T1', rows, columns))
        mpz = self.mpz_line_ids
        body.append('<R002G3>%s</R002G3><R002G5>%s</R002G5>' % (
            _dec(sum(mpz.mapped('own_area')), 4), _dec(sum(mpz.mapped('leased_area')), 4)))
        body.append('<R002G11>%s</R002G11><R002G12>%s</R002G12><R002G13>%s</R002G13><R002G14>%s</R002G14>' % (
            _dec(sum(mpz.mapped('mpz_ngo'))), _dec(sum(mpz.mapped('mpz_region'))),
            _dec(self.mpz_total), _dec(self.rent20_total)))
        body.append(f'<R01G3>{_dec(self.mpz_total)}</R01G3><R02G3>{_dec(self.paid_total)}</R02G3>')
        for row, field in (('R021', 'paid_single_tax'), ('R022', 'paid_profit_tax'), ('R023', 'paid_pdfo'),
                           ('R024', 'paid_military'), ('R025', 'paid_pdfo_employees'),
                           ('R026', 'paid_military_employees'), ('R027', 'paid_pdfo_rent'),
                           ('R028', 'paid_military_rent'), ('R029', 'paid_land_tax'),
                           ('R0210', 'paid_water_rent')):
            if self[field]:
                body.append(f'<{row}G3>{_dec(self[field])}</{row}G3>')
        body.append(f'<R03G3>{_dec(self.rent20_total)}</R03G3><R04G3>{_dec(self.mpz_balance)}</R04G3>')
        body.append(self._signers())
        return self._wrap(ANNEX3_FORM, head, ''.join(body))

    def action_generate_xml(self):
        for rec in self:
            rec._check_xml_ready()
            main_name = dps_standard_filename(rec._wrap(MAIN_FORM, rec._head(MAIN_FORM, []), ''))
            a1_name = dps_standard_filename(rec._wrap(ANNEX1_FORM, rec._head(ANNEX1_FORM, []), ''))
            a3_name = dps_standard_filename(rec._wrap(ANNEX3_FORM, rec._head(ANNEX3_FORM, []), ''))
            main_link = (lambda n: n[:-4] + '.XML')
            linked_main = [(1, ANNEX1_FORM, main_link(a1_name))]
            if rec.mpz_line_ids:
                linked_main.append((1, ANNEX3_FORM, main_link(a3_name)))
            annex_link = [(2, MAIN_FORM, main_link(main_name))]
            main = rec._render_main(rec._head(MAIN_FORM, linked_main))
            annex1 = rec._render_annex1(rec._head(ANNEX1_FORM, annex_link))
            vals = {
                'xml_file': base64.b64encode(main), 'xml_filename': dps_standard_filename(main),
                'annex1_xml_file': base64.b64encode(annex1), 'annex1_xml_filename': dps_standard_filename(annex1),
                'annex3_xml_file': False, 'annex3_xml_filename': False,
            }
            if rec.mpz_line_ids:
                annex3 = rec._render_annex3(rec._head(ANNEX3_FORM, annex_link))
                vals.update(annex3_xml_file=base64.b64encode(annex3),
                            annex3_xml_filename=dps_standard_filename(annex3))
            rec.write(vals)
        return True

    # ------------------------------------------------- контракт dps.submit.mixin

    def action_submit(self):
        return self.action_kep_submit()

    def _dps_check_can_submit(self):
        for rec in self:
            if rec.state != 'calculated':
                raise UserError(_('Подати можна тільки розраховану декларацію.'))

    def _dps_ensure_xml(self):
        self.ensure_one()
        self.action_generate_xml()

    def _dps_submit_label(self):
        return _('Подати декларацію ЄП 4 групи до ДПС')

    def _annex_files(self):
        return [(name, data, filename) for name, data, filename in (
            ('annex1', self.annex1_xml_file, self.annex1_xml_filename),
            ('annex3', self.annex3_xml_file, self.annex3_xml_filename)) if data]

    def kep_prepare_signing(self):
        spec = super().kep_prepare_signing()
        for name, data, filename in self._annex_files():
            doc = dict(spec['documents'][0])
            doc.update(name=name, data_b64=data.decode() if isinstance(data, bytes) else data, filename=filename)
            spec['documents'].append(doc)
        return spec

    def kep_submit_signed(self, signed, auth_signature=None):
        """Декларація з додатками — одним запитом (кабінет приймає масив звітів)."""
        self.ensure_one()
        annexes = self._annex_files()
        if not annexes:
            return super().kep_submit_signed(signed, auth_signature)
        self._dps_check_can_submit()
        config = self._dps_config()
        if not signed.get('doc') or any(not signed.get(name) for name, _data, _fn in annexes):
            raise UserError(_('Не отримано підпис декларації або додатків.'))
        result = config._api_submit_document_presigned(
            signed['doc'], self._dps_filename(), auth_signature,
            extra_files=[(signed[name], filename) for name, _data, filename in annexes])
        self._dps_check_result(result)
        receipt = self._dps_receipt_text(result)
        self._dps_store_receipts(result)
        self._dps_on_submitted(receipt)
        return {'receipt': receipt}

    def _dps_on_submitted(self, receipt):
        self.write({'state': 'submitted', 'submission_date': fields.Date.context_today(self)})
        self.message_post(body=_('Подано до ДПС. Квитанція: %s') % (receipt or '—'))

    def action_accept(self):
        self.write({'state': 'accepted'})

    def action_draft(self):
        self.write({'state': 'draft'})


class L10nUaTax4DeclarationLine(models.Model):
    _name = 'l10n_ua.tax4.declaration.line'
    _description = 'Рядок розрахунку єдиного податку 4 групи'
    _order = 'declaration_id, land_type, id'

    declaration_id = fields.Many2one('l10n_ua.tax4.declaration', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='declaration_id.currency_id')
    plot_id = fields.Many2one('l10n_ua.agro.land.plot', string='Ділянка', required=True)
    land_type = fields.Selection(LAND_TYPES, string='Вид угідь')
    katottg = fields.Char(string='КАТОТТГ')
    area = fields.Float(string='Площа, га', digits=(16, 4))
    ngo_ha = fields.Monetary(string='НГО 1 га')
    rate = fields.Float(string='Ставка, %', digits=(6, 3))
    annual_tax = fields.Monetary(string='Річна сума')
    q1 = fields.Monetary(string='I кв.')
    q2 = fields.Monetary(string='II кв.')
    q3 = fields.Monetary(string='III кв.')
    q4 = fields.Monetary(string='IV кв.')


class L10nUaTax4MpzLine(models.Model):
    _name = 'l10n_ua.tax4.mpz.line'
    _description = 'Рядок МПЗ (додаток 3) декларації ЄП 4 групи'
    _order = 'declaration_id, id'

    declaration_id = fields.Many2one('l10n_ua.tax4.declaration', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='declaration_id.currency_id')
    plot_id = fields.Many2one('l10n_ua.agro.land.plot', string='Ділянка', required=True)
    own_area = fields.Float(string='Власна, га', digits=(16, 4))
    own_arable = fields.Float(string='Рілля (власна), %', digits=(5, 2))
    leased_area = fields.Float(string='Орендована, га', digits=(16, 4))
    leased_arable = fields.Float(string='Рілля (оренда), %', digits=(5, 2))
    ngo_done = fields.Monetary(string='НГО ділянки (НГОд)')
    ngo_region = fields.Monetary(string='НГО 1 га по області')
    k = fields.Float(string='К', digits=(4, 3))
    months = fields.Integer(string='Місяців')
    mpz_ngo = fields.Monetary(string='МПЗ (НГОд)')
    mpz_region = fields.Monetary(string='МПЗ (НГО області)')
    rent20 = fields.Monetary(string='20 % орендної плати')
