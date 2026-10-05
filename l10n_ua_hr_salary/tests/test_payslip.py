"""Tests for payslip — HR-14,15,16,25,29 from HR_UKRAINE.md.

Tests cover:
- Payslip creation in draft state
- Gross salary computation from accruals
- PDFO (18%) calculation
- Military tax (5%) calculation
- ESV (22%) calculation
- Net salary computation
- State workflow
"""

from datetime import date
from odoo.exceptions import UserError
from odoo.tests import tagged
from .common import SalaryTestCase


@tagged('post_install', '-at_install')
class TestPayslip(SalaryTestCase):
    """Test hr.payslip model."""

    def _create_payslip(self, **kwargs):
        vals = {
            'employee_id': self.employee.id,
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
            'company_id': self.company.id,
        }
        vals.update(kwargs)
        return self.env['hr.payslip'].create(vals)

    def _create_payslip_with_accrual(self, amount=25000, **kwargs):
        """Create payslip and add a wage accrual line."""
        payslip = self._create_payslip(**kwargs)
        self.env['hr.payslip.accrual'].create({
            'payslip_id': payslip.id,
            'accrual_type_id': self.accrual_wage.id,
            'quantity': 1,
            'rate': amount,
            'amount': amount,
        })
        return payslip

    def test_payslip_creation(self):
        """Payslip should be created in draft state."""
        payslip = self._create_payslip()
        self.assertEqual(payslip.state, 'draft')

    def test_payslip_gross_salary(self):
        """Gross salary = sum of accrual amounts."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.gross_salary, 25000)

    def test_payslip_compute_pdfo(self):
        """PDFO rate should be 18%."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        self.assertEqual(payslip.pdfo_rate, 18)
        self.assertGreater(payslip.pdfo_amount, 0)

    def test_payslip_compute_military_tax(self):
        """Military tax rate should be 5%."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        self.assertEqual(payslip.military_tax_rate, 5)
        self.assertGreater(payslip.military_tax_amount, 0)

    def test_payslip_compute_esv(self):
        """ESV rate should be 22%."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        self.assertEqual(payslip.esv_rate, 22)
        self.assertGreater(payslip.esv_amount, 0)

    def test_payslip_net_salary(self):
        """Net should be less than gross."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        self.assertGreater(payslip.net_salary, 0)
        self.assertLess(payslip.net_salary, 25000)

    def test_manual_wage_not_doubled_on_compute(self):
        """A hand-entered SALARY accrual must not be doubled by _generate_accruals — issue #185."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        salary_lines = payslip.accrual_ids.filtered(
            lambda a: a.accrual_type_id == self.accrual_wage)
        self.assertEqual(len(salary_lines), 1,
                         'Base wage must appear exactly once, not manual + auto')
        self.assertEqual(payslip.gross_salary, 25000)

    def test_work_rate_proportional_salary(self):
        """work_rate масштабує базовий оклад: 0.5 ставки → половина (#149)."""
        self.version.work_rate = 1.0
        payslip = self._create_payslip()
        payslip.action_compute_sheet()
        full = sum(payslip.accrual_ids.filtered(
            lambda a: a.is_auto_generated and a.accrual_type_id == self.accrual_wage
        ).mapped('amount'))
        self.assertGreater(full, 0, 'Auto base wage expected at full rate')

        self.version.work_rate = 0.5
        payslip.action_compute_sheet()
        half = sum(payslip.accrual_ids.filtered(
            lambda a: a.is_auto_generated and a.accrual_type_id == self.accrual_wage
        ).mapped('amount'))
        self.assertAlmostEqual(half, full * 0.5, places=2)

    def test_payslip_state_verify(self):
        """After compute, state should be verify or remain draft."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        # Some implementations stay in draft after compute
        self.assertIn(payslip.state, ('draft', 'verify'))

    def test_payslip_state_done(self):
        """Done action should set state to done."""
        payslip = self._create_payslip_with_accrual(25000)
        payslip.action_compute_sheet()
        if payslip.state == 'draft':
            payslip.action_payslip_verify()
        payslip.action_payslip_done()
        self.assertEqual(payslip.state, 'done')

    def test_payslip_cancel(self):
        """Cancel should set state to cancel."""
        payslip = self._create_payslip()
        payslip.action_payslip_cancel()
        self.assertEqual(payslip.state, 'cancel')

    def test_payslip_draft_reset(self):
        """Draft reset from cancel."""
        payslip = self._create_payslip()
        payslip.action_payslip_cancel()
        payslip.action_payslip_draft()
        self.assertEqual(payslip.state, 'draft')

    def test_generate_accruals(self):
        """_generate_accruals should create accrual from version wage."""
        payslip = self._create_payslip()
        payslip._compute_working_days()
        payslip._generate_accruals()
        self.assertTrue(payslip.accrual_ids)


@tagged('post_install', '-at_install')
class TestPayslipPSPIntegration(TestPayslip):
    """#96 — ПСП integration з полями hr.employee per ПК ст. 169.

    Reuses TestPayslip's `_create_payslip_with_accrual` helper.
    """

    def test_psp_disability_group_1_gets_200(self):
        """Disability group I → ПСП 200% (ПК 169.1.4 «б»)."""
        self.employee.disability_group = '1'
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '200')

    def test_psp_disability_group_2_gets_150(self):
        """Disability group II → ПСП 150% (ПК 169.1.3 «б»)."""
        self.employee.disability_group = '2'
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '150')

    def test_psp_chornobyl_1_gets_200(self):
        """Chornobyl categories 1-2 → ПСП 200% (ПК 169.1.4 «д»)."""
        self.employee.chornobyl_category = '1'
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '200')

    def test_psp_chornobyl_3_gets_150(self):
        """Chornobyl categories 3-4 → ПСП 150%."""
        self.employee.chornobyl_category = '3'
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '150')

    def test_psp_combat_veteran_gets_200(self):
        """Combat veteran → ПСП 200% (ПК 169.1.4 «ж»)."""
        self.employee.veteran_status = 'combat'
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '200')

    def test_psp_single_parent_with_dependent_gets_150(self):
        """Single parent з утриманцем → ПСП 150% (ПК 169.1.3 «а»)."""
        self.employee.is_single_parent = True
        # Create a dependent child
        self.env['hr.employee.child'].create({
            'name': 'Дитина 1',
            'birthday': date(2018, 5, 1),
            'employee_id': self.employee.id,
        })
        self.employee.invalidate_recordset()
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '150')

    def test_psp_priority_200_over_150(self):
        """Якщо одночасно інвалідність I + одинокий батько → 200% (higher wins)."""
        self.employee.disability_group = '1'
        self.employee.is_single_parent = True
        self.env['hr.employee.child'].create({
            'name': 'Дитина 1',
            'birthday': date(2018, 5, 1),
            'employee_id': self.employee.id,
        })
        self.employee.invalidate_recordset()
        payslip = self._create_payslip_with_accrual(5000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, '200')

    def test_psp_no_benefits_gets_standard(self):
        """Без особливих пільг → ПСП standard (зважаючи на income_limit)."""
        payslip = self._create_payslip_with_accrual(3000)
        payslip.invalidate_recordset()
        self.assertEqual(payslip.psp_type, 'standard')

    def test_psp_amount_for_multi_child_family(self):
        """Сім'я з 2+ дітей → ПСП × N і вищий income_limit (ПК 169.4.1 «в»)."""
        # Drive PSP amounts via subsistence_minimum (compute-stored values)
        # subsistence=3000 → psp_standard=1500, income_limit=4200 (× 3 дітей = 12600)
        self.psp_params.write({'subsistence_minimum': 3000})
        # 3 children
        for i in range(3):
            self.env['hr.employee.child'].create({
                'name': f'Дитина {i + 1}',
                'birthday': date(2018 + i, 5, 1),
                'employee_id': self.employee.id,
            })
        self.employee.invalidate_recordset()
        payslip = self._create_payslip_with_accrual(8000)
        payslip.invalidate_recordset()
        self.assertTrue(payslip.psp_eligible)
        # amount = standard × N children = 1500 × 3 = 4500
        self.assertEqual(payslip.psp_amount, 4500)


@tagged('post_install', '-at_install')
class TestPayslipMultiCompany(SalaryTestCase):
    """Multi-company isolation для hr.payslip."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})
        cls.employee_b = cls.env['hr.employee'].create({
            'name': 'Emp B', 'company_id': cls.company_b.id,
        })

    def test_onchange_company_resets_cross_company_employee(self):
        payslip = self.env['hr.payslip'].new({
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
        })
        payslip.company_id = self.company_b
        payslip._onchange_company_id()
        self.assertFalse(payslip.employee_id)

    def test_onchange_company_keeps_same_company_employee(self):
        payslip = self.env['hr.payslip'].new({
            'company_id': self.company.id,
            'employee_id': self.employee.id,
            'date_from': date(2026, 4, 1),
            'date_to': date(2026, 4, 30),
        })
        # та сама компанія — нічого не скидається
        payslip._onchange_company_id()
        self.assertEqual(payslip.employee_id, self.employee)


@tagged('post_install', '-at_install')
class TestPayslipTariffGrade(SalaryTestCase):
    """Payroll on tariff grades: the hourly rate in force, as agreed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # No statutory floor, so the accrual shows the tariff rate itself.
        cls.psp_params.write({'min_hourly_wage': 0.0})
        cls.salary_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'SALARY')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Salary', 'code': 'SALARY', 'category': 'wage'})
        # Two periods in 2025. Whatever the company already has for grade 6 —
        # the typical set of a fresh database or the grades a migration gave
        # it — is closed before them, so the periods do not overlap.
        Grade = cls.env['hr.tariff.grade']
        Grade.search([
            ('company_id', '=', cls.company.id), ('grade', '=', 6),
        ]).action_archive()
        common = {'name': 'Grade 6', 'grade': 6, 'coefficient': 1.45,
                  'company_id': cls.company.id}
        cls.grade6 = Grade.create(dict(common, hourly_rate=196.02,
                                       date_from=date(2025, 1, 1),
                                       date_to=date(2025, 6, 30)))
        Grade.create(dict(common, hourly_rate=174.0, date_from=date(2025, 7, 1),
                          date_to=date(2025, 12, 31)))
        cls.version.tariff_grade_id = cls.grade6

    def _salary(self, month):
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id, 'version_id': self.version.id,
            'date_from': date(2025, month, 1), 'date_to': date(2025, month, 28),
        })
        slip.write({'scheduled_hours': 160.0, 'scheduled_days': 20,
                    'worked_days': 20, 'worked_hours': 160.0})
        slip._generate_accruals()
        return slip.accrual_ids.filtered(
            lambda a: a.accrual_type_id == self.salary_type)

    def test_grade_rate_is_paid_without_coefficient(self):
        # 196.02 is the agreed rate of grade 6; the progression is already in
        # it, so it is not multiplied by 1.45 again.
        salary = self._salary(6)
        self.assertAlmostEqual(salary.rate, 196.02, places=2)
        self.assertAlmostEqual(salary.amount, 196.02 * 160, places=2)

    def test_rate_of_the_period_is_used(self):
        # The version still points at the grade of the first half-year.
        self.assertAlmostEqual(self._salary(8).rate, 174.0, places=2)

    def test_no_rate_in_force_stops_payroll(self):
        self.grade6.hourly_rate = 0.0
        with self.assertRaises(UserError):
            self._salary(6)
        self.grade6.hourly_rate = 196.02
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id, 'version_id': self.version.id,
            'date_from': date(2024, 12, 1), 'date_to': date(2024, 12, 31),
        })
        slip.write({'scheduled_hours': 160.0, 'worked_hours': 160.0})
        with self.assertRaises(UserError):
            slip._generate_accruals()


@tagged('post_install', '-at_install')
class TestPayslipTaxRates(SalaryTestCase):
    """Tax rates come from the payroll parameters of the payslip's company."""

    def _payslip(self, **values):
        vals = {
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
        }
        vals.update(values)
        return self.env['hr.payslip'].create(vals)

    def test_rates_come_from_company_parameters(self):
        self.psp_params.write({
            'pdfo_rate': 17.0, 'military_tax_rate': 4.0, 'esv_rate': 21.0})
        payslip = self._payslip()
        self.assertAlmostEqual(payslip.pdfo_rate, 17.0)
        self.assertAlmostEqual(payslip.military_tax_rate, 4.0)
        self.assertAlmostEqual(payslip.esv_rate, 21.0)

    def test_closed_payslip_keeps_its_rates(self):
        payslip = self._payslip()
        payslip.action_compute_sheet()
        payslip.action_payslip_verify()
        rate = payslip.pdfo_rate
        self.psp_params.pdfo_rate = 10.0
        payslip.date_to = date(2025, 6, 29)
        self.assertAlmostEqual(payslip.pdfo_rate, rate)

    def test_period_without_parameters_leaves_rates_at_zero(self):
        payslip = self._payslip(
            date_from=date(2020, 6, 1), date_to=date(2020, 6, 30))
        self.assertAlmostEqual(payslip.pdfo_rate, 0.0)
        with self.assertRaises(UserError):
            payslip.action_payslip_verify()


@tagged('post_install', '-at_install')
class TestPayslipSegments(SalaryTestCase):
    """A month is paid by the day: by the version, the rate and the salary
    in force on it.

    July 2025 has 23 working days: 11 of them fall on 1–15 and 12 on 16–31.
    At the daily norm of 8 hours that is 88 and 96 hours, and 184 together.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.psp_params.write({'min_hourly_wage': 0.0})
        cls.salary_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'SALARY')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Salary', 'code': 'SALARY', 'category': 'wage'})
        cls.night_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'NIGHT')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Night', 'code': 'NIGHT', 'category': 'surcharge'})
        cls.allowance_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'ALLOWANCE')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Allowance', 'code': 'ALLOWANCE', 'category': 'wage'})
        Grade = cls.env['hr.tariff.grade']
        Grade.search([
            ('company_id', '=', cls.company.id), ('grade', 'in', (9, 11)),
        ]).action_archive()
        common = {'coefficient': 1.73, 'company_id': cls.company.id}
        cls.before = Grade.create(dict(
            common, name='Grade 9', grade=9, hourly_rate=100.0,
            date_from=date(2025, 1, 1), date_to=date(2025, 7, 15)))
        cls.after = Grade.create(dict(
            common, name='Grade 9', grade=9, hourly_rate=120.0,
            date_from=date(2025, 7, 16)))
        cls.other_grade = Grade.create(dict(
            common, name='Grade 11', grade=11, hourly_rate=150.0,
            date_from=date(2025, 1, 1)))

    def _payslip(self, **values):
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': date(2025, 7, 1), 'date_to': date(2025, 7, 31),
        })
        slip.write(dict({'scheduled_hours': 184.0, 'scheduled_days': 23,
                         'worked_days': 23, 'worked_hours': 184.0}, **values))
        return slip

    def _second_version(self, **values):
        """A version starting on 16 July, so the month falls in two.

        Carries the wage of the first one unless told otherwise: Odoo writes
        a new version by copying the current one.
        """
        return self.env['hr.version'].create(dict({
            'employee_id': self.employee.id,
            'contract_date_start': date(2024, 1, 15),
            'date_version': date(2025, 7, 16),
            'company_id': self.company.id,
            'wage': self.version.wage,
        }, **values))

    def _lines(self, slip, accrual_type=None):
        slip._generate_accruals()
        return slip.accrual_ids.filtered(
            lambda a: a.accrual_type_id == (accrual_type or self.salary_type)
        ).sorted('id')

    # --- the tariff rate changes, the version does not ---

    def test_rate_change_inside_the_month_is_paid_by_the_day(self):
        self.version.tariff_grade_id = self.before
        lines = self._lines(self._payslip())
        self.assertEqual(len(lines), 2, 'one line for each rate')
        self.assertAlmostEqual(lines[0].quantity, 88.0, places=2)
        self.assertAlmostEqual(lines[0].rate, 100.0, places=2)
        self.assertAlmostEqual(lines[0].amount, 8800.0, places=2)
        self.assertAlmostEqual(lines[1].quantity, 96.0, places=2)
        self.assertAlmostEqual(lines[1].rate, 120.0, places=2)
        self.assertAlmostEqual(lines[1].amount, 11520.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped('quantity')), 184.0, places=2,
                               msg='no hour is paid twice or lost')

    def test_a_month_in_one_period_is_paid_on_one_line(self):
        self.version.tariff_grade_id = self.other_grade
        lines = self._lines(self._payslip())
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.amount, 184.0 * 150.0, places=2)
        self.assertNotIn('–', lines.notes, 'no dates when nothing changed')

    def test_hours_entered_by_hand_are_not_split(self):
        self.version.tariff_grade_id = self.before
        lines = self._lines(self._payslip(worked_hours=170.0))
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.rate, 120.0, places=2)
        self.assertAlmostEqual(lines.amount, 170.0 * 120.0, places=2)

    def test_a_worked_day_without_a_rate_stops_payroll(self):
        self.version.tariff_grade_id = self.before
        self.before.action_archive()
        with self.assertRaises(UserError):
            self._lines(self._payslip())

    def test_the_statutory_floor_holds_for_each_part_on_its_own(self):
        self.version.tariff_grade_id = self.before
        self.psp_params.min_hourly_wage = 110.0
        lines = self._lines(self._payslip())
        self.assertAlmostEqual(lines[0].rate, 110.0, places=2,
                               msg='the floor lifts the first half only')
        self.assertAlmostEqual(lines[1].rate, 120.0, places=2)

    def test_night_hours_entered_by_hand_are_paid_whole_at_the_end_rate(self):
        self.version.tariff_grade_id = self.before
        slip = self._payslip(night_hours=10.0)
        night = self._lines(slip, self.night_type)
        self.assertEqual(len(night), 1)
        self.assertAlmostEqual(
            night.rate, 120.0 * self.psp_params.night_surcharge_rate / 100.0,
            places=4)

    # --- the version changes ---

    def test_a_version_that_changes_nothing_paid_for_keeps_one_line(self):
        # Odoo writes a version for any change of the card; one that touches
        # no pay must not split the month.
        self.version.tariff_grade_id = self.other_grade
        self._second_version(tariff_grade_id=self.other_grade.id)
        lines = self._lines(self._payslip())
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.amount, 184.0 * 150.0, places=2)

    def test_a_grade_change_by_version_is_paid_by_the_day(self):
        self.version.tariff_grade_id = self.other_grade
        self._second_version(tariff_grade_id=self.before.id)
        lines = self._lines(self._payslip())
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0].amount, 88.0 * 150.0, places=2)
        # From 16 July the second grade is in force and so is its new rate.
        self.assertAlmostEqual(lines[1].rate, 120.0, places=2)
        self.assertAlmostEqual(lines[1].amount, 96.0 * 120.0, places=2)
        self.assertIn('16', lines[1].notes)

    def test_a_wage_change_by_version_is_paid_by_the_day(self):
        self.version.write({'tariff_grade_id': False, 'wage': 23000})
        self._second_version(wage=46000)
        lines = self._lines(self._payslip())
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0].amount,
                               round(23000 / 23 * 11, 2), places=2)
        self.assertAlmostEqual(lines[1].amount,
                               round(46000 / 23 * 12, 2), places=2)
        self.assertAlmostEqual(sum(lines.mapped('quantity')), 23.0, places=2,
                               msg='no day is paid twice or lost')

    def test_a_work_rate_change_halves_the_hours_of_its_days(self):
        self.version.write({'tariff_grade_id': self.other_grade.id,
                            'wage': 23000})
        self._second_version(tariff_grade_id=self.other_grade.id, work_rate=0.5)
        slip = self._payslip()
        slip._compute_working_days()
        # 11 days at 8 hours and 12 days at 4.
        self.assertAlmostEqual(slip.worked_hours, 11 * 8 + 12 * 4, places=2)
        lines = self._lines(slip)
        self.assertAlmostEqual(sum(lines.mapped('quantity')), slip.worked_hours,
                               places=2)

    def test_allowances_are_paid_for_the_days_of_their_version(self):
        self.version.write({'tariff_grade_id': self.other_grade.id})
        self.env['hr.version.allowance'].create({
            'version_id': self.version.id,
            'allowance_type_id': self.env['hr.allowance.type'].search(
                [], limit=1).id,
            'calculation_method': 'fixed',
            'amount': 2300,
        })
        self._second_version(tariff_grade_id=self.other_grade.id)
        lines = self._lines(self._payslip(), self.allowance_type)
        self.assertEqual(len(lines), 1, 'only the first version has one')
        self.assertAlmostEqual(lines.amount, round(2300 * 11 / 23, 2), places=2)

    def test_different_salary_currencies_refuse_one_payslip(self):
        self.version.write({'tariff_grade_id': self.other_grade.id})
        usd = self.env.ref('base.USD')
        self._second_version(tariff_grade_id=self.other_grade.id,
                             salary_currency_id=usd.id, wage=1000)
        with self.assertRaises(UserError):
            self._lines(self._payslip())

    def test_a_diia_city_change_refuses_one_payslip(self):
        self.version.write({'tariff_grade_id': self.other_grade.id})
        self._second_version(tariff_grade_id=self.other_grade.id,
                             contract_type_ua='gig', diia_city_employee=True)
        with self.assertRaises(UserError):
            self._lines(self._payslip())

    def test_the_payslip_keeps_one_version(self):
        self.version.tariff_grade_id = self.other_grade
        second = self._second_version(tariff_grade_id=self.before.id)
        slip = self._payslip()
        slip._generate_accruals()
        self.assertEqual(slip.version_id, self.version,
                         'the field still holds the version of the period start')
        self.assertNotEqual(slip.version_id, second)


@tagged('post_install', '-at_install')
class TestPayslipSegmentsFromTimesheet(SalaryTestCase):
    """With a timesheet every hour has a date, and is paid by it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'hr.timesheet.line' not in cls.env:
            return
        cls.psp_params.write({'min_hourly_wage': 0.0})
        cls.salary_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'SALARY')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Salary', 'code': 'SALARY', 'category': 'wage'})
        cls.night_type = cls.env['hr.accrual.type'].search(
            [('code', '=', 'NIGHT')], limit=1) or cls.env['hr.accrual.type'].create(
            {'name': 'Night', 'code': 'NIGHT', 'category': 'surcharge'})
        Grade = cls.env['hr.tariff.grade']
        Grade.search([
            ('company_id', '=', cls.company.id), ('grade', '=', 10),
        ]).action_archive()
        common = {'name': 'Grade 10', 'grade': 10, 'coefficient': 1.82,
                  'company_id': cls.company.id}
        cls.before = Grade.create(dict(common, hourly_rate=100.0,
                                       date_from=date(2025, 1, 1),
                                       date_to=date(2025, 7, 15)))
        cls.after = Grade.create(dict(common, hourly_rate=120.0,
                                      date_from=date(2025, 7, 16)))
        cls.version.tariff_grade_id = cls.before
        cls.work_code = cls.env['hr.timesheet.code'].search(
            [('is_worked', '=', True)], limit=1)

    def setUp(self):
        super().setUp()
        if 'hr.timesheet.line' not in self.env:
            self.skipTest('l10n_ua_hr_attendance_sheet is not installed')
        if not self.work_code:
            self.skipTest('no worked timesheet code in this database')

    def _timesheet(self, days):
        sheet = self.env['hr.timesheet'].create({
            'month': '7', 'year': 2025, 'company_id': self.company.id,
        })
        line = self.env['hr.timesheet.line'].create({
            'timesheet_id': sheet.id, 'employee_id': self.employee.id,
        })
        self.env['hr.timesheet.day'].create([{
            'line_id': line.id, 'date': date(2025, 7, day), 'day_number': day,
            'code_id': self.work_code.id, 'hours': hours,
            'night_hours': night, 'is_scheduled': True,
        } for day, hours, night in days])
        sheet.state = 'confirmed'
        return line

    def _payslip(self):
        return self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': date(2025, 7, 1), 'date_to': date(2025, 7, 31),
        })

    def test_hours_are_paid_at_the_rate_of_the_day_they_fall_on(self):
        self._timesheet([(14, 8.0, 0.0), (15, 6.0, 0.0),
                         (16, 8.0, 0.0), (17, 7.5, 0.0)])
        slip = self._payslip()
        slip.action_compute_sheet()
        lines = slip.accrual_ids.filtered(
            lambda a: a.accrual_type_id == self.salary_type).sorted('id')
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0].quantity, 14.0, places=2)
        self.assertAlmostEqual(lines[0].amount, 1400.0, places=2)
        self.assertAlmostEqual(lines[1].quantity, 15.5, places=2)
        self.assertAlmostEqual(lines[1].amount, 1860.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped('quantity')),
                               slip.worked_hours, places=2)

    def test_night_hours_are_paid_at_the_rate_of_their_own_day(self):
        self._timesheet([(14, 8.0, 4.0), (16, 8.0, 2.0)])
        slip = self._payslip()
        slip.action_compute_sheet()
        night = slip.accrual_ids.filtered(
            lambda a: a.accrual_type_id == self.night_type).sorted('id')
        self.assertEqual(len(night), 2, 'the night of each half at its rate')
        percent = self.psp_params.night_surcharge_rate / 100.0
        self.assertAlmostEqual(night[0].amount, round(4.0 * 100.0 * percent, 2),
                               places=2)
        self.assertAlmostEqual(night[1].amount, round(2.0 * 120.0 * percent, 2),
                               places=2)
