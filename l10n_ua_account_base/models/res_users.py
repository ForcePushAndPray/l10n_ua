"""Auto-managed `group_has_ua_company` membership (issue #178).

A user belongs to `group_has_ua_company` iff at least one of their available
companies (`company_ids`) is Ukrainian. This is the stable, session-independent
signal Odoo can act on — menus cannot be filtered by the *active* company.
Membership is recomputed on user/company changes; the menu cache is cleared so
the app launcher reflects it after the next reload.
"""

from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _l10n_ua_recompute_has_ua_company(self):
        """(Re)compute has-UA-company membership for ``self`` (or all users)."""
        group = self.env.ref(
            'l10n_ua_account_base.group_has_ua_company',
            raise_if_not_found=False)
        if not group:
            return
        users = self or self.with_context(active_test=False).search(
            [('share', '=', False)])
        should = users.filtered(
            lambda u: any(c.country_id.code == 'UA' for c in u.company_ids))
        add = should.filtered(lambda u: group not in u.group_ids)
        remove = (users - should).filtered(lambda u: group in u.group_ids)
        # Write on the group side so we don't recurse through user.write().
        if add:
            group.sudo().write({'user_ids': [(4, u.id) for u in add]})
        if remove:
            group.sudo().write({'user_ids': [(3, u.id) for u in remove]})
        if add or remove:
            # Menu visibility (load_menus) is cached per user/groups — refresh.
            self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._l10n_ua_recompute_has_ua_company()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'company_ids' in vals or 'company_id' in vals:
            self._l10n_ua_recompute_has_ua_company()
        return res
