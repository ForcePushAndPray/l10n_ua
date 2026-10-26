import importlib.util
import os
from datetime import date

from odoo.tests import tagged

from .common import AgroOperationsTestCase

MIGRATION = os.path.join(os.path.dirname(__file__), '..', 'migrations', '19.0.1.4.0', 'post-migration.py')


@tagged('post_install', '-at_install')
class TestMigrationCostProduct(AgroOperationsTestCase):

    def test_backfills_product_on_old_cost_lines(self):
        order = self._order(self.op_sow, date=date(2096, 9, 25))
        order.action_load_norms()
        order.action_done()
        lines = order.move_id.line_ids.filtered('l10n_ua_agro_planting_id')
        self.assertEqual(lines.product_id, self.seed | self.diesel)
        self.env.cr.execute('UPDATE account_move_line SET product_id = NULL WHERE id IN %s', (tuple(lines.ids),))
        lines.invalidate_recordset(['product_id'])
        spec = importlib.util.spec_from_file_location('agro_ops_mig_1_4', MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.1.3.0')
        lines.invalidate_recordset(['product_id'])
        for line in lines:
            self.assertTrue(line.product_id)
            self.assertTrue(line.name.endswith(line.product_id.display_name))
