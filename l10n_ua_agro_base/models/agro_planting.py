from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AgroPlanting(models.Model):
    """Посів: культура на полі в сезоні. Одне поле може бути поділене між
    кількома культурами, але сумарна площа не більша за площу поля."""
    _name = 'l10n_ua.agro.planting'
    _description = 'Planting'
    _order = 'season_id desc, field_id, id'

    field_id = fields.Many2one(
        'l10n_ua.agro.field', string='Field', required=True, ondelete='restrict', index=True)
    season_id = fields.Many2one(
        'l10n_ua.agro.season', string='Season', required=True, ondelete='restrict', index=True)
    crop_id = fields.Many2one(
        'l10n_ua.agro.crop', string='Crop', required=True, ondelete='restrict')
    crop_group = fields.Selection(related='crop_id.crop_group', store=True)
    area = fields.Float(string='Sown Area (ha)', digits=(16, 4), required=True)
    variety = fields.Char(string='Variety / Hybrid')
    sowing_date = fields.Date(string='Sowing Date')
    predecessor_crop_id = fields.Many2one(
        'l10n_ua.agro.crop', string='Predecessor',
        compute='_compute_predecessor',
        help='Культура на цьому полі в попередньому сезоні (сівозміна).')
    company_id = fields.Many2one(related='field_id.company_id', store=True)
    land_type = fields.Selection(related='field_id.land_type', store=True)
    note = fields.Text()

    @api.depends('field_id', 'season_id.year')
    def _compute_predecessor(self):
        for planting in self:
            previous = self.search([
                ('field_id', '=', planting.field_id.id),
                ('season_id.year', '<', planting.season_id.year),
            ], order='season_id desc, area desc', limit=1) if planting.field_id and planting.season_id else self
            planting.predecessor_crop_id = previous.crop_id

    @api.depends('field_id', 'crop_id', 'season_id')
    def _compute_display_name(self):
        for planting in self:
            planting.display_name = '%s / %s / %s' % (
                planting.season_id.year or '', planting.field_id.display_name or '',
                planting.crop_id.name or '')

    @api.constrains('area', 'field_id', 'season_id')
    def _check_area(self):
        for planting in self:
            if planting.area <= 0:
                raise ValidationError(self.env._('The sown area must be positive.'))
            sown = sum(self.search([
                ('field_id', '=', planting.field_id.id),
                ('season_id', '=', planting.season_id.id),
            ]).mapped('area'))
            if sown - planting.field_id.area > 0.00005:
                raise ValidationError(self.env._(
                    'The sown area of field %(field)s in %(season)s (%(sown).4f ha) exceeds '
                    'the field area (%(area).4f ha).',
                    field=planting.field_id.display_name, season=planting.season_id.name,
                    sown=sown, area=planting.field_id.area))

    @api.onchange('field_id', 'season_id')
    def _onchange_field_area(self):
        if self.field_id and not self.area:
            self.area = self.field_id.area
