from datetime import datetime, date
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestHrLeave(TransactionCase):
    """Tests for hr.leave Ukrainian extensions"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee Leave',
            'company_id': cls.company.id,
        })
        
        cls.leave_type_calendar = cls.env['hr.leave.type'].create({
            'name': 'Annual Leave (Calendar) Test',
            'ua_leave_category': 'annual_basic',
            'is_calendar_days': True,
            'annual_days': 24,
            'is_paid': True,
            'company_id': cls.company.id,
            'requires_allocation': False,
        })
        
        cls.leave_type_working = cls.env['hr.leave.type'].create({
            'name': 'Other Leave (Working) Test',
            'ua_leave_category': 'other',
            'is_calendar_days': False,
            'is_paid': False,
            'company_id': cls.company.id,
            'requires_allocation': False,
        })

    def test_calendar_days_computation(self):
        """Test that calendar_days is computed correctly"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
        })
        self.assertGreater(leave.calendar_days, 0)

    def test_working_days_computation(self):
        """Test that working_days is computed correctly (Mon-Fri)"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'request_date_from': date(2026, 1, 15),
            'request_date_to':   date(2026, 1, 21),
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
        })
        self.assertGreater(leave.working_days, 0)
        self.assertLessEqual(leave.working_days, leave.calendar_days)

    def test_number_of_days_calendar_type(self):
        """Test that number_of_days uses calendar days for is_calendar_days=True"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
        })
        self.assertGreater(leave.number_of_days, 0)

    def test_vacation_pay_computation(self):
        """Test vacation pay calculation"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
            'average_daily_salary': 500.0,
        })
        self.assertGreaterEqual(leave.vacation_pay_amount, 0)

    def test_vacation_pay_unpaid_leave(self):
        """Test that unpaid leave has zero vacation pay"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_working.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
            'average_daily_salary': 500.0,
        })
        self.assertEqual(leave.vacation_pay_amount, 0.0)

    def test_remaining_days_after_computation(self):
        """Test remaining_days_after calculation"""
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.leave_type_calendar.id,
            'year': 2028,
            'entitled_days': 24,
            'carried_over': 0,
        })
        
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2028, 1, 15, 8, 0, 0),
            'date_to': datetime(2028, 1, 21, 17, 0, 0),
            'vacation_year': 2028,
        })
        
        self.assertGreaterEqual(leave.remaining_days_before, 0)
        self.assertLess(leave.remaining_days_after, leave.remaining_days_before)

    def test_order_fields(self):
        """Test order number and date fields"""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
            'order_number': 'ORD-001',
            'order_date': date(2026, 1, 10),
        })
        self.assertEqual(leave.order_number, 'ORD-001')
        self.assertEqual(leave.order_date, date(2026, 1, 10))

    def test_vacation_year_field(self):
        """Vacation year is read-only and follows the leave start date."""
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
            'vacation_year': 2025,  # ignored — the field is computed
        })
        self.assertEqual(leave.vacation_year, 2026)
        # Moving the dates re-derives the year automatically.
        leave.write({
            'date_from': datetime(2027, 3, 1, 8, 0, 0),
            'date_to': datetime(2027, 3, 5, 17, 0, 0),
        })
        self.assertEqual(leave.vacation_year, 2027)


    def test_default_leave_type_preselected(self):
        """When creating a leave without specifying type, default is preselected."""
        # Set leave_type_calendar as default
        self.leave_type_calendar.write({'ua_is_default': True})
        # Create leave without specifying holiday_status_id
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'date_from': datetime(2026, 1, 15, 8, 0, 0),
            'date_to': datetime(2026, 1, 21, 17, 0, 0),
        })
        self.assertEqual(leave.holiday_status_id, self.leave_type_calendar)

    def test_vacation_period_auto_selected(self):
        """When creating a leave, matching period is auto-selected if it exists."""
        # Create a vacation balance for this employee/type
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.leave_type_calendar.id,
            'period_start': date(2026, 1, 1),
            'period_end': date(2026, 12, 31),
            'entitled_days': 24,
            'company_id': self.company.id,
        })
        # Create leave with dates in that period
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 6, 15, 8, 0, 0),
            'date_to': datetime(2026, 6, 21, 17, 0, 0),
        })
        self.assertEqual(leave.vacation_balance_id, balance)

    def test_vacation_period_cleared_if_not_matching(self):
        """When dates change to no matching period, the field is cleared."""
        # Create leave with a period
        balance = self.env['hr.vacation.balance'].create({
            'employee_id': self.employee.id,
            'leave_type_id': self.leave_type_calendar.id,
            'period_start': date(2026, 1, 1),
            'period_end': date(2026, 12, 31),
            'entitled_days': 24,
            'company_id': self.company.id,
        })
        leave = self.env['hr.leave'].create({
            'name': 'Test Leave',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type_calendar.id,
            'date_from': datetime(2026, 6, 15, 8, 0, 0),
            'date_to': datetime(2026, 6, 21, 17, 0, 0),
            'vacation_balance_id': balance.id,
        })
        # Change dates to 2027 (no matching period)
        leave.write({
            'date_from': datetime(2027, 6, 15, 8, 0, 0),
            'date_to': datetime(2027, 6, 21, 17, 0, 0),
        })
        self.assertFalse(leave.vacation_balance_id)
