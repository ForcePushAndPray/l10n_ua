from datetime import date

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTariffGrade(TransactionCase):
    """Tariff grades: hourly rates of a company, for a period."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'Tariff Grade Test Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Tariff Grade Test Company B'})
        cls.Grade = cls.env['hr.tariff.grade'].with_company(cls.company)
        # New companies get the typical set; these tests build their own.
        cls.Grade.with_context(active_test=False).search(
            [('company_id', 'in', (cls.company | cls.company_b).ids)]).unlink()

    def _grades(self, rates=((1, 1.0, 100.0), (3, 1.18, 122.0)), company=None,
                date_from=date(2026, 1, 1), date_to=False):
        return self.Grade.create([{
            'name': f'Grade {grade}', 'grade': grade, 'coefficient': coef,
            'company_id': (company or self.company).id,
            'date_from': date_from, 'date_to': date_to,
            **({'hourly_rate': rate} if rate is not None else {}),
        } for grade, coef, rate in rates])

    def test_computed_rate_is_first_grade_times_coefficient(self):
        grade1, grade3 = self._grades()
        self.assertAlmostEqual(grade3.computed_rate, 118.0)
        self.assertAlmostEqual(grade3.hourly_rate, 122.0, msg='the agreed rate is kept')
        self.assertAlmostEqual(grade3.rate_diff, 4.0)
        grade1.hourly_rate = 110.0
        self.assertAlmostEqual(grade3.hourly_rate, 122.0,
                               msg='a rate agreed otherwise does not follow grade 1')
        self.assertAlmostEqual(grade3.computed_rate, 129.8)
        self.assertAlmostEqual(grade3.rate_diff, -7.8)

    def test_rate_follows_first_grade_until_set_otherwise(self):
        grade1, grade2, grade3 = self._grades(
            ((1, 1.0, 100.0), (2, 1.09, None), (3, 1.18, None)))
        self.assertAlmostEqual(grade3.hourly_rate, 118.0, msg='filled from the formula')
        grade2.hourly_rate = 110.0
        grade1.hourly_rate = 120.0
        self.assertAlmostEqual(grade3.hourly_rate, 141.6)
        self.assertAlmostEqual(grade2.hourly_rate, 110.0)
        self.assertAlmostEqual(grade3.rate_diff, 0.0)
        self.assertAlmostEqual(grade2.rate_diff, -20.8)

    def test_difference_of_a_kopiyka_shows(self):
        grade3 = self._grades(((1, 1.0, 100.0), (3, 1.18, 118.01)))[1]
        self.assertAlmostEqual(grade3.rate_diff, 0.01)
        grade3.hourly_rate = 118.0
        self.assertEqual(grade3.rate_diff, 0.0)

    def test_rate_in_force_on_date(self):
        old3 = self._grades(date_to=date(2026, 6, 30))[1]
        new3 = self._grades(((1, 1.0, 120.0), (3, 1.18, 141.6)),
                            date_from=date(2026, 7, 1))[1]
        self.assertEqual(old3._l10n_ua_grade_on(date(2026, 3, 31)), old3)
        self.assertEqual(old3._l10n_ua_grade_on(date(2026, 7, 31)), new3)
        self.assertEqual(new3._l10n_ua_grade_on(date(2026, 3, 31)), old3)
        self.assertFalse(old3._l10n_ua_grade_on(date(2025, 12, 31)))

    def test_periods_of_one_grade_do_not_overlap(self):
        self._grades(date_to=date(2026, 6, 30))
        with self.assertRaises(ValidationError):
            self._grades(((3, 1.18, 130.0),), date_from=date(2026, 6, 1))
        # Another company may share the dates.
        self._grades(company=self.company_b, date_from=date(2026, 6, 1))

    def test_companies_are_independent(self):
        grades_a = self._grades()
        grades_b = self._grades(company=self.company_b)
        officer = self.env['res.users'].create({
            'name': 'Tariff officer', 'login': 'tariff_grade_test_officer',
            'company_id': self.company_b.id,
            'company_ids': [(6, 0, (self.company | self.company_b).ids)],
            'group_ids': [(6, 0, [self.env.ref('hr.group_hr_user').id])],
        })
        visible = self.env['hr.tariff.grade'].with_user(officer).with_context(
            allowed_company_ids=[self.company_b.id]).search(
            [('id', 'in', (grades_a | grades_b).ids)])
        self.assertEqual(visible, grades_b)

    def test_rate_below_subsistence_minimum_is_refused(self):
        if 'hr.psp.parameters' not in self.env:
            self.skipTest('l10n_ua_hr_salary is not installed')
        self.env['hr.psp.parameters'].create({
            'year': 2030, 'date_from': date(2030, 1, 1),
            'subsistence_minimum': 4000.0, 'min_wage': 9000.0,
            'company_id': self.company.id,
        })
        # January 2030: 23 weekdays × 8 h = 184 h; 20 × 184 = 3 680 < 4 000.
        with self.assertRaises(ValidationError):
            self._grades(((1, 1.0, 20.0),), date_from=date(2030, 1, 1))
        # A zero rate is one not entered yet.
        self._grades(((1, 1.0, 0.0),), date_from=date(2030, 1, 1))

    def test_job_uses_grades_of_its_own_company(self):
        grade_a = self._grades()[1]
        grade_b = self._grades(company=self.company_b)[1]
        job = self.env['hr.job'].create({
            'name': 'Turner', 'company_id': self.company.id,
            'tariff_grade_id': grade_a.id,
        })
        with self.assertRaises(UserError):
            job.tariff_grade_id = grade_b
        with Form(job) as form:
            form.company_id = self.company_b
            self.assertFalse(form.tariff_grade_id,
                             'a grade of the old company is cleared')

    def test_new_company_gets_the_typical_grades(self):
        company = self.env['res.company'].create({'name': 'Tariff Grade Test Company C'})
        grades = self.env['hr.tariff.grade'].search([('company_id', '=', company.id)])
        templates = self.env['hr.tariff.grade.template'].search([])
        self.assertEqual(sorted(grades.mapped(lambda g: (g.grade, g.coefficient))),
                         sorted(templates.mapped(lambda t: (t.grade, t.coefficient))))
        self.assertFalse(any(grades.mapped('hourly_rate')))
        year = fields.Date.context_today(self.env.user).year
        self.assertEqual(set(grades.mapped('date_from')), {date(year, 1, 1)})
        self.env['hr.tariff.grade']._seed_company_grades()
        self.assertEqual(self.env['hr.tariff.grade'].search_count(
            [('company_id', '=', company.id)]), len(templates))
        grades.filtered(lambda g: g.grade == 1).hourly_rate = 103.66
        self.assertAlmostEqual(grades.filtered(lambda g: g.grade == 2).hourly_rate,
                               112.99, msg='the first-grade rate fills the others')
