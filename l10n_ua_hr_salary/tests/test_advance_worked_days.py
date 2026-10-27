"""The advance based on actual days worked.

July 2025 without public holidays and without a production calendar: 23
weekdays, a norm of 184 hours; the 1st to the 15th hold 11 weekdays (88
hours), the 1st to the 16th 12 (96 hours). The batch reads the hours of the
timesheet from the 1st of the month to the payment date and pays them at the
rate the payslip pays an hour at.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAdvanceWorkedDays(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'hr.timesheet.line' not in cls.env or 'hr.sick.leave' not in cls.env:
            return
        # A company of its own: the batch takes every employee of its company,
        # and one left without a timesheet would stop it.
        cls.company = cls.env['res.company'].create({
            'name': 'Advance Worked Days Test Company',
            'currency_id': cls.env.ref('base.UAH').id,
        })
        cls.company.resource_calendar_id.hours_per_day = 8.0
        # A new company gets its parameters seeded; the test pins the
        # minimum hourly wage it compares the grade rate with.
        params = cls.env['hr.psp.parameters'].get_parameters(
            date(2025, 7, 15), cls.company.id)
        if params:
            params.min_hourly_wage = 48.0
        else:
            cls.env['hr.psp.parameters'].create({
                'year': 2025,
                'date_from': date(2025, 1, 1),
                'subsistence_minimum': 3028,
                'min_wage': 8000,
                'min_hourly_wage': 48.0,
                'company_id': cls.company.id,
            })
        cls.department = cls.env['hr.department'].create({
            'name': 'Advance Worked Days Department',
            'company_id': cls.company.id,
        })
        cls.grade = cls.env['hr.tariff.grade'].create({
            'name': 'Advance Worked Days Grade',
            'grade': 99,
            'hourly_rate': 120.0,
            'date_from': date(2025, 1, 1),
            'company_id': cls.company.id,
        })
        cls.salaried = cls._employee('Salaried Advance Employee', wage=23000)
        cls.hourly = cls._employee(
            'Hourly Advance Employee', wage=0, salary_form='hourly',
            tariff_grade_id=cls.grade.id)

    @classmethod
    def _employee(cls, name, **version_vals):
        employee = cls.env['hr.employee'].create({
            'name': name,
            'company_id': cls.company.id,
            'department_id': cls.department.id,
        })
        version = cls.env['hr.version'].create(dict({
            'employee_id': employee.id,
            'contract_date_start': date(2024, 1, 1),
            'date_version': date(2024, 1, 1),
            'contract_type_ua': 'permanent',
            'employment_type_ua': 'primary',
            'department_id': cls.department.id,
            'work_rate': 1.0,
            'resource_calendar_id': cls.company.resource_calendar_id.id,
            'salary_currency_id': cls.company.currency_id.id,
            'company_id': cls.company.id,
        }, **version_vals))
        employee.write({'current_version_id': version.id})
        return employee

    def setUp(self):
        super().setUp()
        if 'hr.timesheet.line' not in self.env or 'hr.sick.leave' not in self.env:
            self.skipTest('the attendance sheet or the holidays module is not installed')
        self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            ('date_from', '<=', '2025-07-31 23:59:59'),
            ('date_to', '>=', '2025-07-01 00:00:00'),
        ]).unlink()

    def _sheet(self, employees=None):
        sheet = self.env['hr.timesheet'].create({
            'month': '7', 'year': 2025,
            'department_id': self.department.id,
            'company_id': self.company.id,
        })
        for employee in employees if employees is not None \
                else self.salaried | self.hourly:
            self.env['hr.timesheet.line'].create({
                'timesheet_id': sheet.id, 'employee_id': employee.id,
            }).action_generate_days()
        return sheet

    def _approve(self, sheet, until):
        self.env['hr.timesheet.partial.approval'].create({
            'timesheet_id': sheet.id, 'date': until,
        }).action_approve()

    def _run(self, payment_date=date(2025, 7, 15)):
        return self.env['hr.salary.advance.run'].create({
            'name': 'Advance Worked Days Run',
            'date': payment_date,
            'calculation_method': 'worked_days',
            'company_id': self.company.id,
        })

    def _advance(self, run, employee):
        return run.advance_ids.filtered(lambda a: a.employee_id == employee)

    def test_salary_paid_for_the_hours_up_to_the_payment_date(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 15))
        run = self._run()
        run.action_generate_advances()
        advance = self._advance(run, self.salaried)
        self.assertAlmostEqual(advance.worked_hours, 88.0)
        self.assertAlmostEqual(advance.norm_hours, 184.0)
        # 23 000 / 184 × 88
        self.assertAlmostEqual(advance.gross_amount, 11000.0, places=2)

    def test_a_vacation_in_the_period_is_not_paid_by_the_advance(self):
        sheet = self._sheet()
        line = sheet.line_ids.filtered(lambda l: l.employee_id == self.salaried)
        vacation = self.env['hr.timesheet.code'].search([('code', '=', 'ВД')], limit=1)
        line.day_ids.filtered(
            lambda d: date(2025, 7, 7) <= d.date <= date(2025, 7, 11)
        ).write({'code_id': vacation.id, 'hours': 0.0})
        self._approve(sheet, date(2025, 7, 15))
        run = self._run()
        run.action_generate_advances()
        # 23 000 / 184 × 48
        self.assertAlmostEqual(
            self._advance(run, self.salaried).gross_amount, 6000.0, places=2)

    def test_the_period_follows_the_payment_date(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 16))
        run = self._run(date(2025, 7, 16))
        self.assertTrue(run.date_warning)
        run.action_generate_advances()
        # 23 000 / 184 × 96
        self.assertAlmostEqual(
            self._advance(run, self.salaried).gross_amount, 12000.0, places=2)

    def test_hourly_form_paid_at_the_grade_rate(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 15))
        run = self._run()
        run.action_generate_advances()
        advance = self._advance(run, self.hourly)
        self.assertAlmostEqual(advance.hourly_rate, 120.0)
        self.assertAlmostEqual(advance.gross_amount, 10560.0, places=2)

    def test_a_confirmed_sheet_passes_whatever_its_partial_date(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 10))
        sheet.action_confirm()
        self.assertEqual(sheet.partial_approval_date, date(2025, 7, 10))
        run = self._run()
        run.action_generate_advances()
        self.assertEqual(len(run.advance_ids), 2)

    def test_a_sheet_approved_before_the_payment_date_stops_the_batch(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 15))
        run = self._run(date(2025, 7, 16))
        with self.assertRaises(UserError) as error:
            run.action_generate_advances()
        self.assertIn(sheet.display_name, str(error.exception))
        self.assertFalse(run.advance_ids)
        # Approved again up to the payment date, the batch goes through.
        sheet.action_draft()
        self._approve(sheet, date(2025, 7, 16))
        run.action_generate_advances()
        self.assertEqual(len(run.advance_ids), 2)

    def test_an_employee_without_a_sheet_stops_the_batch(self):
        sheet = self._sheet(self.salaried)
        self._approve(sheet, date(2025, 7, 15))
        run = self._run()
        with self.assertRaises(UserError) as error:
            run.action_generate_advances()
        self.assertIn(self.hourly.name, str(error.exception))
        self.assertIn(self.department.name, str(error.exception))
        self.assertFalse(run.advance_ids)

    def test_a_draft_sheet_without_partial_approval_stops_the_batch(self):
        self._sheet()
        run = self._run()
        with self.assertRaises(UserError) as error:
            run.action_generate_advances()
        self.assertIn(self.salaried.name, str(error.exception))
        self.assertIn(self.hourly.name, str(error.exception))
        self.assertFalse(run.advance_ids)

    def test_one_error_lists_every_problem(self):
        sheet = self._sheet(self.salaried)
        self._approve(sheet, date(2025, 7, 10))
        run = self._run()
        with self.assertRaises(UserError) as error:
            run.action_generate_advances()
        self.assertIn(sheet.display_name, str(error.exception))
        self.assertIn(self.hourly.name, str(error.exception))
        # The employee of the early sheet is named by the sheet, not twice.
        self.assertNotIn(self.salaried.name, str(error.exception))

    def test_a_partially_approved_sheet_leaves_the_payslip_alone(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 15))
        slip = self.env['hr.payslip'].create({
            'employee_id': self.salaried.id,
            'date_from': date(2025, 7, 1), 'date_to': date(2025, 7, 31),
            'company_id': self.company.id,
        })
        self.assertFalse(slip._timesheet_line())
        self.assertEqual(slip._l10n_ua_month_norm(), (23, 184.0))

    def test_switching_the_method_recomputes_the_drafts(self):
        sheet = self._sheet()
        self._approve(sheet, date(2025, 7, 15))
        run = self._run()
        run.calculation_method = 'percent'
        run.action_generate_advances()
        self.assertAlmostEqual(
            self._advance(run, self.salaried).gross_amount, 11500.0, places=2)
        run.calculation_method = 'worked_days'
        advance = self._advance(run, self.salaried)
        self.assertEqual(advance.calculation_method, 'worked_days')
        self.assertAlmostEqual(advance.gross_amount, 11000.0, places=2)

    def test_a_payment_date_on_a_day_off_warns(self):
        run = self._run(date(2025, 7, 13))
        self.assertTrue(run.date_warning)
        self.assertFalse(self._run(date(2025, 7, 15)).date_warning)
