from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ua_agro_valuation_method = fields.Selection(
        related='company_id.l10n_ua_agro_valuation_method', readonly=False)
    l10n_ua_agro_produce_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_produce_account_id', readonly=False)
    l10n_ua_agro_recognition_income_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_recognition_income_account_id', readonly=False)
    l10n_ua_agro_recognition_expense_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_recognition_expense_account_id', readonly=False)
    l10n_ua_agro_overhead_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_overhead_account_id', readonly=False)
