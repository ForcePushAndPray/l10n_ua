from odoo import api, fields, models


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    ua_group_id = fields.Many2one(
        'l10n_ua.asset.group',
        string='UA Asset Group',
        help='Asset group according to Ukrainian Tax Code (1-16)',
    )
    ua_inventory_number = fields.Char(
        string='Inventory Number',
    )
    ua_commission_date = fields.Date(
        string='Commissioning Date',
        help='Date when asset was put into operation',
    )
    ua_depreciation_method = fields.Selection(
        selection=[
            ('straight_line', 'Straight-line (Прямолінійний)'),
            ('declining_balance', 'Declining Balance (Зменшення залишку)'),
            ('production', 'Production (Виробничий)'),
            ('cumulative', 'Cumulative (Кумулятивний)'),
        ],
        string='UA Depreciation Method',
        default='straight_line',
    )
    ua_useful_life = fields.Integer(
        string='Useful Life (months)',
        help='Useful life in months',
    )
    ua_liquidation_value = fields.Monetary(
        string='Liquidation Value',
        currency_field='currency_id',
        help='Expected value at the end of useful life',
    )
    ua_production_capacity = fields.Float(
        string='Production Capacity',
        help='Total expected production units (for production method)',
    )
    ua_produced_units = fields.Float(
        string='Produced Units',
        help='Units produced to date',
    )

    @api.onchange('ua_group_id')
    def _onchange_ua_group_id(self):
        if self.ua_group_id and self.ua_group_id.min_useful_life:
            self.ua_useful_life = self.ua_group_id.min_useful_life * 12
