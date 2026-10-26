from odoo import fields, models

WORK_UNITS = [
    ('ha', 'ha'),
    ('t', 't'),
    ('hour', 'hours'),
    ('km', 'km'),
    ('trip', 'trips'),
]


class AgroOperationType(models.Model):
    """Вид польової роботи з розцінкою механізатора і нормою пального."""
    _name = 'l10n_ua.agro.operation.type'
    _description = 'Field Operation'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ('tillage', 'Tillage'),
        ('sowing', 'Sowing'),
        ('fertilizing', 'Fertilizing'),
        ('protection', 'Plant Protection'),
        ('harvest', 'Harvest'),
        ('transport', 'Transport'),
        ('other', 'Other'),
    ], required=True, default='tillage')
    unit = fields.Selection(WORK_UNITS, string='Unit of Work', required=True, default='ha')
    piece_rate = fields.Float(
        string='Piece Rate', digits='Product Price',
        help='Розцінка механізатора за одиницю роботи, грн.')
    fuel_norm = fields.Float(
        string='Fuel Norm', digits=(10, 2),
        help='Норма витрати пального на одиницю роботи, л.')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _code_uniq = models.Constraint(
        'UNIQUE(code, company_id)',
        'The operation code must be unique.',
    )
