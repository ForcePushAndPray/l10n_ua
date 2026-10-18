"""Group of companies for consolidated statements (НП(С)БО 2)."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Settlement and loan accounts on which intra-group balances are eliminated
# (НП(С)БО 2, розд. II п. 4 пп. 2 — «внутрішньогрупове сальдо»).
DEFAULT_ELIMINATION_PREFIXES = '16,18,34,36,37,50,51,52,55,60,61,62,63,68'
DEFAULT_INVESTMENT_PREFIXES = '14'


class L10nUaConsolidationGroup(models.Model):
    _name = 'l10n_ua.consolidation.group'
    _description = 'Consolidation Group'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Group Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    parent_company_id = fields.Many2one(
        'res.company', string='Parent Company', required=True, tracking=True,
        default=lambda self: self.env.company,
        help='Parent company that prepares the consolidated statements of the group.')
    currency_id = fields.Many2one(
        'res.currency', related='parent_company_id.currency_id', string='Currency')
    member_ids = fields.One2many(
        'l10n_ua.consolidation.member', 'group_id', string='Subsidiaries', copy=True)
    company_ids = fields.Many2many(
        'res.company', relation='l10n_ua_consolidation_group_company_rel',
        column1='group_id', column2='company_id',
        string='All Companies', compute='_compute_company_ids', store=True,
        help='Parent company and all subsidiaries. Only users allowed in all of them can '
             'see and build the consolidated statements.')
    intragroup_partner_ids = fields.Many2many(
        'res.partner', relation='l10n_ua_consolidation_group_partner_rel',
        column1='group_id', column2='partner_id',
        string='Intra-group Partners',
        compute='_compute_intragroup_partner_ids', store=True, readonly=False,
        help='Partners that represent group companies. Journal items with these partners '
             '(or their contacts) are intra-group. Defaults to the partners of the member '
             'companies; add other partner records of the same companies if they exist.')
    elimination_account_prefixes = fields.Char(
        string='Intra-group Balance Accounts', required=True,
        default=DEFAULT_ELIMINATION_PREFIXES,
        help='Comma-separated account code prefixes (receivables, payables, loans) on which '
             'intra-group balances are eliminated. Income and expense accounts of Form 2 are '
             'always checked.')
    investment_account_prefixes = fields.Char(
        string='Investment Accounts', required=True, default=DEFAULT_INVESTMENT_PREFIXES,
        help='Account code prefixes of the parent company holding investments in '
             'subsidiaries (рах. 14).')
    note = fields.Text(string='Notes')

    _name_uniq = models.Constraint(
        'UNIQUE(name, parent_company_id)',
        'The group name must be unique per parent company.',
    )

    @api.depends('parent_company_id', 'member_ids.company_id')
    def _compute_company_ids(self):
        for group in self:
            group.company_ids = group.parent_company_id | group.member_ids.company_id

    @api.depends('parent_company_id', 'member_ids.company_id')
    def _compute_intragroup_partner_ids(self):
        for group in self:
            companies = group.parent_company_id | group.member_ids.company_id
            group.intragroup_partner_ids = group.intragroup_partner_ids | companies.partner_id

    @api.constrains('parent_company_id', 'member_ids')
    def _check_members(self):
        for group in self:
            if group.parent_company_id in group.member_ids.company_id:
                raise ValidationError(_(
                    'The parent company %s cannot be its own subsidiary.',
                    group.parent_company_id.name))

    # ── Helpers ─────────────────────────────────────────────

    def _check_user_companies(self):
        """The group spans several companies: the user must be allowed in all
        of them, otherwise the statements would silently miss data."""
        for group in self:
            if self.env.su:
                continue
            missing = group.company_ids - self.env.user.company_ids
            if missing:
                raise AccessError(_(
                    'You need access to all companies of the group "%(group)s" to build '
                    'consolidated statements. Missing: %(companies)s.',
                    group=group.name,
                    companies=', '.join(missing.mapped('name'))))

    def _check_currencies(self):
        """Foreign-currency subsidiaries are not translated (НП(С)БО 21):
        refuse instead of mixing currencies."""
        for group in self:
            wrong = group.member_ids.company_id.filtered(
                lambda c: c.currency_id != group.currency_id)
            if wrong:
                raise ValidationError(_(
                    'Companies %(companies)s keep their books in another currency than the '
                    'parent company (%(currency)s). Translation of foreign subsidiaries '
                    '(НП(С)БО 21) is not supported: prepare their statements in %(currency)s '
                    'and enter them as manual adjustments, or remove them from the group.',
                    companies=', '.join(wrong.mapped('name')),
                    currency=group.currency_id.name))

    def _prefix_list(self, field_name):
        self.ensure_one()
        return [p.strip() for p in (self[field_name] or '').split(',') if p.strip()]

    def action_open_reports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consolidated Statements'),
            'res_model': 'l10n_ua.consolidation.report',
            'view_mode': 'list,form',
            'domain': [('group_id', '=', self.id)],
            'context': {'default_group_id': self.id},
        }


class L10nUaConsolidationMember(models.Model):
    _name = 'l10n_ua.consolidation.member'
    _description = 'Consolidation Group Subsidiary'
    _order = 'group_id, sequence, id'

    group_id = fields.Many2one(
        'l10n_ua.consolidation.group', string='Group', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', string='Subsidiary', required=True)
    ownership_pct = fields.Float(
        string='Ownership %', required=True, default=100.0, digits=(5, 2),
        help="Parent company's share in the subsidiary's capital (votes). "
             'Non-controlling interest = 100 − this percentage.')
    nci_pct = fields.Float(
        string='Non-controlling Interest %', compute='_compute_nci_pct', digits=(5, 2))
    method = fields.Selection(
        [('full', 'Full consolidation')], string='Method', required=True, default='full',
        help='НП(С)БО 2 provides only for full consolidation of subsidiaries.')
    acquisition_date = fields.Date(
        string='Acquisition Date', required=True,
        help='Date control was obtained (НП(С)БО 19 п. 4). The equity of the subsidiary at '
             'this date is eliminated against the investment; results up to this date are '
             'not included in the consolidated statement of financial results.')
    investment_source = fields.Selection(
        [('journal', 'From parent journal items'), ('manual', 'Manual amount')],
        string='Investment Amount', required=True, default='journal',
        help='Journal items: balance of the parent on the investment accounts (рах. 14) '
             'with the subsidiary as partner on the report date.')
    investment_amount_manual = fields.Monetary(
        string='Investment (manual)', currency_field='currency_id')
    currency_id = fields.Many2one(related='group_id.currency_id')

    _company_uniq = models.Constraint(
        'UNIQUE(group_id, company_id)',
        'A company can be added to a group only once.',
    )
    _ownership_range = models.Constraint(
        'CHECK(ownership_pct > 0 AND ownership_pct <= 100)',
        'Ownership must be greater than 0 and at most 100 %.',
    )

    @api.depends('ownership_pct')
    def _compute_nci_pct(self):
        for member in self:
            member.nci_pct = 100.0 - member.ownership_pct
