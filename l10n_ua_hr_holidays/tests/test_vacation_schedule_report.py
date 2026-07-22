from datetime import date
from odoo.tests.common import TransactionCase


class TestVacationScheduleReport(TransactionCase):
    """PR 3: vacation schedule and summary report work with both accounting
    period types (calendar year and work year)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Schedule Test Employee',
            'hire_date': date(2024, 7, 15),
        })
        # annual_basic and annual_additional accrue on a WORK year;
        # social_children on a CALENDAR year.
        cls.annual_type = cls.env.ref(
            'l10n_ua_hr_holidays.leave_type_annual_basic')
        cls.additional_type = cls.env.ref(
            'l10n_ua_hr_holidays.leave_type_annual_additional')
        cls.social_type = cls.env.ref(
            'l10n_ua_hr_holidays.leave_type_social_children')

    def _create_leave(self, leave_type, date_from, date_to):
        return self.env['hr.leave'].create({
            'name': 'Test leave',
            'employee_id': self.employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        })

    # ------------------------------------------------------------------
    # Schedule: planned days pulled from the right period
    # ------------------------------------------------------------------

    def test_schedule_generate_work_period(self):
        """action_generate_lines resolves a work-year leave type by the work
        year that overlaps Jul 1 of the schedule year and pulls its
        total_available (entitled + carried over)."""
        # Work year containing 2025-07-01 for a 2024-07-15 hire:
        # 2024-07-15 .. 2025-07-14 (index 1).
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
            'carried_over': 6,
        })
        self.assertEqual(balance.total_available, 30)

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        # One current-period row per balance; check the one for this balance.
        line = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee
            and l.vacation_balance_id == balance)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.planned_days, 30)

    # ------------------------------------------------------------------
    # Schedule: one row per leave, actual days per leave
    # ------------------------------------------------------------------

    def test_schedule_one_row_per_leave(self):
        """An employee with several planned leaves gets one row per leave, each
        carrying its own type, period, calendar days and dates."""
        basic = self._create_leave(
            self.annual_type, date(2025, 2, 10), date(2025, 2, 14))
        additional = self._create_leave(
            self.additional_type, date(2025, 8, 1), date(2025, 8, 3))

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        # Exactly one row per planned leave (past-period rows, if any, are
        # counted separately and are not leave-linked).
        leaf_lines = lines.filtered(lambda l: l.leave_id)
        self.assertEqual(len(leaf_lines), 2)

        basic_line = lines.filtered(lambda l: l.leave_id == basic)
        add_line = lines.filtered(lambda l: l.leave_id == additional)
        self.assertTrue(basic_line and add_line)

        # Each row mirrors its own leave: type, balance, days and dates.
        self.assertEqual(basic_line.leave_type_id, self.annual_type)
        self.assertEqual(basic_line.vacation_balance_id,
                         basic.vacation_balance_id)
        self.assertEqual(basic_line.planned_days, basic.calendar_days)
        self.assertEqual(basic_line.vacation_period_display,
                         '10.02.2025 - 14.02.2025')
        self.assertEqual(add_line.leave_type_id, self.additional_type)
        self.assertEqual(add_line.vacation_period_display,
                         '01.08.2025 - 03.08.2025')
        # Job position is mirrored from the employee.
        self.assertEqual(basic_line.job_id, self.employee.job_id)

    def test_schedule_actual_days_per_leave(self):
        """actual_days on a row equals the linked leave's calendar days once it
        is approved, and 0 while it is still only planned."""
        basic = self._create_leave(
            self.annual_type, date(2025, 2, 10), date(2025, 2, 14))
        basic.action_approve()
        additional = self._create_leave(
            self.additional_type, date(2025, 8, 1), date(2025, 8, 3))
        # additional stays in a planning state (not approved)

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        basic_line = lines.filtered(lambda l: l.leave_id == basic)
        add_line = lines.filtered(lambda l: l.leave_id == additional)
        self.assertEqual(basic_line.actual_days, basic.calendar_days)
        self.assertEqual(add_line.actual_days, 0)

    def test_schedule_no_leave_falls_back_to_entitlement(self):
        """A current-year period the employee has a balance for is listed even
        with no planned leave — as its own row, no linked leave, empty dates,
        planned days = the period's total available."""
        bal = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
            'carried_over': 6,
        })
        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        line = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee
            and l.vacation_balance_id == bal)
        self.assertEqual(len(line), 1)
        self.assertFalse(line.leave_id)
        self.assertEqual(line.planned_days, 30)
        self.assertEqual(line.vacation_period_display, '')

    def test_schedule_hides_untouched_past_period(self):
        """A past period with NO leaves taken (used = 0) is not listed, even
        though its whole entitlement is technically unused - only partially
        used past periods are shown."""
        untouched = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        self.assertEqual(untouched.used_days, 0)

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2027,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        self.assertFalse(
            lines.filtered(lambda l: l.vacation_balance_id == untouched))

    def test_schedule_shows_prior_period_ending_within_year(self):
        """A previous work year that STARTED before the schedule year but ends
        inside it (Jun-May work year for a 2026 schedule) still counts as a
        past period and is listed with its own unused days (entitled - used)."""
        emp = self.env['hr.employee'].create({
            'name': 'June Hire',
            'hire_date': date(2024, 6, 1),
        })
        # Work year 2025-06-01 .. 2026-05-31: ends inside 2026 but started in
        # 2025, so it is a previous period relative to the 2026 schedule.
        prior = self.env['hr.vacation.balance'].create({
            'employee_id': emp.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2025, 6, 1),
            'period_end': date(2026, 5, 31),
            'period_index': 2,
            'entitled_days': 24,
        })
        # Use part of that period's entitlement (a 2025 leave, not in the 2026
        # schedule year) so unused = entitled - used > 0.
        leave = self.env['hr.leave'].create({
            'name': 'Prior-year leave',
            'employee_id': emp.id,
            'holiday_status_id': self.annual_type.id,
            'request_date_from': date(2025, 9, 1),
            'request_date_to': date(2025, 9, 10),
        })
        leave.action_approve()
        self.assertTrue(prior.used_days > 0)
        expected_unused = int(round(prior.entitled_days - prior.used_days))

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2026,
            'company_id': emp.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(lambda l: l.employee_id == emp)
        prior_line = lines.filtered(lambda l: l.vacation_balance_id == prior)
        self.assertEqual(len(prior_line), 1)
        self.assertFalse(prior_line.leave_id)
        self.assertEqual(prior_line.planned_days, expected_unused)

    def test_schedule_includes_non_annual_balance_types(self):
        """A leave of any tracked type (e.g. Chornobyl additional leave, which
        is neither annual_basic nor annual_additional) appears in the schedule,
        matching what is shown in Vacation Balances."""
        chornobyl = self.env.ref('l10n_ua_hr_holidays.leave_type_chornobyl')
        leave = self.env['hr.leave'].create({
            'name': 'Chornobyl leave',
            'employee_id': self.employee.id,
            'holiday_status_id': chornobyl.id,
            'request_date_from': date(2025, 4, 1),
            'request_date_to': date(2025, 4, 4),
        })
        leave.action_approve()

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        chorn_line = lines.filtered(lambda l: l.leave_id == leave)
        self.assertEqual(len(chorn_line), 1)
        self.assertEqual(chorn_line.leave_type_id, chornobyl)

    def test_schedule_shows_current_period_without_leave(self):
        """A current-year period the employee has a balance for (the annual
        basic period) is listed even when the only planned leave is of another
        type, so the entitlement is not hidden."""
        chornobyl = self.env.ref('l10n_ua_hr_holidays.leave_type_chornobyl')
        # Hired Jan 1 -> the annual basic work year is the calendar year 2026.
        emp = self.env['hr.employee'].create({
            'name': 'January Hire',
            'hire_date': date(2026, 1, 1),
        })
        basic_bal = self.env['hr.vacation.balance'].create({
            'employee_id': emp.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2026, 1, 1),
            'period_end': date(2026, 12, 31),
            'period_index': 1,
            'entitled_days': 24,
        })
        # A leave of a DIFFERENT type (Chornobyl) in 2026.
        self.env['hr.leave'].create({
            'name': 'Chornobyl 2026',
            'employee_id': emp.id,
            'holiday_status_id': chornobyl.id,
            'request_date_from': date(2026, 4, 1),
            'request_date_to': date(2026, 4, 4),
        }).action_approve()

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2026,
            'company_id': emp.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(lambda l: l.employee_id == emp)
        # The Chornobyl leave shows, AND the annual basic period (no leave)
        # still gets its own row.
        self.assertTrue(lines.filtered(lambda l: l.leave_type_id == chornobyl))
        basic_line = lines.filtered(lambda l: l.vacation_balance_id == basic_bal)
        self.assertEqual(len(basic_line), 1)
        self.assertFalse(basic_line.leave_id)
        self.assertEqual(basic_line.leave_type_id, self.annual_type)

    def test_report_lines_grouped_by_employee(self):
        """The PDF report helper groups an employee's leave rows so the name/No/
        job cells rowspan across all of them, and leaves of different types are
        separate type-groups (separate "Leave Type" cells)."""
        self._create_leave(
            self.annual_type, date(2025, 2, 10), date(2025, 2, 14))
        self._create_leave(
            self.additional_type, date(2025, 8, 1), date(2025, 8, 3))

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        groups = schedule._report_lines_grouped()
        emp_group = [g for g in groups if g['employee'] == self.employee]
        self.assertEqual(len(emp_group), 1)
        grp = emp_group[0]
        self.assertEqual(grp['total'], 2)
        # Two different types -> two type-groups, one line each.
        self.assertEqual(len(grp['type_groups']), 2)
        self.assertEqual(len(grp['type_groups'][0]['lines']), 1)

    def test_report_merges_same_leave_type(self):
        """Two leaves of the SAME type merge into one type-group, so the
        "Leave Type" cell rowspans both rows."""
        self._create_leave(
            self.annual_type, date(2025, 2, 10), date(2025, 2, 14))
        self._create_leave(
            self.annual_type, date(2025, 6, 2), date(2025, 6, 6))

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        grp = [g for g in schedule._report_lines_grouped()
               if g['employee'] == self.employee][0]
        self.assertEqual(grp['total'], 2)
        # Same type -> a single type-group covering both rows.
        self.assertEqual(len(grp['type_groups']), 1)
        self.assertEqual(grp['type_groups'][0]['leave_type'], self.annual_type)
        self.assertEqual(len(grp['type_groups'][0]['lines']), 2)

    # ------------------------------------------------------------------
    # Summary report: both period types for the selected year
    # ------------------------------------------------------------------

    def test_summary_report_mixed_periods(self):
        """The summary report gathers both calendar-year balances (matched by
        year) and work-year balances (matched by overlap) for the report
        year."""
        # A calendar-year balance for the report year.
        cal_bal = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.social_type.id,
            'period_start': date(2025, 1, 1),
            'period_end': date(2025, 12, 31),
            'period_index': 2025,
            'entitled_days': 10,
        })

        report = self.env['hr.employee.vacation.summary.report'].create({
            'year': 2025,
            'company_id': self.employee.company_id.id,
        })
        # generate_balances creates the annual_basic (work-year) balances that
        # overlap 2025; the calendar balance above is picked up as well.
        report.action_generate()

        period_types = set(report.balance_ids.mapped('period_type'))
        self.assertIn('calendar', period_types)
        self.assertIn('work', period_types)
        self.assertIn(cal_bal.id, report.balance_ids.ids)

        work = report.balance_ids.filtered(
            lambda b: b.period_type == 'work'
            and b.employee_id == self.employee)
        self.assertTrue(work)
