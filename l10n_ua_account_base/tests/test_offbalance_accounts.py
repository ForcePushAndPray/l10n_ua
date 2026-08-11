"""Клас 0 «Позабалансові рахунки» має доїжджати разом зі стоковим планом ua_psbo.

Тест піднімає окрему компанію і вантажить на неї план явно: у чистій тестовій
базі компанія лишається на `generic_coa`, тож без цього перевірялося б що
завгодно, тільки не український план.
"""
from odoo.tests import TransactionCase, tagged

from ..models.template_ua_psbo import OFFBALANCE_ACCOUNTS


# Odoo доповнює коди нулями до `code_digits` плану (для ua_psbo це 6), тож
# рахунок 01 живе в базі як 010000 — рівно як стоковий 631 як 631000. Очікувані
# коди виводимо з довжини, а не хардкодимо, щоб тест не зламався при її зміні.
CODE_DIGITS = 6
OFFBALANCE_CODES = sorted(code.ljust(CODE_DIGITS, '0')
                           for code, _name, _analytics in OFFBALANCE_ACCOUNTS)
PARTNER_ANALYTICS_CODES = [code.ljust(CODE_DIGITS, '0')
                            for code, _name, analytics in OFFBALANCE_ACCOUNTS
                            if analytics == 'partner']


@tagged('post_install', '-at_install', 'l10n_ua_account_base')
class TestOffBalanceAccounts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({
            'name': 'ТОВ Позабаланс Тест',
            'country_id': cls.env.ref('base.ua').id,
        })
        cls.env['account.chart.template'].try_loading(
            'ua_psbo', company=cls.company, install_demo=False)
        cls.env.user.company_ids |= cls.company

    def _accounts(self, codes):
        return self.env['account.account'].with_company(self.company).search(
            [('code', 'in', codes),
             ('company_ids', 'parent_of', self.company.id)])

    def test_all_nine_offbalance_accounts_loaded(self):
        found = self._accounts(OFFBALANCE_CODES)
        self.assertEqual(
            sorted(found.mapped('code')), OFFBALANCE_CODES,
            'план має містити всі 9 позабалансових рахунків Наказу № 291')

    def test_offbalance_accounts_have_correct_type(self):
        accounts = self._accounts(OFFBALANCE_CODES)
        self.assertTrue(accounts)
        for account in accounts:
            self.assertEqual(account.account_type, 'off_balance',
                              f'рахунок {account.code} має бути позабалансовим')
            self.assertFalse(account.reconcile,
                              f'рахунок {account.code} не звіряється')
            self.assertEqual(account.ua_class, '0')

    def test_stock_chart_is_not_replaced(self):
        """Наш шаблон додає рахунки, а не заміщує стокові 332.

        Перевіряємо за конкретними кодами зі стокового `l10n_ua`, а не за
        обчисленим `ua_class`: клас рахується з першої цифри коду, тож на
        generic-плані він дав би ті самі «класи» і тест зеленів би дарма.
        """
        Account = self.env['account.account'].with_company(self.company)
        for prefix in ('631', '661', '311', '281'):
            found = Account.search([('code', '=like', f'{prefix}%'),
                                     ('company_ids', 'parent_of', self.company.id)])
            self.assertTrue(found, f'стоковий рахунок {prefix} зник з плану')

    def test_partner_analytics_where_counterparty_matters(self):
        for account in self._accounts(PARTNER_ANALYTICS_CODES):
            self.assertEqual(account.ua_analytics_type, 'partner',
                              f'рахунок {account.code} має аналітику за контрагентом')

    def test_offbalance_entry_must_still_balance(self):
        """Odoo вимагає балансу навіть на позабалансових рахунках.

        У 1С запис на клас 0 односторонній. Odoo такого не вміє: `_check_balanced`
        застосовується до будь-якої проводки, тож орендоване майно ведеться парою
        рахунків класу 0. Тест фіксує обмеження, щоб воно не з'їхало непоміченим.
        """
        rented = self._accounts(['010000'])
        contra = self._accounts(['090000'])
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1)
        self.assertTrue(journal, 'план рахунків має створити загальний журнал')

        move = self.env['account.move'].with_company(self.company).create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'line_ids': [
                (0, 0, {'account_id': rented.id, 'name': 'орендоване обладнання',
                        'debit': 15000.0, 'credit': 0.0}),
                (0, 0, {'account_id': contra.id, 'name': 'контрзапис',
                        'debit': 0.0, 'credit': 15000.0}),
            ],
        })
        move.action_post()

        self.assertEqual(move.state, 'posted')

    def test_hook_backfills_existing_company(self):
        """Компанії, яким план дістався до встановлення модуля, добираються хуком.

        Це не теоретичний випадок, а звичайний: шаблон матеріалізується один раз,
        коли на компанію ставиться локалізація, тож у будь-якій наявній базі
        `l10n_ua` стоїть раніше за цей модуль і нових рахунків там не буде.
        """
        from ..hooks import post_init_hook

        self._accounts(OFFBALANCE_CODES).unlink()
        self.assertFalse(self._accounts(OFFBALANCE_CODES))

        post_init_hook(self.env)

        self.assertEqual(sorted(self._accounts(OFFBALANCE_CODES).mapped('code')),
                          OFFBALANCE_CODES)
        self.assertEqual(self._accounts(['050000']).ua_analytics_type, 'partner')

    def test_hook_is_idempotent(self):
        from ..hooks import post_init_hook

        post_init_hook(self.env)
        post_init_hook(self.env)

        self.assertEqual(len(self._accounts(['010000'])), 1,
                          'повторний запуск хука не має дублювати рахунки')
