from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_value_from_extra(self, quantity, at_date=None):
        """Add the allocated production overhead to the finished product.

        Same hook as landed costs: the value of the finished move of a
        manufacturing order includes its share of the posted overhead
        allocations (NP(S)BO 16, item 15), so `_set_value()` carries it into
        the move value and the average / FIFO cost of the product.
        """
        data = super()._get_value_from_extra(quantity, at_date=at_date)
        production = self.production_id
        if not production or self.product_id != production.product_id \
                or self.product_id.cost_method not in ('fifo', 'average'):
            return data
        lines = production.sudo().l10n_ua_overhead_line_ids
        if not lines:
            return data
        amount = lines._overhead_for_move(self, at_date=at_date)
        if self.company_currency_id.is_zero(amount):
            return data
        data['value'] += amount
        desc = self.env._(
            '+ %(value)s production overhead (%(documents)s)',
            value=self.company_currency_id.format(amount),
            documents=', '.join(lines.filtered(
                lambda l: l.allocation_id.state == 'posted').allocation_id.mapped('name')))
        data['description'] = '\n'.join(filter(None, [data.get('description'), desc]))
        return data
