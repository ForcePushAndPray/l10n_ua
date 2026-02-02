from odoo import fields, models


class L10nUaFopGroup(models.Model):
    _name = 'l10n_ua.fop.group'
    _description = 'Група платника єдиного податку'
    _order = 'code'

    code = fields.Selection(
        selection=[
            ('1', '1 група'),
            ('2', '2 група'),
            ('3', '3 група (без ПДВ)'),
            ('3_vat', '3 група (з ПДВ)'),
        ],
        string='Група',
        required=True,
    )
    name = fields.Char(
        string='Назва',
        required=True,
        translate=True,
    )
    tax_rate = fields.Float(
        string='Ставка ЄП (%)',
        help='Ставка єдиного податку як відсоток від доходу',
    )
    income_limit = fields.Monetary(
        string='Ліміт річного доходу',
        currency_field='currency_id',
    )
    can_hire_employees = fields.Boolean(
        string='Може наймати працівників',
    )
    max_employees = fields.Integer(
        string='Макс. кількість працівників',
    )
    description = fields.Text(
        string='Опис',
        translate=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    active = fields.Boolean(
        default=True,
    )
