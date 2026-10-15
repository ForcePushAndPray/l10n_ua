"""Target financing of a non-profit organization — issue #374."""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import NonprofitTestCase


@tagged('post_install', '-at_install', 'l10n_ua_nonprofit')
class TestNonprofitProgram(NonprofitTestCase):

    def test_program_owns_analytic_account(self):
        analytic = self.program.analytic_account_id
        self.assertTrue(analytic)
        self.assertEqual(
            analytic.plan_id, self.env.ref('l10n_ua_nonprofit.analytic_plan_npo_programs'))
        self.assertEqual(analytic.company_id, self.company)
        self.assertEqual(analytic.partner_id, self.donor)
        self.program.name = 'Грант «Чиста вода» 2035'
        self.assertEqual(analytic.name, 'Грант «Чиста вода» 2035')
        self.assertEqual(self.program.income_row, '1.6.1')
        self.assertEqual(self.membership.income_row, '1.7')
        self.assertEqual(self.program.account_id, self.acc_48)
        self.assertEqual(self.program.income_account_id, self.acc_718)

    def test_program_with_entries_cannot_be_deleted(self):
        self._receipt(self.program, date(2035, 1, 10), 100.0)
        with self.assertRaises(UserError):
            self.program.unlink()

    def test_donation_and_expense_figures(self):
        self._receipt(self.program, date(2035, 1, 10), 10000.0)
        self._expense(self.program, date(2035, 1, 20), 4000.0)
        self._expense(False, date(2035, 1, 21), 999.0)   # not the program's
        figures = self.program._get_ledger_figures(date(2035, 1, 31))[self.program.id]
        self.assertEqual(figures['received'], 10000.0)
        self.assertEqual(figures['spent'], 4000.0)
        self.assertEqual(figures['recognised'], 0.0)
        self.assertEqual(figures['transferred'], 0.0)
        program = self.program.with_context(l10n_ua_npo_date=date(2035, 1, 31))
        program.invalidate_recordset()
        self.assertEqual(program.amount_received, 10000.0)
        self.assertEqual(program.amount_spent, 4000.0)
        self.assertEqual(program.amount_balance, 10000.0)
        self.assertEqual(program.amount_unrecognised, 4000.0)
        self.assertEqual(program.budget_remaining, 16000.0)

    def test_split_analytic_distribution(self):
        self._receipt(self.program, date(2035, 1, 5), 1000.0)
        self._receipt(self.membership, date(2035, 1, 5), 1000.0)
        self._expense(False, date(2035, 1, 6), 600.0, distribution=self._distribution(
            (self.program, 50.0), (self.membership, 50.0)))
        figures = (self.program | self.membership)._get_ledger_figures(date(2035, 1, 31))
        self.assertEqual(figures[self.program.id]['spent'], 300.0)
        self.assertEqual(figures[self.membership.id]['spent'], 300.0)


@tagged('post_install', '-at_install', 'l10n_ua_nonprofit')
class TestNonprofitRecognition(NonprofitTestCase):

    def test_recognition_equals_expenses(self):
        self._receipt(self.program, date(2035, 2, 3), 10000.0)
        self._expense(self.program, date(2035, 2, 14), 4000.0)
        recognition = self._recognition(date(2035, 2, 28))
        line = recognition.line_ids.filtered(lambda l: l.program_id == self.program)
        self.assertEqual(line.amount, 4000.0)
        self.assertEqual(line.expense_total, 4000.0)
        self.assertEqual(line.balance_available, 10000.0)
        recognition.action_post()
        self.assertEqual(recognition.state, 'posted')
        move = recognition.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.date, date(2035, 2, 28))
        debit = move.line_ids.filtered(lambda l: l.account_id == self.acc_48)
        credit = move.line_ids.filtered(lambda l: l.account_id == self.acc_718)
        self.assertEqual(debit.debit, 4000.0)
        self.assertEqual(credit.credit, 4000.0)
        analytic_key = str(self.program.analytic_account_id.id)
        self.assertEqual(debit.analytic_distribution, {analytic_key: 100.0})
        self.assertEqual(credit.analytic_distribution, {analytic_key: 100.0})

        figures = self.program._get_ledger_figures(date(2035, 2, 28))[self.program.id]
        self.assertEqual(figures['recognised'], 4000.0)
        self.assertEqual(figures['transferred'], 4000.0)
        self.assertEqual(figures['received'], 10000.0)

        # Nothing left to recognise: a second recognition is refused.
        again = self._recognition(date(2035, 2, 28))
        self.assertFalse(any(again.line_ids.mapped('amount')))
        with self.assertRaises(UserError):
            again.action_post()

    def test_recognition_capped_by_balance_and_caught_up(self):
        self._receipt(self.program, date(2035, 3, 1), 1000.0)
        self._expense(self.program, date(2035, 3, 10), 1500.0)
        march = self._recognition(date(2035, 3, 31), self.program)
        self.assertEqual(march.line_ids.amount, 1000.0)
        march.action_post()
        figures = self.program._get_ledger_figures(date(2035, 3, 31))[self.program.id]
        self.assertEqual(
            figures['received'] - figures['other_debit'] - figures['transferred'], 0.0)
        # New money in April covers the 500 left uncovered in March.
        self._receipt(self.program, date(2035, 4, 2), 2000.0)
        april = self._recognition(date(2035, 4, 30), self.program)
        self.assertEqual(april.line_ids.amount, 500.0)
        self.assertEqual(april.line_ids.recognised_before, 1000.0)

    def test_negative_recognition_after_expense_credit(self):
        self._receipt(self.program, date(2035, 5, 2), 5000.0)
        self._expense(self.program, date(2035, 5, 10), 1000.0)
        self._recognition(date(2035, 5, 31)).action_post()
        # The supplier refunds 300 of the expense.
        self._entry(date(2035, 6, 5), self.acc_631, self.acc_92, 300.0,
                    credit_distribution=self._distribution((self.program, 100.0)))
        june = self._recognition(date(2035, 6, 30), self.program)
        self.assertEqual(june.line_ids.amount, -300.0)
        june.action_post()
        back = june.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_48)
        self.assertEqual(back.credit, 300.0)
        figures = self.program._get_ledger_figures(date(2035, 6, 30))[self.program.id]
        self.assertEqual(figures['recognised'], 700.0)
        self.assertEqual(figures['spent'], 700.0)

    def test_cancel_reverses_and_allows_recompute(self):
        self._receipt(self.program, date(2035, 7, 1), 800.0)
        self._expense(self.program, date(2035, 7, 2), 800.0)
        recognition = self._recognition(date(2035, 7, 31))
        recognition.action_post()
        recognition.action_cancel()
        self.assertEqual(recognition.state, 'cancelled')
        self.assertTrue(self.env['account.move'].search_count([
            ('reversed_entry_id', '=', recognition.move_id.id)]))
        figures = self.program._get_ledger_figures(date(2035, 7, 31))[self.program.id]
        self.assertEqual(figures['recognised'], 0.0)
        self.assertEqual(figures['received'], 800.0)
        recognition.action_draft()
        recognition.action_compute()
        self.assertEqual(recognition.line_ids.amount, 800.0)


@tagged('post_install', '-at_install', 'l10n_ua_nonprofit')
class TestNonprofitPeriodClosing(NonprofitTestCase):

    def test_closing_recognises_target_income(self):
        period = self._period(2035, 8, 31)
        self._receipt(self.program, date(2035, 8, 4), 10000.0)
        self._expense(self.program, date(2035, 8, 18), 4000.0)
        closing = self._closing(period)
        closing.action_close()
        self.assertEqual(closing.state, 'closed')
        recognition = closing.npo_recognition_ids
        self.assertEqual(len(recognition), 1)
        self.assertEqual(recognition.state, 'posted')
        self.assertEqual(recognition.amount_total, 4000.0)
        self.assertEqual(recognition.date, date(2035, 8, 31))
        # The recognised income is closed together with the expense: 718 and
        # 92 cancel out in the financial result of the month.
        by_account = {line.account_id: line for line in closing.closing_line_ids}
        self.assertEqual(by_account[self.acc_718].balance, 4000.0)
        self.assertEqual(by_account[self.acc_92].balance, 4000.0)
        self.assertEqual(closing.net_result, 0.0)

        # Idempotent: running the pre-closing step again posts nothing new.
        closing._post_deferral_entries()
        self.assertEqual(len(closing.npo_recognition_ids), 1)
        self.assertEqual(
            self.env['l10n_ua.npo.recognition'].search_count([('closing_id', '=', closing.id)]), 1)

        # Reversing the closing reverses the recognition.
        closing.action_reverse()
        self.assertEqual(recognition.state, 'cancelled')
        figures = self.program._get_ledger_figures(date(2035, 8, 31))[self.program.id]
        self.assertEqual(figures['recognised'], 0.0)

        # Closed again, the month is recognised again with the same amount.
        closing.action_draft()
        closing.action_close()
        posted = closing.npo_recognition_ids.filtered(lambda r: r.state == 'posted')
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted.amount_total, 4000.0)
        figures = self.program._get_ledger_figures(date(2035, 8, 31))[self.program.id]
        self.assertEqual(figures['recognised'], 4000.0)

    def test_closing_of_profit_company_does_nothing(self):
        self.company.l10n_ua_is_nonprofit = False
        period = self._period(2035, 9, 30)
        self._receipt(self.program, date(2035, 9, 4), 1000.0)
        self._expense(self.program, date(2035, 9, 5), 1000.0)
        closing = self._closing(period)
        closing.action_close()
        self.assertFalse(closing.npo_recognition_ids)

    def test_closing_without_program_expenses_creates_no_recognition(self):
        period = self._period(2035, 10, 31)
        self._receipt(self.program, date(2035, 10, 4), 1000.0)
        self._expense(False, date(2035, 10, 5), 200.0)
        closing = self._closing(period)
        closing.action_close()
        self.assertFalse(closing.npo_recognition_ids)


@tagged('post_install', '-at_install', 'l10n_ua_nonprofit')
class TestNonprofitReports(NonprofitTestCase):

    def _year_data(self):
        """A year of a charity: one grant, membership fees, interest."""
        self._receipt(self.program, date(2036, 3, 2), 10000.0)
        self._expense(self.program, date(2036, 3, 15), 4000.0)
        self._receipt(self.membership, date(2036, 3, 3), 3000.0)
        self._expense(self.membership, date(2036, 3, 16), 3000.0)
        # Bank interest — passive income, no program.
        self._entry(date(2036, 3, 20), self.acc_311, self.acc_732, 500.0)
        # Expense of the organization outside programs.
        self._expense(False, date(2036, 3, 25), 200.0)
        # Income is recognised by closing March; the closing entries must not
        # disturb the annual figures.
        closing = self._closing(self._period(2036, 3, 31))
        closing.action_close()
        return closing

    def test_annual_report_figures(self):
        self._year_data()
        report = self.env['l10n_ua.npo.income.report'].create({'year': 2036})
        self.assertEqual(report.date_from, date(2036, 1, 1))
        self.assertEqual(report.date_to, date(2036, 12, 31))
        report.action_compute()
        self.assertEqual(report.r1_6_1, 4000.0)
        self.assertEqual(report.r1_6, 4000.0)
        self.assertEqual(report.r1_7, 3000.0)
        self.assertEqual(report.r1_9, 500.0)
        self.assertEqual(report.r1, 7500.0)
        self.assertEqual(report.r2_4_1, 4000.0)
        self.assertEqual(report.r2_4, 4000.0)
        self.assertEqual(report.r2_3, 3200.0)
        self.assertEqual(report.r2, 7200.0)
        self.assertEqual(report.r5, 0.0)
        self.assertFalse(report.has_annex_hd)
        rows = {(l.row, l.program_id): l.amount for l in report.line_ids}
        self.assertEqual(rows[('1.6.1', self.program)], 4000.0)
        self.assertEqual(rows[('1.9', self.env['l10n_ua.npo.program'])], 500.0)
        self.assertEqual(report.company_edrpou, report.company_id.edrpou
                         or report.company_id.company_registry
                         or report.company_id.partner_id.edrpou or '')

    def test_monthly_report_period_and_part2(self):
        report = self.env['l10n_ua.npo.income.report'].create({
            'year': 2036, 'period_type': 'month', 'month': '5',
            'report_kind': 'clarifying',
        })
        self.assertEqual(report.date_from, date(2036, 1, 1))
        self.assertEqual(report.date_to, date(2036, 5, 31))
        report.write({'r3_2': 1000.0, 'r4': 500.0, 'r7': 100.0})
        self.assertEqual(report.r3, 1000.0)
        self.assertEqual(report.r5, 1500.0)
        self.assertEqual(report.r6, 270.0)
        self.assertEqual(report.r10, 3.0)

    def test_report_rendering(self):
        self._year_data()
        report = self.env['l10n_ua.npo.income.report'].create({'year': 2036})
        report.action_compute()
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_nonprofit.report_npo_income_document', report.ids)
        html = html.decode()
        self.assertIn('про використання доходів (прибутків)', html)
        self.assertIn('0036', html)
        self.assertIn('1.6.1', html)
        self.assertIn('4 000.00', html)
        self.assertIn('7 500.00', html)

    def test_program_report(self):
        self._year_data()
        wizard = self.env['l10n_ua.npo.program.report'].create({
            'date_from': date(2036, 3, 1),
            'date_to': date(2036, 3, 31),
        })
        wizard.action_compute()
        line = wizard.line_ids.filtered(lambda l: l.program_id == self.program)
        self.assertEqual(line.opening_balance, 0.0)
        self.assertEqual(line.received, 10000.0)
        self.assertEqual(line.recognised, 4000.0)
        self.assertEqual(line.spent, 4000.0)
        self.assertEqual(line.closing_balance, 6000.0)
        self.assertEqual(line.uncovered, 0.0)
        self.assertEqual(line.budget_used, 20.0)
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_nonprofit.report_npo_program_document', wizard.ids)
        self.assertIn('Грант', html.decode())
        # Next month opens with the closing balance.
        april = self.env['l10n_ua.npo.program.report'].create({
            'date_from': date(2036, 4, 1),
            'date_to': date(2036, 4, 30),
            'program_ids': [(6, 0, self.program.ids)],
        })
        april.action_compute()
        self.assertEqual(april.line_ids.opening_balance, 6000.0)


@tagged('post_install', '-at_install', 'l10n_ua_nonprofit')
class TestNonprofitSetup(NonprofitTestCase):

    def test_setup_finds_accounts_and_creates_journal(self):
        self.company.write({
            'l10n_ua_npo_target_account_id': False,
            'l10n_ua_npo_income_account_id': False,
            'l10n_ua_npo_journal_id': False,
        })
        self.company.action_l10n_ua_npo_setup()
        self.assertTrue(self.company.l10n_ua_is_nonprofit)
        self.assertEqual(self.company.l10n_ua_npo_target_account_id, self.acc_48)
        self.assertEqual(self.company.l10n_ua_npo_income_account_id, self.acc_718)
        self.assertEqual(self.company.l10n_ua_npo_journal_id.code, 'NPO')

    def test_expense_prefixes_validated(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.company.l10n_ua_npo_expense_prefixes = '7'
        self.company.l10n_ua_npo_expense_prefixes = '8, 9'
        self.assertEqual(self.company._l10n_ua_npo_expense_prefixes(), ('8', '9'))
