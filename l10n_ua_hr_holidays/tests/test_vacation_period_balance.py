from datetime import date, datetime
from odoo.exceptions import ValidationError
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

    def test_create_period_button_creates_and_links(self):
        """The inline Create button builds the balance and links the leave;
        the button hides once a period is linked."""
        leave = self._create_leave(
            self.annual_type, date(2025, 1, 10), date(2025, 1, 20))
        # No matching balance yet → button is offered
        self.assertFalse(leave.vacation_balance_id)
        self.assertTrue(leave.show_create_vacation_period)

        leave.action_create_vacation_period()

        balance = leave.vacation_balance_id
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(2024, 7, 15))
        self.assertEqual(balance.period_end, date(2025, 7, 14))
        self.assertEqual(balance.entitled_days, self.annual_type.annual_days)
        # Linked now → button hidden
        self.assertFalse(leave.show_create_vacation_period)

    def test_create_period_button_for_any_available_type(self):
        """The button is offered for any employee-available leave type, not
        just the annual ones — educational (calendar) included."""
        educational = self.env.ref('l10n_ua_hr_holidays.leave_type_educational')
        leave = self._create_leave(
            educational, date(2025, 3, 3), date(2025, 3, 7))
        self.assertTrue(leave.show_create_vacation_period)
        leave.action_create_vacation_period()
        balance = leave.vacation_balance_id
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(2025, 1, 1))
        self.assertEqual(balance.period_end, date(2025, 12, 31))

    def test_create_period_button_hidden_when_unresolvable(self):
        """Work-year type without a hire anchor cannot resolve a period, so
        the button stays hidden."""
        anchorless = self.env['hr.employee'].create({'name': 'No hire date'})
        leave = self._create_leave(
            self.annual_type, date(2025, 3, 3), date(2025, 3, 7),
            employee_id=anchorless.id)
        self.assertFalse(leave.show_create_vacation_period)

    def test_date_change_relinks_matching_period(self):
        """Changing the leave dates re-points the leave at the period that
        contains the new start date; the button reappears when none exists.
        vacation_year follows the start date and is read-only."""
        b1 = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        leave = self._create_leave(
            self.annual_type, date(2025, 1, 10), date(2025, 1, 20))
        self.assertEqual(leave.vacation_balance_id, b1)
        self.assertEqual(leave.vacation_year, 2025)
        # Move the dates into a work year with no balance yet.
        leave.write({
            'request_date_from': date(2026, 9, 1),
            'request_date_to': date(2026, 9, 10),
            'date_from': datetime(2026, 9, 1, 8, 0, 0),
            'date_to': datetime(2026, 9, 10, 17, 0, 0),
        })        
        self.assertFalse(leave.vacation_balance_id)
        self.assertTrue(leave.show_create_vacation_period)
        self.assertEqual(leave.vacation_year, 2026)

    def test_mismatched_period_blocks_save(self):
        """A linked period whose year differs from the leave year is
        rejected by the constraint."""
        wrong = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2026, 7, 15),
            'period_end': date(2027, 7, 14),
            'period_index': 3,
            'entitled_days': 24,
        })
        leave = self._create_leave(
            self.annual_type, date(2025, 1, 10), date(2025, 1, 20))
        with self.assertRaises(ValidationError):
            leave.vacation_balance_id = wrong

    def test_used_days_not_lumped_from_other_work_year(self):
        """A leave belonging to an earlier work year must not inflate a
        later work year's used_days just because they share a calendar year
        in the `year` field (period_start.year)."""
        # Employee hired 2024-07-15:
        #   work year 1: 2024-07-15 .. 2025-07-14  (year = 2024)
        #   work year 2: 2025-07-15 .. 2026-07-14  (year = 2025)
        wy2 = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2025, 7, 15),
            'period_end': date(2026, 7, 14),
            'period_index': 2,
            'entitled_days': 24,
        })
        # Leave on 2025-03 belongs to work year 1 (no balance for it yet, so
        # it stays unlinked); its vacation_year is 2025, which equals wy2.year.
        leave = self._create_leave(
            self.annual_type, date(2025, 3, 3), date(2025, 3, 7))
        self.assertFalse(leave.vacation_balance_id)
        wy2.invalidate_recordset(['used_days', 'planned_days'])
        wy2._compute_used_days()
        self.assertEqual(wy2.used_days, 0)
        self.assertEqual(wy2.planned_days, 0)

    def test_backdated_period_carries_over_to_current(self):
        """Creating a past period (with an unused-days leave) propagates its
        remaining days as Carried Over into the following period."""
        # Current work year (index 2) already exists with no carry-over.
        current = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2025, 7, 15),
            'period_end': date(2026, 7, 14),
            'period_index': 2,
            'entitled_days': 24,
        })
        self.assertEqual(current.carried_over, 0)

        # Back-dated leave for the previous work year (index 1), using 10 days.
        past_leave = self._create_leave(
            self.annual_type, date(2024, 9, 2), date(2024, 9, 11))
        # Create the missing past period via the leave's button.
        past_leave.action_create_vacation_period()
        past = past_leave.vacation_balance_id
        self.assertEqual(past.period_start, date(2024, 7, 15))
        self.assertEqual(past.used_days, past_leave.calendar_days)

        # The current period now carries the past period's remaining days.
        expected = past.total_available - past.used_days
        self.assertEqual(current.carried_over, expected)
        self.assertEqual(current.total_available, 24 + expected)

    def test_leave_before_hire_is_blocked(self):
        """A leave that starts before the employee's hire date is rejected."""
        with self.assertRaises(ValidationError):
            self._create_leave(
                self.annual_type, date(2023, 5, 1), date(2023, 5, 10))

    def test_calendar_period_before_hire_hidden_and_blocked(self):
        """A calendar-type leave whose whole year precedes the hire date
        offers no Create button, and the balance itself is rejected."""
        social = self.social_type
        # Employee hired 2024-07-15; a 2023 social leave predates hire.
        with self.assertRaises(ValidationError):
            self._create_leave(social, date(2023, 3, 1), date(2023, 3, 5))
        # Direct balance for a fully-pre-hire calendar year is rejected too.
        with self.assertRaises(ValidationError):
            self.env['hr.vacation.balance'].create({
                'employee_id': self.employee.id,
                'leave_type_id': social.id,
                'period_start': date(2023, 1, 1),
                'period_end': date(2023, 12, 31),
                'period_index': 2023,
                'entitled_days': 10,
            })

    def test_default_get_prefills_period_from_leave_context(self):
        """default_get resolves the whole period from the leave form's
        context defaults (employee, type, year)."""
        Balance = self.env['hr.vacation.balance'].with_context(
            default_employee_id=self.employee.id,
            default_leave_type_id=self.annual_type.id,
            default_period_year=2025,
        )
        defaults = Balance.default_get([
            'employee_id', 'leave_type_id', 'company_id',
            'period_start', 'period_end', 'period_index',
        ])
        self.assertEqual(defaults.get('period_start'), date(2025, 7, 15))
        self.assertEqual(defaults.get('period_end'), date(2026, 7, 14))
        self.assertEqual(defaults.get('period_index'), 2)
        self.assertEqual(
            defaults.get('company_id'), self.employee.company_id.id)

    def test_default_get_calendar_type_from_context(self):
        Balance = self.env['hr.vacation.balance'].with_context(
            default_employee_id=self.employee.id,
            default_leave_type_id=self.social_type.id,
            default_period_year=2026,
        )
        defaults = Balance.default_get(
            ['period_start', 'period_end', 'period_index'])
        self.assertEqual(defaults.get('period_start'), date(2026, 1, 1))
        self.assertEqual(defaults.get('period_end'), date(2026, 12, 31))
        self.assertEqual(defaults.get('period_index'), 2026)

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

