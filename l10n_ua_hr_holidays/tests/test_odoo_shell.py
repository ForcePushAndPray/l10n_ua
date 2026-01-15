# Test script for Odoo shell
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell.py

print("=" * 60)
print("Testing l10n_ua_hr_holidays module - FULL")
print("=" * 60)

# 1. Test leave types - detailed
print("\n1. Testing leave types (detailed)...")
leave_types = env['hr.leave.type'].search([('ua_leave_category', '!=', False)])
print(f"   Found {len(leave_types)} Ukrainian leave types")

# Check specific categories
categories = {
    'annual_basic': 'Щорічна основна',
    'annual_additional': 'Щорічна додаткова',
    'annual_hazardous': 'За шкідливі умови',
    'annual_special': 'За особливий характер',
    'annual_irregular': 'За ненормований день',
    'social_children': 'Соціальна на дітей',
    'educational': 'Навчальна',
    'creative': 'Творча',
    'unpaid': 'Без збереження',
    'maternity': 'Декретна',
    'childcare': 'По догляду за дитиною',
    'sick': 'Лікарняний',
}
for cat, name in categories.items():
    lt = env['hr.leave.type'].search([('ua_leave_category', '=', cat)], limit=1)
    if lt:
        print(f"   ✓ {name} ({cat}): {lt.annual_days} днів")
    else:
        print(f"   ✗ {name} ({cat}) - НЕ ЗНАЙДЕНО")

# Check annual_basic settings
print("\n   Перевірка налаштувань щорічної основної:")
annual = env['hr.leave.type'].search([('ua_leave_category', '=', 'annual_basic')], limit=1)
if annual:
    print(f"   - is_calendar_days: {annual.is_calendar_days}")
    print(f"   - is_transferable: {annual.is_transferable}")
    print(f"   - min_continuous_days: {annual.min_continuous_days}")
    print(f"   - requires_experience: {annual.requires_experience}")
    print(f"   - min_experience_months: {annual.min_experience_months}")
    print(f"   - payment_source: {annual.payment_source}")
    print(f"   - max_carryover_years: {annual.max_carryover_years}")

# 2. Test public holidays - all
print("\n2. Testing public holidays (all)...")
holidays = env['resource.calendar.leaves'].search([('resource_id', '=', False)], order='date_from')
print(f"   Found {len(holidays)} public holidays:")
for h in holidays:
    print(f"   - {h.date_from.date()}: {h.name}")

# 3. Test hr.leave.type fields
print("\n3. Testing hr.leave.type Ukrainian fields...")
lt_model = env['hr.leave.type']
ua_lt_fields = ['ua_leave_category', 'annual_days', 'is_calendar_days', 'is_transferable',
                'max_transfer_days', 'requires_experience', 'min_experience_months',
                'is_paid', 'payment_source', 'min_continuous_days', 'max_carryover_years',
                'max_additional_days']
for field in ua_lt_fields:
    if field in lt_model._fields:
        print(f"   ✓ {field}")
    else:
        print(f"   ✗ {field} - MISSING")

# 4. Test vacation balance model fields
print("\n4. Testing hr.vacation.balance fields...")
balance_model = env['hr.vacation.balance']
balance_fields = ['employee_id', 'leave_type_id', 'year', 'entitled_days', 'carried_over',
                  'total_available', 'used_days', 'planned_days', 'remaining_days']
for field in balance_fields:
    if field in balance_model._fields:
        print(f"   ✓ {field}")
    else:
        print(f"   ✗ {field} - MISSING")

# 5. Test sick leave model fields
print("\n5. Testing hr.sick.leave fields...")
sick_model = env['hr.sick.leave']
sick_fields = ['employee_id', 'sick_leave_number', 'is_electronic', 'e_sick_leave_id',
               'sick_leave_type', 'diagnosis_code', 'insurance_experience_years',
               'payment_percent', 'average_daily_salary', 'employer_days', 'employer_amount',
               'fss_days', 'fss_amount', 'total_amount', 'state']
for field in sick_fields:
    if field in sick_model._fields:
        print(f"   ✓ {field}")
    else:
        print(f"   ✗ {field} - MISSING")

# 6. Test hr.leave Ukrainian fields
print("\n6. Testing hr.leave Ukrainian fields...")
leave_model = env['hr.leave']
ua_fields = ['calendar_days', 'working_days', 'average_daily_salary', 
             'vacation_pay_amount', 'remaining_days_before', 'remaining_days_after',
             'vacation_year', 'order_number', 'order_date']
for field in ua_fields:
    if field in leave_model._fields:
        print(f"   ✓ {field}")
    else:
        print(f"   ✗ {field} - MISSING")

# 7. Test public holiday exclusion
print("\n7. Testing public holiday exclusion...")
from datetime import datetime
test_leave = env['hr.leave'].new({
    'date_from': datetime(2025, 1, 1, 8, 0, 0),
    'date_to': datetime(2025, 1, 7, 17, 0, 0),
})
if hasattr(test_leave, '_get_public_holidays_count'):
    holidays_count = test_leave._get_public_holidays_count()
    print(f"   Public holidays in Jan 1-7, 2025: {holidays_count}")
    print(f"   Expected: 2 (Jan 1 and Jan 7)")
else:
    print("   _get_public_holidays_count method not found")

# 8. Test vacation schedule model
print("\n8. Testing hr.vacation.schedule...")
schedule_model = env['hr.vacation.schedule']
schedule_fields = ['name', 'year', 'company_id', 'state', 'line_ids', 'approval_date']
for field in schedule_fields:
    if field in schedule_model._fields:
        print(f"   ✓ {field}")
    else:
        print(f"   ✗ {field} - MISSING")

# 9. Test sick leave types
print("\n9. Testing sick leave types...")
sick_leave_types = [
    ('illness', 'Захворювання'),
    ('injury', 'Травма'),
    ('child_care', 'Догляд за дитиною'),
    ('pregnancy', 'Вагітність та пологи'),
    ('quarantine', 'Карантин'),
    ('prosthetics', 'Протезування'),
    ('sanatorium', 'Санаторне лікування'),
]
sick = env['hr.sick.leave']
if 'sick_leave_type' in sick._fields:
    selection = sick._fields['sick_leave_type'].selection
    if callable(selection):
        selection = selection(sick)
    for code, name in sick_leave_types:
        if any(s[0] == code for s in selection):
            print(f"   ✓ {name} ({code})")
        else:
            print(f"   ✗ {name} ({code}) - НЕ ЗНАЙДЕНО")

# 10. Test company import button
print("\n10. Testing company import button...")
company_model = env['res.company']
if hasattr(company_model, 'action_import_ua_leave_types'):
    print("   ✓ action_import_ua_leave_types method exists")
else:
    print("   ✗ action_import_ua_leave_types method NOT FOUND")

print("\n" + "=" * 60)
print("Testing complete!")
print("=" * 60)
