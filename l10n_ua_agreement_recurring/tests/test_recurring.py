from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.agreement import period_label


@tagged('post_install', '-at_install')
class TestRecurringInvoices(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'ТОВ Клієнт', 'is_company': True})
        cls.service = cls.env['product.product'].create({
            'name': 'Супровід Odoo', 'type': 'service', 'list_price': 10000.0,
            'standard_price': 4000.0, 'taxes_id': [(5, 0, 0)], 'supplier_taxes_id': [(5, 0, 0)]})
        cls.purchase_type = cls.env.ref('l10n_ua_agreement.agreement_type_purchase')

    def _agreement(self, **vals):
        agreement = self.env['l10n_ua.agreement'].create({
            'name': 'Абонентський супровід', 'partner_id': self.partner.id,
            'start_date': date(2026, 1, 1),
            'recurring_enabled': True, 'recurring_next_date': date(2026, 10, 1),
            'recurring_line_ids': [(0, 0, {'product_id': self.service.id, 'price_unit': 10000.0})],
            **vals})
        agreement.state = 'signed'
        return agreement

    def _invoices(self, agreement):
        return self.env['account.move'].search(
            [('l10n_ua_agreement_id', '=', agreement.id)], order='invoice_date')

    def test_period_label(self):
        self.assertEqual(period_label(date(2026, 10, 1), date(2026, 10, 31)), 'жовтень 2026')
        self.assertEqual(period_label(date(2026, 10, 1), date(2026, 12, 31)), 'IV квартал 2026')
        self.assertEqual(period_label(date(2026, 1, 1), date(2026, 12, 31)), '2026 рік')
        self.assertEqual(period_label(date(2026, 10, 15), date(2026, 11, 14)), '15.10.2026–14.11.2026')

    def test_monthly_in_advance(self):
        agreement = self._agreement()
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 15))
        invoice = self._invoices(agreement)
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.invoice_date, date(2026, 10, 1))
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.invoice_origin, agreement.code)
        self.assertEqual(invoice.invoice_line_ids.name, 'Супровід Odoo for жовтень 2026')
        self.assertEqual(invoice.amount_untaxed, 10000.0)
        self.assertEqual(agreement.recurring_next_date, date(2026, 11, 1))
        self.assertEqual(agreement.invoice_count, 1)
        # Повторний запуск того ж дня нічого не дублює.
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 15))
        self.assertEqual(len(self._invoices(agreement)), 1)

    def test_catch_up_missed_periods(self):
        agreement = self._agreement(recurring_next_date=date(2026, 8, 1))
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 1))
        self.assertEqual(self._invoices(agreement).mapped('invoice_date'),
                         [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)])

    def test_quarterly_in_arrears_with_placeholders(self):
        agreement = self._agreement(
            recurring_rule='quarterly', recurring_invoicing='post',
            recurring_line_ids=[(5, 0, 0), (0, 0, {
                'product_id': self.service.id, 'price_unit': 30000.0,
                'name': 'Супровід за #PERIOD# (#START#–#END#)'})])
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 1))
        invoice = self._invoices(agreement)
        self.assertEqual(invoice.invoice_line_ids.name,
                         'Супровід за III квартал 2026 (01.07.2026–30.09.2026)')
        self.assertEqual(agreement.recurring_next_date, date(2027, 1, 1))

    def test_stops_after_end_date(self):
        agreement = self._agreement(end_date=date(2026, 10, 31),
                                    recurring_next_date=date(2026, 10, 1))
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 12, 15))
        self.assertEqual(self._invoices(agreement).mapped('invoice_date'), [date(2026, 10, 1)])
        self.assertFalse(agreement.recurring_enabled)

    def test_unsigned_agreement_is_not_invoiced(self):
        agreement = self._agreement()
        agreement.state = 'draft'
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 15))
        self.assertFalse(self._invoices(agreement))

    def test_purchase_agreement_and_auto_post(self):
        agreement = self._agreement(agreement_type_id=self.purchase_type.id,
                                    recurring_auto_post=True)
        self.assertEqual(agreement.direction, 'purchase')
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 1))
        bill = self._invoices(agreement)
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.state, 'posted')
        self.assertIn('жовтень 2026', bill.ref)

    def test_manual_button_and_checks(self):
        agreement = self._agreement(recurring_next_date=date(2027, 1, 1))
        action = agreement.action_recurring_create_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(invoice.invoice_date, date(2027, 1, 1))
        self.assertEqual(agreement.recurring_next_date, date(2027, 2, 1))
        self.assertEqual(agreement.action_view_invoices()['domain'][0][2], agreement.id)

        empty = self._agreement(recurring_line_ids=[])
        with self.assertRaises(UserError):
            empty.action_recurring_create_invoice()

    def test_cron_failure_is_reported_not_raised(self):
        agreement = self._agreement(recurring_line_ids=[])
        self.env['l10n_ua.agreement']._cron_recurring_invoices(date(2026, 10, 15))
        self.assertIn('not created', agreement.message_ids[0].body)
