"""Multi-company record-rule presence (issue #178)."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalaryAccountMultiCompany(TransactionCase):

    def test_rules_exist_and_are_global(self):
        refs = [
            'l10n_ua_hr_salary_account.hr_salary_account_config_company_rule',
        ]
        for ref in refs:
            rule = self.env.ref(ref)
            self.assertTrue(rule, f"Rule {ref} must exist")
            self.assertTrue(rule['global'], f"Rule {ref} must be global")


@tagged('post_install', '-at_install')
class TestDepartmentExpenseAccountCompany(TransactionCase):
    """Department salary expense account must belong to its company (#350)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Test #350 Salary A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Test #350 Salary B'})

        def account(code, company):
            return cls.env['account.account'].with_company(company).create({
                'code': code, 'name': f'Salary expense {code}',
                'account_type': 'expense',
                'company_ids': [(6, 0, company.ids)],
            })
        cls.account_a = account('935001', cls.company_a)
        cls.account_b = account('935002', cls.company_b)
        # A shared account needs its code set for every company.
        cls.account_ab = account('935003', cls.company_a)
        cls.account_ab.with_company(cls.company_b).write({
            'code': '935003', 'company_ids': [(4, cls.company_b.id)]})

    def _department(self, company, **vals):
        return self.env['hr.department'].create(
            dict(name='Test #350 department', company_id=company.id if company else False, **vals))

    def test_create_with_foreign_account_fails(self):
        with self.assertRaises(UserError):
            self._department(self.company_a, salary_expense_account_id=self.account_b.id)

    def test_write_foreign_account_fails(self):
        department = self._department(self.company_a)
        with self.assertRaises(UserError):
            department.salary_expense_account_id = self.account_b

    def test_own_and_shared_accounts_allowed(self):
        department = self._department(self.company_a, salary_expense_account_id=self.account_a.id)
        department.salary_expense_account_id = self.account_ab
        self.assertEqual(department.salary_expense_account_id, self.account_ab)

    def test_department_without_company_accepts_any_account(self):
        department = self._department(False, salary_expense_account_id=self.account_b.id)
        self.assertEqual(department.salary_expense_account_id, self.account_b)

    def test_change_company_with_foreign_account_fails(self):
        department = self._department(self.company_a, salary_expense_account_id=self.account_a.id)
        with self.assertRaises(UserError):
            department.company_id = self.company_b

    def test_change_parent_to_other_company_fails(self):
        parent_b = self._department(self.company_b)
        department = self._department(self.company_a, salary_expense_account_id=self.account_a.id)
        with self.assertRaises(UserError):
            department.parent_id = parent_b
            department.flush_recordset()
