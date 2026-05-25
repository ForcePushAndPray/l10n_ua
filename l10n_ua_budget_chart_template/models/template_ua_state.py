"""Chart template for Ukrainian public sector — Наказ Мінфіну № 1203 від 31.12.2013.

Завантажується через `account.chart_template` API в Odoo 19. Базові коди
відображають субʼєкта сектору «розпорядник бюджетних коштів» (третя цифра = 1).
"""
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('ua_state')
    def _get_ua_state_template_data(self):
        return {
            'name': 'Україна — бухоблік у державному секторі (Наказ № 1203)',
            'code_digits': '4',
            'property_account_receivable_id': 'ua_state_2117',
            'property_account_payable_id': 'ua_state_6614',
            'property_account_expense_categ_id': 'ua_state_8013',
            'property_account_income_categ_id': 'ua_state_7411',
        }

    @template('ua_state', 'res.company')
    def _get_ua_state_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.ua',
                'bank_account_code_prefix': '2313',
                'cash_account_code_prefix': '2411',
                'transfer_account_code_prefix': '2215',
                'income_currency_exchange_account_id': 'ua_state_7411',
                'expense_currency_exchange_account_id': 'ua_state_8411',
            },
        }

    @template('ua_state', 'account.journal')
    def _get_ua_state_account_journal(self):
        return {
            'bank': {'name': 'Реєстраційний рахунок (ДКСУ)', 'type': 'bank', 'code': 'РЕЄ', 'sequence': 5},
            'cash': {'name': 'Каса', 'type': 'cash', 'code': 'КАСА', 'sequence': 10},
            'general': {'name': 'Загальний журнал', 'type': 'general', 'code': 'STJ', 'show_on_dashboard': True},
            'sale': {'name': 'Доходи від платних послуг', 'type': 'sale', 'code': 'ВИКЛ', 'sequence': 20},
            'purchase': {'name': 'Закупівлі', 'type': 'purchase', 'code': 'ЗАКУП', 'sequence': 30},
        }

    @template('ua_state', 'account.account')
    def _get_ua_state_account_account(self):
        """Plan of Accounts for the public sector (Наказ № 1203).

        Identifiers `ua_state_NNNN` map to 4-digit subaccount codes. All
        accounts get `ua_budget_is_state_sector=True` so that the budget
        module's analytic helpers know they belong to this chart.
        """
        # Helper to keep the dict compact
        def acc(code, name, atype):
            return {
                'name': name, 'code': code, 'account_type': atype,
                'ua_budget_is_state_sector': True,
            }

        return {
            # ===== Class 1: Necurrent assets =====
            'ua_state_1014': acc('1014', 'Машини та обладнання', 'asset_non_current'),
            'ua_state_1015': acc('1015', 'Транспортні засоби', 'asset_non_current'),
            'ua_state_1016': acc('1016', 'Інструменти, прилади, інвентар', 'asset_non_current'),
            'ua_state_1018': acc('1018', 'Інші основні засоби', 'asset_non_current'),
            'ua_state_1112': acc('1112', 'Бібліотечні фонди', 'asset_non_current'),
            'ua_state_1113': acc('1113', 'Малоцінні необоротні матеріальні активи', 'asset_non_current'),
            'ua_state_1212': acc('1212', 'Права користування природними ресурсами', 'asset_non_current'),
            'ua_state_1216': acc('1216', 'Інші нематеріальні активи', 'asset_non_current'),
            'ua_state_1311': acc('1311', 'Капітальні інвестиції в основні засоби', 'asset_non_current'),
            'ua_state_1411': acc('1411', 'Знос основних засобів', 'asset_non_current'),
            'ua_state_1412': acc('1412', 'Знос інших необоротних матеріальних активів', 'asset_non_current'),
            'ua_state_1413': acc('1413', 'Накопичена амортизація нематеріальних активів', 'asset_non_current'),

            # ===== Class 2: Financial assets / inventories =====
            'ua_state_2011': acc('2011', 'Сировина і матеріали', 'asset_current'),
            'ua_state_2014': acc('2014', 'Будівельні матеріали', 'asset_current'),
            'ua_state_2015': acc('2015', 'Інші виробничі запаси', 'asset_current'),
            'ua_state_1812': acc('1812', 'Малоцінні та швидкозношувані предмети', 'asset_current'),
            'ua_state_2111': acc('2111', 'Поточна дебіторська заборгованість за товари, роботи, послуги', 'asset_receivable'),
            'ua_state_2113': acc('2113', 'Розрахунки за авансами, виданими постачальникам', 'asset_receivable'),
            'ua_state_2117': acc('2117', 'Інша поточна дебіторська заборгованість', 'asset_receivable'),
            'ua_state_2211': acc('2211', 'Грошові кошти в національній валюті', 'asset_cash'),
            'ua_state_2215': acc('2215', 'Грошові кошти в дорозі в національній валюті', 'asset_cash'),
            'ua_state_2313': acc('2313', 'Реєстраційні рахунки', 'asset_cash'),
            'ua_state_2411': acc('2411', 'Каса в національній валюті', 'asset_cash'),

            # ===== Class 5: Capital =====
            'ua_state_5111': acc('5111', 'Внесений капітал розпорядникам бюджетних коштів', 'equity'),
            'ua_state_5411': acc('5411', 'Цільове фінансування розпорядників бюджетних коштів', 'equity'),
            'ua_state_5511': acc('5511', 'Фінансові результати виконання кошторису звітного періоду', 'equity'),
            'ua_state_5512': acc('5512', 'Накопичені фінансові результати виконання кошторису', 'equity'),

            # ===== Class 6: Liabilities =====
            'ua_state_6211': acc('6211', 'Розрахунки з постачальниками та підрядниками', 'liability_payable'),
            'ua_state_6311': acc('6311', 'Розрахунки з бюджетом за податками і зборами', 'liability_current'),
            'ua_state_6313': acc('6313', "Розрахунки із загальнообов'язкового державного соцстрахування", 'liability_current'),
            'ua_state_6411': acc('6411', 'Розрахунки за коштами, тимчасово віднесеними на доходи держбюджету', 'liability_current'),
            'ua_state_6511': acc('6511', 'Розрахунки із заробітної плати', 'liability_current'),
            'ua_state_6512': acc('6512', 'Розрахунки за виплатами працівникам', 'liability_current'),
            'ua_state_6611': acc('6611', 'Розрахунки з підзвітними особами', 'liability_current'),
            'ua_state_6614': acc('6614', 'Розрахунки з іншими кредиторами', 'liability_payable'),

            # ===== Class 7: Income =====
            'ua_state_7011': acc('7011', 'Бюджетні асигнування', 'income'),
            'ua_state_7111': acc('7111', 'Доходи від реалізації продукції (робіт, послуг)', 'income'),
            'ua_state_7411': acc('7411', "Інші доходи за обмінними операціями", 'income_other'),
            'ua_state_7511': acc('7511', 'Доходи за необмінними операціями', 'income_other'),
            'ua_state_7512': acc('7512', 'Трансферти', 'income_other'),
            'ua_state_7513': acc('7513', 'Гранти, дарунки', 'income_other'),

            # ===== Class 8: Expenses =====
            'ua_state_8011': acc('8011', 'Витрати на оплату праці', 'expense'),
            'ua_state_8012': acc('8012', 'Відрахування на соціальні заходи', 'expense'),
            'ua_state_8013': acc('8013', 'Матеріальні витрати', 'expense'),
            'ua_state_8014': acc('8014', 'Амортизація', 'expense_depreciation'),
            'ua_state_8115': acc('8115', 'Інші витрати', 'expense'),
            'ua_state_8211': acc('8211', 'Собівартість реалізованих активів', 'expense_direct_cost'),
            'ua_state_8411': acc('8411', 'Інші витрати за обмінними операціями', 'expense'),
            'ua_state_8511': acc('8511', "Витрати за необмінними операціями", 'expense'),
            'ua_state_8512': acc('8512', 'Трансферти (видатки)', 'expense'),

            # ===== Off-balance (class 0) =====
            'ua_state_01': acc('0001', 'Орендовані основні засоби', 'off_balance'),
            'ua_state_03': acc('0003', 'Бланки документів суворого обліку', 'off_balance'),
            'ua_state_08': acc('0008', "Бюджетні зобов'язання", 'off_balance'),
        }
