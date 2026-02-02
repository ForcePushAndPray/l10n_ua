"""Company settings for Ukrainian accounting: payment approval, cash limit."""

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_payment_approval_enabled = fields.Boolean(
        string='Затвердження платежів',
        default=False,
        help='Увімкнути вимогу затвердження платежів вище порогу',
    )
    l10n_ua_payment_approval_threshold = fields.Monetary(
        string='Поріг затвердження',
        default=50000,
        currency_field='currency_id',
        help='Платежі на суму більше цього порогу потребують затвердження головного бухгалтера',
    )

    # --- Cash limit control ---
    l10n_ua_cash_limit_enabled = fields.Boolean(
        string='Контроль ліміту каси',
        default=False,
        help='Увімкнути контроль залишку каси на кінець робочого дня',
    )
    l10n_ua_cash_limit = fields.Monetary(
        string='Ліміт каси',
        default=10000,
        currency_field='currency_id',
        help='Максимально допустимий залишок готівки в касі на кінець робочого дня',
    )
