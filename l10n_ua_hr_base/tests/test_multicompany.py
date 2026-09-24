"""Multi-company record-rule presence (issue #178)."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBaseMultiCompany(TransactionCase):

    def test_rules_exist_and_are_global(self):
        refs = [
            'l10n_ua_hr_base.hr_employee_military_operational_report_company_rule',
        ]
        for ref in refs:
            rule = self.env.ref(ref)
            self.assertTrue(rule, f"Rule {ref} must exist")
            self.assertTrue(rule['global'], f"Rule {ref} must be global")


@tagged('post_install', '-at_install')
class TestDepartmentHeadCompany(TransactionCase):
    """Department head must belong to the department's company (#350)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Test #350 Base A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Test #350 Base B'})
        cls.head_a = cls.env['hr.employee'].create({
            'name': 'Test #350 head A', 'company_id': cls.company_a.id})
        cls.head_b = cls.env['hr.employee'].create({
            'name': 'Test #350 head B', 'company_id': cls.company_b.id})

    def _department(self, company, **vals):
        return self.env['hr.department'].create(
            dict(name='Test #350 department', company_id=company.id if company else False, **vals))

    def test_create_with_foreign_head_fails(self):
        with self.assertRaises(ValidationError):
            self._department(self.company_a, head_employee_id=self.head_b.id)

    def test_write_foreign_head_fails(self):
        department = self._department(self.company_a)
        with self.assertRaises(ValidationError):
            department.head_employee_id = self.head_b

    def test_own_head_allowed(self):
        department = self._department(self.company_a, head_employee_id=self.head_a.id)
        self.assertEqual(department.head_employee_id, self.head_a)

    def test_department_without_company_accepts_any_head(self):
        department = self._department(False, head_employee_id=self.head_b.id)
        self.assertEqual(department.head_employee_id, self.head_b)

    def test_change_company_with_foreign_head_fails(self):
        department = self._department(self.company_a, head_employee_id=self.head_a.id)
        with self.assertRaises(ValidationError):
            department.company_id = self.company_b
