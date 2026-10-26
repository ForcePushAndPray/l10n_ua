from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_agro_harvest_location_id = fields.Many2one(
        'stock.location', string='Harvest Location',
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (id, False))]",
        help='Склад / тік, куди за замовчуванням оприбутковується врожай.')
