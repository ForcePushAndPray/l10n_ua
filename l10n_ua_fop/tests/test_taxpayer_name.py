"""У декларації ЄП ФОП — лише ПІБ (HNAME, HBOS), як у прийнятих ДПС деклараціях."""

import base64

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTaxpayerName(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.fop_form = cls.env['l10n_ua.legal.form'].search([('is_fop', '=', True)], limit=1)
        cls.other_form = cls.env['l10n_ua.legal.form'].search([('is_fop', '=', False)], limit=1)

    def test_dps_name(self):
        self.company.write({'name': 'ФОП Тестовий Тест Тестович',
                            'l10n_ua_legal_form_id': self.fop_form.id})
        self.assertEqual(self.company._l10n_ua_dps_name(), 'Тестовий Тест Тестович')
        self.company.name = 'ТЕСТОВИЙ Т. Т. ФОП'
        self.assertEqual(self.company._l10n_ua_dps_name(), 'ТЕСТОВИЙ Т. Т.')
        self.company.write({'name': 'ТОВ "ФОП Сервіс"', 'l10n_ua_legal_form_id': self.other_form.id})
        self.assertEqual(self.company._l10n_ua_dps_name(), 'ТОВ "ФОП Сервіс"')

    def test_declaration_xml_uses_name_without_fop(self):
        self.company.write({'name': 'ФОП Тестовий Тест Тестович',
                            'l10n_ua_legal_form_id': self.fop_form.id})
        group = self.env['l10n_ua.fop.group'].search([('code', '=', '3')], limit=1)
        decl = self.env['l10n_ua.fop.declaration'].create({
            'year': 2026, 'period': 'q1', 'fop_group_id': group.id,
            'company_id': self.company.id, 'total_income': 1000.0, 'state': 'calculated'})
        decl.action_generate_xml()
        xml = base64.b64decode(decl.xml_file).decode('windows-1251')
        self.assertIn('<HNAME>Тестовий Тест Тестович</HNAME>', xml)
        self.assertIn('<HBOS>Тестовий Тест Тестович</HBOS>', xml)
