from odoo import api, fields, models


class L10nUaAgreement(models.Model):
    _inherit = 'l10n_ua.agreement'

    l10n_ua_foreign_trade = fields.Boolean(
        string='Foreign Trade Contract', tracking=True,
        help='Зовнішньоекономічний договір (контракт) — для митного оформлення й валютного контролю.')
    l10n_ua_incoterm_id = fields.Many2one('account.incoterms', string='Incoterms', tracking=True)
    l10n_ua_incoterm_place = fields.Char(string='Incoterms Place')
    l10n_ua_settlement_days = fields.Integer(
        string='Settlement Deadline (days)', tracking=True,
        compute='_compute_settlement_days', store=True, readonly=False,
        help='Граничний строк розрахунків за експортом з дати митного оформлення.')
    l10n_ua_customs_declaration_ids = fields.One2many(
        'l10n_ua.customs.declaration', 'agreement_id', string='Customs Declarations')

    @api.depends('l10n_ua_foreign_trade', 'company_id')
    def _compute_settlement_days(self):
        for agreement in self:
            if agreement.l10n_ua_foreign_trade and not agreement.l10n_ua_settlement_days:
                agreement.l10n_ua_settlement_days = agreement.company_id.l10n_ua_export_settlement_days
