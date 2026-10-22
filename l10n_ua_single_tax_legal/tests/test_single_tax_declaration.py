"""Декларація ЄП юрособи 3 групи (J0103509): дохід з бухобліку, рядки, XSD, подання.

XSD у `tests/schemas` — контрольні схеми з пакета СКЗ ДПС (повна версія 1.34.0.0),
форма за наказом № 578 у редакції наказу № 57.
"""
import base64
import os
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

SCHEMAS = os.path.join(os.path.dirname(__file__), 'schemas')
CONFIG = 'odoo.addons.l10n_ua_tax_cabinet.models.l10n_ua_tax_cabinet_config.L10nUaTaxCabinetConfig'


@tagged('post_install', '-at_install')
class TestSingleTaxDeclaration(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # Бухгалтер з українською локалізацією: довідники ДПІ — для групи UA.
        cls.env.user.sudo().group_ids |= cls.env.ref('l10n_ua_account_base.group_ua_user')
        Office = cls.env['l10n_ua.tax.office'].sudo()
        office = Office.search([('code', '=', '2650')], limit=1) or \
            Office.create({'name': 'ГУ ДПС у м. Києві', 'code': '2650'})
        cls.company.write({
            'name': 'ТОВ «Спрощенець»',
            'edrpou': '12345678',
            'l10n_ua_tax_office_id': office.id,
            'kved_main': '62.01',
            'city': 'Київ', 'street': 'вул. Хрещатик, 1', 'zip': '01001',
            'l10n_ua_tax_rate': 5.0,
        })
        cls.customer = cls.env['res.partner'].create({'name': 'ТОВ Покупець'})
        cls.bank = cls.company_data['default_journal_bank']
        cls.receivable = cls.customer.with_company(cls.company).property_account_receivable_id
        cls.vat20 = cls.env['account.tax'].create({
            'name': 'ПДВ 20 % (тест ЄП)', 'amount': 20.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'company_id': cls.company.id,
        })

    # ---------------------------------------------------------------- helpers

    def _invoice(self, amount, day, taxes=None):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.customer.id,
            'invoice_date': day, 'date': day,
            'invoice_line_ids': [(0, 0, {'name': 'послуга', 'quantity': 1,
                                         'price_unit': amount,
                                         'tax_ids': [(6, 0, taxes.ids if taxes else [])]})],
        })
        move.action_post()
        return move

    def _receipt(self, amount, day, invoice=None):
        """Банківська виписка: надходження від покупця (від'ємне — повернення)."""
        bank_account = self.bank.default_account_id
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.bank.id, 'date': day,
            'line_ids': [
                (0, 0, {'account_id': bank_account.id, 'name': 'надходження',
                        'debit': max(amount, 0), 'credit': max(-amount, 0)}),
                (0, 0, {'account_id': self.receivable.id, 'partner_id': self.customer.id,
                        'name': 'оплата', 'debit': max(-amount, 0),
                        'credit': max(amount, 0)}),
            ],
        })
        move.action_post()
        if invoice:
            (move.line_ids | invoice.line_ids).filtered(
                lambda l: l.account_id == self.receivable and not l.reconciled).reconcile()
        return move

    def _declaration(self, period='q1', rate='5', **vals):
        decl = self.env['l10n_ua.single.tax.declaration'].create({
            'year': 2026, 'period': period, 'rate': rate, 'company_id': self.company.id,
            'signatory_name': 'Іван ПЕТРЕНКО', 'signatory_rnokpp': '1234567890', **vals,
        })
        decl.action_calculate()
        return decl

    # ---------------------------------------------------------------- tests

    def test_income_is_received_cash_less_refunds(self):
        invoice = self._invoice(12000.0, '2026-02-10')
        self._receipt(12000.0, '2026-02-20', invoice)
        self._receipt(3000.0, '2026-03-05')            # аванс — теж дохід
        self._receipt(-1000.0, '2026-03-20')           # повернення покупцю
        self._receipt(5000.0, '2026-04-02')            # уже II квартал
        self._invoice(7000.0, '2026-03-25')            # неоплачене — не дохід
        decl = self._declaration()
        self.assertEqual(decl.income_accounting, 14000.0)
        self.assertEqual(decl.income_vat, 0.0)
        self.assertEqual(decl.line_1, 14000.0)
        self.assertEqual(decl.line_5, 14000.0)
        self.assertEqual(decl.line_6, 700.0)
        self.assertEqual(decl.line_10, 700.0)
        self.assertEqual(decl.line_19, 140.0)

    def test_vat_is_not_income_at_3_percent(self):
        invoice = self._invoice(1000.0, '2026-01-15', taxes=self.vat20)
        self.assertEqual(invoice.amount_total, 1200.0)
        self._receipt(1200.0, '2026-01-20', invoice)
        self.company.account_sale_tax_id = self.vat20
        self._receipt(600.0, '2026-02-01')            # аванс: ПДВ за ставкою продажу
        decl = self._declaration(rate='3')
        self.assertEqual(decl.income_accounting, 1800.0)
        self.assertEqual(decl.income_vat, 300.0)
        self.assertEqual(decl.line_1, 1500.0)
        self.assertEqual(decl.line_6, 45.0)

    def test_half_year_pays_only_the_difference(self):
        self._receipt(10000.0, '2026-02-01')
        q1 = self._declaration()
        q1.with_context(l10n_ua_single_tax_declaration_unlock=True).state = 'accepted'
        self._receipt(6000.0, '2026-05-01')
        h1 = self._declaration(period='h1')
        self.assertEqual(h1.line_8, 800.0)
        self.assertEqual(h1.line_9, 500.0)
        self.assertEqual(h1.line_10, 300.0)
        self.assertEqual(h1.line_20, 100.0)
        self.assertEqual(h1.line_21, 60.0)

    def test_income_over_the_limit_is_taxed_twice(self):
        decl = self._declaration()
        limit = decl.income_limit
        self.assertTrue(limit)
        decl.income_other = limit + 1000.0
        self.assertEqual(decl.line_1, limit)
        self.assertEqual(decl.line_2, 1000.0)
        self.assertEqual(decl.line_7, 100.0)        # 1000 × 5 % × 2

    def test_xml_is_valid_against_dps_xsd(self):
        self._receipt(10000.0, '2026-02-01')
        decl = self._declaration()
        decl.accountant_name = 'Олена КОВАЛЬ'
        decl.accountant_rnokpp = '2345678901'
        decl.action_generate_xml()
        xml = base64.b64decode(decl.xml_file)
        schema = etree.XMLSchema(etree.parse(os.path.join(SCHEMAS, 'J0103509.xsd')))
        root = etree.fromstring(xml)
        schema.assertValid(root)
        # C_REG C_RAJ TIN C_DOC SUB VER STAN TYPE CNT PERIOD_TYPE MONTH YEAR C_STI_ORIG
        self.assertEqual(decl.xml_filename, '26500012345678J0103509100000000120320262650.xml')
        body = root.find('DECLARBODY')
        self.assertEqual(body.findtext('H1KV'), '1')
        self.assertEqual(body.findtext('HKVED'), '62.01')
        self.assertEqual(body.findtext('R001G4'), '10000.00')
        self.assertEqual(body.findtext('R006G4'), '500.00')
        self.assertEqual(body.findtext('R019G4'), '100.00')
        self.assertIsNone(body.find('R001G3'))
        self.assertIsNone(body.find('R002G4'))

    def test_vat_payer_fills_column_3(self):
        self.company.account_sale_tax_id = self.vat20
        self._receipt(1200.0, '2026-02-01')           # аванс 1200 з ПДВ → дохід 1000
        decl = self._declaration(rate='3', period='9m')
        decl.action_generate_xml()
        root = etree.fromstring(base64.b64decode(decl.xml_file))
        etree.XMLSchema(etree.parse(os.path.join(SCHEMAS, 'J0103509.xsd'))).assertValid(root)
        body = root.find('DECLARBODY')
        self.assertEqual(body.findtext('H3KV'), '1')
        self.assertEqual(body.findtext('R001G3'), '1000.00')
        self.assertEqual(body.findtext('R006G3'), '30.00')
        self.assertEqual(body.findtext('R019G3'), '10.00')

    def test_missing_requisites_are_reported_together(self):
        decl = self._declaration()
        decl.signatory_rnokpp = False
        self.company.kved_main = False
        with self.assertRaises(UserError) as err:
            decl.action_generate_xml()
        self.assertIn('РНОКПП', str(err.exception))
        self.assertIn('КВЕД', str(err.exception))

    def test_submitted_declaration_is_locked(self):
        decl = self._declaration()
        decl.with_context(l10n_ua_single_tax_declaration_unlock=True).state = 'submitted'
        with self.assertRaises(UserError):
            decl.income_other = 100.0
        with self.assertRaises(UserError):
            decl.unlink()

    def test_submit_posts_the_xml(self):
        self._receipt(10000.0, '2026-02-01')
        decl = self._declaration()
        config = self.env['l10n_ua.tax.cabinet.config'].with_context(active_test=False).search(
            [('company_id', '=', self.company.id)], limit=1)
        vals = {'name': 'Кабінет', 'taxpayer_code': '12345678', 'active': True}
        if config:
            config.write(vals)
        else:
            self.env['l10n_ua.tax.cabinet.config'].create({**vals, 'company_id': self.company.id})
        with patch(CONFIG + '._get_dps_encrypt_certificate', return_value=b'CERT'):
            spec = decl.kep_prepare_signing()
        self.assertEqual(spec['documents'][0]['filename'], decl.xml_filename)

        posted = {}

        def fake_post(config, content, fname, headers, extra_files=()):
            posted['fname'] = fname
            return [{'status': 'OK', 'id': 77}]

        with patch(CONFIG + '._post_report', autospec=True, side_effect=fake_post):
            decl.kep_submit_signed({'doc': 'ENV1'}, 'AUTH')
        self.assertEqual(posted['fname'], decl.xml_filename)
        self.assertEqual(decl.state, 'submitted')
        self.assertEqual(decl.dps_submission_id, '77')
