"""Книга обліку доходів заповнюється з банківських виписок сама.

Призначення платежів — як у реальних виписках ПриватБанку (з латинськими «i»).
"""

from datetime import date
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models import l10n_ua_fop_income_autofill as autofill
from ..models.l10n_ua_fop_income_autofill import classify_bank_income


@tagged('post_install', '-at_install')
class TestIncomeBookAutofill(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        fop_form = cls.env['l10n_ua.legal.form'].search([('is_fop', '=', True)], limit=1)
        cls.company.write({'l10n_ua_legal_form_id': fop_form.id, 'l10n_ua_fop_group': '3',
                           'l10n_ua_is_vat_payer': False})
        Group = cls.env['l10n_ua.fop.group']
        cls.group_3 = Group.search([('code', '=', '3')]) or Group.create(
            {'code': '3', 'name': '3 група', 'tax_rate': 5.0, 'limit_min_wages': 1167})
        # Валюта рахунку — будь-яка, крім валюти компанії (курс НБУ підмінено).
        cls.eur = cls.env.ref('base.EUR')
        if cls.eur == cls.company.currency_id:
            cls.eur = cls.env.ref('base.USD')
        cls.eur.active = True
        Journal = cls.env['account.journal']
        cls.uah_journal = Journal.create({'name': 'Приват, грн', 'type': 'bank', 'code': 'TPU'})
        cls.eur_journal = Journal.create({'name': 'Приват, валюта', 'type': 'bank', 'code': 'TPE',
                                          'currency_id': cls.eur.id})
        autofill._NBU_CACHE.clear()

    def setUp(self):
        super().setUp()
        autofill._NBU_CACHE.clear()

    def _line(self, journal, day, amount, ref, partner_name=''):
        return self.env['account.bank.statement.line'].create({
            'journal_id': journal.id, 'date': day, 'amount': amount,
            'payment_ref': ref, 'partner_name': partner_name})

    def _book(self, year, quarter):
        return self.env['l10n_ua.fop.income.book'].search([
            ('company_id', '=', self.company.id), ('year', '=', year), ('quarter', '=', quarter)])

    def test_classification(self):
        self.assertEqual(classify_bank_income(
            'Гривнi вiд продажу 476.19 EUR по курсу 51.46', 'Продаж UAH клiєнтiв')[0], 'currency_sale')
        self.assertEqual(classify_bank_income(
            'повeрн ЕП 15.01.2022 №1 Вiдсутнiй номер картки', '')[0], 'refund')
        self.assertEqual(classify_bank_income(
            'ВИДАЧА ГОТIВКИ З БАНКОМАТУ 15.05.2024', 'Розрахунок VISA')[0], 'cash')
        self.assertIsNone(classify_bank_income(
            'За розробку ПЗ за березень 2026р. згiдно дог. без ПДВ', 'ТОВ "КЛIК САППОРТ"'))
        self.assertIsNone(classify_bank_income(
            '5169 **** **** 8706 22.03.2026 Зарахування: ABNK, Dnipro', 'P2P Credit Fust Fund'))

    def test_incoming_lines_land_in_quarter_book(self):
        self._line(self.uah_journal, date(2026, 3, 20), 222426.08,
                   'За розробку ПЗ за березень 2026р. без ПДВ', 'ТОВ "КЛIК САППОРТ"')
        self._line(self.uah_journal, date(2026, 3, 22), 4000.0,
                   'Зарахування: ABNK, Dnipro', 'P2P Credit Fust Fund')
        self._line(self.uah_journal, date(2026, 3, 25), -5000.0, 'Сплата ЄП')  # видаток — не в книгу
        self._line(self.uah_journal, date(2026, 4, 22), 24504.74,
                   'Гривнi вiд продажу 476.19 EUR по курсу 51.46', 'Продаж UAH клiєнтiв')
        q1, q2 = self._book(2026, '1'), self._book(2026, '2')
        self.assertEqual(q1.state, 'draft')
        self.assertEqual(q1.fop_group_id, self.group_3)
        self.assertEqual(len(q1.line_ids), 2)
        self.assertAlmostEqual(q1.total_income, 226426.08)
        sale = q2.line_ids
        self.assertFalse(sale.is_income)
        self.assertIn('продажу валюти', sale.not_income_reason)
        self.assertEqual(q2.total_income, 0.0)

    def test_foreign_currency_at_nbu_rate(self):
        with patch.object(autofill.requests, 'get') as get:
            get.return_value.json.return_value = [{'rate': 51.9113, 'cc': 'EUR'}]
            self._line(self.eur_journal, date(2026, 4, 22), 475.29,
                       'From ODOO for PPC/BEL004/BEFORE 01/04/2026', 'НАДОЗIРНИЙ С. В. ФОП')
        line = self._book(2026, '2').line_ids
        self.assertTrue(line.is_income)
        self.assertEqual(line.original_amount, 475.29)
        self.assertEqual(line.original_currency_id, self.eur)
        self.assertEqual(line.nbu_rate, 51.9113)
        self.assertEqual(line.amount, 24672.92)  # саме так у поданій декларації за півріччя
        self.assertEqual(get.call_args.kwargs['params']['date'], '20260422')

    def test_no_rate_means_retry_later(self):
        # Ні НБУ, ні курсу саме на цю дату в Odoo — запис чекає наступного разу.
        self.env['res.currency.rate'].search([
            ('currency_id', '=', self.eur.id), ('name', '=', date(2026, 4, 22))]).unlink()
        with patch.object(autofill.requests, 'get', side_effect=OSError('offline')):
            self._line(self.eur_journal, date(2026, 4, 22), 475.29, 'From ODOO')
        book = self._book(2026, '2')
        self.assertFalse(book.line_ids)
        with patch.object(autofill.requests, 'get') as get:
            get.return_value.json.return_value = [{'rate': 51.9113}]
            book._fill_from_bank()
        self.assertEqual(book.line_ids.amount, 24672.92)

    def test_odoo_rate_when_nbu_is_down(self):
        self.env['res.currency.rate'].search([
            ('currency_id', '=', self.eur.id), ('name', '=', date(2026, 4, 22))]).unlink()
        self.env['res.currency.rate'].create({
            'currency_id': self.eur.id, 'name': date(2026, 4, 22),
            'rate': 1 / 51.9113, 'company_id': self.company.id})
        with patch.object(autofill.requests, 'get', side_effect=OSError('offline')):
            self._line(self.eur_journal, date(2026, 4, 22), 475.29, 'From ODOO')
        self.assertEqual(self._book(2026, '2').line_ids.amount, 24672.92)

    def test_fill_is_idempotent_and_respects_manual_choice(self):
        self._line(self.uah_journal, date(2026, 3, 22), 5700.0, 'Зарахування', 'P2P Credit')
        book = self._book(2026, '1')
        book.line_ids.is_income = False  # користувач вирішив, що це не дохід
        book._fill_from_bank()
        book._fill_from_bank()
        self.assertEqual(len(book.line_ids), 1)
        self.assertFalse(book.line_ids.is_income)

    def test_confirmed_book_is_not_changed(self):
        self._line(self.uah_journal, date(2026, 3, 20), 1000.0, 'Оплата послуг')
        book = self._book(2026, '1')
        book.action_confirm()
        self._line(self.uah_journal, date(2026, 3, 21), 2000.0, 'Оплата послуг')
        self.assertEqual(len(book.line_ids), 1)
        self.assertIn('Після підтвердження', book.message_ids[0].body)

    def test_backfill_and_compare_with_declaration(self):
        # Рядки, що існували до встановлення: без автозаповнення.
        with patch.object(type(self.env['l10n_ua.fop.income.book']), '_autofill_bank_lines'):
            self._line(self.uah_journal, date(2025, 2, 13), 40850.0, 'Сплата за IТ послугу')
            self._line(self.uah_journal, date(2025, 3, 12), 38000.0, 'Сплата за IТ послугу')
        self.env['l10n_ua.fop.declaration'].create({
            'year': 2025, 'period': 'q1', 'fop_group_id': self.group_3.id,
            'company_id': self.company.id, 'total_income': 78850.0, 'state': 'accepted'})
        self.env['l10n_ua.fop.income.book']._backfill_all()
        book = self._book(2025, '1')
        self.assertEqual(book.total_income, 78850.0)
        self.assertIn('збігається', book.message_ids[0].body)

    def test_cron_runs(self):
        self.env['l10n_ua.fop.income.book']._cron_fill_from_bank()
