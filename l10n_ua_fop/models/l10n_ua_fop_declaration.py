from odoo import api, fields, models


class L10nUaFopDeclaration(models.Model):
    _name = 'l10n_ua.fop.declaration'
    _description = 'FOP Single Tax Declaration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, period desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
        tracking=True,
    )
    period = fields.Selection(
        selection=[
            ('q1', 'Q1'),
            ('h1', 'H1 (Half Year)'),
            ('9m', '9 Months'),
            ('year', 'Year'),
        ],
        string='Period',
        required=True,
        tracking=True,
    )
    fop_group_id = fields.Many2one(
        'l10n_ua.fop.group',
        string='FOP Group',
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
    
    # Income
    total_income = fields.Monetary(
        string='Total Income',
        currency_field='currency_id',
        tracking=True,
    )
    
    # Single tax
    tax_rate = fields.Float(
        string='Tax Rate (%)',
        related='fop_group_id.tax_rate',
    )
    single_tax = fields.Monetary(
        string='Single Tax',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )
    
    # ESV
    esv_base = fields.Monetary(
        string='ESV Base (Min Wage)',
        currency_field='currency_id',
    )
    esv_rate = fields.Float(
        string='ESV Rate (%)',
        default=22.0,
    )
    esv_amount = fields.Monetary(
        string='ESV Amount',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
    )
    
    # Total
    total_payable = fields.Monetary(
        string='Total Payable',
        compute='_compute_taxes',
        store=True,
        currency_field='currency_id',
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
    submission_date = fields.Date(
        string='Submission Date',
    )
    xml_file = fields.Binary(
        string='XML File',
    )
    xml_filename = fields.Char(
        string='XML Filename',
    )

    @api.depends('year', 'period', 'fop_group_id')
    def _compute_name(self):
        period_names = {
            'q1': 'Q1',
            'h1': 'H1',
            '9m': '9M',
            'year': 'Year',
        }
        for record in self:
            period_name = period_names.get(record.period, '')
            group_name = record.fop_group_id.name if record.fop_group_id else ''
            record.name = f'EP Declaration {period_name}/{record.year} ({group_name})'

    @api.depends('total_income', 'tax_rate', 'esv_base', 'esv_rate')
    def _compute_taxes(self):
        for record in self:
            record.single_tax = record.total_income * (record.tax_rate / 100) if record.tax_rate else 0
            record.esv_amount = record.esv_base * (record.esv_rate / 100) if record.esv_base else 0
            record.total_payable = record.single_tax + record.esv_amount

    def action_calculate(self):
        # TODO: Calculate from income books
        self.write({'state': 'calculated'})

    def action_submit(self):
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })

    def action_accept(self):
        self.write({'state': 'accepted'})

    def action_draft(self):
        self.write({
            'state': 'draft',
            'submission_date': False,
        })

    def action_generate_xml(self):
        # TODO: Implement XML generation
        pass
