"""Tariff grades per company and period, with hourly rates only.

Until now `hr.tariff.grade` was one list for the whole database, with a
monthly salary or an hourly rate that payroll multiplied by the coefficient,
although the amounts entered already carried the progression. Nothing is
recalculated here, only moved:

* a grade used by versions or job positions goes to each company using it, in
  force from the earliest day that company could need a rate for; the first
  company keeps the record, every other one gets a copy and its versions and
  positions are pointed at it. Grades with an amount that nobody uses go to
  every company;
* grades nobody uses and nobody put an amount on are the old seed data and are
  removed: every company gets the typical set from the template on upgrade;
* a monthly salary is not turned into an hourly rate. `min_salary` was the
  monthly salary of the grade — the field said so and payroll divided it by
  the hours of the month — while the rate is now multiplied by the hours
  worked. The grade is left with no rate, so payroll stops on it and names it,
  and the amount is kept for the post-migration to write in the grade's log.
"""

import logging
from datetime import date as Date

from odoo import fields
from odoo.tools.sql import column_exists, table_exists

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_base 19.0.1.8.1'
MONTHLY_BACKUP = 'l10n_ua_tariff_grade_monthly_salary'


def migrate(cr, version):
    if not version or not table_exists(cr, 'hr_tariff_grade'):
        return
    if column_exists(cr, 'hr_tariff_grade', 'company_id'):
        return
    for column in ('company_id INTEGER', 'date_from DATE', 'date_to DATE'):
        cr.execute(f'ALTER TABLE hr_tariff_grade ADD COLUMN {column}')
    # Grade numbers now repeat from company to company and period to period.
    cr.execute("ALTER TABLE hr_tariff_grade DROP CONSTRAINT IF EXISTS hr_tariff_grade_grade_uniq")
    # The seed records either go or become one company's own grades.
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'l10n_ua_hr_base' AND model = 'hr.tariff.grade'
    """)
    _keep_monthly_salaries(cr)
    _from_shared_list(cr)
    _carry_notes_to_copies(cr)


def _keep_monthly_salaries(cr):
    """Set aside the monthly salaries instead of taking them for rates.

    An hourly rate cannot be derived from them here: the old payroll divided
    the salary by the hours of the month being computed and by the calendar of
    the employee, and the new rate has to be the one the collective agreement
    states. A figure made up from a norm chosen here would look authoritative
    and be wrong by a few percent, and nothing would ever say so; a grade with
    no rate stops payroll with a message naming it.
    """
    cr.execute(f"""
        CREATE TABLE IF NOT EXISTS {MONTHLY_BACKUP}
            (grade_id INTEGER PRIMARY KEY, amount NUMERIC)
    """)
    if not column_exists(cr, 'hr_tariff_grade', 'min_salary'):
        return
    cr.execute(f"""
        INSERT INTO {MONTHLY_BACKUP} (grade_id, amount)
        SELECT id, min_salary FROM hr_tariff_grade
         WHERE COALESCE(min_salary, 0) <> 0 AND COALESCE(hourly_rate, 0) = 0
            ON CONFLICT (grade_id) DO NOTHING
    """)
    if cr.rowcount:
        _logger.warning(
            '%s: %s tariff grade(s) held a monthly salary and no hourly rate. '
            'A monthly salary is not an hourly rate, so they are left without '
            'one: payroll stops on such a grade until the rate of the '
            'collective agreement is entered. The amount is written in the log '
            'of each grade.', PREFIX, cr.rowcount)


def _carry_notes_to_copies(cr):
    """The copies made for the other companies carry the same note.

    Grade numbers were unique in the whole database until now, so every grade
    of a number descends from the one original of that number.
    """
    cr.execute(f"""
        INSERT INTO {MONTHLY_BACKUP} (grade_id, amount)
        SELECT copy.id, backup.amount
          FROM {MONTHLY_BACKUP} backup
          JOIN hr_tariff_grade original ON original.id = backup.grade_id
          JOIN hr_tariff_grade copy ON copy.grade = original.grade
         WHERE COALESCE(copy.hourly_rate, 0) = 0
            ON CONFLICT (grade_id) DO NOTHING
    """)


def _earliest_dates(cr):
    """The earliest day each company could need a rate for.

    A grade had no period until now, so its rate was in force always, and the
    period that replaces it has to open early enough for every month that can
    still be recomputed to find a rate. The day of the upgrade would do for a
    company whose history starts later, and stop payroll on every month before
    it for every other one.
    """
    earliest = {}
    queries = ["""
        SELECT company_id, MIN(date_version) FROM hr_version
         WHERE company_id IS NOT NULL GROUP BY company_id
    """]
    if table_exists(cr, 'hr_payslip') and column_exists(cr, 'hr_payslip', 'date_from'):
        queries.append("""
            SELECT company_id, MIN(date_from) FROM hr_payslip
             WHERE company_id IS NOT NULL GROUP BY company_id
        """)
    for query in queries:
        cr.execute(query)
        for company_id, day in cr.fetchall():
            known = earliest.get(company_id)
            if day and (known is None or day < known):
                earliest[company_id] = day
    # A company with neither keeps no history yet: the year it was created
    # covers the months of it that payroll may still be asked for.
    cr.execute("SELECT id, create_date FROM res_company")
    for company_id, created in cr.fetchall():
        earliest.setdefault(
            company_id, Date((created or fields.Date.today()).year, 1, 1))
    return earliest


def _from_shared_list(cr):
    version_links = column_exists(cr, 'hr_version', 'tariff_grade_id')
    used = """
        SELECT company_id, tariff_grade_id FROM hr_job
         WHERE tariff_grade_id IS NOT NULL AND company_id IS NOT NULL
    """ + ("""
        UNION SELECT company_id, tariff_grade_id FROM hr_version
         WHERE tariff_grade_id IS NOT NULL AND company_id IS NOT NULL
    """ if version_links else "")
    cr.execute(f"SELECT DISTINCT company_id FROM ({used}) u ORDER BY company_id")
    companies = [company_id for (company_id,) in cr.fetchall()]
    if not companies:
        # A grade whose monthly salary was set aside is not seed data either:
        # the note about it has somewhere to go only while the grade is there.
        cr.execute(f"""
            DELETE FROM hr_tariff_grade
             WHERE COALESCE(hourly_rate, 0) = 0
               AND id NOT IN (SELECT grade_id FROM {MONTHLY_BACKUP})
               AND id NOT IN (SELECT tariff_grade_id FROM hr_job
                               WHERE tariff_grade_id IS NOT NULL)
        """)
        cr.execute("SELECT 1 FROM hr_tariff_grade LIMIT 1")
        if not cr.fetchone():
            return
        cr.execute("SELECT id FROM res_company ORDER BY id")
        companies = [company_id for (company_id,) in cr.fetchall()]

    earliest = _earliest_dates(cr)
    today = fields.Date.today()
    for index, company_id in enumerate(companies):
        date_from = earliest.get(company_id) or today
        if index == 0:
            cr.execute("UPDATE hr_tariff_grade SET company_id = %s, date_from = %s",
                       (company_id, date_from))
            continue
        cr.execute("""
            INSERT INTO hr_tariff_grade
                (company_id, date_from, name, grade, coefficient, hourly_rate,
                 active, create_date, write_date)
            SELECT %s, %s, name, grade, coefficient, hourly_rate,
                   active, NOW() AT TIME ZONE 'UTC',
                   NOW() AT TIME ZONE 'UTC'
              FROM hr_tariff_grade WHERE company_id = %s
         RETURNING id, grade
        """, (company_id, date_from, companies[0]))
        for new_id, grade in cr.fetchall():
            for table in ['hr_job'] + (['hr_version'] if version_links else []):
                cr.execute(f"""
                    UPDATE {table} t SET tariff_grade_id = %s
                      FROM hr_tariff_grade old
                     WHERE t.company_id = %s AND t.tariff_grade_id = old.id
                       AND old.company_id = %s AND old.grade = %s
                """, (new_id, company_id, companies[0], grade))
    _logger.info('%s: tariff grades given to %s company(ies).',
                 PREFIX, len(companies))
