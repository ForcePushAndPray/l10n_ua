"""Give back the allowances a version lost when it was created.

`create_version` builds a new version from `copy_data()`, and until now the
allowances were not copied: a version written for any change of the card —
a phone number, an address — started without them, and from the month it
took over payroll paid none. A version that has no allowance at all while
the one before it in the same contract had some is that footprint, and it
gets the allowances that were still running on the day it starts, as
`copy=True` would have given it. A version of another contract is a new
employment and is left alone.

Payslips are not touched: an upgrade recomputes none of them, so what was
paid stays as it was, and the allowances count from the next computation.
"""

import logging
from collections import defaultdict

from odoo import SUPERUSER_ID, api
from odoo.tools import format_date

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_contract 19.0.8.2.1'


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    restored = defaultdict(list)
    for employee in env['hr.version'].search([]).employee_id:
        previous = None
        for current in employee.version_ids.sorted('date_version'):
            if previous and not current.allowance_ids \
                    and previous.allowance_ids \
                    and current.contract_date_start == previous.contract_date_start:
                copies = env['hr.version.allowance']
                for allowance in previous.allowance_ids:
                    if allowance.date_to and allowance.date_to < current.date_version:
                        continue
                    copies |= allowance.copy({'version_id': current.id})
                if copies:
                    restored[employee].append((current, copies))
            previous = current
    for employee, entries in restored.items():
        employee = employee.with_context(
            lang=employee.company_id.partner_id.lang or env.lang)
        for current, copies in entries:
            employee.message_post(body=employee.env._(
                'The upgrade gave back to the version of %(date)s the '
                'allowances it lost when it was created: %(allowances)s. They '
                'are copied from the version before it in the same contract — '
                'a new version did not carry them over until now. Payslips '
                'already computed are not changed; the allowances count from '
                'the next computation.',
                date=format_date(employee.env, current.date_version),
                allowances=', '.join(copies.allowance_type_id.mapped('name'))))
    if restored:
        _logger.warning(
            '%s: allowances given back to %s version(s) of %s employee(s) that '
            'had lost them when they were created; the details are in the log '
            'of each employee.', PREFIX,
            sum(len(entries) for entries in restored.values()), len(restored))
