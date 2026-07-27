"""Тести міграції 19.0.3.0.0: hr.work.schedule → resource.calendar (#213).

Скрипт міграції — не імпортований пакет, тому вантажимо його з файлу і
викликаємо migrate() на курсорі тестової транзакції: усе відкотиться разом
із нею.
"""

import importlib.util
import os

from odoo.tests import tagged

from .common import ContractTestCase

MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', '19.0.3.0.0', 'post-migrate.py')


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'l10n_ua_hr_contract_post_migrate_19_3_0', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestMigrationCalendars(ContractTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration = _load_migration()
        cls.company_calendar = cls.company.resource_calendar_id

    def _schedule(self, **kwargs):
        vals = {
            'name': 'Тестовий графік',
            'schedule_type': 'standard',
            'hours_per_week': 36.0,
            'hours_per_day': 7.2,
            'working_days_per_week': 5,
            'company_id': self.company.id,
        }
        vals.update(kwargs)
        return self.env['hr.work.schedule'].create(vals)

    def _run(self):
        self.migration.migrate(self.env.cr, '19.0.2.0.0')
        self.env.invalidate_all()

    def test_migration_maps_by_code(self):
        """Версія з графіком STD36 потрапляє на resource_calendar_ua_std36."""
        schedule = self._schedule(code='STD36')
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        self.assertEqual(
            version.resource_calendar_id,
            self.env.ref('l10n_ua_hr_contract.resource_calendar_ua_std36'))
        self.assertAlmostEqual(version.scheduled_hours_day, 7.2, places=2)

    def test_migration_preserves_custom_calendar(self):
        """Свідомо обраний календар не перезаписується."""
        custom = self.env['resource.calendar'].create({
            'name': 'Індивідуальний графік',
            'company_id': self.company.id,
        })
        schedule = self._schedule(code='STD36')
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=custom.id)

        self._run()

        self.assertEqual(
            version.resource_calendar_id, custom,
            'Migration overwrote a calendar the HR officer chose deliberately')

    def test_migration_creates_calendar_for_custom_schedule(self):
        """Клієнтський графік без відповідника дає новий календар."""
        schedule = self._schedule(
            name='Клієнтський 30-годинний',
            code='CUSTOM30',
            hours_per_week=30.0,
            hours_per_day=6.0,
            working_days_per_week=5)
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        calendar = version.resource_calendar_id
        self.assertNotEqual(calendar, self.company_calendar)
        self.assertEqual(calendar.ua_code, 'CUSTOM30')
        self.assertAlmostEqual(calendar.hours_per_week, 30.0, places=2)
        self.assertAlmostEqual(calendar.hours_per_day, 6.0, places=2)
        self.assertAlmostEqual(version.scheduled_hours_day, 6.0, places=2)

    def test_migration_creates_flexible_calendar_for_shift_schedule(self):
        """Змінний графік без тижневої сітки зберігає явну норму."""
        schedule = self._schedule(
            name='Клієнтський змінний',
            code='CUSTOMSHIFT',
            schedule_type='shift',
            hours_per_week=42.0,
            hours_per_day=12.0,
            working_days_per_week=0)
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        calendar = version.resource_calendar_id
        self.assertEqual(calendar.ua_schedule_type, 'shift')
        self.assertEqual(calendar.schedule_type, 'flexible')
        self.assertFalse(calendar.attendance_ids)
        self.assertAlmostEqual(calendar.hours_per_week, 42.0, places=2)
        self.assertAlmostEqual(calendar.hours_per_day, 12.0, places=2)

    def test_migration_reuses_calendar_across_versions(self):
        """Один клієнтський графік дає один календар на всі версії."""
        schedule = self._schedule(name='Спільний', code='SHARED30')
        first = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)
        second = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        self.assertEqual(first.resource_calendar_id,
                         second.resource_calendar_id)
        self.assertNotEqual(first.resource_calendar_id, self.company_calendar)
