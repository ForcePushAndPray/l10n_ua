"""Multi-company record-rule presence (issue #178)."""

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

    def test_company_field_is_limited_to_enabled_companies(self):
        """The company dropdown is limited to the enabled companies."""
        for model in ('hr.salary.account.config',):
            domain = self.env[model].fields_get(
                ['company_id'], ['domain'])['company_id']['domain']
            self.assertIn(
                'allowed_company_ids', domain,
                f"{model}: company_id must be limited to enabled companies")
