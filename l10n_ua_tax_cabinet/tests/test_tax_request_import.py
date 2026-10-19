"""Запит F1319104 і відповідь F1419104 з кабінету → «Запити до ДПС».

XML — тієї ж структури, що й реальні документи з кабінету (рядок R0401: у
запиті місяці числами, у відповіді — назвами), з вигаданими реквізитами.
"""

import base64
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def drfo_xml(code, months=('1', '12'), year='2025', filled='15042026'):
    sub, response = code[3:6], code == 'F1419104'
    m_from, m_to = months
    if response:
        names = {'1': 'січень', '12': 'грудень', '6': 'червень'}
        period = (f'<R0401G1S>{names[m_from]}</R0401G1S><R0401G2>{year}</R0401G2>'
                  f'<R0401G3S>{names[m_to]}</R0401G3S><R0401G4>{year}</R0401G4>')
    else:
        period = (f'<R0401G1>{m_from}</R0401G1><R0401G2>{year}</R0401G2>'
                  f'<R0401G3>{m_to}</R0401G3><R0401G4>{year}</R0401G4>')
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        f'<DECLAR xsi:noNamespaceSchemaLocation="{code}.XSD" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><DECLARHEAD>'
        f'<TIN>1234567890</TIN><C_DOC>{code[:3]}</C_DOC><C_DOC_SUB>{sub}</C_DOC_SUB>'
        '<C_DOC_VER>4</C_DOC_VER><C_DOC_TYPE>0</C_DOC_TYPE><PERIOD_MONTH>4</PERIOD_MONTH>'
        f'<PERIOD_TYPE>1</PERIOD_TYPE><PERIOD_YEAR>2026</PERIOD_YEAR><D_FILL>{filled}</D_FILL>'
        f'</DECLARHEAD><DECLARBODY><HTIN>1234567890</HTIN>{period}'
        f'<HFILL>{filled}</HFILL></DECLARBODY></DECLAR>')
    return xml.encode('windows-1251')


@tagged('post_install', '-at_install')
class TestTaxRequestImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Request = cls.env['l10n_ua.tax.request']
        Type = cls.env['l10n_ua.tax.document.type']
        cls.types = {code: Type.search([('code', '=', code)]) for code in ('F1319104', 'F1419104')}

    def _doc(self, code, number, **kw):
        return self.env['l10n_ua.tax.document'].create({
            'name': code, 'document_type_id': self.types[code].id,
            'document_number': number, 'company_id': self.company.id,
            'source': 'cabinet', 'file_xml': base64.b64encode(drfo_xml(code, **kw)),
            'file_xml_name': f'{number}.xml'})

    def _requests(self):
        return self.Request.search([('company_id', '=', self.company.id),
                                    ('request_type', '=', 'f1319104')])

    def test_request_then_response(self):
        request_doc = self._doc('F1319104', '18089703')
        request_doc._l10n_ua_after_import()
        request = self._requests()
        self.assertEqual(request.state, 'submitted')
        self.assertEqual(request.period_from, date(2025, 1, 1))
        self.assertEqual(request.period_to, date(2025, 12, 31))
        self.assertEqual(request.request_date, date(2026, 4, 15))
        self.assertEqual(request.tax_document_id, request_doc)
        self.assertIn('01.2025–12.2025', request.name)

        response_doc = self._doc('F1419104', '18090479')
        response_doc._l10n_ua_after_import()
        self.assertEqual(self._requests(), request)
        self.assertEqual(request.state, 'answered')
        self.assertEqual(request.response_document_id, response_doc)
        self.assertEqual(request.action_open_response()['res_id'], response_doc.id)

        # Повтор нічого не дублює.
        (request_doc | response_doc)._l10n_ua_after_import()
        self.assertEqual(len(self._requests()), 1)

    def test_response_before_request(self):
        """Кабінет може віддати відповідь раніше за запит — вони все одно зійдуться."""
        response_doc = self._doc('F1419104', '18090479')
        response_doc._l10n_ua_after_import()
        request_doc = self._doc('F1319104', '18089703')
        request_doc._l10n_ua_after_import()
        request = self._requests()
        self.assertEqual(len(request), 1)
        self.assertEqual(request.state, 'answered')
        self.assertEqual(request.tax_document_id, request_doc)
        self.assertEqual(request.response_document_id, response_doc)

    def test_different_periods_stay_separate(self):
        self._doc('F1319104', '1', months=('1', '6'))._l10n_ua_after_import()
        self._doc('F1419104', '2', months=('1', '12'))._l10n_ua_after_import()
        requests = self._requests()
        self.assertEqual(len(requests), 2)
        half = requests.filtered(lambda r: r.period_to == date(2025, 6, 30))
        self.assertEqual(half.state, 'submitted')
        self.assertFalse(half.response_document_id)

    def test_imported_type_cannot_be_generated(self):
        self._doc('F1319104', '18089703')._l10n_ua_after_import()
        with self.assertRaises(UserError):
            self._requests().action_generate_xml()
