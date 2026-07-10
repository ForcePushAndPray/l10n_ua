from datetime import date

from odoo.tests.common import TransactionCase


class TestVacationPeriodBalance(TransactionCase):
    """PR 2: period-based hr.vacation.balance + vacation_balance_id on hr.leave."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Тестовий Працівник Періодів',
            'hire_date': date(2024, 7, 15),
        })
        cls.annual_type = cls.env.ref(
            'l10n_ua_hr_holidays.leave_type_annual_basic')
        cls.social_type = cls.env.ref(
            'l10n_ua_hr_holidays.leave_type_social_children')

    def _create_leave(self, leave_type, date_from, date_to, **extra):
        vals = {
            'name': 'Test leave',
            'employee_id': self.employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        }
        vals.update(extra)
        return self.env['hr.leave'].create(vals)

    # ------------------------------------------------------------------
    # Balance period derivation
    # ------------------------------------------------------------------

    def test_work_period_balance_create(self):
        """Work-year balance derives bounds from hire_date anniversary."""
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        self.assertEqual(balance.period_type, 'work')
        self.assertEqual(balance.year, 2024)
        self.assertIn('15.07.2024', balance.period_label)
        self.assertIn('14.07.2025', balance.period_label)

    def test_calendar_period_balance_create(self):
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.social_type.id,
            'period_start': date(2025, 1, 1),
            'period_end': date(2025, 12, 31),
            'period_index': 2025,
            'entitled_days': 10,
        })
        self.assertEqual(balance.period_type, 'calendar')
        self.assertEqual(balance.year, 2025)
        self.assertEqual(balance.period_label, '01.01.2025 – 31.12.2025')

    def test_create_with_legacy_year_derives_work_period(self):
        """Legacy create({'year': ...}) still works: the period is derived
        from the leave type's period_type (transfer wizard compatibility)."""
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'year': 2024,
            'entitled_days': 24,
        })
        self.assertEqual(balance.period_start, date(2024, 7, 15))
        self.assertEqual(balance.period_end, date(2025, 7, 14))
        self.assertEqual(balance.period_index, 1)

    def test_create_with_legacy_year_calendar_type(self):
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.social_type.id,
            'year': 2024,
            'entitled_days': 10,
        })
        self.assertEqual(balance.period_start, date(2024, 1, 1))
        self.assertEqual(balance.period_end, date(2024, 12, 31))

    def test_unique_constraint_on_period_start(self):
        self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
        })
        with self.assertRaises(Exception):
            self.env['hr.vacation.balance'].create({
                'employee_id': self.employee.id,
                'leave_type_id': self.annual_type.id,
                'period_start': date(2024, 7, 15),
                'period_end': date(2025, 7, 14),
            })

    def test_proportional_entitled_days_short_period(self):
        """A shortened period (e.g. termination) prorates entitled days."""
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            # 8 months out of 12
            'period_end': date(2025, 3, 14),
        })
        # 243 days / 365 * 24 ≈ 15.98
        self.assertAlmostEqual(balance.entitled_days, 24 * 243 / 365.0, places=1)

    # ------------------------------------------------------------------
    # Leave ↔ balance linking
    # ------------------------------------------------------------------

    def test_leave_auto_links_work_balance(self):
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'entitled_days': 24,
        })
        leave = self._create_leave(
            self.annual_type, date(2025, 1, 10), date(2025, 1, 20))
        self.assertEqual(leave.vacation_balance_id, balance)

    def test_cross_calendar_year_leave_single_period(self):
        """A leave spanning Dec–Jan stays within one work year and is
        charged fully against that single balance."""
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'entitled_days': 24,
        })
        leave = self._create_leave(
            self.annual_type, date(2024, 12, 20), date(2025, 1, 5))
        leave.action_approve()
        self.assertEqual(leave.vacation_balance_id, balance)
        self.assertEqual(balance.used_days, leave.calendar_days)

    def test_balance_created_after_leave_links_retroactively(self):
        """generate/manual balance created later picks up existing leaves."""
        leave = self._create_leave(
            self.annual_type, date(2024, 9, 2), date(2024, 9, 8))
        self.assertFalse(leave.vacation_balance_id)
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'entitled_days': 24,
        })
        self.assertEqual(leave.vacation_balance_id, balance)

    def test_remaining_before_within_work_period(self):
        """Chronological remaining_before counts leaves of the same work
        year even across a calendar-year boundary."""
        self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'entitled_days': 24,
        })
        first = self._create_leave(
            self.annual_type, date(2024, 10, 7), date(2024, 10, 13))
        second = self._create_leave(
            self.annual_type, date(2025, 2, 3), date(2025, 2, 9))
        self.assertEqual(first.remaining_days_before, 24)
        self.assertEqual(
            second.remaining_days_before, 24 - first.calendar_days)

    # ------------------------------------------------------------------
    # generate_balances
    # ------------------------------------------------------------------

    def test_generate_balances_work_type(self):
        Balance = self.env['hr.vacation.balance']
        Balance.generate_balances(
            year=date.today().year, leave_types=self.annual_type)
        balance = Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.annual_type.id),
        ], limit=1)
        self.assertTrue(balance)
        # Bounds anchored to July 15 anniversary, not Jan 1
        self.assertEqual(balance.period_start.month, 7)
        self.assertEqual(balance.period_start.day, 15)

    def test_generate_balances_calendar_type(self):
        Balance = self.env['hr.vacation.balance']
        year = date.today().year
        Balance.generate_balances(year=year, leave_types=self.social_type)
        balance = Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.social_type.id),
        ], limit=1)
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(year, 1, 1))
        self.assertEqual(balance.period_end, date(year, 12, 31))

    def test_generate_balances_skips_employee_without_hire_date(self):
        Balance = self.env['hr.vacation.balance']
        nameless = self.env['hr.employee'].create({'name': 'Без дати найму'})
        Balance.generate_balances(
            year=date.today().year, leave_types=self.annual_type)
        balance = Balance.search([
            ('employee_id', '=', nameless.id),
            ('leave_type_id', '=', self.annual_type.id),
        ])
        self.assertFalse(balance)

    def test_reanchor_period_after_hire_date_set(self):
        """A work-year balance created while the employee had no hire
        anchor gets calendar bounds; once hire_date is known, Recalculate
        re-anchors it to the hire anniversary."""
        employee = self.env['hr.employee'].create({'name': 'Пізній якір'})
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': employee.id,
            'leave_type_id': self.annual_type.id,
            'year': 2026,
            'entitled_days': 24,
        })
        # No anchor at creation time → calendar fallback
        self.assertEqual(balance.period_start, date(2026, 1, 1))
        self.assertEqual(balance.period_end, date(2026, 12, 31))

        employee.hire_date = date(2025, 7, 1)
        balance.action_recalculate()

        self.assertEqual(balance.period_start, date(2026, 7, 1))
        self.assertEqual(balance.period_end, date(2027, 6, 30))
        self.assertEqual(balance.period_index, 2)

    def test_reanchor_noop_when_already_correct(self):
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        balance.action_recalculate()
        self.assertEqual(balance.period_start, date(2024, 7, 15))
        self.assertEqual(balance.period_end, date(2025, 7, 14))

    def test_carryover_between_work_years(self):
        Balance = self.env['hr.vacation.balance']
        first = Balance.create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        self.assertEqual(first.remaining_days, 24)
        # Simulate the generator creating the next work year
        second = Balance.create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2025, 7, 15),
            'period_end': date(2026, 7, 14),
            'period_index': 2,
            'entitled_days': 24,
            'carried_over': first.remaining_days,
        })
        self.assertEqual(second.total_available, 48)

