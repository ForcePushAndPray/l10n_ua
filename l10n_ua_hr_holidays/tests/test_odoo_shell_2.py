# Test script for Odoo shell - Part 2: Odoo Workflow & Allocations
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_2.py

from datetime import datetime, timedelta

print("=" * 60)
print("Testing l10n_ua_hr_holidays - Part 2: Workflow & Allocations")
print("=" * 60)

# Get or create test data
company = env.company
print(f"\nCompany: {company.name}")

# Find or create test employee
employee = env['hr.employee'].search([('company_id', '=', company.id)], limit=1)
if not employee:
    print("\n⚠️ No employee found. Creating test employee...")
    employee = env['hr.employee'].create({
        'name': 'Test Employee UA',
        'company_id': company.id,
    })
print(f"Employee: {employee.name}")

# Find annual leave type
annual_leave = env['hr.leave.type'].search([
    ('ua_leave_category', '=', 'annual_basic'),
    ('company_id', 'in', [company.id, False]),
], limit=1)
if not annual_leave:
    annual_leave = env['hr.leave.type'].search([
        ('name', 'ilike', 'annual'),
    ], limit=1)
print(f"Leave type: {annual_leave.name if annual_leave else 'NOT FOUND'}")

# 1. Test allocation workflow
print("\n" + "=" * 60)
print("1. Testing Allocation Workflow (hr.leave.allocation)")
print("=" * 60)

if annual_leave:
    print(f"\n   requires_allocation: {annual_leave.requires_allocation}")
    
    # Check existing allocations
    existing_alloc = env['hr.leave.allocation'].search([
        ('employee_id', '=', employee.id),
        ('holiday_status_id', '=', annual_leave.id),
        ('state', '=', 'validate'),
    ])
    print(f"   Existing validated allocations: {len(existing_alloc)}")
    
    if not existing_alloc:
        print("\n   Creating new allocation...")
        try:
            allocation = env['hr.leave.allocation'].create({
                'name': 'Test Annual Allocation 2026',
                'employee_id': employee.id,
                'holiday_status_id': annual_leave.id,
                'number_of_days': 24,
            })
            print(f"   ✓ Allocation created: {allocation.name}")
            print(f"   - State: {allocation.state}")
            print(f"   - Days: {allocation.number_of_days}")
            
            # Try to approve
            if allocation.state == 'draft':
                try:
                    allocation.action_validate()
                    print(f"   ✓ Allocation approved, state: {allocation.state}")
                except Exception as e:
                    print(f"   ⚠️ Could not approve: {e}")
        except Exception as e:
            print(f"   ✗ Error creating allocation: {e}")
    else:
        allocation = existing_alloc[0]
        print(f"   Using existing allocation: {allocation.name}")
        print(f"   - Days: {allocation.number_of_days}")

# 2. Test leave request workflow
print("\n" + "=" * 60)
print("2. Testing Leave Request Workflow (hr.leave)")
print("=" * 60)

if annual_leave and employee:
    # Check employee's remaining leaves
    print(f"\n   Checking leave balance for {employee.name}...")
    
    # Create a test leave request
    date_from = datetime(2026, 7, 1, 8, 0, 0)
    date_to = datetime(2026, 7, 10, 17, 0, 0)
    
    print(f"\n   Creating leave request: {date_from.date()} - {date_to.date()}")
    
    try:
        leave = env['hr.leave'].create({
            'employee_id': employee.id,
            'holiday_status_id': annual_leave.id,
            'date_from': date_from,
            'date_to': date_to,
            'request_date_from': date_from.date(),
            'request_date_to': date_to.date(),
        })
        print(f"   ✓ Leave request created")
        print(f"   - State: {leave.state}")
        print(f"   - number_of_days: {leave.number_of_days}")
        print(f"   - calendar_days: {leave.calendar_days}")
        print(f"   - working_days: {leave.working_days}")
        print(f"   - remaining_days_before: {leave.remaining_days_before}")
        
        # Check public holidays exclusion
        holidays_in_period = leave._get_public_holidays_count()
        print(f"   - Public holidays in period: {holidays_in_period}")
        
        # Clean up - delete test leave
        leave.unlink()
        print(f"   ✓ Test leave deleted")
        
    except Exception as e:
        print(f"   ✗ Error: {e}")

# 3. Test vacation balance
print("\n" + "=" * 60)
print("3. Testing Vacation Balance (hr.vacation.balance)")
print("=" * 60)

if annual_leave and employee:
    year = 2026
    
    # Check existing balance
    balance = env['hr.vacation.balance'].search([
        ('employee_id', '=', employee.id),
        ('leave_type_id', '=', annual_leave.id),
        ('year', '=', year),
    ], limit=1)
    
    if not balance:
        print(f"\n   Creating balance for {year}...")
        try:
            balance = env['hr.vacation.balance'].create({
                'employee_id': employee.id,
                'leave_type_id': annual_leave.id,
                'year': year,
                'entitled_days': 24,
                'carried_over': 5,
            })
            print(f"   ✓ Balance created")
        except Exception as e:
            print(f"   ✗ Error: {e}")
    else:
        print(f"   Using existing balance for {year}")
    
    if balance:
        print(f"   - entitled_days: {balance.entitled_days}")
        print(f"   - carried_over: {balance.carried_over}")
        print(f"   - total_available: {balance.total_available}")
        print(f"   - used_days: {balance.used_days}")
        print(f"   - planned_days: {balance.planned_days}")
        print(f"   - remaining_days: {balance.remaining_days}")

# 4. Test vacation schedule
print("\n" + "=" * 60)
print("4. Testing Vacation Schedule (hr.vacation.schedule)")
print("=" * 60)

schedule = env['hr.vacation.schedule'].search([
    ('company_id', '=', company.id),
    ('year', '=', 2026),
], limit=1)

if schedule:
    print(f"   Found schedule: {schedule.name}")
    print(f"   - Year: {schedule.year}")
    print(f"   - State: {schedule.state}")
    print(f"   - Lines: {len(schedule.line_ids)}")
else:
    print("   No schedule found for 2026")
    print("   Creating new schedule...")
    try:
        schedule = env['hr.vacation.schedule'].create({
            'year': 2026,
            'company_id': company.id,
        })
        print(f"   ✓ Schedule created: {schedule.name}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("Part 2 Testing complete!")
print("=" * 60)
