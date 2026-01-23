from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    total_incoming = fields.Monetary(
        string='Total Incoming (Кт)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help='Sum of positive amounts (incoming/credit)',
    )
    total_outgoing = fields.Monetary(
        string='Total Outgoing (Дт)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help='Sum of negative amounts (outgoing/debit)',
    )
    # Keep old field names for compatibility
    total_debit = fields.Monetary(
        string='Total Debit',
        related='total_outgoing',
        currency_field='currency_id',
    )
    total_credit = fields.Monetary(
        string='Total Credit',
        related='total_incoming',
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('posted', 'Posted'),
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
            # Incoming (Кт) = positive amounts (credit to bank account)
            record.total_incoming = sum(line.amount for line in record.line_ids if line.amount > 0)
            # Outgoing (Дт) = negative amounts (debit from bank account)
            record.total_outgoing = sum(abs(line.amount) for line in record.line_ids if line.amount < 0)

    def action_confirm(self):
        """Confirm statement - create draft journal entries."""
        for statement in self:
            if statement.state != 'draft':
                continue
            if not statement.line_ids:
                raise ValidationError(_("Cannot confirm empty statement."))
            statement._create_account_moves()
        self.write({'state': 'confirmed'})

    def action_post(self):
        """Post statement - post all journal entries."""
        for statement in self:
            if statement.state != 'confirmed':
                continue
            # Post all draft moves
            draft_moves = statement.line_ids.mapped('move_id').filtered(
                lambda m: m.state == 'draft'
            )
            draft_moves.action_post()
        self.write({'state': 'posted'})

    def action_draft(self):
        """Reset to draft - only if no posted moves."""
        for statement in self:
            posted_moves = statement.line_ids.filtered(
                lambda l: l.move_id and l.move_id.state == 'posted'
            )
            if posted_moves:
                raise ValidationError(
                    _("Cannot reset to draft: %d lines have posted journal entries. "
                      "Cancel them first.") % len(posted_moves)
                )
            # Unlink draft moves
            draft_moves = statement.line_ids.mapped('move_id').filtered(
                lambda m: m.state == 'draft'
            )
            if draft_moves:
                draft_moves.unlink()
            statement.line_ids.write({'move_id': False, 'is_reconciled': False})
        self.write({'state': 'draft'})

    def _create_account_moves(self):
        """Create journal entries for statement lines."""
        self.ensure_one()

        if not self.journal_id.default_account_id:
            raise ValidationError(
                _("Journal '%s' has no default account configured.") % self.journal_id.name
            )

        bank_account = self.journal_id.default_account_id

        for line in self.line_ids:
            if line.move_id:
                continue  # Already has a move

            # Determine counterpart account
            # For now use suspense account, user can change later
            suspense_account = self.company_id.account_journal_suspense_account_id
            if not suspense_account:
                raise ValidationError(
                    _("Company has no suspense account configured. "
                      "Go to Settings > Accounting > Default Accounts.")
                )

            # Create journal entry
            move_vals = {
                'journal_id': self.journal_id.id,
                'date': line.date,
                'ref': line.payment_ref or line.external_id or '',
                'narration': line.description,
                'partner_id': line.partner_id.id if line.partner_id else False,
                'move_type': 'entry',
                'line_ids': [],
            }

            if line.amount > 0:
                # Incoming: Debit Bank, Credit Suspense
                move_vals['line_ids'] = [
                    (0, 0, {
                        'account_id': bank_account.id,
                        'partner_id': line.partner_id.id if line.partner_id else False,
                        'name': line.description or line.payment_ref or '/',
                        'debit': line.amount,
                        'credit': 0,
                    }),
                    (0, 0, {
                        'account_id': suspense_account.id,
                        'partner_id': line.partner_id.id if line.partner_id else False,
                        'name': line.description or line.payment_ref or '/',
                        'debit': 0,
                        'credit': line.amount,
                    }),
                ]
            else:
                # Outgoing: Debit Suspense, Credit Bank
                amount = abs(line.amount)
                move_vals['line_ids'] = [
                    (0, 0, {
                        'account_id': suspense_account.id,
                        'partner_id': line.partner_id.id if line.partner_id else False,
                        'name': line.description or line.payment_ref or '/',
                        'debit': amount,
                        'credit': 0,
                    }),
                    (0, 0, {
                        'account_id': bank_account.id,
                        'partner_id': line.partner_id.id if line.partner_id else False,
                        'name': line.description or line.payment_ref or '/',
                        'debit': 0,
                        'credit': amount,
                    }),
                ]

            move = self.env['account.move'].create(move_vals)
            line.move_id = move

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
