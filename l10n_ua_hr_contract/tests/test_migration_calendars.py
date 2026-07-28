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

    def test_migration_rejects_bridge_calendar_with_wrong_norm(self):
        """Bridge-календар із чужою нормою не приймається (знайдено на демо).

        На демо hr.work.schedule.resource_calendar_id вказував на календар із
        20 год/тиждень для 40-годинного графіка. Це поле нічим і ніколи не
        валідувалося, тож довіряти йому без звірки не можна.
        """
        wrong = self.env['resource.calendar'].create({
            'name': 'Насправді 20 годин',
            'company_id': self.company.id,
            'attendance_ids': [(5, 0, 0)] + [
                (0, 0, {'name': 'Робочий день', 'dayofweek': str(d),
                        'day_period': 'morning',
                        'hour_from': 8.0, 'hour_to': 12.0})
                for d in range(5)],
        })
        self.assertAlmostEqual(wrong.hours_per_week, 20.0, places=2)

        schedule = self._schedule(code='STD36', resource_calendar_id=wrong.id)
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        self.assertNotEqual(
            version.resource_calendar_id, wrong,
            'Migration trusted a bridge calendar with a mismatched norm')
        self.assertEqual(
            version.resource_calendar_id,
            self.env.ref('l10n_ua_hr_contract.resource_calendar_ua_std36'))

    def test_migration_preserves_locally_edited_norm(self):
        """Локально змінена норма передвизначеного графіка не втрачається.

        На демо SHIFT2X2 мав 48 год/тиждень замість типових 42; зіставлення
        за кодом мовчки перевело б працівника на 42.
        """
        schedule = self._schedule(
            name='Змінний 2/2, локально 48 год',
            code='SHIFT2X2',
            schedule_type='shift',
            hours_per_week=48.0,
            hours_per_day=12.0,
            working_days_per_week=0)
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=self.company_calendar.id)

        self._run()

        calendar = version.resource_calendar_id
        self.assertNotEqual(
            calendar,
            self.env.ref('l10n_ua_hr_contract.resource_calendar_ua_shift2x2'),
            'Migration silently replaced a locally edited norm')
        self.assertAlmostEqual(calendar.hours_per_week, 48.0, places=2)
        self.assertAlmostEqual(version.scheduled_hours_week, 48.0, places=2)

    def test_migration_leaves_already_correct_version_alone(self):
        """Версія, що вже на цільовому календарі, не потрапляє в пропущені."""
        calendar = self.env.ref(
            'l10n_ua_hr_contract.resource_calendar_ua_std36')
        schedule = self._schedule(code='STD36')
        version = self._create_version(
            work_schedule_ua_id=schedule.id,
            resource_calendar_id=calendar.id)

        with self.assertLogs('l10n_ua_hr_contract_post_migrate_19_3_0') as logs:
            self._run()

        reported = [line for line in logs.output
                    if line.startswith('WARNING')
                    and '(%s,' % version.id in line]
        self.assertFalse(
            reported,
            'Version already on the target calendar was reported for manual '
            'review: %s' % reported)
        self.assertEqual(version.resource_calendar_id, calendar)

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
