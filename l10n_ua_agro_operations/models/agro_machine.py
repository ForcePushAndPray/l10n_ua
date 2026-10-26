from odoo import fields, models


class AgroMachine(models.Model):
    """Сільгосптехніка: трактор, комбайн, обприскувач, автомобіль."""
    _name = 'l10n_ua.agro.machine'
    _description = 'Agricultural Machine'
    _order = 'machine_type, name'

    name = fields.Char(required=True)
    code = fields.Char(string='Garage Number')
    active = fields.Boolean(default=True)
    machine_type = fields.Selection([
        ('tractor', 'Tractor'),
        ('combine', 'Combine Harvester'),
        ('sprayer', 'Sprayer'),
        ('truck', 'Truck'),
        ('implement', 'Implement'),
        ('other', 'Other'),
    ], string='Type', required=True, default='tractor')
    license_plate = fields.Char(string='Registration Number')
    fuel_product_id = fields.Many2one(
        'product.product', string='Fuel',
        help='Пальне, яке списується за нарядами цієї техніки.')
    fuel_factor = fields.Float(
        string='Fuel Norm Factor', default=1.0, digits=(5, 2),
        help='Коефіцієнт до норми витрати пального операції для цієї машини.')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    def _compute_display_name(self):
        for machine in self:
            machine.display_name = '[%s] %s' % (machine.code, machine.name) if machine.code else machine.name
