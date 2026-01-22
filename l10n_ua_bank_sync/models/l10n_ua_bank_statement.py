from odoo import api, fields, models, _


class L10nUaBankStatement(models.Model):
    _name = 'l10n_ua.bank.statement'
    _description = 'Ukrainian Bank Statement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        tracking=True,
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
        related='journal_id.currency_id',
    )
    line_ids = fields.One2many(
        'l10n_ua.bank.statement.line',
        'statement_id',
        string='Lines',
    )
    line_count = fields.Integer(
        string='Line Count',
        compute='_compute_line_count',
    )
    opening_balance = fields.Monetary(
        string='Opening Balance',
        currency_field='currency_id',
    )
    closing_balance = fields.Monetary(
        string='Closing Balance',
        currency_field='currency_id',
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
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('reconciled', 'Reconciled'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    sync_provider = fields.Selection(
        selection=[
            ('manual', 'Manual'),
        ],
        string='Source',
        default='manual',
    )
    sync_job_id = fields.Many2one(
        'l10n_ua.bank.sync.job',
        string='Sync Job',
        ondelete='set null',
    )

    @api.depends('journal_id', 'date')
    def _compute_name(self):
        for record in self:
            journal_name = record.journal_id.name if record.journal_id else ''
            date_str = record.date.strftime('%d.%m.%Y') if record.date else ''
            record.name = f'{journal_name} {date_str}'

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends('line_ids.amount')
    def _compute_totals(self):
        for record in self:
            record.total_debit = sum(line.amount for line in record.line_ids if line.amount > 0)
            record.total_credit = sum(abs(line.amount) for line in record.line_ids if line.amount < 0)

    def action_import(self):
        self.write({'state': 'imported'})

    def action_reconcile(self):
        self.write({'state': 'reconciled'})

    def action_draft(self):
        self.write({'state': 'draft'})

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


class L10nUaBankStatementLine(models.Model):
    _name = 'l10n_ua.bank.statement.line'
    _description = 'Ukrainian Bank Statement Line'
    _order = 'date, id'

    statement_id = fields.Many2one(
        'l10n_ua.bank.statement',
        string='Statement',
        required=True,
        ondelete='cascade',
    )
    date = fields.Date(
        string='Date',
        required=True,
    )
    external_id = fields.Char(
        string='External ID',
        index=True,
        help='Unique transaction ID from bank',
    )
    payment_ref = fields.Char(
        string='Payment Reference',
    )
    description = fields.Text(
        string='Description',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    partner_name = fields.Char(
        string='Partner Name',
    )
    partner_iban = fields.Char(
        string='Partner IBAN',
    )
    partner_edrpou = fields.Char(
        string='Partner EDRPOU',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        help='Positive for incoming, negative for outgoing',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='statement_id.currency_id',
    )
    journal_id = fields.Many2one(
        related='statement_id.journal_id',
        store=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
    )
    is_reconciled = fields.Boolean(
        string='Reconciled',
        default=False,
    )

    _sql_constraints = [
        ('external_id_journal_uniq',
         'unique(external_id, journal_id)',
         'External ID must be unique per journal!'),
    ]
