from odoo import fields, models


OVERHEAD_BASES = [
    ('labour', 'Direct Labour Cost'),
    ('machine_hours', 'Machine Hours'),
    ('material', 'Direct Material Cost'),
    ('quantity', 'Quantity Produced'),
]

NORMAL_CAPACITY_HELP = (
    'Normal capacity for one month, in units of this allocation base. Fixed '
    'overhead is allocated to production in the ratio actual base / normal '
    'capacity, at most in full; the rest goes to the cost of sales. Zero '
    'means that fixed overhead is always allocated in full.'
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_overhead_base = fields.Selection(
        OVERHEAD_BASES,
        string='Overhead Allocation Base',
        default='labour',
        help='Base used to allocate production overhead (account 91) to '
             'manufacturing orders (NP(S)BO 16, item 15): work center cost, '
             'work center hours, cost of consumed components or quantity '
             'produced.',
    )
    # Normal capacity per month, one value per allocation base: the bases are
    # measured in different units (UAH, hours, units), so a single figure
    # would silently become wrong when the base is changed.
    l10n_ua_overhead_normal_labour = fields.Float(
        string='Normal Capacity: Direct Labour Cost (UAH)',
        digits='Product Price',
        help=NORMAL_CAPACITY_HELP,
    )
    l10n_ua_overhead_normal_machine_hours = fields.Float(
        string='Normal Capacity: Machine Hours',
        digits='Product Price',
        help=NORMAL_CAPACITY_HELP,
    )
    l10n_ua_overhead_normal_material = fields.Float(
        string='Normal Capacity: Direct Material Cost (UAH)',
        digits='Product Price',
        help=NORMAL_CAPACITY_HELP,
    )
    l10n_ua_overhead_normal_quantity = fields.Float(
        string='Normal Capacity: Quantity Produced',
        digits='Product Price',
        help=NORMAL_CAPACITY_HELP,
    )
    l10n_ua_overhead_variable_account_ids = fields.Many2many(
        'account.account',
        'l10n_ua_overhead_company_variable_rel',
        'company_id', 'account_id',
        string='Variable Overhead Accounts',
        help='Sub-accounts of 91 holding variable overhead, allocated to '
             'production in full.',
    )
    l10n_ua_overhead_fixed_account_ids = fields.Many2many(
        'account.account',
        'l10n_ua_overhead_company_fixed_rel',
        'company_id', 'account_id',
        string='Fixed Overhead Accounts',
        help='Sub-accounts of 91 holding fixed overhead, allocated at normal '
             'capacity. Empty: every account 91* that is not variable.',
    )
    l10n_ua_overhead_wip_account_id = fields.Many2one(
        'account.account',
        string='Work in Progress Account (23)',
    )
    l10n_ua_overhead_unallocated_account_id = fields.Many2one(
        'account.account',
        string='Unallocated Fixed Overhead Account (90x)',
        help='Cost of sales sub-account receiving the fixed overhead not '
             'allocated because production was below normal capacity '
             '(usually 901).',
    )
    l10n_ua_overhead_finished_account_id = fields.Many2one(
        'account.account',
        string='Finished Goods Account (26)',
        help='Used when the product has no perpetual stock valuation account.',
    )
    l10n_ua_overhead_cogs_account_id = fields.Many2one(
        'account.account',
        string='Cost of Sales Account (901)',
        help='Receives the overhead attributable to finished products already '
             'issued from stock when the allocation is posted.',
    )
    l10n_ua_overhead_journal_id = fields.Many2one(
        'account.journal',
        string='Overhead Allocation Journal',
        domain="[('type', '=', 'general')]",
    )
    l10n_ua_overhead_auto_allocate = fields.Boolean(
        string='Allocate Overhead on Period Closing',
        default=True,
        help='When closing a period with a balance on the overhead accounts '
             'and no posted allocation, create and post the allocation '
             'automatically. Off: the closing refuses until it is posted.',
    )

    def _l10n_ua_find_account(self, *prefixes):
        """First account of the company whose code starts with one of the
        prefixes, tried in order."""
        self.ensure_one()
        Account = self.env['account.account'].with_company(self)
        for prefix in prefixes:
            account = Account.search([
                ('code', '=like', prefix + '%'),
                ('company_ids', 'in', self.id),
                ('active', '=', True),
            ], order='code', limit=1)
            if account:
                return account
        return Account

    def _l10n_ua_overhead_normal_base(self, base):
        """Normal monthly capacity of the company for the given base."""
        self.ensure_one()
        field = 'l10n_ua_overhead_normal_%s' % (base or 'labour')
        return self[field] if field in self._fields else 0.0

    def _l10n_ua_overhead_accounts(self):
        """(variable, fixed) overhead accounts of the company.

        Variable accounts are only those configured. Fixed accounts are the
        configured ones, or else every account 91* that is not variable — so
        nothing on 91 is left behind and, by default, the whole overhead is
        treated as fixed (the cautious reading of NP(S)BO 16).
        """
        self.ensure_one()
        variable = self.l10n_ua_overhead_variable_account_ids
        fixed = self.l10n_ua_overhead_fixed_account_ids
        if not fixed:
            fixed = self.env['account.account'].with_company(self).search([
                ('code', '=like', '91%'),
                ('company_ids', 'in', self.id),
            ]) - variable
        return variable, fixed - variable
