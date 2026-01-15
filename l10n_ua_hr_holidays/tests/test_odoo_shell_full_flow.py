# Test script for Odoo shell - Full Flow: Allocation → Leave Request → Approval
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_full_flow.py

from datetime import datetime, timedelta

print("=" * 70)
print("Testing FULL FLOW: Allocation → Leave Request → Approval → Calculation")
print("=" * 70)

# Setup
company = env.company
print(f"\nCompany: {company.name}")

# Get or create employee
employee = env['hr.employee'].search([('company_id', '=', company.id)], limit=1)
if not employee:
    employee = env['hr.employee'].create({
        'name': 'Test Employee Full Flow',
        'company_id': company.id,
    })
print(f"Employee: {employee.name}")

# Get annual leave type
annual_leave = env['hr.leave.type'].search([
    ('ua_leave_category', '=', 'annual_basic'),
], limit=1)
print(f"Leave type: {annual_leave.name if annual_leave else 'NOT FOUND'}")

if not annual_leave:
    print("\n❌ Cannot proceed without annual leave type")
    exit()

# ============================================================
# STEP 1: Create and Approve Allocation
# ============================================================
print("\n" + "=" * 70)
print("STEP 1: Create and Approve Allocation (hr.leave.allocation)")
print("=" * 70)

# Delete existing test allocations
existing = env['hr.leave.allocation'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
    ('name', 'ilike', 'Full Flow Test'),
])
if existing:
    existing.unlink()
    print("   Deleted existing test allocations")

# Create allocation
allocation = env['hr.leave.allocation'].create({
    'name': f'Full Flow Test - {employee.name} - 2026',
    'employee_id': employee.id,
    'holiday_status_id': annual_leave.id,
    'number_of_days': 24,
})
print(f"\n   ✓ Allocation created: {allocation.name}")
print(f"   - ID: {allocation.id}")
print(f"   - State: {allocation.state}")
print(f"   - Days: {allocation.number_of_days}")

# Try to approve allocation (need to be HR manager)
print("\n   Attempting to approve allocation...")
try:
    # First try action_validate (standard Odoo)
    if hasattr(allocation, 'action_validate'):
        allocation.sudo().action_validate()
        print(f"   ✓ Allocation approved via action_validate")
    elif hasattr(allocation, 'action_approve'):
        allocation.sudo().action_approve()
        print(f"   ✓ Allocation approved via action_approve")
    else:
        # Direct state change
        allocation.sudo().write({'state': 'validate'})
        print(f"   ✓ Allocation approved via direct write")
    
    print(f"   - New state: {allocation.state}")
except Exception as e:
    print(f"   ⚠️ Could not approve: {e}")
    print(f"   - Current state: {allocation.state}")

# Check allocation state
allocation.invalidate_recordset()
print(f"\n   Final allocation state: {allocation.state}")

# ============================================================
# STEP 2: Check Employee Leave Balance
# ============================================================
print("\n" + "=" * 70)
print("STEP 2: Check Employee Leave Balance")
print("=" * 70)

# Get leave balance from Odoo
leave_type_data = annual_leave.get_allocation_data(employee)
print(f"\n   Leave type allocation data:")
print(f"   {leave_type_data}")

# Also check via employee
if hasattr(employee, 'allocation_remaining_display'):
    print(f"   allocation_remaining_display: {employee.allocation_remaining_display}")

# ============================================================
# STEP 3: Create Leave Request
# ============================================================
print("\n" + "=" * 70)
print("STEP 3: Create Leave Request (hr.leave)")
print("=" * 70)

# Only proceed if allocation is validated
if allocation.state != 'validate':
    print("\n   ⚠️ Allocation not validated. Trying to create leave anyway...")

# Delete existing test leaves
existing_leaves = env['hr.leave'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
    ('private_name', 'ilike', 'Full Flow Test'),
])
if existing_leaves:
    for leave in existing_leaves:
        if leave.state != 'refuse':
            try:
                leave.action_refuse()
            except:
                pass
    existing_leaves.unlink()
    print("   Deleted existing test leaves")

# Create leave request
date_from = datetime(2026, 7, 1, 8, 0, 0)
date_to = datetime(2026, 7, 10, 17, 0, 0)

print(f"\n   Creating leave request: {date_from.date()} - {date_to.date()}")

try:
    leave = env['hr.leave'].sudo().create({
        'employee_id': employee.id,
        'holiday_status_id': annual_leave.id,
        'date_from': date_from,
        'date_to': date_to,
        'request_date_from': date_from.date(),
        'request_date_to': date_to.date(),
        'private_name': 'Full Flow Test Leave',
    })
    print(f"\n   ✓ Leave request created")
    print(f"   - ID: {leave.id}")
    print(f"   - State: {leave.state}")
    print(f"   - number_of_days: {leave.number_of_days}")
    print(f"   - calendar_days: {leave.calendar_days}")
    print(f"   - working_days: {leave.working_days}")
    
    # Check public holidays
    if hasattr(leave, '_get_public_holidays_count'):
        holidays = leave._get_public_holidays_count()
        print(f"   - Public holidays in period: {holidays}")
    
    # ============================================================
    # STEP 4: Approve Leave Request
    # ============================================================
    print("\n" + "=" * 70)
    print("STEP 4: Approve Leave Request")
    print("=" * 70)
    
    print(f"\n   Current state: {leave.state}")
    
    try:
        if leave.state == 'draft':
            leave.sudo().action_confirm()
            print(f"   ✓ Leave confirmed, state: {leave.state}")
        
        if leave.state == 'confirm':
            leave.sudo().action_validate()
            print(f"   ✓ Leave validated, state: {leave.state}")
        elif leave.state == 'validate':
            print(f"   ✓ Leave already validated")
        
    except Exception as e:
        print(f"   ⚠️ Could not approve leave: {e}")
    
    print(f"\n   Final leave state: {leave.state}")
    
    # ============================================================
    # STEP 5: Calculate Vacation Pay
    # ============================================================
    print("\n" + "=" * 70)
    print("STEP 5: Calculate Vacation Pay")
    print("=" * 70)
    
    # Set average daily salary for testing
    leave.write({'average_daily_salary': 500.0})
    
    # Trigger computation
    leave.invalidate_recordset()
    
    print(f"\n   - calendar_days: {leave.calendar_days}")
    print(f"   - average_daily_salary: {leave.average_daily_salary}")
    print(f"   - vacation_pay_amount: {leave.vacation_pay_amount}")
    print(f"   - Expected: {leave.calendar_days * 500.0}")
    
    if leave.vacation_pay_amount == leave.calendar_days * 500.0:
        print(f"   ✓ Vacation pay calculation correct!")
    else:
        print(f"   ⚠️ Vacation pay may need manual calculation")
    
    # ============================================================
    # STEP 6: Check Balance After Leave
    # ============================================================
    print("\n" + "=" * 70)
    print("STEP 6: Check Balance After Leave")
    print("=" * 70)
    
    print(f"\n   - remaining_days_before: {leave.remaining_days_before}")
    print(f"   - remaining_days_after: {leave.remaining_days_after}")
    print(f"   - number_of_days used: {leave.number_of_days}")
    
    # Check hr.vacation.balance
    balance = env['hr.vacation.balance'].search([
        ('employee_id', '=', employee.id),
        ('leave_type_id', '=', annual_leave.id),
        ('year', '=', 2026),
    ], limit=1)
    
    if balance:
        balance.invalidate_recordset()
        print(f"\n   hr.vacation.balance for 2026:")
        print(f"   - entitled_days: {balance.entitled_days}")
        print(f"   - used_days: {balance.used_days}")
        print(f"   - remaining_days: {balance.remaining_days}")
    
    # ============================================================
    # CLEANUP
    # ============================================================
    print("\n" + "=" * 70)
    print("CLEANUP")
    print("=" * 70)
    
    # Optionally clean up test data
    # leave.action_refuse()
    # leave.unlink()
    # allocation.unlink()
    print("\n   Test data kept for manual inspection")
    print(f"   - Allocation ID: {allocation.id}")
    print(f"   - Leave ID: {leave.id}")
    
except Exception as e:
    print(f"\n   ❌ Error creating leave: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("FULL FLOW TEST COMPLETE!")
print("=" * 70)
