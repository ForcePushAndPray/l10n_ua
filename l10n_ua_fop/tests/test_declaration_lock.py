"""Подана / прийнята ДПС декларація ЄП не змінюється — лише уточнюючою."""

import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_declaration_import import Q1, f0103309


@tagged('post_install', '-at_install')
class TestDeclarationLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env['l10n_ua.fop.group'].search([('code', '=', '3')], limit=1)
        cls.Declaration = cls.env['l10n_ua.fop.declaration']

    def _declaration(self, state):
        return self.Declaration.create({
            'year': 2026, 'period': 'q1', 'fop_group_id': self.group.id,
            'company_id': self.env.company.id, 'total_income': 1000.0, 'state': state})

    def test_accepted_is_locked(self):
        decl = self._declaration('accepted')
        for vals in ({'total_income': 2000.0}, {'period': 'h1'}, {'state': 'draft'},
                     {'xml_file': base64.b64encode(b'<x/>')}):
            with self.assertRaises(UserError):
                decl.write(vals)
        with self.assertRaises(UserError):
            decl.action_draft()
        with self.assertRaises(UserError):
            decl.unlink()
        with self.assertRaises(UserError):
            decl.action_calculate()
        with self.assertRaises(UserError):
            decl.notes = '<p>Примітка</p>'
        self.assertEqual(decl.total_income, 1000.0)

    def test_submitted_can_go_back_to_draft(self):
        decl = self._declaration('submitted')
        for vals in ({'total_income': 2000.0}, {'notes': '<p>Примітка</p>'}):
            with self.assertRaises(UserError):
                decl.write(vals)
        decl.action_draft()
        self.assertEqual(decl.state, 'draft')
        decl.total_income = 2000.0
        decl.action_accept()  # з чернетки — не «прийнято»
        self.assertEqual(decl.state, 'draft')

    def test_submit_and_accept_flow(self):
        decl = self._declaration('calculated')
        decl._dps_on_submitted('квитанція')
        self.assertEqual(decl.state, 'submitted')
        decl.action_accept()
        self.assertEqual(decl.state, 'accepted')

    def test_reimport_onto_accepted(self):
        decl = self._declaration('accepted')
        f0103309_type = self.env['l10n_ua.tax.document.type'].search([('code', '=', 'F0103309')])
        doc = self.env['l10n_ua.tax.document'].create({
            'name': 'Декларація', 'document_type_id': f0103309_type.id,
            'company_id': self.env.company.id, 'source': 'cabinet',
            'file_xml': base64.b64encode(f0103309(**Q1)), 'file_xml_name': 'q1.xml'})
        doc._l10n_ua_after_import()
        self.assertEqual(decl.tax_document_id, doc)
        self.assertEqual(decl.total_income, 1000.0)  # прийняту не переписуємо
