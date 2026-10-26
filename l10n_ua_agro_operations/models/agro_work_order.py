from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_round

from .agro_operation_type import WORK_UNITS


class AgroWorkOrder(models.Model):
    """Наряд на польові роботи (облікового листа тракториста-машиніста
    рядок): що, де, ким і якою технікою зроблено, які матеріали й пальне
    витрачено. Проведення списує матеріали зі складу на поле:
    Дт 23 (аналітика поле × культура) — Кт 20."""
    _name = 'l10n_ua.agro.work.order'
    _description = 'Field Work Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='/', copy=False, readonly=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    planting_id = fields.Many2one(
        'l10n_ua.agro.planting', string='Planting', required=True, index=True, tracking=True,
        domain="[('company_id', '=', company_id)]")
    field_id = fields.Many2one(related='planting_id.field_id', store=True, index=True)
    season_id = fields.Many2one(related='planting_id.season_id', store=True, index=True)
    crop_id = fields.Many2one(related='planting_id.crop_id', store=True, index=True)
    operation_type_id = fields.Many2one(
        'l10n_ua.agro.operation.type', string='Operation', required=True, tracking=True)
    unit = fields.Selection(related='operation_type_id.unit')
    area_done = fields.Float(
        string='Area Done (ha)', digits=(16, 4), tracking=True,
        help='Оброблена площа — від неї рахуються норми внесення з техкарти.')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env.company.l10n_ua_agro_warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1))
    worker_ids = fields.One2many(
        'l10n_ua.agro.work.order.worker', 'order_id', string='Operators', copy=True)
    material_ids = fields.One2many(
        'l10n_ua.agro.work.order.material', 'order_id', string='Materials and Fuel', copy=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    stock_move_ids = fields.One2many(
        'stock.move', 'l10n_ua_agro_work_order_id', string='Stock Moves', readonly=True)
    labor_amount = fields.Monetary(string='Labor', compute='_compute_amounts', store=True)
    material_amount = fields.Monetary(string='Materials', compute='_compute_amounts', store=True)
    fuel_amount = fields.Monetary(string='Fuel', compute='_compute_amounts', store=True)
    total_amount = fields.Monetary(string='Total Cost', compute='_compute_amounts', store=True)
    note = fields.Text()

    @api.depends('worker_ids.amount', 'material_ids.amount', 'material_ids.is_fuel')
    def _compute_amounts(self):
        for order in self:
            order.labor_amount = sum(order.worker_ids.mapped('amount'))
            order.fuel_amount = sum(order.material_ids.filtered('is_fuel').mapped('amount'))
            order.material_amount = sum(order.material_ids.filtered(lambda m: not m.is_fuel).mapped('amount'))
            order.total_amount = order.labor_amount + order.fuel_amount + order.material_amount

    @api.model
    def _default_fuel_product(self):
        return self.env.ref('l10n_ua_agro_operations.product_diesel', raise_if_not_found=False) \
            or self.env['product.product']

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id') or self.env.company.id)
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'l10n_ua.agro.work.order') or '/'
        return super().create(vals_list)

    def unlink(self):
        if any(order.state == 'done' for order in self):
            raise UserError(self.env._('Cancel the work order before deleting it.'))
        return super().unlink()

    @api.onchange('planting_id')
    def _onchange_planting(self):
        if self.planting_id and not self.area_done:
            self.area_done = self.planting_id.area

    @api.constrains('area_done', 'planting_id')
    def _check_area(self):
        for order in self:
            if order.area_done < 0:
                raise ValidationError(self.env._('The area done cannot be negative.'))
            if order.area_done - order.planting_id.area > 0.00005:
                raise ValidationError(self.env._(
                    'The area done (%(done).4f ha) exceeds the sown area of %(planting)s (%(area).4f ha).',
                    done=order.area_done, planting=order.planting_id.display_name,
                    area=order.planting_id.area))

    def _tech_card(self):
        self.ensure_one()
        return self.env['l10n_ua.agro.tech.card'].search([
            ('crop_id', '=', self.crop_id.id),
            ('season_id', '=', self.season_id.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def action_load_norms(self):
        """Матеріали з техкарти (норма × площа) і пальне за нормою операції
        (обсяг роботи операторів × норма × коефіцієнт машини)."""
        for order in self:
            if order.state != 'draft':
                raise UserError(self.env._('Only a draft work order can be filled.'))
            order.material_ids.filtered('is_from_norm').unlink()
            lines = []
            card = order._tech_card()
            for material in card.material_ids.filtered(
                    lambda m: m.operation_type_id == order.operation_type_id):
                qty = float_round(material.rate_ha * order.area_done,
                                  precision_rounding=material.product_id.uom_id.rounding)
                lines.append({
                    'order_id': order.id, 'product_id': material.product_id.id,
                    'quantity': qty, 'norm_quantity': qty, 'is_from_norm': True})
            fuel = defaultdict(float)
            for worker in order.worker_ids:
                product = worker.machine_id.fuel_product_id or order._default_fuel_product()
                if product and order.operation_type_id.fuel_norm:
                    fuel[product] += worker.volume * order.operation_type_id.fuel_norm * (
                        worker.machine_id.fuel_factor or 1.0)
            for product, qty in fuel.items():
                qty = float_round(qty, precision_rounding=product.uom_id.rounding)
                lines.append({
                    'order_id': order.id, 'product_id': product.id, 'quantity': qty,
                    'norm_quantity': qty, 'is_fuel': True, 'is_from_norm': True})
            self.env['l10n_ua.agro.work.order.material'].create(lines)
        return True

    # --- Проведення ---

    def _consumption_location(self):
        return self.env.ref('l10n_ua_agro_operations.stock_location_field_consumption')

    def _analytic_distribution(self):
        """Аналітика поле (план «Поля») + культура (план «Культури»)."""
        self.ensure_one()
        field_account = self.field_id._l10n_ua_agro_analytic_account()
        crop_account = self.crop_id._l10n_ua_agro_analytic_account(self.company_id)
        return {'%s,%s' % (field_account.id, crop_account.id): 100.0}

    def action_done(self):
        for order in self:
            if order.state != 'draft':
                continue
            if not order.worker_ids and not order.material_ids:
                raise UserError(self.env._('Add the operators or the materials of the work order.'))
            materials = order.material_ids.filtered(
                lambda m: not float_is_zero(m.quantity, precision_rounding=m.product_id.uom_id.rounding))
            if materials and not order.warehouse_id:
                raise UserError(self.env._('Set the warehouse the materials are taken from.'))
            # агроном проводить наряд без прав складу й бухгалтерії
            order.sudo()._create_stock_moves(materials.sudo())
            order.state = 'done'
            order.sudo()._post_material_entry(materials.sudo())
        return True

    def _create_stock_moves(self, materials):
        self.ensure_one()
        if not materials:
            return
        source = self.warehouse_id.lot_stock_id
        dest = self._consumption_location()
        moves = self.env['stock.move'].create([{
            'product_id': line.product_id.id,
            'product_uom_qty': line.quantity,
            'product_uom': line.product_id.uom_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'l10n_ua_agro_work_order_id': self.id,
            'l10n_ua_agro_material_id': line.id,
        } for line in materials])
        moves._action_confirm()
        moves._action_assign()
        for move in moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        moves._action_done()

    def _post_material_entry(self, materials):
        """Дт 23 (поле × культура) — Кт рахунок запасів за вартістю списання."""
        self.ensure_one()
        if not materials:
            return
        company = self.company_id
        debit_account = company._l10n_ua_agro_ops_account(
            'l10n_ua_agro_production_account_id', ('231', '23'))
        if not debit_account:
            raise UserError(self.env._('Set the crop production account in the Agro settings.'))
        journal = company.l10n_ua_agro_operations_journal_id or self.env['account.journal'].search([
            ('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        distribution = self._analytic_distribution()
        credit = defaultdict(float)
        lines = []
        for line in materials:
            line.amount = line._stock_value()
            if company.currency_id.is_zero(line.amount):
                continue
            account = line._stock_account()
            credit[account] += line.amount
            lines.append((0, 0, {
                'name': '%s: %s' % (self.name, line.product_id.display_name),
                'account_id': debit_account.id,
                'debit': line.amount,
                'analytic_distribution': distribution,
                'l10n_ua_agro_planting_id': self.planting_id.id,
            }))
        if not lines:
            return
        for account, amount in credit.items():
            lines.append((0, 0, {
                'name': self.env._('Write-off to field %(field)s, %(order)s',
                                   field=self.field_id.display_name, order=self.name),
                'account_id': account.id,
                'credit': company.currency_id.round(amount),
            }))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.name,
            'company_id': company.id,
            'line_ids': lines,
        })
        move.action_post()
        self.move_id = move

    def action_cancel(self):
        for order in self:
            if order.state == 'done':
                order.sudo()._return_stock_moves()
                if order.move_id:
                    order.move_id.sudo()._reverse_moves(
                        [{'date': order.move_id.date, 'ref': self.env._('Reversal of %s', order.name)}],
                        cancel=True)
        self.write({'state': 'cancel'})

    def _return_stock_moves(self):
        self.ensure_one()
        done = self.stock_move_ids.filtered(lambda m: m.state == 'done' and m.location_dest_id == self._consumption_location())
        if not done:
            return
        returns = self.env['stock.move'].create([{
            'product_id': move.product_id.id,
            'product_uom_qty': move.quantity,
            'product_uom': move.product_uom.id,
            'location_id': move.location_dest_id.id,
            'location_dest_id': move.location_id.id,
            'company_id': move.company_id.id,
            'origin': self.name,
            'origin_returned_move_id': move.id,
            'l10n_ua_agro_work_order_id': self.id,
        } for move in done])
        returns._action_confirm()
        for move in returns:
            move.quantity = move.product_uom_qty
            move.picked = True
        returns._action_done()

    def action_draft(self):
        for order in self:
            if order.state != 'cancel':
                raise UserError(self.env._('Only a cancelled work order can be reset to draft.'))
        self.write({'state': 'draft', 'move_id': False})
        self.material_ids.write({'amount': 0.0})

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class AgroWorkOrderWorker(models.Model):
    """Виробіток механізатора за нарядом (обсяг × розцінка)."""
    _name = 'l10n_ua.agro.work.order.worker'
    _description = 'Work Order Operator'
    _order = 'order_id, id'

    order_id = fields.Many2one('l10n_ua.agro.work.order', required=True, ondelete='cascade', index=True)
    state = fields.Selection(related='order_id.state', store=True)
    date = fields.Date(related='order_id.date', store=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    employee_id = fields.Many2one(
        'hr.employee', string='Operator', required=True, domain="[('company_id', 'in', (company_id, False))]")
    machine_id = fields.Many2one('l10n_ua.agro.machine', string='Machine')
    volume = fields.Float(string='Output', digits=(16, 4), required=True)
    hours = fields.Float(string='Hours', digits=(6, 2))
    rate = fields.Float(
        string='Piece Rate', digits='Product Price', compute='_compute_rate', store=True, readonly=False)
    amount = fields.Monetary(string='Pay', compute='_compute_amount', store=True)

    @api.depends('order_id.operation_type_id')
    def _compute_rate(self):
        for line in self:
            line.rate = line.order_id.operation_type_id.piece_rate

    @api.depends('volume', 'rate')
    def _compute_amount(self):
        for line in self:
            line.amount = line.currency_id.round(line.volume * line.rate) if line.currency_id \
                else line.volume * line.rate

    @api.onchange('employee_id')
    def _onchange_employee(self):
        order = self.order_id
        if self.employee_id and not self.volume and order.unit == 'ha':
            already = sum((order.worker_ids - self).mapped('volume'))
            self.volume = max(order.area_done - already, 0.0)


class AgroWorkOrderMaterial(models.Model):
    """Матеріал або пальне, списані за нарядом на поле."""
    _name = 'l10n_ua.agro.work.order.material'
    _description = 'Work Order Material'
    _order = 'order_id, is_fuel, id'

    order_id = fields.Many2one('l10n_ua.agro.work.order', required=True, ondelete='cascade', index=True)
    state = fields.Selection(related='order_id.state', store=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    product_id = fields.Many2one('product.product', string='Material', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id')
    quantity = fields.Float(string='Quantity', digits='Product Unit', required=True)
    norm_quantity = fields.Float(
        string='By Norm', digits='Product Unit',
        help='Кількість за нормою техкарти або нормою пального.')
    deviation = fields.Float(
        string='Deviation', digits='Product Unit', compute='_compute_deviation', store=True,
        help='Фактична витрата мінус норма: додатна — перевитрата.')
    is_fuel = fields.Boolean(string='Fuel')
    is_from_norm = fields.Boolean(readonly=True)
    amount = fields.Monetary(
        string='Cost', readonly=True,
        help='Вартість списання зі складу (заповнюється при проведенні наряду).')

    @api.depends('quantity', 'norm_quantity')
    def _compute_deviation(self):
        for line in self:
            line.deviation = line.quantity - line.norm_quantity if line.norm_quantity else 0.0

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(self.env._('The quantity cannot be negative.'))

    def _stock_value(self):
        """Вартість, за якою склад списав матеріал; якщо склад її не оцінив —
        облікова ціна товару."""
        self.ensure_one()
        moves = self.order_id.stock_move_ids.filtered(
            lambda m: m.l10n_ua_agro_material_id == self and m.state == 'done')
        value = sum(moves.mapped('value'))
        if self.currency_id.is_zero(value):
            value = self.quantity * self.product_id.standard_price
        return self.currency_id.round(value)

    def _stock_account(self):
        self.ensure_one()
        account = self.product_id.categ_id.property_stock_valuation_account_id
        if not account:
            account = self.company_id._l10n_ua_agro_ops_account(
                'l10n_ua_agro_material_account_id', ('203',) if self.is_fuel else ('201', '20'))
        if not account:
            raise UserError(self.env._(
                'Set the stock valuation account of %s or the materials account in the Agro settings.',
                self.product_id.display_name))
        return account
