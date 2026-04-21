# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.exceptions import ValidationError
from datetime import date
from dateutil.relativedelta import relativedelta

from .common import TestHrUaBase


@tagged('post_install', '-at_install')
class TestHrStaffingTable(TestHrUaBase):
    """Test hr.staffing.table model."""

    def _create_staffing_record(self, **kwargs):
        """Helper to create staffing table record."""
        vals = {
            'company_id': self.company.id,
            'department_id': self.department.id,
            'job_id': self.job.id,
            'units': 1.0,
            'salary': 15000.0,
            'date_from': date.today(),
        }
        vals.update(kwargs)
        return self.env['hr.staffing.table'].create(vals)

    def test_staffing_table_creation(self):
        """Test basic staffing table record creation."""
        record = self._create_staffing_record()

        self.assertEqual(record.units, 1.0)
        self.assertEqual(record.salary, 15000.0)
        self.assertEqual(record.state, 'draft')

    def test_staffing_table_name_computation(self):
        """Test name computed field."""
        record = self._create_staffing_record()

        expected_name = f"{self.department.name} / {self.job.name}"
        self.assertEqual(record.name, expected_name)

    def test_total_salary_fund_computation(self):
        """Test total_salary_fund computed field."""
        record = self._create_staffing_record(
            units=2.5,
            salary=10000.0,
        )

        self.assertEqual(record.total_salary_fund, 25000.0)

    def test_units_validation_zero(self):
        """Test that zero units is rejected."""
        with self.assertRaises(ValidationError):
            self._create_staffing_record(units=0)

    def test_units_validation_negative(self):
        """Test that negative units is rejected."""
        with self.assertRaises(ValidationError):
            self._create_staffing_record(units=-1)

    def test_units_fractional(self):
        """Test fractional units (part-time positions)."""
        record = self._create_staffing_record(units=0.5)
        self.assertEqual(record.units, 0.5)
        self.assertEqual(record.total_salary_fund, 7500.0)

    def test_date_validation(self):
        """Test date range validation."""
        with self.assertRaises(ValidationError):
            self._create_staffing_record(
                date_from=date(2024, 12, 31),
                date_to=date(2024, 1, 1),  # Before date_from
            )

    def test_date_validation_same_date(self):
        """Test that same date_from and date_to is allowed."""
        record = self._create_staffing_record(
            date_from=date(2024, 6, 15),
            date_to=date(2024, 6, 15),
        )
        self.assertEqual(record.date_from, record.date_to)

    def test_salary_range_validation(self):
        """Test salary range validation."""
        # Min > Max should fail
        with self.assertRaises(ValidationError):
            self._create_staffing_record(
                salary=15000,
                salary_min=20000,
                salary_max=10000,
            )

    def test_salary_below_minimum(self):
        """Test that salary below minimum is rejected."""
        with self.assertRaises(ValidationError):
            self._create_staffing_record(
                salary=8000,
                salary_min=10000,
                salary_max=20000,
            )

    def test_salary_above_maximum(self):
        """Test that salary above maximum is rejected."""
        with self.assertRaises(ValidationError):
            self._create_staffing_record(
                salary=25000,
                salary_min=10000,
                salary_max=20000,
            )

    def test_salary_within_range(self):
        """Test valid salary within range."""
        record = self._create_staffing_record(
            salary=15000,
            salary_min=10000,
            salary_max=20000,
        )
        self.assertEqual(record.salary, 15000)

    def test_filled_units_computation(self):
        """Test filled_units computed field."""
        record = self._create_staffing_record(units=3.0)

        # Draft state - no filled units
        self.assertEqual(record.filled_units, 0.0)

        # Approve the record
        record.action_approve()

        # No employees yet - force recompute
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 0.0)

        # Create employees in the same department and job
        self._create_employee()
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 1.0)

        self._create_employee(name='Employee 2')
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 2.0)

    def test_vacant_units_computation(self):
        """Test vacant_units computed field."""
        record = self._create_staffing_record(units=3.0)
        record.action_approve()

        # No employees - all vacant
        record._compute_filled_units()
        record._compute_vacant_units()
        self.assertEqual(record.vacant_units, 3.0)

        # Add one employee
        self._create_employee()
        record._compute_filled_units()
        record._compute_vacant_units()
        self.assertEqual(record.vacant_units, 2.0)

    def test_vacant_units_never_negative(self):
        """Test that vacant_units is never negative (overstaffed)."""
        record = self._create_staffing_record(units=1.0)
        record.action_approve()

        # Create more employees than positions
        self._create_employee(name='Employee 1')
        self._create_employee(name='Employee 2')
        self._create_employee(name='Employee 3')
        record._compute_filled_units()
        record._compute_vacant_units()

        # Vacant should be 0, not negative
        self.assertEqual(record.vacant_units, 0.0)
        self.assertEqual(record.filled_units, 3.0)

    def test_state_transitions(self):
        """Test state transitions."""
        record = self._create_staffing_record()

        # Initial state
        self.assertEqual(record.state, 'draft')

        # Draft -> Approved
        record.action_approve()
        self.assertEqual(record.state, 'approved')

        # Approved -> Archived
        record.action_archive()
        self.assertEqual(record.state, 'archived')

        # Archived -> Draft
        record.action_draft()
        self.assertEqual(record.state, 'draft')

    def test_order_fields(self):
        """Test order number and date fields."""
        record = self._create_staffing_record(
            order_number='ШР-001/2024',
            order_date=date(2024, 1, 15),
        )

        self.assertEqual(record.order_number, 'ШР-001/2024')
        self.assertEqual(record.order_date, date(2024, 1, 15))


@tagged('post_install', '-at_install')
class TestHrStaffingTableIntegration(TestHrUaBase):
    """Integration tests for staffing table with employees."""

    def test_employee_department_change(self):
        """Test that filled_units updates when employee changes department."""
        # Create second department
        dept2 = self.env['hr.department'].create({
            'name': 'Department 2',
            'company_id': self.company.id,
        })

        record = self.env['hr.staffing.table'].create({
            'company_id': self.company.id,
            'department_id': self.department.id,
            'job_id': self.job.id,
            'units': 2.0,
            'salary': 15000.0,
            'date_from': date.today(),
            'state': 'approved',
        })

        employee = self._create_employee()
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 1.0)

        # Move employee to another department
        employee.department_id = dept2
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 0.0)

    def test_employee_job_change(self):
        """Test that filled_units updates when employee changes job."""
        # Create second job
        job2 = self.env['hr.job'].create({
            'name': 'Job 2',
            'company_id': self.company.id,
            'department_id': self.department.id,
        })

        record = self.env['hr.staffing.table'].create({
            'company_id': self.company.id,
            'department_id': self.department.id,
            'job_id': self.job.id,
            'units': 2.0,
            'salary': 15000.0,
            'date_from': date.today(),
            'state': 'approved',
        })

        employee = self._create_employee()
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 1.0)

        # Change employee job
        employee.job_id = job2
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 0.0)

    def test_employee_archived(self):
        """Test that archived employees don't count in filled_units."""
        record = self.env['hr.staffing.table'].create({
            'company_id': self.company.id,
            'department_id': self.department.id,
            'job_id': self.job.id,
            'units': 2.0,
            'salary': 15000.0,
            'date_from': date.today(),
            'state': 'approved',
        })

        employee = self._create_employee()
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 1.0)

        # Archive employee
        employee.active = False
        record._compute_filled_units()
        self.assertEqual(record.filled_units, 0.0)


@tagged('post_install', '-at_install')
class TestStaffingTableMultiCompany(TestHrUaBase):
    """Multi-company isolation для hr.staffing.table."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({
            'name': 'Company B',
        })
        cls.dept_b = cls.env['hr.department'].create({
            'name': 'Dept B',
            'company_id': cls.company_b.id,
        })
        cls.job_b = cls.env['hr.job'].create({
            'name': 'Job B',
            'company_id': cls.company_b.id,
            'department_id': cls.dept_b.id,
        })

    def test_onchange_company_resets_cross_company_dept(self):
        """Зміна company_id скидає department_id якщо він з іншої компанії."""
        record = self.env['hr.staffing.table'].new({
            'company_id': self.company.id,
            'department_id': self.department.id,
            'job_id': self.job.id,
        })
        record.company_id = self.company_b
        record._onchange_company_id()
        self.assertFalse(record.department_id,
            'Department from other company must be cleared')
        self.assertFalse(record.job_id,
            'Job from other company must be cleared')

    def test_onchange_company_keeps_shared_records(self):
        """Shared records (company_id=False) не скидаються."""
        shared_dept = self.env['hr.department'].create({
            'name': 'Shared Dept',
            'company_id': False,
        })
        record = self.env['hr.staffing.table'].new({
            'company_id': self.company.id,
            'department_id': shared_dept.id,
        })
        record.company_id = self.company_b
        record._onchange_company_id()
        self.assertEqual(record.department_id, shared_dept,
            'Shared department must remain after company switch')
