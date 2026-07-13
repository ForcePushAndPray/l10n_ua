"""Tests for the unused-vacation compensation phrase on dismissal orders — issue #125."""

from datetime import date
from unittest import SkipTest
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestVacationCompensation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'hr.vacation.balance' not in cls.env:
            raise SkipTest('l10n_ua_hr_holidays not installed')
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Звільнюваний Працівник',
            'company_id': cls.company.id,
        })
        cls.leave_type = cls.env['hr.leave.type'].search([], limit=1)
        if not cls.leave_type:
            cls.leave_type = cls.env['hr.leave.type'].create({
                'name': 'Щорічна основна',
            })

    def _balance(self, year, entitled):
        return self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.leave_type.id,
            'year': year,
            'entitled_days': entitled,
        })

    def _dismissal(self, dismissal_date, **kwargs):
        vals = {
            'order_type': 'dismissal',
            'date': dismissal_date,
            'date_dismissal': dismissal_date,
            'employee_id': self.employee.id,
            'subject': 'Звільнення',
        }
        vals.update(kwargs)
        return self.env['hr.order'].create(vals)

    def test_unused_days_computed_from_balance(self):
        """unused_vacation_days is pulled from the dismissal-year balance."""
        self._balance(2026, 12)
        order = self._dismissal(date(2026, 5, 20))
        self.assertAlmostEqual(order.unused_vacation_days, 12, places=2)

    def test_days_scoped_to_dismissal_year(self):
        """Only the dismissal year's balance counts, not other years."""
        self._balance(2025, 8)
        self._balance(2026, 3)
        order = self._dismissal(date(2026, 7, 1))
        self.assertAlmostEqual(order.unused_vacation_days, 3, places=2)

    def test_manual_override_persists(self):
        """A hand-entered day count is kept (field is editable)."""
        self._balance(2026, 12)
        order = self._dismissal(date(2026, 5, 20))
        order.unused_vacation_days = 5
        self.assertAlmostEqual(order.unused_vacation_days, 5, places=2)

    def test_phrase_rendered_in_report(self):
        """The standard compensation sentence appears in the printed order."""
        self._balance(2026, 7)
        order = self._dismissal(date(2026, 5, 20))
        html = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_hr_documents.report_hr_order', order.ids)[0]
        text = html.decode() if isinstance(html, bytes) else html
        self.assertIn('виплатити компенсацію', text)
        self.assertIn('невикористаної відпустки', text)

    def test_phrase_suppressed_when_disabled(self):
        """No phrase when the flag is off."""
        self._balance(2026, 7)
        order = self._dismissal(date(2026, 5, 20), include_vacation_compensation=False)
        html = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_hr_documents.report_hr_order', order.ids)[0]
        text = html.decode() if isinstance(html, bytes) else html
        self.assertNotIn('виплатити компенсацію', text)

    def test_non_dismissal_has_no_days(self):
        """A non-dismissal order never computes compensation days."""
        self._balance(2026, 10)
        order = self.env['hr.order'].create({
            'order_type': 'bonus',
            'date': date(2026, 5, 20),
            'employee_id': self.employee.id,
            'subject': 'Премія',
        })
        self.assertEqual(order.unused_vacation_days, 0)
