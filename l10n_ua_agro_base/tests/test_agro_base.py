from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAgroBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Season = cls.env['l10n_ua.agro.season']
        cls.season_26 = Season.create({
            'year': 2096, 'date_start': date(2095, 8, 1), 'date_end': date(2096, 12, 31)})
        cls.season_27 = Season.create({
            'year': 2097, 'date_start': date(2096, 8, 1), 'date_end': date(2097, 12, 31)})
        cls.field = cls.env['l10n_ua.agro.field'].create({
            'name': 'За фермою', 'code': 'F-01', 'area': 100.0})
        cls.wheat = cls.env.ref('l10n_ua_agro_base.crop_wheat_winter')
        cls.sunflower = cls.env.ref('l10n_ua_agro_base.crop_sunflower')
        cls.pumpkin = cls.env.ref('l10n_ua_agro_base.crop_pumpkin_seed')

    def _plant(self, season, crop, area):
        return self.env['l10n_ua.agro.planting'].create({
            'field_id': self.field.id, 'season_id': season.id,
            'crop_id': crop.id, 'area': area})

    def test_sown_area_cannot_exceed_field(self):
        self._plant(self.season_26, self.wheat, 60.0)
        self._plant(self.season_26, self.pumpkin, 40.0)
        with self.assertRaises(ValidationError):
            self._plant(self.season_26, self.sunflower, 0.5)

    def test_predecessor_and_current_crop(self):
        self._plant(self.season_26, self.wheat, 70.0)
        self._plant(self.season_26, self.pumpkin, 30.0)
        planting = self._plant(self.season_27, self.sunflower, 100.0)
        # попередник — культура з найбільшою площею минулого сезону
        self.assertEqual(planting.predecessor_crop_id, self.wheat)
        self.assertEqual(self.field.current_crop_id, self.sunflower)
        self.assertEqual(self.season_27.sown_area, 100.0)

    def test_season_name_and_dates(self):
        self.assertEqual(self.season_26.name, 'Season 2096')
        with self.assertRaises(ValidationError):
            self.season_26.date_end = date(2095, 1, 1)

    def test_menu_and_groups(self):
        root = self.env.ref('l10n_ua_agro_base.menu_l10n_ua_agro_root')
        self.assertTrue(root.web_icon)
        self.assertIn(self.env.ref('l10n_ua_agro_base.group_ua_agro_user'), root.group_ids)
