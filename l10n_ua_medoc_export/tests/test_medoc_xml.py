"""Контейнер ZVIT: структура, кодування, пропуск порожніх реквізитів."""
from datetime import date

from lxml import etree

from odoo.tests import BaseCase, tagged

from ..tools.medoc_xml import MedocCard, build_zvit, fmt_number


@tagged('post_install', '-at_install', 'l10n_ua_medoc_export')
class TestMedocXml(BaseCase):

    def _build(self, card):
        return build_zvit('12345678', [card], date(2026, 10, 11))

    def test_fmt_number_trims_zeros(self):
        self.assertEqual(fmt_number(1200.0), '1200')
        self.assertEqual(fmt_number(15.95), '15.95')
        self.assertEqual(fmt_number(126.663333, 6), '126.663333')
        self.assertEqual(fmt_number(0.0), '0')

    def test_container_structure(self):
        card = MedocCard([('CHARCODE', 'J1201016'), ('NOTATION', '')])
        card.add('N3', 'ТОВ "Осока" & Ко')
        raw = self._build(card)
        self.assertTrue(raw.startswith(
            b'<?xml version="1.0" encoding="windows-1251"?>'))
        root = etree.fromstring(raw)
        self.assertEqual(root.tag, 'ZVIT')
        self.assertEqual(root.findtext('TRANSPORT/VERSION'), '4.1')
        self.assertEqual(root.findtext('TRANSPORT/CREATEDATE'), '11.10.2026')
        self.assertEqual(root.findtext('ORG/FIELDS/EDRPOU'), '12345678')
        self.assertEqual(root.findtext('ORG/CARD/FIELDS/CHARCODE'), 'J1201016')
        row = root.find('ORG/CARD/DOCUMENT/ROW')
        self.assertEqual(dict(row.attrib), {'LINE': '0', 'TAB': '0', 'NAME': 'N3'})
        self.assertEqual(row.findtext('VALUE'), 'ТОВ "Осока" & Ко')

    def test_empty_values_are_skipped(self):
        """M.E.Doc не приймає <VALUE></VALUE> — порожній реквізит не пишемо."""
        card = MedocCard([('CHARCODE', 'AKT_pdv')], primary=True)
        for value in ('', '   ', None, False):
            card.add('SIDE_TEL_K', value)
        card.add('TAB1_A3', 0, tab=1, line=2)
        root = etree.fromstring(self._build(card))
        self.assertEqual(root.find('ORG/CARD').get('RTFDOC'), '1')
        rows = root.findall('ORG/CARD/DOCUMENT/ROW')
        self.assertEqual([r.get('NAME') for r in rows], ['TAB1_A3'])
        self.assertEqual(rows[0].get('LINE'), '2')
        self.assertEqual(rows[0].findtext('VALUE'), '0')

    def test_chars_outside_cp1251_survive(self):
        card = MedocCard([('CHARCODE', 'RAH_pdv')])
        card.add('FIRM_NAME', 'ТОВ «Памʼять»')  # U+02BC немає у windows-1251
        raw = self._build(card)
        self.assertIn(b'&#700;', raw)
        root = etree.fromstring(raw)
        self.assertEqual(
            root.findtext('ORG/CARD/DOCUMENT/ROW/VALUE'), 'ТОВ «Памʼять»')
