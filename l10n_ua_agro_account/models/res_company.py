from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_agro_valuation_method = fields.Selection([
        ('fair_value', 'Fair Value less Costs to Sell'),
        ('planned_cost', 'Planned Cost'),
    ], string='Harvest Valuation', default='fair_value', required=True,
        help='П(С)БО 30: сільгосппродукція при первісному визнанні — за справедливою вартістю '
             'мінус витрати на місці продажу; якщо її неможливо визначити — за собівартістю '
             '(протягом року за плановою, наприкінці — доведення до фактичної).')
    l10n_ua_agro_produce_account_id = fields.Many2one(
        'account.account', string='Agricultural Produce Account',
        help='27 «Продукція сільськогосподарського виробництва».')
    l10n_ua_agro_recognition_income_account_id = fields.Many2one(
        'account.account', string='Initial Recognition Income Account',
        help='710 «Дохід від первісного визнання та від зміни вартості активів, які '
             'обліковуються за справедливою вартістю».')
    l10n_ua_agro_recognition_expense_account_id = fields.Many2one(
        'account.account', string='Initial Recognition Expense Account',
        help='940 «Витрати від первісного визнання та від зміни вартості активів, які '
             'обліковуються за справедливою вартістю» — сюди закривається собівартість.')
    l10n_ua_agro_overhead_account_id = fields.Many2one(
        'account.account', string='Production Overhead Account',
        help='91 «Загальновиробничі витрати» — розподіляються на посіви в калькуляції.')
