from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_agro_in_kind_vat_included = fields.Boolean(
        string='VAT Included in the In-kind Rent', default=True,
        help='Увімкнено: вартість виданої продукції включає ПДВ (ПДВ виділяється, Дт 712 — Кт 641). '
             'Вимкнено: ПДВ нараховується зверху й відноситься до витрат (Дт 94 — Кт 641).')
    l10n_ua_agro_in_kind_vat_expense_account_id = fields.Many2one(
        'account.account', string='In-kind Rent VAT Expense Account',
        help='Рахунок витрат на ПДВ, нарахований зверху вартості натуроплати (94).')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ua_agro_in_kind_vat_included = fields.Boolean(
        related='company_id.l10n_ua_agro_in_kind_vat_included', readonly=False)
    l10n_ua_agro_in_kind_vat_expense_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_in_kind_vat_expense_account_id', readonly=False)
