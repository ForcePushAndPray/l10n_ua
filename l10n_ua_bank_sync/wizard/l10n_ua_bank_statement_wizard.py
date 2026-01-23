from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nUaBankStatementWizard(models.TransientModel):
    """Wizard to generate bank statement from transactions."""
    _name = 'l10n_ua.bank.statement.wizard'
    _description = 'Generate Bank Statement'

    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', '=', 'bank')],
        default=lambda self: self._default_journal_id(),
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.today,
    )
    compute_opening_balance = fields.Boolean(
        string='Compute Opening Balance',
        default=True,
        help='Calculate opening balance from prior transactions',
    )

    # Preview
    transaction_count = fields.Integer(
        string='Transactions Found',
        compute='_compute_preview',
    )
    total_incoming = fields.Monetary(
        string='Total Incoming',
        compute='_compute_preview',
        currency_field='currency_id',
    )
    total_outgoing = fields.Monetary(
        string='Total Outgoing',
        compute='_compute_preview',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='journal_id.currency_id',
    )

    def _default_journal_id(self):
        return self.env['account.journal'].search([('type', '=', 'bank')], limit=1)

    @api.depends('journal_id', 'date_from', 'date_to')
    def _compute_preview(self):
        for wizard in self:
            if not wizard.journal_id or not wizard.date_from or not wizard.date_to:
                wizard.transaction_count = 0
                wizard.total_incoming = 0
                wizard.total_outgoing = 0
                continue

            transactions = self.env['l10n_ua.bank.transaction'].search([
                ('journal_id', '=', wizard.journal_id.id),
                ('date', '>=', wizard.date_from),
                ('date', '<=', wizard.date_to),
            ])

            wizard.transaction_count = len(transactions)
            wizard.total_incoming = sum(t.amount for t in transactions if t.amount > 0)
            wizard.total_outgoing = sum(abs(t.amount) for t in transactions if t.amount < 0)

    def action_generate(self):
        """Generate statement from transactions."""
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_("Date From must be before Date To"))

        # Check for existing statement in this period
        existing = self.env['l10n_ua.bank.statement'].search([
            ('journal_id', '=', self.journal_id.id),
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
        ], limit=1)

        if existing:
            raise UserError(_(
                "A statement already exists for this period: %s\n"
                "Please delete it first or choose a different period."
            ) % existing.name)

        # Calculate opening balance
        opening_balance = 0
        if self.compute_opening_balance:
            prior_trans = self.env['l10n_ua.bank.transaction'].search([
                ('journal_id', '=', self.journal_id.id),
                ('date', '<', self.date_from),
            ])
            opening_balance = sum(prior_trans.mapped('amount'))

        # Create statement
        statement = self.env['l10n_ua.bank.statement'].create({
            'journal_id': self.journal_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'opening_balance': opening_balance,
            'company_id': self.journal_id.company_id.id,
            'sync_provider': 'manual',
        })

        # Link transactions
        transactions = self.env['l10n_ua.bank.transaction'].search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        transactions.write({'statement_id': statement.id})

        # Open statement form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bank Statement'),
            'res_model': 'l10n_ua.bank.statement',
            'view_mode': 'form',
            'res_id': statement.id,
        }
