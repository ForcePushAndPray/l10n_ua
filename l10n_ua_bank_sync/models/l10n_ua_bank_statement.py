from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class L10nUaBankStatement(models.Model):
    """
    Bank Statement - summary of transactions for a period.
    Can be generated from transactions for reporting/export.
    """
    _name = 'l10n_ua.bank.statement'
    _description = 'Ukrainian Bank Statement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', '=', 'bank')],
        tracking=True,
    )
    bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Bank Account',
        related='journal_id.bank_account_id',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
    )

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for record in self:
            record.currency_id = record.journal_id.currency_id or record.company_id.currency_id

    # Period
    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        tracking=True,
    )
    statement_type = fields.Selection(
        selection=[
            ('both', 'Both'),
            ('incoming', 'Incoming'),
            ('outgoing', 'Outgoing'),
        ],
        string='Type',
        default='both',
        required=True,
    )
    # Keep 'date' as alias for compatibility
    date = fields.Date(
        string='Date',
        compute='_compute_date',
        store=True,
    )

    # Transactions
    transaction_ids = fields.One2many(
        'l10n_ua.bank.transaction',
        'statement_id',
        string='Transactions',
    )
    transaction_count = fields.Integer(
        string='Transaction Count',
        compute='_compute_totals',
        store=True,
    )

    # Balances
    opening_balance = fields.Monetary(
        string='Opening Balance',
        currency_field='currency_id',
        help='Balance at the start of the period',
    )
    closing_balance = fields.Monetary(
        string='Closing Balance',
        compute='_compute_closing_balance',
        store=True,
        currency_field='currency_id',
        help='Balance at the end of the period',
    )
    total_incoming = fields.Monetary(
        string='Total Incoming',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_outgoing = fields.Monetary(
        string='Total Outgoing',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    turnover = fields.Monetary(
        string='Turnover',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help='Sum of incoming and outgoing',
    )

    sync_provider = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('privatbank', 'PrivatBank'),
            ('monobank', 'Monobank'),
        ],
        string='Source',
        default='manual',
    )
    sync_job_id = fields.Many2one(
        'l10n_ua.bank.sync.job',
        string='Sync Job',
        ondelete='set null',
    )

    @api.depends('journal_id', 'date_from', 'date_to', 'statement_type')
    def _compute_name(self):
        type_labels = {'both': '', 'incoming': ' (Incoming)', 'outgoing': ' (Outgoing)'}
        for record in self:
            journal_name = record.journal_id.name if record.journal_id else ''
            date_from = record.date_from.strftime('%d.%m.%Y') if record.date_from else ''
            date_to = record.date_to.strftime('%d.%m.%Y') if record.date_to else ''
            type_suffix = type_labels.get(record.statement_type, '')
            if date_from == date_to:
                record.name = f'{journal_name} {date_from}{type_suffix}'
            else:
                record.name = f'{journal_name} {date_from} - {date_to}{type_suffix}'

    @api.depends('date_from')
    def _compute_date(self):
        for record in self:
            record.date = record.date_from

    @api.depends('transaction_ids', 'transaction_ids.amount')
    def _compute_totals(self):
        for record in self:
            record.transaction_count = len(record.transaction_ids)
            record.total_incoming = sum(t.amount for t in record.transaction_ids if t.amount > 0)
            record.total_outgoing = sum(abs(t.amount) for t in record.transaction_ids if t.amount < 0)
            record.turnover = record.total_incoming + record.total_outgoing

    @api.depends('opening_balance', 'total_incoming', 'total_outgoing')
    def _compute_closing_balance(self):
        for record in self:
            record.closing_balance = record.opening_balance + record.total_incoming - record.total_outgoing

    def action_generate(self):
        """Generate statement: link transactions and compute opening balance."""
        for record in self:
            if not record.date_from or not record.date_to or not record.journal_id:
                continue

            # 1. Unlink existing transactions from this statement
            record.transaction_ids.write({'statement_id': False})

            # 2. Build domain based on statement type
            domain = [
                ('journal_id', '=', record.journal_id.id),
                ('date', '>=', record.date_from),
                ('date', '<=', record.date_to),
                ('statement_id', '=', False),
            ]
            if record.statement_type == 'incoming':
                domain.append(('amount', '>', 0))
            elif record.statement_type == 'outgoing':
                domain.append(('amount', '<', 0))

            # 3. Link matching transactions
            transactions = self.env['l10n_ua.bank.transaction'].search(domain)
            transactions.write({'statement_id': record.id})

            # 4. Compute opening balance from transactions before period
            prior_domain = [
                ('journal_id', '=', record.journal_id.id),
                ('date', '<', record.date_from),
            ]
            if record.statement_type == 'incoming':
                prior_domain.append(('amount', '>', 0))
            elif record.statement_type == 'outgoing':
                prior_domain.append(('amount', '<', 0))

            prior_trans = self.env['l10n_ua.bank.transaction'].search(prior_domain)
            record.opening_balance = sum(prior_trans.mapped('amount'))

    def action_view_transactions(self):
        """View transactions for this statement."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transactions'),
            'res_model': 'l10n_ua.bank.transaction',
            'view_mode': 'list,form',
            'domain': [('statement_id', '=', self.id)],
            'context': {
                'default_statement_id': self.id,
                'default_journal_id': self.journal_id.id,
            },
        }

    def action_export_xlsx(self):
        """Export statement to XLSX."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/l10n_ua_bank_sync/export_statement_xlsx/{self.id}',
            'target': 'self',
        }

    def action_print_pdf(self):
        """Print statement as PDF."""
        self.ensure_one()
        return self.env.ref('l10n_ua_bank_sync.action_report_bank_statement').report_action(self)

    def action_view_sync_job(self):
        """Open related sync job."""
        self.ensure_one()
        if not self.sync_job_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Job'),
            'res_model': 'l10n_ua.bank.sync.job',
            'view_mode': 'form',
            'res_id': self.sync_job_id.id,
        }
