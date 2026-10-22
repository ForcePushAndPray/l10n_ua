"""Річна декларація ФОП 1–2 груп, F0103407 (#331).

Та сама форма, що й F0103309 (наказ № 578 у ред. № 57), але за рік: розділ II
(перша група) або III (друга) — щоквартальні авансові внески ЄП і обсяг доходу,
військовий збір — 10 % мінімальної зарплати на 1 січня за кожен місяць (рядок 22).
"""

import base64
import os
from datetime import date

from lxml import etree

from odoo.exceptions import UserError
from odoo.modules.module import get_module_path
from odoo.tests import tagged

from .test_declaration_import import DeclarationImportCase


def f0103407(prefix, income_tag, quarterly, income, military, year=2026):
    rows = [f'<{prefix}G{q}>{quarterly:.2f}</{prefix}G{q}>' for q in range(1, 5)]
    rows += [f'<{income_tag}>{income:.2f}</{income_tag}>', f'<R008G3>{income:.2f}</R008G3>']
    rows += [f'<R08G{m}>1</R08G{m}>' for m in range(1, 13)]
    rows.append(f'<R022G3>{military:.2f}</R022G3>')
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n<DECLAR '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="F0103407.xsd">\n<DECLARHEAD>\n'
        '<TIN>1234567890</TIN><C_DOC>F01</C_DOC><C_DOC_SUB>034</C_DOC_SUB>'
        '<C_DOC_VER>7</C_DOC_VER><C_DOC_TYPE>0</C_DOC_TYPE>'
        f'<PERIOD_MONTH>12</PERIOD_MONTH><PERIOD_TYPE>5</PERIOD_TYPE><PERIOD_YEAR>{year}</PERIOD_YEAR>'
        '<D_FILL>15012027</D_FILL>\n</DECLARHEAD>\n<DECLARBODY>\n'
        f'<HZ>1</HZ><HY>1</HY><HZY>{year}</HZY>\n' + '\n'.join(rows)
        + '\n<HFILL>15012027</HFILL>\n</DECLARBODY>\n</DECLAR>'
    )
    return xml.encode('windows-1251')


@tagged('post_install', '-at_install')
class TestAnnualDeclaration(DeclarationImportCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_1 = cls.env.ref('l10n_ua_fop.fop_group_1')
        cls.group_2 = cls.env.ref('l10n_ua_fop.fop_group_2')
        office = cls.env['l10n_ua.tax.office'].search([('code', '=', '1716')], limit=1) or \
            cls.env['l10n_ua.tax.office'].create({'name': 'ДПІ (тест)', 'code': '1716'})
        cls.company.write({'vat': '2940910418', 'l10n_ua_tax_office_id': office.id,
                           'city': 'Київ', 'street': 'вул. Тестова, 1'})
        kved = cls.env['l10n_ua.kved'].search([('code', '=', '62.01')], limit=1)
        if kved and not cls.company.l10n_ua_kved_ids:
            cls.env['l10n_ua.company.kved'].create(
                {'company_id': cls.company.id, 'kved_id': kved.id, 'is_primary': True})

    def _annual(self, group, income=120_000.0, monthly=432.35):
        book = self.env['l10n_ua.fop.income.book'].create({
            'year': 2026, 'quarter': '2', 'fop_group_id': group.id,
            'company_id': self.company.id})
        self.env['l10n_ua.fop.income.book.line'].create({
            'book_id': book.id, 'date': date(2026, 5, 15), 'amount': income,
            'description': 'Дохід'})
        book.action_confirm()
        decl = self.Declaration.create({
            'year': 2026, 'period': 'year', 'fop_group_id': group.id,
            'company_id': self.company.id, 'monthly_tax_amount': monthly})
        decl.action_calculate()
        return decl

    def test_annual_xml_follows_f0103407(self):
        schema_path = os.path.join(get_module_path('l10n_ua_tax_F0103309'),
                                   'tests', 'schemas', 'F0103407.xsd')
        schema = etree.XMLSchema(etree.parse(schema_path))
        for group, prefix, income_tag in ((self.group_1, 'R02', 'R001G3'),
                                          (self.group_2, 'R03', 'R003G3')):
            with self.subTest(group=group.code):
                decl = self._annual(group)
                decl.action_generate_xml()
                root = etree.fromstring(base64.b64decode(decl.xml_file))
                schema.assertValid(root)
                body = root.find('DECLARBODY')
                self.assertEqual(body.findtext(f'{prefix}G1'), '1297.05')    # 432,35 × 3
                self.assertEqual(body.findtext(income_tag), '120000.00')
                self.assertEqual(body.findtext('R022G3'), '10376.40')       # 864,70 × 12
                self.assertTrue(decl._dps_filename().startswith('1716'))
                self.assertIn('F0103407', decl._dps_filename())
                decl.unlink()

    def test_military_levy_uses_january_minimum_wage(self):
        # Мінзарплату змінили з липня — збір 1–2 груп усе одно від розміру на 1 січня.
        self.env['l10n_ua.min.wage'].create({'date_from': date(2026, 7, 1), 'amount': 9500.0})
        decl = self._annual(self.group_1)
        self.assertAlmostEqual(decl.military_levy, 10_376.40, places=2)

    def test_quarterly_period_is_refused(self):
        decl = self.Declaration.create({
            'year': 2026, 'period': 'h1', 'fop_group_id': self.group_2.id,
            'company_id': self.company.id, 'monthly_tax_amount': 1729.40,
            'state': 'calculated'})
        with self.assertRaisesRegex(UserError, 'F0103407'):
            decl.action_generate_xml()

    def test_filed_annual_declaration_is_imported(self):
        doc_type = self.env['l10n_ua.tax.document.type'].search([('code', '=', 'F0103407')])
        self.assertTrue(doc_type)
        doc = self._doc(f0103407('R03', 'R003G3', 5188.20, 900_000.0, 10_376.40))
        doc.document_type_id = doc_type
        doc._l10n_ua_after_import()
        decl = self._declarations().filtered(lambda d: d.period == 'year')
        self.assertEqual(decl.state, 'accepted')
        self.assertEqual(decl.fop_group_id, self.group_2)
        self.assertEqual(decl.total_income, 900_000.0)
        self.assertAlmostEqual(decl.monthly_tax_amount, 1729.40, places=2)
        self.assertAlmostEqual(decl.single_tax, 20_752.80, places=2)
        self.assertEqual(decl.tax_document_id, doc)
