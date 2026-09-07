"""Multi-company rule presence test (issue #178).

Asserts each multi-company ir.rule exists and is global. Note: the flag is
read as rule['global'] — there is NO rule.global_ attribute.
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMultiCompanyRules(TransactionCase):

    RULE_XMLIDS = [
        'l10n_ua_hr_vacation_reserve.hr_vacation_reserve_company_rule',
    ]

    def test_rules_exist_and_global(self):
        for xmlid in self.RULE_XMLIDS:
            rule = self.env.ref(xmlid)
            self.assertEqual(rule._name, 'ir.rule')
            self.assertTrue(
                rule['global'],
                "Rule %s must be global" % xmlid,
            )

    def test_company_field_is_limited_to_enabled_companies(self):
        """Випадайка компанії обмежена увімкненими в перемикачі компаній."""
        for model in ('hr.vacation.reserve',):
            domain = self.env[model].fields_get(
                ['company_id'], ['domain'])['company_id']['domain']
            self.assertIn(
                'allowed_company_ids', domain,
                f"{model}: company_id має бути обмежене увімкненими компаніями")
