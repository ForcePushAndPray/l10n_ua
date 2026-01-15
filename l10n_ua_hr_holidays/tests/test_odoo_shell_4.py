# Test script for Odoo shell - Part 4: Import & Translations
# Run with: ~/Projects/odoo-19/run-odoo19_shell.sh < test_odoo_shell_4.py

print("=" * 60)
print("Testing l10n_ua_hr_holidays - Part 4: Import & Translations")
print("=" * 60)

company = env.company

# 1. Test import button
print("\n" + "=" * 60)
print("1. Testing Import UA Leave Types Button")
print("=" * 60)

print(f"\n   Company: {company.name}")

# Check if method exists
if hasattr(company, 'action_import_ua_leave_types'):
    print("   ✓ action_import_ua_leave_types method exists")
    
    # Count leave types before
    before_count = env['hr.leave.type'].search_count([
        ('ua_leave_category', '!=', False),
        ('company_id', 'in', [company.id, False]),
    ])
    print(f"   - Leave types before: {before_count}")
    
    # Execute import (uncomment to test)
    # try:
    #     company.action_import_ua_leave_types()
    #     after_count = env['hr.leave.type'].search_count([
    #         ('ua_leave_category', '!=', False),
    #         ('company_id', 'in', [company.id, False]),
    #     ])
    #     print(f"   ✓ Import executed")
    #     print(f"   - Leave types after: {after_count}")
    # except Exception as e:
    #     print(f"   ✗ Import error: {e}")
else:
    print("   ✗ action_import_ua_leave_types method NOT FOUND")

# 2. Test translations
print("\n" + "=" * 60)
print("2. Testing Ukrainian Translations")
print("=" * 60)

# Check if Ukrainian language is installed
ua_lang = env['res.lang'].search([('code', '=', 'uk_UA')], limit=1)
if ua_lang:
    print(f"   ✓ Ukrainian language installed: {ua_lang.name}")
else:
    print("   ✗ Ukrainian language NOT installed")
    print("   To install: Settings → Languages → Add Ukrainian")

# Check translations for key terms
print("\n   Checking key translations...")
translations_to_check = [
    ('hr.leave.type', 'ua_leave_category', 'Категорія UA'),
    ('hr.leave', 'calendar_days', 'Календарні дні'),
    ('hr.leave', 'vacation_pay_amount', 'Сума відпускних'),
    ('hr.vacation.balance', 'entitled_days', 'Належить днів'),
    ('hr.sick.leave', 'payment_percent', 'Відсоток оплати'),
]

for model, field, expected_ua in translations_to_check:
    try:
        ir_field = env['ir.model.fields'].search([
            ('model', '=', model),
            ('name', '=', field),
        ], limit=1)
        if ir_field:
            # Check if translation exists
            trans = env['ir.translation'].search([
                ('name', '=', f'{model},{field}'),
                ('lang', '=', 'uk_UA'),
                ('type', '=', 'model'),
            ], limit=1)
            if trans:
                print(f"   ✓ {model}.{field}: {trans.value}")
            else:
                print(f"   - {model}.{field}: (no translation, using field_description)")
        else:
            print(f"   ⚠️ {model}.{field}: field not found")
    except Exception as e:
        print(f"   ✗ Error checking {model}.{field}: {e}")

# 3. Test leave type names in Ukrainian
print("\n" + "=" * 60)
print("3. Testing Leave Type Names (Ukrainian)")
print("=" * 60)

leave_types = env['hr.leave.type'].search([
    ('ua_leave_category', '!=', False),
], limit=15)

print(f"\n   Found {len(leave_types)} Ukrainian leave types:")
for lt in leave_types:
    print(f"   - {lt.name}")

# 4. Test public holiday names
print("\n" + "=" * 60)
print("4. Testing Public Holiday Names (Ukrainian)")
print("=" * 60)

holidays = env['resource.calendar.leaves'].search([
    ('resource_id', '=', False),
], limit=15, order='date_from')

print(f"\n   Found {len(holidays)} public holidays:")
for h in holidays:
    print(f"   - {h.date_from.date()}: {h.name}")

# 5. Test error messages
print("\n" + "=" * 60)
print("5. Testing Error Messages")
print("=" * 60)

# Check ValidationError messages in code
print("\n   Error messages defined in code:")
print("   - 'Employee must work at least X months before first annual leave'")
print("   - 'Employee has unused vacation days from X or earlier'")
print("   - 'Balance for this employee, leave type and year already exists'")
print("   (These should be translated in uk_UA.po)")

print("\n" + "=" * 60)
print("Part 4 Testing complete!")
print("=" * 60)
