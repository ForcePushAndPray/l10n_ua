from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    l10n_ua_agro_rent_payment_id = fields.Many2one(
        'l10n_ua.agro.rent.payment', string='Land Rent Payment',
        index='btree_not_null', readonly=True, copy=False)
