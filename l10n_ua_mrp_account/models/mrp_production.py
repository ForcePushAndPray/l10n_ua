from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    l10n_ua_overhead_line_ids = fields.One2many(
        'l10n_ua.overhead.allocation.line',
        'production_id',
        string='Overhead Allocations',
        readonly=True,
    )
    l10n_ua_overhead_amount = fields.Monetary(
        string='Allocated Overhead',
        compute='_compute_l10n_ua_overhead_amount',
        currency_field='l10n_ua_currency_id',
    )
    l10n_ua_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Company Currency',
    )

    def _compute_l10n_ua_overhead_amount(self):
        for production in self:
            production.l10n_ua_overhead_amount = sum(
                production.l10n_ua_overhead_line_ids.filtered(
                    lambda l: l.allocation_id.state == 'posted').mapped('amount'))

    def _l10n_ua_finished_moves(self):
        """Done moves of the main finished product (by-products excluded)."""
        self.ensure_one()
        return self.move_finished_ids.filtered(
            lambda m: m.state == 'done' and m.product_id == self.product_id)

    def _l10n_ua_material_cost(self):
        self.ensure_one()
        return sum(self.move_raw_ids.filtered(lambda m: m.state == 'done').mapped('value'))

    def _l10n_ua_workorder_hours(self, workorder):
        if workorder._should_estimate_cost():
            return workorder.duration_expected / 60.0
        return workorder.duration / 60.0

    def _l10n_ua_labour_cost(self):
        self.ensure_one()
        return sum(wo._cal_cost() for wo in self.workorder_ids)

    def _l10n_ua_machine_hours(self):
        self.ensure_one()
        return sum(self._l10n_ua_workorder_hours(wo) for wo in self.workorder_ids)

    def _l10n_ua_overhead_base_value(self, base):
        """Value of the allocation base for this order (NP(S)BO 16, item 15)."""
        self.ensure_one()
        if base == 'labour':
            return self._l10n_ua_labour_cost()
        if base == 'machine_hours':
            return self._l10n_ua_machine_hours()
        if base == 'material':
            return self._l10n_ua_material_cost()
        return self.qty_produced

    def _l10n_ua_cost_calculation(self):
        """Data of the printed cost calculation (калькуляція собівартості)."""
        self.ensure_one()
        currency = self.company_id.currency_id
        materials = []
        for move in self.move_raw_ids.filtered(lambda m: m.state == 'done'):
            materials.append({
                'product': move.product_id.display_name,
                'quantity': move.quantity,
                'uom': move.product_uom.name,
                'value': currency.round(move.value),
            })
        operations = []
        for wo in self.workorder_ids:
            operations.append({
                'name': wo.name,
                'workcenter': wo.workcenter_id.display_name,
                'hours': self._l10n_ua_workorder_hours(wo),
                'rate': wo.costs_hour or wo.workcenter_id.costs_hour,
                'value': currency.round(wo._cal_cost()),
            })
        overhead = []
        for line in self.l10n_ua_overhead_line_ids.filtered(
                lambda l: l.allocation_id.state == 'posted'):
            overhead.append({
                'document': line.allocation_id.name,
                'date_from': line.allocation_id.date_from,
                'date_to': line.allocation_id.date_to,
                'base': dict(line.allocation_id._fields['base']._description_selection(
                    self.env)).get(line.allocation_id.base),
                'share': line.share,
                'value': line.amount,
            })
        material_cost = sum(m['value'] for m in materials)
        labour_cost = sum(o['value'] for o in operations)
        quantity = sum(
            m.product_uom._compute_quantity(m.quantity, self.product_id.uom_id)
            for m in self._l10n_ua_finished_moves()) or self.qty_produced
        extra_cost = currency.round(self.extra_cost * quantity)
        overhead_cost = sum(o['value'] for o in overhead)
        total = material_cost + labour_cost + extra_cost + overhead_cost
        return {
            'materials': materials,
            'operations': operations,
            'overhead': overhead,
            'material_cost': material_cost,
            'labour_cost': labour_cost,
            'extra_cost': extra_cost,
            'overhead_cost': overhead_cost,
            'total': total,
            'quantity': quantity,
            'uom': self.product_id.uom_id.name,
            'unit_cost': total / quantity if quantity else 0.0,
            'currency': currency,
        }

    def _l10n_ua_fmt(self, value):
        """Amount for the printed forms: 1 234.50."""
        return '{:,.2f}'.format(value or 0.0).replace(',', ' ')
