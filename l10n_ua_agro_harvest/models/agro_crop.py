from odoo import fields, models


class AgroCrop(models.Model):
    _inherit = 'l10n_ua.agro.crop'

    base_moisture = fields.Float(
        string='Base Moisture (%)', digits=(5, 2),
        help='Базисна вологість (ДСТУ / договір): понад неї маса зменшується за формулою Дюваля.')
    base_impurity = fields.Float(
        string='Base Impurity (%)', digits=(5, 2),
        help='Базисна смітна домішка.')
