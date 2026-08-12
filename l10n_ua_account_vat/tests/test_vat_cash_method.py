"""Дата ПН: перша подія проти касового методу (п. 187.10 ПКУ)."""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install', 'l10n_ua_account_vat')
class TestVatCashMethod(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Покупець (перша подія)'})
        cls.customer_cash = cls.env['res.partner'].create({'name': 'Покупець (касовий)'})
        cls.customer_cash.with_company(cls.env.company).l10n_ua_vat_cash_method = True

    def _invoice(self, partner, invoice_date):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            'date': invoice_date,
            'invoice_line_ids': [(0, 0, {
                'name': 'послуга',
                'quantity': 1,
                'price_unit': 1000.0,
                'tax_ids': [],
            })],
        })
        move.action_post()
        return move

    def _pay(self, move, payment_date, amount=None):
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids
        ).create({
            'payment_date': payment_date,
            'amount': amount if amount is not None else move.amount_total,
        })
        return wizard._create_payments()

    # ------------------------------------------------------------ перша подія

    def test_first_event_uses_invoice_date_when_unpaid(self):
        """Без оплати перша подія — відвантаження, тобто дата документа."""
        move = self._invoice(self.customer, '2025-03-10')

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-03-10'))

    def test_first_event_uses_payment_date_on_prepayment(self):
        """Передоплата — раніша подія, отже ПН за датою грошей."""
        move = self._invoice(self.customer, '2025-03-10')
        self._pay(move, '2025-03-04')

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-03-04'))

    def test_first_event_keeps_invoice_date_on_postpayment(self):
        """Післяоплата пізніша за відвантаження і дату ПН не зсуває."""
        move = self._invoice(self.customer, '2025-03-10')
        self._pay(move, '2025-04-02')

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-03-10'))

    # --------------------------------------------------------- касовий метод

    def test_cash_method_uses_payment_date(self):
        """За касовим методом дата ПН — дата руху коштів, а не документа."""
        move = self._invoice(self.customer_cash, '2025-03-10')
        self._pay(move, '2025-04-02')

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-04-02'))

    def test_cash_method_refuses_while_unpaid(self):
        """Поки грошей немає, зобовʼязання не виникло — ПН складати нема на що."""
        move = self._invoice(self.customer_cash, '2025-03-10')

        with self.assertRaises(UserError):
            move._l10n_ua_tax_invoice_date()

    def test_cash_method_refuses_on_partial_payment(self):
        """Часткова оплата: відмова замість мовчазної ПН на повну суму (#255)."""
        move = self._invoice(self.customer_cash, '2025-03-10')
        self._pay(move, '2025-04-02', amount=400.0)

        with self.assertRaises(UserError):
            move._l10n_ua_tax_invoice_date()

    def test_cash_method_uses_first_payment_while_split_is_unsupported(self):
        """Часткові оплати: поки що одна ПН від дати першого надходження.

        Це фіксація наявного обмеження, а не бажаної поведінки: за п. 187.10
        зобов'язання виникає на суму **кожного** надходження, тобто тут мали б
        бути дві ПН — 400 грн від 02.04 і 600 грн від 06.05. Розбиття потребує
        привʼязки ПН до погашення й розподілу сум по номенклатурі, тому
        винесене окремо (#255).
        """
        move = self._invoice(self.customer_cash, '2025-03-10')
        self._pay(move, '2025-04-02', amount=400.0)
        self._pay(move, '2025-05-06', amount=600.0)

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-04-02'))

    def test_settlement_without_payment_object_counts(self):
        """Залік кредит-ноти — теж погашення, хоч account.payment там немає."""
        move = self._invoice(self.customer_cash, '2025-03-10')
        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.customer_cash.id,
            'invoice_date': '2025-04-02',
            'date': '2025-04-02',
            'invoice_line_ids': [(0, 0, {
                'name': 'залік', 'quantity': 1, 'price_unit': 1000.0, 'tax_ids': []})],
        })
        credit_note.action_post()
        receivable = (move.line_ids | credit_note.line_ids).filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        receivable.reconcile()

        self.assertFalse(move.matched_payment_ids,
                         'у цьому сценарії платіжного документа немає — на це й тест')
        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-04-02'))

    # -------------------------------------------------- чужі й коригуючі ПН

    def test_vendor_bill_keeps_supplier_date(self):
        """Дату вхідної ПН визначає постачальник, а не наше правило визнання."""
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.customer_cash.id,
            'invoice_date': '2025-03-10',
            'date': '2025-03-10',
            'invoice_line_ids': [(0, 0, {
                'name': 'послуга', 'quantity': 1, 'price_unit': 1000.0, 'tax_ids': []})],
        })
        bill.action_post()

        # Неоплачений рахунок від контрагента на касовому методі: раніше тут
        # був UserError, тобто вже отриману ПН неможливо було завести взагалі.
        self.assertEqual(bill._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-03-10'))
        self.assertEqual(bill._l10n_ua_tax_invoice_rule(), 'document')

    def test_credit_note_uses_its_own_date(self):
        """РК складається на дату коригуючої події, а не першої події оригіналу."""
        move = self._invoice(self.customer, '2025-03-10')
        self._pay(move, '2025-03-04')  # передоплата зсунула дату оригінальної ПН
        refund = move._reverse_moves([
            {'invoice_date': '2025-05-20', 'date': '2025-05-20'}])
        refund.action_post()

        refund.action_create_tax_invoice()
        correction = refund.tax_invoice_ids

        self.assertEqual(correction.date, fields.Date.to_date('2025-05-20'))
        self.assertEqual(correction.vat_method, 'document')

    # ------------------------------------------------------------------- ПН

    def test_created_tax_invoice_records_date_and_method(self):
        """Дата ПН береться з правила визнання, а не з дня натискання кнопки."""
        move = self._invoice(self.customer_cash, '2025-03-10')
        self._pay(move, '2025-04-02')

        move.action_create_tax_invoice()
        tax_invoice = move.tax_invoice_ids

        self.assertEqual(len(tax_invoice), 1)
        self.assertEqual(tax_invoice.date, fields.Date.to_date('2025-04-02'))
        self.assertEqual(tax_invoice.vat_method, 'cash')
        self.assertNotEqual(tax_invoice.date, fields.Date.context_today(move),
                             'дата ПН не має дорівнювати сьогоднішній')

    def test_flag_is_company_dependent(self):
        """Ознака належить парі компанія-контрагент, а не контрагенту глобально."""
        other = self.env['res.company'].create({'name': 'Інша компанія'})
        self.env.user.company_ids |= other

        self.assertTrue(self.customer_cash.with_company(self.env.company).l10n_ua_vat_cash_method)
        self.assertFalse(self.customer_cash.with_company(other).l10n_ua_vat_cash_method)
