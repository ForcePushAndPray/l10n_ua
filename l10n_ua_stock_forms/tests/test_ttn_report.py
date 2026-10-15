"""The consignment note (TTN, form No 1-TN) printed from a delivery order."""

from html import unescape

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ua_stock_forms')
class TestTtnReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.partner_id.write({
            'street': 'вул. Городоцька, 10',
            'city': 'Львів',
            'zip': '79000',
            'country_id': cls.env.ref('base.ua').id,
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'ТОВ Покупець',
            'street': 'вул. Хрещатик, 1',
            'city': 'Київ',
            'country_id': cls.env.ref('base.ua').id,
            'company_registry': '12345678',
        })
        cls.carrier = cls.env['res.partner'].create({
            'name': 'ТОВ Перевізник',
            'company_registry': '87654321',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Цвях будівельний',
            'is_storable': True,
            'lst_price': 120.0,
            'weight': 2.5,
        })
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.tax = cls.env['account.tax'] if 'account.tax' in cls.env else None
        if cls.tax is not None:
            group = cls.env['account.tax.group'].create({
                'name': 'ПДВ',
                'country_id': cls.env.ref('base.ua').id,
            })
            cls.tax = cls.env['account.tax'].create({
                'name': 'ПДВ 20%',
                'amount': 20.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'country_id': cls.env.ref('base.ua').id,
                'tax_group_id': group.id,
            })
            cls.product.taxes_id = cls.tax

    def _picking(self, qty=4.0):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'product_uom': self.product.uom_id.id,
                'location_id': self.warehouse.lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        return picking

    def _render(self, picking):
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_stock_forms.report_ttn', picking.ids)
        return unescape(html.decode())

    def _fill_transport(self, picking):
        picking.write({
            'l10n_ua_ttn_carrier_id': self.carrier.id,
            'l10n_ua_ttn_vehicle': 'MAN TGX',
            'l10n_ua_ttn_vehicle_plate': 'АА1234ВВ',
            'l10n_ua_ttn_trailer_plate': 'АА5678XT',
            'l10n_ua_ttn_driver_name': 'Петренко Петро Петрович',
            'l10n_ua_ttn_driver_license': 'ВХК123456',
        })

    def test_defaults_from_warehouse_and_delivery_address(self):
        picking = self._picking()
        self.assertEqual(picking.l10n_ua_ttn_place, 'Львів')
        self.assertIn('Городоцька', picking.l10n_ua_ttn_loading_point)
        self.assertIn('Хрещатик', picking.l10n_ua_ttn_unloading_point)
        self.assertEqual(picking.l10n_ua_ttn_package_count, 0)
        self.assertFalse(picking.l10n_ua_ttn_number)

        # A new delivery address moves the unloading point with it.
        other = self.customer.copy({'street': 'вул. Соборна, 5', 'city': 'Рівне'})
        picking.partner_id = other
        self.assertIn('Соборна', picking.l10n_ua_ttn_unloading_point)

        # Incoming transfers carry no note.
        receipt = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'partner_id': self.customer.id,
        })
        self.assertFalse(receipt.l10n_ua_ttn_loading_point)

    def test_package_count_and_gross_weight(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 10)
        picking = self._picking()
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.l10n_ua_ttn_package_count, 0)

        package = self.env['stock.package'].create({'name': 'BOX-1'})
        picking.move_line_ids.result_package_id = package
        self.assertEqual(picking.l10n_ua_ttn_package_count, 1)

        totals = picking._l10n_ua_ttn_totals(picking._l10n_ua_ttn_lines())
        # 4 pcs x 2.5 kg = 10 kg = 0.01 t
        self.assertAlmostEqual(totals['lines_weight'], 0.01)
        self.assertAlmostEqual(totals['gross_weight'], 0.01)

    def test_amount_in_words(self):
        uah = self.env.ref('base.UAH')
        words = self.env['stock.picking']._l10n_ua_ttn_amount_in_words
        self.assertEqual(words(1200.5, uah), 'Одна тисяча двісті гривень 50 копійок')
        self.assertEqual(words(2.0, uah), 'Дві гривні 00 копійок')
        self.assertEqual(
            self.env['stock.picking']._l10n_ua_ttn_number_in_words(12), 'дванадцять')

    def test_report_without_sale_order(self):
        picking = self._picking()
        picking.action_confirm()
        self._fill_transport(picking)

        lines = picking._l10n_ua_ttn_lines()
        self.assertEqual(len(lines), 1)
        totals = picking._l10n_ua_ttn_totals(lines)
        self.assertAlmostEqual(lines[0]['price_unit'], 120.0)
        self.assertAlmostEqual(totals['amount_untaxed'], 480.0)
        expected_total = 576.0 if self.tax is not None else 480.0
        self.assertAlmostEqual(totals['amount_total'], expected_total)
        self.assertAlmostEqual(totals['amount_tax'], expected_total - 480.0)

        html = self._render(picking)
        for value in (picking.name, 'АА1234ВВ', 'АА5678XT', 'MAN TGX',
                      'Петренко Петро Петрович', 'ВХК123456',
                      'ТОВ Перевізник', '87654321', 'ТОВ Покупець', '12345678',
                      'Цвях будівельний', 'Хрещатик', 'Городоцька',
                      '0.010', '%.2f' % expected_total,
                      picking._l10n_ua_ttn_amount_in_words(
                          expected_total, totals['currency'])):
            self.assertIn(value, html)

    def test_report_with_sale_order(self):
        if 'sale_line_id' not in self.env['stock.move']._fields:
            self.skipTest('Sales is not installed (sale_stock)')
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 3,
                'price_unit': 100.0,
                'tax_ids': [(6, 0, self.tax.ids)],
            })],
        })
        order.action_confirm()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        self._fill_transport(picking)
        picking.l10n_ua_ttn_number = 'ТТН-0001'

        totals = picking._l10n_ua_ttn_totals(picking._l10n_ua_ttn_lines())
        # The order price wins over the sales price of the product.
        self.assertAlmostEqual(totals['amount_untaxed'], 300.0)
        self.assertAlmostEqual(totals['amount_total'], 360.0)
        self.assertAlmostEqual(totals['amount_tax'], 60.0)
        self.assertAlmostEqual(totals['lines_weight'], 0.0075)

        html = self._render(picking)
        for value in ('ТТН-0001', 'АА1234ВВ', 'Петренко Петро Петрович',
                      '100.00', '360.00', '60.00',
                      picking._l10n_ua_ttn_amount_in_words(360.0, totals['currency'])):
            self.assertIn(value, html)
