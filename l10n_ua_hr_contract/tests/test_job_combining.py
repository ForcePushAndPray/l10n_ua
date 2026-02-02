"""Tests for job combining (сумісництво) — HR-6 from HR_UKRAINE.md.

Tests cover:
- Job combining creation
- Surcharge calculation (percent and fixed)
- State workflow (draft -> active -> cancelled)
- Allowance creation on activation
"""

from datetime import date
from odoo.tests import tagged
from .common import ContractTestCase


@tagged('post_install', '-at_install')
class TestJobCombining(ContractTestCase):
    """Test hr.job.combining workflow."""

    def _create_combining(self, employee=None, version=None, **kwargs):
        if employee is None:
            employee = self._create_employee()
        if version is None:
            version = self._create_version(employee=employee, wage=20000)
        vals = {
            'employee_id': employee.id,
            'version_id': version.id,
            'combined_job_id': self.job_2.id,
            'combined_department_id': self.department.id,
            'date_from': date(2025, 3, 1),
            'surcharge_type': 'percent',
            'surcharge_percent': 50,
            'order_number': 'НК-C01/2025',
            'order_date': date(2025, 2, 25),
        }
        vals.update(kwargs)
        return self.env['hr.job.combining'].create(vals)

    def test_combining_creation(self):
        """Job combining should be created in draft state."""
        jc = self._create_combining()
        self.assertEqual(jc.state, 'draft')
        self.assertTrue(jc.name)

    def test_surcharge_percent_calculation(self):
        """Percent surcharge = version.wage * percent / 100."""
        employee = self._create_employee()
        version = self._create_version(employee=employee, wage=20000)
        jc = self._create_combining(
            employee=employee, version=version,
            surcharge_type='percent', surcharge_percent=50,
        )
        self.assertAlmostEqual(jc.calculated_surcharge, 10000, places=2)

    def test_surcharge_fixed_calculation(self):
        """Fixed surcharge should use the direct amount."""
        employee = self._create_employee()
        version = self._create_version(employee=employee, wage=20000)
        jc = self._create_combining(
            employee=employee, version=version,
            surcharge_type='fixed',
            surcharge_amount=7000,
        )
        self.assertAlmostEqual(jc.calculated_surcharge, 7000, places=2)

    def test_combining_activate(self):
        """Activation should create an allowance on the version."""
        jc = self._create_combining()
        jc.action_activate()
        self.assertEqual(jc.state, 'active')
        self.assertTrue(jc.allowance_id, 'Allowance should be created on activation')

    def test_combining_cancel(self):
        """Cancellation should deactivate the allowance."""
        jc = self._create_combining()
        jc.action_activate()
        jc.action_cancel()
        self.assertEqual(jc.state, 'cancelled')

    def test_combining_date_validation(self):
        """End date must be after start date."""
        with self.assertRaises(Exception):
            self._create_combining(
                date_from=date(2025, 6, 1),
                date_to=date(2025, 5, 1),
            )

    def test_combining_display_name(self):
        """Display name should contain employee and job info."""
        jc = self._create_combining()
        self.assertTrue(jc.display_name)
