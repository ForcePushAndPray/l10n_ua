from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import AgroLandTestCase


@tagged('post_install', '-at_install')
class TestAgroLand(AgroLandTestCase):

    def test_cadastral_number_format(self):
        with self.assertRaises(ValidationError):
            self.env['l10n_ua.agro.land.plot'].create({
                'cadastral_number': '5621684800-01-001-0104', 'area': 1.0})

    def test_lease_rent_and_end_date(self):
        lease = self._lease(self.lessor, self.plot1)
        self.assertEqual(lease.annual_rent, 9600.0)  # 12 % від 80 000
        self.assertEqual(lease.date_end, date(2104, 12, 31))
        self.assertEqual(self.plot1.lease_ids, lease)
        self.assertTrue(lease.lessor_is_individual)

    def test_plot_cannot_be_leased_twice(self):
        self._lease(self.lessor, self.plot1)
        with self.assertRaises(ValidationError):
            self._lease(self.lessor2, self.plot1, date_start=date(2100, 1, 1))
        # після закінчення першого договору — можна
        self._lease(self.lessor2, self.plot1, date_start=date(2105, 1, 1))

    def test_accrual_withholds_taxes_for_individuals(self):
        self._lease(self.lessor, self.plot1)                          # 9 600
        self._lease(self.lessor_company, self.plot3, percent=10.0)    # 30 000, без утримань
        accrual = self._accrual()
        self.assertEqual(len(accrual.line_ids), 2)
        person = accrual.line_ids.filtered(lambda l: l.lessor_id == self.lessor)
        self.assertEqual(person.amount, 9600.0)
        self.assertEqual(person.pdfo_amount, 1728.0)      # 18 %
        self.assertEqual(person.military_amount, 480.0)   # 5 %
        self.assertEqual(person.net_amount, 7392.0)
        self.assertEqual(person.katottg, 'UA56040170010076211')
        company_line = accrual.line_ids - person
        self.assertEqual(company_line.pdfo_amount, 0.0)
        self.assertEqual(company_line.net_amount, 30000.0)

        accrual.action_post()
        move = accrual.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(sum(move.line_ids.filtered(
            lambda l: l.account_id == self.acc_23).mapped('debit')), 39600.0)
        self.assertEqual(sum(move.line_ids.filtered(
            lambda l: l.account_id == self.acc_6411).mapped('credit')), 1728.0)
        self.assertEqual(sum(move.line_ids.filtered(
            lambda l: l.account_id == self.acc_642).mapped('credit')), 480.0)
        self.assertEqual(sum(move.line_ids.filtered(
            lambda l: l.account_id == self.acc_685).mapped('credit')), 37392.0)
        self.assertEqual(accrual.amount_residual, 37392.0)

    def test_accrual_prorated_by_days(self):
        # договір з 1 липня: за 2095 рік — 184 дні з 365
        self._lease(self.lessor, self.plot1, date_start=date(2095, 7, 1))
        accrual = self._accrual(date(2095, 1, 1), date(2095, 12, 31))
        self.assertEqual(accrual.line_ids.amount, round(9600.0 * 184 / 365, 2))

    def test_money_payment_reconciles(self):
        self._lease(self.lessor, self.plot1)
        accrual = self._accrual()
        accrual.action_post()
        payment = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 12, 31), 'payment_form': 'money', 'journal_id': self.cash.id,
            'accrual_id': accrual.id})
        payment.action_fill()
        self.assertEqual(payment.amount_total, 7392.0)
        payment.line_ids.amount = 5000.0
        payment.action_post()
        line = accrual.line_ids
        self.assertEqual(line.paid_amount, 5000.0)
        self.assertEqual(line.residual, 2392.0)
        self.assertEqual(self.lessor.l10n_ua_agro_lease_count, 1)

        overpay = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 12, 31), 'payment_form': 'money', 'journal_id': self.cash.id,
            'line_ids': [(0, 0, {'accrual_line_id': line.id, 'amount': 3000.0})]})
        with self.assertRaises(ValidationError):
            overpay.action_post()

        payment.action_cancel()
        self.assertEqual(line.residual, 7392.0)
        self.assertEqual(payment.move_id.state, 'cancel')

    def test_in_kind_payment_creates_delivery(self):
        wheat = self.env['product.product'].create({
            'name': 'Пшениця 3 клас (тест)', 'is_storable': True,
            'uom_id': self.env.ref('uom.product_uom_kgm').id})
        self._lease(self.lessor, self.plot1, payment_form='in_kind', in_kind_product_id=wheat.id)
        self._lease(self.lessor2, self.plot2, payment_form='in_kind', in_kind_product_id=wheat.id)
        accrual = self._accrual()
        accrual.action_post()
        payment = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 12, 31), 'payment_form': 'in_kind', 'journal_id': self.journal.id,
            'product_id': wheat.id, 'price_unit': 8.0})
        payment.action_fill()
        payment.action_post()
        # 7 392 / 8 = 924 кг; 9 240 / 8 = 1 155 кг
        self.assertEqual(len(payment.picking_ids), 2)
        picking = payment.picking_ids.filtered(lambda p: p.partner_id == self.lessor)
        self.assertEqual(picking.move_ids.product_uom_qty, 924.0)
        self.assertEqual(payment.quantity_total, 2079.0)
        self.assertEqual(picking.state, 'confirmed')
        self.assertEqual(sum(payment.move_id.line_ids.filtered(
            lambda l: l.account_id == self.acc_712).mapped('credit')), 16632.0)
        self.assertFalse(accrual.line_ids.filtered('residual'))

    def test_cannot_cancel_paid_accrual(self):
        self._lease(self.lessor, self.plot1)
        accrual = self._accrual()
        accrual.action_post()
        payment = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 12, 31), 'payment_form': 'money', 'journal_id': self.cash.id})
        payment.action_fill()
        payment.action_post()
        with self.assertRaises(UserError):
            accrual.action_cancel()

    def test_expiry_cron(self):
        today = fields.Date.context_today(self.env['l10n_ua.agro.land.lease'])
        expiring = self._lease(self.lessor, self.plot1,
                               date_start=today - relativedelta(years=10) + relativedelta(days=30))
        expired = self._lease(self.lessor2, self.plot2,
                              date_start=today - relativedelta(years=10, days=5))
        self.env['l10n_ua.agro.land.lease']._cron_check_expiry()
        self.assertEqual(expired.state, 'expired')
        self.assertEqual(expiring.state, 'active')
        self.assertTrue(expiring.expiry_notified)
        self.assertEqual(len(expiring.activity_ids), 1)
        # повторний запуск не дублює нагадування
        self.env['l10n_ua.agro.land.lease']._cron_check_expiry()
        self.assertEqual(len(expiring.activity_ids), 1)
        self.assertEqual(self.plot1.use_state, 'leased')
        self.assertEqual(self.plot2.use_state, 'free')
        self.assertIn(self.plot2, self.env['l10n_ua.agro.land.plot'].search(
            [('use_state', '=', 'free')]))
