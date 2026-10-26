import base64
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_ua_agro_land.tests.common import AgroLandTestCase


@tagged('post_install', '-at_install')
class TestInKindVat(AgroLandTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.l10n_ua_is_vat_payer = True
        cls.acc_6412 = cls._account('6412', 'Розрахунки за ПДВ', 'liability_payable')
        cls.acc_949 = cls._account('949', 'Інші витрати операційної діяльності', 'expense')
        cls.vat14 = cls.env['account.tax'].create({
            'name': 'ПДВ 14 % (тест натуроплати)', 'amount': 14.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'company_id': cls.company.id,
            'invoice_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base'}),
                (0, 0, {'repartition_type': 'tax', 'account_id': cls.acc_6412.id})],
            'refund_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base'}),
                (0, 0, {'repartition_type': 'tax', 'account_id': cls.acc_6412.id})],
        })
        cls.wheat = cls.env['product.product'].create({
            'name': 'Пшениця 3 клас (тест ПДВ)', 'is_storable': True,
            'uom_id': cls.env.ref('uom.product_uom_kgm').id, 'taxes_id': [(6, 0, cls.vat14.ids)],
            'uktzed_code': '1001'})
        cls.lease1 = cls._new_lease(cls.lessor, cls.plot1)     # 9 600 → 7 392 до виплати
        cls.lease2 = cls._new_lease(cls.lessor2, cls.plot2)    # 12 000 → 9 240
        accrual = cls.env['l10n_ua.agro.rent.accrual'].create({
            'date': date(2096, 12, 31), 'date_from': date(2096, 1, 1), 'date_to': date(2096, 12, 31)})
        accrual.action_compute()
        accrual.action_post()
        cls.accrual = accrual

    @classmethod
    def _new_lease(cls, lessor, plots):
        lease = cls.env['l10n_ua.agro.land.lease'].create({
            'name': 'V-%s' % plots[0].cadastral_number[-4:], 'lessor_id': lessor.id,
            'plot_ids': [(6, 0, plots.ids)], 'date_start': date(2095, 1, 1), 'term_years': 10,
            'rent_method': 'ngo_percent', 'rent_percent': 12.0, 'payment_form': 'in_kind'})
        lease.action_activate()
        return lease

    def _payment(self):
        payment = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 12, 31), 'payment_form': 'in_kind', 'journal_id': self.journal.id,
            'product_id': self.wheat.id, 'price_unit': 8.0, 'accrual_id': self.accrual.id})
        payment.action_fill()
        payment.action_post()
        return payment

    def test_vat_included_and_tax_invoices(self):
        payment = self._payment()
        # 7 392 і 9 240 включають ПДВ 14 %
        base1, base2 = round(7392 / 1.14, 2), round(9240 / 1.14, 2)
        vat = round(7392 - base1, 2) + round(9240 - base2, 2)
        self.assertAlmostEqual(payment.vat_amount, vat, places=2)
        move = payment.vat_move_id
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(sum(move.line_ids.filtered(lambda l: l.account_id == self.acc_6412).mapped('credit')),
                               vat, places=2)
        self.assertAlmostEqual(sum(move.line_ids.filtered(lambda l: l.account_id == self.acc_712).mapped('debit')),
                               vat, places=2)
        invoices = payment.tax_invoice_ids
        self.assertEqual(len(invoices), 2)
        first = invoices.filtered(lambda t: t.partner_id == self.lessor)
        self.assertEqual(first.non_payer_reason, '02')
        self.assertEqual(first.date, date(2096, 12, 31))
        self.assertEqual(first.line_ids.vat_rate, '14')
        self.assertEqual(first.line_ids.quantity, 924.0)
        self.assertAlmostEqual(first.total_base, base1, places=2)
        self.assertAlmostEqual(first.total_vat, round(7392 - base1, 2), places=2)
        first.action_generate_xml()
        xml = base64.b64decode(first.file_xml).decode('windows-1251')
        self.assertIn('<BUYER_IPN>100000000000</BUYER_IPN>', xml)
        self.assertIn('<BUYER_NAME>Неплатник</BUYER_NAME>', xml)
        self.assertIn('<HTYPR>02</HTYPR>', xml)

    def test_vat_on_top_and_cancel(self):
        self.company.write({'l10n_ua_agro_in_kind_vat_included': False,
                            'l10n_ua_agro_in_kind_vat_expense_account_id': self.acc_949.id})
        payment = self._payment()
        self.assertAlmostEqual(payment.vat_amount, round(7392 * 0.14, 2) + round(9240 * 0.14, 2), places=2)
        self.assertAlmostEqual(payment.tax_invoice_ids.filtered(
            lambda t: t.partner_id == self.lessor).total_base, 7392.0, places=2)
        self.assertTrue(payment.vat_move_id.line_ids.filtered(lambda l: l.account_id == self.acc_949))
        payment.action_cancel()
        self.assertEqual(set(payment.tax_invoice_ids.mapped('state')), {'cancelled'})
        reversal = self.env['account.move'].search([('reversed_entry_id', '=', payment.vat_move_id.id)])
        self.assertEqual(reversal.state, 'posted')

    def test_registered_invoice_blocks_cancel(self):
        payment = self._payment()
        payment.tax_invoice_ids[:1].state = 'registered'
        with self.assertRaises(UserError):
            payment.action_cancel()

    def test_non_vat_payer_and_money(self):
        self.company.l10n_ua_is_vat_payer = False
        payment = self._payment()
        self.assertFalse(payment.tax_invoice_ids)
        self.assertFalse(payment.vat_move_id)
