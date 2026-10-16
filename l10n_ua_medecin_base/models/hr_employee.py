from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_ua_medecin_specialty_id = fields.Many2one(
        'l10n_ua.medecin.specialty', string='Медична спеціалізація',
        index='btree_not_null',
        help='Спеціалізація лікаря. Працівники з заповненою спеціалізацією '
             'показуються в меню «Медицина → Налаштування → Лікарі».')
