from odoo import api, fields, models


class L10nUaTaxInvoice(models.Model):
    _name = 'l10n_ua.tax.invoice'
    _description = 'Tax Invoice (Податкова накладна)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, number desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    number = fields.Char(
        string='Number',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    invoice_type = fields.Selection(
        selection=[
            ('issued', 'Issued (Видана)'),
            ('received', 'Received (Отримана)'),
        ],
        string='Type',
        required=True,
        default='issued',
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        tracking=True,
    )
    partner_ipn = fields.Char(
        related='partner_id.ipn',
        string='Partner IPN',
    )
    partner_name = fields.Char(
        related='partner_id.name',
        string='Partner Name',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Related Invoice',
    )
    line_ids = fields.One2many(
        'l10n_ua.tax.invoice.line',
        'tax_invoice_id',
        string='Lines',
    )
    total_base = fields.Monetary(
        string='Total Base',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_vat = fields.Monetary(
        string='Total VAT',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('registered', 'Registered in ERPN'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    erpn_number = fields.Char(
        string='ERPN Registration Number',
        tracking=True,
    )
    erpn_date = fields.Datetime(
        string='ERPN Registration Date',
    )

    @api.depends('number', 'date')
    def _compute_name(self):
        for record in self:
            record.name = f'PN {record.number} від {record.date}' if record.number else 'New'

    @api.depends('line_ids.base_amount', 'line_ids.vat_amount')
    def _compute_totals(self):
        for record in self:
            record.total_base = sum(record.line_ids.mapped('base_amount'))
            record.total_vat = sum(record.line_ids.mapped('vat_amount'))
            record.total_amount = record.total_base + record.total_vat

    def action_register_erpn(self):
        # TODO: Implement ERPN registration
        self.write({'state': 'registered'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_generate_xml(self):
        # TODO: Implement XML generation for ERPN
        pass


class L10nUaTaxInvoiceLine(models.Model):
    _name = 'l10n_ua.tax.invoice.line'
    _description = 'Tax Invoice Line'
    _order = 'sequence, id'

    tax_invoice_id = fields.Many2one(
        'l10n_ua.tax.invoice',
        string='Tax Invoice',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    name = fields.Char(
        string='Description',
        required=True,
    )
    uktzed_code = fields.Char(
        string='UKTZED Code',
        help='Ukrainian Classification of Foreign Economic Activity',
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
    )
    price_unit = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id',
    )
    base_amount = fields.Monetary(
        string='Base Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    vat_rate = fields.Selection(
        selection=[
            ('20', '20%'),
            ('7', '7%'),
            ('0', '0%'),
            ('exempt', 'Exempt'),
        ],
        string='VAT Rate',
        default='20',
    )
    vat_amount = fields.Monetary(
        string='VAT Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='tax_invoice_id.currency_id',
    )

    @api.depends('quantity', 'price_unit', 'vat_rate')
    def _compute_amounts(self):
        for line in self:
            line.base_amount = line.quantity * line.price_unit
            if line.vat_rate and line.vat_rate != 'exempt':
                rate = float(line.vat_rate) / 100
                line.vat_amount = line.base_amount * rate
            else:
                line.vat_amount = 0
