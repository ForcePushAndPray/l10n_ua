import base64
import io

from odoo import api, fields, models
from odoo.exceptions import UserError
import xlsxwriter

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
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
    ], default='draft', required=True, tracking=True, copy=False,
        help='Наряди беруть норми лише з затвердженої технологічної карти.')
    approved_by_id = fields.Many2one('res.users', string='Approved by', readonly=True, copy=False)
    approved_date = fields.Date(string='Approved on', readonly=True, copy=False)
    author_id = fields.Many2one(
        'hr.employee', string='Prepared by', help='Агроном, який склав технологічну карту.')

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

    def action_approve(self):
        for card in self:
            if not card.operation_ids and not card.material_ids:
                raise UserError(self.env._('Add the operations and materials before approving the card.'))
        self.write({'state': 'approved', 'approved_by_id': self.env.uid,
                    'approved_date': fields.Date.context_today(self)})

    def action_draft(self):
        self.write({'state': 'draft', 'approved_by_id': False, 'approved_date': False})

    def action_copy_to_next_season(self):
        """Копія карти на наступний сезон (рік урожаю + 1) — чернеткою."""
        self.ensure_one()
        season = self.env['l10n_ua.agro.season'].search([
            ('year', '=', self.season_id.year + 1), ('company_id', '=', self.company_id.id)], limit=1)
        if not season:
            raise UserError(self.env._('Create the season %s first.', self.season_id.year + 1))
        if self.search_count([('crop_id', '=', self.crop_id.id), ('season_id', '=', season.id),
                              ('company_id', '=', self.company_id.id)]):
            raise UserError(self.env._(
                'The %(season)s already has a technological card for %(crop)s.',
                season=season.name, crop=self.crop_id.name))
        new = self.copy({
            'season_id': season.id,
            'name': (self.name or '').replace(str(self.season_id.year), str(season.year)),
        })
        # строки операцій — на рік уперед
        for line in new.operation_ids:
            line.write({
                'date_from': line.date_from and line.date_from.replace(year=line.date_from.year + 1),
                'date_to': line.date_to and line.date_to.replace(year=line.date_to.year + 1),
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': new.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def _print_lines(self):
        """Рядки друку / XLSX: операції й матеріали з підсумками на площу."""
        self.ensure_one()
        area = self.area
        units = dict(self.env['l10n_ua.agro.operation.type']._fields['unit']._description_selection(self.env))
        operations = [{
            'operation': line.operation_type_id.name,
            'date_from': line.date_from, 'date_to': line.date_to,
            'unit': units.get(line.operation_type_id.unit, ''),
            'volume_ha': line.volume_ha, 'volume': line.volume_ha * area,
            'fuel_ha': line.fuel_ha, 'fuel': line.fuel_ha * area,
            'labor_ha': line.labor_ha, 'labor': line.labor_ha * area,
            'cost_ha': line.cost_ha, 'cost': line.cost_ha * area,
        } for line in self.operation_ids]
        materials = [{
            'product': line.product_id.display_name,
            'operation': line.operation_type_id.name or '',
            'uom': line.uom_id.name,
            'rate_ha': line.rate_ha, 'quantity': line.rate_ha * area,
            'price': line.price_unit, 'cost_ha': line.cost_ha, 'cost': line.cost_ha * area,
        } for line in self.material_ids]
        return operations, materials

    def action_export_xlsx(self):
        self.ensure_one()
        operations, materials = self._print_lines()
        out = io.BytesIO()
        book = xlsxwriter.Workbook(out, {'in_memory': True})
        sheet = book.add_worksheet(self.env._('Technological Card')[:31])
        bold = book.add_format({'bold': True})
        title = book.add_format({'bold': True, 'font_size': 13})
        head = book.add_format({'bold': True, 'border': 1, 'text_wrap': True, 'align': 'center',
                                'valign': 'vcenter', 'bg_color': '#EEEEEE'})
        cell = book.add_format({'border': 1})
        num = book.add_format({'border': 1, 'num_format': '#,##0.00'})
        num3 = book.add_format({'border': 1, 'num_format': '#,##0.000'})
        date_fmt = book.add_format({'border': 1, 'num_format': 'dd.mm.yyyy'})
        total = book.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00'})
        _ = self.env._
        row = 0
        sheet.write(row, 0, self.company_id.name, bold)
        row += 1
        sheet.write(row, 0, _('TECHNOLOGICAL CARD: %(crop)s, harvest %(year)s',
                              crop=self.crop_id.name, year=self.season_id.year), title)
        row += 1
        sheet.write(row, 0, _('Area, ha'))
        sheet.write_number(row, 1, self.area)
        sheet.write(row, 3, _('Status'))
        sheet.write(row, 4, dict(self._fields['state']._description_selection(self.env))[self.state])
        row += 2
        headers = [_('Operation'), _('From'), _('To'), _('Unit'), _('Volume per ha'), _('Volume'),
                   _('Fuel per ha, l'), _('Fuel, l'), _('Pay per ha'), _('Pay'), _('Cost per ha'), _('Cost')]
        for col, text in enumerate(headers):
            sheet.write(row, col, text, head)
        row += 1
        for line in operations:
            sheet.write(row, 0, line['operation'], cell)
            for col, key in ((1, 'date_from'), (2, 'date_to')):
                if line[key]:
                    sheet.write_datetime(row, col, fields.Datetime.to_datetime(line[key]), date_fmt)
                else:
                    sheet.write_blank(row, col, None, cell)
            sheet.write(row, 3, line['unit'], cell)
            for col, key in enumerate(('volume_ha', 'volume', 'fuel_ha', 'fuel', 'labor_ha', 'labor',
                                       'cost_ha', 'cost'), start=4):
                sheet.write_number(row, col, line[key], num3 if 'volume' in key else num)
            row += 1
        sheet.write(row, 0, _('Total operations'), bold)
        sheet.write_number(row, 10, sum(line['cost_ha'] for line in operations), total)
        sheet.write_number(row, 11, sum(line['cost'] for line in operations), total)
        row += 2
        headers = [_('Material'), _('Operation'), _('Unit'), _('Rate per ha'), _('Quantity'),
                   _('Price'), _('Cost per ha'), _('Cost')]
        for col, text in enumerate(headers):
            sheet.write(row, col, text, head)
        row += 1
        for line in materials:
            sheet.write(row, 0, line['product'], cell)
            sheet.write(row, 1, line['operation'], cell)
            sheet.write(row, 2, line['uom'], cell)
            for col, key in enumerate(('rate_ha', 'quantity', 'price', 'cost_ha', 'cost'), start=3):
                sheet.write_number(row, col, line[key], num3 if key in ('rate_ha', 'quantity') else num)
            row += 1
        sheet.write(row, 0, _('Total materials'), bold)
        sheet.write_number(row, 6, sum(line['cost_ha'] for line in materials), total)
        sheet.write_number(row, 7, sum(line['cost'] for line in materials), total)
        row += 2
        sheet.write(row, 0, _('Planned cost per ha'), bold)
        sheet.write_number(row, 1, self.cost_ha, total)
        sheet.write(row, 3, _('Planned cost'), bold)
        sheet.write_number(row, 4, self.cost_total, total)
        sheet.set_column(0, 0, 34)
        sheet.set_column(1, 11, 13)
        book.close()
        filename = '%s.xlsx' % (self.name or 'tech_card').replace('/', '-')
        attachment = self.env['ir.attachment'].create({
            'name': filename, 'datas': base64.b64encode(out.getvalue()),
            'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

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
    fuel_ha = fields.Float(string='Fuel per ha, l', digits=(10, 2), compute='_compute_breakdown')
    labor_ha = fields.Monetary(string='Pay per ha', compute='_compute_breakdown')

    @api.depends('operation_type_id', 'volume_ha')
    def _compute_breakdown(self):
        for line in self:
            line.fuel_ha = line.volume_ha * line.operation_type_id.fuel_norm
            line.labor_ha = line.volume_ha * line.operation_type_id.piece_rate

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
