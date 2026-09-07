"""Multi-company record-rule presence (issue #178)."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBonusMultiCompanyRules(TransactionCase):

    def test_rules_exist_and_are_global(self):
        refs = [
            'l10n_ua_hr_salary_bonus.hr_bonus_company_rule',
            'l10n_ua_hr_salary_bonus.hr_bonus_type_company_rule',
        ]
        for ref in refs:
            rule = self.env.ref(ref)
            self.assertTrue(rule, f"Rule {ref} must exist")
            self.assertTrue(rule['global'], f"Rule {ref} must be global")

    def test_company_field_is_limited_to_enabled_companies(self):
        """Випадайка компанії обмежена увімкненими в перемикачі компаній."""
        for model in ('hr.bonus', 'hr.bonus.type'):
            domain = self.env[model].fields_get(
                ['company_id'], ['domain'])['company_id']['domain']
            self.assertIn(
                'allowed_company_ids', domain,
                f"{model}: company_id має бути обмежене увімкненими компаніями")
