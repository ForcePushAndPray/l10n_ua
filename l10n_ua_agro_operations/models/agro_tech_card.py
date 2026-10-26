from odoo import api, fields, models

from .agro_operation_type import WORK_UNITS


class AgroTechCard(models.Model):
    """Технологічна карта культури на сезон: план операцій і норм внесення
    на 1 га; планова собівартість на гектар і на всю посівну площу."""
    _name = 'l10n_ua.agro.tech.card'
    _description = 'Technological Card'
    _inherit = ['mail.thread']
    _order = 'season_id desc, crop_id'

    name = fields.Char(required=True, tracking=True)
    crop_id = fields.Many2one('l10n_ua.agro.crop', string='Crop', required=True, tracking=True)
    season_id = fields.Many2one('l10n_ua.agro.season', string='Season', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    active = fields.Boolean(default=True)
    operation_ids = fields.One2many(
        'l10n_ua.agro.tech.card.operation', 'card_id', string='Operations', copy=True)
    material_ids = fields.One2many(
        'l10n_ua.agro.tech.card.material', 'card_id', string='Materials', copy=True)
    planting_ids = fields.Many2many(
        'l10n_ua.agro.planting', string='Plantings', compute='_compute_plantings',
        help='Посіви культури в сезоні, до яких застосовується карта.')
    area = fields.Float(string='Area (ha)', digits=(16, 4), compute='_compute_plantings')
    material_cost_ha = fields.Monetary(string='Materials per ha', compute='_compute_costs')
    operation_cost_ha = fields.Monetary(string='Operations per ha', compute='_compute_costs')
    cost_ha = fields.Monetary(string='Planned Cost per ha', compute='_compute_costs')
    cost_total = fields.Monetary(string='Planned Cost', compute='_compute_costs')
    note = fields.Html()

    _crop_season_uniq = models.Constraint(
        'UNIQUE(crop_id, season_id, company_id)',
        'A technological card for this crop and season already exists.',
    )

    @api.depends('crop_id', 'season_id')
    def _compute_plantings(self):
        Planting = self.env['l10n_ua.agro.planting']
        for card in self:
            plantings = Planting.search([
                ('crop_id', '=', card.crop_id.id),
                ('season_id', '=', card.season_id.id),
                ('company_id', '=', card.company_id.id),
            ]) if card.crop_id and card.season_id else Planting
            card.planting_ids = plantings
            card.area = sum(plantings.mapped('area'))

    @api.depends('operation_ids.cost_ha', 'material_ids.cost_ha', 'area')
    def _compute_costs(self):
        for card in self:
            card.material_cost_ha = sum(card.material_ids.mapped('cost_ha'))
            card.operation_cost_ha = sum(card.operation_ids.mapped('cost_ha'))
            card.cost_ha = card.material_cost_ha + card.operation_cost_ha
            card.cost_total = card.cost_ha * card.area

    @api.onchange('crop_id', 'season_id')
    def _onchange_name(self):
        if self.crop_id and self.season_id and not self.name:
            self.name = '%s — %s' % (self.crop_id.name, self.season_id.name)


class AgroTechCardOperation(models.Model):
    _name = 'l10n_ua.agro.tech.card.operation'
    _description = 'Technological Card Operation'
    _order = 'card_id, sequence, id'

    card_id = fields.Many2one('l10n_ua.agro.tech.card', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    operation_type_id = fields.Many2one(
        'l10n_ua.agro.operation.type', string='Operation', required=True)
    unit = fields.Selection(related='operation_type_id.unit')
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')
    volume_ha = fields.Float(
        string='Volume per ha', default=1.0, digits=(10, 3),
        help='Обсяг роботи на 1 га посіву: 1 — один прохід по площі; для перевезень — т/га.')
    currency_id = fields.Many2one(related='card_id.currency_id')
    cost_ha = fields.Monetary(
        string='Cost per ha', compute='_compute_cost_ha', store=True, readonly=False,
        help='Планові витрати на операцію на 1 га: оплата праці й пальне за нормою; можна змінити.')

    @api.depends('operation_type_id', 'volume_ha')
    def _compute_cost_ha(self):
        for line in self:
            operation = line.operation_type_id
            fuel_price = self.env['l10n_ua.agro.work.order']._default_fuel_product().standard_price
            line.cost_ha = line.volume_ha * (operation.piece_rate + operation.fuel_norm * fuel_price)


class AgroTechCardMaterial(models.Model):
    _name = 'l10n_ua.agro.tech.card.material'
    _description = 'Technological Card Material'
    _order = 'card_id, sequence, id'

    card_id = fields.Many2one('l10n_ua.agro.tech.card', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    operation_type_id = fields.Many2one(
        'l10n_ua.agro.operation.type', string='Operation',
        help='Операція, під час якої вносять матеріал: тоді наряд цієї операції підтягне його сам.')
    product_id = fields.Many2one('product.product', string='Material', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id')
    rate_ha = fields.Float(string='Rate per ha', digits=(12, 4), required=True)
    currency_id = fields.Many2one(related='card_id.currency_id')
    price_unit = fields.Monetary(
        string='Price', compute='_compute_price_unit', store=True, readonly=False)
    cost_ha = fields.Monetary(string='Cost per ha', compute='_compute_cost_ha', store=True)

    @api.depends('product_id')
    def _compute_price_unit(self):
        for line in self:
            line.price_unit = line.product_id.standard_price

    @api.depends('rate_ha', 'price_unit')
    def _compute_cost_ha(self):
        for line in self:
            line.cost_ha = line.rate_ha * line.price_unit
