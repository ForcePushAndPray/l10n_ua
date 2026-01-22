from odoo import api, fields, models


class L10nUaVatDeclaration(models.Model):
    _name = 'l10n_ua.vat.declaration'
    _description = 'VAT Declaration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    period_id = fields.Many2one(
        'l10n_ua.tax.period',
        string='Tax Period',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('calculated', 'Calculated'),
            ('submitted', 'Submitted'),
            ('accepted', 'Accepted'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    
    # Section I - Tax liabilities
    sales_20 = fields.Monetary(string='Sales 20%', currency_field='currency_id')
    vat_20 = fields.Monetary(string='VAT 20%', currency_field='currency_id')
    sales_7 = fields.Monetary(string='Sales 7%', currency_field='currency_id')
    vat_7 = fields.Monetary(string='VAT 7%', currency_field='currency_id')
    sales_0 = fields.Monetary(string='Sales 0%', currency_field='currency_id')
    sales_exempt = fields.Monetary(string='Sales Exempt', currency_field='currency_id')
    total_liabilities = fields.Monetary(
        string='Total Tax Liabilities',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    
    # Section II - Tax credit
    purchases_20 = fields.Monetary(string='Purchases 20%', currency_field='currency_id')
    credit_20 = fields.Monetary(string='Credit 20%', currency_field='currency_id')
    purchases_7 = fields.Monetary(string='Purchases 7%', currency_field='currency_id')
    credit_7 = fields.Monetary(string='Credit 7%', currency_field='currency_id')
    total_credit = fields.Monetary(
        string='Total Tax Credit',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    
    # Result
    vat_payable = fields.Monetary(
        string='VAT Payable',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    vat_refundable = fields.Monetary(
        string='VAT Refundable',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('period_id')
    def _compute_name(self):
        for record in self:
            period_name = record.period_id.name if record.period_id else ''
            record.name = f'VAT Declaration {period_name}'

    @api.depends('vat_20', 'vat_7', 'credit_20', 'credit_7')
    def _compute_totals(self):
        for record in self:
            record.total_liabilities = record.vat_20 + record.vat_7
            record.total_credit = record.credit_20 + record.credit_7
            diff = record.total_liabilities - record.total_credit
            if diff > 0:
                record.vat_payable = diff
                record.vat_refundable = 0
            else:
                record.vat_payable = 0
                record.vat_refundable = abs(diff)

    def action_calculate(self):
        # TODO: Calculate from VAT registers
        self.write({'state': 'calculated'})

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_accept(self):
        self.write({'state': 'accepted'})

    def action_draft(self):
        self.write({'state': 'draft'})
