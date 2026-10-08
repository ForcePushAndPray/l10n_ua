"""Give back the allowances a version lost when it was created.

`create_version` builds a new version from `copy_data()`, and until now the
allowances were not copied: a version written for any change of the card —
a phone number, an address — started without them, and from the month it
took over payroll paid none.

The ground for an allowance is an order, not a row in the database, so a
version without allowances is given them back only where nothing else says
they could have been taken off on purpose: it has none at all, the version
before it in the same contract had some, and it changed nothing the pay
depends on. Such a version was written for something else, and its missing
allowances are the footprint of the copy; it gets those still running on the
day it starts, as `copy=True` would have given it. A version that also
changed the terms of pay — a transfer, a new salary — may well have dropped
them by order: it is left as it is, and the log of the employee names the
allowances of the version before, for the officer to check against the
orders. A version of another contract is a new employment and is not looked
at.

Payslips are not touched: an upgrade recomputes none of them, so what was
paid stays as it was, and the allowances count from the next computation.
"""

import logging
from collections import defaultdict

from odoo import SUPERUSER_ID, api
from odoo.tools import format_date
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_contract 19.0.8.2.1'

# What the pay of a version depends on. Read from the table: some of these
# columns belong to modules that are not loaded yet when this runs.
PAY_COLUMNS = (
    'wage', 'work_rate', 'job_id', 'department_id', 'tariff_grade_id',
    'staffing_line_id', 'resource_calendar_id', 'salary_form',
    'salary_currency_id', 'contract_type_ua', 'diia_city_employee',
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    terms = _pay_terms(cr)
    restored, reported = defaultdict(list), defaultdict(list)
    for employee in env['hr.version'].search([]).employee_id:
        previous = None
        for current in employee.version_ids.sorted('date_version'):
            if previous and not current.allowance_ids \
                    and previous.allowance_ids \
                    and current.contract_date_start == previous.contract_date_start:
                running = previous.allowance_ids.filtered(
                    lambda a: not a.date_to or a.date_to >= current.date_version)
                if running and terms.get(current.id) == terms.get(previous.id):
                    copies = env['hr.version.allowance']
                    for allowance in running:
                        copies |= allowance.copy({'version_id': current.id})
                    restored[employee].append((current, copies))
                elif running:
                    reported[employee].append((current, running))
            previous = current
    _write_notes(env, restored, reported)
    if restored:
        _logger.warning(
            '%s: allowances given back to %s version(s) of %s employee(s) that '
            'had lost them when they were created; the details are in the log '
            'of each employee.', PREFIX,
            sum(len(entries) for entries in restored.values()), len(restored))
    if reported:
        _logger.warning(
            '%s: %s version(s) of %s employee(s) have no allowances while the '
            'version before had some, but they also changed the terms of pay, '
            'so the allowances may have been taken off on purpose and are not '
            'given back; the log of each employee names them.', PREFIX,
            sum(len(entries) for entries in reported.values()), len(reported))


def _pay_terms(cr):
    """{version id: the values its pay depends on}, for the columns present.

    Empty values are one: to the ORM a boolean left NULL and one set to false
    are both unset, and so are a wage of NULL and of zero.
    """
    columns = [c for c in PAY_COLUMNS if column_exists(cr, 'hr_version', c)]
    cr.execute(f"SELECT id, {', '.join(columns)} FROM hr_version")
    return {row[0]: tuple(value or None for value in row[1:])
            for row in cr.fetchall()}


def _write_notes(env, restored, reported):
    for employee in set(restored) | set(reported):
        employee = employee.with_context(
            lang=employee.company_id.partner_id.lang or env.lang)
        for current, copies in restored.get(employee, []):
            employee.message_post(body=employee.env._(
                'The upgrade gave back to the version of %(date)s the '
                'allowances it lost when it was created: %(allowances)s. They '
                'are copied from the version before it in the same contract — '
                'a new version did not carry them over until now. Payslips '
                'already computed are not changed; the allowances count from '
                'the next computation.',
                date=format_date(employee.env, current.date_version),
                allowances=', '.join(copies.allowance_type_id.mapped('name'))))
        for current, running in reported.get(employee, []):
            employee.message_post(body=employee.env._(
                'The version of %(date)s has no allowances, while the version '
                'before it in the same contract had: %(allowances)s. A new '
                'version did not carry allowances over until now, but this one '
                'also changed the terms of pay, so they may have been taken off '
                'by order: the upgrade does not give them back. If the order '
                'for them still stands, add them to this version.',
                date=format_date(employee.env, current.date_version),
                allowances=', '.join(running.allowance_type_id.mapped('name'))))
