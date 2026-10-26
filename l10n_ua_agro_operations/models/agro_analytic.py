from odoo import fields, models


class AgroField(models.Model):
    _inherit = 'l10n_ua.agro.field'

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', copy=False,
        help='Аналітичний рахунок поля (план «Поля»): на нього відносяться витрати.')

    def _l10n_ua_agro_analytic_account(self):
        self.ensure_one()
        if not self.analytic_account_id:
            self.analytic_account_id = self.env['account.analytic.account'].sudo().create({
                'name': self.display_name,
                'code': self.code,
                'plan_id': self.env.ref('l10n_ua_agro_operations.analytic_plan_agro_fields').id,
                'company_id': self.company_id.id,
            })
        return self.analytic_account_id


class AgroCrop(models.Model):
    _inherit = 'l10n_ua.agro.crop'

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', copy=False,
        help='Аналітичний рахунок культури (план «Культури»).')

    def _l10n_ua_agro_analytic_account(self, company=None):
        self.ensure_one()
        if not self.analytic_account_id:
            self.sudo().analytic_account_id = self.env['account.analytic.account'].sudo().create({
                'name': self.name,
                'code': self.code,
                'plan_id': self.env.ref('l10n_ua_agro_operations.analytic_plan_agro_crops').id,
                'company_id': False,
            })
        return self.analytic_account_id
