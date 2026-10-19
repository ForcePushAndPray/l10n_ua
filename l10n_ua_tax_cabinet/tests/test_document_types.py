"""Тип документа з кабінету — за кодом форми, а якщо код невідомий — з XML."""

import base64
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.l10n_ua_tax_document import doc_code_from_xml

DRFO_RESPONSE_XML = (
    '<?xml version="1.0" encoding="windows-1251"?>\n'
    '        <DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="F1419104.XSD">\n<DECLARHEAD><TIN>1234567890</TIN>'
    '<C_DOC>F14</C_DOC><C_DOC_SUB>191</C_DOC_SUB><C_DOC_VER>4</C_DOC_VER></DECLARHEAD>'
    '</DECLAR>').encode('cp1251')

HEAD_ONLY_XML = (
    '<?xml version="1.0" encoding="windows-1251"?><DECLAR><DECLARHEAD>'
    '<C_DOC>F01</C_DOC><C_DOC_SUB>033</C_DOC_SUB><C_DOC_VER>9</C_DOC_VER>'
    '</DECLARHEAD></DECLAR>').encode('cp1251')


@tagged('post_install', '-at_install')
class TestDocumentTypes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        config = cls.env['l10n_ua.tax.cabinet.config'].with_context(
            active_test=False).search([('company_id', '=', company.id)], limit=1)
        vals = {'name': 'Кабінет (тест типів)', 'taxpayer_code': '1234567890',
                'active': True, 'auto_download_xml': True, 'auto_download_pdf': False}
        if config:
            config.write(vals)
        else:
            config = cls.env['l10n_ua.tax.cabinet.config'].create(
                {**vals, 'company_id': company.id})
        cls.config = config
        cls.Type = cls.env['l10n_ua.tax.document.type']

    def test_drfo_types_exist(self):
        self.assertEqual(self.Type.search([('code', '=', 'F1319104')]).category, 'request')
        self.assertEqual(self.Type.search([('code', '=', 'F1419104')]).category, 'response')

    def test_code_from_xml(self):
        self.assertEqual(doc_code_from_xml(DRFO_RESPONSE_XML), 'F1419104')
        self.assertEqual(doc_code_from_xml(HEAD_ONLY_XML), 'F0103309')
        self.assertIsNone(doc_code_from_xml(b'<html/>'))
        self.assertIsNone(doc_code_from_xml(None))

    def test_unknown_list_code_is_resolved_from_xml(self):
        item = {'codRegdoc': '171627579144092', 'doc': 'J9999999',
                'docName': 'Відомості з ДРФО', 'periodYear': 2026, 'periodMonth': 4}
        with patch.object(type(self.config), '_api_download_document_xml', autospec=True,
                          return_value=base64.b64encode(DRFO_RESPONSE_XML)):
            count = self.env['l10n_ua.tax.document']._process_api_documents(
                self.config, [item], 'reg_doc', 2026, auth_signature='SIG')
        self.assertEqual(count, 1)
        doc = self.env['l10n_ua.tax.document'].search([('external_id', '=', '171627579144092')])
        self.assertEqual(doc.document_type_id.code, 'F1419104')

    def test_retype_leaves_known_types_alone(self):
        declaration = self.Type.search([('code', '=', 'F0103309')])
        doc = self.env['l10n_ua.tax.document'].create({
            'name': 'Декларація', 'document_type_id': declaration.id,
            'company_id': self.env.company.id,
            'file_xml': base64.b64encode(DRFO_RESPONSE_XML)})
        doc._retype_from_xml()
        self.assertEqual(doc.document_type_id, declaration)
