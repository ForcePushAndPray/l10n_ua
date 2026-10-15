"""Consignment note (ТТН, form No 1-TN) data on a delivery order.

The form is appendix 7 to the Rules for the carriage of goods by road in
Ukraine (order of the Ministry of Transport No 363 of 14.10.1997), as worded
by the orders of the Ministry for Communities and Territories Development
No 1332 of 14.11.2024 and No 1727 of 12.12.2025.

The module depends on `stock` alone. What the form needs from sales
(prices of the order lines), accounting (taxes) or the Ukrainian partner
registry (EDRPOU / RNOKPP) is read only when those modules are installed,
by checking `_fields` rather than `hasattr`: the latter is true for any name
on a recordset and would hide a missing field.
"""

import logging

from odoo import api, fields, models

try:
    from num2words import num2words
except ImportError:  # pragma: no cover - a hard requirement of Odoo itself
    num2words = None

_logger = logging.getLogger(__name__)


def _one_line_address(partner):
    """The address of a partner on one line, without the name."""
    if not partner:
        return ''
    parts = [
        partner.zip, partner.country_id.name, partner.state_id.name,
        partner.city, partner.street, partner.street2,
    ]
    return ', '.join(part for part in parts if part)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    l10n_ua_ttn_number = fields.Char(
        string='Consignment Note No.', copy=False,
        help='Number of the consignment note (TTN). The reference of the '
             'transfer is printed when left empty.')
    l10n_ua_ttn_date = fields.Date(
        string='Consignment Note Date', copy=False,
        help='Date of the consignment note. The date of the transfer is '
             'printed when left empty.')
    l10n_ua_ttn_place = fields.Char(
        string='Place of Issue',
        compute='_compute_l10n_ua_ttn_addresses', store=True, readonly=False,
        help='Where the consignment note is drawn up: the city of the '
             'warehouse by default.')
    l10n_ua_ttn_vehicle = fields.Char(
        string='Vehicle', help='Make, model and type of the vehicle.')
    l10n_ua_ttn_vehicle_plate = fields.Char(string='Vehicle Plate')
    l10n_ua_ttn_trailer = fields.Char(
        string='Trailer/Semi-trailer',
        help='Make, model and type of the trailer or semi-trailer.')
    l10n_ua_ttn_trailer_plate = fields.Char(string='Trailer Plate')
    l10n_ua_ttn_transport_kind = fields.Char(string='Type of Carriage')
    l10n_ua_ttn_vehicle_storage = fields.Char(
        string='Vehicle Storage Place',
        help='Address of the carrier, its unit or branch where the vehicle '
             'is kept. Filled in when the regulation on working time and '
             'rest of drivers requires it.')
    l10n_ua_ttn_carrier_id = fields.Many2one(
        'res.partner', string='Road Carrier',
        help='The road carrier. Its tax code is taken from the partner.')
    l10n_ua_ttn_driver_name = fields.Char(string='Driver')
    l10n_ua_ttn_driver_license = fields.Char(string="Driver's License No.")
    l10n_ua_ttn_loading_point = fields.Char(
        string='Loading Point',
        compute='_compute_l10n_ua_ttn_addresses', store=True, readonly=False,
        help='The address of the warehouse by default.')
    l10n_ua_ttn_unloading_point = fields.Char(
        string='Unloading Point',
        compute='_compute_l10n_ua_ttn_addresses', store=True, readonly=False,
        help='The delivery address by default.')
    l10n_ua_ttn_package_count = fields.Integer(
        string='Number of Packages',
        compute='_compute_l10n_ua_ttn_package_count', store=True, readonly=False,
        help='The number of packages of the transfer by default.')
    l10n_ua_ttn_vehicle_length = fields.Float(string='Vehicle Length, m', digits=(16, 2))
    l10n_ua_ttn_vehicle_width = fields.Float(string='Vehicle Width, m', digits=(16, 2))
    l10n_ua_ttn_vehicle_height = fields.Float(string='Vehicle Height, m', digits=(16, 2))
    l10n_ua_ttn_vehicle_total_weight = fields.Float(
        string='Laden Vehicle Weight, t', digits=(16, 3),
        help='Total weight of the vehicle with the goods.')
    l10n_ua_ttn_documents = fields.Char(
        string='Accompanying Documents',
        help='Documents accompanying the goods: certificates, invoices, etc.')

    l10n_ua_ttn_weight_uom_name = fields.Char(
        string='Weight Unit', compute='_compute_l10n_ua_ttn_weight_uom_name')

    def _compute_l10n_ua_ttn_weight_uom_name(self):
        name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()
        for picking in self:
            picking.l10n_ua_ttn_weight_uom_name = name

    @api.depends('picking_type_id', 'partner_id', 'company_id')
    def _compute_l10n_ua_ttn_addresses(self):
        for picking in self:
            if picking.picking_type_code != 'outgoing':
                picking.l10n_ua_ttn_place = picking.l10n_ua_ttn_place or False
                picking.l10n_ua_ttn_loading_point = picking.l10n_ua_ttn_loading_point or False
                picking.l10n_ua_ttn_unloading_point = picking.l10n_ua_ttn_unloading_point or False
                continue
            origin = (picking.picking_type_id.warehouse_id.partner_id
                      or picking.company_id.partner_id)
            picking.l10n_ua_ttn_place = origin.city or False
            picking.l10n_ua_ttn_loading_point = _one_line_address(origin) or False
            picking.l10n_ua_ttn_unloading_point = _one_line_address(picking.partner_id) or False

    @api.depends('move_line_ids.result_package_id')
    def _compute_l10n_ua_ttn_package_count(self):
        for picking in self:
            packages = picking.move_line_ids.result_package_id.outermost_package_id
            picking.l10n_ua_ttn_package_count = len(packages)

    # ------------------------------------------------------------------
    # Report helpers
    # ------------------------------------------------------------------

    def _l10n_ua_ttn_report_lang(self):
        """The form is a Ukrainian statutory one: print it in Ukrainian
        whenever that language is installed, the user's language otherwise."""
        return self.env['res.lang']._get_code('uk_UA') or self.env.lang

    def _l10n_ua_ttn_currency(self):
        self.ensure_one()
        if 'sale_id' in self._fields and self.sale_id:
            return self.sale_id.currency_id
        return self.company_id.currency_id

    def _l10n_ua_ttn_party_codes(self, partner):
        """Tax codes of a party: EDRPOU or RNOKPP when the Ukrainian
        registry fields are installed, the generic company ID / VAT otherwise.
        For the company itself the code kept on the company is used too."""
        partner = partner.commercial_partner_id
        records = [partner]
        if partner == self.company_id.partner_id:
            records.append(self.company_id)
        for record in records:
            for fname in ('edrpou', 'ipn', 'company_registry', 'vat'):
                if fname in record._fields and record[fname]:
                    return record[fname]
        return ''

    def _l10n_ua_ttn_party(self, partner):
        """Name, address and tax code of a party on one line."""
        self.ensure_one()
        if not partner:
            return ''
        commercial = partner.commercial_partner_id
        parts = [commercial.name or partner.display_name,
                 _one_line_address(commercial)]
        code = self._l10n_ua_ttn_party_codes(partner)
        if code:
            parts.append(self.env._('code %s', code))
        return ', '.join(part for part in parts if part)

    def _l10n_ua_ttn_shipper(self):
        self.ensure_one()
        return self.company_id.partner_id

    def _l10n_ua_ttn_display_number(self):
        self.ensure_one()
        return self.l10n_ua_ttn_number or self.name

    def _l10n_ua_ttn_display_date(self):
        self.ensure_one()
        if self.l10n_ua_ttn_date:
            return self.l10n_ua_ttn_date
        moment = self.date_done or self.scheduled_date
        return fields.Date.context_today(self, moment) if moment else False

    def _l10n_ua_ttn_weight_in_tonnes(self, weight):
        """Convert a weight expressed in the database weight unit to tonnes."""
        weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        tonne = self.env.ref('uom.product_uom_ton', raise_if_not_found=False)
        if not weight or not weight_uom or not tonne or weight_uom == tonne:
            return weight or 0.0
        return weight_uom._compute_quantity(weight, tonne, round=False)

    def _l10n_ua_ttn_move_amounts(self, move, qty):
        """Amounts of `qty` of a move (in the move's unit): without and with
        VAT, from the sale order line or, failing one, the sales price."""
        currency = self._l10n_ua_ttn_currency()
        sale_line = move.sale_line_id if 'sale_line_id' in move._fields else False
        if sale_line and sale_line.product_uom_qty:
            sale_qty = move.product_uom._compute_quantity(
                qty, sale_line.product_uom_id, round=False)
            ratio = sale_qty / sale_line.product_uom_qty
            return (currency.round(sale_line.price_subtotal * ratio),
                    currency.round(sale_line.price_total * ratio))
        product = move.product_id
        price = product.uom_id._compute_price(product.lst_price, move.product_uom)
        excluded = included = currency.round(price * qty)
        if 'taxes_id' in product._fields:
            taxes = product.taxes_id.filtered(
                lambda tax: tax.company_id in self.company_id.parent_ids)
            if taxes:
                res = taxes.compute_all(
                    price, currency, qty, product=product, partner=self.partner_id)
                excluded, included = res['total_excluded'], res['total_included']
        return excluded, included

    def _l10n_ua_ttn_lines(self):
        """The rows of the «Cargo details» table, one per stock move."""
        self.ensure_one()
        lines = []
        for move in self.move_ids.filtered(
                lambda m: m.state != 'cancel' and m.product_id):
            qty = move.quantity or move.product_uom_qty
            if not qty:
                continue
            excluded, included = self._l10n_ua_ttn_move_amounts(move, qty)
            product_qty = move.product_uom._compute_quantity(
                qty, move.product_id.uom_id, round=False)
            packaging = move.move_line_ids.result_package_id.package_type_id
            lines.append({
                'move': move,
                'name': move.product_id.display_name,
                'uom': move.product_uom.name,
                'qty': qty,
                'price_unit': excluded / qty,
                'amount_untaxed': excluded,
                'amount_total': included,
                'packaging': ', '.join(packaging.mapped('name')),
                'weight': self._l10n_ua_ttn_weight_in_tonnes(
                    product_qty * move.product_id.weight),
            })
        return lines

    def _l10n_ua_ttn_totals(self, lines):
        self.ensure_one()
        currency = self._l10n_ua_ttn_currency()
        untaxed = currency.round(sum(line['amount_untaxed'] for line in lines))
        total = currency.round(sum(line['amount_total'] for line in lines))
        lines_weight = sum(line['weight'] for line in lines)
        # The weight of the shipment, packaging included, when the transfer
        # knows it; the weight of the goods alone otherwise.
        gross = self._l10n_ua_ttn_weight_in_tonnes(self.shipping_weight) or lines_weight
        return {
            'qty': sum(line['qty'] for line in lines),
            'amount_untaxed': untaxed,
            'amount_total': total,
            'amount_tax': currency.round(total - untaxed),
            'lines_weight': lines_weight,
            'gross_weight': gross,
            'currency': currency,
        }

    @api.model
    def _l10n_ua_ttn_number_in_words(self, number):
        """A count or a weight in Ukrainian words, as the form asks."""
        if num2words is None:
            return ''
        try:
            if float(number).is_integer():
                return num2words(int(number), lang='uk')
            return num2words(round(number, 3), lang='uk')
        except (NotImplementedError, OverflowError, ValueError):
            return ''

    @api.model
    def _l10n_ua_ttn_amount_in_words(self, amount, currency):
        """«одна тисяча двісті гривень 50 копійок»: hryvnias in words,
        kopecks in figures, as Ukrainian primary documents usually put it."""
        if num2words is None:
            return ''
        amount = currency.round(amount)
        integral = int(amount)
        fractional = int(round((amount - integral) * 100))
        try:
            words = num2words(float(integral), lang='uk', to='currency',
                              currency=currency.name)
            subunit = num2words(fractional / 100.0, lang='uk', to='currency',
                                currency=currency.name)
        except NotImplementedError:
            return currency.amount_to_text(amount)
        # num2words spells both parts: «… гривень, нуль копійок».
        words = words.split(',')[0].strip()
        subunit = subunit.rsplit(' ', 1)[-1]
        text = '%s %02d %s' % (words, fractional, subunit)
        return text[:1].upper() + text[1:]
