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

    def test_moving_the_advance_recomputes_the_amount(self):
        """Перенесення авансу на інший місяць змінює й курс.

        `gross_amount` збережене, тож без `date` у залежностях у базі лишався
        б курс дня створення — а це живі гроші на картку.
        """
        advance = self.env['hr.salary.advance'].create({
            'employee_id': self.employee.id,
            'date': date(2026, 6, 15),
            'wage_percent': 50.0,
        })
        self.assertAlmostEqual(advance.gross_amount, 22134.0, places=2)

        advance.date = date(2026, 1, 20)

        self.assertAlmostEqual(advance.gross_amount, 21176.6, places=2)

    def test_advance_run_converts_the_wage(self):
        """Пакетне нарахування має ту саму ваду й те саме лікування."""
        run = self.env['hr.salary.advance.run'].create({
            'name': 'Аванс 06/2026',
            'date': date(2026, 6, 15),
            'company_id': self.company.id,
        })

        self.assertAlmostEqual(
            run._get_employee_wage(self.employee), 44268.0, places=2)

    def test_run_skips_employees_without_a_rate_instead_of_dying(self):
        """Один працівник без курсу не має лишати без авансу всю установу.

        Пропущені не зникають мовчки: їхні імена йдуть у попередження, а
        повторний запуск підхопить їх, щойно курс внесуть.
        """
        # Період, на який курсу немає взагалі.
        run = self.env['hr.salary.advance.run'].create({
            'name': 'Аванс 12/2025',
            'date': date(2025, 12, 20),
            'company_id': self.company.id,
        })
        other = self.env['hr.employee'].create({
            'name': 'Гривневий працівник',
            'company_id': self.company.id,
        })
        other.current_version_id.write({
            'wage': 20000.0,
            'contract_date_start': date(2024, 1, 15),
        })

        result = run.action_generate_advances()

        self.assertEqual(result.get('tag'), 'display_notification',
                         'пропуск має бути видимим, а не тихим')
        self.assertIn(self.employee.name, result['params']['message'])
        paid = run.advance_ids.mapped('employee_id')
        self.assertIn(other, paid, 'решта працівників мають отримати аванс')
        self.assertNotIn(self.employee, paid)
