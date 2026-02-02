"""Tests for hr.version Ukrainian extensions — HR-1,2,3,4 from HR_UKRAINE.md.

Tests cover:
- Contract type and work mode fields
- Probation period computation
- Work rate validation
- Total wage computation (base + allowances)
- Work conditions and additional vacation days
- Diia.City employee flag
"""

from datetime import date
from odoo.tests import tagged
from .common import ContractTestCase


@tagged('post_install', '-at_install')
class TestHrVersion(ContractTestCase):
    """Test hr.version Ukrainian contract extensions."""

    def test_version_creation_defaults(self):
        """Version should have correct Ukrainian defaults."""
        version = self._create_version()
        self.assertEqual(version.contract_type_ua, 'permanent')
        self.assertEqual(version.work_mode, 'full_time')
        self.assertTrue(version.is_main_workplace)
        self.assertEqual(version.work_rate, 1.0)
        self.assertEqual(version.working_hours_week, 40.0)

    def test_version_contract_types(self):
        """All 8 Ukrainian contract types should be valid."""
        types = ['permanent', 'fixed_term', 'contract', 'civil',
                 'gig', 'author', 'seasonal', 'temporary']
        for ct in types:
            version = self._create_version(contract_type_ua=ct)
            self.assertEqual(version.contract_type_ua, ct)

    def test_probation_end_date_computation(self):
        """Probation end date = start + days."""
        version = self._create_version(
            contract_date_start=date(2025, 3, 1),
            probation_period_days=90,
        )
        self.assertTrue(version.probation_end_date)
        self.assertEqual(version.probation_end_date, date(2025, 5, 30))

    def test_probation_zero_days(self):
        """Zero probation days should result in no end date."""
        version = self._create_version(probation_period_days=0)
        self.assertFalse(version.probation_end_date)

    def test_work_rate_part_time(self):
        """Part-time work rate 0.5 should be valid."""
        version = self._create_version(
            work_rate=0.5,
            is_part_time=True,
            work_mode='part_time',
        )
        self.assertEqual(version.work_rate, 0.5)
        self.assertTrue(version.is_part_time)

    def test_total_wage_no_allowances(self):
        """Total wage with no allowances equals base wage."""
        version = self._create_version(wage=30000)
        self.assertEqual(version.total_wage, 30000)
        self.assertEqual(version.total_allowances, 0)

    def test_total_wage_with_allowances(self):
        """Total wage should include active allowances."""
        version = self._create_version(wage=25000)
        self.env['hr.version.allowance'].create({
            'version_id': version.id,
            'allowance_type_id': self.allowance_seniority.id,
            'calculation_method': 'fixed',
            'amount': 5000,
        })
        version.invalidate_recordset()
        self.assertEqual(version.total_allowances, 5000)
        self.assertEqual(version.total_wage, 30000)

    def test_work_conditions_normal(self):
        """Normal conditions should give 0 additional vacation days."""
        version = self._create_version(work_conditions='normal')
        self.assertEqual(version.additional_vacation_days, 0)

    def test_work_conditions_hazardous(self):
        """Hazardous conditions should give additional vacation days."""
        version = self._create_version(work_conditions='hazardous')
        self.assertGreater(version.additional_vacation_days, 0)
        self.assertLessEqual(version.additional_vacation_days, 35)

    def test_diia_city_employee(self):
        """Diia.City flag should be stored on version."""
        version = self._create_version(
            contract_type_ua='gig',
            diia_city_employee=True,
        )
        self.assertTrue(version.diia_city_employee)

    def test_employee_related_fields(self):
        """Employee should expose version fields as related."""
        employee = self._create_employee()
        version = self._create_version(
            employee=employee,
            contract_type_ua='fixed_term',
            work_mode='remote',
        )
        employee.write({'current_version_id': version.id})
        employee.invalidate_recordset()
        self.assertEqual(employee.contract_type_ua, 'fixed_term')
        self.assertEqual(employee.work_mode, 'remote')

    def test_termination_reason_reference(self):
        """Termination reason should link to version."""
        reason = self.env['hr.termination.reason'].create({
            'name': 'За власним бажанням',
            'article': '38',
            'category': 'own_will',
        })
        version = self._create_version(
            termination_reason_ua_id=reason.id,
        )
        self.assertEqual(version.termination_reason_ua_id.article, '38')
