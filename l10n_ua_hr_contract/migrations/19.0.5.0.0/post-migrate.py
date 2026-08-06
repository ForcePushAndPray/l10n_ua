"""Carry the manual staffing pointer over into the native position fields.

`hr.version.staffing_line_id` is derived now: it follows department + job on
the date the version is in force. Whatever a version used to point at is
therefore only preserved if the position fields say the same thing — so where
they are empty, they are filled in from the line the HR officer had chosen.

Where they disagree, the native fields win, as agreed: they are what every
order, П-2 card and report already prints. The disagreement is not swallowed
silently though — it lands in the employee's chatter so it can be reviewed.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

BACKUP = 'hr_version_staffing_backup_19_5_0'


def _table_exists(cr, table):
    cr.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables "
        "WHERE table_name = %s)", (table,))
    return cr.fetchone()[0]


def migrate(cr, version):
    if not version:
        return

    if not _table_exists(cr, BACKUP):
        _logger.info(
            "l10n_ua_hr_contract 19.0.5.0.0: %s absent, nothing to carry over",
            BACKUP)
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        SELECT b.version_id, b.job_title, b.is_custom_job_title,
               s.department_id, s.job_id, s.name
        FROM {backup} b
        JOIN hr_staffing_table s ON s.id = b.staffing_line_id
        WHERE b.staffing_line_id IS NOT NULL
    """.format(backup=BACKUP))
    rows = cr.fetchall()

    filled = 0
    conflicts = 0
    restored_titles = 0

    for (version_id, old_title, was_custom_title,
         line_department, line_job, line_name) in rows:
        record = env['hr.version'].browse(version_id).exists()
        if not record:
            continue

        vals = {}
        divergences = []
        if line_department:
            if not record.department_id:
                vals['department_id'] = line_department
            elif record.department_id.id != line_department:
                divergences.append('department')
        if line_job:
            if not record.job_id:
                vals['job_id'] = line_job
            elif record.job_id.id != line_job:
                divergences.append('job')

        if vals:
            record.write(vals)
            filled += 1
            # Core recomputes job_title from the new position. A title that was
            # typed by hand is legitimate — an employee may present themselves
            # differently from the staffing wording — so it is put back.
            if was_custom_title and old_title and record.job_title != old_title:
                record.write({'job_title': old_title})
                restored_titles += 1

        if divergences and record.employee_id:
            conflicts += 1
            record.employee_id.message_post(body=(
                'Staffing table: the version of %(date)s used to point at the '
                'line "%(line)s", which disagrees with the card (%(fields)s). '
                'The job and the department on the card were left as they are '
                '- they are what orders and the P-2 card print. Please check '
                'that this is what you expect.' % {
                    'date': record.date_version,
                    'line': line_name or '',
                    'fields': ', '.join(divergences),
                }))

    _logger.info(
        "l10n_ua_hr_contract 19.0.5.0.0: filled position fields on %s versions "
        "from the staffing table, restored %s hand-written job titles, "
        "%s divergences reported in chatter",
        filled, restored_titles, conflicts)

    # Versions that used to carry a line and no longer resolve to one: the
    # position is outside the staffing table, or the table has no approved line
    # covering that date. A legitimate state — keeping a staffing table is not
    # mandatory — but worth naming, because for an employee whose wage sits in
    # the table this is exactly where a zero comes from.
    cr.execute(
        'SELECT version_id FROM %s WHERE staffing_line_id IS NOT NULL' % BACKUP)
    candidates = env['hr.version'].browse(
        [row[0] for row in cr.fetchall()]).exists()
    unresolved = candidates.filtered(lambda v: not v.staffing_line_id)
    if unresolved:
        _logger.warning(
            "l10n_ua_hr_contract 19.0.5.0.0: %s versions no longer resolve to "
            "a staffing line (ids: %s)",
            len(unresolved), unresolved.ids[:50])

