"""Валідація згенерованого XML F0103309 проти офіційного XSD ДПС.

XSD `tests/schemas/F0103309.xsd` — контрольна схема з пакета СКЗ ДПС
(«Спеціалізоване клієнтське програмне забезпечення…», повна версія
1.34.0.0, tax.gov.ua/data/files/627351.zip). Публічна держсхема,
вендориться як тест-фікстура. Оновлювати при зміні версії форми
(див. docs/forms-watch-playbook.md).
"""

import os

from lxml import etree

from odoo.tests import TransactionCase, tagged

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schemas', 'F0103309.xsd')
SCHEMA_F0103407 = os.path.join(os.path.dirname(__file__), 'schemas', 'F0103407.xsd')


@tagged('post_install', '-at_install')
class TestF0103309XsdValidation(TransactionCase):

    def _sample_vals(self):
        # Реквізити з реального прийнятого зразка (ФОП гр.3, I півріччя 2026),
        # проти якого генератор звірено byte-for-byte (коміт 3d7c7a4).
        return {
            'taxpayer_tin': '2940910418',
            'taxpayer_name': 'ТОВ Тест',
            'taxpayer_address': 'УКРАЇНА, м. Київ, вул. Тестова, 1',
            'taxpayer_email': 'test@example.com',
            'taxpayer_phone': '+38(000)-000-00-00',
            'declaration_type': '0',
            'tax_office_code': '1716',
            'tax_office_name': 'ГУ ДПС (тест)',
            'quarter_marker': 'HHY',
            'period_type': '3',
            'period_month': '6',
            'year': 2026,
            'employee_count': 0,
            'activities': [('62.01', "Комп'ютерне програмування")],
            'income_total': 100000.0,
            'tax_amount': 5000.0,
            'tax_paid_prev': 0.0,
            'tax_to_pay': 5000.0,
            'military_amount': 1000.0,
            'military_paid_prev': 0.0,
            'military_to_pay': 1000.0,
        }

    def test_generated_xml_validates_against_official_xsd(self):
        wizard = self.env['l10n_ua.tax.document.wizard']
        xml = wizard._render_F0103309_xml(self._sample_vals())

        # Подання йде у windows-1251 — валідуємо саме ті байти, що підуть у ДПС.
        doc = etree.fromstring(xml.encode('windows-1251'))
        schema = etree.XMLSchema(etree.parse(SCHEMA_PATH))
        schema.assertValid(doc)  # кидає DocumentInvalid із деталями, якщо не так

    def test_period_markers_validate(self):
        """Кожен маркер періоду з мапи має давати XSD-валідний документ."""
        wizard = self.env['l10n_ua.tax.document.wizard']
        schema = etree.XMLSchema(etree.parse(SCHEMA_PATH))
        for period_type in ('2', '3', '4', '5'):
            vals = self._sample_vals()
            vals['period_type'] = period_type
            xml = wizard._render_F0103309_xml(vals)
            doc = etree.fromstring(xml.encode('windows-1251'))
            self.assertTrue(
                schema.validate(doc),
                'PERIOD_TYPE=%s дав XSD-невалідний XML: %s' % (
                    period_type, schema.error_log),
            )

    def test_annual_group_1_2_declaration_validates(self):
        """F0103407 — річна декларація 1–2 груп: розділ II або III, ВЗ помісячно."""
        wizard = self.env['l10n_ua.tax.document.wizard']
        schema = etree.XMLSchema(etree.parse(SCHEMA_F0103407))
        for group, income_tag, tax_tag in (('1', 'R001G3', 'R02G4'), ('2', 'R003G3', 'R03G4')):
            vals = dict(self._sample_vals(), group=group,
                        quarterly_tax=[1297.05] * 4, military_months=range(1, 13),
                        military_amount=10376.40)
            xml = wizard._render_F0103407_xml(vals)
            doc = etree.fromstring(xml.encode('windows-1251'))
            self.assertTrue(schema.validate(doc), '%s: %s' % (group, schema.error_log))
            body = doc.find('DECLARBODY')
            self.assertEqual(body.findtext('HY'), '1')
            self.assertEqual(body.findtext(income_tag), '100000.00')
            self.assertEqual(body.findtext(tax_tag), '1297.05')
            self.assertEqual(body.findtext('R08G12'), '1')
            self.assertEqual(body.findtext('R022G3'), '10376.40')
            self.assertEqual(doc.findtext('DECLARHEAD/C_DOC_SUB'), '034')

    def test_without_email_and_phone(self):
        """Порожні HEMAIL/HTEL XSD не приймає — без контактів їх не пишемо."""
        wizard = self.env['l10n_ua.tax.document.wizard']
        schema = etree.XMLSchema(etree.parse(SCHEMA_PATH))
        vals = dict(self._sample_vals(), taxpayer_email='', taxpayer_phone='')
        doc = etree.fromstring(wizard._render_F0103309_xml(vals).encode('windows-1251'))
        self.assertTrue(schema.validate(doc), schema.error_log)
        self.assertIsNone(doc.find('DECLARBODY/HEMAIL'))
