"""Multi-company record rule + обмеження випадайки компанії."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFssMultiCompany(TransactionCase):

    def test_rule_exists_and_is_global(self):
        rule = self.env.ref('l10n_ua_hr_fss.hr_fss_settlement_company_rule')
        self.assertTrue(rule, "Rule hr_fss_settlement_company_rule must exist")
        self.assertTrue(rule['global'], "Rule must be global")

    def test_company_field_is_limited_to_enabled_companies(self):
        """Випадайка компанії обмежена увімкненими в перемикачі компаній."""
        domain = self.env['hr.fss.settlement'].fields_get(
            ['company_id'], ['domain'])['company_id']['domain']
        self.assertIn('allowed_company_ids', domain,
                      "company_id має бути обмежене увімкненими компаніями")
