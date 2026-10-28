"""Consolidated statements run: forms № 1-к and № 2-к (НП(С)БО 2)."""

from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from odoo.addons.l10n_ua_accounting.models.l10n_ua_pnl_report import (
    pnl_amount, pnl_closing_move_domain,
)

from .consolidation_rows import (
    BALANCE_ROWS, BALANCE_ROW_BY_KEY, EQUITY_DETAIL_KEYS, PNL_ROWS, PNL_ROW_BY_KEY,
    balance_side, complete_balance, complete_pnl, match_balance_row, match_pnl_row,
)

ELIMINATION_KINDS = [
    ('intragroup', 'Intra-group balances and transactions'),
    ('cost_of_sales', 'Intra-group sales against cost of sales'),
    ('investment', 'Investment vs. subsidiary equity'),
    ('nci', 'Non-controlling interest'),
    ('manual', 'Manual adjustments'),
]
# Column order in the worksheet
_KIND_ORDER = {k: i for i, (k, _label) in enumerate(ELIMINATION_KINDS)}

_ROW_KEY_SELECTION = (
    [('b_' + r['key'], '%s %s' % (r['code'], r['name']))
     for r in BALANCE_ROWS if r['line_type'] == 'detail']
    + [('p_' + r['key'], '%s %s' % (r['code'], r['name']))
       for r in PNL_ROWS if r['line_type'] == 'detail']
)


class L10nUaConsolidationReport(models.Model):
    _name = 'l10n_ua.consolidation.report'
    _description = 'Consolidated Financial Statements'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    group_id = fields.Many2one(
        'l10n_ua.consolidation.group', string='Group', required=True, tracking=True,
        ondelete='restrict')
    parent_company_id = fields.Many2one(
        related='group_id.parent_company_id', store=True, string='Parent Company')
    currency_id = fields.Many2one(related='group_id.currency_id')
    date_from = fields.Date(
        string='Period Start', required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(
        string='Period End', required=True, tracking=True,
        default=fields.Date.context_today,
        help='Balance date of form 1-к and end of the period of form 2-к.')
    with_comparison = fields.Boolean(
        string='Comparison Column', default=True,
        help='1-к: balance at the start of the period (day before Period Start); '
             '2-к: the same period of the previous year.')
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed')],
        default='draft', required=True, tracking=True)
    line_ids = fields.One2many('l10n_ua.consolidation.line', 'report_id', string='Lines')
    balance_line_ids = fields.One2many(
        'l10n_ua.consolidation.line', 'report_id', string='Form 1-к',
        domain=[('form', '=', 'balance')])
    pnl_line_ids = fields.One2many(
        'l10n_ua.consolidation.line', 'report_id', string='Form 2-к',
        domain=[('form', '=', 'pnl')])
    cell_ids = fields.One2many('l10n_ua.consolidation.cell', 'report_id', string='Worksheet')
    adjustment_ids = fields.One2many(
        'l10n_ua.consolidation.adjustment', 'report_id', string='Manual Adjustments')
    total_assets = fields.Monetary(readonly=True, currency_field='currency_id')
    total_liabilities = fields.Monetary(
        string='Total Equity and Liabilities', readonly=True, currency_field='currency_id')
    balance_difference = fields.Monetary(
        readonly=True, currency_field='currency_id',
        help='Total assets − total equity and liabilities of form 1-к. Must be zero.')
    net_profit = fields.Monetary(readonly=True, currency_field='currency_id')
    nci_profit = fields.Monetary(
        string='Net Profit of Non-controlling Interest', readonly=True,
        currency_field='currency_id')
    nci_equity = fields.Monetary(
        string='Non-controlling Interest', readonly=True, currency_field='currency_id')
    warning_text = fields.Text(string='Warnings', readonly=True)
    note = fields.Text(string='Notes')

    @api.depends('group_id.name', 'date_to')
    def _compute_name(self):
        for rec in self:
            date_str = rec.date_to.strftime('%d.%m.%Y') if rec.date_to else ''
            rec.name = 'Консолідована звітність %s на %s' % (rec.group_id.name or '', date_str)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_('The period start must not be after its end.'))

    # ── Actions ─────────────────────────────────────────────

    def action_compute(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Cannot recalculate a confirmed report. Set it back to draft first.'))
            rec._compute_consolidation()

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Calculate the report before confirming.'))
            rec.state = 'confirmed'

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print_balance(self):
        self.ensure_one()
        self.group_id._check_user_companies()
        return self.env.ref('l10n_ua_consolidation.action_report_consolidated_balance').report_action(self)

    def action_print_pnl(self):
        self.ensure_one()
        self.group_id._check_user_companies()
        return self.env.ref('l10n_ua_consolidation.action_report_consolidated_pnl').report_action(self)

    def action_open_worksheet(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consolidation Worksheet'),
            'res_model': 'l10n_ua.consolidation.cell',
            'view_mode': 'pivot,list',
            'domain': [('report_id', '=', self.id)],
            'context': {'search_default_filter_current': 1, 'search_default_filter_balance': 1},
        }

    # ── Data sources ────────────────────────────────────────

    def _aml(self):
        """Journal items of all group companies (access checked beforehand)."""
        return self.env['account.move.line'].with_context(
            allowed_company_ids=self.group_id.company_ids.ids)

    @staticmethod
    def _account_codes(accounts, company):
        return {a.id: a.with_company(company).code or '' for a in accounts}

    def _intragroup_partner_ids(self, company):
        """Partners (with their contacts) that are intra-group for ``company``."""
        Partner = self.env['res.partner'].with_context(active_test=False)
        group_ids = set(Partner.search([('id', 'child_of', self.group_id.intragroup_partner_ids.ids)]).ids)
        own_ids = set(Partner.search([('id', 'child_of', company.partner_id.ids)]).ids)
        return group_ids - own_ids

    def _company_balance(self, company, date, ig_partner_ids=frozenset()):
        """Form 1-к detail amounts of one company at ``date``.

        Returns (details, intragroup, unmapped): ``intragroup`` is the part of
        each row booked on settlement/loan accounts against group partners.
        """
        prefixes = self.group_id._prefix_list('elimination_account_prefixes')
        groups = self._aml()._read_group(
            [('company_id', '=', company.id), ('parent_state', '=', 'posted'),
             ('date', '<=', date)],
            groupby=['account_id', 'partner_id'], aggregates=['balance:sum'])
        codes = self._account_codes(self.env['account.account'].browse({g[0].id for g in groups}), company)
        details = defaultdict(float)
        intragroup = defaultdict(float)
        unmapped = defaultdict(float)
        for account, partner, balance in groups:
            code = codes.get(account.id, '')
            if not code or code.startswith('0'):
                continue  # off-balance accounts (клас 0)
            key = match_balance_row(code, balance)
            if key is None:
                unmapped[code] += balance
                continue
            value = balance if balance_side(BALANCE_ROW_BY_KEY[key]) == 'asset' else -balance
            details[key] += value
            if partner.id in ig_partner_ids and any(code.startswith(p) for p in prefixes):
                intragroup[key] += value
        return details, intragroup, unmapped

    def _company_pnl(self, company, date_from, date_to, ig_partner_ids=frozenset()):
        """Form 2-к detail amounts of one company (Form 2 turnover rule:
        net turnover without the closing through 79, ``pnl_amount``)."""
        groups = self._aml()._read_group(
            [('company_id', '=', company.id), ('parent_state', '=', 'posted'),
             ('date', '>=', date_from), ('date', '<=', date_to)]
            + pnl_closing_move_domain(self.env, company, date_from, date_to),
            groupby=['account_id', 'partner_id'], aggregates=['debit:sum', 'credit:sum'])
        codes = self._account_codes(self.env['account.account'].browse({g[0].id for g in groups}), company)
        details = defaultdict(float)
        intragroup = defaultdict(float)
        for account, partner, debit, credit in groups:
            key = match_pnl_row(codes.get(account.id, ''))
            if key is None:
                continue
            value = pnl_amount(PNL_ROW_BY_KEY[key]['turnover'], debit, credit)
            details[key] += value
            if partner.id in ig_partner_ids:
                intragroup[key] += value
        return details, intragroup

    def _investment(self, member, date):
        """Parent's investment in ``member`` as {row_key: amount}."""
        if member.investment_source == 'manual':
            return {'lt_financial_investments': member.investment_amount_manual}
        parent = self.group_id.parent_company_id
        prefixes = self.group_id._prefix_list('investment_account_prefixes')
        groups = self._aml()._read_group(
            [('company_id', '=', parent.id), ('parent_state', '=', 'posted'),
             ('date', '<=', date),
             ('partner_id', 'child_of', member.company_id.partner_id.ids)],
            groupby=['account_id'], aggregates=['balance:sum'])
        codes = self._account_codes(self.env['account.account'].browse({g[0].id for g in groups}), parent)
        result = defaultdict(float)
        for account, balance in groups:
            code = codes.get(account.id, '')
            if any(code.startswith(p) for p in prefixes):
                key = match_balance_row(code, balance) or 'lt_financial_investments'
                result[key] += balance
        return result

    # ── Consolidation ───────────────────────────────────────

    def _members_for_balance(self, date):
        return self.group_id.member_ids.filtered(lambda m: m.acquisition_date <= date)

    def _consolidate_balance(self, date, period, warnings):
        """Return {column: {row_key: amount}} for form 1-к at ``date``.

        Columns: ('company', company) and ('elimination', kind, company|None).
        """
        group = self.group_id
        rounding = self.currency_id.rounding
        members = self._members_for_balance(date)
        companies = group.parent_company_id | members.company_id
        columns = {}
        elim = defaultdict(lambda: defaultdict(float))  # (kind, company) -> key -> amount
        ig_totals = {'asset': 0.0, 'liability': 0.0}
        for company in companies:
            details, intragroup, unmapped = self._company_balance(
                company, date, self._intragroup_partner_ids(company))
            columns[('company', company)] = details
            for key, value in intragroup.items():
                elim[('intragroup', company)][key] -= value
                ig_totals[balance_side(BALANCE_ROW_BY_KEY[key])] += value
            unmapped = {c: v for c, v in unmapped.items() if not float_is_zero(v, precision_rounding=rounding)}
            if unmapped:
                warnings.append(_(
                    '%(company)s, %(date)s: accounts not mapped to form 1-к rows: %(accounts)s.',
                    company=company.name, date=date,
                    accounts=', '.join('%s (%.2f)' % (c, v) for c, v in sorted(unmapped.items()))))
        mismatch = ig_totals['asset'] - ig_totals['liability']
        if not float_is_zero(mismatch, precision_rounding=rounding):
            warnings.append(_(
                '%(date)s: intra-group receivables (%(assets).2f) and payables (%(liabilities).2f) '
                'do not match (difference %(diff).2f). Reconcile them or add a manual adjustment '
                '(goods/cash in transit).',
                date=date, assets=ig_totals['asset'], liabilities=ig_totals['liability'], diff=mismatch))

        for member in members:
            sub = member.company_id
            share = member.ownership_pct / 100.0
            nci_share = 1.0 - share
            sub_now = columns[('company', sub)]
            sub_acq = self._company_balance(sub, member.acquisition_date)[0]
            investment = self._investment(member, date)
            invested = sum(investment.values())
            equity_acq = sum(sub_acq.get(k, 0.0) for k in EQUITY_DETAIL_KEYS)
            bucket = elim[('investment', sub)]
            # НП(С)БО 2 розд. II п. 4 пп. 1: інвестиція материнського vs частка в капіталі
            for key, value in investment.items():
                bucket[key] -= value
            for key in EQUITY_DETAIL_KEYS:
                bucket[key] -= sub_acq.get(key, 0.0)
            bucket['nci'] += nci_share * equity_acq
            goodwill = invested - share * equity_acq
            if goodwill >= 0:
                bucket['goodwill'] += goodwill
            else:
                # НП(С)БО 19 п. 13: перевищення визнається доходом на дату придбання
                bucket['retained_earnings'] -= goodwill
            if float_is_zero(invested, precision_rounding=rounding):
                warnings.append(_(
                    '%(company)s: no investment of the parent company found on accounts %(accounts)s '
                    'with this partner — set the investment amount manually on the group.',
                    company=sub.name, accounts=group.investment_account_prefixes))
            # Неконтрольована частка у змінах капіталу після придбання
            nci_bucket = elim[('nci', sub)]
            for key in EQUITY_DETAIL_KEYS:
                delta = sub_now.get(key, 0.0) - sub_acq.get(key, 0.0)
                if delta:
                    nci_bucket[key] -= nci_share * delta
                    nci_bucket['nci'] += nci_share * delta

        for adj in self.adjustment_ids.filtered(lambda a: a.form == 'balance' and a.period == period):
            elim[('manual', adj.company_id)][adj.row_key[2:]] += adj.amount

        for (kind, company), values in elim.items():
            columns[('elimination', kind, company)] = values
        return columns

    def _consolidate_pnl(self, date_from, date_to, period, warnings):
        """Return ({column: {row_key: amount}}, nci_profit) for form 2-к."""
        group = self.group_id
        rounding = self.currency_id.rounding
        columns = {}
        elim = defaultdict(lambda: defaultdict(float))
        periods = [(group.parent_company_id, date_from, None)]
        for member in group.member_ids:
            start = max(date_from, member.acquisition_date + timedelta(days=1))
            if start <= date_to:
                periods.append((member.company_id, start, member))
        income = expense = revenue = 0.0
        nci_profit = 0.0
        for company, start, member in periods:
            details, intragroup = self._company_pnl(
                company, start, date_to, self._intragroup_partner_ids(company))
            columns[('company', company)] = details
            for key, value in intragroup.items():
                elim[('intragroup', company)][key] -= value
                if PNL_ROW_BY_KEY[key]['turnover'] == 'credit':
                    income += value
                else:
                    expense += value
            revenue += intragroup.get('net_revenue', 0.0)
            if member:
                nci_profit += (1.0 - member.ownership_pct / 100.0) * complete_pnl(details)['net_profit']

        # Intra-group revenue whose counterpart is not an intra-group expense of
        # the buyer (goods capitalised into inventory and later sold) is
        # eliminated against cost of sales: the group earns nothing on it.
        unmatched = income - expense
        if unmatched > 0 and not float_is_zero(unmatched, precision_rounding=rounding):
            against_cost = min(unmatched, revenue)
            if not float_is_zero(against_cost, precision_rounding=rounding):
                elim[('cost_of_sales', None)]['cost_of_sales'] -= against_cost
            rest = unmatched - against_cost
            if not float_is_zero(rest, precision_rounding=rounding):
                warnings.append(_(
                    '%(start)s – %(end)s: intra-group income %(amount).2f has no intra-group expense '
                    'counterpart (e.g. dividends from subsidiaries). It is eliminated and reduces '
                    'the consolidated result — check it and add a manual adjustment if needed.',
                    start=date_from, end=date_to, amount=rest))
        elif unmatched < 0 and not float_is_zero(unmatched, precision_rounding=rounding):
            warnings.append(_(
                '%(start)s – %(end)s: intra-group expenses exceed intra-group income by %(amount).2f '
                '(the seller did not book the income against a group partner?). Check and add a '
                'manual adjustment.', start=date_from, end=date_to, amount=-unmatched))

        # Negative goodwill of an acquisition inside the period (НП(С)БО 19 п. 13)
        for member in group.member_ids.filtered(lambda m: date_from <= m.acquisition_date <= date_to):
            sub_acq = self._company_balance(member.company_id, member.acquisition_date)[0]
            equity_acq = sum(sub_acq.get(k, 0.0) for k in EQUITY_DETAIL_KEYS)
            goodwill = sum(self._investment(member, date_to).values()) \
                - member.ownership_pct / 100.0 * equity_acq
            if goodwill < 0:
                elim[('investment', member.company_id)]['other_income'] -= goodwill

        for adj in self.adjustment_ids.filtered(lambda a: a.form == 'pnl' and a.period == period):
            elim[('manual', adj.company_id)][adj.row_key[2:]] += adj.amount

        for (kind, company), values in elim.items():
            columns[('elimination', kind, company)] = values
        return columns, nci_profit

    def _compute_consolidation(self):
        self.ensure_one()
        group = self.group_id
        group._check_user_companies()
        group._check_currencies()
        warnings = []
        runs = [('current', self.date_to, self.date_from, self.date_to)]
        if self.with_comparison:
            runs.append(('previous', self.date_from - timedelta(days=1),
                         self.date_from - relativedelta(years=1),
                         self.date_to - relativedelta(years=1)))

        self.cell_ids.unlink()
        self.line_ids.unlink()
        Line = self.env['l10n_ua.consolidation.line']
        lines = {}
        line_vals = []
        for form, rows in (('balance', BALANCE_ROWS), ('pnl', PNL_ROWS)):
            for row in rows:
                line_vals.append({
                    'report_id': self.id,
                    'form': form,
                    'sequence': row['sequence'],
                    'row_key': row['key'],
                    'code': row['code'],
                    'name': row['name'],
                    'line_type': row['line_type'],
                    'section': row['section'],
                    'expense': form == 'pnl' and row.get('turnover') == 'debit',
                })
        for line in Line.create(line_vals):
            lines[(line.form, line.row_key)] = line

        totals = {}
        line_amounts = defaultdict(dict)
        cell_vals = []
        for period, bal_date, pnl_from, pnl_to in runs:
            bal_columns = self._consolidate_balance(bal_date, period, warnings)
            pnl_columns, nci_profit = self._consolidate_pnl(pnl_from, pnl_to, period, warnings)
            for form, columns, complete in (('balance', bal_columns, complete_balance),
                                            ('pnl', pnl_columns, complete_pnl)):
                consolidated = defaultdict(float)
                company_sum = defaultdict(float)
                elim_sum = defaultdict(float)
                for column, values in columns.items():
                    full = complete(values)
                    for key, value in values.items():
                        consolidated[key] += value
                    target = company_sum if column[0] == 'company' else elim_sum
                    for key, value in full.items():
                        target[key] += value
                    cell_vals += self._cell_vals(lines, form, period, column, full)
                full = complete(consolidated)
                if form == 'pnl':
                    full['np_nci'] = nci_profit
                    full['np_owners'] = full['net_profit'] - nci_profit
                cell_vals += self._cell_vals(lines, form, period, ('consolidated',), full)
                for key, value in full.items():
                    line_amounts[(form, key)][period] = value
                    if period == 'current':
                        line_amounts[(form, key)]['companies'] = company_sum.get(key, 0.0)
                        line_amounts[(form, key)]['eliminations'] = elim_sum.get(key, 0.0)
                totals[(form, period)] = full

        for (form, key), values in line_amounts.items():
            lines[(form, key)].write({
                'current_amount': values.get('current', 0.0),
                'previous_amount': values.get('previous', 0.0),
                'companies_amount': values.get('companies', 0.0),
                'elimination_amount': values.get('eliminations', 0.0),
            })
        self.env['l10n_ua.consolidation.cell'].create(cell_vals)

        bal = totals[('balance', 'current')]
        pnl = totals[('pnl', 'current')]
        difference = bal['total_assets'] - bal['total_liabilities']
        if not self.currency_id.is_zero(difference):
            warnings.append(_(
                'Form 1-к does not balance: assets − equity and liabilities = %.2f. '
                'See the warnings above (unmapped accounts, unmatched intra-group balances, '
                'one-sided manual adjustments).', difference))
        self.write({
            'total_assets': bal['total_assets'],
            'total_liabilities': bal['total_liabilities'],
            'balance_difference': difference,
            'net_profit': pnl['net_profit'],
            'nci_profit': pnl['np_nci'],
            'nci_equity': bal['nci'],
            'warning_text': '\n'.join(dict.fromkeys(str(w) for w in warnings)) or False,
        })

    def _cell_vals(self, lines, form, period, column, amounts):
        vals = []
        kind = column[0]
        company = False
        elimination_kind = False
        if kind == 'company':
            company = column[1]
            sequence = 10 + (0 if company == self.group_id.parent_company_id
                             else 1 + self.group_id.member_ids.company_id.ids.index(company.id))
            label = '%02d %s' % (sequence, company.name)
        elif kind == 'elimination':
            elimination_kind, company = column[1], column[2]
            sequence = 500 + _KIND_ORDER[elimination_kind]
            kind_label = dict(self.env['l10n_ua.consolidation.cell']._fields['elimination_kind']
                              ._description_selection(self.env))[elimination_kind]
            label = '%s %s' % (sequence, kind_label)
        else:
            sequence = 900
            label = '%s %s' % (sequence, _('Consolidated'))
        rounding = self.currency_id.rounding
        for key, value in amounts.items():
            line = lines.get((form, key))
            if not line or line.line_type == 'section':
                continue
            if kind != 'consolidated' and float_is_zero(value, precision_rounding=rounding) \
                    and kind != 'company':
                continue
            vals.append({
                'report_id': self.id,
                'line_id': line.id,
                'period': period,
                'column_type': kind,
                'elimination_kind': elimination_kind,
                'company_id': company.id if company else False,
                'column_sequence': sequence,
                'column_label': label,
                'amount': value,
            })
        return vals

    # ── Printing helpers ────────────────────────────────────

    def _get_form_lines(self, form):
        self.ensure_one()
        return self.line_ids.filtered(lambda l: l.form == form).sorted('sequence')

    @api.model
    def _fmt_amount(self, value, brackets=False):
        """Whole hryvnias with a space as thousands separator; expenses and
        negative values in brackets, as on the official forms."""
        value = round(value or 0.0)
        if not value:
            return '–'
        text = '{:,.0f}'.format(abs(value)).replace(',', '\u00a0')
        return '(%s)' % text if brackets or value < 0 else text


class L10nUaConsolidationLine(models.Model):
    _name = 'l10n_ua.consolidation.line'
    _description = 'Consolidated Statement Row'
    _order = 'form, sequence, id'

    report_id = fields.Many2one(
        'l10n_ua.consolidation.report', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='report_id.currency_id')
    form = fields.Selection([('balance', 'Form 1-к'), ('pnl', 'Form 2-к')], required=True)
    sequence = fields.Integer()
    row_key = fields.Char(required=True)
    code = fields.Char(string='Row Code')
    name = fields.Char(string='Line Name')
    line_type = fields.Selection([
        ('section', 'Section Header'),
        ('detail', 'Detail'),
        ('subtotal', 'Subtotal'),
        ('total', 'Total'),
        ('attribution', 'Attribution'),
    ], default='detail')
    section = fields.Char()
    expense = fields.Boolean(help='Expense row of form 2-к, printed in brackets.')
    companies_amount = fields.Monetary(
        string='Sum of Companies', currency_field='currency_id')
    elimination_amount = fields.Monetary(string='Eliminations', currency_field='currency_id')
    current_amount = fields.Monetary(string='Consolidated', currency_field='currency_id')
    previous_amount = fields.Monetary(string='Comparison', currency_field='currency_id')


class L10nUaConsolidationCell(models.Model):
    """Worksheet cell: one row of a form × one column (company / elimination /
    consolidated) × period. Used by the pivot view."""
    _name = 'l10n_ua.consolidation.cell'
    _description = 'Consolidation Worksheet Cell'
    _order = 'form, row_sequence, column_sequence, id'

    report_id = fields.Many2one(
        'l10n_ua.consolidation.report', required=True, ondelete='cascade', index=True)
    line_id = fields.Many2one('l10n_ua.consolidation.line', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='report_id.currency_id')
    form = fields.Selection(related='line_id.form', store=True)
    row_sequence = fields.Integer(related='line_id.sequence', store=True)
    row_label = fields.Char(compute='_compute_row_label', store=True, string='Row')
    period = fields.Selection(
        [('current', 'Reporting Period'), ('previous', 'Comparison Period')], required=True)
    column_type = fields.Selection([
        ('company', 'Company'),
        ('elimination', 'Elimination'),
        ('consolidated', 'Consolidated'),
    ], required=True)
    elimination_kind = fields.Selection(ELIMINATION_KINDS)
    company_id = fields.Many2one('res.company', string='Company')
    column_sequence = fields.Integer()
    column_label = fields.Char(string='Column')
    amount = fields.Monetary(currency_field='currency_id')

    @api.depends('line_id.code', 'line_id.name', 'line_id.sequence')
    def _compute_row_label(self):
        for cell in self:
            line = cell.line_id
            cell.row_label = '%04d %s %s' % (line.sequence, line.code or '', line.name or '')


class L10nUaConsolidationAdjustment(models.Model):
    _name = 'l10n_ua.consolidation.adjustment'
    _description = 'Consolidation Manual Adjustment'
    _order = 'report_id, form, id'

    report_id = fields.Many2one(
        'l10n_ua.consolidation.report', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='report_id.currency_id')
    period = fields.Selection(
        [('current', 'Reporting Period'), ('previous', 'Comparison Period')],
        required=True, default='current')
    form = fields.Selection(
        [('balance', 'Form 1-к'), ('pnl', 'Form 2-к')], required=True, default='balance')
    row_key = fields.Selection(_ROW_KEY_SELECTION, string='Row', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        help='Group company the adjustment relates to (for information).')
    amount = fields.Monetary(
        required=True, currency_field='currency_id',
        help='Change of the row as printed: positive increases the row, negative decreases it. '
             'For form 1-к keep assets and equity/liabilities balanced (e.g. unrealised profit '
             'in inventory: 1100 −X and 1420 −X; form 2-к: 2050 +X).')
    name = fields.Char(string='Explanation', required=True)

    @api.constrains('form', 'row_key')
    def _check_row_form(self):
        for adj in self:
            if adj.row_key and adj.row_key[:2] != ('b_' if adj.form == 'balance' else 'p_'):
                raise UserError(_('The row "%s" does not belong to the selected form.', adj.row_key))
