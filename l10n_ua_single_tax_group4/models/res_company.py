from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_tax4_expense_account_id = fields.Many2one(
        'account.account', string='Рахунок витрат на ЄП 4 групи',
        help='23 — у собівартість рослинництва (розподіл калькуляцією), або 92.')
    l10n_ua_tax4_payable_account_id = fields.Many2one(
        'account.account', string='Рахунок розрахунків за ЄП 4 групи',
        help='641 «Розрахунки за податками».')
    l10n_ua_tax4_region_ngo = fields.Monetary(
        string='НГО 1 га ріллі по області',
        help='Для мінімального податкового зобов\'язання за ділянками, НГО яких не проведена '
             '(пп. 381.1.2 ПКУ), з урахуванням індексації.')
