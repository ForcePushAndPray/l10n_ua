from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class L10nUaBankTransaction(models.Model):
    """
    Bank Transaction - main entity for bank operations.

    Workflow:
    1. Transactions are created by sync jobs or manual import
    2. Accountant creates journal entries (draft) for selected transactions
    3. Accountant posts journal entries when ready
    """
    _name = 'l10n_ua.bank.transaction'
    _description = 'Ukrainian Bank Transaction'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )
    external_id = fields.Char(
        string='External ID',
        required=True,
        index=True,
        help='Unique transaction ID from bank',
    )
    date = fields.Date(
        string='Date',
        required=True,
        index=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        ondelete='cascade',
        domain=[('type', '=', 'bank')],
    )
    company_id = fields.Many2one(
        'res.company',
        related='journal_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='journal_id.currency_id',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        help='Positive for incoming, negative for outgoing',
    )
    payment_ref = fields.Char(
        string='Payment Reference',
    )
    description = fields.Text(
        string='Description',
    )

    # Partner info from bank
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    partner_name = fields.Char(
        string='Partner Name (from bank)',
    )
    partner_iban = fields.Char(
        string='Partner IBAN',
    )
    partner_edrpou = fields.Char(
        string='Partner EDRPOU',
    )

    # Statement link (optional grouping by date)
    statement_id = fields.Many2one(
        'l10n_ua.bank.statement',
        string='Statement',
        ondelete='set null',
        help='Optional daily statement grouping',
    )

    # Sync tracking
    sync_job_id = fields.Many2one(
        'l10n_ua.bank.sync.job',
        string='Sync Job',
        ondelete='set null',
        help='Job that imported this transaction',
    )
    sync_provider = fields.Selection(
        related='sync_job_id.provider',
        store=True,
    )

    # Accounting link
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        ondelete='set null',
    )
    move_state = fields.Selection(
        related='move_id.state',
        string='Move State',
        store=True,
    )

    # State based on move
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('draft', 'Draft Entry'),
            ('posted', 'Posted'),
        ],
        string='State',
        compute='_compute_state',
        store=True,
    )

    is_reconciled = fields.Boolean(
        string='Reconciled',
        default=False,
    )

    _unique_external_journal = models.Constraint(
        'UNIQUE(external_id, journal_id)',
        'Transaction with this External ID already exists for this journal!',
    )

    @api.depends('date', 'amount', 'partner_name')
    def _compute_display_name(self):
        for rec in self:
            date_str = rec.date.strftime('%d.%m.%Y') if rec.date else ''
            partner = rec.partner_name or rec.partner_id.name or ''
            if len(partner) > 20:
                partner = partner[:20] + '...'
            sign = '+' if rec.amount >= 0 else ''
            rec.display_name = f"{date_str} {sign}{rec.amount:,.2f} {partner}"

    @api.depends('move_id', 'move_id.state')
    def _compute_state(self):
        for rec in self:
            if not rec.move_id:
                rec.state = 'new'
            elif rec.move_id.state == 'posted':
                rec.state = 'posted'
            else:
                rec.state = 'draft'

    def action_create_move(self):
        """Create journal entry for this transaction."""
        self.ensure_one()

        if self.move_id:
            raise ValidationError(_("Journal entry already exists for this transaction."))

        journal = self.journal_id
        if not journal.default_account_id:
            raise ValidationError(
                _("Journal '%s' has no default account configured.") % journal.name
            )

        bank_account = journal.default_account_id
        suspense_account = self.company_id.account_journal_suspense_account_id

        if not suspense_account:
            raise ValidationError(
                _("Company has no suspense account configured. "
                  "Go to Settings > Accounting > Default Accounts.")
            )

        # Create journal entry
        move_vals = {
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.payment_ref or self.external_id or '',
            'narration': self.description,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'move_type': 'entry',
            'line_ids': [],
        }

        if self.amount > 0:
            # Incoming: Debit Bank, Credit Suspense
            move_vals['line_ids'] = [
                (0, 0, {
                    'account_id': bank_account.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'name': self.description or self.payment_ref or '/',
                    'debit': self.amount,
                    'credit': 0,
                }),
                (0, 0, {
                    'account_id': suspense_account.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'name': self.description or self.payment_ref or '/',
                    'debit': 0,
                    'credit': self.amount,
                }),
            ]
        else:
            # Outgoing: Debit Suspense, Credit Bank
            amount = abs(self.amount)
            move_vals['line_ids'] = [
                (0, 0, {
                    'account_id': suspense_account.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'name': self.description or self.payment_ref or '/',
                    'debit': amount,
                    'credit': 0,
                }),
                (0, 0, {
                    'account_id': bank_account.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'name': self.description or self.payment_ref or '/',
                    'debit': 0,
                    'credit': amount,
                }),
            ]

        move = self.env['account.move'].create(move_vals)
        self.move_id = move
        return move

    def action_view_move(self):
        """View related journal entry."""
        self.ensure_one()
        if not self.move_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def action_post_move(self):
        """Post the journal entry."""
        for rec in self:
            if rec.move_id and rec.move_id.state == 'draft':
                rec.move_id.action_post()

    def action_delete_move(self):
        """Delete draft journal entry and reset to new state."""
        for rec in self:
            if rec.move_id:
                if rec.move_id.state == 'posted':
                    raise ValidationError(
                        _("Cannot delete posted journal entry. Cancel it first.")
                    )
                rec.move_id.unlink()

    def action_create_and_post_move(self):
        """Create and immediately post journal entry."""
        for rec in self:
            if not rec.move_id:
                rec.action_create_move()
            if rec.move_id and rec.move_id.state == 'draft':
                rec.move_id.action_post()

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-link to statement if exists for same date/journal."""
        records = super().create(vals_list)
        for rec in records:
            if not rec.statement_id:
                # Find or create statement for this date
                statement = self.env['l10n_ua.bank.statement'].search([
                    ('journal_id', '=', rec.journal_id.id),
                    ('date', '=', rec.date),
                ], limit=1)
                if statement:
                    rec.statement_id = statement
        return records
