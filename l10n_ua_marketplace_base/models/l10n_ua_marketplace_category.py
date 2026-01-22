from odoo import api, fields, models


class L10nUaMarketplaceCategory(models.Model):
    _name = 'l10n_ua.marketplace.category'
    _description = 'Marketplace Category Mapping'
    _order = 'marketplace_type, name'

    name = fields.Char(
        string='Marketplace Category',
        required=True,
    )
    marketplace_type = fields.Selection(
        selection=[
            ('rozetka', 'Rozetka'),
            ('prom', 'Prom.ua'),
        ],
        string='Marketplace',
        required=True,
    )
    external_id = fields.Char(
        string='External ID',
        help='Category ID in marketplace system',
    )
    odoo_category_id = fields.Many2one(
        'product.category',
        string='Odoo Category',
    )
    parent_id = fields.Many2one(
        'l10n_ua.marketplace.category',
        string='Parent Category',
    )
    child_ids = fields.One2many(
        'l10n_ua.marketplace.category',
        'parent_id',
        string='Child Categories',
    )
    active = fields.Boolean(
        default=True,
    )

    _sql_constraints = [
        ('external_id_marketplace_uniq', 'unique(external_id, marketplace_type)',
         'External ID must be unique per marketplace!'),
    ]
