"""Tests for HR orders (накази) — HR-1,19,20 from HR_UKRAINE.md.

Tests cover:
- Order creation with auto-sequencing
- Order types (hiring, dismissal, transfer, etc.)
- Subject computation
- State workflow (draft -> confirmed -> cancelled)
- Employee order count
"""

from datetime import date
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHrOrder(TransactionCase):
    """Test hr.order model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.department = cls.env['hr.department'].create({
            'name': 'Відділ кадрів',
            'company_id': cls.company.id,
        })

        cls.job = cls.env['hr.job'].create({
            'name': 'Менеджер',
            'company_id': cls.company.id,
            'department_id': cls.department.id,
        })

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Коваленко Марія Петрівна',
            'company_id': cls.company.id,
            'department_id': cls.department.id,
            'job_id': cls.job.id,
        })

    def _create_order(self, order_type='hiring', **kwargs):
        vals = {
            'order_type': order_type,
            'employee_id': self.employee.id,
            'date': date(2025, 6, 1),
            'subject': 'Test subject',
            'company_id': self.company.id,
        }
        vals.update(kwargs)
        return self.env['hr.order'].create(vals)

    def test_order_creation(self):
        """Order should be created in draft state with auto number."""
        order = self._create_order()
        self.assertEqual(order.state, 'draft')
        self.assertTrue(order.name)

    def test_order_hiring(self):
        """Hiring order should have correct type."""
        order = self._create_order('hiring')
        self.assertEqual(order.order_type, 'hiring')

    def test_order_dismissal(self):
        """Dismissal order should have correct type."""
        order = self._create_order('dismissal')
        self.assertEqual(order.order_type, 'dismissal')

    def test_order_types(self):
        """All 8 order types should be valid."""
        types = ['hiring', 'dismissal', 'transfer', 'vacation',
                 'bonus', 'sick_leave', 'business_trip', 'other']
        for otype in types:
            order = self._create_order(otype)
            self.assertEqual(order.order_type, otype)
            order.unlink()

    def test_order_subject_default(self):
        """Subject should be present on created order."""
        order = self._create_order('hiring')
        self.assertTrue(order.subject)

    def test_order_confirm(self):
        """Confirm should move to confirmed state."""
        order = self._create_order()
        order.action_confirm()
        self.assertEqual(order.state, 'confirmed')

    def test_order_cancel(self):
        """Cancel should move to cancelled state."""
        order = self._create_order()
        order.action_confirm()
        order.action_cancel()
        self.assertEqual(order.state, 'cancelled')

    def test_order_draft_reset(self):
        """Draft should reset from cancelled."""
        order = self._create_order()
        order.action_confirm()
        order.action_cancel()
        order.action_draft()
        self.assertEqual(order.state, 'draft')

    def test_order_auto_sequence(self):
        """Each order should get a unique name/number."""
        order1 = self._create_order('hiring')
        order2 = self._create_order('hiring')
        self.assertNotEqual(order1.name, order2.name)

    def test_employee_orders_count(self):
        """Employee should track order count."""
        self._create_order('hiring')
        self._create_order('transfer')
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.orders_count, 2)

    def test_employee_onchange_fills_department(self):
        """Setting employee should auto-fill department and job."""
        order = self.env['hr.order'].new({
            'order_type': 'hiring',
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order._onchange_employee_id()
        self.assertEqual(order.department_id, self.department)
        self.assertEqual(order.job_id, self.job)
