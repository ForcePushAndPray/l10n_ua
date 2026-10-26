from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ua_agro_calculation_id = fields.Many2one(
        'l10n_ua.agro.cost.calculation', string='Crop Cost Calculation',
        index='btree_not_null', readonly=True, copy=False)
