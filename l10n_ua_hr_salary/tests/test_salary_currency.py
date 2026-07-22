"""Нарахування зарплати в іноземній валюті (#206)."""

from datetime import date

from odoo.tests import tagged
from .common import SalaryTestCase


@tagged('post_install', '-at_install')
class TestSalaryCurrency(SalaryTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.psp_params.write({'min_hourly_wage': 0.0})
        cls.usd = cls.env.ref('base.USD')
        # Тип нарахування SALARY (окладна форма)
        if not cls.env['hr.accrual.type'].search([('code', '=', 'SALARY')], limit=1):
            cls.env['hr.accrual.type'].create({
                'name': 'Оклад', 'code': 'SALARY', 'category': 'wage'})

    def _payslip(self):
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'version_id': self.version.id,
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
        })
        slip.write({
            'scheduled_hours': 160.0, 'scheduled_days': 20,
            'worked_days': 20, 'worked_hours': 160.0,
        })
        return slip

    def _salary_accrual(self, slip):
        return slip.accrual_ids.filtered(
            lambda a: a.accrual_type_id.code == 'SALARY')

    def test_company_currency_rate_one(self):
        # За замовчуванням валюта окладу = валюта компанії → курс 1.0
        slip = self._payslip()
        self.assertEqual(slip.salary_currency_id, self.company.currency_id)
        self.assertAlmostEqual(slip.salary_rate, 1.0, places=6)

    def test_company_currency_no_conversion(self):
        # Оклад 25000 у валюті компанії → нарахування без перерахунку
        slip = self._payslip()
        slip._generate_accruals()
        acc = self._salary_accrual(slip)
        self.assertAlmostEqual(acc.amount, 25000.0, places=2)

    def test_foreign_wage_converted(self):
        # Оклад 1000 USD за курсом 40 → 40000 грн
        self.version.write({
            'salary_currency_id': self.usd.id, 'wage': 1000.0})
        slip = self._payslip()
        self.assertEqual(slip.salary_currency_id, self.usd)
        slip.salary_rate = 40.0
        slip._generate_accruals()
        acc = self._salary_accrual(slip)
        self.assertAlmostEqual(acc.amount, 40000.0, places=2)

    def test_foreign_wage_taxes_in_uah(self):
        # Податки рахуються від гривневого еквіваленту (gross у грн)
        self.version.write({
            'salary_currency_id': self.usd.id, 'wage': 1000.0})
        slip = self._payslip()
        slip.salary_rate = 40.0
        slip.action_compute_sheet()
        self.assertAlmostEqual(slip.gross_salary, 40000.0, places=2)
        # Військовий збір 5% від гривневого gross = 2000 (без ПСП-знижок)
        self.assertAlmostEqual(slip.military_tax_amount, 2000.0, places=2)

    def test_foreign_prorated(self):
        # Половина місяця → половина гривневого окладу
        self.version.write({
            'salary_currency_id': self.usd.id, 'wage': 1000.0})
        slip = self._payslip()
        slip.salary_rate = 40.0
        slip.write({'worked_days': 10})
        slip._generate_accruals()
        acc = self._salary_accrual(slip)
        # 1000 × 40 × 10/20 = 20000
        self.assertAlmostEqual(acc.amount, 20000.0, places=2)
