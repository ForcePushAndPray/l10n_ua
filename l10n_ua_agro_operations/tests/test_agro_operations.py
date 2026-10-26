from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import AgroOperationsTestCase


@tagged('post_install', '-at_install')
class TestAgroOperations(AgroOperationsTestCase):

    def test_tech_card_costs(self):
        # матеріали: 220 × 20 + 150 × 25 = 8 150 грн/га
        self.assertEqual(self.card.material_cost_ha, 8150.0)
        # операції: сівба 90 + 6 л × 55; внесення 45 + 3 л × 55 = 630
        self.assertEqual(self.card.operation_cost_ha, 630.0)
        self.assertEqual(self.card.area, 100.0)
        self.assertEqual(self.card.cost_total, 878000.0)
        self.assertEqual(self.planting.planned_cost, 878000.0)

    def test_load_norms_and_validate(self):
        order = self._order(self.op_sow)
        order.action_load_norms()
        seed_line = order.material_ids.filtered(lambda m: m.product_id == self.seed)
        fuel_line = order.material_ids.filtered('is_fuel')
        self.assertEqual(seed_line.quantity, 13200.0)              # 220 кг × 60 га
        self.assertFalse(order.material_ids.filtered(lambda m: m.product_id == self.fertilizer))
        self.assertAlmostEqual(fuel_line.quantity, 396.0)           # 6 л × 60 га × 1.1
        self.assertEqual(order.worker_ids.amount, 5400.0)           # 60 га × 90 грн
        fuel_line.quantity = 410.0
        self.assertAlmostEqual(fuel_line.deviation, 14.0)

        order.action_done()
        self.assertEqual(order.state, 'done')
        self.assertEqual(set(order.stock_move_ids.mapped('state')), {'done'})
        self.assertEqual(seed_line.amount, 264000.0)                # 13 200 × 20
        self.assertEqual(fuel_line.amount, 22550.0)                 # 410 × 55
        move = order.move_id
        self.assertEqual(move.state, 'posted')
        debit = move.line_ids.filtered(lambda l: l.account_id == self.acc_231)
        self.assertEqual(sum(debit.mapped('debit')), 286550.0)
        self.assertEqual(debit.l10n_ua_agro_planting_id, self.planting)
        self.assertTrue(self.field.analytic_account_id)
        self.assertTrue(self.wheat.analytic_account_id)
        self.assertIn(str(self.field.analytic_account_id.id), list(debit[0].analytic_distribution)[0])
        self.assertEqual(sum(move.line_ids.filtered(lambda l: l.account_id == self.acc_201).mapped('credit')), 264000.0)
        self.assertEqual(sum(move.line_ids.filtered(lambda l: l.account_id == self.acc_203).mapped('credit')), 22550.0)
        self.assertEqual(self.planting.actual_cost, 286550.0 + 5400.0)
        self.assertEqual(self.seed.with_context(
            warehouse_id=self.warehouse.id).qty_available, 20000 - 13200)

        self.env.flush_all()
        report = self.env['l10n_ua.agro.cost.report'].search([('planting_id', '=', self.planting.id)])
        self.assertEqual(sum(report.mapped('actual_amount')), 291950.0)
        self.assertEqual(round(sum(report.mapped('planned_amount')), 2), 878000.0)

    def test_cancel_returns_stock_and_reverses(self):
        order = self._order(self.op_fert, area=40.0)
        order.action_load_norms()
        order.action_done()
        order.action_cancel()
        self.assertEqual(order.state, 'cancel')
        self.assertEqual(self.fertilizer.with_context(
            warehouse_id=self.warehouse.id).qty_available, 20000)
        self.assertEqual(order.move_id.state, 'posted')
        reversal = self.env['account.move'].search([('reversed_entry_id', '=', order.move_id.id)])
        self.assertEqual(reversal.state, 'posted')
        self.assertEqual(self.planting.actual_cost, 0.0)
        order.action_draft()
        self.assertEqual(order.state, 'draft')

    def test_area_cannot_exceed_planting(self):
        with self.assertRaises(ValidationError):
            self._order(self.op_sow, area=100.5)
