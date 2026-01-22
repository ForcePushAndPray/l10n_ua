from odoo import api, fields, models


class L10nUaFopIncomeBook(models.Model):
    _name = 'l10n_ua.fop.income.book'
    _description = 'FOP Income Book (Книга обліку доходів)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, quarter desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    quarter = fields.Selection(
        selection=[
            ('1', 'Q1'),
            ('2', 'Q2'),
            ('3', 'Q3'),
            ('4', 'Q4'),
        ],
        string='Quarter',
        required=True,
    )
    fop_group_id = fields.Many2one(
        'l10n_ua.fop.group',
        string='FOP Group',
        required=True,
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
    line_ids = fields.One2many(
        'l10n_ua.fop.income.book.line',
        'book_id',
        string='Lines',
    )
    total_income = fields.Monetary(
        string='Total Income',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )

    @api.depends('year', 'quarter')
    def _compute_name(self):
        for record in self:
            record.name = f'Income Book Q{record.quarter}/{record.year}'

    @api.depends('line_ids.amount')
    def _compute_totals(self):
        for record in self:
            record.total_income = sum(record.line_ids.mapped('amount'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})


class L10nUaFopIncomeBookLine(models.Model):
    _name = 'l10n_ua.fop.income.book.line'
    _description = 'FOP Income Book Line'
    _order = 'date, id'

    book_id = fields.Many2one(
        'l10n_ua.fop.income.book',
        string='Income Book',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date',
        required=True,
    )
    document_number = fields.Char(
        string='Document Number',
    )
    description = fields.Char(
        string='Description',
    )
    income_type = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('bank', 'Bank Transfer'),
            ('card', 'Card Payment'),
        ],
        string='Income Type',
        default='bank',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='book_id.currency_id',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    bank_statement_line_id = fields.Many2one(
        'account.bank.statement.line',
        string='Bank Statement Line',
    )
