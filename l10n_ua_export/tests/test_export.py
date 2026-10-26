from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestExport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.l10n_ua_is_vat_payer = True
        cls.eur = cls.env.ref('base.EUR')
        cls.eur.active = True
        Rate = cls.env['res.currency.rate']
        Rate.search([('currency_id', '=', cls.eur.id), ('company_id', 'in', (cls.company.id, False))]).unlink()
        for day, rate in ((date(2026, 9, 1), 45.0), (date(2026, 9, 3), 46.0)):
            Rate.create({'currency_id': cls.eur.id, 'name': day, 'rate': 1.0 / rate, 'company_id': cls.company.id})
        cls.buyer = cls.env['res.partner'].create({
            'name': 'Kürbis Trading GmbH (test)', 'is_company': True, 'country_id': cls.env.ref('base.at').id,
            'vat': 'ATU12345678'})
        # договір веде відділ продажів
        cls.env.user.sudo().group_ids |= cls.env.ref('sales_team.group_sale_salesman_all_leads')
        cls.contract = cls.env['l10n_ua.agreement'].create({
            'code': 'EXP-1/2026', 'name': 'Export contract', 'direction': 'sale', 'partner_id': cls.buyer.id,
            'currency_id': cls.eur.id, 'l10n_ua_foreign_trade': True, 'l10n_ua_settlement_days': 180,
            'l10n_ua_incoterm_id': cls.env.ref('account.incoterm_FCA').id, 'l10n_ua_incoterm_place': 'Dubno'})
        cls.seeds = cls.env['product.product'].create({
            'name': 'Pumpkin seeds GWS (test)', 'type': 'consu', 'uktzed_code': '1207709100',
            'uom_id': cls.env.ref('uom.product_uom_kgm').id, 'weight': 1.0, 'taxes_id': [(6, 0, [])]})

    def _invoice(self, invoice_date=date(2026, 9, 1)):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.buyer.id, 'currency_id': self.eur.id,
            'invoice_date': invoice_date, 'date': invoice_date, 'l10n_ua_agreement_id': self.contract.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.seeds.id, 'quantity': 4000.0, 'price_unit': 2.5,
                                         'tax_ids': [(6, 0, [])]})]})
        move.action_post()
        return move

    def _declaration(self, invoice, clearance=date(2026, 9, 3)):
        declaration = self.env['l10n_ua.customs.declaration'].create({
            'name': 'UA500020/2026/%06d' % invoice.id, 'date': clearance, 'partner_id': self.buyer.id,
            'agreement_id': self.contract.id, 'invoice_ids': [(6, 0, invoice.ids)], 'customs_value': 460000.0})
        declaration.action_confirm()
        return declaration

    def test_tax_invoice_zero_rate_at_customs_rate(self):
        invoice = self._invoice()
        declaration = self._declaration(invoice)
        self.assertEqual(declaration.currency_id, self.eur)
        self.assertEqual(declaration.amount_total, 10000.0)
        declaration.action_create_tax_invoice()
        tax_invoice = declaration.tax_invoice_id
        self.assertEqual(tax_invoice.date, date(2026, 9, 3))             # дата МД — перша подія
        self.assertEqual(tax_invoice.non_payer_reason, '07')
        self.assertEqual(tax_invoice.line_ids.vat_rate, '0')
        self.assertAlmostEqual(tax_invoice.total_base, 460000.0, places=2)  # 10 000 € × 46,00
        self.assertEqual(tax_invoice.total_vat, 0.0)
        self.assertEqual(tax_invoice.line_ids.uktzed_code, '1207709100')
        with self.assertRaises(UserError):
            declaration.action_create_tax_invoice()

    def test_currency_control_states(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice()
        declaration = self._declaration(invoice)
        self.assertEqual(declaration.settlement_deadline, date(2026, 9, 3) + timedelta(days=180))
        overdue = self._declaration(self._invoice(), clearance=today - timedelta(days=200))
        due_soon = self._declaration(self._invoice(), clearance=today - timedelta(days=170))
        self.assertEqual(overdue.settlement_state, 'overdue')
        self.assertEqual(due_soon.settlement_state, 'due_soon')
        self.env['l10n_ua.customs.declaration']._cron_settlement_reminder()
        self.assertTrue(overdue.activity_ids)
        self.assertTrue(due_soon.reminder_sent)
        # оплата покупця — розрахунки завершено
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({
                'payment_date': date(2026, 10, 1)})._create_payments()
        self.assertEqual(declaration.amount_residual, 0.0)
        self.assertEqual(declaration.settlement_state, 'settled')

    def test_reports_render(self):
        invoice = self._invoice()
        declaration = self._declaration(invoice)
        Report = self.env['ir.actions.report']
        html, _fmt = Report._render_qweb_html('l10n_ua_export.action_report_commercial_invoice', invoice.ids)
        self.assertIn(b'COMMERCIAL INVOICE', html)
        self.assertIn('Kürbis Trading'.encode(), html)
        self.assertIn(b'FCA', html)
        html, _fmt = Report._render_qweb_html('l10n_ua_export.action_report_packing_list', declaration.ids)
        self.assertIn(b'PACKING LIST', html)

    def test_cancel_registered_tax_invoice(self):
        declaration = self._declaration(self._invoice())
        declaration.action_create_tax_invoice()
        declaration.tax_invoice_id.state = 'registered'
        with self.assertRaises(UserError):
            declaration.action_cancel()
