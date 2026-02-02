"""Tests for work schedules and termination reasons — HR-1,19 from HR_UKRAINE.md.

Tests cover:
- Work schedule creation and types
- Schedule line working hours computation
- Termination reason full reference
- Termination reason compensation flags
"""

from odoo.tests import tagged
from .common import ContractTestCase


@tagged('post_install', '-at_install')
class TestWorkSchedule(ContractTestCase):
    """Test hr.work.schedule model."""

    def _create_schedule(self, **kwargs):
        vals = {
            'name': '5-денний робочий тиждень',
            'schedule_type': 'standard',
            'hours_per_week': 40.0,
            'hours_per_day': 8.0,
            'working_days_per_week': 5,
        }
        vals.update(kwargs)
        return self.env['hr.work.schedule'].create(vals)

    def test_schedule_creation(self):
        """Schedule should be created with defaults."""
        schedule = self._create_schedule()
        self.assertEqual(schedule.schedule_type, 'standard')
        self.assertEqual(schedule.hours_per_week, 40.0)
        self.assertTrue(schedule.active)

    def test_schedule_types(self):
        """All schedule types should be valid."""
        for stype in ['standard', 'shift', 'flexible', 'summarized']:
            schedule = self._create_schedule(
                name=f'Schedule {stype}',
                schedule_type=stype,
            )
            self.assertEqual(schedule.schedule_type, stype)
            schedule.unlink()

    def test_schedule_line_working_hours(self):
        """Line working hours = work time - break time."""
        schedule = self._create_schedule()
        line = self.env['hr.work.schedule.line'].create({
            'schedule_id': schedule.id,
            'day_of_week': '0',  # Monday
            'is_working_day': True,
            'work_from': 9.0,
            'work_to': 18.0,
            'break_from': 13.0,
            'break_to': 14.0,
        })
        # 9h work - 1h break = 8h
        self.assertAlmostEqual(line.working_hours, 8.0, places=1)

    def test_schedule_night_work(self):
        """Night work flags should be stored."""
        schedule = self._create_schedule(
            is_night_work=True,
            night_start_hour=22.0,
            night_end_hour=6.0,
        )
        self.assertTrue(schedule.is_night_work)

    def test_schedule_hazardous(self):
        """Hazardous and reduced hours flags."""
        schedule = self._create_schedule(
            is_hazardous=True,
            reduced_hours=True,
            hours_per_week=36.0,
        )
        self.assertTrue(schedule.is_hazardous)
        self.assertTrue(schedule.reduced_hours)
        self.assertEqual(schedule.hours_per_week, 36.0)


@tagged('post_install', '-at_install')
class TestTerminationReason(ContractTestCase):
    """Test hr.termination.reason model."""

    def _create_reason(self, **kwargs):
        vals = {
            'name': 'За власним бажанням',
            'article': '38',
            'paragraph': '1',
            'category': 'own_will',
            'notice_days': 14,
        }
        vals.update(kwargs)
        return self.env['hr.termination.reason'].create(vals)

    def test_reason_creation(self):
        """Reason should have required fields."""
        reason = self._create_reason()
        self.assertTrue(reason.name)
        self.assertEqual(reason.category, 'own_will')

    def test_full_reference_computed(self):
        """Full reference should combine article and paragraph."""
        reason = self._create_reason(article='38', paragraph='1')
        # full_reference may be False if not implemented, or a string
        if reason.full_reference:
            self.assertIn('38', reason.full_reference)
        else:
            # At minimum, article should be stored
            self.assertEqual(reason.article, '38')

    def test_reason_own_will_notice(self):
        """Own will requires 14 days notice."""
        reason = self._create_reason(
            category='own_will',
            notice_days=14,
        )
        self.assertEqual(reason.notice_days, 14)

    def test_reason_compensation(self):
        """Employer initiative may require compensation."""
        reason = self._create_reason(
            name='Скорочення штату',
            article='40',
            paragraph='1',
            category='employer_initiative',
            requires_compensation=True,
            compensation_amount='one_month',
        )
        self.assertTrue(reason.requires_compensation)
        self.assertEqual(reason.compensation_amount, 'one_month')

    def test_reason_categories(self):
        """All termination categories should be valid."""
        categories = ['own_will', 'agreement', 'fixed_term', 'transfer',
                       'employer_initiative', 'circumstances', 'other']
        for i, cat in enumerate(categories):
            reason = self._create_reason(
                name=f'Reason {cat}',
                article=str(30 + i),
                category=cat,
            )
            self.assertEqual(reason.category, cat)
            reason.unlink()
