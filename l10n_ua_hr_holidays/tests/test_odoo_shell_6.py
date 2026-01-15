# Test script for Odoo shell - Part 6: Calendar Days in Balance
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_6.py

from datetime import datetime, date

print("=" * 70)
print("Testing l10n_ua_hr_holidays - Part 6: Calendar Days in Balance")
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
# 1. Check that _compute_used_days uses calendar_days
# ============================================================
print("\n" + "=" * 70)
print("1. Verify _compute_used_days uses calendar_days")
print("=" * 70)

# Check source code
import inspect
Balance = env['hr.vacation.balance']
if hasattr(Balance, '_compute_used_days'):
    source = inspect.getsource(Balance._compute_used_days)
    if 'calendar_days' in source:
        print("   ✓ _compute_used_days uses 'calendar_days'")
    else:
        print("   ✗ _compute_used_days does NOT use 'calendar_days'")
    
    if 'number_of_days' in source:
        print("   ⚠️ _compute_used_days still references 'number_of_days'")
    else:
        print("   ✓ _compute_used_days does not use 'number_of_days'")

# ============================================================
# 2. Find existing leave and compare values
# ============================================================
print("\n" + "=" * 70)
print("2. Compare number_of_days vs calendar_days on existing leave")
print("=" * 70)

test_leave = env['hr.leave'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
], limit=1, order='id desc')

if test_leave:
    print(f"\n   Leave ID: {test_leave.id}")
    print(f"   Date: {test_leave.date_from} - {test_leave.date_to}")
    print(f"   State: {test_leave.state}")
    print(f"   number_of_days (working): {test_leave.number_of_days}")
    print(f"   calendar_days (Ukrainian): {test_leave.calendar_days}")
    
    if test_leave.number_of_days != test_leave.calendar_days:
        print(f"\n   ✓ Values are different - calendar_days is correct for Ukrainian law")
        print(f"   Difference: {test_leave.calendar_days - test_leave.number_of_days} days")
    else:
        print(f"\n   Values are equal (may be correct if no weekends in period)")
else:
    print("   No leave found")

# ============================================================
# 3. Test balance calculation with calendar_days
# ============================================================
print("\n" + "=" * 70)
print("3. Test balance calculation")
print("=" * 70)

# Find or create balance for 2026
balance = env['hr.vacation.balance'].search([
    ('employee_id', '=', employee.id),
    ('leave_type_id', '=', annual_leave.id),
    ('year', '=', 2026),
], limit=1)

if not balance:
    print("   Creating balance for 2026...")
    balance = env['hr.vacation.balance'].create({
        'employee_id': employee.id,
        'leave_type_id': annual_leave.id,
        'year': 2026,
        'entitled_days': 24,
        'carried_over': 0,
    })
    print(f"   ✓ Balance created: ID={balance.id}")

# Force recompute
balance.invalidate_recordset()

print(f"\n   Balance for {balance.year}:")
print(f"   - entitled_days: {balance.entitled_days}")
print(f"   - carried_over: {balance.carried_over}")
print(f"   - total_available: {balance.total_available}")
print(f"   - used_days: {balance.used_days}")
print(f"   - planned_days: {balance.planned_days}")
print(f"   - remaining_days: {balance.remaining_days}")

# ============================================================
# 4. Verify used_days matches sum of calendar_days
# ============================================================
print("\n" + "=" * 70)
print("4. Verify used_days = sum(calendar_days) for approved leaves")
print("=" * 70)

approved_leaves = env['hr.leave'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
    ('state', '=', 'validate'),
    ('date_from', '>=', '2026-01-01'),
    ('date_to', '<=', '2026-12-31'),
])

sum_calendar_days = sum(approved_leaves.mapped('calendar_days'))
sum_number_of_days = sum(approved_leaves.mapped('number_of_days'))

print(f"\n   Approved leaves in 2026: {len(approved_leaves)}")
print(f"   Sum of calendar_days: {sum_calendar_days}")
print(f"   Sum of number_of_days: {sum_number_of_days}")
print(f"   Balance used_days: {balance.used_days}")

if balance.used_days == sum_calendar_days:
    print(f"\n   ✓ used_days matches sum of calendar_days (Ukrainian law compliant)")
elif balance.used_days == sum_number_of_days:
    print(f"\n   ✗ used_days matches sum of number_of_days (NOT Ukrainian law compliant)")
else:
    print(f"\n   ⚠️ used_days doesn't match either sum")

# ============================================================
# 5. Verify planned_days matches sum of calendar_days
# ============================================================
print("\n" + "=" * 70)
print("5. Verify planned_days = sum(calendar_days) for pending leaves")
print("=" * 70)

planned_leaves = env['hr.leave'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
    ('state', 'in', ['draft', 'confirm']),
    ('date_from', '>=', '2026-01-01'),
    ('date_to', '<=', '2026-12-31'),
])

sum_planned_calendar = sum(planned_leaves.mapped('calendar_days'))
sum_planned_number = sum(planned_leaves.mapped('number_of_days'))

print(f"\n   Pending leaves in 2026: {len(planned_leaves)}")
print(f"   Sum of calendar_days: {sum_planned_calendar}")
print(f"   Sum of number_of_days: {sum_planned_number}")
print(f"   Balance planned_days: {balance.planned_days}")

if balance.planned_days == sum_planned_calendar:
    print(f"\n   ✓ planned_days matches sum of calendar_days (Ukrainian law compliant)")
elif balance.planned_days == sum_planned_number:
    print(f"\n   ✗ planned_days matches sum of number_of_days (NOT Ukrainian law compliant)")
else:
    print(f"\n   ⚠️ planned_days doesn't match either sum")

print("\n" + "=" * 70)
print("Part 6 Testing complete!")
print("=" * 70)
