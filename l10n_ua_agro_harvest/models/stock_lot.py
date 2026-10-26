from odoo import api, fields, models


class StockLot(models.Model):
    """Партія врожаю: поле й сезон, середньозважена якість за всіма
    оприбуткуваннями (для посвідчення якості й покупця)."""
    _inherit = 'stock.lot'

    l10n_ua_agro_planting_id = fields.Many2one(
        'l10n_ua.agro.planting', string='Planting', index='btree_not_null', readonly=True)
    l10n_ua_agro_field_id = fields.Many2one(related='l10n_ua_agro_planting_id.field_id', string='Field')
    l10n_ua_agro_season_id = fields.Many2one(related='l10n_ua_agro_planting_id.season_id', string='Season')
    l10n_ua_agro_receipt_ids = fields.One2many(
        'l10n_ua.agro.harvest.receipt', 'lot_id', string='Harvest Receipts')
    l10n_ua_agro_credit_weight = fields.Float(
        string='Received (kg)', digits=(16, 1), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_moisture = fields.Float(
        string='Moisture (%)', digits=(5, 2), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_impurity = fields.Float(
        string='Impurity (%)', digits=(5, 2), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_grain_impurity = fields.Float(
        string='Grain Impurity (%)', digits=(5, 2), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_test_weight = fields.Float(
        string='Test Weight (g/l)', digits=(6, 1), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_oil_content = fields.Float(
        string='Oil Content (%)', digits=(5, 2), compute='_compute_l10n_ua_agro_quality')
    l10n_ua_agro_protein = fields.Float(
        string='Protein (%)', digits=(5, 2), compute='_compute_l10n_ua_agro_quality')

    @api.depends('l10n_ua_agro_receipt_ids.state', 'l10n_ua_agro_receipt_ids.credit_weight')
    def _compute_l10n_ua_agro_quality(self):
        indicators = ('moisture', 'impurity', 'grain_impurity', 'test_weight', 'oil_content', 'protein')
        for lot in self:
            receipts = lot.l10n_ua_agro_receipt_ids.filtered(lambda r: r.state == 'done')
            total = sum(receipts.mapped('net_weight'))
            lot.l10n_ua_agro_credit_weight = sum(receipts.mapped('credit_weight'))
            for name in indicators:
                # середнє, зважене за фізичною масою; показник, якого не міряли, не тягне вниз
                measured = receipts.filtered(name)
                weight = sum(measured.mapped('net_weight'))
                lot['l10n_ua_agro_' + name] = sum(
                    r[name] * r.net_weight for r in measured) / weight if total and weight else 0.0
