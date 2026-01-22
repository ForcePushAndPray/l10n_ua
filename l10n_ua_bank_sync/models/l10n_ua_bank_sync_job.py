import json
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nUaBankSyncJob(models.Model):
    _name = 'l10n_ua.bank.sync.job'
    _description = 'Bank Sync Job'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    config_id = fields.Many2one(
        'l10n_ua.bank.sync.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='config_id.company_id',
        store=True,
    )
    journal_id = fields.Many2one(
        related='config_id.journal_id',
        store=True,
    )
    provider = fields.Selection(
        related='config_id.provider',
        store=True,
    )

    # Date range
    date_from = fields.Date(
        string='Date From',
        required=True,
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
    )

    # State
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('fetching', 'Fetching from Bank'),
            ('fetched', 'Fetched'),
            ('processing', 'Processing'),
            ('done', 'Done'),
            ('error', 'Error'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )

    # Raw payload storage
    raw_payload = fields.Text(
        string='Raw Payload (JSON)',
        help='Raw response from bank API stored as JSON',
    )
    payload_fetched_at = fields.Datetime(
        string='Payload Fetched At',
    )

    # Processing results
    transactions_count = fields.Integer(
        string='Transactions Found',
        readonly=True,
    )
    imported_count = fields.Integer(
        string='Imported',
        readonly=True,
    )
    updated_count = fields.Integer(
        string='Updated',
        readonly=True,
    )
    error_count = fields.Integer(
        string='Errors',
        readonly=True,
    )

    # Related statements
    statement_ids = fields.One2many(
        'l10n_ua.bank.statement',
        'sync_job_id',
        string='Created Statements',
    )
    statement_count = fields.Integer(
        string='Statement Count',
        compute='_compute_statement_count',
    )

    # Logs
    log_ids = fields.One2many(
        'l10n_ua.bank.sync.log',
        'job_id',
        string='Logs',
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
    )

    @api.depends('config_id.name', 'date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            config_name = rec.config_id.name if rec.config_id else ''
            date_from = rec.date_from.strftime('%d.%m.%Y') if rec.date_from else ''
            date_to = rec.date_to.strftime('%d.%m.%Y') if rec.date_to else ''
            rec.name = f"{config_name}: {date_from} - {date_to}"

    @api.depends('statement_ids')
    def _compute_statement_count(self):
        for rec in self:
            rec.statement_count = len(rec.statement_ids)

    def _log(self, message, level='info', data=None):
        """Add log entry."""
        self.ensure_one()

        # Log to Python logger
        log_method = getattr(_logger, level, _logger.info)
        log_method(f"[Job {self.id}] {message}")

        # Create log record
        self.env['l10n_ua.bank.sync.log'].create({
            'job_id': self.id,
            'level': level,
            'message': message,
            'data': json.dumps(data, ensure_ascii=False, default=str) if data else False,
        })

    def action_fetch(self):
        """Fetch data from bank API."""
        self.ensure_one()

        if self.state not in ('draft', 'error'):
            raise UserError(_("Can only fetch in draft or error state"))

        self._log(f"Starting fetch from {self.date_from} to {self.date_to}")
        self.write({
            'state': 'fetching',
            'error_message': False,
        })

        try:
            # Call provider-specific fetch method
            raw_data = self.config_id._fetch_from_bank(self.date_from, self.date_to)

            # Store raw payload
            self.write({
                'raw_payload': json.dumps(raw_data, ensure_ascii=False, default=str),
                'payload_fetched_at': fields.Datetime.now(),
                'state': 'fetched',
            })
            self._log(f"Fetch completed, payload stored", data={'size': len(self.raw_payload)})

            # Auto-process after fetch
            self.action_process()

        except Exception as e:
            self._log(f"Fetch error: {str(e)}", level='error')
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            raise

    def action_process(self):
        """Process stored payload and create statement lines."""
        self.ensure_one()

        if self.state not in ('fetched', 'error'):
            raise UserError(_("Can only process in fetched or error state"))

        if not self.raw_payload:
            raise UserError(_("No payload to process. Fetch data first."))

        self._log("Starting payload processing")
        self.write({
            'state': 'processing',
            'error_message': False,
        })

        try:
            # Parse raw data
            raw_data = json.loads(self.raw_payload)
            transactions = self.config_id._parse_transactions(raw_data)

            self.transactions_count = len(transactions)
            self._log(f"Parsed {len(transactions)} transactions")

            # Process transactions
            imported = 0
            updated = 0
            errors = 0

            for trans in transactions:
                try:
                    result = self._process_transaction(trans)
                    if result == 'imported':
                        imported += 1
                    elif result == 'updated':
                        updated += 1
                except Exception as e:
                    errors += 1
                    self._log(f"Error processing transaction: {str(e)}", level='error', data=trans)

            self.write({
                'imported_count': imported,
                'updated_count': updated,
                'error_count': errors,
                'state': 'done',
            })

            # Update config last sync date
            self.config_id.write({
                'last_sync_date': fields.Datetime.now(),
            })

            self._log(f"Processing completed: {imported} imported, {updated} updated, {errors} errors")

        except Exception as e:
            self._log(f"Processing error: {str(e)}", level='error')
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            raise

    def action_reprocess(self):
        """Reprocess stored payload without fetching again."""
        self.ensure_one()

        if not self.raw_payload:
            raise UserError(_("No payload to reprocess"))

        # Reset counters
        self.write({
            'state': 'fetched',
            'imported_count': 0,
            'updated_count': 0,
            'error_count': 0,
            'error_message': False,
        })

        self._log("Starting reprocess of stored payload")
        return self.action_process()

    def action_reset_to_draft(self):
        """Reset job to draft state."""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'raw_payload': False,
            'payload_fetched_at': False,
            'transactions_count': 0,
            'imported_count': 0,
            'updated_count': 0,
            'error_count': 0,
            'error_message': False,
        })
        # Delete related logs
        self.log_ids.unlink()

    def _process_transaction(self, trans):
        """
        Process single transaction - create or update.

        Args:
            trans: dict with transaction data:
                - id: unique transaction ID
                - date: transaction date
                - amount: signed amount (positive=incoming)
                - description: payment description
                - partner_name: counterparty name
                - partner_iban: counterparty IBAN
                - partner_edrpou: counterparty EDRPOU

        Returns:
            'imported' or 'updated'
        """
        trans_id = trans.get('id') or trans.get('ref') or ''

        # Parse transaction date
        trans_date = trans.get('date')
        if isinstance(trans_date, str):
            # Try to parse date string
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']:
                try:
                    trans_date = datetime.strptime(trans_date[:10], fmt).date()
                    break
                except ValueError:
                    continue
            else:
                trans_date = fields.Date.today()

        # Find partner
        partner = self._match_partner(trans)

        # Parse amount
        amount = trans.get('amount', 0)
        if isinstance(amount, str):
            amount = float(amount.replace(' ', '').replace(',', '.'))

        # Check if already imported
        existing = self.env['l10n_ua.bank.statement.line'].search([
            ('external_id', '=', trans_id),
            ('statement_id.journal_id', '=', self.journal_id.id),
        ], limit=1)

        line_vals = {
            'date': trans_date,
            'payment_ref': trans_id,
            'description': trans.get('description') or trans.get('purpose') or '',
            'amount': amount,
            'partner_id': partner.id if partner else False,
            'partner_name': trans.get('partner_name') or trans.get('CNTR_NAME') or '',
            'partner_iban': trans.get('partner_iban') or trans.get('CNTR_ACC') or '',
            'partner_edrpou': trans.get('partner_edrpou') or trans.get('CNTR_CRF') or '',
        }

        if existing:
            # Update existing record
            existing.write(line_vals)
            self._log(f"Updated transaction: {trans_id}", level='debug')
            return 'updated'

        # Get or create statement for transaction date
        statement = self._get_or_create_statement(trans_date)

        # Create new statement line
        line_vals.update({
            'statement_id': statement.id,
            'external_id': trans_id,
        })
        self.env['l10n_ua.bank.statement.line'].create(line_vals)
        self._log(f"Created transaction: {trans_id}", level='debug')

        return 'imported'

    def _get_or_create_statement(self, date):
        """Get existing or create new statement for date."""
        Statement = self.env['l10n_ua.bank.statement']

        # Search by journal and date only (not by job_id to avoid duplicates)
        statement = Statement.search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '=', date),
        ], limit=1)

        if not statement:
            statement = Statement.create({
                'journal_id': self.journal_id.id,
                'date': date,
                'company_id': self.company_id.id,
                'sync_job_id': self.id,
                'sync_provider': self.provider,
            })
        elif not statement.sync_job_id:
            # Link existing statement to this job if not already linked
            statement.sync_job_id = self.id

        return statement

    def _match_partner(self, trans):
        """Match partner by EDRPOU, IPN or IBAN."""
        Partner = self.env['res.partner']
        partner = False

        edrpou = trans.get('partner_edrpou') or trans.get('CNTR_CRF') or ''
        iban = trans.get('partner_iban') or trans.get('CNTR_ACC') or ''

        if edrpou:
            partner = Partner.search([('edrpou', '=', edrpou)], limit=1)

        if not partner and iban:
            bank_account = self.env['res.partner.bank'].search([
                ('acc_number', '=', iban)
            ], limit=1)
            if bank_account:
                partner = bank_account.partner_id

        return partner

    def action_view_statements(self):
        """View created statements."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Statements'),
            'res_model': 'l10n_ua.bank.statement',
            'view_mode': 'list,form',
            'domain': [('sync_job_id', '=', self.id)],
        }

    def action_view_logs(self):
        """View job logs."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs'),
            'res_model': 'l10n_ua.bank.sync.log',
            'view_mode': 'list,form',
            'domain': [('job_id', '=', self.id)],
        }


class L10nUaBankSyncLog(models.Model):
    _name = 'l10n_ua.bank.sync.log'
    _description = 'Bank Sync Log Entry'
    _order = 'create_date desc'

    job_id = fields.Many2one(
        'l10n_ua.bank.sync.job',
        string='Job',
        required=True,
        ondelete='cascade',
    )
    timestamp = fields.Datetime(
        string='Timestamp',
        default=fields.Datetime.now,
    )
    level = fields.Selection(
        selection=[
            ('debug', 'Debug'),
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('error', 'Error'),
        ],
        string='Level',
        default='info',
    )
    message = fields.Text(
        string='Message',
    )
    data = fields.Text(
        string='Data (JSON)',
        help='Additional data in JSON format',
    )
