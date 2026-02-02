"""Bank transaction auto-matching rules."""

from odoo import api, fields, models


class L10nUaBankMatchRule(models.Model):
    """Rule for automatically matching bank transactions to accounts.

    When a bank transaction matches a rule, the rule's counterpart account
    is used instead of the suspense account when creating journal entries.
    Rules are evaluated in sequence order; the first match wins.
    """
    _name = 'l10n_ua.bank.match.rule'
    _description = 'Bank Transaction Matching Rule'
    _order = 'sequence, id'

    name = fields.Char(
        string='Name',
        required=True,
        help='Rule description, e.g. "Оренда офісу", "ЄСВ", "Оплата від Альфа-Трейд"',
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(
        string='Priority',
        default=10,
        help='Lower number = higher priority. First matching rule wins.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        domain=[('type', '=', 'bank')],
        help='Limit rule to a specific bank journal. Leave empty for all journals.',
    )

    # --- Match conditions (AND logic) ---
    match_direction = fields.Selection(
        selection=[
            ('any', 'Any'),
            ('incoming', 'Incoming (+)'),
            ('outgoing', 'Outgoing (-)'),
        ],
        string='Direction',
        default='any',
        required=True,
    )
    match_partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        help='Match only transactions with this partner.',
    )
    match_partner_edrpou = fields.Char(
        string='Partner EDRPOU',
        help='Match by counterparty EDRPOU code.',
    )
    match_text = fields.Char(
        string='Contains Text',
        help='Case-insensitive substring match in payment reference and/or description.',
    )
    match_text_field = fields.Selection(
        selection=[
            ('any', 'Reference or Description'),
            ('payment_ref', 'Payment Reference only'),
            ('description', 'Description only'),
        ],
        string='Text Match In',
        default='any',
    )
    match_amount_min = fields.Float(
        string='Min Amount',
        help='Minimum absolute amount (0 = no limit).',
    )
    match_amount_max = fields.Float(
        string='Max Amount',
        help='Maximum absolute amount (0 = no limit).',
    )

    # --- Actions ---
    account_id = fields.Many2one(
        'account.account',
        string='Counterpart Account',
        required=True,
        help='Account to use instead of the suspense account.',
    )
    set_partner_id = fields.Many2one(
        'res.partner',
        string='Set Partner',
        help='Override the transaction partner with this value.',
    )
    label = fields.Char(
        string='Label',
        help='Override the journal entry line label.',
    )
    auto_post = fields.Boolean(
        string='Auto-Post',
        default=False,
        help='Automatically post the journal entry after creation.',
    )

    match_count = fields.Integer(
        string='Matches',
        compute='_compute_match_count',
    )

    def action_view_matched_transactions(self):
        """Open transactions matched by this rule."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Transactions: {self.name}',
            'res_model': 'l10n_ua.bank.transaction',
            'view_mode': 'list,form',
            'domain': [('matched_rule_id', '=', self.id)],
        }

    def _compute_match_count(self):
        """Count transactions matched by each rule."""
        data = self.env['l10n_ua.bank.transaction'].read_group(
            domain=[('matched_rule_id', 'in', self.ids)],
            fields=['matched_rule_id'],
            groupby=['matched_rule_id'],
        )
        counts = {d['matched_rule_id'][0]: d['matched_rule_id_count'] for d in data}
        for rule in self:
            rule.match_count = counts.get(rule.id, 0)

    def check_match(self, transaction):
        """Check if this rule matches a bank transaction.

        Args:
            transaction: l10n_ua.bank.transaction record (single)

        Returns:
            bool: True if all conditions match
        """
        self.ensure_one()

        # Journal filter
        if self.journal_id and self.journal_id != transaction.journal_id:
            return False

        # Direction
        if self.match_direction == 'incoming' and transaction.amount <= 0:
            return False
        if self.match_direction == 'outgoing' and transaction.amount >= 0:
            return False

        # Partner
        if self.match_partner_id and self.match_partner_id != transaction.partner_id:
            return False

        # EDRPOU
        if self.match_partner_edrpou:
            if (transaction.partner_edrpou or '').strip() != self.match_partner_edrpou.strip():
                return False

        # Text match
        if self.match_text:
            text = self.match_text.lower()
            matched = False
            if self.match_text_field in ('any', 'payment_ref'):
                if text in (transaction.payment_ref or '').lower():
                    matched = True
            if not matched and self.match_text_field in ('any', 'description'):
                if text in (transaction.description or '').lower():
                    matched = True
            if not matched:
                return False

        # Amount range
        abs_amount = abs(transaction.amount)
        if self.match_amount_min and abs_amount < self.match_amount_min:
            return False
        if self.match_amount_max and abs_amount > self.match_amount_max:
            return False

        return True
