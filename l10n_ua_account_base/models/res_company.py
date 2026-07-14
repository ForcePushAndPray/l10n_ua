"""Company-level Ukrainian flag driving UA-company gating (issue #178)."""

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ua_is_ua_company = fields.Boolean(
        string='Українська компанія',
        compute='_compute_l10n_ua_is_ua_company',
        store=True,
        help='Компанія зареєстрована в Україні (країна = Україна). '
             'Використовується, щоб приховувати UA-специфічний функціонал '
             '(меню/звіти/кнопки) у не-українських компаніях.',
    )

    @api.depends('country_id')
    def _compute_l10n_ua_is_ua_company(self):
        for company in self:
            company.l10n_ua_is_ua_company = company.country_id.code == 'UA'

    def _l10n_ua_is_ukrainian(self):
        """Whether Ukrainian rules apply to this (single) company.

        Tolerates an empty recordset (new records without a company yet).
        Canonical helper — reuse instead of re-checking country codes.
        """
        return len(self) == 1 and self.country_id.code == 'UA'

    def write(self, vals):
        res = super().write(vals)
        if 'country_id' in vals:
            # Country change flips the has-UA-company group for every user
            # who has this company available.
            users = self.env['res.users'].with_context(
                active_test=False).search([('company_ids', 'in', self.ids)])
            users._l10n_ua_recompute_has_ua_company()
        return res
