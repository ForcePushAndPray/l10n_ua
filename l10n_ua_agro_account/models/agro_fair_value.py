from odoo import api, fields, models


class AgroFairValue(models.Model):
    """Справедлива вартість сільгосппродукції мінус очікувані витрати на
    місці продажу (П(С)БО 30, п. 7) — на дату, за одиницю виміру товару."""
    _name = 'l10n_ua.agro.fair.value'
    _description = 'Fair Value of Agricultural Produce'
    _order = 'date desc, product_id'

    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    uom_id = fields.Many2one(related='product_id.uom_id')
    date = fields.Date(required=True, default=fields.Date.context_today)
    price = fields.Monetary(
        string='Fair Value', required=True,
        help='Ціна активного ринку за одиницю мінус очікувані витрати на місці продажу.')
    source = fields.Char(help='Джерело ціни: біржа, котирування трейдерів, договір.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _product_date_uniq = models.Constraint(
        'UNIQUE(product_id, date, company_id)',
        'There is already a fair value of this product on this date.',
    )

    @api.model
    def _get_price(self, product, on_date, company):
        record = self.search([
            ('product_id', '=', product.id), ('date', '<=', on_date), ('company_id', '=', company.id),
        ], order='date desc', limit=1)
        return record.price if record else None
