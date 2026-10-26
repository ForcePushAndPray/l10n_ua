from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_ua_agro_planting_id = fields.Many2one(
        'l10n_ua.agro.planting', string='Planting', index='btree_not_null',
        help='Посів (поле × сезон × культура), на який віднесено витрати — для калькуляції собівартості.')
