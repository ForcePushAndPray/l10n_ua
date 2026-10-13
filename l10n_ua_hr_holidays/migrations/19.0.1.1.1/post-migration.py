"""Sick-leave certificates confirmed and not yet paid get a confirmation date.

The payslip accrues a certificate's benefit in the month of its confirmation
date. A certificate confirmed before the date existed has none, and no payslip
would ever accrue it. Those still waiting to be paid — confirmed, not paid —
are dated the day of the upgrade, so the payslip of the current month pays
them. Paid ones are left without a date: they were paid outside the payslip,
and dating them would pay them again.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE hr_sick_leave SET confirmed_date = CURRENT_DATE
         WHERE state = 'confirmed' AND confirmed_date IS NULL
    """)
    _logger.info('Confirmed sick leaves dated today for the payslip: %s', cr.rowcount)
