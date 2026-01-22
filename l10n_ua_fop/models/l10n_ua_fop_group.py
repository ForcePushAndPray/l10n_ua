from odoo import fields, models


class L10nUaFopGroup(models.Model):
    _name = 'l10n_ua.fop.group'
    _description = 'FOP Tax Group'
    _order = 'code'

    code = fields.Selection(
        selection=[
            ('1', 'Group 1'),
            ('2', 'Group 2'),
            ('3', 'Group 3 (no VAT)'),
            ('3_vat', 'Group 3 (with VAT)'),
        ],
        string='Group',
        required=True,
    )
    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )
    tax_rate = fields.Float(
        string='Tax Rate (%)',
        help='Single tax rate as percentage of income',
    )
    income_limit = fields.Monetary(
        string='Annual Income Limit',
        currency_field='currency_id',
    )
    can_hire_employees = fields.Boolean(
        string='Can Hire Employees',
    )
    max_employees = fields.Integer(
        string='Max Employees',
    )
    description = fields.Text(
        string='Description',
        translate=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    active = fields.Boolean(
        default=True,
    )
