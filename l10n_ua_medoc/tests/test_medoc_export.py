"""Експорт ПН, актів і рахунків-фактур у файл обміну M.E.Doc."""
import base64
from datetime import date

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install', 'l10n_ua_medoc')
class TestMedocExport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'edrpou': '12345678',
            'l10n_ua_is_vat_payer': True,
            'l10n_ua_vat_ipn': '123456789012',
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'ТОВ "Осока"',
            'company_type': 'company',
            'edrpou': '30000005',
            'ipn': '3184710691',
            'is_vat_payer': True,
        })
        cls.vat_20 = cls.env['account.tax'].create({
            'name': 'ПДВ 20% (medoc)', 'amount': 20.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'company_id': cls.company.id,
        })

    def _tax_invoice(self, partner=None, **vals):
        return self.env['l10n_ua.tax.invoice'].create({
            'number': '15',
            'date': date(2026, 9, 17),
            'partner_id': (partner or self.customer).id,
            'line_ids': [
                (0, 0, {'name': 'Ринва біла', 'uktzed_code': '3925900000',
                        'quantity': 3, 'price_unit': 126.663333,
                        'vat_rate': '20'}),
                (0, 0, {'name': 'Доставка', 'dkpp_code': '49.41',
                        'quantity': 1, 'price_unit': 100.0, 'vat_rate': '7'}),
            ],
            **vals,
        })

    def _export(self, records, doc_kind=None):
        ctx = {'active_model': records._name, 'active_ids': records.ids}
        wizard = self.env['l10n_ua.medoc.export'].with_context(**ctx).create(
            {'doc_kind': doc_kind} if doc_kind else {})
        wizard.action_export()
        self.assertTrue(wizard.file_name.endswith('.xml'))
        return etree.fromstring(base64.b64decode(wizard.file_data))

    @staticmethod
    def _rows(card, tab=0, line=0):
        return {
            row.get('NAME'): row.findtext('VALUE')
            for row in card.findall('DOCUMENT/ROW')
            if row.get('TAB') == str(tab) and row.get('LINE') == str(line)
        }

    def test_tax_invoice_card(self):
        pn = self._tax_invoice()
        root = self._export(pn)
        self.assertEqual(root.findtext('ORG/FIELDS/EDRPOU'), '12345678')
        card = root.find('ORG/CARD')
        self.assertIsNone(card.get('RTFDOC'))
        self.assertEqual(card.findtext('FIELDS/CHARCODE'), 'J1201016')
        self.assertEqual(card.findtext('FIELDS/PERTYPE'), '0')
        self.assertEqual(card.findtext('FIELDS/PERDATE'), '01.09.2026')
        head = self._rows(card)
        self.assertEqual(head['FIRM_EDRPOU'], '12345678')
        self.assertEqual(head['FIRM_INN'], '123456789012')
        self.assertEqual(head['N11'], '17.09.2026')
        self.assertEqual(head['N2_11'], '15')
        self.assertEqual(head['N3'], 'ТОВ "Осока"')
        self.assertEqual(head['N4'], '3184710691')
        self.assertEqual(head['EDR_POK'], '30000005')
        self.assertNotIn('N13', head)
        self.assertEqual(head['A5_7'], '379.99')
        self.assertEqual(head['A6_7'], '76')
        self.assertEqual(head['A5_71'], '100')
        self.assertEqual(head['A6_71'], '7')
        self.assertEqual(head['A6_11'], '83')
        self.assertEqual(head['A7_11'], '562.99')
        first = self._rows(card, tab=1, line=0)
        self.assertEqual(first['TAB1_A1'], '1')
        self.assertEqual(first['TAB1_A131'], '3925900000')
        self.assertNotIn('TAB1_A133', first)
        self.assertEqual(first['TAB1_A15'], '3')
        self.assertEqual(first['TAB1_A16'], '126.663333')
        self.assertEqual(first['TAB1_A8'], '20')
        self.assertEqual(first['TAB1_A10'], '379.99')
        second = self._rows(card, tab=1, line=1)
        self.assertEqual(second['TAB1_A133'], '49.41')
        self.assertEqual(second['TAB1_A8'], '7')

    def test_tax_invoice_non_payer(self):
        """ПН на неплатника: умовний ІПН, не видається покупцю, причина 02."""
        buyer = self.env['res.partner'].create({'name': 'Фізособа'})
        head = self._rows(self._export(self._tax_invoice(buyer)).find('ORG/CARD'))
        self.assertEqual(head['N4'], '100000000000')
        self.assertEqual(head['N3'], 'Неплатник')
        self.assertEqual(head['N13'], '1')
        self.assertEqual(head['N14'], '02')

    def test_non_payer_with_rnokpp(self):
        """РНОКПП ФОП-неплатника не робить його платником ПДВ."""
        buyer = self.env['res.partner'].create({
            'name': 'ФОП Неплатник', 'ipn': '3184710691'})
        head = self._rows(self._export(self._tax_invoice(buyer)).find('ORG/CARD'))
        self.assertEqual(head['N4'], '100000000000')
        self.assertEqual(head['N3'], 'Неплатник')
        self.assertEqual(head['N13'], '1')
        self.assertNotIn('EDR_POK', head)
        # Зменшення для неплатника реєструє постачальник
        head = self._rows(self._export(
            self._adjustment(self._tax_invoice(buyer))).find('ORG/CARD'))
        self.assertEqual(head['N26'], '1')
        self.assertNotIn('N16', head)
        self.assertEqual(head['N4'], '100000000000')

    def test_payer_flag_and_ipn_must_agree(self):
        """Платник без ІПН і 12-значний ІПН без позначки — помилка, не здогад."""
        no_ipn = self.env['res.partner'].create({
            'name': 'ТОВ Без ІПН', 'is_vat_payer': True})
        with self.assertRaises(UserError):
            self._export(self._tax_invoice(no_ipn))
        no_flag = self.env['res.partner'].create({
            'name': 'ТОВ Без позначки', 'vat': '300000026594'})
        with self.assertRaises(UserError):
            self._export(self._tax_invoice(no_flag))

    def test_cancelled_is_rejected(self):
        pn = self._tax_invoice()
        pn.action_cancel()
        with self.assertRaises(UserError):
            self._export(pn)

    def test_unknown_rate_is_rejected(self):
        """Рядок без ставки не стає мовчки 20 %."""
        pn = self._tax_invoice()
        pn.line_ids[0].vat_rate = False
        with self.assertRaises(UserError):
            self._export(pn)

    def test_buyer_ipn_falls_back_to_vat(self):
        """12-значний ІПН юрособи зберігається у стандартному полі vat."""
        buyer = self.env['res.partner'].create({
            'name': 'ТОВ Платник', 'company_type': 'company',
            'vat': '300000026594', 'is_vat_payer': True})
        head = self._rows(self._export(self._tax_invoice(buyer)).find('ORG/CARD'))
        self.assertEqual(head['N4'], '300000026594')
        self.assertNotIn('N13', head)

    def test_several_tax_invoices_in_one_file(self):
        pns = self._tax_invoice() | self._tax_invoice(number='16')
        cards = self._export(pns).findall('ORG/CARD')
        self.assertEqual(len(cards), 2)
        docids = {card.findtext('FIELDS/DOCID') for card in cards}
        self.assertEqual(len(docids), 2)
        # DOCID стабільний між вивантаженнями — повторний імпорт не дублює
        again = self._export(pns).findall('ORG/CARD')
        self.assertEqual(docids, {c.findtext('FIELDS/DOCID') for c in again})

    def test_fop_seller_uses_f_form(self):
        self.company.edrpou = False
        self.company.partner_id.ipn = '1234567899'
        root = self._export(self._tax_invoice())
        self.assertEqual(root.findtext('ORG/FIELDS/EDRPOU'), '1234567899')
        self.assertEqual(root.findtext('ORG/CARD/FIELDS/CHARCODE'), 'F1201016')

    def test_received_is_rejected(self):
        with self.assertRaises(UserError):
            self._export(self._tax_invoice(invoice_type='received'))

    def _adjustment(self, original, **vals):
        """РК на повернення однієї ринви з оригінальної ПН."""
        return self.env['l10n_ua.tax.invoice'].create({
            'doc_type': 'rk',
            'number': '3',
            'date': date(2026, 10, 2),
            'partner_id': original.partner_id.id,
            'original_invoice_id': original.id,
            'reason': 'Повернення товару',
            'line_ids': [(0, 0, {
                'name': 'Доставка', 'dkpp_code': '49.41',
                'quantity': -1, 'price_unit': 100.0, 'vat_rate': '7'})],
            **vals,
        })

    def test_adjustment_card(self):
        original = self._tax_invoice()
        card = self._export(self._adjustment(original)).find('ORG/CARD')
        self.assertEqual(card.findtext('FIELDS/CHARCODE'), 'J1201216')
        self.assertEqual(card.findtext('FIELDS/PERDATE'), '01.10.2026')
        head = self._rows(card)
        self.assertEqual(head['N15'], '02.10.2026')
        self.assertEqual(head['N1_11'], '3')
        self.assertEqual(head['N2'], '17.09.2026')
        self.assertEqual(head['N2_11'], '15')
        self.assertEqual(head['N4'], '3184710691')
        # Зменшення для покупця-платника реєструє покупець
        self.assertEqual(head['N16'], '1')
        self.assertNotIn('N26', head)
        self.assertEqual(head['A1_91'], '-100')
        self.assertEqual(head['A2_91'], '-7')
        self.assertEqual(head['A2_92'], '-7')
        line = self._rows(card, tab=1)
        # «Доставка» — другий рядок оригінальної ПН
        self.assertEqual(line['TAB1_A01'], '2')
        self.assertEqual(line['TAB1_A2'], 'Повернення товару')
        self.assertEqual(line['TAB1_A33'], '49.41')
        self.assertEqual(line['TAB1_A5'], '-1')
        self.assertEqual(line['TAB1_A6'], '100')
        self.assertEqual(line['TAB1_A011'], '7')
        self.assertEqual(line['TAB1_A013'], '-100')

    def test_adjustment_registered_by_seller(self):
        """Збільшення та РК на неплатника реєструє постачальник."""
        original = self._tax_invoice()
        increase = self._adjustment(original, line_ids=[(0, 0, {
            'name': 'Доставка', 'quantity': 1, 'price_unit': 100.0,
            'vat_rate': '7'})])
        head = self._rows(self._export(increase).find('ORG/CARD'))
        self.assertEqual(head['N26'], '1')
        self.assertNotIn('N16', head)

        buyer = self.env['res.partner'].create({'name': 'Фізособа'})
        head = self._rows(self._export(
            self._adjustment(self._tax_invoice(buyer))).find('ORG/CARD'))
        self.assertEqual(head['N26'], '1')
        self.assertEqual(head['N4'], '100000000000')
        self.assertEqual(head['N17'], '1')
        self.assertEqual(head['N18'], '02')

    def test_adjustment_needs_original(self):
        original = self._tax_invoice()
        with self.assertRaises(UserError):
            self._export(self._adjustment(original, original_invoice_id=False))
        # рядок, якого немає в оригінальній ПН
        with self.assertRaises(UserError):
            self._export(self._adjustment(original, line_ids=[(0, 0, {
                'name': 'Чужий товар', 'quantity': -1, 'price_unit': 5.0,
                'vat_rate': '20'})]))

    def test_adjustment_same_item_on_several_lines(self):
        """Один товар кількома рядками ПН: кожен рядок РК — свій рядок ПН."""
        original = self._tax_invoice(line_ids=[
            (0, 0, {'name': 'Ринва', 'quantity': 3, 'price_unit': 100.0,
                    'vat_rate': '20'}),
            (0, 0, {'name': 'Ринва', 'quantity': 2, 'price_unit': 90.0,
                    'vat_rate': '20'}),
            (0, 0, {'name': 'Ринва', 'quantity': 1, 'price_unit': 90.0,
                    'vat_rate': '20'}),
        ])
        card = self._export(self._adjustment(original, line_ids=[
            (0, 0, {'name': 'Ринва', 'quantity': -1, 'price_unit': 90.0,
                    'vat_rate': '20'}),
            (0, 0, {'name': 'Ринва', 'quantity': -1, 'price_unit': 90.0,
                    'vat_rate': '20'}),
            (0, 0, {'name': 'Ринва', 'quantity': -1, 'price_unit': 100.0,
                    'vat_rate': '20'}),
        ])).find('ORG/CARD')
        self.assertEqual(
            [self._rows(card, tab=1, line=idx)['TAB1_A01'] for idx in range(3)],
            ['2', '3', '1'])

    def test_mixed_pn_and_rk_in_one_file(self):
        original = self._tax_invoice()
        cards = self._export(
            original | self._adjustment(original)).findall('ORG/CARD')
        self.assertEqual(
            sorted(c.findtext('FIELDS/CHARCODE') for c in cards),
            ['J1201016', 'J1201216'])

    def _move(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_date': '2026-09-17',
            'invoice_line_ids': [(0, 0, {
                'name': 'Консультація', 'quantity': 2, 'price_unit': 500.0,
                'discount': 10.0, 'tax_ids': [(6, 0, self.vat_20.ids)],
            })],
        })
        move.action_post()
        return move

    def test_act_card(self):
        move = self._move()
        card = self._export(move, 'act').find('ORG/CARD')
        self.assertEqual(card.get('RTFDOC'), '1')
        self.assertEqual(card.findtext('FIELDS/CHARCODE'), 'AKT_pdv')
        self.assertEqual(card.findtext('FIELDS/SDOCTYPE'), '10104')
        self.assertEqual(card.findtext('FIELDS/PARTCODE'), '7')
        head = self._rows(card)
        self.assertEqual(head['DOCDATE'], '17.09.2026 00:00:00')
        self.assertEqual(head['NUM'], move.name)
        self.assertEqual(head['SUMWITHOUTPDV'], '900')
        self.assertEqual(head['SUMPDV'], '180')
        self.assertEqual(head['DOCSUM'], '1080')
        self.assertEqual(head['SIDE_CD_K'], 'ТОВ "Осока"')
        self.assertEqual(head['SIDE_EDRPOU_K'], '30000005')
        line = self._rows(card, tab=1)
        self.assertEqual(line['TAB1_SPR1_NAME'], 'Консультація')
        self.assertEqual(line['TAB1_A3'], '2')
        self.assertEqual(line['TAB1_A4'], '450')
        self.assertEqual(line['TAB1_A5'], '900')

    def test_invoice_card(self):
        card = self._export(self._move(), 'invoice').find('ORG/CARD')
        self.assertEqual(card.findtext('FIELDS/CHARCODE'), 'RAH_pdv')
        self.assertEqual(card.findtext('FIELDS/SDOCTYPE'), '10103')
        line = self._rows(card, tab=1)
        self.assertEqual(line['TAB1_A1'], 'Консультація')
        self.assertNotIn('TAB1_SPR1_NAME', line)

    def test_draft_move_is_rejected(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.customer.id,
            'invoice_date': '2026-09-17',
            'invoice_line_ids': [(0, 0, {
                'name': 'Консультація', 'quantity': 1, 'price_unit': 500.0})],
        })
        with self.assertRaises(UserError):
            self._export(move, 'act')

    def test_vendor_bill_is_rejected(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.customer.id,
            'invoice_date': '2026-09-17'})
        with self.assertRaises(UserError):
            self._export(bill, 'act')
