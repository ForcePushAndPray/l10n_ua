from odoo import api, fields, models


class AgroPlanting(models.Model):
    _inherit = 'l10n_ua.agro.planting'

    harvest_receipt_ids = fields.One2many(
        'l10n_ua.agro.harvest.receipt', 'planting_id', string='Harvest Receipts')
    harvest_weight = fields.Float(
        string='Harvested (t)', digits=(16, 3), compute='_compute_harvest', store=True,
        help='Валовий збір у заліковій масі.')
    harvest_yield = fields.Float(
        string='Yield (c/ha)', digits=(10, 2), compute='_compute_harvest', store=True,
        aggregator='avg', help='Урожайність, ц/га, у заліковій масі.')

    @api.depends('harvest_receipt_ids.state', 'harvest_receipt_ids.credit_weight', 'area')
    def _compute_harvest(self):
        for planting in self:
            kg = sum(planting.harvest_receipt_ids.filtered(
                lambda r: r.state == 'done').mapped('credit_weight'))
            planting.harvest_weight = kg / 1000.0
            planting.harvest_yield = kg / 100.0 / planting.area if planting.area else 0.0
