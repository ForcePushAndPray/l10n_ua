"""Target programs / funding sources of a non-profit organization (#374).

A program is the unit of target financing: a donor's grant, a charity
collection, membership fees, humanitarian aid. It owns an analytic account
(plan "Цільові програми"); the program is identified on journal items by that
analytic account:

* receipts — credit of account 48 with the program analytic
  (Дт 311/301/377 – Кт 48);
* spending — expense accounts (classes 8/9, see the company setting) with
  the program analytic (bills, payroll, depreciation …);
* recognition — Дт 48 – Кт 718 with the program analytic, posted by
  ``l10n_ua.npo.recognition`` (П(С)БО 15 «Дохід», п. 17).

All figures are read from posted journal items, so manual entries, reversals
and corrections are taken into account the same way as generated ones.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Рядки Частини І Звіту про використання доходів (прибутків) неприбуткової
# організації (наказ Мінфіну від 17.06.2016 № 553 у ред. наказу № 469).
INCOME_ROWS = [
    ('1.1', '1.1 Budget financing (general fund)'),
    ('1.2', '1.2 Special account balances carried over'),
    ('1.3', '1.3 Special fund income of a budget institution'),
    ('1.4', '1.4 Grants, subsidies, budget financing, technical assistance'),
    ('1.5', '1.5 Assets received for the statutory purposes'),
    ('1.6', '1.6 Gratuitous financial aid, voluntary donations'),
    ('1.6.1', '1.6.1 Charitable aid'),
    ('1.6.2', '1.6.2 Humanitarian aid (HD)'),
    ('1.6.3', '1.6.3 Funds and goods for the Defence Forces'),
    ('1.7', '1.7 Contributions of founders and members'),
    ('1.8', '1.8 Non-state pension contributions'),
    ('1.9', '1.9 Passive income'),
    ('1.10', '1.10 Assets received on termination of a legal entity'),
    ('1.11', '1.11 Other income'),
]
EXPENSE_ROWS = [
    ('2.1', '2.1 Budget institution expenses (general fund)'),
    ('2.2', '2.2 Budget institution expenses (special fund)'),
    ('2.3', '2.3 Maintenance and statutory activities'),
    ('2.4', '2.4 Gratuitous financial aid, donations given'),
    ('2.4.1', '2.4.1 Charitable aid given'),
    ('2.4.2', '2.4.2 Humanitarian aid given (HD)'),
    ('2.4.3', '2.4.3 Funds and goods given to the Defence Forces'),
    ('2.5', '2.5 Assets transferred on liquidation'),
    ('2.6', '2.6 Other expenses'),
]

FUNDING_TYPES = [
    ('charity', 'Charitable Aid'),
    ('donation', 'Voluntary Donations / Gratuitous Aid'),
    ('humanitarian', 'Humanitarian Aid'),
    ('grant', 'Grant / Technical Assistance / Budget Financing'),
    ('membership', 'Membership Fees'),
    ('statutory', 'Assets for Statutory Purposes'),
    ('other', 'Other'),
]
FUNDING_TYPE_ROW = {
    'charity': '1.6.1',
    'donation': '1.6',
    'humanitarian': '1.6.2',
    'grant': '1.4',
    'membership': '1.7',
    'statutory': '1.5',
    'other': '1.11',
}

TARGET_PREFIX = '48'
RESULT_PREFIX = '79'

LEDGER_KEYS = ('received', 'other_debit', 'transferred', 'recognised', 'spent')


def analytic_share(line, analytic_id):
    """Share (0..1) of a journal item that belongs to an analytic account.

    Distribution keys may combine accounts of several plans ("12,57").
    """
    share = 0.0
    key_id = str(analytic_id)
    for key, percentage in (line.analytic_distribution or {}).items():
        if key_id in str(key).split(','):
            share += (percentage or 0.0) / 100.0
    return share


class L10nUaNpoProgram(models.Model):
    _name = 'l10n_ua.npo.program'
    _description = 'Non-profit Target Program'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name'
    _check_company_auto = True

    name = fields.Char(string='Program', required=True, tracking=True)
    code = fields.Char(string='Code', tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active'), ('closed', 'Closed')],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    funding_type = fields.Selection(
        FUNDING_TYPES,
        string='Funding Type',
        required=True,
        default='charity',
        tracking=True,
    )
    income_row = fields.Selection(
        INCOME_ROWS,
        string='Income Row of the Report',
        compute='_compute_income_row',
        store=True,
        readonly=False,
        help='Row of Part I of the Report on the use of income where the '
             'income recognised on this program is shown.',
    )
    expense_row = fields.Selection(
        EXPENSE_ROWS,
        string='Expense Row of the Report',
        required=True,
        default='2.3',
        help='Row of Part I of the Report where the spending of this program '
             'is shown: 2.3 for the maintenance and statutory activities, '
             '2.4.x when the program gives aid to beneficiaries.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Donor',
        tracking=True,
        help='Donor / grantor / funding source. Empty for collections from '
             'many donors and membership fees.',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        readonly=True,
        copy=False,
        ondelete='restrict',
        check_company=True,
        help='Tag receipts on 48 and program expenses with this analytic '
             'account. Created with the program.',
    )
    account_id = fields.Many2one(
        'account.account',
        string='Target Financing Account',
        required=True,
        check_company=True,
        domain="[('code', '=like', '48%')]",
        default=lambda self: self.env.company.l10n_ua_npo_target_account_id,
        tracking=True,
    )
    income_account_id = fields.Many2one(
        'account.account',
        string='Recognised Income Account',
        required=True,
        check_company=True,
        default=lambda self: self.env.company.l10n_ua_npo_income_account_id,
        tracking=True,
        help='Credited when the target financing is recognised as income.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        check_company=True,
        domain="[('type', '=', 'general')]",
        help='Journal of the recognition entries of this program. Empty: the '
             'company target financing journal.',
    )
    date_start = fields.Date(string='Start Date', tracking=True)
    date_end = fields.Date(string='End Date', tracking=True)
    budget_amount = fields.Monetary(
        string='Budget',
        currency_field='currency_id',
        tracking=True,
        help='Planned amount of the program (grant agreement, estimate).',
    )
    note = fields.Html(string='Purpose and Conditions')

    # --- figures to date (all posted entries) ---
    amount_received = fields.Monetary(
        string='Received', compute='_compute_figures', currency_field='currency_id')
    amount_spent = fields.Monetary(
        string='Spent', compute='_compute_figures', currency_field='currency_id')
    amount_recognised = fields.Monetary(
        string='Recognised as Income', compute='_compute_figures',
        currency_field='currency_id')
    amount_balance = fields.Monetary(
        string='Balance on 48', compute='_compute_figures',
        currency_field='currency_id')
    amount_unrecognised = fields.Monetary(
        string='Expenses Not Yet Covered', compute='_compute_figures',
        currency_field='currency_id',
        help='Program expenses not yet matched by recognised income (the '
             'balance of 48 was not sufficient).')
    budget_remaining = fields.Monetary(
        string='Budget Remaining', compute='_compute_figures',
        currency_field='currency_id')

    _code_company_uniq = models.Constraint(
        'UNIQUE(code, company_id)',
        'The program code must be unique per company.',
    )

    @api.depends('funding_type')
    def _compute_income_row(self):
        for program in self:
            program.income_row = FUNDING_TYPE_ROW.get(program.funding_type, '1.11')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for program in self:
            if program.date_start and program.date_end \
                    and program.date_end < program.date_start:
                raise ValidationError(_('The program ends before it starts.'))

    @api.depends('analytic_account_id', 'account_id', 'income_account_id')
    def _compute_figures(self):
        programs = self.filtered('analytic_account_id')
        date_to = self.env.context.get('l10n_ua_npo_date') \
            or fields.Date.context_today(self)
        figures = programs._get_ledger_figures(date_to) if programs else {}
        for program in self:
            data = figures.get(program.id, dict.fromkeys(LEDGER_KEYS, 0.0))
            program.amount_received = data['received']
            program.amount_spent = data['spent']
            program.amount_recognised = data['recognised']
            program.amount_balance = (data['received'] - data['other_debit']
                                      - data['transferred'])
            program.amount_unrecognised = data['spent'] - data['recognised']
            program.budget_remaining = program.budget_amount - data['spent']

    # ------------------------------------------------------------------
    # Analytic account
    # ------------------------------------------------------------------
    @api.model
    def _get_analytic_plan(self):
        plan = self.env.ref('l10n_ua_nonprofit.analytic_plan_npo_programs',
                            raise_if_not_found=False)
        if not plan:
            plan = self.env['account.analytic.plan'].create({
                'name': 'Цільові програми',
                'default_applicability': 'optional',
            })
        return plan

    def _prepare_analytic_account_vals(self):
        self.ensure_one()
        return {
            'name': self.name,
            'code': self.code,
            'plan_id': self._get_analytic_plan().id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        programs = super().create(vals_list)
        for program in programs.filtered(lambda p: not p.analytic_account_id):
            program.analytic_account_id = self.env['account.analytic.account'].create(
                program._prepare_analytic_account_vals())
        return programs

    def write(self, vals):
        res = super().write(vals)
        sync = {key: vals[key] for key in ('name', 'code', 'partner_id') if key in vals}
        if sync:
            self.analytic_account_id.write(sync)
        return res

    def unlink(self):
        for program in self:
            if program.analytic_account_id and self.env['account.move.line'].search_count([
                ('analytic_distribution', 'in', program.analytic_account_id.ids),
            ], limit=1):
                raise UserError(_(
                    'Program %s has journal items and cannot be deleted. '
                    'Archive or close it instead.', program.name))
        analytic = self.analytic_account_id
        res = super().unlink()
        analytic.unlink()
        return res

    def action_activate(self):
        self.write({'state': 'active'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------
    @api.model
    def _get_closing_moves(self, companies):
        """Closing entries of the period closing (P&L → 79x → 44x)."""
        closings = self.env['l10n_ua.period.closing'].sudo().search([
            ('company_id', 'in', companies.ids),
            ('state', '=', 'closed'),
        ])
        return closings.closing_move_id | closings.retained_move_id

    def _get_ledger_figures(self, date_to, date_from=None):
        """Program figures from posted journal items.

        :returns: ``{program_id: {key: amount}}`` with keys

            * ``received`` — credits of 48 (receipts of target financing);
            * ``other_debit`` — debits of 48 other than the transfer to income
              (refunds to the donor, direct write-offs);
            * ``transferred`` — net debit of 48 in entries that also hit the
              program income account (the recognition entries and their
              reversals);
            * ``recognised`` — net credit of the program income account;
            * ``spent`` — net debit of the program expense accounts.
        """
        result = {program.id: dict.fromkeys(LEDGER_KEYS, 0.0) for program in self}
        programs = self.filtered('analytic_account_id')
        if not programs:
            return result
        by_analytic = {str(p.analytic_account_id.id): p for p in programs}
        companies = programs.company_id
        domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', 'in', companies.ids),
            ('analytic_distribution', 'in', programs.analytic_account_id.ids),
            ('date', '<=', date_to),
            ('move_id', 'not in', self._get_closing_moves(companies).ids),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        lines = self.env['account.move.line'].sudo().search(domain)
        prefixes = {c.id: c._l10n_ua_npo_expense_prefixes() for c in companies}
        for line in lines:
            code = line.account_id.with_company(line.company_id).code or ''
            analytic_ids = {
                analytic_id
                for key in (line.analytic_distribution or {})
                for analytic_id in str(key).split(',')
            }
            for analytic_id in analytic_ids:
                program = by_analytic.get(analytic_id)
                if not program or program.company_id != line.company_id:
                    continue
                share = analytic_share(line, analytic_id)
                vals = result[program.id]
                if code.startswith(TARGET_PREFIX):
                    if program.income_account_id in line.move_id.line_ids.account_id:
                        vals['transferred'] += (line.debit - line.credit) * share
                    else:
                        vals['received'] += line.credit * share
                        vals['other_debit'] += line.debit * share
                elif line.account_id == program.income_account_id:
                    vals['recognised'] += (line.credit - line.debit) * share
                elif code.startswith(prefixes[line.company_id.id]) \
                        and not code.startswith(RESULT_PREFIX):
                    vals['spent'] += (line.debit - line.credit) * share
        for program in self:
            currency = program.currency_id or self.env.company.currency_id
            vals = result[program.id]
            for key in LEDGER_KEYS:
                vals[key] = currency.round(vals[key])
        return result

    def _get_recognition_amounts(self, date):
        """Income to recognise on ``date`` per program (П(С)БО 15, п. 17).

        Income equals the program expenses not yet covered by recognised
        income, capped by the balance of 48 (a program cannot recognise more
        than it received). Expenses above the balance stay uncovered and are
        recognised later, once new receipts arrive. A negative amount gives
        income back to 48 (expenses were credited after recognition).

        :returns: ``{program_id: dict(spent, recognised, balance, amount)}``
        """
        figures = self._get_ledger_figures(date)
        res = {}
        for program in self:
            data = figures[program.id]
            balance = data['received'] - data['other_debit'] - data['transferred']
            uncovered = data['spent'] - data['recognised']
            if uncovered > 0:
                amount = min(uncovered, max(balance, 0.0))
            else:
                amount = uncovered
            res[program.id] = {
                'spent': data['spent'],
                'recognised': data['recognised'],
                'balance': balance,
                'amount': program.currency_id.round(amount),
            }
        return res

    def action_open_journal_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items: %s', self.name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('analytic_distribution', 'in', self.analytic_account_id.ids),
                ('parent_state', '=', 'posted'),
            ],
            'context': {'search_default_group_by_account': 1},
        }
