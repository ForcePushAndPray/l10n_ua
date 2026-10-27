"""A timesheet approved up to a date: the days up to it are locked, the sheet
stays in draft, and setting it back to draft unlocks them."""
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartialApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.resource_calendar_id.hours_per_day = 8.0
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Partial Approval Employee',
            'company_id': cls.company.id,
        })
        cls.employee.version_ids[:1].write({
            'date_version': date(2024, 1, 1),
            'contract_date_start': date(2024, 1, 1),
            'work_rate': 1.0,
        })
        cls.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            ('date_from', '<=', '2025-07-31 23:59:59'),
            ('date_to', '>=', '2025-07-01 00:00:00'),
        ]).unlink()
        cls.env['hr.production.calendar'].search([
            ('year', '=', 2025), ('company_id', '=', cls.company.id),
        ]).unlink()

    def setUp(self):
        super().setUp()
        self.sheet = self.env['hr.timesheet'].create({
            'month': '7', 'year': 2025, 'company_id': self.company.id})
        self.line = self.env['hr.timesheet.line'].create({
            'timesheet_id': self.sheet.id, 'employee_id': self.employee.id})
        self.line.action_generate_days()

    def _wizard(self, **vals):
        return self.env['hr.timesheet.partial.approval'].with_context(
            default_timesheet_id=self.sheet.id).create(vals)

    def _day(self, day):
        return self.line.day_ids.filtered(lambda d: d.date == date(2025, 7, day))

    def test_the_wizard_proposes_the_15th(self):
        self.assertEqual(self._wizard().date, date(2025, 7, 15))

    def test_a_date_outside_the_month_is_refused(self):
        with self.assertRaises(ValidationError):
            self._wizard(date=date(2025, 8, 1)).action_approve()
        self.assertFalse(self.sheet.partial_approval_date)

    def test_the_approved_days_are_locked_and_the_rest_is_not(self):
        self._wizard().action_approve()
        self.assertEqual(self.sheet.state, 'draft')
        self.assertEqual(self.sheet.partial_approval_date, date(2025, 7, 15))
        self.assertEqual(self.sheet.partial_approval_user_id, self.env.user)
        with self.assertRaises(UserError):
            self._day(15).hours = 4.0
        with self.assertRaises(UserError):
            self._day(1).unlink()
        with self.assertRaises(UserError):
            self._day(16).date = date(2025, 7, 14)
        with self.assertRaises(UserError):
            self.env['hr.timesheet.day'].create({
                'line_id': self.line.id, 'date': date(2025, 7, 2),
                'day_number': 2, 'code_id': self._day(2).code_id.id,
            })
        self._day(16).hours = 4.0
        self.assertEqual(self._day(16).hours, 4.0)

    def test_rebuilding_the_sheet_is_refused(self):
        self._wizard().action_approve()
        with self.assertRaises(UserError):
            self.sheet.action_generate_lines()
        with self.assertRaises(UserError):
            self.line.action_generate_days()
        with self.assertRaises(UserError):
            self.line.unlink()
        with self.assertRaises(UserError):
            self.sheet.month = '8'
        with self.assertRaises(UserError):
            self.sheet.unlink()

    def test_moving_a_line_is_refused(self):
        other = self.env['hr.employee'].create({
            'name': 'Other Employee', 'company_id': self.company.id})
        other_sheet = self.env['hr.timesheet'].create({
            'month': '8', 'year': 2025, 'company_id': self.company.id})
        self._wizard().action_approve()
        with self.assertRaises(UserError):
            self.line.employee_id = other
        with self.assertRaises(UserError):
            self.line.timesheet_id = other_sheet

    def test_a_second_partial_approval_is_refused(self):
        self._wizard().action_approve()
        with self.assertRaises(UserError):
            self.sheet.action_partial_approve()

    def test_set_to_draft_clears_the_approval(self):
        self._wizard().action_approve()
        self.sheet.action_draft()
        self.assertFalse(self.sheet.partial_approval_date)
        self.assertFalse(self.sheet.partial_approval_user_id)
        self._day(1).hours = 4.0
        self.assertEqual(self._day(1).hours, 4.0)
        self.assertTrue(self.sheet.action_partial_approve())

    def test_a_full_approval_keeps_the_date(self):
        self._wizard().action_approve()
        self.sheet.action_confirm()
        self.sheet.action_approve()
        self.assertEqual(self.sheet.state, 'approved')
        self.assertEqual(self.sheet.partial_approval_date, date(2025, 7, 15))
