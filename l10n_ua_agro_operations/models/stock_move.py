from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    l10n_ua_agro_work_order_id = fields.Many2one(
        'l10n_ua.agro.work.order', string='Field Work Order', index='btree_not_null',
        readonly=True, copy=False)
    l10n_ua_agro_material_id = fields.Many2one(
        'l10n_ua.agro.work.order.material', readonly=True, copy=False, ondelete='set null')
