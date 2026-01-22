from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    marketplace_publish = fields.Boolean(
        string='Publish to Marketplaces',
        default=False,
    )
    marketplace_ids = fields.Many2many(
        'l10n_ua.marketplace.config',
        string='Marketplaces',
        help='Marketplaces where this product is published',
    )
    marketplace_category_ids = fields.Many2many(
        'l10n_ua.marketplace.category',
        string='Marketplace Categories',
    )
    uktzed_code = fields.Char(
        string='UKTZED Code',
        help='Ukrainian Classification of Foreign Economic Activity',
    )
