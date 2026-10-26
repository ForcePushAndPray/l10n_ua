from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AgroSeason(models.Model):
    """Сезон = рік урожаю. Посіви, роботи й урожай прив'язані до сезону."""
    _name = 'l10n_ua.agro.season'
    _description = 'Agricultural Season'
    _order = 'year desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False)
    year = fields.Integer(
        string='Harvest Year', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)
    state = fields.Selection([
        ('planning', 'Planning'),
        ('sowing', 'Sowing'),
        ('harvest', 'Harvest'),
        ('closed', 'Closed'),
    ], default='planning', required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    planting_ids = fields.One2many('l10n_ua.agro.planting', 'season_id', string='Plantings')
    sown_area = fields.Float(
        string='Sown Area (ha)', digits=(16, 4), compute='_compute_sown_area')

    _year_company_uniq = models.Constraint(
        'UNIQUE(year, company_id)',
        'A season for this harvest year already exists in the company.',
    )

    @api.depends('year')
    def _compute_name(self):
        for season in self:
            if season.year:
                season.name = self.env._('Season %s', season.year)

    @api.onchange('year')
    def _onchange_year(self):
        # сезон охоплює озимі, посіяні восени попереднього року
        if self.year:
            self.date_start = fields.Date.to_date('%s-08-01' % (self.year - 1))
            self.date_end = fields.Date.to_date('%s-12-31' % self.year)

    @api.depends('planting_ids.area')
    def _compute_sown_area(self):
        for season in self:
            season.sown_area = sum(season.planting_ids.mapped('area'))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for season in self:
            if season.date_start > season.date_end:
                raise ValidationError(self.env._('The season cannot end before it starts.'))

    def action_start_sowing(self):
        self.write({'state': 'sowing'})

    def action_start_harvest(self):
        self.write({'state': 'harvest'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reopen(self):
        self.write({'state': 'planning'})
