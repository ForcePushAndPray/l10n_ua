"""Non-profit organization settings of the company (#374).

Ознака неприбутковості — за структурою п. 4 Порядку ведення Реєстру
неприбуткових установ та організацій (постанова КМУ від 13.07.2016 № 440,
у редакції постанови КМУ від 27.12.2024 № 1514), групи — пп. 133.4.6 ПКУ.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

NONPROFIT_CODES = [
    ('0031', '0031 - Budget institutions'),
    ('0032', '0032 - Public associations'),
    ('0033', '0033 - Political parties'),
    ('0034', '0034 - Creative unions'),
    ('0035', '0035 - Religious organizations'),
    ('0036', '0036 - Charitable organizations'),
    ('0037', '0037 - Pension funds'),
    ('0038', '0038 - Unions'),
    ('0039', '0039 - Associations and other unions of legal entities'),
    ('0040', '0040 - Housing construction cooperatives'),
    ('0041', '0041 - Country house (dacha) cooperatives'),
    ('0042', '0042 - Gardening and garage cooperatives (societies)'),
    ('0043', '0043 - Associations of co-owners of apartment buildings'),
    ('0044', '0044 - Trade unions, their associations and organizations'),
    ('0045', '0045 - Employers organizations and their associations'),
    ('0046', '0046 - Agricultural service cooperatives'),
    ('0047', '0047 - Cooperative associations of agricultural service cooperatives'),
    ('0048', '0048 - Other legal entities meeting the requirements of para. 133.4 of the Tax Code'),
]

# Accounts created by the setup button when the chart has none.
# 48 "Цільове фінансування і цільові надходження" — рядок 1525 Балансу;
# 718 "Дохід від безоплатно одержаних оборотних активів" (Інструкція до
# Плану рахунків, наказ Мінфіну від 30.11.1999 № 291).
SETUP_ACCOUNTS = {
    'target': ('483', 'Благодійна допомога (цільові надходження)', 'liability_non_current'),
    'income': ('718', 'Дохід від безоплатно одержаних оборотних активів', 'income_other'),
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_is_nonprofit = fields.Boolean(
        string='Non-profit Organization',
        help='The company is included in the Register of non-profit institutions '
             'and organizations (para. 133.4 of the Tax Code of Ukraine) and '
             'files the Report on the use of income instead of the profit tax '
             'return.',
    )
    l10n_ua_nonprofit_code = fields.Selection(
        NONPROFIT_CODES,
        string='Non-profit Attribute Code',
        help='Non-profit attribute assigned by the tax authority when the '
             'organization was included in the Register (CMU resolution of '
             '13.07.2016 No. 440, para. 4).',
    )
    l10n_ua_nonprofit_register_date = fields.Date(
        string='Register Inclusion Date',
        help='Date of the decision to include the organization in the Register '
             'of non-profit institutions and organizations.',
    )
    l10n_ua_nonprofit_register_number = fields.Char(
        string='Register Decision Number',
        help='Number of the decision to include the organization in the Register.',
    )
    l10n_ua_npo_target_account_id = fields.Many2one(
        'account.account',
        string='Default Target Financing Account',
        domain="[('code', '=like', '48%')]",
        help='Account 48 "Target financing and target receipts" used by new '
             'programs.',
    )
    l10n_ua_npo_income_account_id = fields.Many2one(
        'account.account',
        string='Default Recognised Income Account',
        help='Income account credited when target financing is recognised as '
             'income (usually 718 or 719).',
    )
    l10n_ua_npo_journal_id = fields.Many2one(
        'account.journal',
        string='Target Financing Journal',
        domain="[('type', '=', 'general')]",
        help='Journal of the income recognition entries. Empty: the journal of '
             'the period closing.',
    )
    l10n_ua_npo_expense_prefixes = fields.Char(
        string='Program Expense Accounts',
        default='8,9',
        help='Comma-separated code prefixes of the expense accounts whose '
             'amounts, tagged with a program analytic account, count as '
             'program spending. If expenses are booked on class 8 and then '
             'moved to class 9, keep only one of the classes here, otherwise '
             'they are counted twice.',
    )
    l10n_ua_npo_recognise_on_closing = fields.Boolean(
        string='Recognise Target Income on Period Closing',
        default=True,
        help='Closing a month posts the recognition of target financing as '
             'income (Dr 48 - Cr 718) before the income and expense accounts '
             'are closed.',
    )

    def _l10n_ua_npo_expense_prefixes(self):
        self.ensure_one()
        prefixes = (self.l10n_ua_npo_expense_prefixes or '').replace(';', ',')
        return tuple(p.strip() for p in prefixes.split(',') if p.strip())

    @api.constrains('l10n_ua_npo_expense_prefixes')
    def _check_l10n_ua_npo_expense_prefixes(self):
        for company in self:
            for prefix in company._l10n_ua_npo_expense_prefixes():
                if not prefix.isdigit() or prefix.startswith(('4', '7')):
                    raise ValidationError(_(
                        'Program expense accounts must be code prefixes of '
                        'expense accounts (classes 8 and 9), got "%s".', prefix))

    def _l10n_ua_npo_find_or_create_account(self, key):
        self.ensure_one()
        code, name, account_type = SETUP_ACCOUNTS[key]
        Account = self.env['account.account'].with_company(self)
        domain = [('company_ids', 'in', self.id)]
        prefix = '48' if key == 'target' else code
        account = Account.search(domain + [('code', '=', code)], limit=1) \
            or Account.search(domain + [('code', '=like', prefix + '%')], order='code', limit=1)
        if not account:
            account = Account.create({
                'code': code,
                'name': name,
                'account_type': account_type,
                'company_ids': [(6, 0, self.ids)],
            })
        return account

    def action_l10n_ua_npo_setup(self):
        """Fill in the accounts and journal of a non-profit organization.

        Finds 48x/718 in the chart (or creates them when missing) and a
        general journal "Цільове фінансування".
        """
        for company in self:
            vals = {'l10n_ua_is_nonprofit': True}
            if not company.l10n_ua_npo_target_account_id:
                vals['l10n_ua_npo_target_account_id'] = \
                    company._l10n_ua_npo_find_or_create_account('target').id
            if not company.l10n_ua_npo_income_account_id:
                vals['l10n_ua_npo_income_account_id'] = \
                    company._l10n_ua_npo_find_or_create_account('income').id
            if not company.l10n_ua_npo_journal_id:
                Journal = self.env['account.journal']
                journal = Journal.search([
                    ('company_id', '=', company.id),
                    ('code', '=', 'NPO'),
                ], limit=1) or Journal.create({
                    'name': 'Цільове фінансування',
                    'code': 'NPO',
                    'type': 'general',
                    'company_id': company.id,
                })
                vals['l10n_ua_npo_journal_id'] = journal.id
            company.write(vals)
        return True
