# Test script for Odoo shell - Part 5: Balance, Compensation, Uniqueness
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_5.py

from datetime import datetime, date
from dateutil.relativedelta import relativedelta

print("=" * 70)
print("Testing l10n_ua_hr_holidays - Part 5: Balance & Compensation")
print("=" * 70)

# Setup
company = env.company
print(f"\nCompany: {company.name}")

employee = env['hr.employee'].search([('company_id', '=', company.id)], limit=1)
print(f"Employee: {employee.name}")

annual_leave = env['hr.leave.type'].search([
    ('ua_leave_category', '=', 'annual_basic'),
], limit=1)
print(f"Leave type: {annual_leave.name if annual_leave else 'NOT FOUND'}")

# ============================================================
# 1. Testing Balance Uniqueness Constraint
# ============================================================
print("\n" + "=" * 70)
print("1. Testing Balance Uniqueness Constraint")
print("=" * 70)

# Check if constraint exists in model
Balance = env['hr.vacation.balance']
constraints = [c[0] for c in Balance._sql_constraints] if hasattr(Balance, '_sql_constraints') else []
print(f"   SQL constraints: {constraints}")

if 'unique_employee_id_leave_type_id_year' in str(constraints):
    print("   ✓ Uniqueness constraint defined in model")
else:
    print("   Checking database constraint...")
    env.cr.execute("""
        SELECT constraint_name FROM information_schema.table_constraints 
        WHERE table_name = 'hr_vacation_balance' AND constraint_type = 'UNIQUE'
    """)
    db_constraints = env.cr.fetchall()
    print(f"   DB constraints: {db_constraints}")
    if any('unique' in str(c).lower() for c in db_constraints):
        print("   ✓ Uniqueness constraint exists in database")

# ============================================================
# 2. Testing Carryover Limit (2 years)
# ============================================================
print("\n" + "=" * 70)
print("2. Testing Carryover Limit (2 years)")
print("=" * 70)

# Check if max_carryover_years field exists
if 'max_carryover_years' in env['hr.leave.type']._fields:
    print(f"   ✓ max_carryover_years field exists")
    print(f"   Value for annual leave: {annual_leave.max_carryover_years}")
else:
    print("   ⚠️ max_carryover_years field not found on leave type")

# Check if _check_carryover_limit constraint exists
if hasattr(Balance, '_check_carryover_limit'):
    print("   ✓ _check_carryover_limit constraint method exists")
else:
    print("   ⚠️ _check_carryover_limit method not found")

# ============================================================
# 3. Testing Compensation Calculation
# ============================================================
print("\n" + "=" * 70)
print("3. Testing Compensation Calculation")
print("=" * 70)

# Check compensation method exists
if hasattr(Balance, 'calculate_compensation'):
    print("   ✓ calculate_compensation method exists")
else:
    print("   ⚠️ calculate_compensation method not found")

# Check compensation fields
comp_fields = ['compensation_amount', 'compensation_days']
for field in comp_fields:
    if field in Balance._fields:
        print(f"   ✓ {field} field exists")
    else:
        print(f"   ⚠️ {field} field not found")

# Check existing balance for compensation test
existing_balance = env['hr.vacation.balance'].search([
    ('employee_id', '=', employee.id),
    ('leave_type_id', '=', annual_leave.id),
], limit=1)

if existing_balance:
    print(f"\n   Existing balance found (year {existing_balance.year}):")
    print(f"   - entitled_days: {existing_balance.entitled_days}")
    print(f"   - carried_over: {existing_balance.carried_over}")
    print(f"   - total_available: {existing_balance.total_available}")
    print(f"   - used_days: {existing_balance.used_days}")
    print(f"   - remaining_days: {existing_balance.remaining_days}")

# ============================================================
# 4. Testing Average Salary Calculation
# ============================================================
print("\n" + "=" * 70)
print("4. Testing Average Salary Calculation (CMU Resolution № 100)")
print("=" * 70)

# Check if hr.payslip model exists
try:
    env['hr.payslip']
    print("   ✓ hr.payslip model exists (hr_payroll installed)")
except KeyError:
    print("   ⚠️ hr.payslip model not found (hr_payroll not installed)")

# Check _calculate_average_salary method on hr.leave
Leave = env['hr.leave']
if hasattr(Leave, '_calculate_average_salary'):
    print("   ✓ _calculate_average_salary method exists on hr.leave")
else:
    print("   ⚠️ _calculate_average_salary method not found")

# Check average_daily_salary field
if 'average_daily_salary' in Leave._fields:
    print("   ✓ average_daily_salary field exists on hr.leave")

# ============================================================
# 5. Testing Used Days Computation
# ============================================================
print("\n" + "=" * 70)
print("5. Testing Used Days Computation")
print("=" * 70)

# Check _compute_used_days method
if hasattr(Balance, '_compute_used_days'):
    print("   ✓ _compute_used_days method exists")
else:
    print("   ⚠️ _compute_used_days method not found")

# Check used_days field is computed
used_days_field = Balance._fields.get('used_days')
if used_days_field and used_days_field.compute:
    print(f"   ✓ used_days is computed field (compute={used_days_field.compute})")
else:
    print("   ⚠️ used_days is not a computed field")

# Find test leave
test_leave = env['hr.leave'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
], limit=1, order='id desc')

if test_leave:
    print(f"\n   Latest leave: ID={test_leave.id}")
    print(f"   - State: {test_leave.state}")
    print(f"   - number_of_days: {test_leave.number_of_days}")
    print(f"   - calendar_days: {test_leave.calendar_days}")

# ============================================================
# 6. Testing Public Holidays in Salary Calculation
# ============================================================
print("\n" + "=" * 70)
print("6. Testing Public Holidays Exclusion from Salary Denominator")
print("=" * 70)

# Count public holidays in a year
public_holidays_2025 = env['resource.calendar.leaves'].search([
    ('resource_id', '=', False),
    ('date_from', '>=', '2025-01-01'),
    ('date_to', '<=', '2025-12-31'),
])
print(f"\n   Public holidays in 2025: {len(public_holidays_2025)}")

# Calculate expected denominator
calendar_days_2025 = 365
expected_denominator = calendar_days_2025 - len(public_holidays_2025)
print(f"   Calendar days: {calendar_days_2025}")
print(f"   Expected denominator (without holidays): {expected_denominator}")

# Check _get_public_holidays_count method
if hasattr(Leave, '_get_public_holidays_count'):
    print("   ✓ _get_public_holidays_count method exists on hr.leave")

print("\n" + "=" * 70)
print("Part 5 Testing complete!")
print("=" * 70)
