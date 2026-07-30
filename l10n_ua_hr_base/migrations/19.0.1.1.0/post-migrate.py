import logging
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migration script for l10n_ua_hr_base 19.0.1.1.0.

    Migrates legacy employee addresses (registration_* & actual_address) into
    native Odoo 19 private_* fields and ensures registration_same_as_actual flag
    is accurately populated from legacy actual_same_as_registration.
    """
    _logger.info("Starting post-migration address data migration for l10n_ua_hr_base 19.0.1.1.0...")

    if not column_exists(cr, 'hr_employee', 'actual_same_as_registration'):
        _logger.info("Legacy column actual_same_as_registration not found. Skipping migration.")
        return

    # Step 1: Populate registration_street from legacy registration_address text field if empty
    if column_exists(cr, 'hr_employee', 'registration_address') and column_exists(cr, 'hr_employee', 'registration_street'):
        cr.execute("""
            UPDATE hr_employee
            SET registration_street = registration_address
            WHERE (registration_street IS NULL OR registration_street = '')
              AND registration_address IS NOT NULL AND registration_address != '';
        """)

    # Step 2: Copy registration address into hr_version private_* fields when flag was True
    cr.execute("""
        UPDATE hr_version v
        SET
            private_street = COALESCE(v.private_street, e.registration_street, e.registration_address),
            private_city = COALESCE(v.private_city, e.registration_city),
            private_zip = COALESCE(v.private_zip, e.registration_zip),
            private_state_id = COALESCE(v.private_state_id, e.registration_region_id)
        FROM hr_employee e
        WHERE v.employee_id = e.id 
          AND e.actual_same_as_registration = TRUE
          AND (v.private_street IS NULL OR v.private_street = '');
    """)

    # Step 3: Copy legacy actual_address text field into private_street when flag was False
    if column_exists(cr, 'hr_employee', 'actual_address'):
        cr.execute("""
            UPDATE hr_version v
            SET private_street = e.actual_address
            FROM hr_employee e
            WHERE v.employee_id = e.id 
              AND (e.actual_same_as_registration = FALSE OR e.actual_same_as_registration IS NULL)
              AND e.actual_address IS NOT NULL
              AND e.actual_address != ''
              AND (v.private_street IS NULL OR v.private_street = '');
        """)

    # Step 4: Unconditionally transfer legacy actual_same_as_registration into new registration_same_as_actual
    if column_exists(cr, 'hr_employee', 'registration_same_as_actual'):
        cr.execute("""
            UPDATE hr_employee
            SET registration_same_as_actual = actual_same_as_registration
            WHERE actual_same_as_registration IS NOT NULL;
        """)

        # Step 5: Synchronize registration_* fields with hr_version private_* fields for all records with flag = True
        cr.execute("""
            UPDATE hr_employee e
            SET
                registration_street = v.private_street,
                registration_street2 = v.private_street2,
                registration_city = v.private_city,
                registration_zip = v.private_zip,
                registration_region_id = v.private_state_id
            FROM hr_version v
            WHERE v.employee_id = e.id
              AND e.registration_same_as_actual = TRUE;
        """)

    _logger.info("Post-migration address data migration for l10n_ua_hr_base 19.0.1.1.0 completed.")
