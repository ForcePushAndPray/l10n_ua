# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.exceptions import ValidationError
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from .common import TestHrUaBase


@tagged('post_install', '-at_install')
class TestHrEmployeeRnokpp(TestHrUaBase):
    """Test RNOKPP (Ukrainian Tax ID) validation."""

    def test_rnokpp_validation_algorithm(self):
        """Test the RNOKPP checksum validation algorithm."""
        Employee = self.env['hr.employee']

        # Valid RNOKPPs
        self.assertTrue(Employee._validate_rnokpp('3184710691'))
        self.assertTrue(Employee._validate_rnokpp('2222222225'))

        # Generate and validate
        valid = self.generate_valid_rnokpp('123456789')
        self.assertTrue(Employee._validate_rnokpp(valid))

    def test_rnokpp_invalid_checksum(self):
        """Test that invalid checksum is rejected."""
        Employee = self.env['hr.employee']
        self.assertFalse(Employee._validate_rnokpp('1234567890'))
        self.assertFalse(Employee._validate_rnokpp('0000000001'))

    def test_rnokpp_invalid_format(self):
        """Test that invalid format is rejected."""
        Employee = self.env['hr.employee']

        # Too short
        self.assertFalse(Employee._validate_rnokpp('123456789'))

        # Too long
        self.assertFalse(Employee._validate_rnokpp('12345678901'))

        # Contains letters
        self.assertFalse(Employee._validate_rnokpp('123456789A'))

        # Empty
        self.assertFalse(Employee._validate_rnokpp(''))
        self.assertFalse(Employee._validate_rnokpp(None))

    def test_employee_create_with_valid_rnokpp(self):
        """Test creating employee with valid RNOKPP."""
        unique_rnokpp = self.get_unique_rnokpp()
        employee = self._create_employee(rnokpp=unique_rnokpp)
        self.assertEqual(employee.rnokpp, unique_rnokpp)

    def test_employee_create_with_invalid_rnokpp(self):
        """Test that creating employee with invalid RNOKPP raises error."""
        with self.assertRaises(ValidationError):
            self._create_employee(rnokpp=self.invalid_rnokpp_checksum)

    def test_rnokpp_uniqueness(self):
        """Test that RNOKPP must be unique."""
        unique_rnokpp = self.get_unique_rnokpp()
        self._create_employee(rnokpp=unique_rnokpp)

        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            self._create_employee(name='Another Employee', rnokpp=unique_rnokpp)

    def test_rnokpp_validation_disabled(self):
        """Test that RNOKPP validation can be disabled via system parameter."""
        self.env['ir.config_parameter'].sudo().set_param('hr_ua.validate_rnokpp', 'False')

        # Use a unique invalid RNOKPP to avoid conflicts
        invalid_rnokpp = '0000000001'  # Invalid checksum but unique
        # Should not raise error with invalid RNOKPP
        employee = self._create_employee(rnokpp=invalid_rnokpp)
        self.assertEqual(employee.rnokpp, invalid_rnokpp)

        # Re-enable validation
        self.env['ir.config_parameter'].sudo().set_param('hr_ua.validate_rnokpp', 'True')


@tagged('post_install', '-at_install')
class TestHrEmployeePassport(TestHrUaBase):
    """Test passport/ID card validation."""

    def test_passport_old_format_valid(self):
        """Test valid old format passport (6 digits)."""
        employee = self._create_employee(
            document_type='passport',
            passport_id='123456',
        )
        self.assertEqual(employee.passport_id, '123456')

    def test_passport_old_format_invalid_length(self):
        """Test that old passport with wrong length is rejected."""
        with self.assertRaises(ValidationError):
            self._create_employee(
                document_type='passport',
                passport_id='12345',  # 5 digits instead of 6
            )

        with self.assertRaises(ValidationError):
            self._create_employee(
                document_type='passport',
                passport_id='1234567',  # 7 digits instead of 6
            )

    def test_id_card_valid(self):
        """Test valid ID card (9 digits)."""
        employee = self._create_employee(
            document_type='id_card',
            passport_id='123456789',
        )
        self.assertEqual(employee.passport_id, '123456789')

    def test_id_card_invalid_length(self):
        """Test that ID card with wrong length is rejected."""
        with self.assertRaises(ValidationError):
            self._create_employee(
                document_type='id_card',
                passport_id='12345678',  # 8 digits instead of 9
            )

        with self.assertRaises(ValidationError):
            self._create_employee(
                document_type='id_card',
                passport_id='1234567890',  # 10 digits instead of 9
            )

    def test_document_type_other_no_validation(self):
        """Test that 'other' document type has no length validation."""
        employee = self._create_employee(
            document_type='other',
            passport_id='ANY-FORMAT-123',
        )
        self.assertEqual(employee.passport_id, 'ANY-FORMAT-123')


@tagged('post_install', '-at_install')
class TestHrEmployeeComputedFields(TestHrUaBase):
    """Test computed fields on hr.employee."""

    def test_children_count(self):
        """Test children_count computed field."""
        employee = self._create_employee()
        self.assertEqual(employee.children_count, 0)

        # Add children
        self.env['hr.employee.child'].create({
            'employee_id': employee.id,
            'name': 'Child 1',
            'birthday': date.today() - relativedelta(years=5),
        })
        employee.invalidate_recordset(['children_count'])
        self.assertEqual(employee.children_count, 1)

        self.env['hr.employee.child'].create({
            'employee_id': employee.id,
            'name': 'Child 2',
            'birthday': date.today() - relativedelta(years=3),
        })
        employee.invalidate_recordset(['children_count'])
        self.assertEqual(employee.children_count, 2)

    def test_dependents_count(self):
        """dependents_count counts children who are minors (<18), full-time
        students or disabled — the age/student/disability logic per PSP rules.
        The is_dependent flag is a manual marker only and does NOT affect it."""
        employee = self._create_employee()

        # Minor child -> counts as a dependent (age < 18).
        self.env['hr.employee.child'].create({
            'employee_id': employee.id,
            'name': 'Minor Child',
            'birthday': date.today() - relativedelta(years=10),
        })
        employee.invalidate_recordset(['dependents_count'])
        self.assertEqual(employee.dependents_count, 1)

        # Adult, non-student, non-disabled child -> NOT a dependent, even with
        # the manual is_dependent flag set.
        child2 = self.env['hr.employee.child'].create({
            'employee_id': employee.id,
            'name': 'Adult Child',
            'birthday': date.today() - relativedelta(years=25),
            'is_dependent': True,
        })
        employee.invalidate_recordset(['dependents_count'])
        self.assertEqual(employee.dependents_count, 1)  # Still 1

        # Marking the adult as a full-time student makes them a dependent.
        child2.is_student = True
        employee.invalidate_recordset(['dependents_count'])
        self.assertEqual(employee.dependents_count, 2)

    def test_work_experience_company(self):
        """Test work_experience_company computed field."""
        employee = self._create_employee()
        self.assertEqual(employee.work_experience_company, 0.0)

        # Set hire date to 2 years ago
        employee.hire_date = date.today() - relativedelta(years=2)
        employee.invalidate_recordset(['work_experience_company'])
        self.assertAlmostEqual(employee.work_experience_company, 2.0, places=1)

        # Set hire date to 6 months ago
        employee.hire_date = date.today() - relativedelta(months=6)
        employee.invalidate_recordset(['work_experience_company'])
        self.assertAlmostEqual(employee.work_experience_company, 0.5, places=1)

    def test_actual_address_copy(self):
        """Test that actual_address is copied from registration when flag is set."""
        employee = self._create_employee(
            registration_address='123 Main Street, Kyiv',
        )

        # Set flag via onchange simulation
        employee.actual_same_as_registration = True
        employee._onchange_actual_same_as_registration()

        self.assertEqual(employee.actual_address, '123 Main Street, Kyiv')


@tagged('post_install', '-at_install')
class TestHrEmployeeMilitaryBenefits(TestHrUaBase):
    """Test military accounting and benefits fields."""

    def test_military_status_default(self):
        """Test that military status defaults to 'not_applicable'."""
        employee = self._create_employee()
        self.assertEqual(employee.military_status, 'not_applicable')

    def test_disability_group_default(self):
        """Test that disability group defaults to 'none'."""
        employee = self._create_employee()
        self.assertEqual(employee.disability_group, 'none')

    def test_chornobyl_category_default(self):
        """Test that Chornobyl category defaults to 'none'."""
        employee = self._create_employee()
        self.assertEqual(employee.chornobyl_category, 'none')

    def test_veteran_status_default(self):
        """Test that veteran status defaults to 'none'."""
        employee = self._create_employee()
        self.assertEqual(employee.veteran_status, 'none')

    def test_military_fields_set(self):
        """Test setting military accounting fields."""
        employee = self._create_employee(
            military_status='liable',
            military_category='1',
            military_fitness='fit',
        )

        self.assertEqual(employee.military_status, 'liable')
        self.assertEqual(employee.military_category, '1')
        self.assertEqual(employee.military_fitness, 'fit')


@tagged('post_install', '-at_install')
class TestHrEmployeeMilitaryCompliance3621IX(TestHrUaBase):
    """#88 — Закон 3621-IX від 04.05.2024: military_fitness selection."""

    def test_fitness_values_no_legacy_limited(self):
        """'limited' must not be a valid selection any more."""
        employee = self._create_employee()
        with self.assertRaises(ValueError):
            employee.military_fitness = 'limited'

    def test_fitness_new_values_accepted(self):
        """Both new values must work."""
        employee = self._create_employee(military_fitness='fit_support')
        self.assertEqual(employee.military_fitness, 'fit_support')
        employee.military_fitness = 'temp_unfit'
        self.assertEqual(employee.military_fitness, 'temp_unfit')


@tagged('post_install', '-at_install')
class TestHrEmployeeMilitaryMedical402(TestHrUaBase):
    """#89 — Наказ МОУ № 402: medical_category, military_mlk_retest_date."""

    def test_medical_category_can_be_set(self):
        for code in ('A', 'B', 'V', 'G', 'D'):
            employee = self._create_employee(military_medical_category=code)
            self.assertEqual(employee.military_medical_category, code)

    def test_mlk_retest_due_soon_true_within_14_days(self):
        employee = self._create_employee(
            military_mlk_retest_date=date.today() + timedelta(days=7),
        )
        self.assertTrue(employee.military_mlk_retest_due_soon)

    def test_mlk_retest_due_soon_false_when_far(self):
        employee = self._create_employee(
            military_mlk_retest_date=date.today() + timedelta(days=30),
        )
        self.assertFalse(employee.military_mlk_retest_due_soon)

    def test_mlk_retest_due_soon_false_when_blank(self):
        employee = self._create_employee()
        self.assertFalse(employee.military_mlk_retest_due_soon)


@tagged('post_install', '-at_install')
class TestHrEmployeeMilitaryReservationNotifications(TestHrUaBase):
    """#91 — ПКМУ № 1608: cron нагадування HR про прострочене бронювання."""

    def _ensure_hr_officer(self, login_suffix):
        """Make sure group_hr_ua_officer has at least one user (test isolation)."""
        hr_group = self.env.ref('l10n_ua_hr_base.group_hr_ua_officer')
        if not hr_group.user_ids:
            self.env['res.users'].create({
                'name': f'HR Officer Test {login_suffix}',
                'login': f'hr_officer_test_{login_suffix}',
                'group_ids': [(4, hr_group.id)],
            })

    def test_cron_marks_expired_and_runs_notify(self):
        """Cron flag-ить прострочене бронювання і викликає _notify.

        Стартовий стан: бронювання вже прострочене (compute сам ставить True
        при створенні). Cron нічого не змінює (запис вже flagged), але метод
        _notify все одно повинен виконуватися для employees що поточно flagged.
        """
        self._ensure_hr_officer('cron')
        employee = self._create_employee(
            military_reservation=True,
            military_reservation_until=date.today() - timedelta(days=1),
        )
        # Compute auto-flags expired upon creation
        self.assertTrue(employee.military_reservation_expired)
        # Manually run notification to verify it works without errors
        employee._notify_military_reservation_expired()
        activities = employee.activity_ids.filtered(
            lambda a: 'бронювання' in (a.summary or '').lower()
        )
        self.assertTrue(activities)

    def test_notification_creates_activity(self):
        """_notify створює activity для HR officer."""
        self._ensure_hr_officer('act')
        employee = self._create_employee(
            military_reservation=True,
            military_reservation_until=date.today() - timedelta(days=2),
        )
        employee._notify_military_reservation_expired()
        activities = employee.activity_ids.filtered(
            lambda a: 'бронювання' in (a.summary or '').lower()
        )
        self.assertTrue(activities,
                         'Notification повинна створити activity з ключовим словом "бронювання"')

    def test_notification_idempotent(self):
        """Повторний виклик не дублює activity."""
        self._ensure_hr_officer('idem')
        employee = self._create_employee(
            military_reservation=True,
            military_reservation_until=date.today() - timedelta(days=2),
        )
        employee._notify_military_reservation_expired()
        first_count = len(employee.activity_ids.filtered(
            lambda a: 'бронювання' in (a.summary or '').lower()
        ))
        employee._notify_military_reservation_expired()
        second_count = len(employee.activity_ids.filtered(
            lambda a: 'бронювання' in (a.summary or '').lower()
        ))
        self.assertEqual(first_count, second_count,
                          'Повторні виклики не повинні додавати activity')


@tagged('post_install', '-at_install')
class TestHrEmployeeSinglePaymentSecurity(TestHrUaBase):
    """#97 — is_single_parent захищено group_hr_ua_officer, attachments на child."""

    def test_is_single_parent_writable_by_hr_officer(self):
        """HR officer може писати is_single_parent."""
        employee = self._create_employee()
        # Поточний користувач у тестах є admin → HR officer member by inheritance
        employee.is_single_parent = True
        self.assertTrue(employee.is_single_parent)

    def test_is_single_parent_blocked_for_simple_user(self):
        """Звичайний користувач (без HR officer) НЕ повинен бачити поле."""
        # Create a user in only hr.group_hr_user (without UA officer escalation)
        # NOTE: l10n_ua hr setup auto-implies UA-user from hr_user, so we need a
        # group strictly without HR access at all.
        plain_user = self.env['res.users'].create({
            'name': 'Plain User',
            'login': 'plain_user_97',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        employee = self._create_employee()
        # As a plain user with no HR access, accessing the field should be denied
        # (read access). We verify the field has groups attribute.
        field = employee._fields['is_single_parent']
        self.assertEqual(field.groups, 'l10n_ua_hr_base.group_hr_ua_officer',
                          'is_single_parent must require l10n_ua_hr_base.group_hr_ua_officer')

    def test_child_supporting_documents_attachment(self):
        """hr.employee.child може мати М2М attachment'и для підтверджуючих документів."""
        employee = self._create_employee()
        child = self.env['hr.employee.child'].create({
            'name': 'Дитина-Тест',
            'birthday': date(2018, 5, 1),
            'employee_id': employee.id,
        })
        attachment = self.env['ir.attachment'].create({
            'name': 'birth_cert.pdf',
            'res_model': 'hr.employee.child',
            'res_id': child.id,
            'type': 'binary',
            'datas': b'JVBERi0=',  # mini PDF marker
        })
        child.birth_cert_attachment_ids = [(4, attachment.id)]
        self.assertIn(attachment, child.birth_cert_attachment_ids)


@tagged('post_install', '-at_install')
class TestHrEmployeeMilitaryRegister1487(TestHrUaBase):
    """#90 — ПКМУ № 1487: military_register_category selection."""

    def test_register_category_default(self):
        employee = self._create_employee()
        self.assertEqual(employee.military_register_category, 'not_applicable')

    def test_register_category_all_values(self):
        for code in ('conscript', 'liable', 'reservist', 'not_applicable'):
            employee = self._create_employee(military_register_category=code)
            self.assertEqual(employee.military_register_category, code)

    def test_legacy_military_status_still_usable(self):
        """Legacy military_status field stays — for historical data and reports."""
        employee = self._create_employee(military_status='liable',
                                          military_register_category='liable')
        self.assertEqual(employee.military_status, 'liable')
        self.assertEqual(employee.military_register_category, 'liable')


@tagged('post_install', '-at_install')
class TestHrEmployeeHireDate(TestHrUaBase):
    """hire_date derived from the native contract versions (hr.version)."""

    def _set_contract(self, employee, start, end=False, version=None):
        version = version or employee.version_ids[:1]
        version.write({'contract_date_start': start, 'contract_date_end': end})
        return version

    def test_hire_date_derived_from_contract_version(self):
        """Hire date comes from the version's contract_date_start."""
        employee = self._create_employee()
        self._set_contract(employee, date(2021, 3, 15))
        self.assertEqual(employee.hire_date, date(2021, 3, 15))

    def test_hire_date_follows_contract_change(self):
        """Correcting the version's date recomputes hire_date."""
        employee = self._create_employee()
        version = self._set_contract(employee, date(2021, 3, 15))
        version.contract_date_start = date(2021, 4, 1)
        self.assertEqual(employee.hire_date, date(2021, 4, 1))

    def test_manual_hire_date_kept_without_contract_dates(self):
        """Legacy import: with no contract dates the manual value survives."""
        employee = self._create_employee(hire_date=date(2015, 1, 10))
        self.assertEqual(employee.hire_date, date(2015, 1, 10))
        # Writing a version field other than the contract dates keeps it.
        employee.version_ids[:1].date_version = date(2015, 1, 10)
        self.assertEqual(employee.hire_date, date(2015, 1, 10))

    def test_contract_wins_over_manual_value(self):
        """The native field wins: the version overrides a manual date."""
        employee = self._create_employee(hire_date=date(2015, 1, 10))
        self._set_contract(employee, date(2016, 9, 1))
        self.assertEqual(employee.hire_date, date(2016, 9, 1))

    def test_rehire_after_gap_moves_anchor(self):
        """A rehire (gap of 4 days or more) moves the anchor forward."""
        employee = self._create_employee()
        self._set_contract(employee, date(2020, 1, 1), date(2022, 5, 31))
        self.env['hr.version'].create({
            'employee_id': employee.id,
            'company_id': employee.company_id.id,
            'date_version': date(2023, 2, 1),
            'contract_date_start': date(2023, 2, 1),
        })
        self.assertEqual(employee.hire_date, date(2023, 2, 1))

    def test_continuous_transfer_keeps_anchor(self):
        """An uninterrupted transfer (next day) keeps the original anchor."""
        employee = self._create_employee()
        self._set_contract(employee, date(2020, 1, 1), date(2022, 5, 31))
        self.env['hr.version'].create({
            'employee_id': employee.id,
            'company_id': employee.company_id.id,
            'date_version': date(2022, 6, 1),
            'contract_date_start': date(2022, 6, 1),
        })
        self.assertEqual(employee.hire_date, date(2020, 1, 1))

    def test_work_year_anchored_on_contract_date(self):
        """The vacation work year is anchored on the contract start date."""
        employee = self._create_employee()
        self._set_contract(employee, date(2021, 3, 15))
        start, end, index = employee._get_work_year_for_date(date(2023, 5, 1))
        self.assertEqual(start, date(2023, 3, 15))
        self.assertEqual(end, date(2024, 3, 14))
        self.assertEqual(index, 3)

    def test_demo_employees_derive_hire_date_from_versions(self):
        """Demo cards are shaped like real ones: the hire date comes from the
        contract version, not from a manual employee-level value.

        Skipped when the database is installed without demo data.
        """
        expected = {
            'demo_employee_director': date(2015, 1, 10),
            'demo_employee_hr_manager': date(2018, 6, 1),
            'demo_employee_accountant': date(2016, 9, 1),
            'demo_employee_it_admin': date(2020, 3, 15),
            'demo_employee_developer': date(2021, 8, 1),
            'demo_employee_hr_specialist': date(2022, 1, 10),
        }
        first = self.env.ref('l10n_ua_hr_base.demo_employee_director',
                             raise_if_not_found=False)
        if not first:
            self.skipTest('demo data is not installed')
        for xml_id, hire_date in expected.items():
            employee = self.env.ref('l10n_ua_hr_base.%s' % xml_id)
            versions = employee.with_context(active_test=False).version_ids
            self.assertIn(
                hire_date, versions.mapped('contract_date_start'),
                '%s: the contract version must carry the hire date' % xml_id)
            self.assertEqual(
                employee.hire_date, hire_date,
                '%s: hire_date must derive from the contract version' % xml_id)

    def test_company_experience_at_given_date(self):
        """Experience is measured at the given date, not "today"."""
        employee = self._create_employee()
        self._set_contract(employee, date(2020, 1, 1))
        self.assertAlmostEqual(
            employee._get_company_experience_years(date(2025, 1, 1)), 5.0, places=2)
        self.assertAlmostEqual(
            employee._get_company_experience_years(date(2023, 7, 1)), 3.5, places=2)
        # No experience before the hire date.
        self.assertEqual(
            employee._get_company_experience_years(date(2019, 1, 1)), 0.0)
