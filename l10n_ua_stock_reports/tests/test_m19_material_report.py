"""Матеріальний звіт М-19: opening balance, movement and closing balance."""

from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestM19MaterialReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.stock = cls.env.ref('stock.stock_location_stock')
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.customer = cls.env.ref('stock.stock_location_customers')
        cls.product = cls.env['product.product'].create({
            'name': 'Цемент М-400',
            'is_storable': True,
            'default_code': 'CEM400',
            'standard_price': 150.0,
        })

    def _move(self, source, dest, qty, when):
        """A done stock move, dated explicitly so it lands in the period."""
        move = self.env['stock.move'].create({
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
        })
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = qty
        move.picked = True
        move._action_done()
        move.move_line_ids.write({'date': when})
        return move

    def _wizard(self, **kwargs):
        vals = {
            'date_from': '2026-03-01',
            'date_to': '2026-03-31',
            'location_id': self.stock.id,
            'responsible_person': 'Комірник Іваненко',
        }
        vals.update(kwargs)
        return self.env['l10n_ua.m19.material.report.wizard'].create(vals)

    def test_opening_receipts_issues_and_closing(self):
        self._move(self.supplier, self.stock, 100, datetime(2026, 2, 10, 8, 0))
        self._move(self.supplier, self.stock, 40, datetime(2026, 3, 5, 8, 0))
        self._move(self.stock, self.customer, 30, datetime(2026, 3, 20, 8, 0))

        lines = self._wizard()._get_report_lines()
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line['opening_qty'], 100)
        self.assertEqual(line['in_qty'], 40)
        self.assertEqual(line['out_qty'], 30)
        self.assertEqual(line['closing_qty'], 110)
        # Amounts are quantity at the product's cost price.
        self.assertEqual(line['closing_value'], 110 * 150.0)

    def test_moves_outside_the_period_stay_out(self):
        self._move(self.supplier, self.stock, 10, datetime(2026, 4, 2, 8, 0))
        lines = self._wizard()._get_report_lines()
        self.assertFalse(lines)

    def test_internal_move_is_neither_receipt_nor_issue(self):
        """A transfer inside the location must not inflate either column."""
        shelf = self.env['stock.location'].create({
            'name': 'Полиця А',
            'usage': 'internal',
            'location_id': self.stock.id,
        })
        self._move(self.supplier, self.stock, 50, datetime(2026, 3, 3, 8, 0))
        self._move(self.stock, shelf, 20, datetime(2026, 3, 6, 8, 0))

        line = self._wizard()._get_report_lines()[0]
        self.assertEqual(line['in_qty'], 50)
        self.assertEqual(line['out_qty'], 0)
        self.assertEqual(line['closing_qty'], 50)

    def test_totals(self):
        self._move(self.supplier, self.stock, 20, datetime(2026, 3, 4, 8, 0))
        wizard = self._wizard()
        lines = wizard._get_report_lines()
        totals = wizard._get_report_totals(lines)
        self.assertEqual(totals['in_value'], 20 * 150.0)
        self.assertEqual(totals['closing_value'], 20 * 150.0)

    def test_period_must_be_ordered(self):
        with self.assertRaises(UserError):
            self._wizard(date_from='2026-03-31', date_to='2026-03-01')

    def test_print_returns_report_action(self):
        action = self._wizard().action_print()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(
            action['report_name'], 'l10n_ua_stock_reports.report_m19_material')
