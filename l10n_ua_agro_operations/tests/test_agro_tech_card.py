import base64
import io
import zipfile
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AgroOperationsTestCase


@tagged('post_install', '-at_install')
class TestAgroTechCard(AgroOperationsTestCase):

    def test_only_approved_card_feeds_norms(self):
        self.card.action_draft()
        order = self._order(self.op_sow)
        order.action_load_norms()
        self.assertFalse(order.material_ids.filtered(lambda m: m.product_id == self.seed))
        self.card.action_approve()
        order.action_load_norms()
        self.assertTrue(order.material_ids.filtered(lambda m: m.product_id == self.seed))
        self.assertEqual(self.card.approved_by_id, self.env.user)

    def test_copy_to_next_season(self):
        self.card.operation_ids[0].write({'date_from': date(2096, 9, 20), 'date_to': date(2096, 10, 5)})
        with self.assertRaises(UserError):
            self.card.action_copy_to_next_season()           # сезону 2098 ще немає
        season = self.env['l10n_ua.agro.season'].create({
            'year': 2098, 'date_start': date(2097, 8, 1), 'date_end': date(2098, 12, 31)})
        action = self.card.action_copy_to_next_season()
        new = self.env['l10n_ua.agro.tech.card'].browse(action['res_id'])
        self.assertEqual(new.season_id, season)
        self.assertEqual(new.state, 'draft')
        self.assertEqual(new.name, 'Пшениця озима 2098')
        self.assertEqual(len(new.material_ids), 2)
        self.assertEqual(new.operation_ids[0].date_from, date(2097, 9, 20))
        with self.assertRaises(UserError):
            self.card.action_copy_to_next_season()           # уже є

    def test_print_and_xlsx(self):
        operations, materials = self.card._print_lines()
        sow = [r for r in operations if r['operation'] == self.op_sow.name][0]
        self.assertEqual(sow['fuel_ha'], 6.0)
        self.assertEqual(sow['labor'], 9000.0)                 # 90 грн × 100 га
        seed = [r for r in materials if r['product'] == self.seed.display_name][0]
        self.assertEqual(seed['quantity'], 22000.0)
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_agro_operations.action_report_tech_card', self.card.ids)
        self.assertIn(b'o_ua_agro', html)
        action = self.card.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        data = base64.b64decode(attachment.datas)
        self.assertTrue(data.startswith(b'PK'))                # xlsx — zip
        with zipfile.ZipFile(io.BytesIO(data)) as book:
            strings = book.read('xl/sharedStrings.xml').decode()
            sheet = book.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn(self.seed.display_name, strings)
        self.assertIn('<v>878000</v>', sheet)
