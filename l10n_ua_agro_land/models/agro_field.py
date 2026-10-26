from odoo import api, fields, models


class AgroField(models.Model):
    _inherit = 'l10n_ua.agro.field'

    plot_ids = fields.One2many('l10n_ua.agro.land.plot', 'field_id', string='Land Plots')
    plots_area = fields.Float(
        string='Plots Area (ha)', digits=(16, 4), compute='_compute_plots_area',
        help='Сумарна площа земельних ділянок поля за кадастром.')

    @api.depends('plot_ids.area')
    def _compute_plots_area(self):
        for field in self:
            field.plots_area = sum(field.plot_ids.mapped('area'))
