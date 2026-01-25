from odoo import fields, models


class L10nUaAssetGroup(models.Model):
    _name = 'l10n_ua.asset.group'
    _description = 'Fixed Asset Group (Tax Code)'
    _order = 'code'

    code = fields.Char(
        string='Code',
        required=True,
    )
    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )
    min_useful_life = fields.Integer(
        string='Min Useful Life (years)',
        help='Minimum useful life according to Tax Code',
    )
    description = fields.Text(
        string='Description',
        translate=True,
    )
    active = fields.Boolean(
        default=True,
    )

    _unique_code = models.Constraint(
        'UNIQUE(code)',
        'Asset group code must be unique!',
    )
