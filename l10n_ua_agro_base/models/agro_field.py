from odoo import api, fields, models

LAND_TYPES = [
    ('arable', 'Arable Land'),
    ('hayfield', 'Hayfields'),
    ('pasture', 'Pastures'),
    ('perennial', 'Perennial Plantings'),
    ('fallow', 'Fallow'),
]


class AgroField(models.Model):
    """Поле — виробнича одиниця сівозміни; складається з земельних ділянок
    (``l10n_ua_agro_land``), але живе й без них."""
    _name = 'l10n_ua.agro.field'
    _description = 'Field'
    _inherit = ['mail.thread']
    _order = 'code, name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(tracking=True)
    active = fields.Boolean(default=True)
    area = fields.Float(string='Area (ha)', digits=(16, 4), required=True, tracking=True)
    land_type = fields.Selection(LAND_TYPES, string='Land Type', required=True, default='arable')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    geojson = fields.Text(
        string='Contour (GeoJSON)',
        help='Контур поля у GeoJSON (WGS84), напр. експорт із Публічної кадастрової карти.')
    planting_ids = fields.One2many('l10n_ua.agro.planting', 'field_id', string='Plantings')
    current_planting_id = fields.Many2one(
        'l10n_ua.agro.planting', string='Current Planting', compute='_compute_current_planting')
    current_crop_id = fields.Many2one(
        'l10n_ua.agro.crop', string='Current Crop', compute='_compute_current_planting')
    note = fields.Html()

    _code_company_uniq = models.Constraint(
        'UNIQUE(code, company_id)',
        'The field code must be unique in the company.',
    )

    @api.depends('planting_ids.season_id.year', 'planting_ids.area')
    def _compute_current_planting(self):
        for field in self:
            planting = field.planting_ids.sorted(
                lambda p: (p.season_id.year, p.area), reverse=True)[:1]
            field.current_planting_id = planting
            field.current_crop_id = planting.crop_id

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for field in self:
            field.display_name = '[%s] %s' % (field.code, field.name) if field.code else field.name
