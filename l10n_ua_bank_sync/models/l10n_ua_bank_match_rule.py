"""Bank transaction auto-matching rules.

DEPRECATED (Фаза 2 рефактора): цей кастомний рушій правил заміщується
рідним ``account.reconcile.model``. Native-виписки (Фаза 1) звіряються
рідним механізмом Odoo. Використайте ``action_convert_to_reconcile_model``,
щоб перенести правила у native; сам рушій лишиться до Фази 3 (чистка).
"""

from odoo import _, api, fields, models


class L10nUaBankMatchRule(models.Model):
    """Rule for automatically matching bank transactions to accounts.

    When a bank transaction matches a rule, the rule's counterpart account
    is used instead of the suspense account when creating journal entries.
    Rules are evaluated in sequence order; the first match wins.

    DEPRECATED: замінюється рідним ``account.reconcile.model`` (Фаза 2).
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

    def _to_reconcile_model_vals(self):
        """Мапінг кастомного правила у vals рідного account.reconcile.model.

        Обмеження: напрям (match_direction) не має прямого відповідника в
        Odoo 19 reconcile-моделі й не переноситься; текстовий критерій
        мапиться як 'contains'.
        """
        self.ensure_one()
        vals = {
            'name': self.name or _('Rule'),
            'sequence': self.sequence,
            'company_id': self.company_id.id or self.env.company.id,
            'active': self.active,
            'trigger': 'auto_reconcile' if self.auto_post else 'manual',
        }
        if self.journal_id:
            vals['match_journal_ids'] = [(6, 0, [self.journal_id.id])]
        if self.match_text:
            vals['match_label'] = 'contains'
            vals['match_label_param'] = self.match_text
        if self.match_amount_min and self.match_amount_max:
            vals['match_amount'] = 'between'
            vals['match_amount_min'] = self.match_amount_min
            vals['match_amount_max'] = self.match_amount_max
        elif self.match_amount_min:
            vals['match_amount'] = 'greater'
            vals['match_amount_min'] = self.match_amount_min
        elif self.match_amount_max:
            vals['match_amount'] = 'lower'
            vals['match_amount_max'] = self.match_amount_max
        partners = self.match_partner_id
        if self.match_partner_edrpou:
            found = self.env['res.partner'].search(
                [('edrpou', '=', self.match_partner_edrpou)], limit=1)
            partners |= found
        if partners:
            vals['match_partner_ids'] = [(6, 0, partners.ids)]
        if self.account_id:
            # «Встановити контрагента» переноситься на контрагента рядка-контрпари.
            vals['line_ids'] = [(0, 0, {
                'account_id': self.account_id.id,
                'partner_id': self.set_partner_id.id or False,
                'amount_type': 'percentage',
                'amount_string': '100',
                'label': self.label or self.name or '',
            })]
        return vals

    def action_convert_to_reconcile_model(self):
        """Створити рідні account.reconcile.model з обраних правил (Фаза 2)."""
        Model = self.env['account.reconcile.model']
        created = Model
        for rule in self:
            created |= Model.create(rule._to_reconcile_model_vals())
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reconciliation Models'),
            'res_model': 'account.reconcile.model',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }

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
