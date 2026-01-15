# Test script for Odoo shell - Part 3: Calculations & Compensation
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_3.py

from datetime import datetime, timedelta

print("=" * 60)
print("Testing l10n_ua_hr_holidays - Part 3: Calculations")
print("=" * 60)

company = env.company
employee = env['hr.employee'].search([('company_id', '=', company.id)], limit=1)
annual_leave = env['hr.leave.type'].search([
    ('ua_leave_category', '=', 'annual_basic'),
], limit=1)

print(f"\nCompany: {company.name}")
print(f"Employee: {employee.name if employee else 'NOT FOUND'}")
print(f"Leave type: {annual_leave.name if annual_leave else 'NOT FOUND'}")

# 1. Test average salary calculation
print("\n" + "=" * 60)
print("1. Testing Average Salary Calculation (Постанова КМУ № 100)")
print("=" * 60)

if employee:
    # Create a test leave to calculate salary
    date_from = datetime(2026, 8, 1, 8, 0, 0)
    date_to = datetime(2026, 8, 14, 17, 0, 0)
    
    print(f"\n   Test period: {date_from.date()} - {date_to.date()}")
    
    try:
        leave = env['hr.leave'].new({
            'employee_id': employee.id,
            'holiday_status_id': annual_leave.id if annual_leave else False,
            'date_from': date_from,
            'date_to': date_to,
        })
        
        # Test _calculate_average_salary method
        if hasattr(leave, '_calculate_average_salary'):
            avg_salary = leave._calculate_average_salary()
            print(f"   ✓ _calculate_average_salary method exists")
            print(f"   - Average daily salary: {avg_salary}")
            
            # Check if contract exists for fallback
            contract = employee.contract_id
            if contract:
                print(f"   - Contract wage: {contract.wage}")
                print(f"   - Fallback would be: {round(contract.wage / 29.3, 2)}")
            else:
                print(f"   - No contract found (fallback to 0)")
        else:
            print(f"   ✗ _calculate_average_salary method NOT FOUND")
            
    except Exception as e:
        print(f"   ✗ Error: {e}")

# 2. Test vacation pay calculation
print("\n" + "=" * 60)
print("2. Testing Vacation Pay Calculation")
print("=" * 60)

if employee and annual_leave:
    try:
        leave = env['hr.leave'].new({
            'employee_id': employee.id,
            'holiday_status_id': annual_leave.id,
            'date_from': datetime(2026, 8, 1, 8, 0, 0),
            'date_to': datetime(2026, 8, 14, 17, 0, 0),
            'average_daily_salary': 500.0,
        })
        
        print(f"   - calendar_days: {leave.calendar_days}")
        print(f"   - average_daily_salary: {leave.average_daily_salary}")
        print(f"   - vacation_pay_amount: {leave.vacation_pay_amount}")
        print(f"   - Expected: {leave.calendar_days * 500.0}")
        
        if leave.vacation_pay_amount == leave.calendar_days * 500.0:
            print(f"   ✓ Vacation pay calculation correct")
        else:
            print(f"   ⚠️ Vacation pay may need manual trigger")
            
    except Exception as e:
        print(f"   ✗ Error: {e}")

# 3. Test compensation calculation
print("\n" + "=" * 60)
print("3. Testing Compensation Calculation")
print("=" * 60)

if employee and annual_leave:
    balance = env['hr.vacation.balance'].search([
        ('employee_id', '=', employee.id),
        ('leave_type_id', '=', annual_leave.id),
    ], limit=1)
    
    if balance:
        print(f"\n   Balance found: {balance.display_name}")
        print(f"   - remaining_days: {balance.remaining_days}")
        
        # Test compensation calculation
        if hasattr(balance, 'calculate_compensation'):
            print(f"   ✓ calculate_compensation method exists")
            
            # Test termination compensation (all days)
            comp_termination = balance.calculate_compensation(is_termination=True)
            print(f"   - Termination compensation: {comp_termination}")
            
            # Test non-termination compensation (only days > 24)
            comp_no_term = balance.calculate_compensation(is_termination=False)
            print(f"   - Non-termination compensation: {comp_no_term}")
            print(f"   - (Only days over 24 if used >= 24)")
        else:
            print(f"   ✗ calculate_compensation method NOT FOUND")
    else:
        print(f"   No balance found for testing")

# 4. Test sick leave payment calculation
print("\n" + "=" * 60)
print("4. Testing Sick Leave Payment Calculation")
print("=" * 60)

sick_model = env['hr.sick.leave']

# Test payment percent by experience
print("\n   Testing payment percent by insurance experience:")
test_cases = [
    (2, 50, "< 3 years"),
    (4, 60, "3-5 years"),
    (6, 70, "5-8 years"),
    (10, 100, "> 8 years"),
]

for years, expected_percent, desc in test_cases:
    try:
        sick = sick_model.new({
            'employee_id': employee.id if employee else False,
            'insurance_experience_years': years,
            'sick_leave_type': 'illness',
        })
        actual = sick.payment_percent
        status = "✓" if actual == expected_percent else "✗"
        print(f"   {status} {desc} ({years} years): {actual}% (expected {expected_percent}%)")
    except Exception as e:
        print(f"   ✗ Error for {years} years: {e}")

# Test pregnancy - always 100%
try:
    sick_pregnancy = sick_model.new({
        'employee_id': employee.id if employee else False,
        'insurance_experience_years': 1,
        'sick_leave_type': 'pregnancy',
    })
    status = "✓" if sick_pregnancy.payment_percent == 100 else "✗"
    print(f"   {status} Pregnancy (any experience): {sick_pregnancy.payment_percent}% (expected 100%)")
except Exception as e:
    print(f"   ✗ Error for pregnancy: {e}")

# 5. Test employer vs FSS days
print("\n" + "=" * 60)
print("5. Testing Employer vs FSS Days Split")
print("=" * 60)

try:
    sick = sick_model.new({
        'employee_id': employee.id if employee else False,
        'date_from': datetime(2026, 3, 1),
        'date_to': datetime(2026, 3, 10),
        'insurance_experience_years': 10,
        'sick_leave_type': 'illness',
        'average_daily_salary': 500.0,
    })
    
    print(f"   Period: 10 calendar days")
    print(f"   - employer_days: {sick.employer_days} (expected: 5)")
    print(f"   - fss_days: {sick.fss_days} (expected: 5)")
    print(f"   - employer_amount: {sick.employer_amount}")
    print(f"   - fss_amount: {sick.fss_amount}")
    print(f"   - total_amount: {sick.total_amount}")
    
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test pregnancy - all FSS
try:
    sick_preg = sick_model.new({
        'employee_id': employee.id if employee else False,
        'date_from': datetime(2026, 3, 1),
        'date_to': datetime(2026, 6, 30),
        'insurance_experience_years': 1,
        'sick_leave_type': 'pregnancy',
        'average_daily_salary': 500.0,
    })
    
    print(f"\n   Pregnancy leave:")
    print(f"   - employer_days: {sick_preg.employer_days} (expected: 0)")
    print(f"   - fss_days: {sick_preg.fss_days}")
    print(f"   - payment_percent: {sick_preg.payment_percent}% (expected: 100%)")
    
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("Part 3 Testing complete!")
print("=" * 60)
