"""Структура меню «Медицина»: розклад — точка входу, звіти — pivot/graph."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMedecinMenu(TransactionCase):

    def _first_leaf(self, menu):
        """Перший пункт з дією (обхід у глибину за sequence, як веб-клієнт)."""
        if menu.action:
            return menu
        for child in menu.child_id.sorted(lambda m: (m.sequence, m.id)):
            leaf = self._first_leaf(child)
            if leaf:
                return leaf
        return self.env['ir.ui.menu']

    def test_root_opens_schedule(self):
        root = self.env.ref('l10n_ua_medecin_base.menu_medecin_root')
        self.assertEqual(root.name, 'Медицина')
        leaf = self._first_leaf(root)
        self.assertEqual(
            leaf, self.env.ref('l10n_ua_medecin_clinical.menu_encounter_calendar'))
        action = self.env.ref('l10n_ua_medecin_clinical.action_encounter_calendar')
        self.assertEqual(leaf.action, action)
        self.assertEqual(action.view_mode.split(',')[0], 'calendar')

    def test_reporting_actions_pivot_graph(self):
        for xmlid in (
            'l10n_ua_medecin_clinical.action_report_encounter',
            'l10n_ua_medecin_clinical.action_report_morbidity',
            'l10n_ua_medecin_patient.action_report_declaration',
        ):
            action = self.env.ref(xmlid)
            modes = action.view_mode.split(',')
            self.assertIn('pivot', modes, xmlid)
            self.assertIn('graph', modes, xmlid)
            reporting = self.env.ref('l10n_ua_medecin_base.menu_medecin_reporting')
            self.assertTrue(
                self.env['ir.ui.menu'].search([
                    ('action', '=', f'ir.actions.act_window,{action.id}'),
                    ('parent_id', '=', reporting.id),
                ]), f'{xmlid}: немає пункту в «Звітність»')

    def test_new_actions_views_load(self):
        for xmlid in (
            'l10n_ua_medecin_clinical.action_encounter_calendar',
            'l10n_ua_medecin_clinical.action_encounter',
            'l10n_ua_medecin_clinical.action_diagnosis',
            'l10n_ua_medecin_clinical.action_report_encounter',
            'l10n_ua_medecin_clinical.action_report_morbidity',
            'l10n_ua_medecin_patient.action_report_declaration',
            'l10n_ua_medecin_base.action_medecin_doctor',
        ):
            action = self.env.ref(xmlid)
            views = [(v.id, v.view_mode) for v in action.view_ids] or \
                [(False, m) for m in action.view_mode.split(',')]
            res = self.env[action.res_model].get_views(
                views + [(action.search_view_id.id, 'search')])
            for mode in action.view_mode.split(','):
                self.assertIn(mode, res['views'], f'{xmlid}: {mode}')
