from datetime import date
from odoo.tests.common import TransactionCase


class TestVacationScheduleReport(TransactionCase):
    """PR 3: vacation schedule and summary report work with both accounting
    period types (calendar year and work year)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Тестовий Працівник Графіка',
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

        line = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        self.assertTrue(line)
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
        self.assertEqual(len(lines), 2)

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
        """An employee with no planned leave still gets a single row carrying
        the entitlement, with no linked leave and empty dates."""
        self.env['hr.vacation.balance'].create({
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

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        self.assertEqual(len(lines), 1)
        self.assertFalse(lines.leave_id)
        self.assertEqual(lines.planned_days, 30)
        self.assertEqual(lines.vacation_period_display, '')

    def test_schedule_shows_past_unused_periods(self):
        """A past accounting period that still has unused days appears as its
        own row (leave-less, showing the past period and the unused count) so
        outstanding vacation is visible in the schedule."""
        # Work year 2024-07-15 .. 2025-07-14: ended before the 2027 schedule
        # year and has 24 unused days.
        past = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.annual_type.id,
            'period_start': date(2024, 7, 15),
            'period_end': date(2025, 7, 14),
            'period_index': 1,
            'entitled_days': 24,
        })
        self.assertEqual(past.remaining_days, 24)

        schedule = self.env['hr.vacation.schedule'].create({
            'year': 2027,
            'company_id': self.employee.company_id.id,
        })
        schedule.action_generate_lines()

        lines = schedule.line_ids.filtered(
            lambda l: l.employee_id == self.employee)
        past_line = lines.filtered(lambda l: l.vacation_balance_id == past)
        self.assertEqual(len(past_line), 1)
        self.assertFalse(past_line.leave_id)
        self.assertEqual(past_line.leave_type_id, self.annual_type)
        self.assertEqual(past_line.planned_days, 24)

    def test_report_lines_grouped_by_employee(self):
        """The PDF report helper groups an employee's leave rows so the name/№/
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
        # Two different types → two type-groups, one line each.
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
        # Same type → a single type-group covering both rows.
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

