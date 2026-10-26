from odoo.tests import tagged

from odoo.addons.l10n_ua_agro_operations.tests.common import AgroOperationsTestCase


@tagged('post_install', '-at_install')
class TestAgroPiecePay(AgroOperationsTestCase):

    def test_piece_entries_follow_work_order(self):
        order = self._order(self.op_sow)
        order.action_done()
        entry = self.env['hr.piece.work.entry'].search([('l10n_ua_agro_worker_id.order_id', '=', order.id)])
        self.assertEqual(entry.employee_id, self.operator)
        self.assertEqual(entry.quantity, 60.0)
        self.assertEqual(entry.unit_rate, 90.0)
        self.assertEqual(entry.amount, 5400.0)
        self.assertEqual(entry.date, order.date)
        order.action_cancel()
        self.assertFalse(entry.exists())
