"""Sick-leave certificates confirmed and not yet paid get a confirmation date.

The payslip accrues a certificate's benefit in the month of its confirmation
date. A certificate confirmed before the date existed has none, and no payslip
would ever accrue it. Those still waiting to be paid — confirmed, not paid —
are dated the day of the upgrade, so the payslip of the current month pays
them. Paid ones are left without a date: they were paid outside the payslip,
and dating them would pay them again.

Before the payslip accrued certificates itself, the benefit was entered by
hand as a sick-leave line of a payslip, and the certificate was often left
confirmed. Such a certificate is not dated: the payslip of the current month
would pay it a second time. A certificate is taken as paid that way when a
payslip of the same employee from the start of the sickness on has a manual
sick-leave or maternity line. Those are left to the accountant, with a note
on the certificate.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

SICK_CODES = ('SICK_EMP', 'SICK_FSS', 'MATERNITY')


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    paid_by_hand = []
    if _table_exists(cr, 'hr_payslip_accrual') and _table_exists(cr, 'hr_accrual_type'):
        cr.execute("""
            SELECT DISTINCT s.id
              FROM hr_sick_leave s
              JOIN hr_payslip p ON p.employee_id = s.employee_id
                               AND p.date_to >= s.date_from
                               AND p.state != 'cancel'
              JOIN hr_payslip_accrual a ON a.payslip_id = p.id
              JOIN hr_accrual_type t ON t.id = a.accrual_type_id
             WHERE s.state = 'confirmed' AND s.confirmed_date IS NULL
               AND t.code IN %s
               AND NOT COALESCE(a.is_auto_generated, FALSE)
        """, (SICK_CODES,))
        paid_by_hand = [row[0] for row in cr.fetchall()]

    cr.execute("""
        UPDATE hr_sick_leave SET confirmed_date = CURRENT_DATE
         WHERE state = 'confirmed' AND confirmed_date IS NULL
           AND NOT (id = ANY(%s))
    """, (paid_by_hand,))
    _logger.info('Confirmed sick leaves dated today for the payslip: %s', cr.rowcount)

    if paid_by_hand:
        env = api.Environment(cr, SUPERUSER_ID, {})
        certificates = env['hr.sick.leave'].browse(paid_by_hand)
        for certificate in certificates:
            # A one-off note of the upgrade, written in the users' language.
            certificate.message_post(body=(
                'Після оновлення розрахунковий лист не нарахує цей листок '
                'непрацездатності: у листках працівника вже є внесений вручну '
                'рядок лікарняних, тож допомогу, ймовірно, виплачено. Якщо так — '
                'позначте листок оплаченим; якщо ні — заповніть «Дату '
                'підтвердження», і його нарахує листок того місяця.'))
        _logger.warning(
            'Confirmed sick leaves left undated, a payslip has a manual sick-leave '
            'line (check and mark as paid): %s', ', '.join(certificates.mapped('name')))
