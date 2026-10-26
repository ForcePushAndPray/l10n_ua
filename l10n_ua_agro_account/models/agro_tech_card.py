from odoo import api, fields, models


class AgroTechCard(models.Model):
    _inherit = 'l10n_ua.agro.tech.card'

    planned_yield = fields.Float(
        string='Planned Yield (c/ha)', digits=(10, 2), tracking=True,
        help='Планова урожайність основної продукції, ц/га.')
    planned_unit_cost = fields.Float(
        string='Planned Cost per kg', digits=(12, 4), compute='_compute_planned_unit_cost',
        help='Планові витрати на 1 га / планова урожайність — для оцінки врожаю за плановою собівартістю.')

    @api.depends('cost_ha', 'planned_yield')
    def _compute_planned_unit_cost(self):
        for card in self:
            card.planned_unit_cost = card.cost_ha / (card.planned_yield * 100.0) if card.planned_yield else 0.0
