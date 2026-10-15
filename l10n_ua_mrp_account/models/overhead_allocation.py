"""Розподіл загальновиробничих витрат (ЗВВ) — issue #373.

П(С)БО 16 «Витрати», п. 15–16:

* ЗВВ накопичуються на рахунку 91;
* змінні ЗВВ розподіляються на кожен об'єкт витрат (23) повністю, за базою
  розподілу (зарплата, машино-години, матеріали, обсяг виробництва);
* постійні ЗВВ розподіляються на 23 за базою при нормальній потужності:
  розподілено = постійні × min(1, фактична база / нормальна база);
  нерозподілена частина включається до собівартості реалізації (90x).

Документ «Розподіл ЗВВ» за період бере сальдо рахунків 91 на кінець періоду
(змінні й постійні — за налаштуваннями компанії), знаходить завершені за
період виробничі замовлення, ділить розподілену суму пропорційно їхній базі
і проводить одну проводку:

    Дт 23  Кт 91   — розподілені ЗВВ (змінні + розподілені постійні)
    Дт 90x Кт 91   — нерозподілені постійні ЗВВ
    Дт 26  Кт 23   — ЗВВ у собівартості випущеної продукції (частка на складі)
    Дт 901 Кт 23   — ЗВВ продукції, що вже вибула зі складу на дату розподілу

Вартість випуску в Odoo 19 — це `stock.move.value` руху готової продукції
(окремої моделі шарів оцінки вже немає). Як і «Додаткові витрати» (landed
costs), розподілені ЗВВ додаються до вартості руху через
`stock.move._get_value_from_extra`, після чого `_set_value()` перераховує
вартість руху і собівартість товару (середня / FIFO). Скасування сторнує
проводку і так само повертає вартість руху.
"""

from datetime import datetime, time

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero

from .res_company import OVERHEAD_BASES


class L10nUaOverheadAllocation(models.Model):
    _name = 'l10n_ua.overhead.allocation'
    _description = 'Production Overhead Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='/',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string='Period From', required=True, tracking=True)
    date_to = fields.Date(string='Period To', required=True, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('cancelled', 'Cancelled')],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    base = fields.Selection(
        OVERHEAD_BASES,
        string='Allocation Base',
        required=True,
        default=lambda self: self.env.company.l10n_ua_overhead_base or 'labour',
        tracking=True,
    )
    normal_base = fields.Float(
        string='Normal Capacity',
        digits='Product Price',
        default=lambda self: self.env.company.l10n_ua_overhead_normal_base,
        tracking=True,
        help='Value of the allocation base at normal capacity for the period. '
             'Zero: fixed overhead is allocated in full.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        check_company=True,
        domain="[('type', '=', 'general')]",
        default=lambda self: self._default_journal(),
    )
    variable_account_ids = fields.Many2many(
        'account.account',
        'l10n_ua_overhead_alloc_variable_rel',
        'allocation_id', 'account_id',
        string='Variable Overhead Accounts',
    )
    fixed_account_ids = fields.Many2many(
        'account.account',
        'l10n_ua_overhead_alloc_fixed_rel',
        'allocation_id', 'account_id',
        string='Fixed Overhead Accounts',
    )
    wip_account_id = fields.Many2one(
        'account.account', string='Work in Progress Account (23)')
    unallocated_account_id = fields.Many2one(
        'account.account', string='Unallocated Overhead Account (90x)')
    finished_account_id = fields.Many2one(
        'account.account', string='Finished Goods Account (26)')
    cogs_account_id = fields.Many2one(
        'account.account', string='Cost of Sales Account (901)')

    source_line_ids = fields.One2many(
        'l10n_ua.overhead.allocation.source', 'allocation_id',
        string='Overhead Balances', copy=False)
    line_ids = fields.One2many(
        'l10n_ua.overhead.allocation.line', 'allocation_id',
        string='Manufacturing Orders', copy=False)

    variable_amount = fields.Monetary(
        string='Variable Overhead', compute='_compute_amounts', store=True)
    fixed_amount = fields.Monetary(
        string='Fixed Overhead', compute='_compute_amounts', store=True)
    total_amount = fields.Monetary(
        string='Total Overhead', compute='_compute_amounts', store=True)
    actual_base = fields.Float(
        string='Actual Base', digits='Product Price',
        compute='_compute_amounts', store=True)
    allocation_rate = fields.Float(
        string='Fixed Overhead Rate', digits=(16, 4),
        compute='_compute_amounts', store=True,
        help='min(1, actual base / normal capacity): share of fixed overhead '
             'allocated to production.')
    fixed_allocated_amount = fields.Monetary(
        string='Fixed Overhead Allocated', compute='_compute_amounts', store=True)
    allocated_amount = fields.Monetary(
        string='Allocated to Production (23)', compute='_compute_amounts', store=True)
    unallocated_amount = fields.Monetary(
        string='Unallocated (90x)', compute='_compute_amounts', store=True)

    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)
    reversal_move_id = fields.Many2one(
        'account.move', string='Reversal Entry', readonly=True, copy=False)
    closing_id = fields.Many2one(
        'l10n_ua.period.closing', string='Posted by Closing',
        readonly=True, copy=False, index='btree_not_null')
    note = fields.Text(string='Notes')

    _check_dates = models.Constraint(
        'CHECK(date_from <= date_to)',
        'The period start must not be after its end.',
    )

    @api.model
    def _default_journal(self):
        company = self.env.company
        return company.l10n_ua_overhead_journal_id or self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'l10n_ua.overhead.allocation') or '/'
        records = super().create(vals_list)
        records._fill_default_accounts()
        return records

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_posted(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError(_('A posted overhead allocation cannot be deleted; cancel it first.'))

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def _fill_default_accounts(self):
        for rec in self:
            company = rec.company_id
            vals = {}
            variable, fixed = company._l10n_ua_overhead_accounts()
            if not rec.variable_account_ids and variable - rec.fixed_account_ids:
                variable -= rec.fixed_account_ids
                vals['variable_account_ids'] = [Command.set(variable.ids)]
            else:
                variable = rec.variable_account_ids
            if not rec.fixed_account_ids and fixed - variable:
                vals['fixed_account_ids'] = [Command.set((fixed - variable).ids)]
            defaults = {
                'wip_account_id': company.l10n_ua_overhead_wip_account_id
                or company._l10n_ua_find_account('231', '23'),
                'unallocated_account_id': company.l10n_ua_overhead_unallocated_account_id
                or company._l10n_ua_find_account('901', '90'),
                'finished_account_id': company.l10n_ua_overhead_finished_account_id
                or company._l10n_ua_find_account('26'),
                'cogs_account_id': company.l10n_ua_overhead_cogs_account_id
                or company.l10n_ua_overhead_unallocated_account_id
                or company._l10n_ua_find_account('901', '90'),
            }
            for field, account in defaults.items():
                if not rec[field] and account:
                    vals[field] = account.id
            if vals:
                rec.write(vals)

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    @api.depends('source_line_ids.amount', 'source_line_ids.kind',
                 'line_ids.base_value', 'normal_base', 'currency_id')
    def _compute_amounts(self):
        for rec in self:
            currency = rec.currency_id or self.env.company.currency_id
            variable = sum(rec.source_line_ids.filtered(
                lambda s: s.kind == 'variable').mapped('amount'))
            fixed = sum(rec.source_line_ids.filtered(
                lambda s: s.kind == 'fixed').mapped('amount'))
            actual = sum(rec.line_ids.mapped('base_value'))
            if float_is_zero(actual, precision_digits=6):
                # Nothing was produced: there is no object to carry the
                # overhead, the whole of it stays a period expense.
                rate, allocated_fixed, allocated = 0.0, 0.0, 0.0
            else:
                if rec.normal_base > 0:
                    rate = min(1.0, actual / rec.normal_base)
                else:
                    rate = 1.0
                allocated_fixed = currency.round(fixed * rate)
                allocated = currency.round(variable + allocated_fixed)
            rec.variable_amount = variable
            rec.fixed_amount = fixed
            rec.total_amount = variable + fixed
            rec.actual_base = actual
            rec.allocation_rate = rate
            rec.fixed_allocated_amount = allocated_fixed
            rec.allocated_amount = allocated
            rec.unallocated_amount = currency.round(variable + fixed - allocated)

    def _get_productions(self):
        """Manufacturing orders of the company finished within the period."""
        self.ensure_one()
        return self.env['mrp.production'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date_finished', '>=', datetime.combine(self.date_from, time.min)),
            ('date_finished', '<=', datetime.combine(self.date_to, time.max)),
        ], order='date_finished, id')

    def _get_account_balances(self, accounts):
        """Balance (debit - credit) of each account up to the period end.

        The cumulative balance, not the period turnover, is taken so that
        account 91 is left at zero even if an earlier month was not allocated.
        """
        self.ensure_one()
        if not accounts:
            return {}
        groups = self.env['account.move.line']._read_group([
            ('account_id', 'in', accounts.ids),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', self.date_to),
        ], ['account_id'], ['balance:sum'])
        return {account: balance for account, balance in groups}

    def action_compute(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only a draft allocation can be computed.'))
            rec._fill_default_accounts()
            currency = rec.currency_id
            overlap = rec.variable_account_ids & rec.fixed_account_ids
            if overlap:
                raise UserError(_(
                    'Account %s cannot be both variable and fixed overhead.',
                    ', '.join(overlap.mapped('display_name'))))
            sources = [Command.clear()]
            for kind, accounts in (('variable', rec.variable_account_ids),
                                   ('fixed', rec.fixed_account_ids)):
                for account, balance in rec._get_account_balances(accounts).items():
                    if not currency.is_zero(balance):
                        sources.append(Command.create({
                            'account_id': account.id,
                            'kind': kind,
                            'amount': currency.round(balance),
                        }))
            lines = [Command.clear()]
            for production in rec._get_productions():
                lines.append(Command.create({
                    'production_id': production.id,
                    'quantity': production.qty_produced,
                    'base_value': production._l10n_ua_overhead_base_value(rec.base),
                    'material_cost': currency.round(production._l10n_ua_material_cost()),
                    'labour_cost': currency.round(production._l10n_ua_labour_cost()),
                }))
            rec.write({'source_line_ids': sources, 'line_ids': lines})
            rec._distribute()
        return True

    def _distribute(self):
        """Spread the allocated amount over the orders in proportion to their
        base; the rounding difference goes to the largest line."""
        self.ensure_one()
        currency = self.currency_id
        lines = self.line_ids
        actual = self.actual_base
        if not lines or float_is_zero(actual, precision_digits=6):
            lines.write({'amount': 0.0, 'share': 0.0})
            return
        total = self.allocated_amount
        distributed = 0.0
        for line in lines:
            amount = currency.round(total * line.base_value / actual)
            line.write({'amount': amount, 'share': 100.0 * line.base_value / actual})
            distributed += amount
        diff = currency.round(total - distributed)
        if not currency.is_zero(diff):
            biggest = max(lines, key=lambda l: abs(l.base_value))
            biggest.amount += diff

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------

    def _check_can_post(self):
        self.ensure_one()
        missing = []
        if not self.wip_account_id:
            missing.append(_('work in progress (23)'))
        if not self.unallocated_account_id and not self.currency_id.is_zero(self.unallocated_amount):
            missing.append(_('unallocated overhead (90x)'))
        if missing:
            raise UserError(_('Set the accounts: %s.', ', '.join(missing)))
        overlapping = self.search([
            ('id', '!=', self.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
        ], limit=1)
        if overlapping:
            raise UserError(_(
                'Overhead allocation %(other)s already covers part of the period '
                '%(date_from)s - %(date_to)s.',
                other=overlapping.name, date_from=self.date_from, date_to=self.date_to))

    def _finished_account(self, product):
        accounts = product.product_tmpl_id.with_company(self.company_id).get_product_accounts()
        if product.with_company(self.company_id).valuation == 'real_time' \
                and accounts.get('stock_valuation'):
            return accounts['stock_valuation']
        return self.finished_account_id or accounts.get('stock_valuation')

    def _prepare_move_lines(self):
        self.ensure_one()
        currency = self.currency_id
        vals = []

        def add(account, amount, name, **extra):
            if currency.is_zero(amount):
                return
            vals.append(Command.create(dict(
                account_id=account.id,
                name=name,
                debit=amount if amount > 0 else 0.0,
                credit=-amount if amount < 0 else 0.0,
                **extra,
            )))

        for source in self.source_line_ids:
            add(source.account_id, -source.amount,
                _('Overhead %(account)s → allocation', account=source.account_id.code))
        add(self.wip_account_id, self.allocated_amount,
            _('Overhead allocated to production'))
        add(self.unallocated_account_id, self.unallocated_amount,
            _('Unallocated fixed overhead (NP(S)BO 16, item 16)'))
        for line in self.line_ids:
            if currency.is_zero(line.amount):
                continue
            label = _('Overhead: %s', line.production_id.name)
            finished = self._finished_account(line.product_id)
            if not finished:
                raise UserError(_(
                    'Set the finished goods account (26) for the allocation or a '
                    'stock valuation account for %s.', line.product_id.display_name))
            if not currency.is_zero(line.amount_sold) and not self.cogs_account_id:
                raise UserError(_('Set the cost of sales account (901).'))
            add(finished, line.amount_stock, label, product_id=line.product_id.id)
            add(self.cogs_account_id, line.amount_sold, label, product_id=line.product_id.id)
            add(self.wip_account_id, -line.amount, label, product_id=line.product_id.id)
        return vals

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only a draft allocation can be posted.'))
            rec.action_compute()
            rec._check_can_post()
            if rec.currency_id.is_zero(rec.total_amount):
                raise UserError(_('There is no overhead on the selected accounts '
                                  'up to %s.', rec.date_to))
            rec.line_ids._compute_stock_split()
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': rec.journal_id.id,
                'date': rec.date_to,
                'ref': _('Overhead allocation %s', rec.name),
                'company_id': rec.company_id.id,
                'line_ids': rec._prepare_move_lines(),
            })
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted', 'reversal_move_id': False})
            rec.line_ids._update_finished_value()
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only a posted allocation can be cancelled.'))
            closed = self.env['l10n_ua.period.closing'].search([
                ('id', '!=', self.env.context.get('l10n_ua_overhead_reversing_closing', 0)),
                ('company_id', '=', rec.company_id.id),
                ('state', '=', 'closed'),
                ('period_id.date_start', '<=', rec.date_to),
                ('period_id.date_end', '>=', rec.date_to),
            ], limit=1)
            if closed:
                raise UserError(_(
                    'The period is closed by %s; reverse the period closing first.',
                    closed.name))
            reversal = self.env['account.move']
            if rec.move_id and rec.move_id.state == 'posted':
                reversal = rec.move_id._reverse_moves(
                    default_values_list=[{
                        'date': rec.date_to,
                        'ref': _('Reversal of %s', rec.move_id.ref),
                    }],
                    cancel=True,
                )
            rec.write({'state': 'cancelled', 'reversal_move_id': reversal[:1].id,
                       'closing_id': False})
            rec.line_ids._update_finished_value()
        return True

    def _cancel_from_closing(self, closing):
        """Cancel the allocations posted by a period closing being reversed.

        The closing being reversed has already unlocked the period but is
        still in the closed state, hence the context key.
        """
        self.filtered(lambda r: r.state == 'posted').with_context(
            l10n_ua_overhead_reversing_closing=closing.id).action_cancel()

    def action_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only a cancelled allocation can be reset to draft.'))
        self.write({'state': 'draft', 'move_id': False, 'reversal_move_id': False})
        return True

    def action_open_moves(self):
        self.ensure_one()
        moves = self.move_id | self.reversal_move_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

    def action_open_productions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manufacturing Orders'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.production_id.ids)],
        }

    @api.constrains('variable_account_ids', 'fixed_account_ids')
    def _check_accounts_disjoint(self):
        for rec in self:
            if rec.variable_account_ids & rec.fixed_account_ids:
                raise ValidationError(_(
                    'An overhead account cannot be both variable and fixed.'))


class L10nUaOverheadAllocationSource(models.Model):
    _name = 'l10n_ua.overhead.allocation.source'
    _description = 'Production Overhead Balance'
    _order = 'kind desc, account_id'

    allocation_id = fields.Many2one(
        'l10n_ua.overhead.allocation', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='allocation_id.company_id', store=True)
    currency_id = fields.Many2one(related='allocation_id.currency_id')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    kind = fields.Selection(
        [('variable', 'Variable'), ('fixed', 'Fixed')], string='Behaviour', required=True)
    amount = fields.Monetary(string='Balance')


class L10nUaOverheadAllocationLine(models.Model):
    _name = 'l10n_ua.overhead.allocation.line'
    _description = 'Production Overhead Allocation Line'
    _order = 'allocation_id, id'

    allocation_id = fields.Many2one(
        'l10n_ua.overhead.allocation', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='allocation_id.company_id', store=True)
    currency_id = fields.Many2one(related='allocation_id.currency_id')
    state = fields.Selection(related='allocation_id.state', string='Status')
    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', required=True, index=True)
    product_id = fields.Many2one(
        related='production_id.product_id', store=True, string='Product')
    quantity = fields.Float(string='Quantity', digits='Product Unit')
    base_value = fields.Float(string='Base', digits='Product Price')
    share = fields.Float(string='Share (%)', digits=(16, 4))
    material_cost = fields.Monetary(string='Materials')
    labour_cost = fields.Monetary(string='Work Centers')
    amount = fields.Monetary(string='Overhead')
    amount_stock = fields.Monetary(
        string='To Stock (26)',
        help='Part of the overhead of products still in stock when posted.')
    amount_sold = fields.Monetary(
        string='To Cost of Sales',
        help='Part of the overhead of products already issued from stock when '
             'posted; their issue value is not re-valued, so this share is '
             'charged straight to the cost of sales.')
    valuation_adjusted = fields.Boolean(
        string='Stock Value Adjusted',
        help='The overhead is added to the value of the finished product move '
             '(products valued at average cost or FIFO). Products at standard '
             'price keep their value; the overhead is only in the accounts.')

    def _adjustable(self):
        return self.filtered(lambda l: l.product_id.cost_method in ('fifo', 'average'))

    def _compute_stock_split(self):
        """Split each line between stock (26) and cost of sales by the share
        of the finished quantity still in stock (FIFO stack)."""
        for line in self:
            currency = line.currency_id
            adjustable = line in line._adjustable()
            ratio = 1.0
            if adjustable:
                moves = line.production_id._l10n_ua_finished_moves()
                valued = sum(m._get_valued_qty() for m in moves)
                remaining = sum(moves.mapped('remaining_qty'))
                if valued > 0:
                    ratio = max(0.0, min(1.0, remaining / valued))
            stock = currency.round(line.amount * ratio)
            line.write({
                'amount_stock': stock,
                'amount_sold': currency.round(line.amount - stock),
                'valuation_adjusted': adjustable,
            })

    def _update_finished_value(self):
        """Re-value the finished product moves (adds or removes the overhead)."""
        moves = self.env['stock.move']
        for line in self._adjustable():
            moves |= line.production_id._l10n_ua_finished_moves()
        if moves:
            moves.sudo()._set_value()

    def _overhead_for_move(self, move, at_date=None):
        """Overhead of posted allocations attributable to one finished move."""
        lines = self.filtered(
            lambda l: l.allocation_id.state == 'posted'
            and (not at_date or l.allocation_id.date_to <= fields.Date.to_date(at_date)))
        if not lines:
            return 0.0
        moves = move.production_id._l10n_ua_finished_moves()
        total_qty = sum(m._get_valued_qty() for m in moves)
        if not total_qty:
            return 0.0
        return sum(lines.mapped('amount')) * move._get_valued_qty() / total_qty
