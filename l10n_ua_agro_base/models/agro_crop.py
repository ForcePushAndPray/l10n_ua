from odoo import fields, models

CROP_GROUPS = [
    ('cereal', 'Cereals'),
    ('oilseed', 'Oilseeds'),
    ('legume', 'Legumes'),
    ('industrial', 'Industrial Crops'),
    ('vegetable', 'Vegetables and Melons'),
    ('fodder', 'Fodder Crops'),
    ('perennial', 'Perennial Plantings'),
    ('other', 'Other'),
]


class AgroCrop(models.Model):
    """Культура: довідник для посівів, техкарт і статзвітності."""
    _name = 'l10n_ua.agro.crop'
    _description = 'Crop'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    crop_group = fields.Selection(CROP_GROUPS, string='Crop Group', required=True, default='cereal')
    sowing_type = fields.Selection([
        ('winter', 'Winter'),
        ('spring', 'Spring'),
        ('perennial', 'Perennial'),
    ], string='Sowing Type', required=True, default='spring',
        help='Озимі сіють під урожай наступного року — витрати переходять між сезонами.')
    product_id = fields.Many2one(
        'product.product', string='Main Product',
        help='Основна продукція (зерно, насіння), яку оприбутковують з урожаю.')
    byproduct_id = fields.Many2one(
        'product.product', string='By-product',
        help='Побічна продукція (солома, лушпиння).')
    color = fields.Integer()

    _code_uniq = models.Constraint(
        'UNIQUE(code)',
        'The crop code must be unique.',
    )
