"""Tests for the 7д / 9д debt forms of the universal budget wizard.

Ці дві форми групують проводки по КЕКВ і фонду, і саме тут агрегація найлегше
ламається непомітно: помилка дає не виняток, а порожню або перекручену таблицю
заборгованості.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ua_budget_reports')
class TestBudgetDebtForms(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.kekv_2111 = cls.env.ref('l10n_ua_budget_base.kekv_2111')
        cls.kekv_2273 = cls.env.ref('l10n_ua_budget_base.kekv_2273')
        cls.kpkvk = cls.env.ref('l10n_ua_budget_base.kpkvk_2201190_2025')
        cls.estimate = cls.env['l10n_ua.budget.estimate'].create({
            'title': 'TEST estimate for debt forms',
            'year': 2025,
            'fund_type': 'both',
            'kpkvk_id': cls.kpkvk.id,
            'line_ids': [
                (0, 0, {'kekv_id': cls.kekv_2111.id, 'fund_type': 'general', 'm01': 1000}),
            ],
        })
        cls.estimate.action_submit()
        cls.estimate.action_approve()

    def _account(self, account_type):
        account = self.env['account.account'].search(
            [('account_type', '=', account_type),
             ('company_ids', 'parent_of', self.company.id)], limit=1)
        self.assertTrue(account, f'No {account_type} account available for test')
        return account

    def _post_entry(self, account_type, kekv, fund_type, debit, credit):
        """Проводка з аналітикою КЕКВ/фонд на рахунку заданого типу."""
        counterpart = self._account('expense' if debit else 'income')
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2025-06-15',
            'company_id': self.company.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self._account(account_type).id,
                    'name': 'debt line',
                    'debit': debit, 'credit': credit,
                    'ua_kekv_id': kekv.id,
                    'ua_fund_type': fund_type,
                }),
                (0, 0, {
                    'account_id': counterpart.id,
                    'name': 'counterpart',
                    'debit': credit, 'credit': debit,
                    'ua_kekv_id': kekv.id,
                    'ua_fund_type': fund_type,
                }),
            ],
        })
        move.action_post()
        return move

    def _wizard(self, form_kind):
        return self.env['l10n_ua.budget.multi_form.wizard'].create({
            'estimate_id': self.estimate.id,
            'form_kind': form_kind,
            'period': 'year',
        })

    def test_payable_debt_groups_by_kekv_and_fund(self):
        """7д: кредитове сальдо по кредиторці потрапляє в рядок свого КЕКВ і фонду."""
        self._post_entry('liability_payable', self.kekv_2111, 'general', debit=0, credit=2500)

        rows = self._wizard('7d').get_report_data()

        matching = [r for r in rows if r['kekv_code'] == self.kekv_2111.code]
        self.assertEqual(len(matching), 1, f'очікували один рядок КЕКВ, маємо: {rows}')
        self.assertEqual(matching[0]['balance'], 2500.0)
        self.assertEqual(matching[0]['fund'], 'Загальний')
        self.assertEqual(matching[0]['kekv_name'], self.kekv_2111.name)

    def test_receivable_debt_uses_opposite_sign(self):
        """9д: дебіторка рахується як дебет мінус кредит, на відміну від 7д."""
        self._post_entry('asset_receivable', self.kekv_2273, 'special', debit=1800, credit=0)

        rows = self._wizard('9d').get_report_data()

        matching = [r for r in rows if r['kekv_code'] == self.kekv_2273.code]
        self.assertEqual(len(matching), 1, f'очікували один рядок КЕКВ, маємо: {rows}')
        self.assertEqual(matching[0]['balance'], 1800.0)
        self.assertEqual(matching[0]['fund'], 'Спеціальний')

    def test_zero_balance_rows_are_dropped(self):
        """Повністю погашена заборгованість не має з'являтись у формі."""
        self._post_entry('liability_payable', self.kekv_2111, 'general', debit=0, credit=1200)
        self._post_entry('liability_payable', self.kekv_2111, 'general', debit=1200, credit=0)

        rows = self._wizard('7d').get_report_data()

        self.assertFalse([r for r in rows if r['kekv_code'] == self.kekv_2111.code])

    def test_execution_by_fund_handles_no_entries(self):
        """Без жодної проводки факт має бути 0.0, а не False чи виняток."""
        rows = self._wizard('2m').get_report_data()

        self.assertTrue(rows, 'кошторис має загальнофондовий рядок')
        self.assertEqual(rows[0]['actual'], 0.0)
        self.assertIsInstance(rows[0]['actual'], float)
