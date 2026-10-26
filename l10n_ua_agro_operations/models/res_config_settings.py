from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ua_agro_operations_journal_id = fields.Many2one(
        related='company_id.l10n_ua_agro_operations_journal_id', readonly=False)
    l10n_ua_agro_production_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_production_account_id', readonly=False)
    l10n_ua_agro_material_account_id = fields.Many2one(
        related='company_id.l10n_ua_agro_material_account_id', readonly=False)
    l10n_ua_agro_warehouse_id = fields.Many2one(
        related='company_id.l10n_ua_agro_warehouse_id', readonly=False)
