"""Put the consequences of the new `date_to` where an HR officer will see them.

19.0.1.4.0 changed what `hr.staffing.table.date_to` means. It used to be
"Effective Until" — the end of this line's own period, filled in by hand
whenever an officer closed a line and opened the next. It now means "Position
Discontinued": `_resolve_batch` stops at a line whose `date_to` has passed and
deliberately does not fall through to an older one, because a position that was
abolished does not come back.

On a database where "Effective Until" was filled in as a matter of habit, that
turns into a hole. Where the hole is at the end — the newest approved line of a
position carries a past date — the position resolves to nothing at all, and for
an employee whose version carries no wage of its own the next payslip is a
silent zero. Where it is in the middle, only recalculations of the months inside
it are affected.

The upgrade that made the change already scans for both cases, and writes what
it finds to the log. A log nobody reads: the first sign of the problem is a
payslip. So the finding is repeated where the person who can act on it works —
the chatter of the staffing lines themselves, the way
`_report_duplicate_start_dates` already does for the other thing that can go
wrong with this table. The log stays as it is; it is for the administrator
running the upgrade.

Nothing is modified. Which lines were meant as "the position ended" and which as
"we closed this line and opened the next" is a statement about orders that were
signed, and a migration cannot read them.

Filed here, and not with the release that made the change, for two reasons.
Writing to a chatter needs the ORM, and the pre-migration of this very module
does not have one: `load_openerp_module` runs after
`migrations.migrate_module(package, 'pre')`, so `hr.staffing.table` is not in
the registry yet when that script runs. And a script filed under 19.0.1.4.0
would never run on the databases this is for — the ones that already went
through that upgrade and have been living with the hole since.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column))
    return bool(cr.fetchone())


def _dead_ends(cr):
    """Positions whose newest approved line is closed by a past date.

    Those resolve to nothing from the day after, and the line they superseded
    does not come back.
    """
    cr.execute("""
        WITH latest AS (
            SELECT DISTINCT ON (company_id, department_id, job_id)
                   id, company_id, department_id, job_id, date_from, date_to
              FROM hr_staffing_table
             WHERE state = 'approved'
             ORDER BY company_id, department_id, job_id, date_from DESC, id DESC
        )
        SELECT l.id, l.company_id, l.department_id, l.job_id, l.date_to,
               d.name->>'en_US', j.name->>'en_US'
          FROM latest l
          LEFT JOIN hr_department d ON d.id = l.department_id
          LEFT JOIN hr_job j ON j.id = l.job_id
         WHERE l.date_to IS NOT NULL
           AND l.date_to < CURRENT_DATE
         ORDER BY 6, 7
    """)
    return cr.fetchall()


def _gaps(cr):
    """Approved lines that end before the next line of the position starts."""
    cr.execute("""
        SELECT s.id, s.date_to, min(n.date_from),
               d.name->>'en_US', j.name->>'en_US'
          FROM hr_staffing_table s
          JOIN hr_staffing_table n
            ON n.state = 'approved'
           AND n.company_id = s.company_id
           AND n.department_id IS NOT DISTINCT FROM s.department_id
           AND n.job_id IS NOT DISTINCT FROM s.job_id
           AND n.date_from > s.date_from
          LEFT JOIN hr_department d ON d.id = s.department_id
          LEFT JOIN hr_job j ON j.id = s.job_id
         WHERE s.state = 'approved'
           AND s.date_to IS NOT NULL
         GROUP BY s.id, s.date_to, d.name->>'en_US', j.name->>'en_US'
        HAVING s.date_to < min(n.date_from) - 1
         ORDER BY 4, 5
    """)
    return cr.fetchall()


def _employees_without_wage(cr, line_ids):
    """Who is standing on those positions, and would be calculated at zero.

    Matched two ways on purpose: `hr_version.department_id` / `job_id` are
    still empty on the versions whose position lived only in
    `staffing_line_id` — l10n_ua_hr_contract fills them in its own
    post-migration, and that module depends on this one, so it is loaded after
    this script has run. Counting by the position alone would leave out exactly
    the employees this report is for.

    `current_version_id`, not `version_id`: the second is computed and has no
    column of its own.
    """
    pointer = _column_exists(cr, 'hr_version', 'staffing_line_id')
    cr.execute("""
        SELECT s.id, count(DISTINCT e.id)
          FROM hr_staffing_table s
          JOIN hr_version v
            ON (v.company_id = s.company_id
                AND v.department_id = s.department_id
                AND v.job_id = s.job_id)
            {pointer}
          JOIN hr_employee e
            ON e.current_version_id = v.id AND e.active
         WHERE s.id = ANY(%s)
           AND COALESCE(v.wage, 0) = 0
         GROUP BY s.id
    """.format(pointer='OR v.staffing_line_id = s.id' if pointer else ''),
        (line_ids,))
    return dict(cr.fetchall())


def _log(dead, gaps, by_line):
    """The administrator's copy, unchanged from the scan that came with
    19.0.1.4.0: it is read while the upgrade is running, by whoever is running
    it, and it names ids the chatter cannot show side by side."""
    if dead:
        exposed = sum(by_line.values())
        _logger.warning(
            "l10n_ua_hr_base 19.0.1.6.1: %s position(s) have their newest "
            "approved line closed by a past date. Since 19.0.1.4.0 that reads "
            "as \"position discontinued\": those positions resolve to nothing, "
            "and %s employee(s) on them carry no wage of their own, so their "
            "next payslip is calculated at zero. Open a new approved line "
            "from the day the position continues, or clear the date where it "
            "never ended.",
            len(dead), exposed)
        for (line_id, company_id, department_id, job_id,
             date_to, department, job) in dead:
            _logger.warning(
                "  company %s, %s (id %s) / %s (id %s): line %s ends %s, "
                "%s employee(s) with no wage of their own",
                company_id, department or '?', department_id,
                job or '?', job_id, line_id, date_to,
                by_line.get(line_id, 0))

    if gaps:
        _logger.warning(
            "l10n_ua_hr_base 19.0.1.6.1: %s approved staffing line(s) end "
            "before the next line of the same position starts. Payslips "
            "recalculated for the months inside those gaps resolve to "
            "nothing.",
            len(gaps))
        for line_id, date_to, next_from, department, job in gaps:
            _logger.warning(
                "  %s / %s: line %s ends %s, next starts %s",
                department or '?', job or '?', line_id, date_to, next_from)


def migrate(cr, version):
    if not version:
        return

    dead = _dead_ends(cr)
    gaps = _gaps(cr)
    if not dead and not gaps:
        _logger.info(
            "l10n_ua_hr_base 19.0.1.6.1: no approved staffing line carries a "
            "past end date, so the meaning that field took in 19.0.1.4.0 "
            "changes nothing here")
        return

    by_line = _employees_without_wage(
        cr, [row[0] for row in dead]) if dead else {}
    _log(dead, gaps, by_line)

    # The notes are a diagnostic, and a diagnostic may not decide whether the
    # upgrade goes through: `migrate_module` puts nothing around `migrate()`,
    # so anything raised here rolls back every module of the upgrade over a
    # chatter message that the log above has already carried. In a savepoint,
    # so that a database error does not poison the transaction the rest of the
    # loading still has to write in, and flushed inside it, or a failure would
    # surface later — outside both.
    try:
        with cr.savepoint():
            env = api.Environment(cr, SUPERUSER_ID, {})
            Staffing = env['hr.staffing.table']
            if dead:
                Staffing.browse([row[0] for row in dead]).exists() \
                    ._message_log_position_discontinued(by_line)
            if gaps:
                next_start = {row[0]: row[2] for row in gaps}
                Staffing.browse(list(next_start)).exists() \
                    ._message_log_position_gap(next_start)
            env.flush_all()
    except Exception:  # noqa: BLE001 - a note may not abort the upgrade
        _logger.exception(
            "l10n_ua_hr_base 19.0.1.6.1: the findings above could not be "
            "written to the chatter of the staffing lines. They are in this "
            "log in full, and the upgrade carries on without them")
