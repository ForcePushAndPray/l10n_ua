"""Extension of account.payment for Ukrainian cash orders (PKO/VKO)."""

from odoo import models, fields, api, _


class AccountPayment(models.Model):
    """Extend account.payment for Ukrainian cash orders.

    In Ukrainian accounting:
    - PKO (ПКО) = Прибутковий касовий ордер = Cash Receipt Order (inbound)
    - VKO (ВКО) = Видатковий касовий ордер = Cash Disbursement Order (outbound)

    Both use the standard account.payment model with cash journal.
    """
    _inherit = 'account.payment'

    # Ukrainian document number (КО-1 / КО-2 format)
    ua_cash_order_number = fields.Char(
        string='Cash Order Number',
        copy=False,
        help='Ukrainian cash order number (auto-generated for cash journals)',
    )

    # Basis for payment (підстава)
    ua_payment_basis = fields.Char(
        string='Payment Basis',
        help='Basis/reason for this cash operation (підстава)',
    )

    # Person who received/paid cash
    ua_cash_person = fields.Char(
        string='Cash Person',
        help='Person who received (for VKO) or paid (for PKO) cash',
    )

    # Person's document (passport, ID)
    ua_person_document = fields.Char(
        string='Person Document',
        help='Document of the person (passport, ID card)',
    )

    # Appendix documents
    ua_appendix = fields.Char(
        string='Appendix',
        help='List of appendix documents (додатки)',
    )

    # Computed field for Ukrainian document type
    ua_cash_order_type = fields.Selection(
        selection=[
            ('pko', 'ПКО (Прибутковий)'),
            ('vko', 'ВКО (Видатковий)'),
            ('other', 'Other'),
        ],
        string='Cash Order Type',
        compute='_compute_ua_cash_order_type',
        store=True,
    )

    # Is this a cash journal payment
    is_ua_cash_order = fields.Boolean(
        string='Is Cash Order',
        compute='_compute_is_ua_cash_order',
        store=True,
    )

    @api.depends('journal_id', 'journal_id.type')
    def _compute_is_ua_cash_order(self):
        for payment in self:
            payment.is_ua_cash_order = payment.journal_id.type == 'cash'

    @api.depends('payment_type', 'journal_id.type')
    def _compute_ua_cash_order_type(self):
        for payment in self:
            if payment.journal_id.type == 'cash':
                if payment.payment_type == 'inbound':
                    payment.ua_cash_order_type = 'pko'
                else:
                    payment.ua_cash_order_type = 'vko'
            else:
                payment.ua_cash_order_type = 'other'

    @api.model_create_multi
    def create(self, vals_list):
        """Generate Ukrainian cash order number for cash payments."""
        for vals in vals_list:
            if not vals.get('ua_cash_order_number'):
                journal_id = vals.get('journal_id')
                if journal_id:
                    journal = self.env['account.journal'].browse(journal_id)
                    if journal.type == 'cash':
                        payment_type = vals.get('payment_type', 'inbound')
                        if payment_type == 'inbound':
                            sequence = journal.ua_pko_sequence_id
                        else:
                            sequence = journal.ua_vko_sequence_id
                        if sequence:
                            vals['ua_cash_order_number'] = sequence.next_by_id()

        return super().create(vals_list)

    def action_print_pko(self):
        """Print PKO (Cash Receipt Order) form KO-1."""
        self.ensure_one()
        return self.env.ref('l10n_ua_accounting.action_report_pko').report_action(self)

    def action_print_vko(self):
        """Print VKO (Cash Disbursement Order) form KO-2."""
        self.ensure_one()
        return self.env.ref('l10n_ua_accounting.action_report_vko').report_action(self)
