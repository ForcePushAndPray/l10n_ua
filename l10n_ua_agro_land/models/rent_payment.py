from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round


class AgroRentPayment(models.Model):
    """Виплата орендної плати (відомість): грошима з каси/банку або
    натурою — продукцією зі складу.

    Грошима: Дт 685 — Кт 30/31. Натурою: Дт 685 — Кт 712 і видаткова
    накладна зі складу (собівартість списує складський облік).
    """
    _name = 'l10n_ua.agro.rent.payment'
    _description = 'Land Rent Payment'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(default='/', copy=False, readonly=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    payment_form = fields.Selection([
        ('money', 'Money'),
        ('in_kind', 'In Kind'),
    ], string='Payment Form', required=True, default='money', tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        domain="[('company_id', '=', company_id), ('type', 'in', ('cash', 'bank', 'general'))]")
    payable_account_id = fields.Many2one(
        'account.account', string='Payable Account', required=True,
        default=lambda self: self.env.company._l10n_ua_agro_account(
            'l10n_ua_agro_rent_payable_account_id', ('6851', '685')))
    income_account_id = fields.Many2one(
        'account.account', string='Income Account',
        default=lambda self: self.env.company._l10n_ua_agro_account(
            'l10n_ua_agro_in_kind_income_account_id', ('712',)),
        help='Дохід від реалізації продукції, виданої в рахунок орендної плати (712).')
    product_id = fields.Many2one('product.product', string='Product')
    price_unit = fields.Monetary(
        string='Price per Unit',
        help='Ціна одиниці продукції, за якою вона зараховується в рахунок орендної плати.')
    uom_id = fields.Many2one(related='product_id.uom_id')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse',
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1))
    accrual_id = fields.Many2one(
        'l10n_ua.agro.rent.accrual', string='Accrual',
        domain="[('state', '=', 'posted'), ('company_id', '=', company_id)]",
        help='Обмежити заповнення боргами за одним нарахуванням.')
    line_ids = fields.One2many(
        'l10n_ua.agro.rent.payment.line', 'payment_id', string='Lines', copy=False)
    amount_total = fields.Monetary(string='Total', compute='_compute_totals', store=True)
    quantity_total = fields.Float(
        string='Total Quantity', digits='Product Unit', compute='_compute_totals', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    picking_ids = fields.One2many('stock.picking', 'l10n_ua_agro_rent_payment_id',
                                  string='Delivery Orders', readonly=True)
    picking_count = fields.Integer(compute='_compute_picking_count')
    note = fields.Text()

    @api.depends('line_ids.amount', 'line_ids.quantity')
    def _compute_totals(self):
        for payment in self:
            payment.amount_total = sum(payment.line_ids.mapped('amount'))
            payment.quantity_total = sum(payment.line_ids.mapped('quantity'))

    def _compute_picking_count(self):
        for payment in self:
            payment.picking_count = len(payment.picking_ids)

    @api.onchange('payment_form', 'company_id')
    def _onchange_payment_form(self):
        journal_types = ('cash', 'bank') if self.payment_form == 'money' else ('general',)
        if self.journal_id.type not in journal_types:
            company = self.company_id or self.env.company
            journal = company.l10n_ua_agro_rent_journal_id \
                if self.payment_form == 'in_kind' else self.env['account.journal']
            self.journal_id = journal or self.env['account.journal'].search([
                ('type', 'in', journal_types), ('company_id', '=', company.id)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'l10n_ua.agro.rent.payment') or '/'
        return super().create(vals_list)

    def unlink(self):
        if any(payment.state == 'posted' for payment in self):
            raise UserError(self.env._('Cancel the posted rent payment before deleting it.'))
        return super().unlink()

    def action_fill(self):
        """Заповнити рядки непогашеними боргами з орендної плати."""
        for payment in self:
            if payment.state != 'draft':
                raise UserError(self.env._('Only a draft payment can be filled.'))
            domain = [
                ('company_id', '=', payment.company_id.id),
                ('state', '=', 'posted'),
                ('residual', '>', 0),
                ('id', 'not in', payment.line_ids.accrual_line_id.ids),
            ]
            if payment.accrual_id:
                domain.append(('accrual_id', '=', payment.accrual_id.id))
            accrual_lines = self.env['l10n_ua.agro.rent.accrual.line'].search(
                domain, order='lessor_id, id')
            self.env['l10n_ua.agro.rent.payment.line'].create([{
                'payment_id': payment.id,
                'accrual_line_id': line.id,
                'amount': line.residual,
            } for line in accrual_lines])
        return True

    def _check_can_post(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._('Add the lessors to pay first.'))
        if self.payment_form == 'in_kind':
            if not self.product_id or float_is_zero(self.price_unit, precision_digits=2):
                raise UserError(self.env._('Set the product and its price for the in-kind payment.'))
            if not self.income_account_id:
                raise UserError(self.env._('Set the income account for the in-kind payment.'))
            if not self.warehouse_id:
                raise UserError(self.env._('Set the warehouse the products are issued from.'))
        for line in self.line_ids:
            if float_compare(line.amount, line.accrual_line_id.residual,
                             precision_rounding=self.currency_id.rounding) > 0:
                raise ValidationError(self.env._(
                    'The payment to %(lessor)s (%(amount)s) exceeds the rent debt (%(debt)s).',
                    lessor=line.lessor_id.name, amount=line.amount,
                    debt=line.accrual_line_id.residual))

    def action_post(self):
        for payment in self:
            if payment.state != 'draft':
                continue
            payment._check_can_post()
            move = self.env['account.move'].create(payment._prepare_move_vals())
            move.action_post()
            payment.write({'move_id': move.id, 'state': 'posted'})
            payment._reconcile_with_accruals()
            if payment.payment_form == 'in_kind':
                payment._create_pickings()
        return True

    def _prepare_move_vals(self):
        self.ensure_one()
        if self.payment_form == 'money':
            counterpart = self.journal_id.default_account_id
            if not counterpart:
                raise UserError(self.env._(
                    'Journal %s has no default account.', self.journal_id.display_name))
        else:
            counterpart = self.income_account_id
        lines = []
        for line in self.line_ids:
            label = self.env._('Land rent payment, %s', line.accrual_line_id.lease_id.name)
            lines.append((0, 0, {
                'name': label, 'account_id': self.payable_account_id.id,
                'partner_id': line.lessor_id.id, 'debit': line.amount,
            }))
            lines.append((0, 0, {
                'name': label, 'account_id': counterpart.id,
                'partner_id': line.lessor_id.id, 'credit': line.amount,
            }))
        return {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': lines,
        }

    def _reconcile_with_accruals(self):
        """Звірити 685 по кожному орендодавцю з проводками нарахувань."""
        self.ensure_one()
        account = self.payable_account_id
        if not account.reconcile:
            return
        accrual_moves = self.line_ids.accrual_line_id.accrual_id.move_id
        for partner in self.line_ids.lessor_id:
            to_reconcile = (self.move_id.line_ids | accrual_moves.line_ids).filtered(
                lambda l: l.account_id == account and l.partner_id == partner
                and not l.reconciled)
            if to_reconcile.filtered('debit') and to_reconcile.filtered('credit'):
                to_reconcile.reconcile()

    def _create_pickings(self):
        self.ensure_one()
        picking_type = self.warehouse_id.out_type_id
        customer_location = self.env.ref('stock.stock_location_customers')
        quantities = defaultdict(float)
        for line in self.line_ids:
            quantities[line.lessor_id] += line.quantity
        Picking = self.env['stock.picking']
        for partner, quantity in quantities.items():
            if float_is_zero(quantity, precision_rounding=self.product_id.uom_id.rounding):
                continue
            picking = Picking.create({
                'partner_id': partner.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': customer_location.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'l10n_ua_agro_rent_payment_id': self.id,
                'move_ids': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_uom_qty': quantity,
                    'product_uom': self.product_id.uom_id.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': customer_location.id,
                    'company_id': self.company_id.id,
                })],
            })
            picking.action_confirm()

    def action_cancel(self):
        for payment in self:
            if payment.picking_ids.filtered(lambda p: p.state == 'done'):
                raise UserError(self.env._(
                    'The products of %s have already been issued: return them first.', payment.name))
            payment.picking_ids.action_cancel()
            if payment.move_id:
                payment.move_id.line_ids.remove_move_reconcile()
                payment.move_id.button_draft()
                payment.move_id.button_cancel()
        self.write({'state': 'cancel'})

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        action['context'] = {}
        return action

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class AgroRentPaymentLine(models.Model):
    _name = 'l10n_ua.agro.rent.payment.line'
    _description = 'Land Rent Payment Line'
    _order = 'payment_id, lessor_id, id'

    payment_id = fields.Many2one(
        'l10n_ua.agro.rent.payment', required=True, ondelete='cascade', index=True)
    state = fields.Selection(related='payment_id.state', store=True)
    date = fields.Date(related='payment_id.date', store=True)
    company_id = fields.Many2one(related='payment_id.company_id', store=True)
    currency_id = fields.Many2one(related='payment_id.currency_id')
    accrual_line_id = fields.Many2one(
        'l10n_ua.agro.rent.accrual.line', string='Rent Accrual', required=True,
        ondelete='restrict', index=True,
        domain="[('state', '=', 'posted'), ('residual', '>', 0), ('company_id', '=', company_id)]")
    lessor_id = fields.Many2one(related='accrual_line_id.lessor_id', store=True)
    lease_id = fields.Many2one(related='accrual_line_id.lease_id', store=True)
    debt = fields.Monetary(related='accrual_line_id.residual', string='Debt')
    amount = fields.Monetary(string='Amount', required=True)
    quantity = fields.Float(
        string='Quantity', digits='Product Unit', compute='_compute_quantity', store=True,
        help='Кількість продукції для видачі натурою: сума / ціна.')

    @api.depends('amount', 'payment_id.price_unit', 'payment_id.payment_form', 'payment_id.product_id')
    def _compute_quantity(self):
        for line in self:
            payment = line.payment_id
            if payment.payment_form == 'in_kind' and payment.price_unit:
                # кількість, яку реально видасть склад (точність одиниці виміру)
                line.quantity = float_round(line.amount / payment.price_unit,
                                            precision_rounding=payment.product_id.uom_id.rounding or 0.01)
            else:
                line.quantity = 0.0

    @api.onchange('accrual_line_id')
    def _onchange_accrual_line(self):
        if self.accrual_line_id and not self.amount:
            self.amount = self.accrual_line_id.residual

    @api.constrains('amount')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(self.env._('The payment amount must be positive.'))
