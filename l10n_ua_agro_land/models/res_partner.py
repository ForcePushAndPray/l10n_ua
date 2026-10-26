from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_ua_agro_lease_ids = fields.One2many(
        'l10n_ua.agro.land.lease', 'lessor_id', string='Land Leases')
    l10n_ua_agro_lease_count = fields.Integer(compute='_compute_l10n_ua_agro_lease_count')

    def _compute_l10n_ua_agro_lease_count(self):
        counts = dict(self.env['l10n_ua.agro.land.lease']._read_group(
            [('lessor_id', 'in', self.ids)], ['lessor_id'], ['__count']))
        for partner in self:
            partner.l10n_ua_agro_lease_count = counts.get(partner, 0)

    def action_view_l10n_ua_agro_leases(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'l10n_ua_agro_land.l10n_ua_agro_land_lease_action')
        action['domain'] = [('lessor_id', '=', self.id)]
        action['context'] = {'default_lessor_id': self.id}
        return action
