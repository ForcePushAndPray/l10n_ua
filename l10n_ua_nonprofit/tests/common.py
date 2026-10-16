"""Shared setup for the non-profit tests (#374).

Accounts are found or created here (48x, 718, 732, 92, 311, 631, 79x, 44x),
so the tests run the same with or without a chart of accounts installed.
"""

from datetime import date

from odoo.tests import TransactionCase


class NonprofitTestCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.country_id = cls.env.ref('base.ua')
        cls.company.fiscalyear_lock_date = False
        cls.acc_48 = cls._account('483', 'Благодійна допомога', 'liability_non_current')
        cls.acc_718 = cls._account('718', 'Дохід від безоплатно одержаних оборотних активів', 'income_other')
        cls.acc_732 = cls._account('732', 'Відсотки одержані', 'income_other')
        cls.acc_92 = cls._account('92', 'Адміністративні витрати', 'expense')
        cls.acc_311 = cls._account('311', 'Поточні рахунки в національній валюті', 'asset_cash')
        cls.acc_631 = cls._account('631', 'Розрахунки з постачальниками', 'liability_payable')
        cls.acc_791 = cls._account('791', 'Результат операційної діяльності', 'equity')
        cls.acc_792 = cls._account('792', 'Результат фінансових операцій', 'equity')
        cls.acc_793 = cls._account('793', 'Результат іншої діяльності', 'equity')
        cls.acc_441 = cls._account('441', 'Прибуток нерозподілений', 'equity')
        cls.acc_442 = cls._account('442', 'Непокриті збитки', 'equity')

        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', cls.company.id),
        ], limit=1) or cls.env['account.journal'].create({
            'name': 'Різне (тест)',
            'code': 'MISCT',
            'type': 'general',
            'company_id': cls.company.id,
        })
        cls.company.write({
            'l10n_ua_is_nonprofit': True,
            'l10n_ua_nonprofit_code': '0036',
            'l10n_ua_nonprofit_register_date': date(2020, 3, 2),
            'l10n_ua_nonprofit_register_number': '1234567890',
            'l10n_ua_npo_target_account_id': cls.acc_48.id,
            'l10n_ua_npo_income_account_id': cls.acc_718.id,
            'l10n_ua_npo_journal_id': cls.journal.id,
            'l10n_ua_npo_expense_prefixes': '9',
            'l10n_ua_npo_recognise_on_closing': True,
        })
        cls.donor = cls.env['res.partner'].create({
            'name': 'Міжнародний фонд (тест)',
            'company_type': 'company',
        })
        cls.supplier = cls.env['res.partner'].create({
            'name': 'Постачальник (тест)',
            'company_type': 'company',
        })
        Program = cls.env['l10n_ua.npo.program']
        cls.program = Program.create({
            'name': 'Грант «Чиста вода»',
            'code': 'T-WATER',
            'funding_type': 'charity',
            'partner_id': cls.donor.id,
            'budget_amount': 20000.0,
            'expense_row': '2.4.1',
        })
        cls.program.action_activate()
        cls.membership = Program.create({
            'name': 'Членські внески',
            'code': 'T-MEMBER',
            'funding_type': 'membership',
        })
        cls.membership.action_activate()

    @classmethod
    def _account(cls, code, name, account_type):
        Account = cls.env['account.account']
        account = Account.search([
            ('code', '=', code), ('company_ids', 'in', cls.company.id)], limit=1)
        return account or Account.create({
            'code': code,
            'name': name,
            'account_type': account_type,
            'company_ids': [(6, 0, cls.company.ids)],
            'reconcile': account_type == 'liability_payable',
        })

    def _distribution(self, *programs_pct):
        return {str(program.analytic_account_id.id): pct for program, pct in programs_pct}

    def _entry(self, on_date, debit_account, credit_account, amount,
               debit_distribution=None, credit_distribution=None, partner=None):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal.id,
            'date': on_date,
            'line_ids': [
                (0, 0, {'account_id': debit_account.id, 'debit': amount,
                        'partner_id': partner and partner.id,
                        'analytic_distribution': debit_distribution}),
                (0, 0, {'account_id': credit_account.id, 'credit': amount,
                        'partner_id': partner and partner.id,
                        'analytic_distribution': credit_distribution}),
            ],
        })
        move.action_post()
        return move

    def _receipt(self, program, on_date, amount):
        """Дт 311 – Кт 48 (program)."""
        return self._entry(on_date, self.acc_311, self.acc_48, amount,
                           credit_distribution=self._distribution((program, 100.0)),
                           partner=program.partner_id or self.donor)

    def _expense(self, program, on_date, amount, distribution=None):
        """Дт 92 (program) – Кт 631."""
        return self._entry(on_date, self.acc_92, self.acc_631, amount,
                           debit_distribution=distribution
                           or (program and self._distribution((program, 100.0))),
                           partner=self.supplier)

    def _recognition(self, on_date, programs=None):
        recognition = self.env['l10n_ua.npo.recognition'].create({
            'date': on_date,
            'program_ids': [(6, 0, programs.ids)] if programs else False,
        })
        recognition.action_compute()
        return recognition

    def _period(self, year, month, last_day):
        return self.env['l10n_ua.tax.period'].create({
            'period_type': 'month',
            'date_start': date(year, month, 1),
            'date_end': date(year, month, last_day),
            'company_id': self.company.id,
        })

    def _closing(self, period):
        return self.env['l10n_ua.period.closing'].create({
            'period_id': period.id,
            'company_id': self.company.id,
            'journal_id': self.journal.id,
            'account_791_id': self.acc_791.id,
            'account_792_id': self.acc_792.id,
            'account_793_id': self.acc_793.id,
            'account_profit_id': self.acc_441.id,
            'account_loss_id': self.acc_442.id,
        })
