from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_export_settlement_days = fields.Integer(
        string='Export Settlement Deadline (days)', default=180,
        help='Граничний строк розрахунків за експортом з дати митного оформлення, якщо в договорі '
             'не вказано інший. Чинне значення встановлює НБУ (постанова № 5 від 02.01.2019 зі змінами '
             'воєнного часу) — перевірте актуальний строк.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ua_export_settlement_days = fields.Integer(
        related='company_id.l10n_ua_export_settlement_days', readonly=False)
