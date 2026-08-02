"""Матеріальний звіт (form М-19) — the report a person in charge of a store
files for a period.

Мінстат order No 193 of 21.06.1996, which approved the form, has been
repealed, but the duty to account for the materials held by that person has
not, so this is still the layout Ukrainian accountants ask for.

The figures come from done stock moves in and out of the chosen location, so
the report works on the standard Inventory app alone — no accounting
localization behind it. Amounts are the quantities at the product's cost
price (облікова ціна); a report valued from stock valuation layers is a
separate job, and this one deliberately states its basis rather than mixing
the two.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class L10nUaM19MaterialReportWizard(models.TransientModel):
    _name = 'l10n_ua.m19.material.report.wizard'
    _description = 'Матеріальний звіт (М-19)'

    date_from = fields.Date(
        string='Період з',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='Період по',
        required=True,
        default=fields.Date.context_today,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Місце зберігання',
        required=True,
        domain="[('usage', '=', 'internal')]",
    )
    responsible_person = fields.Char(
        string='МВО (відповідальна особа)',
        help='Матеріально відповідальна особа, яка звітує за цей склад',
    )
    include_zero = fields.Boolean(
        string='Включити нульові рядки',
        default=False,
        help='Показувати номенклатуру, що не має ні залишку, ні руху за період',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise UserError(_('Початок періоду має передувати його кінцю.'))

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'l10n_ua_stock_reports.action_report_m19_material'
        ).report_action(self)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _move_line_domain(self, field, date_from, date_to):
        """Done move lines that moved stock through `field` of the location.

        `field` is location_dest_id for receipts and location_id for issues;
        child_of catches the sub-locations a warehouse is made of.
        """
        self.ensure_one()
        domain = [
            ('state', '=', 'done'),
            (field, 'child_of', self.location_id.id),
            ('company_id', '=', self.company_id.id),
        ]
        # A move inside the location (or between its children) is not a
        # receipt nor an issue — it must not inflate either column.
        other = 'location_id' if field == 'location_dest_id' else 'location_dest_id'
        domain.append('!')
        domain.append((other, 'child_of', self.location_id.id))
        if date_from:
            domain.append(('date', '>=', fields.Datetime.to_datetime(date_from)))
        if date_to:
            end = fields.Datetime.to_datetime(date_to).replace(
                hour=23, minute=59, second=59)
            domain.append(('date', '<=', end))
        return domain

    def _quantities(self, field, date_from, date_to):
        """{product: quantity in the product's own UoM} for one direction."""
        self.ensure_one()
        lines = self.env['stock.move.line'].search(
            self._move_line_domain(field, date_from, date_to))
        quantities = {}
        for line in lines:
            product = line.product_id
            qty = line.product_uom_id._compute_quantity(
                line.quantity, product.uom_id) if line.product_uom_id else line.quantity
            quantities[product] = quantities.get(product, 0.0) + qty
        return quantities

    def _get_report_lines(self):
        """Rows of the М-19 table, one per product, sorted by name."""
        self.ensure_one()
        opening_in = self._quantities('location_dest_id', False, self.date_from and
                                      fields.Date.subtract(self.date_from, days=1))
        opening_out = self._quantities('location_id', False, self.date_from and
                                       fields.Date.subtract(self.date_from, days=1))
        period_in = self._quantities('location_dest_id', self.date_from, self.date_to)
        period_out = self._quantities('location_id', self.date_from, self.date_to)

        products = (set(opening_in) | set(opening_out)
                    | set(period_in) | set(period_out))
        lines = []
        for product in products:
            opening = opening_in.get(product, 0.0) - opening_out.get(product, 0.0)
            received = period_in.get(product, 0.0)
            issued = period_out.get(product, 0.0)
            closing = opening + received - issued
            if not self.include_zero and not any((opening, received, issued, closing)):
                continue
            price = product.standard_price or 0.0
            lines.append({
                'product': product,
                'code': product.default_code or '',
                'name': product.display_name,
                'uom': product.uom_id.name,
                'price': price,
                'opening_qty': opening,
                'opening_value': opening * price,
                'in_qty': received,
                'in_value': received * price,
                'out_qty': issued,
                'out_value': issued * price,
                'closing_qty': closing,
                'closing_value': closing * price,
            })
        return sorted(lines, key=lambda line: line['name'])

    def _get_report_totals(self, lines):
        keys = ('opening_value', 'in_value', 'out_value', 'closing_value')
        return {key: sum(line[key] for line in lines) for key in keys}
