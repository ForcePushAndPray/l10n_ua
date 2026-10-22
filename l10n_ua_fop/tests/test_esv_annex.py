"""ЄСВ — додаток 1 до декларації ЄП: рахується лише з галочкою."""

import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_declaration_import import Q1, f0103309


@tagged('post_install', '-at_install')
class TestEsvAnnex(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env['l10n_ua.fop.group'].search([('code', '=', '3')], limit=1)
        cls.f0103309 = cls.env['l10n_ua.tax.document.type'].search([('code', '=', 'F0103309')])

    def _declaration(self, **vals):
        return self.env['l10n_ua.fop.declaration'].create({
            'year': 2026, 'period': 'h1', 'fop_group_id': self.group.id,
            'company_id': self.env.company.id, 'total_income': 1_434_788.50, **vals})

    def _import(self, xml):
        doc = self.env['l10n_ua.tax.document'].create({
            'name': 'Декларація', 'document_type_id': self.f0103309.id,
            'company_id': self.env.company.id, 'source': 'cabinet',
            'file_xml': base64.b64encode(xml), 'file_xml_name': 'd.xml'})
        doc._l10n_ua_after_import()
        return self.env['l10n_ua.fop.declaration'].search([('tax_document_id', '=', doc.id)])

    def test_without_annex_no_esv(self):
        decl = self._declaration()
        self.assertFalse(decl.esv_annex)
        self.assertEqual(decl.esv_amount, 0.0)
        self.assertAlmostEqual(decl.total_payable, decl.single_tax + decl.military_levy, places=2)

    def test_with_annex_esv_counts(self):
        decl = self._declaration(esv_annex=True)
        self.assertGreater(decl.esv_amount, 0.0)
        self.assertAlmostEqual(
            decl.total_payable, decl.single_tax + decl.esv_amount + decl.military_levy, places=2)
        decl.state = 'calculated'
        with self.assertRaises(UserError):
            decl.action_generate_xml()  # додаток 1 Odoo ще не формує

    def test_imported_without_hd1(self):
        decl = self._import(f0103309(**Q1))
        self.assertFalse(decl.esv_annex)
        self.assertEqual(decl.esv_amount, 0.0)

    def test_imported_with_hd1(self):
        xml = f0103309(**Q1).replace(b'<HZY>', b'<HD1>1</HD1>\n<HZY>')
        decl = self._import(xml)
        self.assertTrue(decl.esv_annex)

    def test_annex_locked_after_filing(self):
        decl = self._declaration(state='accepted')
        with self.assertRaises(UserError):
            decl.esv_annex = True
