from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ua_agro_rent_journal_id = fields.Many2one(
        related='company_id.l10n_ua_agro_rent_journal_id', readonly=False)
    l10n_ua_agro_rent_expense_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_rent_expense_account_id', readonly=False)
    l10n_ua_agro_rent_payable_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_rent_payable_account_id', readonly=False)
    l10n_ua_agro_pdfo_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_pdfo_account_id', readonly=False)
    l10n_ua_agro_military_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_military_account_id', readonly=False)
    l10n_ua_agro_in_kind_income_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_in_kind_income_account_id', readonly=False)
    l10n_ua_agro_pdfo_rate = fields.Float(
        related='company_id.l10n_ua_agro_pdfo_rate', readonly=False)
    l10n_ua_agro_military_rate = fields.Float(
        related='company_id.l10n_ua_agro_military_rate', readonly=False)
