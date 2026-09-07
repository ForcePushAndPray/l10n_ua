"""Multi-company record-rule isolation (issue #178).

Full isolation test on hr.psp.parameters: a user restricted to a non-UA
company must not see records belonging to another (UA) company, but must
see records of their own company. Also asserts every rule added by this
module exists and is global.
"""

from datetime import date
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalaryMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_ua = cls.env['res.company'].create({'name': 'UA Co'})
        cls.company_other = cls.env['res.company'].create({'name': 'Other Co'})

        # User restricted to the non-UA company with HR access.
        cls.user_other = cls.env['res.users'].create({
            'name': 'Restricted HR User',
            'login': 'restricted_hr_user_178',
            'company_id': cls.company_other.id,
            'company_ids': [(6, 0, [cls.company_other.id])],
            'group_ids': [(4, cls.env.ref('l10n_ua_hr_base.group_hr_ua_user').id)],
        })

        common_vals = {
            'year': 2026,
            'date_from': date(2026, 1, 1),
            'subsistence_minimum': 3028.0,
            'min_wage': 8000.0,
            'min_hourly_wage': 48.0,
        }
        cls.psp_ua = cls.env['hr.psp.parameters'].create(
            dict(common_vals, company_id=cls.company_ua.id))
        cls.psp_other = cls.env['hr.psp.parameters'].create(
            dict(common_vals, date_from=date(2026, 2, 1),
                 company_id=cls.company_other.id))

    def test_restricted_user_cannot_see_other_company_record(self):
        visible = self.env['hr.psp.parameters'].with_user(
            self.user_other).search([])
        self.assertIn(self.psp_other, visible,
                      "User must see their own company's record")
        self.assertNotIn(self.psp_ua, visible,
                         "User must NOT see another company's record")

    def test_rules_exist_and_are_global(self):
        refs = [
            'l10n_ua_hr_salary.hr_execution_document_company_rule',
            'l10n_ua_hr_salary.hr_payslip_company_rule',
            'l10n_ua_hr_salary.hr_payslip_run_company_rule',
            'l10n_ua_hr_salary.hr_salary_advance_company_rule',
            'l10n_ua_hr_salary.hr_salary_advance_run_company_rule',
            'l10n_ua_hr_salary.hr_psp_parameters_company_rule',
            'l10n_ua_hr_salary.hr_salary_deposit_company_rule',
            'l10n_ua_hr_salary.hr_piece_work_entry_company_rule',
            'l10n_ua_hr_salary.hr_cpi_index_company_rule',
            'l10n_ua_hr_salary.hr_seniority_scale_company_rule',
        ]
        for ref in refs:
            rule = self.env.ref(ref)
            self.assertTrue(rule, f"Rule {ref} must exist")
            self.assertTrue(rule['global'], f"Rule {ref} must be global")

    def test_company_field_is_limited_to_enabled_companies(self):
        """Випадайка компанії обмежена увімкненими в перемикачі.

        Без домену адміністратор (`base.group_erp_manager` бачить усі
        компанії за правилом `base.res_company_rule_erp_manager`) міг
        обрати вимкнену компанію і впертися в AccessError уже під час
        збереження — record rule модуля її не пропускає.
        """
        models = [
            'hr.payslip',
            'hr.payslip.run',
            'hr.salary.advance',
            'hr.salary.advance.run',
            'hr.execution.document',
            'hr.psp.parameters',
            'hr.salary.deposit',
            'hr.piece.work.entry',
            'hr.cpi.index',
            'hr.seniority.scale',
        ]
        for model in models:
            domain = self.env[model].fields_get(
                ['company_id'], ['domain'])['company_id']['domain']
            self.assertIn(
                'allowed_company_ids', domain,
                f"{model}: company_id має бути обмежене увімкненими компаніями")
