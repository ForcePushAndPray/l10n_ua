# Test script for Odoo shell - Part 7: Remaining Checklist Items
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_7.py

from datetime import datetime, date

print("=" * 70)
print("Testing l10n_ua_hr_holidays - Part 7: Remaining Checklist Items")
print("=" * 70)

# Setup
company = env.company
employee = env['hr.employee'].search([('company_id', '=', company.id)], limit=1)
annual_leave = env['hr.leave.type'].search([('ua_leave_category', '=', 'annual_basic')], limit=1)

print(f"\nCompany: {company.name}")
print(f"Employee: {employee.name}")

# ============================================================
# 1. Check allocation_validation_type (item 3.1, 9.1)
# ============================================================
print("\n" + "=" * 70)
print("1. allocation_validation_type")
print("=" * 70)

if 'allocation_validation_type' in env['hr.leave.type']._fields:
    print(f"   ✓ Field exists on hr.leave.type")
    print(f"   Value for annual leave: {annual_leave.allocation_validation_type}")
else:
    print("   ⚠️ Field not found (may be in different Odoo version)")

# ============================================================
# 2. Check Chornobyl and Veteran leave types (item 1.3)
# ============================================================
print("\n" + "=" * 70)
print("2. Additional leave types (Chornobyl, Veterans)")
print("=" * 70)

# Search by category or by name (for existing records with old category)
chornobyl = env['hr.leave.type'].search([
    '|', ('ua_leave_category', '=', 'chornobyl'),
    ('name', 'ilike', 'чорнобил')
], limit=1)
veteran = env['hr.leave.type'].search([
    '|', ('ua_leave_category', '=', 'veteran'),
    ('name', 'ilike', 'ветеран')
], limit=1)

if chornobyl:
    print(f"   ✓ Chornobyl leave type exists: {chornobyl.name}")
    print(f"     Category: {chornobyl.ua_leave_category}, Days: {chornobyl.annual_days}")
else:
    print("   ⚠️ Chornobyl leave type not found - update module or add manually")

if veteran:
    print(f"   ✓ Veteran leave type exists: {veteran.name}")
    print(f"     Category: {veteran.ua_leave_category}, Days: {veteran.annual_days}")
else:
    print("   ⚠️ Veteran leave type not found - update module or add manually")

# ============================================================
# 3. Test vacation schedule workflow (items 8.1, 8.2, 8.3)
# ============================================================
print("\n" + "=" * 70)
print("3. Vacation Schedule Workflow")
print("=" * 70)

Schedule = env['hr.vacation.schedule']
schedule = Schedule.search([('year', '=', 2026)], limit=1)

if not schedule:
    print("   Creating schedule for 2026...")
    schedule = Schedule.create({
        'year': 2026,
        'company_id': company.id,
    })
    print(f"   ✓ Schedule created: {schedule.name}")

print(f"\n   Schedule: {schedule.name}")
print(f"   State: {schedule.state}")

# Test generate lines
print("\n   Testing action_generate_lines...")
try:
    schedule.action_generate_lines()
    print(f"   ✓ Lines generated: {len(schedule.line_ids)} lines")
except Exception as e:
    print(f"   ⚠️ Error generating lines: {e}")

# Test workflow
print("\n   Testing workflow...")
if schedule.state == 'draft':
    try:
        schedule.action_confirm()
        print(f"   ✓ Confirmed: state = {schedule.state}")
    except Exception as e:
        print(f"   ⚠️ Error confirming: {e}")

if schedule.state == 'confirmed':
    try:
        schedule.action_approve()
        print(f"   ✓ Approved: state = {schedule.state}")
        print(f"   Approval date: {schedule.approval_date}")
    except Exception as e:
        print(f"   ⚠️ Error approving: {e}")

# Reset to draft for future tests
schedule.action_draft()
print(f"   Reset to draft: state = {schedule.state}")

# ============================================================
# 4. Test leave approval (items 4.3, 9.2)
# ============================================================
print("\n" + "=" * 70)
print("4. Leave Approval Workflow")
print("=" * 70)

# Find or create allocation
allocation = env['hr.leave.allocation'].search([
    ('employee_id', '=', employee.id),
    ('holiday_status_id', '=', annual_leave.id),
    ('state', '=', 'validate'),
], limit=1)

if not allocation:
    print("   Creating allocation...")
    allocation = env['hr.leave.allocation'].create({
        'name': 'Test Allocation 2026',
        'employee_id': employee.id,
        'holiday_status_id': annual_leave.id,
        'number_of_days': 24,
    })
    # Use correct method name for Odoo 19
    if hasattr(allocation, 'action_validate'):
        allocation.action_validate()
    elif hasattr(allocation, '_action_validate'):
        allocation._action_validate()
    elif hasattr(allocation, 'action_confirm'):
        allocation.action_confirm()
    print(f"   ✓ Allocation created and validated")

# Create leave request
print("\n   Creating leave request...")
try:
    leave = env['hr.leave'].create({
        'employee_id': employee.id,
        'holiday_status_id': annual_leave.id,
        'date_from': '2026-08-01 08:00:00',
        'date_to': '2026-08-10 17:00:00',
        'request_date_from': '2026-08-01',
        'request_date_to': '2026-08-10',
    })
    print(f"   ✓ Leave created: ID={leave.id}, state={leave.state}")
    print(f"   number_of_days: {leave.number_of_days}")
    print(f"   calendar_days: {leave.calendar_days}")
    
    # Approve leave
    print("\n   Approving leave...")
    if leave.state == 'draft':
        leave.action_confirm()
        print(f"   Confirmed: state = {leave.state}")
    
    if leave.state == 'confirm':
        # Use correct method name for Odoo 19
        if hasattr(leave, 'action_validate'):
            leave.action_validate()
        elif hasattr(leave, '_action_validate'):
            leave._action_validate()
        elif hasattr(leave, 'action_approve'):
            leave.action_approve()
        print(f"   ✓ Validated: state = {leave.state}")
    
    # Check balance update
    balance = env['hr.vacation.balance'].search([
        ('employee_id', '=', employee.id),
        ('leave_type_id', '=', annual_leave.id),
        ('year', '=', 2026),
    ], limit=1)
    
    if balance:
        balance.invalidate_recordset()
        print(f"\n   Balance after approval:")
        print(f"   - used_days: {balance.used_days}")
        print(f"   - remaining_days: {balance.remaining_days}")
    
    # Cleanup - cancel leave
    if leave.state == 'validate':
        if hasattr(leave, 'action_refuse'):
            leave.action_refuse()
        elif hasattr(leave, '_action_refuse'):
            leave._action_refuse()
        print(f"\n   Leave refused for cleanup: state = {leave.state}")
        
except Exception as e:
    print(f"   ⚠️ Error: {e}")

# ============================================================
# 5. Test compensation calculation (items 6.1, 6.2)
# ============================================================
print("\n" + "=" * 70)
print("5. Compensation Calculation")
print("=" * 70)

Balance = env['hr.vacation.balance']
test_balance = Balance.search([
    ('employee_id', '=', employee.id),
    ('leave_type_id', '=', annual_leave.id),
], limit=1)

# Create balance if not exists
if not test_balance:
    print("   Creating balance for testing...")
    test_balance = Balance.create({
        'employee_id': employee.id,
        'leave_type_id': annual_leave.id,
        'year': 2026,
        'entitled_days': 24,
        'carried_over': 5,
    })
    print(f"   ✓ Balance created: ID={test_balance.id}")

if test_balance and hasattr(Balance, 'calculate_compensation'):
    print(f"   Balance: entitled={test_balance.entitled_days}, used={test_balance.used_days}, remaining={test_balance.remaining_days}")
    
    # Test termination compensation
    print("\n   Testing termination compensation (all days)...")
    try:
        result = test_balance.calculate_compensation(is_termination=True)
        print(f"   ✓ Termination compensation: {result}")
        print(f"   Expected: remaining_days × СДЗ = {test_balance.remaining_days} × СДЗ")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
    
    # Test non-termination compensation
    print("\n   Testing non-termination compensation (days over 24)...")
    try:
        result = test_balance.calculate_compensation(is_termination=False)
        print(f"   ✓ Non-termination compensation: {result}")
        if test_balance.used_days < 24:
            print(f"   Note: used_days ({test_balance.used_days}) < 24, so compensation = 0")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
else:
    print("   ⚠️ Balance not found or calculate_compensation method missing")

# ============================================================
# 6. Test import leave types (item 10.1)
# ============================================================
print("\n" + "=" * 70)
print("6. Import Leave Types")
print("=" * 70)

if hasattr(env['res.company'], 'action_import_ua_leave_types'):
    print("   ✓ action_import_ua_leave_types method exists")
    # Don't actually run it to avoid duplicates
else:
    print("   ⚠️ Method not found on res.company")

# ============================================================
# 7. Check resource_id = False for public holidays (item 12.3)
# ============================================================
print("\n" + "=" * 70)
print("7. Public Holidays resource_id Check")
print("=" * 70)

public_holidays = env['resource.calendar.leaves'].search([
    ('resource_id', '=', False),
    ('date_from', '>=', '2025-01-01'),
])
print(f"   Public holidays with resource_id=False: {len(public_holidays)}")

wrong_holidays = env['resource.calendar.leaves'].search([
    ('resource_id', '!=', False),
    ('name', 'ilike', '%свят%'),
])
if wrong_holidays:
    print(f"   ⚠️ Found {len(wrong_holidays)} holidays with resource_id set (should be False)")
else:
    print("   ✓ All holidays have resource_id=False")

# ============================================================
# 8. Check l10n_ua_hr_contract integration (hr.version)
# ============================================================
print("\n" + "=" * 70)
print("8. l10n_ua_hr_contract Integration Check (hr.version)")
print("=" * 70)

try:
    Version = env['hr.version']
    print("   ✓ hr.version model exists")

    version = employee.current_version_id
    if version:
        print(f"   ✓ Current version found: {version.name}")
        print(f"   - contract_date_start: {version.contract_date_start}")
        print(f"   - wage: {version.wage}")

        # Check Ukrainian fields if l10n_ua_hr_contract installed
        if hasattr(version, 'contract_type_ua'):
            print(f"   - contract_type_ua: {version.contract_type_ua}")
            print(f"   - is_main_workplace: {version.is_main_workplace}")
            print(f"   - work_mode: {version.work_mode}")
            print("   ✓ Ukrainian contract fields available")
        else:
            print("   ⚠️ Ukrainian contract fields not found (l10n_ua_hr_contract not installed)")

        # Check experience calculation
        if version.contract_date_start:
            from dateutil.relativedelta import relativedelta
            today = date.today()
            experience = relativedelta(today, version.contract_date_start)
            months = experience.years * 12 + experience.months
            print(f"   - Experience: {months} months ({experience.years} years, {experience.months} months)")
    else:
        print("   ⚠️ No current version for employee")
except KeyError:
    print("   ⚠️ hr.version not found")

# ============================================================
# 9. Check l10n_ua_hr_salary integration
# ============================================================
print("\n" + "=" * 70)
print("9. l10n_ua_hr_salary Integration Check")
print("=" * 70)

try:
    Payslip = env['hr.payslip']
    print("   ✓ hr.payslip model exists (l10n_ua_hr_salary installed)")
    
    payslips = Payslip.search([('employee_id', '=', employee.id)], limit=5)
    if not payslips:
        print("   Creating demo payslip...")
        payslip = Payslip.create({
            'name': f'Payslip {employee.name} 12/2025',
            'employee_id': employee.id,
            'date_from': '2025-12-01',
            'date_to': '2025-12-31',
        })
        print(f"   ✓ Demo payslip created: {payslip.name}")
        payslips = payslip
    
    print(f"   ✓ Found {len(payslips)} payslips for employee")
    
    # Calculate total earnings for last 12 months
    from datetime import timedelta
    year_ago = date.today() - timedelta(days=365)
    recent_payslips = Payslip.search([
        ('employee_id', '=', employee.id),
        ('date_from', '>=', year_ago.isoformat()),
        ('state', '=', 'done'),
    ])
    if recent_payslips:
        total_gross = sum(recent_payslips.mapped('gross_salary'))
        print(f"   Total gross for last 12 months: {total_gross}")
    else:
        print("   Note: No confirmed payslips in last 12 months (need to confirm payslip)")
except KeyError:
    print("   ⚠️ hr.payslip not found (l10n_ua_hr_salary not installed)")

print("\n" + "=" * 70)
print("Part 7 Testing complete!")
print("=" * 70)
