"""Книга обліку доходів ФОП заповнюється сама — з банківських виписок.

Кожне надходження на рахунок ФОП (будь-який банківський журнал компанії) стає
записом книги свого кварталу:

* дохід — як є (у гривнях);
* валюта — у гривнях за курсом НБУ на дату надходження на валютний рахунок
  (п. 292.15 ПКУ), курс і сума у валюті зберігаються в записі;
* продаж валюти, повернення, власні перекази, зняття готівки — записом
  «не дохід» із причиною: їх видно в книзі, але в суму вони не входять.
  Користувач може перемкнути «Дохід» вручну — автоматика цього не перезапише.

Коли: одразу після надходження рядка виписки (імпорт, синхронізація з банком),
щодня кроном (догнати пропущене) і кнопкою «Заповнити з банку». Підтверджена
книга не змінюється — про нове надходження в ній з'являється повідомлення.
"""

import logging
import re
from datetime import date

import requests

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

NBU_URL = 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange'
_NBU_CACHE = {}

# Банки пишуть українські слова з латинськими «i», «e», «o»… — до порівняння
# зводимо все до кирилиці.
_HOMOGLYPHS = str.maketrans('ieaopcxykmht', 'іеаорсхукмнт')

# (причина, шаблон) — перевіряються призначення платежу й назва платника.
NOT_INCOME_RULES = [
    ('currency_sale', 'Гривня від продажу валюти — дохід уже враховано при надходженні валюти',
     re.compile(r'гривн[іи]\s+в[іи]д\s+продажу')),
    ('refund', 'Повернення коштів',
     re.compile(r'^\s*поверн|повернення')),
    ('own_transfer', 'Переказ власних коштів',
     re.compile(r'власн[а-я]*\s+кошт|м[іи]ж\s+власними\s+рахунками')),
    ('cash', 'Зняття готівки',
     re.compile(r'видача\s+готівки')),
]


def _normalize(text):
    return (text or '').lower().translate(_HOMOGLYPHS)


def classify_bank_income(payment_ref, partner_name):
    """None — це дохід; інакше (код, пояснення) — чому не дохід."""
    text = '%s\n%s' % (_normalize(payment_ref), _normalize(partner_name))
    for code, label, pattern in NOT_INCOME_RULES:
        if pattern.search(text):
            return code, label
    return None


def quarter_of(day):
    return str((day.month - 1) // 3 + 1)


class L10nUaFopIncomeBookLine(models.Model):
    _inherit = 'l10n_ua.fop.income.book.line'

    is_income = fields.Boolean(
        string='Дохід', default=True,
        help='Знято — запис лишається в книзі для звірки з випискою, але в дохід '
             'кварталу не входить (продаж валюти, повернення, власний переказ).')
    not_income_reason = fields.Char(string='Чому не дохід')
    original_amount = fields.Float(string='Сума у валюті', digits=(16, 2))
    original_currency_id = fields.Many2one('res.currency', string='Валюта')
    nbu_rate = fields.Float(string='Курс НБУ', digits=(12, 4))

    _unique_bank_line = models.Constraint(
        'UNIQUE(bank_statement_line_id)',
        'Цей рядок виписки вже записано в книгу доходів.',
    )


class L10nUaFopIncomeBook(models.Model):
    _inherit = 'l10n_ua.fop.income.book'

    @api.depends('line_ids.amount', 'line_ids.is_income')
    def _compute_totals(self):
        for rec in self:
            income = rec.line_ids.filtered('is_income')
            rec.total_income = sum(income.mapped('amount'))
            rec.line_count = len(income)

    # --- заповнення ---

    def action_fill_from_bank(self):
        self.ensure_one()
        added = self._fill_from_bank()
        message = self._compare_with_declaration()
        if message:
            self.message_post(body=message)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Додано записів з виписок: %s.') % added + (
                    ' ' + message if message else ''),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _quarter_bounds(self):
        self.ensure_one()
        first_month = (int(self.quarter) - 1) * 3 + 1
        start = date(self.year, first_month, 1)
        end = date(self.year + (first_month == 10), (first_month + 2) % 12 + 1, 1)
        return start, end

    def _fill_from_bank(self):
        """Дописати ще не записані надходження кварталу; повертає кількість."""
        added = 0
        for book in self.filtered(lambda b: b.state == 'draft'):
            start, end = book._quarter_bounds()
            lines = self.env['account.bank.statement.line'].sudo().search([
                ('company_id', '=', book.company_id.id),
                ('journal_id.type', '=', 'bank'),
                ('amount', '>', 0),
                ('date', '>=', start),
                ('date', '<', end),
            ], order='date, id')
            added += book._add_bank_lines(lines)
        return added

    def _add_bank_lines(self, st_lines):
        self.ensure_one()
        BookLine = self.env['l10n_ua.fop.income.book.line'].sudo()
        known = set(BookLine.search([
            ('bank_statement_line_id', 'in', st_lines.ids)]).mapped('bank_statement_line_id').ids)
        company_currency = self.company_id.currency_id
        vals_list = []
        for st_line in st_lines:
            if st_line.id in known:
                continue
            currency = st_line.journal_id.currency_id or company_currency
            vals = {
                'book_id': self.id,
                'date': st_line.date,
                'document_number': (st_line.move_id.name or '')[:64],
                'description': (st_line.payment_ref or st_line.partner_name or '')[:250],
                'partner_id': st_line.partner_id.id,
                'income_type': 'bank',
                'bank_statement_line_id': st_line.id,
            }
            if currency == company_currency:
                vals['amount'] = st_line.amount
            else:
                rate = self._l10n_ua_nbu_rate(currency, st_line.date)
                if not rate:
                    # Без курсу не записуємо — спробуємо наступного разу.
                    continue
                vals.update(amount=round(st_line.amount * rate, 2),
                            original_amount=st_line.amount,
                            original_currency_id=currency.id, nbu_rate=rate)
            reason = classify_bank_income(st_line.payment_ref, st_line.partner_name)
            if reason:
                vals.update(is_income=False, not_income_reason=reason[1])
            vals_list.append(vals)
        if vals_list:
            BookLine.create(vals_list)
        return len(vals_list)

    @api.model
    def _l10n_ua_nbu_rate(self, currency, day):
        """Офіційний курс НБУ (гривень за одиницю валюти) на дату."""
        key = (currency.name, day)
        if key in _NBU_CACHE:
            return _NBU_CACHE[key]
        rate = 0.0
        try:
            response = requests.get(NBU_URL, params={
                'valcode': currency.name, 'date': day.strftime('%Y%m%d'), 'json': ''},
                timeout=15)
            response.raise_for_status()
            data = response.json()
            rate = float(data[0]['rate']) if data else 0.0
        except Exception as e:  # noqa: BLE001 — без мережі беремо курс з Odoo
            _logger.warning("NBU rate %s %s unavailable: %s", currency.name, day, e)
        if not rate:
            # Курс саме на цю дату в довіднику Odoo (його туди пише синхронізація НБУ).
            odoo_rate = self.env['res.currency.rate'].sudo().search([
                ('currency_id', '=', currency.id), ('name', '=', day)], limit=1)
            rate = 1 / odoo_rate.rate if odoo_rate.rate else 0.0
        if rate:
            _NBU_CACHE[key] = rate
        return rate

    # --- автоматика ---

    @api.model
    def _book_for(self, company, day):
        """Книга кварталу дати; чернетку створюємо, якщо її ще немає."""
        group = self._company_fop_group(company)
        if not group:
            return self.browse()
        domain = [('company_id', '=', company.id), ('year', '=', day.year),
                  ('quarter', '=', quarter_of(day)), ('fop_group_id', '=', group.id)]
        book = self.sudo().search(domain, limit=1)
        if not book:
            book = self.sudo().create({
                'company_id': company.id, 'year': day.year,
                'quarter': quarter_of(day), 'fop_group_id': group.id})
        return book

    @api.model
    def _company_fop_group(self, company):
        code = company.l10n_ua_fop_group
        if code == '3' and company.l10n_ua_is_vat_payer:
            code = '3_vat'
        return self.env['l10n_ua.fop.group'].sudo().search([('code', '=', code)], limit=1)

    @api.model
    def _autofill_bank_lines(self, st_lines):
        """Нові надходження → книги їхніх кварталів (виклик з виписки)."""
        st_lines = st_lines.filtered(
            lambda l: l.amount > 0 and l.company_id.l10n_ua_is_fop
            and l.journal_id.type == 'bank')
        by_book = {}
        for st_line in st_lines:
            book = self._book_for(st_line.company_id, st_line.date)
            if book:
                by_book.setdefault(book, self.env['account.bank.statement.line'])
                by_book[book] |= st_line
        for book, lines in by_book.items():
            if book.state == 'draft':
                book._add_bank_lines(lines)
            else:
                book.message_post(body=_(
                    'Після підтвердження книги на рахунок надійшло ще %s платіж(і). '
                    'Поверніть книгу в чернетку й натисніть «Заповнити з банку», '
                    'щоб їх урахувати.') % len(lines))

    @api.model
    def _cron_fill_from_bank(self):
        """Догнати пропущене: поточний і попередній квартал кожного ФОП."""
        today = fields.Date.context_today(self)
        prev = date(today.year - (today.month <= 3), ((today.month - 1) // 3 * 3 - 3) % 12 + 1, 1)
        for company in self.env['res.company'].sudo().search([('l10n_ua_is_fop', '=', True)]):
            for day in (prev, today):
                book = self._book_for(company, day)
                if book:
                    book._fill_from_bank()

    @api.model
    def _backfill_all(self):
        """Книги за всі квартали, де є надходження на рахунки ФОП (перше встановлення)."""
        Line = self.env['account.bank.statement.line'].sudo()
        for company in self.env['res.company'].sudo().search([('l10n_ua_is_fop', '=', True)]):
            days = Line.search([('company_id', '=', company.id), ('amount', '>', 0),
                                ('journal_id.type', '=', 'bank')]).mapped('date')
            for year, quarter in sorted({(d.year, quarter_of(d)) for d in days}):
                book = self._book_for(company, date(year, (int(quarter) - 1) * 3 + 1, 1))
                if book:
                    book._fill_from_bank()
                    message = book._compare_with_declaration()
                    if message:
                        book.message_post(body=message)

    def _compare_with_declaration(self):
        """Звірка з поданою (прийнятою) декларацією, що закінчується цим кварталом."""
        self.ensure_one()
        period = {'1': 'q1', '2': 'h1', '3': '9m', '4': 'year'}[self.quarter]
        declaration = self.env['l10n_ua.fop.declaration'].sudo().search([
            ('company_id', '=', self.company_id.id), ('year', '=', self.year),
            ('period', '=', period), ('fop_group_id', '=', self.fop_group_id.id),
            ('state', 'in', ('submitted', 'accepted'))], limit=1)
        if not declaration:
            return ''
        books = self.search([
            ('company_id', '=', self.company_id.id), ('year', '=', self.year),
            ('fop_group_id', '=', self.fop_group_id.id),
            ('quarter', 'in', [str(q) for q in range(1, int(self.quarter) + 1)])])
        total = sum(books.mapped('total_income'))
        declared = declaration.total_income
        if abs(total - declared) < 0.01:
            return _('Дохід з початку року за книгами (%(total).2f) збігається з поданою '
                     'декларацією «%(decl)s».', total=total, decl=declaration.name)
        return _('Дохід з початку року за книгами — %(total).2f, у поданій декларації '
                 '«%(decl)s» — %(declared).2f: різниця %(diff).2f. Перевірте записи '
                 '«не дохід» і надходження поза банком.', total=total,
                 decl=declaration.name, declared=declared, diff=total - declared)


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        incoming = lines.filtered(lambda l: l.amount > 0 and l.company_id.l10n_ua_is_fop)
        if incoming:
            try:
                with self.env.cr.savepoint():
                    self.env['l10n_ua.fop.income.book']._autofill_bank_lines(incoming)
            except Exception:  # noqa: BLE001 — книга не має зривати імпорт виписки
                _logger.exception("Книга доходів: не вдалося записати надходження %s", incoming.ids)
        return lines
