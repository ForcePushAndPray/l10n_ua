from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_ua_agro_land.tests.common import AgroLandTestCase


@tagged('post_install', '-at_install')
class TestLandRent4DF(AgroLandTestCase):

    def _report(self, quarter='4'):
        return self.env['l10n_ua.tax.4df'].create({
            'year': 2096, 'quarter': quarter, 'company_id': self.company.id})

    def test_rent_in_4df_with_code_106(self):
        self._lease(self.lessor, self.plot1)                        # 9 600
        self._lease(self.lessor_company, self.plot3, percent=10.0)  # юрособа — не в 4ДФ
        accrual = self._accrual(date(2096, 1, 1), date(2096, 12, 31))
        accrual.action_post()
        payment = self.env['l10n_ua.agro.rent.payment'].create({
            'date': date(2096, 11, 15), 'payment_form': 'money', 'journal_id': self.cash.id,
            'accrual_id': accrual.id})
        payment.action_fill()
        payment.line_ids.filtered(lambda l: l.lessor_id == self.lessor).amount = 3696.0
        payment.line_ids.filtered(lambda l: l.lessor_id != self.lessor).unlink()
        payment.action_post()

        report = self._report()
        report.action_generate()
        line = report.line_4df_ids.filtered(lambda l: l.partner_id == self.lessor)
        self.assertEqual(len(report.line_4df_ids.filtered('partner_id')), 1)
        self.assertEqual(line.income_type, '106')
        self.assertEqual(line.rnokpp, '3124567896')
        self.assertEqual(line.accrued_amount, 9600.0)
        self.assertEqual(line.paid_amount, 4800.0)   # половина «на руки» → половина доходу
        self.assertEqual(line.pdfo_amount, 1728.0)
        self.assertEqual(line.military_amount, 480.0)
        self.assertEqual(report.total_employees, 1)

        # інший квартал — нічого
        other = self._report('2')
        other.action_generate()
        self.assertFalse(other.line_4df_ids.filtered('partner_id'))

    def test_missing_rnokpp(self):
        self.lessor.ipn = False
        self._lease(self.lessor, self.plot1)
        accrual = self._accrual(date(2096, 1, 1), date(2096, 12, 31))
        accrual.action_post()
        with self.assertRaises(UserError):
            self._report().action_generate()
