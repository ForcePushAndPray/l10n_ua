"""Аванс за валютним окладом — у гривні, а не числом із договору.

Найдорожче місце з усіх, де оклад читався напряму: аванс не рахується від
розрахункового листка, а береться відсотком від окладу — і йде живими
грошима на картку. Оклад 1000 USD давав аванс 500 грн замість 22 134.
"""
from datetime import date

from odoo.tests import tagged

from .common import SalaryTestCase


@tagged('post_install', '-at_install')
class TestAdvanceCurrency(SalaryTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usd = cls.env.ref('base.USD')
        cls.env['res.currency.rate'].create([
            {'name': '2026-01-01', 'currency_id': cls.usd.id,
             'company_id': cls.company.id, 'inverse_company_rate': 42.3532},
            {'name': '2026-06-01', 'currency_id': cls.usd.id,
             'company_id': cls.company.id, 'inverse_company_rate': 44.2680},
        ])
        cls.version.write({'salary_currency_id': cls.usd.id, 'wage': 1000.0})

    def test_advance_converts_the_wage(self):
        advance = self.env['hr.salary.advance'].create({
            'employee_id': self.employee.id,
            'date': date(2026, 6, 15),
            'wage_percent': 50.0,
        })

        # 1000 USD × 44.2680 × 50% = 22 134 грн; без перерахунку було б 500.
        self.assertAlmostEqual(advance.gross_amount, 22134.0, places=2)

    def test_advance_uses_the_rate_of_its_own_date(self):
        """Аванс січня і аванс червня рахуються за різними курсами."""
        january = self.env['hr.salary.advance'].create({
            'employee_id': self.employee.id,
            'date': date(2026, 1, 20),
            'wage_percent': 50.0,
        })

        self.assertAlmostEqual(january.gross_amount, 21176.6, places=2)

    def test_advance_run_converts_the_wage(self):
        """Пакетне нарахування має ту саму ваду й те саме лікування."""
        run = self.env['hr.salary.advance.run'].create({
            'name': 'Аванс 06/2026',
            'date': date(2026, 6, 15),
            'company_id': self.company.id,
        })

        self.assertAlmostEqual(
            run._get_employee_wage(self.employee), 44268.0, places=2)
