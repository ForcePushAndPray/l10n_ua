from odoo import api, fields, models


class L10nUaJournalOrder(models.Model):
    _name = 'l10n_ua.journal.order'
    _description = 'Journal Order (Журнал-ордер)'
    _order = 'period_start desc, journal_id'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'l10n_ua.journal.order.line',
        'journal_order_id',
        string='Lines',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='State',
        default='draft',
    )
    total_debit = fields.Monetary(
        string='Total Debit',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_credit = fields.Monetary(
        string='Total Credit',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    @api.depends('journal_id', 'period_start', 'period_end')
    def _compute_name(self):
        for record in self:
            if record.journal_id and record.period_start:
                record.name = f'{record.journal_id.name} ({record.period_start} - {record.period_end})'
            else:
                record.name = 'New'

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_totals(self):
        for record in self:
            record.total_debit = sum(record.line_ids.mapped('debit'))
            record.total_credit = sum(record.line_ids.mapped('credit'))

    def action_compute(self):
        """Compute journal order lines from account moves."""
        self.ensure_one()
        self.line_ids.unlink()
        # TODO: Implement computation logic
        return True

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})


class L10nUaJournalOrderLine(models.Model):
    _name = 'l10n_ua.journal.order.line'
    _description = 'Journal Order Line'
    _order = 'date, id'

    journal_order_id = fields.Many2one(
        'l10n_ua.journal.order',
        string='Journal Order',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date',
        required=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    description = fields.Char(
        string='Description',
    )
    debit = fields.Monetary(
        string='Debit',
        currency_field='currency_id',
    )
    credit = fields.Monetary(
        string='Credit',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='journal_order_id.currency_id',
    )
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
    )
