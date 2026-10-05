"""Say what the order was linked to, on the databases where the link goes.

`leave_id` and `holiday_status_id` move to l10n_ua_hr_holidays (see
`pre-migration.py`). Where that module is installed the external ids are
handed over and nothing is lost.

Where it is not, the fields are genuinely gone: this module used to depend on
core `hr_holidays`, so an order could be tied to a time off without
l10n_ua_hr_holidays anywhere, and the end-of-load cleanup drops the columns
together with the values in them. The feature going away is the decision of
#327; the record of which time off an order was issued for is the officer's
data, and it is written into the chatter of every affected order before the
column is dropped — the cleanup runs after all migrations, so this is the last
moment it can be read.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

OLD_MODULE = 'l10n_ua_hr_documents'
NEW_MODULE = 'l10n_ua_hr_holidays'


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        "SELECT 1 FROM ir_module_module WHERE name = %s AND state IN %s",
        (NEW_MODULE, ('installed', 'to upgrade', 'to install')),
    )
    if cr.fetchone():
        # The fields kept their owner and their data: nothing to rescue.
        return

    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'hr_order' AND column_name = 'leave_id'""")
    if not cr.fetchone():
        return

    # holiday_status_id is a stored, writable related: an order may carry a
    # leave type with no time off linked at all, and that value goes too.
    cr.execute(
        """SELECT id, leave_id, holiday_status_id FROM hr_order
            WHERE leave_id IS NOT NULL OR holiday_status_id IS NOT NULL""")
    rows = cr.fetchall()
    links = {oid: leave for oid, leave, _type in rows if leave}
    types = {oid: type_id for oid, _leave, type_id in rows if type_id}
    if not rows:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    installed = env['res.lang'].get_installed()
    env = api.Environment(cr, SUPERUSER_ID, {
        'lang': env.user.lang or (installed[0][0] if installed else 'en_US'),
    })

    # The leave itself may still be readable (core hr_holidays installed) or
    # not; either way the note has to carry enough to find it again by hand.
    described = {}
    if 'hr.leave' in env:
        leaves = env['hr.leave'].browse(set(links.values())).exists()
        described = {
            leave.id: '%s, %s — %s' % (
                leave.employee_id.display_name or '',
                leave.request_date_from or '',
                leave.request_date_to or '')
            for leave in leaves
        }

    type_names = {}
    if 'hr.leave.type' in env:
        type_names = {
            leave_type.id: leave_type.display_name
            for leave_type in env['hr.leave.type'].with_context(
                active_test=False).browse(set(types.values())).exists()
        }

    def note(order):
        parts = []
        if order.id in types:
            parts.append(env._(
                'Leave type recorded on this order: %(type)s. The field '
                'holding it now lives in Ukraine - HR Holidays, which is not '
                'installed here, so it is removed with this update.',
                type=type_names.get(types[order.id]) or '#%s' % types[order.id]))
        if order.id in links:
            parts.append(env._(
                'This order was linked to time off #%(leave)s%(detail)s. The link '
                'itself is not kept: it now lives in Ukraine - HR Holidays, which '
                'is not installed here, so the field holding it is removed with '
                'this update. The note stays, so the time off this order was '
                'issued for can still be found.',
                leave=links[order.id],
                detail=' (%s)' % described[links[order.id]]
                if links[order.id] in described else ''))
        return ' '.join(parts)

    orders = env['hr.order'].browse([row[0] for row in rows])
    orders._message_log_batch({order.id: note(order) for order in orders})
    _logger.warning(
        'l10n_ua_hr_documents 19.0.1.2.0: %s order(s) carried a link to a '
        'time off or a leave type, and %s is not installed, so hr_order.leave_id and '
        'hr_order.holiday_status_id are dropped with this update. Each order '
        'has the link written into its chatter: %s',
        len(rows), NEW_MODULE, sorted(row[0] for row in rows))
