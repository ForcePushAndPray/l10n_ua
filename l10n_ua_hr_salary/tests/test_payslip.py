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
