"""Extension of account.journal for Ukrainian cash order sequences."""

from odoo import models, fields, api


class AccountJournal(models.Model):
    """Extend account.journal with Ukrainian cash order sequences."""
    _inherit = 'account.journal'

    # Sequence for PKO (Cash Receipt Orders)
    ua_pko_sequence_id = fields.Many2one(
        'ir.sequence',
        string='PKO Sequence',
        help='Sequence for Ukrainian Cash Receipt Orders (ПКО)',
        copy=False,
    )

    # Sequence for VKO (Cash Disbursement Orders)
    ua_vko_sequence_id = fields.Many2one(
        'ir.sequence',
        string='VKO Sequence',
        help='Sequence for Ukrainian Cash Disbursement Orders (ВКО)',
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create PKO/VKO sequences for cash journals."""
        journals = super().create(vals_list)

        for journal in journals:
            if journal.type == 'cash':
                journal._create_ua_cash_sequences()

        return journals

    def _create_ua_cash_sequences(self):
        """Create Ukrainian cash order sequences for this journal."""
        self.ensure_one()
        if self.type != 'cash':
            return

        IrSequence = self.env['ir.sequence']

        # Create PKO sequence if not exists
        if not self.ua_pko_sequence_id:
            pko_sequence = IrSequence.create({
                'name': f'ПКО - {self.name}',
                'code': f'ua.pko.{self.code or self.id}',
                'prefix': 'ПКО-',
                'padding': 5,
                'company_id': self.company_id.id,
            })
            self.ua_pko_sequence_id = pko_sequence

        # Create VKO sequence if not exists
        if not self.ua_vko_sequence_id:
            vko_sequence = IrSequence.create({
                'name': f'ВКО - {self.name}',
                'code': f'ua.vko.{self.code or self.id}',
                'prefix': 'ВКО-',
                'padding': 5,
                'company_id': self.company_id.id,
            })
            self.ua_vko_sequence_id = vko_sequence

    def action_create_ua_sequences(self):
        """Manual action to create UA sequences for existing cash journals."""
        for journal in self:
            if journal.type == 'cash':
                journal._create_ua_cash_sequences()
        return True
