import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.l10n_ua_agro_base.models.agro_field import LAND_TYPES

# КОАТУУ(10):зона(2):квартал(3):ділянка(4) — Порядок ведення ДЗК, пост. КМУ № 1051
CADASTRAL_RE = re.compile(r'^\d{10}:\d{2}:\d{3}:\d{4}$')


class AgroLandPlot(models.Model):
    """Земельна ділянка з Державного земельного кадастру."""
    _name = 'l10n_ua.agro.land.plot'
    _description = 'Land Plot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'cadastral_number'
    _order = 'cadastral_number'

    cadastral_number = fields.Char(
        string='Cadastral Number', required=True, tracking=True, index='trigram',
        help='Формат 0000000000:00:000:0000.')
    active = fields.Boolean(default=True)
    area = fields.Float(string='Area (ha)', digits=(16, 4), required=True, tracking=True)
    land_type = fields.Selection(LAND_TYPES, string='Land Type', required=True, default='arable')
    purpose_code = fields.Char(
        string='Purpose Code',
        help='Код цільового призначення за КВЦПЗ, напр. 01.01 — для ведення товарного '
             'сільськогосподарського виробництва.')
    ownership = fields.Selection([
        ('private', 'Private (leased)'),
        ('state', 'State-owned'),
        ('communal', 'Communal'),
        ('company', 'Owned by the Company'),
    ], string='Ownership', required=True, default='private', tracking=True)
    owner_id = fields.Many2one(
        'res.partner', string='Owner', tracking=True,
        help='Власник паю (фізособа) або розпорядник землі державної/комунальної власності.')
    ngo_value = fields.Monetary(
        string='Normative Monetary Valuation', tracking=True,
        help='Нормативна грошова оцінка ділянки (НГО) з урахуванням індексації.')
    ngo_date = fields.Date(string='Valuation Date')
    katottg = fields.Char(
        string='KATOTTG',
        help='Код громади, на території якої розташована ділянка: ПДФО з орендної плати '
             'сплачується за місцезнаходженням ділянки.')
    location = fields.Char(string='Location')
    field_id = fields.Many2one('l10n_ua.agro.field', string='Field', index=True, tracking=True)
    lease_ids = fields.Many2many(
        'l10n_ua.agro.land.lease', 'l10n_ua_agro_land_lease_plot_rel', 'plot_id', 'lease_id',
        string='Leases')
    current_lease_id = fields.Many2one(
        'l10n_ua.agro.land.lease', string='Current Lease', compute='_compute_current_lease')
    use_state = fields.Selection([
        ('own', 'Owned'),
        ('leased', 'Leased'),
        ('free', 'Not in Use'),
    ], string='Use', compute='_compute_current_lease', search='_search_use_state')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    note = fields.Text()

    _cadastral_company_uniq = models.Constraint(
        'UNIQUE(cadastral_number, company_id)',
        'A land plot with this cadastral number already exists in the company.',
    )

    @api.constrains('cadastral_number')
    def _check_cadastral_number(self):
        for plot in self:
            if not CADASTRAL_RE.match(plot.cadastral_number or ''):
                raise ValidationError(self.env._(
                    'Invalid cadastral number %s: expected the format 0000000000:00:000:0000.',
                    plot.cadastral_number))

    @api.constrains('area')
    def _check_area(self):
        for plot in self:
            if plot.area <= 0:
                raise ValidationError(self.env._('The plot area must be positive.'))

    def _compute_current_lease(self):
        today = fields.Date.context_today(self)
        for plot in self:
            lease = plot.lease_ids.filtered(
                lambda l: l.state == 'active' and l._covers(today))[:1]
            plot.current_lease_id = lease
            if plot.ownership == 'company':
                plot.use_state = 'own'
            else:
                plot.use_state = 'leased' if lease else 'free'

    def _search_use_state(self, operator, value):
        if operator not in ('=', 'in'):
            return NotImplemented
        values = {value} if operator == '=' else set(value)
        today = fields.Date.context_today(self)
        leases = self.env['l10n_ua.agro.land.lease'].search([
            ('state', '=', 'active'),
            ('date_start', '<=', today),
            '|', ('date_end', '=', False), ('date_end', '>=', today),
        ])
        leased_ids = leases.plot_ids.filtered(lambda p: p.ownership != 'company').ids
        domains = []
        if 'own' in values:
            domains.append([('ownership', '=', 'company')])
        if 'leased' in values:
            domains.append([('id', 'in', leased_ids)])
        if 'free' in values:
            domains.append([('ownership', '!=', 'company'), ('id', 'not in', leased_ids)])
        if not domains:
            return [('id', '=', False)]
        result = domains[0]
        for domain in domains[1:]:
            result = ['|'] + result + domain
        return result

    @api.onchange('cadastral_number')
    def _onchange_cadastral_number(self):
        # Користувачі копіюють номер із Публічної кадастрової карти з пробілами
        if self.cadastral_number:
            self.cadastral_number = re.sub(r'\s+', '', self.cadastral_number)
