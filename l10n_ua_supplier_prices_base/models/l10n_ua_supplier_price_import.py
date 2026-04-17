import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


STATE_TRANSITIONS = {
    'draft': ('fetching',),
    'fetching': ('fetched', 'error'),
    'fetched': ('parsing',),
    'parsing': ('parsed', 'error'),
    'parsed': ('applying',),
    'applying': ('done', 'error'),
    'error': ('draft',),
    'done': (),
}


class L10nUaSupplierPriceImport(models.Model):
    _name = 'l10n_ua.supplier.price.import'
    _description = 'Supplier Price Import'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_imported desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, default='/', tracking=True)
    source_id = fields.Many2one(
        'l10n_ua.supplier.price.source',
        string='Source',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    partner_id = fields.Many2one(
        related='source_id.partner_id', store=True, readonly=True, string='Supplier',
    )
    company_id = fields.Many2one(
        related='source_id.company_id', store=True, readonly=True,
    )
    date_imported = fields.Datetime(
        string='Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('fetching', 'Fetching'),
            ('fetched', 'Fetched'),
            ('parsing', 'Parsing'),
            ('parsed', 'Parsed'),
            ('applying', 'Applying'),
            ('done', 'Done'),
            ('error', 'Error'),
        ],
        default='draft',
        required=True,
        tracking=True,
        readonly=True,
    )
    raw_file = fields.Binary(
        string='Raw File',
        attachment=True,
        help='Збережений файл після fetch — використовується для повторного парсингу',
    )
    raw_filename = fields.Char(string='Filename')
    error_log = fields.Text(string='Error Log', readonly=True)

    line_ids = fields.One2many(
        'l10n_ua.supplier.price.import.line',
        'import_id',
        string='Lines',
    )
    line_count = fields.Integer(compute='_compute_line_stats', store=True)
    matched_count = fields.Integer(compute='_compute_line_stats', store=True)
    unknown_count = fields.Integer(compute='_compute_line_stats', store=True)
    error_count = fields.Integer(compute='_compute_line_stats', store=True)

    @api.depends('line_ids', 'line_ids.status')
    def _compute_line_stats(self):
        for imp in self:
            lines = imp.line_ids
            imp.line_count = len(lines)
            imp.matched_count = len(lines.filtered(lambda l: l.status in ('matched', 'created')))
            imp.unknown_count = len(lines.filtered(lambda l: l.status == 'unknown'))
            imp.error_count = len(lines.filtered(lambda l: l.status == 'error'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'l10n_ua.supplier.price.import'
                ) or '/'
        return super().create(vals_list)

    def _set_state(self, new_state, error_message=None):
        """Validate transition then update state. NEVER use direct write({'state': ...})."""
        for imp in self:
            allowed = STATE_TRANSITIONS.get(imp.state, ())
            if new_state not in allowed:
                raise UserError(_(
                    "Invalid state transition: %(from)s → %(to)s. Allowed: %(allowed)s",
                    **{'from': imp.state, 'to': new_state, 'allowed': allowed or '(terminal)'},
                ))
            vals = {'state': new_state}
            if error_message is not None:
                vals['error_log'] = error_message
            super(L10nUaSupplierPriceImport, imp).write(vals)

    # === Action buttons (manual control) ===

    def action_fetch(self):
        """draft → fetching → fetched. Дочірні модулі реалізують fetch для свого fetcher_type."""
        for imp in self:
            imp._set_state('fetching')
            try:
                imp._do_fetch()
                imp._set_state('fetched')
            except Exception as e:
                _logger.exception("Fetch failed for import %s", imp.name)
                imp._set_state('error', error_message=f'Fetch error: {e}')
                raise UserError(_("Fetch failed: %s", e))
        return True

    def action_parse(self):
        """fetched → parsing → parsed."""
        for imp in self:
            if not imp.raw_file:
                raise UserError(_("No raw file to parse. Run Fetch first."))
            imp._set_state('parsing')
            try:
                imp.line_ids.unlink()
                imp._do_parse()
                imp._set_state('parsed')
            except Exception as e:
                _logger.exception("Parse failed for import %s", imp.name)
                imp._set_state('error', error_message=f'Parse error: {e}')
                raise UserError(_("Parse failed: %s", e))
        return True

    def action_apply(self):
        """parsed → applying → done. Створює/оновлює product.supplierinfo."""
        for imp in self:
            if not imp.line_ids:
                raise UserError(_("No lines to apply. Run Parse first."))
            imp._set_state('applying')
            try:
                imp._do_apply()
                imp._set_state('done')
            except Exception as e:
                _logger.exception("Apply failed for import %s", imp.name)
                imp._set_state('error', error_message=f'Apply error: {e}')
                raise UserError(_("Apply failed: %s", e))
        return True

    def action_restart(self):
        """error → draft. Очищує error_log."""
        for imp in self:
            if imp.state != 'error':
                raise UserError(_("Restart is only allowed from error state."))
            super(L10nUaSupplierPriceImport, imp).write({
                'state': 'draft',
                'error_log': False,
            })
        return True

    # === Pluggable hooks for extension modules ===

    def _do_fetch(self):
        """Override per fetcher_type. Must populate raw_file and raw_filename."""
        self.ensure_one()
        if self.source_id.fetcher_type == 'manual':
            if not self.raw_file:
                raise UserError(_("Upload a file before fetching (manual mode)."))
            return
        raise UserError(_(
            "No fetcher implementation for type '%s'. "
            "Install the corresponding module (e.g. l10n_ua_supplier_prices_api).",
            self.source_id.fetcher_type,
        ))

    def _do_parse(self):
        """Override per parser_type. Must create supplier.price.import.line records."""
        self.ensure_one()
        raise UserError(_(
            "No parser implementation for type '%s'. "
            "Install the corresponding module (e.g. l10n_ua_supplier_prices_xml).",
            self.source_id.parser_type,
        ))

    def _do_apply(self):
        """Default apply — створює/оновлює product.supplierinfo для кожної matched line."""
        self.ensure_one()
        Supplierinfo = self.env['product.supplierinfo']
        chunk_size = 500
        lines = self.line_ids
        applied = 0
        deadline = datetime.now() + timedelta(seconds=self.source_id.apply_timeout)

        for offset in range(0, len(lines), chunk_size):
            if datetime.now() > deadline:
                raise UserError(_(
                    "Apply timeout (%(t)ss) exceeded after %(n)s lines. "
                    "Increase apply_timeout on source or split import.",
                    t=self.source_id.apply_timeout, n=applied,
                ))
            chunk = lines[offset:offset + chunk_size]
            for line in chunk:
                line._apply_to_supplierinfo()
                applied += 1
            self.env.cr.commit()

    # === Watchdog cron ===

    @api.model
    def _cron_watchdog(self):
        """Знаходить imports застряглі в проміжних станах і переводить у error."""
        in_flight_states = ('fetching', 'parsing', 'applying')
        candidates = self.search([('state', 'in', in_flight_states)])
        now = datetime.now()
        stuck_count = 0
        for imp in candidates:
            timeout_minutes = imp.source_id.watchdog_timeout_minutes
            stuck_for = (now - fields.Datetime.from_string(imp.write_date)).total_seconds() / 60
            if stuck_for >= timeout_minutes:
                imp._set_state('error', error_message=_(
                    "Watchdog: stuck in state %(s)s for %(m).0f minutes (limit %(l)s).",
                    s=imp.state, m=stuck_for, l=timeout_minutes,
                ))
                stuck_count += 1
        if stuck_count:
            _logger.warning("Watchdog: marked %d stuck imports as error", stuck_count)
        return stuck_count

    @api.model
    def _cron_auto_sync(self):
        """Створює нові draft imports для джерел з auto_sync_active=True."""
        Source = self.env['l10n_ua.supplier.price.source']
        sources = Source.search([('auto_sync_active', '=', True), ('active', '=', True)])
        now = datetime.now()
        created = 0
        for source in sources:
            if source.last_sync_date:
                next_sync = fields.Datetime.from_string(source.last_sync_date) + \
                            timedelta(hours=source.sync_interval_hours)
                if now < next_sync:
                    continue
            imp = self.create({'source_id': source.id})
            try:
                imp.action_fetch()
                imp.action_parse()
                imp.action_apply()
                source.last_sync_date = now
                created += 1
            except Exception as e:
                _logger.error("Auto-sync failed for source %s: %s", source.name, e)
        return created
