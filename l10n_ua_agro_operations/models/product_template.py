from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ua_agro_material_type = fields.Selection([
        ('seed', 'Seeds and Planting Material'),
        ('fertilizer', 'Fertilizers'),
        ('protection', 'Plant Protection Products'),
        ('fuel', 'Fuel and Lubricants'),
        ('other', 'Other Materials'),
    ], string='Agro Material Type',
        help='Визначає, у який акт потрапляє списання: насіння — ВЗСГ-4, добрива й ЗЗР — ВЗСГ-3.')
    l10n_ua_agro_active_ingredient = fields.Float(
        string='Active Ingredient (%)', digits=(5, 2),
        help='Вміст діючої речовини — для перерахунку в акті ВЗСГ-3.')
