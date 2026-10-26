"""Спільне налаштування тестів оренди паїв (#470).

Рахунки шукаються або створюються тут (23, 685, 6411, 642, 712, 301), тож
тести працюють однаково з планом рахунків і без нього.
"""

from datetime import date

from odoo.tests import TransactionCase


class AgroLandTestCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.fiscalyear_lock_date = False
        cls.acc_23 = cls._account('231', 'Основне виробництво', 'asset_current')
        cls.acc_685 = cls._account('685', 'Розрахунки з іншими кредиторами', 'liability_payable')
        cls.acc_6411 = cls._account('6411', 'Розрахунки за ПДФО', 'liability_payable')
        cls.acc_642 = cls._account('642', 'Розрахунки з обов\'язкових платежів', 'liability_payable')
        cls.acc_712 = cls._account('712', 'Дохід від реалізації інших оборотних активів', 'income_other')
        cls.acc_301 = cls._account('301', 'Каса в національній валюті', 'asset_cash')
        cls.journal = cls.env['account.journal'].create({
            'name': 'Оренда землі (тест)', 'code': 'RENTT', 'type': 'general',
            'company_id': cls.company.id})
        cls.cash = cls.env['account.journal'].create({
            'name': 'Каса (тест)', 'code': 'CSHT', 'type': 'cash',
            'company_id': cls.company.id, 'default_account_id': cls.acc_301.id})
        cls.company.write({
            'l10n_ua_agro_rent_journal_id': cls.journal.id,
            'l10n_ua_agro_rent_expense_account_id': cls.acc_23.id,
            'l10n_ua_agro_rent_payable_account_id': cls.acc_685.id,
            'l10n_ua_agro_pdfo_account_id': cls.acc_6411.id,
            'l10n_ua_agro_military_account_id': cls.acc_642.id,
            'l10n_ua_agro_in_kind_income_account_id': cls.acc_712.id,
        })
        Partner = cls.env['res.partner']
        cls.lessor = Partner.create({'name': 'Коваль Марія Іванівна', 'ipn': '3124567896'})
        cls.lessor2 = Partner.create({'name': 'Ткачук Петро Олексійович', 'ipn': '2987654320'})
        cls.lessor_company = Partner.create({'name': 'ТОВ «Земля» (тест)', 'is_company': True})
        Plot = cls.env['l10n_ua.agro.land.plot']
        cls.plot1 = Plot.create({
            'cadastral_number': '5621684800:01:001:0101', 'area': 2.5,
            'ngo_value': 80000.0, 'owner_id': cls.lessor.id, 'katottg': 'UA56040170010076211'})
        cls.plot2 = Plot.create({
            'cadastral_number': '5621684800:01:001:0102', 'area': 3.0,
            'ngo_value': 100000.0, 'owner_id': cls.lessor2.id, 'katottg': 'UA56040170010076211'})
        cls.plot3 = Plot.create({
            'cadastral_number': '5621684800:01:001:0103', 'area': 10.0,
            'ngo_value': 300000.0, 'owner_id': cls.lessor_company.id})

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

    def _lease(self, lessor, plots, date_start=date(2095, 1, 1), percent=12.0, **vals):
        lease = self.env['l10n_ua.agro.land.lease'].create(dict({
            'name': 'L-%s' % plots[0].cadastral_number[-4:],
            'lessor_id': lessor.id,
            'plot_ids': [(6, 0, plots.ids)],
            'date_start': date_start,
            'term_years': 10,
            'rent_method': 'ngo_percent',
            'rent_percent': percent,
        }, **vals))
        lease.action_activate()
        return lease

    def _accrual(self, date_from=date(2096, 1, 1), date_to=date(2096, 12, 31)):
        accrual = self.env['l10n_ua.agro.rent.accrual'].create({
            'date': date_to, 'date_from': date_from, 'date_to': date_to})
        accrual.action_compute()
        return accrual
