from odoo import api, fields, models

from odoo.addons.l10n_ua_agro_base.models.agro_field import LAND_TYPES


class L10nUaTax4Rate(models.Model):
    """Ставки ЄП 4 групи, % бази оподаткування (НГО), ПКУ п. 293.9."""
    _name = 'l10n_ua.tax4.rate'
    _description = 'Ставка єдиного податку 4 групи'
    _order = 'land_type, mountain_zone'

    land_type = fields.Selection(LAND_TYPES, string='Вид угідь', required=True)
    mountain_zone = fields.Boolean(string='Гірська / поліська зона')
    rate = fields.Float(string='Ставка, %', digits=(6, 3), required=True)

    _type_zone_uniq = models.Constraint(
        'UNIQUE(land_type, mountain_zone)',
        'Ставка для цього виду угідь і зони вже є.',
    )

    @api.model
    def _get_rate(self, land_type, mountain_zone):
        rate = self.search([('land_type', '=', land_type), ('mountain_zone', '=', bool(mountain_zone))], limit=1)
        return rate.rate if rate else 0.0
