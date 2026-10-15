"""Form № 1-ПВ «Звіт із праці» (hr.report.labor), issue #370.

The fixture company, in the first quarter of 2026:

* Олена (female, staff, full rate) — the whole quarter;
* Борис (staff) — hired on 16.02.2026;
* Євген (staff) — dismissed on 20.03.2026 for staff reduction (п. 1 ст. 40);
* Сергій — external part-timer at half a rate;
* Дмитро — civil-law contract.

Payslips (done): Олена 20 000 salary + 5 000 bonus + 3 000 sick pay from the
Social Insurance Fund every month, 160 h; Сергій 6 000, 80 h; Дмитро 10 000.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ua_hr_reports')
class TestReportLabor(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A company of its own: the report counts the whole company.
        cls.company = cls.env['res.company'].create({
            'name': '1-PV Test Co',
            'currency_id': cls.env.ref('base.UAH').id,
        })
        cls.olena = cls._employee('Олена Коваль', date(2025, 1, 1), gender='female')
        cls.borys = cls._employee('Борис Мельник', date(2026, 2, 16))
        cls.yevhen = cls._employee(
            'Євген Шевчук', date(2025, 1, 1), end=date(2026, 3, 20),
            reason=cls.env.ref('l10n_ua_hr_contract.termination_reason_reduction'))
        cls.serhii = cls._employee('Сергій Бондар', date(2025, 1, 1),
                                   employment='external', rate=0.5)
        cls.dmytro = cls._employee('Дмитро Ткач', date(2025, 1, 1), contract='civil')

        salary = cls.env.ref('l10n_ua_hr_salary.accrual_type_salary')
        bonus = cls.env.ref('l10n_ua_hr_salary.accrual_type_bonus')
        sick_fss = cls.env.ref('l10n_ua_hr_salary.accrual_type_sick_fss')
        cls.slips = cls.env['hr.payslip']
        for month in (1, 2, 3):
            cls.slips |= cls._payslip(cls.olena, month, 160,
                                      [(salary, 20000), (bonus, 5000), (sick_fss, 3000)])
            cls.slips |= cls._payslip(cls.serhii, month, 80, [(salary, 6000)])
            cls.slips |= cls._payslip(cls.dmytro, month, 0, [(salary, 10000)])

    @classmethod
    def _employee(cls, name, start, end=False, gender='male', employment='primary',
                  contract='permanent', rate=1.0, reason=False):
        employee = cls.env['hr.employee'].create({
            'name': name,
            'company_id': cls.company.id,
            'gender': gender,
        })
        version = employee.with_context(active_test=False).version_ids[:1]
        version.write({
            'date_version': start,
            'contract_date_start': start,
            'contract_date_end': end,
            'contract_type_ua': contract,
            'employment_type_ua': employment,
            'work_rate': rate,
            'termination_reason_ua_id': reason and reason.id,
        })
        return employee

    @classmethod
    def _payslip(cls, employee, month, hours, accruals):
        last = {1: 31, 2: 28, 3: 31}[month]
        slip = cls.env['hr.payslip'].create({
            'employee_id': employee.id,
            'company_id': cls.company.id,
            'date_from': date(2026, month, 1),
            'date_to': date(2026, month, last),
        })
        for kind, amount in accruals:
            cls.env['hr.payslip.accrual'].create({
                'payslip_id': slip.id,
                'accrual_type_id': kind.id,
                'quantity': 1,
                'rate': amount,
                'amount': amount,
            })
        slip.write({'worked_hours': hours, 'overtime_hours': 0.0, 'state': 'done'})
        return slip

    def _report(self, **vals):
        values = {'company_id': self.company.id, 'year': 2026}
        values.update(vals)
        report = self.env['hr.report.labor'].create(values)
        report.action_compute()
        return report

    # ------------------------------------------------------------------ monthly

    def test_monthly_rows(self):
        report = self._report(period_type='month', month='1')
        self.assertEqual(report.name, '1-ПВ (місячна) за січень 2026 р.')
        self.assertEqual(
            sorted(set(report.line_ids.mapped('code'))),
            ['1020', '1030', '1040', '1060', '1070'])
        # Олена and Євген are the staff in January; the part-timer and the
        # civil contractor are not.
        self.assertEqual(report.get_value('1040'), 2)
        # The wage fund of all workers leaves out the sick pay of the Fund.
        self.assertEqual(report.get_value('1020'), 41.0)
        self.assertEqual(report.get_value('1070'), 25.0)
        self.assertEqual(report.get_value('1060'), 160)

    def test_monthly_pdfo_excludes_sick_pay(self):
        report = self._report(period_type='month', month='1')
        slips = self.slips.filtered(lambda s: s.date_from == date(2026, 1, 1))
        expected = 0.0
        for slip in slips:
            taxable = sum(a.amount for a in slip.accrual_ids if a.is_taxable_pdfo)
            in_fund = sum(a.amount for a in slip.accrual_ids
                          if a.is_taxable_pdfo and a.accrual_type_id.code != 'SICK_FSS')
            if taxable:
                expected += slip.pdfo_amount * in_fund / taxable
        self.assertTrue(expected, 'The fixture payslips must carry personal income tax')
        self.assertAlmostEqual(report.get_value('1030'), round(expected / 1000, 1))
        self.assertLess(report.get_value('1030'), report.get_value('1020') * 0.18 + 0.1)

    def test_average_headcount_partial_months(self):
        # February: Олена and Євген all month, Борис 13 of 28 days → 2.46.
        february = self._report(period_type='month', month='2')
        self.assertEqual(february.get_value('1040'), 2)
        # March: Олена and Борис, Євген 19 of 31 days → 2.61.
        march = self._report(period_type='month', month='3')
        self.assertEqual(march.get_value('1040'), 3)
        # The average wage fell with the headcount up: the deviation against
        # February is reported for the explanation the form asks for.
        self.assertAlmostEqual(march.headcount_change, 50.0)
        self.assertTrue(march.needs_explanation)

    def test_deadline(self):
        # 07.02.2026 is a Saturday.
        january = self.env['hr.report.labor'].create({
            'company_id': self.company.id, 'year': 2026,
            'period_type': 'month', 'month': '1'})
        self.assertEqual(january.date_deadline, date(2026, 2, 9))
        fourth = self.env['hr.report.labor'].create({
            'company_id': self.company.id, 'year': 2026,
            'period_type': 'quarter', 'quarter': '4'})
        self.assertEqual(fourth.date_deadline, date(2027, 1, 7))
        self.assertEqual(fourth.date_from, date(2026, 10, 1))
        self.assertEqual(fourth.date_to, date(2026, 12, 31))

    # ---------------------------------------------------------------- quarterly

    def test_quarter_headcount_and_movement(self):
        report = self._report(period_type='quarter', quarter='1')
        self.assertEqual(report.get_value('3020'), 1)       # Борис
        self.assertEqual(report.get_value('3020', '2'), 0)
        self.assertEqual(report.get_value('3040'), 1)       # Євген
        self.assertEqual(report.get_value('3050'), 1)       # скорочення штату
        self.assertEqual(report.get_value('3060'), 0)
        self.assertEqual(report.get_value('3070'), 2)       # Олена, Борис
        self.assertEqual(report.get_value('3070', '2'), 1)
        # Rows of the 31 December and Section V belong to the fourth quarter only.
        self.assertFalse(report._line('3080'))
        self.assertFalse(report._line('8010'))

    def test_quarter_aggregates_three_months(self):
        report = self._report(period_type='quarter', quarter='1')
        self.assertEqual(report.get_value('5020'), 60.0)
        self.assertEqual(report.get_value('5030'), 15.0)
        self.assertEqual(report.get_value('5050'), 15.0)
        self.assertEqual(report.get_value('5060'), 0.0)
        self.assertEqual(report.get_value('5010'), 75.0)
        monthly = sum(self._report(period_type='month', month=m).get_value('1070')
                      for m in ('1', '2', '3'))
        self.assertEqual(report.get_value('5010'), monthly)
        # Women among the staff: Олена.
        self.assertEqual(report.get_value('7010', '1'), 1)
        self.assertEqual(report.get_value('7010', '2'), 75.0)
        self.assertEqual(report.get_value('7010', '3'), 480)
        # The external part-timer at half a rate, and the civil contractor.
        self.assertEqual(report.get_value('7030', '1'), 1)
        self.assertEqual(report.get_value('7030', '2'), 18.0)
        self.assertEqual(report.get_value('7030', '3'), 240)
        self.assertEqual(report.get_value('7040', '1'), 1)
        self.assertEqual(report.get_value('7040', '2'), 30.0)

    def test_fourth_quarter_rows(self):
        report = self._report(period_type='quarter', quarter='4')
        self.assertTrue(report._line('3080'))
        self.assertTrue(report._line('3100', '2'))
        for code in ('8010', '8020', '8030', '8040'):
            line = report._line(code)
            self.assertFalse(line.is_auto)
            self.assertTrue(line.is_manual)
        # Олена and Борис on the 31st of December, Сергій not being staff.
        self.assertEqual(report.get_value('3070'), 2)
        self.assertEqual(report.get_value('3080'), 0)

    # ------------------------------------------------------------------ editing

    def test_manual_override_kept_on_recompute(self):
        report = self._report(period_type='month', month='1')
        line = report._line('1040')
        line.write({'is_manual': True, 'manual_value': 7})
        report.action_compute()
        self.assertEqual(line.computed_value, 2)
        self.assertEqual(line.value, 7)
        self.assertEqual(report.get_value('1040'), 7)

    def test_manual_component_flows_into_total(self):
        report = self._report(period_type='quarter', quarter='1')
        report._line('5060').write({'is_manual': True, 'manual_value': 4.5})
        report.action_compute()
        self.assertEqual(report.get_value('5010'), 79.5)

    def test_manual_rows_without_data(self):
        report = self._report(period_type='quarter', quarter='1')
        line = report._line('4080')
        self.assertFalse(line.is_auto)
        line.manual_value = 16
        report.action_compute()
        self.assertEqual(report.get_value('4080'), 16)

    def test_done_locks_the_report(self):
        report = self._report(period_type='month', month='1')
        report.action_done()
        self.assertEqual(report.state, 'done')
        with self.assertRaises(UserError):
            report.action_compute()
        with self.assertRaises(UserError):
            report._line('1040').manual_value = 3
        report.action_draft()
        self.assertEqual(report.state, 'draft')

    def test_period_unique_per_company(self):
        self._report(period_type='month', month='1')
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['hr.report.labor'].create({
                'company_id': self.company.id, 'year': 2026,
                'period_type': 'month', 'month': '1'})

    def test_accrual_type_group_override(self):
        bonus = self.env.ref('l10n_ua_hr_salary.accrual_type_bonus')
        self.assertEqual(bonus._l10n_ua_1pv_effective_group(), 'bonus')
        bonus.l10n_ua_1pv_group = 'incentive'
        report = self._report(period_type='quarter', quarter='1')
        self.assertEqual(report.get_value('5050'), 0.0)
        self.assertEqual(report.get_value('5060'), 15.0)
        self.assertEqual(report.get_value('5010'), 75.0)

    # ------------------------------------------------------------------ output

    def test_report_renders(self):
        for vals in ({'period_type': 'month', 'month': '1'},
                     {'period_type': 'quarter', 'quarter': '4'}):
            report = self._report(**vals)
            html, _format = self.env['ir.actions.report']._render_qweb_html(
                'l10n_ua_hr_reports.report_hr_report_labor', report.ids)
            html = html.decode()
            self.assertIn('ЗВІТ ІЗ ПРАЦІ', html)
            self.assertIn('15 квітня 2024 р. № 117', html)
            self.assertIn('1070' if vals['period_type'] == 'month' else '8040', html)

    def test_export_xlsx(self):
        report = self._report(period_type='quarter', quarter='1')
        action = report.action_export_xlsx()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'hr.report.labor'), ('res_id', '=', report.id)])
        self.assertTrue(attachment.name.endswith('.xlsx'))
        self.assertTrue(attachment.datas)
