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

    def test_cash_method_takes_earliest_of_several_payments(self):
        """Часткові оплати: зобовʼязання виникає з першої."""
        move = self._invoice(self.customer_cash, '2025-03-10')
        self._pay(move, '2025-04-02', amount=400.0)
        self._pay(move, '2025-05-06', amount=600.0)

        self.assertEqual(move._l10n_ua_tax_invoice_date(), fields.Date.to_date('2025-04-02'))

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
