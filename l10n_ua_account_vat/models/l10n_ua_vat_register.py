from odoo import api, fields, models


class L10nUaVatRegister(models.Model):
    _name = 'l10n_ua.vat.register'
    _description = 'VAT Register'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    register_type = fields.Selection(
        selection=[
            ('received', 'Received (Отримані)'),
            ('issued', 'Issued (Видані)'),
        ],
        string='Register Type',
        required=True,
    )
    period_id = fields.Many2one(
        'l10n_ua.tax.period',
        string='Tax Period',
        required=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'l10n_ua.vat.register.line',
        'register_id',
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
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    @api.depends('register_type', 'period_id')
    def _compute_name(self):
        for record in self:
            type_name = 'Received' if record.register_type == 'received' else 'Issued'
            period_name = record.period_id.name if record.period_id else ''
            record.name = f'VAT Register {type_name} {period_name}'

    @api.depends('line_ids.base_amount', 'line_ids.vat_amount')
    def _compute_totals(self):
        for record in self:
            record.total_base = sum(record.line_ids.mapped('base_amount'))
            record.total_vat = sum(record.line_ids.mapped('vat_amount'))


class L10nUaVatRegisterLine(models.Model):
    _name = 'l10n_ua.vat.register.line'
    _description = 'VAT Register Line'
    _order = 'date, id'

    register_id = fields.Many2one(
        'l10n_ua.vat.register',
        string='Register',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date',
        required=True,
    )
    tax_invoice_id = fields.Many2one(
        'l10n_ua.tax.invoice',
        string='Tax Invoice',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
    )
    partner_ipn = fields.Char(
        related='partner_id.ipn',
        string='Partner IPN',
    )
    invoice_number = fields.Char(
        string='Invoice Number',
    )
    invoice_date = fields.Date(
        string='Invoice Date',
    )
    base_amount = fields.Monetary(
        string='Base Amount',
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
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='register_id.currency_id',
    )
