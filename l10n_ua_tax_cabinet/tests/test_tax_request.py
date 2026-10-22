"""Тести інформаційного запиту до ДПС (l10n_ua.tax.request, J1300208).

Покриття:
- XSD-валідність згенерованого XML проти офіційного XSD ДПС;
- генерація XML + збереження у xml_file/xml_filename;
- відсутність обов'язкових реквізитів → UserError (жодного фейку);
- wiring підпису: action_submit відкриває універсальний діалог,
  _dps_on_submitted фіксує стан і квитанцію.
"""

import base64
import importlib.util
import os
from datetime import date

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schemas', 'J1300208.xsd')


@tagged('post_install', '-at_install')
class TestTaxRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        office = cls.env['l10n_ua.tax.office'].search([('code', '=', '1716')], limit=1) \
            or cls.env['l10n_ua.tax.office'].create(
                {'name': 'ГУ ДПС у Харківській області', 'code': '1716'})
        cls.office = office
        cls.company.write({'edrpou': '12345678', 'tax_office_code': '1716',
                           'l10n_ua_tax_office_id': office.id})
        # Конфігурація кабінету потрібна для подання, і тест має заводити її
        # сам: доти вона бралася з бази, тобто ці два тести проходили лише
        # там, де конфіг лишив по собі хтось інший (тести l10n_ua_account_vat).
        # UNIQUE(company_id) — переуживаємо наявний рядок, якщо він є.
        config = cls.env['l10n_ua.tax.cabinet.config'].with_context(
            active_test=False).search([('company_id', '=', cls.company.id)], limit=1)
        vals = {'name': 'Кабінет (тест запиту)', 'taxpayer_code': '12345678',
                'active': True}
        if config:
            config.write(vals)
        else:
            cls.env['l10n_ua.tax.cabinet.config'].create(
                {**vals, 'company_id': cls.company.id})

    def _request(self, **kw):
        vals = {
            'request_type': 'j1300208',
            'request_date': date(2025, 6, 10),
            'company_id': self.company.id,
        }
        vals.update(kw)
        return self.env['l10n_ua.tax.request'].create(vals)

    def test_generate_xml_validates_against_xsd(self):
        req = self._request()
        req.action_generate_xml()
        self.assertEqual(req.state, 'generated')
        self.assertTrue(req.xml_file)
        self.assertTrue(req.xml_filename.startswith('J13002'))
        xml = base64.b64decode(req.xml_file)
        schema = etree.XMLSchema(etree.parse(SCHEMA_PATH))
        doc = etree.fromstring(xml)  # байти вже windows-1251 з декларацією
        self.assertTrue(schema.validate(doc),
                        'XSD-невалідний XML: %s' % schema.error_log)

    def _body(self, req):
        req.action_generate_xml()
        xml = base64.b64decode(req.xml_file)
        schema = etree.XMLSchema(etree.parse(SCHEMA_PATH))
        doc = etree.fromstring(xml)
        self.assertTrue(schema.validate(doc), 'XSD-невалідний XML: %s' % schema.error_log)
        return doc.find('DECLARBODY')

    def test_period_defaults_to_the_year_up_to_the_request_date(self):
        body = self._body(self._request())
        self.assertEqual(body.findtext('HSTI'), self.office.name)
        self.assertEqual(body.findtext('HMONTH1'), '1')
        self.assertEqual(body.findtext('HYEAR1'), '2025')
        self.assertEqual(body.findtext('HDATE1'), '10062025')
        self.assertIsNone(body.find('M01'))

    def test_period_and_extract_option(self):
        body = self._body(self._request(
            period_from=date(2025, 3, 1), period_to=date(2025, 5, 31),
            extract_option='m02'))
        self.assertEqual(body.findtext('HMONTH1'), '3')
        self.assertEqual(body.findtext('HDATE1'), '31052025')
        self.assertEqual(body.findtext('M02'), '1')
        self.assertEqual(len([el for el in body if el.tag.startswith('M0')]), 1)

    def test_period_across_years_is_refused(self):
        req = self._request(period_from=date(2024, 12, 1), period_to=date(2025, 1, 31))
        with self.assertRaises(UserError):
            req.action_generate_xml()

    def test_missing_tax_office_raises(self):
        self.company.write({'l10n_ua_tax_office_id': False, 'tax_office_code': '9999'})
        with self.assertRaises(UserError):
            self._request().action_generate_xml()

    def test_migration_moves_unsent_requests_to_the_new_form(self):
        old_draft = self._request(request_type='j1300205')
        old_sent = self._request(request_type='j1300205')
        old_sent.write({'state': 'submitted'})
        self.env.flush_all()
        path = os.path.join(os.path.dirname(__file__), os.pardir, 'migrations',
                            '19.0.2.3.7', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mig_19_0_2_3_7', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.2.3.6')
        self.env.invalidate_all()
        self.assertEqual(old_draft.request_type, 'j1300208')
        self.assertEqual(old_sent.request_type, 'j1300205')

    def test_missing_company_data_raises(self):
        # Прибрати всі джерела ЄДРПОУ (edrpou + company_registry + vat).
        self.company.write({
            'edrpou': False, 'company_registry': False, 'vat': False})
        req = self._request()
        with self.assertRaises(UserError):
            req.action_generate_xml()

    def test_action_submit_opens_sign_dialog(self):
        req = self._request()
        action = req.action_submit()
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'l10n_ua_sign.kep_sign')
        self.assertEqual(action['params'], {
            'model': 'l10n_ua.tax.request', 'res_id': req.id})
        # XML сформовано під час підготовки, статус ще не «подано».
        self.assertTrue(req.xml_file)
        self.assertNotEqual(req.state, 'submitted')

    def test_prepare_signing_payload(self):
        req = self._request()
        data = req.kep_prepare_signing()
        self.assertEqual(len(data['documents']), 1)
        doc = data['documents'][0]
        self.assertEqual(doc['name'], 'doc')
        self.assertEqual(doc['format'], 'dps_transport')
        self.assertTrue(doc['data_b64'])

    def test_on_submitted_sets_state(self):
        req = self._request()
        req.action_generate_xml()
        req._dps_on_submitted('Квитанція: прийнято')
        self.assertEqual(req.state, 'submitted')
        self.assertTrue(req.submission_date)
        self.assertIn('прийнято', req.response_receipt)


@tagged('post_install', '-at_install')
class TestReceiptText(TransactionCase):

    def test_receipt_from_array_and_object(self):
        Request = self.env['l10n_ua.tax.request']
        self.assertEqual(Request._dps_receipt_text([{'message': 'Документ прийнято'}]), 'Документ прийнято')
        self.assertEqual(Request._dps_receipt_text({'message': 'ok'}), 'ok')
        self.assertIn('"id": 5', Request._dps_receipt_text([{'id': 5}]))
        self.assertEqual(Request._dps_receipt_text([]), 'Подано')
