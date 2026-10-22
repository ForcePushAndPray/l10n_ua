"""Періодичні рахунки за договором — без OCA ``contract``.

Дата наступного рахунку (``recurring_next_date``) — день, яким рахунок
датується. Період, за який він виставляється:

* передоплата — від цієї дати на N місяців / кварталів / років уперед;
* післоплата — та сама тривалість, що закінчилась напередодні.

Крон щодня створює рахунки для підписаних договорів, у яких ця дата настала,
і доганяє пропущені періоди. Період, що починається після дати завершення
договору, не виставляється — повторення вимикається.
"""

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

RULE_MONTHS = {'monthly': 1, 'quarterly': 3, 'yearly': 12}
MONTHS_UK = ('січень', 'лютий', 'березень', 'квітень', 'травень', 'червень', 'липень',
             'серпень', 'вересень', 'жовтень', 'листопад', 'грудень')
QUARTERS_UK = ('I', 'II', 'III', 'IV')
# Скільки періодів крон доганяє за раз для одного договору: захист від
# тисяч рахунків, якщо дату наступного рахунку помилково поставили в минуле.
MAX_CATCH_UP = 24


def period_label(start, end):
    """«жовтень 2026», «IV квартал 2026», «2026 рік» або «01.10.2026–15.11.2026»."""
    whole_months = start.day == 1 and (end + relativedelta(days=1)).day == 1
    if whole_months:
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        if months == 1:
            return '%s %d' % (MONTHS_UK[start.month - 1], start.year)
        if months == 3 and start.month % 3 == 1:
            return '%s квартал %d' % (QUARTERS_UK[start.month // 3], start.year)
        if months == 12 and start.month == 1:
            return '%d рік' % start.year
    return '%s–%s' % (start.strftime('%d.%m.%Y'), end.strftime('%d.%m.%Y'))


class L10nUaAgreement(models.Model):
    _inherit = 'l10n_ua.agreement'

    recurring_enabled = fields.Boolean(
        string='Recurring Invoices', tracking=True,
        help='Invoice this agreement automatically every period.')
    recurring_interval = fields.Integer(string='Every', default=1, tracking=True)
    recurring_rule = fields.Selection(
        [('monthly', 'Month(s)'), ('quarterly', 'Quarter(s)'), ('yearly', 'Year(s)')],
        string='Period', default='monthly', required=True, tracking=True)
    recurring_invoicing = fields.Selection(
        [('pre', 'In advance (current period)'), ('post', 'In arrears (previous period)')],
        string='Invoice for', default='pre', required=True, tracking=True)
    recurring_next_date = fields.Date(
        string='Next Invoice', tracking=True, copy=False,
        help='Date of the next invoice. In advance: the period starts on it; '
             'in arrears: the period ends the day before.')
    recurring_auto_post = fields.Boolean(
        string='Post Automatically', help='Otherwise the invoices are left as drafts.')
    recurring_journal_id = fields.Many2one(
        'account.journal', string='Journal', check_company=True,
        domain="[('type', 'in', ('sale', 'purchase'))]",
        help='Leave empty for the default sales / purchase journal.')
    recurring_line_ids = fields.One2many(
        'l10n_ua.agreement.recurring.line', 'agreement_id', string='Recurring Lines', copy=True)
    recurring_amount = fields.Monetary(
        string='Per Period', compute='_compute_recurring_amount')
    invoice_ids = fields.One2many('account.move', 'l10n_ua_agreement_id', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count')

    @api.depends('recurring_line_ids.price_subtotal')
    def _compute_recurring_amount(self):
        for rec in self:
            rec.recurring_amount = sum(rec.recurring_line_ids.mapped('price_subtotal'))

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids.filtered(lambda m: m.is_invoice(include_receipts=True)))

    @api.onchange('recurring_enabled')
    def _onchange_recurring_enabled(self):
        if self.recurring_enabled and not self.recurring_next_date:
            self.recurring_next_date = self.start_date or fields.Date.context_today(self)

    # --- періоди ---

    def _recurring_delta(self):
        self.ensure_one()
        return relativedelta(months=RULE_MONTHS[self.recurring_rule] * max(self.recurring_interval, 1))

    def _recurring_period(self, invoice_date):
        """(початок, кінець) періоду рахунку з датою ``invoice_date``."""
        self.ensure_one()
        delta = self._recurring_delta()
        if self.recurring_invoicing == 'post':
            return invoice_date - delta, invoice_date - relativedelta(days=1)
        return invoice_date, invoice_date + delta - relativedelta(days=1)

    # --- рахунки ---

    def _recurring_check(self):
        for rec in self:
            if not rec.recurring_line_ids:
                raise UserError(_('Add at least one recurring line to agreement %s.',
                                  rec.display_name))
            if not rec.recurring_next_date:
                raise UserError(_('Set the next invoice date of agreement %s.', rec.display_name))

    def _recurring_period_in_term(self, start):
        self.ensure_one()
        return not self.end_date or start <= self.end_date

    def _recurring_invoice_vals(self, invoice_date):
        self.ensure_one()
        start, end = self._recurring_period(invoice_date)
        # Опис рядка («за жовтень 2026») — мовою клієнта, а не мовою крону.
        lang = self.partner_id.lang or self.env.lang
        lines = [(0, 0, line.with_context(lang=lang)._invoice_line_vals(start, end))
                 for line in self.recurring_line_ids]
        vals = {
            'move_type': 'out_invoice' if self.direction == 'sale' else 'in_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': invoice_date,
            'invoice_origin': self.code,
            'l10n_ua_agreement_id': self.id,
            'invoice_line_ids': lines,
        }
        if self.recurring_journal_id:
            vals['journal_id'] = self.recurring_journal_id.id
        if self.direction == 'purchase':
            vals['ref'] = _('%(agreement)s, %(period)s',
                            agreement=self.display_name, period=period_label(start, end))
        return vals

    def _recurring_create_invoice(self):
        """Рахунок за період ``recurring_next_date``; дата зсувається на наступний."""
        self.ensure_one()
        self._recurring_check()
        start, _end = self._recurring_period(self.recurring_next_date)
        if not self._recurring_period_in_term(start):
            raise UserError(_('The next period of agreement %s starts after the agreement ends.',
                              self.display_name))
        move = self.env['account.move'].with_company(self.company_id).create(
            self._recurring_invoice_vals(self.recurring_next_date))
        if self.recurring_auto_post:
            move.action_post()
        self.recurring_next_date += self._recurring_delta()
        self.message_post(body=Markup(_('Recurring invoice created: %s')) % move._get_html_link())
        return move

    def action_recurring_create_invoice(self):
        self.ensure_one()
        move = self._recurring_create_invoice()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }

    def action_view_invoices(self):
        self.ensure_one()
        sale = self.direction == 'sale'
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account.action_move_out_invoice_type' if sale else 'account.action_move_in_invoice_type')
        action['domain'] = [('l10n_ua_agreement_id', '=', self.id),
                            ('move_type', 'in', ('out_invoice', 'out_refund') if sale
                             else ('in_invoice', 'in_refund'))]
        action['context'] = {'default_l10n_ua_agreement_id': self.id,
                             'default_partner_id': self.partner_id.id,
                             'default_move_type': 'out_invoice' if sale else 'in_invoice'}
        return action

    @api.model
    def _cron_recurring_invoices(self, date_ref=None):
        """Рахунки за всі настали періоди підписаних договорів."""
        date_ref = date_ref or fields.Date.context_today(self)
        agreements = self.search([
            ('recurring_enabled', '=', True),
            ('state', '=', 'signed'),
            ('recurring_next_date', '<=', date_ref),
        ])
        for agreement in agreements:
            try:
                with self.env.cr.savepoint():
                    for _i in range(MAX_CATCH_UP):
                        if agreement.recurring_next_date > date_ref:
                            break
                        start, _end = agreement._recurring_period(agreement.recurring_next_date)
                        if not agreement._recurring_period_in_term(start):
                            agreement.recurring_enabled = False
                            agreement.message_post(body=_(
                                'Recurring invoicing stopped: the agreement ended on %s.',
                                agreement.end_date))
                            break
                        agreement._recurring_create_invoice()
            except UserError as e:
                agreement.message_post(body=_('Recurring invoice not created: %s', e.args[0]))


class L10nUaAgreementRecurringLine(models.Model):
    _name = 'l10n_ua.agreement.recurring.line'
    _description = 'Agreement Recurring Line'
    _order = 'sequence, id'
    _check_company_auto = True

    agreement_id = fields.Many2one(
        'l10n_ua.agreement', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='agreement_id.company_id', store=True)
    currency_id = fields.Many2one(related='agreement_id.currency_id')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', string='Product', check_company=True)
    name = fields.Char(
        string='Description',
        help='#PERIOD# — the period («жовтень 2026», «IV квартал 2026»), '
             '#START# / #END# — its first and last day. Empty — the product name '
             '«for <period>».')
    quantity = fields.Float(string='Quantity', default=1.0, digits='Product Unit')
    price_unit = fields.Float(string='Unit Price', digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='Taxes', check_company=True)
    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_price_subtotal')

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.onchange('product_id')
    def _onchange_product_id(self):
        product = self.product_id
        if not product:
            return
        if self.agreement_id.direction == 'purchase':
            self.price_unit = product.standard_price
            taxes = product.supplier_taxes_id
        else:
            self.price_unit = product.lst_price
            taxes = product.taxes_id
        self.tax_ids = taxes.filtered(lambda t: t.company_id == self.agreement_id.company_id)

    def _render_description(self, start, end):
        self.ensure_one()
        label = period_label(start, end)
        if not self.name:
            return _('%(product)s for %(period)s',
                     product=self.product_id.display_name or '', period=label).strip()
        return (self.name.replace('#PERIOD#', label)
                .replace('#START#', start.strftime('%d.%m.%Y'))
                .replace('#END#', end.strftime('%d.%m.%Y')))

    def _invoice_line_vals(self, start, end):
        self.ensure_one()
        vals = {
            'name': self._render_description(start, end),
            'quantity': self.quantity,
            'price_unit': self.price_unit,
            'tax_ids': [(6, 0, self.tax_ids.ids)],
        }
        if self.product_id:
            vals['product_id'] = self.product_id.id
        return vals
