from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

# За скільки днів до граничного строку розрахунків нагадувати
REMINDER_DAYS = 30


class L10nUaCustomsDeclaration(models.Model):
    """Митна декларація на експорт (ЕК-10): дата оформлення — перша подія для
    ПДВ (п. 187.1 ПКУ) і початок граничного строку валютних розрахунків."""
    _name = 'l10n_ua.customs.declaration'
    _description = 'Export Customs Declaration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Declaration Number', required=True, tracking=True, copy=False,
                       help='Номер митної декларації, напр. UA500020/2026/012345.')
    date = fields.Date(string='Clearance Date', required=True, tracking=True,
                       help='Дата митного оформлення (випуску) — дата першої події з ПДВ.')
    regime = fields.Selection([('ek10', 'EK-10 Export'), ('ek11', 'EK-11 Re-export')],
                              string='Customs Regime', required=True, default='ek10')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    partner_id = fields.Many2one('res.partner', string='Buyer', required=True, tracking=True)
    agreement_id = fields.Many2one(
        'l10n_ua.agreement', string='Foreign Trade Contract', tracking=True,
        domain="[('l10n_ua_foreign_trade', '=', True), ('company_id', '=', company_id)]")
    incoterm_id = fields.Many2one(related='agreement_id.l10n_ua_incoterm_id')
    currency_id = fields.Many2one('res.currency', string='Contract Currency', required=True,
                                  compute='_compute_currency', store=True, readonly=False, precompute=True)
    invoice_ids = fields.Many2many(
        'account.move', 'l10n_ua_customs_declaration_move_rel', 'declaration_id', 'move_id',
        string='Invoices', domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), "
                                  "('company_id', '=', company_id)]")
    picking_ids = fields.Many2many('stock.picking', string='Deliveries',
                                   domain="[('picking_type_code', '=', 'outgoing'), ('company_id', '=', company_id)]")
    customs_value = fields.Monetary(string='Customs Value (UAH)', currency_field='company_currency_id')
    phyto_certificate = fields.Char(string='Phytosanitary Certificate')
    phyto_certificate_date = fields.Date(string='Phytosanitary Certificate Date')
    origin_certificate = fields.Char(string='Certificate of Origin')
    origin_certificate_date = fields.Date(string='Certificate of Origin Date')
    quality_certificate = fields.Char(string='Quality Certificate')
    quality_certificate_date = fields.Date(string='Quality Certificate Date')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')],
                             default='draft', required=True, tracking=True, copy=False)
    tax_invoice_id = fields.Many2one('l10n_ua.tax.invoice', string='Tax Invoice', readonly=True, copy=False)

    # --- валютний контроль
    amount_total = fields.Monetary(string='Invoiced', compute='_compute_settlement', store=True)
    amount_residual = fields.Monetary(string='Unpaid', compute='_compute_settlement', store=True)
    settlement_days = fields.Integer(string='Settlement Days', compute='_compute_settlement', store=True)
    settlement_deadline = fields.Date(string='Settlement Deadline', compute='_compute_settlement', store=True)
    settlement_state = fields.Selection([
        ('open', 'Open'),
        ('due_soon', 'Due Soon'),
        ('overdue', 'Overdue'),
        ('settled', 'Settled'),
    ], string='Currency Control', compute='_compute_settlement', store=True)
    reminder_sent = fields.Boolean(copy=False)

    _name_company_uniq = models.Constraint(
        'UNIQUE(name, company_id)',
        'A customs declaration with this number already exists.',
    )

    @api.depends('invoice_ids.currency_id', 'agreement_id.currency_id')
    def _compute_currency(self):
        for declaration in self:
            declaration.currency_id = declaration.invoice_ids[:1].currency_id or declaration.agreement_id.currency_id \
                or declaration.currency_id or declaration.company_id.currency_id

    @api.depends('invoice_ids.amount_total', 'invoice_ids.amount_residual', 'date',
                 'agreement_id.l10n_ua_settlement_days', 'state')
    def _compute_settlement(self):
        today = fields.Date.context_today(self)
        for declaration in self:
            invoices = declaration.invoice_ids.filtered(lambda m: m.state == 'posted')
            declaration.amount_total = sum(invoices.mapped('amount_total'))
            declaration.amount_residual = sum(invoices.mapped('amount_residual'))
            days = declaration.agreement_id.l10n_ua_settlement_days or \
                declaration.company_id.l10n_ua_export_settlement_days
            declaration.settlement_days = days
            declaration.settlement_deadline = declaration.date + timedelta(days=days) \
                if declaration.date and days else False
            if declaration.state != 'confirmed':
                declaration.settlement_state = False
            elif invoices and declaration.currency_id.is_zero(declaration.amount_residual):
                declaration.settlement_state = 'settled'
            elif declaration.settlement_deadline and declaration.settlement_deadline < today:
                declaration.settlement_state = 'overdue'
            elif declaration.settlement_deadline and \
                    declaration.settlement_deadline <= today + timedelta(days=REMINDER_DAYS):
                declaration.settlement_state = 'due_soon'
            else:
                declaration.settlement_state = 'open'

    @api.onchange('invoice_ids')
    def _onchange_invoices(self):
        invoice = self.invoice_ids[:1]
        if invoice:
            self.partner_id = self.partner_id or invoice.commercial_partner_id
            if not self.agreement_id and invoice.l10n_ua_agreement_id.l10n_ua_foreign_trade:
                self.agreement_id = invoice.l10n_ua_agreement_id

    def action_confirm(self):
        for declaration in self:
            if not declaration.invoice_ids:
                raise UserError(self.env._('Link the export invoices to the customs declaration.'))
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        for declaration in self:
            if declaration.tax_invoice_id and declaration.tax_invoice_id.state == 'registered':
                raise UserError(self.env._(
                    'The tax invoice %s is registered: issue an adjustment calculation first.',
                    declaration.tax_invoice_id.number))
            declaration.tax_invoice_id.filtered(lambda t: t.state == 'draft').action_cancel()
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

    # --- ПН на експорт

    def action_create_tax_invoice(self):
        """ПН за ставкою 0 % з типом причини 07 на дату митного оформлення;
        база — контрактна вартість за курсом НБУ на цю дату (п. 188.1 ПКУ)."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(self.env._('Confirm the customs declaration first.'))
        if self.tax_invoice_id and self.tax_invoice_id.state != 'cancelled':
            raise UserError(self.env._('The tax invoice %s already exists.', self.tax_invoice_id.number))
        company = self.company_id
        lines = []
        seq = 10
        for invoice in self.invoice_ids:
            for line in invoice._l10n_ua_export_lines():
                base = invoice.currency_id._convert(
                    line.price_subtotal, company.currency_id, company, self.date)
                quantity = line.quantity or 1.0
                lines.append((0, 0, {
                    'sequence': seq,
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.display_name,
                    **line.product_id._l10n_ua_product_codes(),
                    'quantity': quantity,
                    'uom_id': line.product_uom_id.id,
                    'price_unit': base / quantity,
                    'vat_rate': '0',
                }))
                seq += 10
        tax_invoice = self.env['l10n_ua.tax.invoice'].create({
            'invoice_type': 'issued',
            'doc_type': 'pn',
            'number': self.env['ir.sequence'].next_by_code('l10n_ua.tax.invoice.issued') or '/',
            'date': self.date,
            'vat_method': 'first_event',
            'partner_id': self.partner_id.commercial_partner_id.id,
            'company_id': company.id,
            'move_id': self.invoice_ids[:1].id,
            'non_payer_reason': '07',
            'line_ids': lines,
        })
        self.tax_invoice_id = tax_invoice
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.tax.invoice',
            'res_id': tax_invoice.id,
            'view_mode': 'form',
        }

    # --- нагадування

    @api.model
    def _cron_settlement_reminder(self):
        """Перерахувати стани валютного контролю й нагадати за 30 днів до строку."""
        declarations = self.search([('state', '=', 'confirmed'), ('settlement_state', '!=', 'settled')])
        declarations._compute_settlement()
        for declaration in declarations.filtered(
                lambda d: d.settlement_state in ('due_soon', 'overdue') and not d.reminder_sent):
            declaration.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=declaration.settlement_deadline,
                summary=self.env._('Export settlement deadline'),
                note=self.env._(
                    'Export under %(declaration)s: %(residual)s %(currency)s unpaid, the settlement deadline '
                    'is %(deadline)s.', declaration=declaration.name, residual=declaration.amount_residual,
                    currency=declaration.currency_id.name, deadline=declaration.settlement_deadline),
                user_id=declaration.create_uid.id or self.env.uid,
            )
            declaration.reminder_sent = True

    def _l10n_ua_packing_rows(self):
        """Рядки пакувального листа: товар, партія, кількість, нетто / брутто."""
        self.ensure_one()
        rows = []
        for picking in self.picking_ids:
            for move_line in picking.move_line_ids:
                product = move_line.product_id
                net = move_line.quantity * (product.weight or (1.0 if product.uom_id == self.env.ref(
                    'uom.product_uom_kgm') else 0.0))
                rows.append({'product': product, 'lot': move_line.lot_id, 'quantity': move_line.quantity,
                             'uom': move_line.product_uom_id, 'net': net, 'picking': picking})
        return rows
