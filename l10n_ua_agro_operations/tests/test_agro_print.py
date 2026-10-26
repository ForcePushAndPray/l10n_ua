from odoo.tests import tagged

from .common import AgroOperationsTestCase


@tagged('post_install', '-at_install')
class TestAgroPrintForms(AgroOperationsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.seed.l10n_ua_agro_material_type = 'seed'
        cls.fertilizer.write({'l10n_ua_agro_material_type': 'fertilizer', 'l10n_ua_agro_active_ingredient': 34.4})
        cls.agronomist = cls.env['hr.employee'].create({'name': 'Шевчук Ольга Василівна'})
        cls.operator2 = cls.env['hr.employee'].create({'name': 'Остапчук Василь Іванович'})

    def _orders(self):
        sow = self._order(self.op_sow, area=60.0, responsible_id=self.agronomist.id, worker_ids=[
            (0, 0, {'employee_id': self.operator.id, 'machine_id': self.tractor.id, 'volume': 40.0, 'hours': 6}),
            (0, 0, {'employee_id': self.operator2.id, 'machine_id': self.tractor.id, 'volume': 20.0, 'hours': 3}),
        ])
        sow.action_load_norms()
        sow.action_done()
        fert = self._order(self.op_fert, area=40.0, responsible_id=self.agronomist.id)
        fert.action_load_norms()
        fert.action_done()
        draft = self._order(self.op_fert, area=10.0)
        return sow | fert | draft

    def test_vzsg_rows(self):
        orders = self._orders()
        seeds = orders._print_material_rows(('seed',))
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0]['quantity'], 13200.0)
        self.assertEqual(seeds[0]['area'], 60.0)
        self.assertEqual(seeds[0]['norm_ha'], 220.0)
        self.assertEqual(seeds[0]['actual_ha'], 220.0)
        self.assertEqual(seeds[0]['debit'], self.acc_231.code)
        self.assertEqual(seeds[0]['credit'], self.acc_201.code)
        fert = orders._print_material_rows(('fertilizer', 'protection'))
        self.assertEqual(len(fert), 1)                         # чернетка не друкується
        self.assertEqual(fert[0]['quantity'], 6000.0)
        self.assertAlmostEqual(fert[0]['quantity_ai'], 6000 * 0.344, places=3)
        self.assertEqual(fert[0]['price'], 25.0)

    def test_operator_sheets(self):
        sheets = self._orders()._print_operator_sheets()
        by_employee = {s['employee']: s for s in sheets}
        first = by_employee[self.operator]
        self.assertEqual(len(first['rows']), 2)
        self.assertEqual(first['volume'], 80.0)                # 40 сівба + 40 внесення
        self.assertEqual(first['amount'], 40 * 90 + 40 * 45)
        self.assertEqual(first['machine_days'], 1)
        second = by_employee[self.operator2]
        # пальне сівби (60 га × 6 л × 1.1) ділиться за виробітком 40 : 20
        self.assertAlmostEqual(second['fuel_norm'], 396.0 / 3, places=2)

    def test_reports_render(self):
        orders = self._orders()
        Report = self.env['ir.actions.report']
        for ref in ('action_report_vzsg3', 'action_report_vzsg4', 'action_report_operator_sheet'):
            html, _fmt = Report._render_qweb_html(
                'l10n_ua_agro_operations.%s' % ref, orders.ids)
            self.assertIn(b'o_ua_agro', html)
        html, _fmt = Report._render_qweb_html('l10n_ua_agro_operations.action_report_vzsg4', orders.ids)
        self.assertIn('Шевчук Ольга Василівна'.encode(), html)
