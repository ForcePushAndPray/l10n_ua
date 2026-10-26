from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_agro_operations_journal_id = fields.Many2one(
        'account.journal', string='Field Operations Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]")
    l10n_ua_agro_production_account_id = fields.Many2one(
        'account.account', string='Crop Production Account',
        help='Витрати рослинництва — 231 «Основне виробництво».')
    l10n_ua_agro_material_account_id = fields.Many2one(
        'account.account', string='Materials Account',
        help='Рахунок запасів, якщо в категорії товару не вказано рахунок оцінки (20х).')
    l10n_ua_agro_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Field Operations Warehouse',
        domain="[('company_id', '=', id)]")

    def _l10n_ua_agro_ops_account(self, field, prefixes):
        self.ensure_one()
        if self[field]:
            return self[field]
        Account = self.env['account.account']
        for prefix in prefixes:
            account = Account.search([
                ('code', '=like', prefix + '%'),
                ('company_ids', 'in', self.id),
                ('active', '=', True),
            ], order='code', limit=1)
            if account:
                return account
        return Account
