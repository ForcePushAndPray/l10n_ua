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

    def test_period_auto_created_and_linked_on_create(self):
        """Saving a leave with no existing period auto-creates the matching
        work-year period and links it."""
        leave = self._create_leave(
            self.annual_type, date(2025, 1, 10), date(2025, 1, 20))
        balance = leave.vacation_balance_id
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(2024, 7, 15))
        self.assertEqual(balance.period_end, date(2025, 7, 14))
        self.assertEqual(balance.entitled_days, self.annual_type.annual_days)

    def test_period_auto_created_for_calendar_type(self):
        """A calendar leave type (educational) also auto-creates its
        Jan 1 – Dec 31 period on save."""
        educational = self.env.ref('l10n_ua_hr_holidays.leave_type_educational')
        leave = self._create_leave(
            educational, date(2025, 3, 3), date(2025, 3, 7))
        balance = leave.vacation_balance_id
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(2025, 1, 1))
        self.assertEqual(balance.period_end, date(2025, 12, 31))

    def test_period_not_created_when_unresolvable(self):
        """Work-year type without a hire anchor cannot resolve a period, so
                nothing is auto-created and the leave stays unlinked."""
        anchorless = self.env['hr.employee'].create({'name': 'No hire date'})
        leave = self._create_leave(
            self.annual_type, date(2025, 3, 3), date(2025, 3, 7),
            employee_id=anchorless.id)
        self.assertFalse(leave.vacation_balance_id)

    def test_date_change_relinks_matching_period(self):
        """Changing the leave dates re-points the leave at the period that
        contains the new start date, auto-creating it when none exists.
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
        # Move the dates into the next work year, which has no balance yet:
        # a new period is auto-created for it and linked.
        leave.write({
            'request_date_from': date(2025, 9, 1),
            'request_date_to': date(2025, 9, 10),
            'date_from': datetime(2025, 9, 1, 8, 0, 0),
            'date_to': datetime(2025, 9, 10, 17, 0, 0),
        })
        self.assertTrue(leave.vacation_balance_id)
        self.assertNotEqual(leave.vacation_balance_id, b1)
        self.assertEqual(
            leave.vacation_balance_id.period_start, date(2025, 7, 15))
        self.assertEqual(leave.vacation_year, 2025)

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
        # Leave on 2025-03 belongs to work year 1; it auto-creates and links
        # the WY1 period. Its vacation_year is 2025 (= wy2.year), but it must
        # NOT count against wy2 (work year 2).
        leave = self._create_leave(
            self.annual_type, date(2025, 3, 3), date(2025, 3, 7))
        self.assertEqual(
            leave.vacation_balance_id.period_start, date(2024, 7, 15))
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
        # Its period is auto-created on save; approve it so the days count as
        # *used* (a draft leave would only count as planned).
        past_leave = self._create_leave(
            self.annual_type, date(2024, 9, 2), date(2024, 9, 11))
        past_leave.action_approve()
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

    def test_leave_auto_creates_and_links_its_balance(self):
        """A leave with no pre-existing period auto-creates its balance and
        links to it, so the period shows up in Vacation Balances."""
        leave = self._create_leave(
            self.annual_type, date(2024, 9, 2), date(2024, 9, 8))
        balance = leave.vacation_balance_id
        self.assertTrue(balance)
        self.assertEqual(balance.period_start, date(2024, 7, 15))
        self.assertEqual(balance.period_end, date(2025, 7, 14))
        self.assertIn(balance, self.env['hr.vacation.balance'].search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.annual_type.id),
        ]))

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

    def test_generate_backfills_missing_periods_and_cascades(self):
        """generate_balances fills gaps from the hire date so carry-over
        cascades across a year that had no balance record (employee took no
        leave that year)."""
        Balance = self.env['hr.vacation.balance']
        # Only work year 1 exists, fully unused (24 days). WY2 is missing.
        wy1 = Balance.create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        self.assertEqual(wy1.remaining_days, 24)
        # Backfill up to today (which falls in work year 2).
        Balance.generate_balances(
            year=date.today().year, leave_types=self.annual_type)
        wy2 = Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.annual_type.id),
            ('period_start', '=', date(2025, 7, 15)),
        ])
        self.assertTrue(wy2, "Work year 2 should have been backfilled")
        # WY1's 24 unused days now carry into WY2 (annual is transferable).
        self.assertEqual(wy2.carried_over, 24)
        self.assertEqual(wy2.total_available, 48)

    def test_generate_only_for_auto_calc_types(self):
        """generate_balances (no explicit types) processes only leave types
        flagged with ua_auto_calc_balance."""
        Balance = self.env['hr.vacation.balance']
        # Flag OFF -> nothing generated for this type (annual_basic ships
        # with the flag on, so turn it off explicitly for this assertion).
        self.annual_type.ua_auto_calc_balance = False
        Balance.generate_balances(year=date.today().year)
        self.assertFalse(Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.annual_type.id),
        ]))
        # Flag ON -> now its periods are generated.
        self.annual_type.ua_auto_calc_balance = True
        Balance.generate_balances(year=date.today().year)
        self.assertTrue(Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', self.annual_type.id),
        ]))

    def test_generate_skips_cross_company_leave_types(self):
        """generate_balances must not pair an employee with another company's
        leave type (multi-company: one annual_basic per company would create
        a duplicate balance for the same employee and period)."""
        Balance = self.env['hr.vacation.balance']
        company_b = self.env['res.company'].create({'name': 'Company B'})
        lt_b = self.env['hr.leave.type'].create({
            'name': 'Annual B',
            'ua_leave_category': 'annual_basic',
            'period_type': 'work',
            'annual_days': 24,
            'is_transferable': True,
            'ua_auto_calc_balance': True,
            'company_id': company_b.id,
            'requires_allocation': False,
        })
        # self.employee is not in company B, so no balance may be created for
        # it under company B's leave type.
        Balance.generate_balances(
            year=date.today().year, leave_types=lt_b)
        self.assertFalse(Balance.search([
            ('employee_id', '=', self.employee.id),
            ('leave_type_id', '=', lt_b.id),
        ]))

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

    # ------------------------------------------------------------------
    # Per-type transfer rules: carry-over cap + non-blocking warning
    # ------------------------------------------------------------------

    def _work_type(self, **overrides):
        vals = {
            'name': 'Transfer Rule Type',
            'ua_leave_category': 'other',
            'period_type': 'work',
            'annual_days': 24,
            'is_transferable': True,
            'requires_allocation': False,
        }
        vals.update(overrides)
        return self.env['hr.leave.type'].create(vals)

    def _wy1_with_unused(self, leave_type):
        """A first work-year period (index 1) with 24 unused days."""
        return self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': leave_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })

    def test_non_transferable_type_forfeits_and_warns(self):
        """A non-transferable type carries nothing forward; the leave still
        saves but shows a non-blocking warning about forfeited days."""
        lt = self._work_type(is_transferable=False)
        self._wy1_with_unused(lt)
        leave = self._create_leave(lt, date(2025, 9, 1), date(2025, 9, 5))
        wy2 = leave.vacation_balance_id
        self.assertEqual(wy2.period_index, 2)
        self.assertEqual(wy2.carried_over, 0)          # nothing carried
        self.assertTrue(leave.carryover_warning)       # 24 days forfeited
        self.assertTrue(leave.id)                       # saved despite warning

    def test_capped_transfer_caps_and_warns(self):
        """max_transfer_days caps the carry-over; the excess is reported as a
        warning without blocking the save."""
        lt = self._work_type(is_transferable=True, max_transfer_days=10)
        self._wy1_with_unused(lt)
        leave = self._create_leave(lt, date(2025, 9, 1), date(2025, 9, 5))
        wy2 = leave.vacation_balance_id
        self.assertEqual(wy2.carried_over, 10)         # capped at the max
        self.assertTrue(leave.carryover_warning)       # 14 days forfeited

    def test_unlimited_transfer_no_warning(self):
        """A transferable type with no cap carries everything and warns of
        nothing."""
        lt = self._work_type(is_transferable=True)     # no max_transfer_days
        self._wy1_with_unused(lt)
        leave = self._create_leave(lt, date(2025, 9, 1), date(2025, 9, 5))
        wy2 = leave.vacation_balance_id
        self.assertEqual(wy2.carried_over, 24)         # everything carried
        self.assertFalse(leave.carryover_warning)


