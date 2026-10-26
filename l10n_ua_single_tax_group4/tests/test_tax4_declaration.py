"""Декларація ЄП 4 групи (J0103806 + J0138106 + J0138306): розрахунок, МПЗ, XSD.

XSD у `tests/schemas` — контрольні схеми з пакета СКЗ ДПС (повна версія
1.34.0.0), форма за наказом № 578 у редакції наказу № 57.
"""
import base64
import os
from datetime import date

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_ua_agro_land.tests.common import AgroLandTestCase

SCHEMAS = os.path.join(os.path.dirname(__file__), 'schemas')
KATOTTG_A = 'UA56040170010076211'
KATOTTG_B = 'UA56040190000012345'


@tagged('post_install', '-at_install')
class TestTax4Declaration(AgroLandTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.sudo().group_ids |= cls.env.ref('l10n_ua_account_base.group_ua_user')
        Office = cls.env['l10n_ua.tax.office'].sudo()
        cls.office = Office.search([('code', '=', '1701')], limit=1) or \
            Office.create({'name': 'ГУ ДПС у Рівненській області', 'code': '1701'})
        cls.office_b = Office.search([('code', '=', '1705')], limit=1) or \
            Office.create({'name': 'Дубенська ДПІ', 'code': '1705'})
        cls.company.write({
            'name': 'ТОВ «Агро-Тест»', 'edrpou': '12345678', 'l10n_ua_tax_office_id': cls.office.id,
            'kved_main': '01.11', 'katottg': KATOTTG_A,
            'city': 'с. Зелена Долина', 'street': 'вул. Польова, 1', 'zip': '35600',
        })
        cls.acc_641 = cls._account('6414', 'Розрахунки за іншими податками', 'liability_payable')
        cls.company.l10n_ua_tax4_payable_account_id = cls.acc_641
        Plot = cls.env['l10n_ua.agro.land.plot']
        # власна рілля: 50 га, НГО 1 500 000 (30 000 / га)
        cls.own = Plot.create({
            'cadastral_number': '5621684800:01:002:0901', 'area': 50.0, 'ngo_value': 1500000.0,
            'ownership': 'company', 'owner_id': cls.company.partner_id.id, 'katottg': KATOTTG_A})
        # пай фізособи: 3 га, НГО 90 000, оренда з 01.07.2026
        cls.plot1.write({'area': 3.0, 'ngo_value': 90000.0, 'katottg': KATOTTG_A})
        cls.share_lease = cls._lease_cls(cls.lessor, cls.plot1, date(2026, 7, 1))
        # комунальне пасовище: 12,5 га, НГО 312 500, оренда в сільради з 2021
        cls.council = cls.env['res.partner'].create({'name': 'Сільська рада (тест)', 'is_company': True})
        cls.pasture = Plot.create({
            'cadastral_number': '5621684800:02:004:0901', 'area': 12.5, 'ngo_value': 312500.0,
            'land_type': 'pasture', 'ownership': 'communal', 'owner_id': cls.council.id,
            'katottg': KATOTTG_B, 'l10n_ua_tax4_arable_share': 0.0})
        cls.pasture_lease = cls._lease_cls(cls.council, cls.pasture, date(2021, 3, 1))
        (cls.plot2 | cls.plot3).write({'l10n_ua_tax4_excluded': True})
        # орендна плата за 2026 рік: нарахування й виплата
        accrual = cls.env['l10n_ua.agro.rent.accrual'].create({
            'date': date(2026, 12, 31), 'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31)})
        accrual.action_compute()
        accrual.action_post()
        cls.rent_accrual = accrual
        payment = cls.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2026, 12, 31), 'payment_form': 'money', 'journal_id': cls.cash.id,
            'accrual_id': accrual.id})
        payment.action_fill()
        payment.action_post()

    @classmethod
    def _lease_cls(cls, lessor, plots, start):
        lease = cls.env['l10n_ua.agro.land.lease'].create({
            'name': 'L-%s' % plots[0].cadastral_number[-6:], 'lessor_id': lessor.id,
            'plot_ids': [(6, 0, plots.ids)], 'date': start, 'date_start': start, 'term_years': 10,
            'registration_date': start, 'registration_number': '4150%04d' % plots[0].id,
            'rent_method': 'ngo_percent', 'rent_percent': 12.0})
        lease.action_activate()
        return lease

    def _declaration(self):
        decl = self.env['l10n_ua.tax4.declaration'].create({
            'year': 2027, 'signatory_name': 'Петро КОВАЛЬ', 'signatory_rnokpp': '3124567896'})
        decl.action_calculate()
        return decl

    def _validate(self, data, xsd):
        root = etree.fromstring(base64.b64decode(data))
        etree.XMLSchema(etree.parse(os.path.join(SCHEMAS, xsd))).assertValid(root)
        return root

    def test_tax_calculation(self):
        decl = self._declaration()
        own = decl.line_ids.filtered(lambda l: l.plot_id == self.own)
        self.assertEqual(own.ngo_ha, 30000.0)
        self.assertEqual(own.rate, 0.95)
        self.assertEqual(own.annual_tax, 14250.0)                     # 50 × 30 000 × 0,95 %
        self.assertEqual((own.q1, own.q2, own.q3, own.q4), (1425.0, 1425.0, 7125.0, 4275.0))
        pasture = decl.line_ids.filtered(lambda l: l.plot_id == self.pasture)
        self.assertEqual(pasture.annual_tax, 2968.75)                 # 12,5 × 25 000 × 0,95 %
        self.assertFalse(decl.line_ids.filtered(lambda l: l.plot_id == self.plot2))   # виключена
        self.assertEqual(decl.katottg, KATOTTG_A)
        self.assertEqual(decl.tax_office_id, self.office)

    def test_mpz_and_paid_taxes(self):
        decl = self._declaration()
        mpz = {l.plot_id: l for l in decl.mpz_line_ids}
        self.assertEqual(mpz[self.own].months, 12)
        self.assertEqual(mpz[self.own].mpz_ngo, 85500.0)              # 1 500 000 × 0,057
        self.assertEqual(mpz[self.plot1].months, 6)
        self.assertEqual(mpz[self.plot1].mpz_ngo, 2565.0)             # 90 000 × 0,057 × 6/12 > 2 100
        self.assertEqual(mpz[self.pasture].mpz_ngo, 17812.5)          # 312 500 × 0,057 > 700 × 12,5
        self.assertEqual(mpz[self.pasture].rent20, 7500.0)            # 20 % × 37 500 (комунальна земля)
        self.assertEqual(mpz[self.plot1].rent20, 0.0)                 # фізособа — не враховується
        self.assertEqual(decl.paid_pdfo_rent, sum(self.rent_accrual.line_ids.mapped('pdfo_amount')))
        expected = 85500.0 + 2565.0 + 17812.5 - decl.paid_total - 7500.0
        self.assertAlmostEqual(decl.mpz_balance, expected, places=2)
        self.assertAlmostEqual(decl.mpz_difference, max(expected, 0.0), places=2)
        self.assertAlmostEqual(decl.total_q1, decl.tax_q1 + decl.mpz_difference, places=2)

    def test_reporting_split_and_xsd(self):
        decl = self._declaration()
        decl.action_create_reporting()
        self.assertEqual(set(decl.child_ids.mapped('katottg')), {KATOTTG_A, KATOTTG_B})
        child_b = decl.child_ids.filtered(lambda c: c.katottg == KATOTTG_B)
        self.assertEqual(child_b.line_ids.plot_id, self.pasture)
        total_area = sum(decl.line_ids.mapped('area'))
        self.assertAlmostEqual(child_b.mpz_difference,
                               round(decl.mpz_balance * 12.5 / total_area, 2), places=2)
        child_b.tax_office_id = self.office_b
        for rec in (decl, child_b):
            rec.action_generate_xml()
            main = self._validate(rec.xml_file, 'J0103806.xsd')
            annex1 = self._validate(rec.annex1_xml_file, 'J0138106.xsd')
            self._validate(rec.annex3_xml_file, 'J0138306.xsd')
            self.assertEqual(len(main.findall('DECLARHEAD/LINKED_DOCS/DOC')), 2)
            self.assertEqual(main.findtext('DECLARBODY/HKATOTTG'), rec.katottg)
        self.assertEqual(decl.xml_file and etree.fromstring(base64.b64decode(decl.xml_file)).findtext(
            'DECLARBODY/HZG'), '1')
        body_b = etree.fromstring(base64.b64decode(child_b.annex1_xml_file)).find('DECLARBODY')
        self.assertEqual(body_b.findtext('T13RXXXXG8S'), self.pasture.cadastral_number)
        self.assertEqual(etree.fromstring(base64.b64decode(child_b.xml_file)).findtext(
            'DECLARHEAD/C_STI_ORIG'), '1705')

    def test_accruals_and_checks(self):
        decl = self._declaration()
        decl.action_post_accruals()
        self.assertEqual(len(decl.accrual_move_ids), 4)
        self.assertAlmostEqual(sum(decl.accrual_move_ids.line_ids.filtered(
            lambda l: l.account_id == self.acc_641).mapped('credit')), decl.total_annual, places=2)
        with self.assertRaises(UserError):
            decl.action_post_accruals()
        decl.signatory_rnokpp = False
        with self.assertRaises(UserError):
            decl.action_generate_xml()
