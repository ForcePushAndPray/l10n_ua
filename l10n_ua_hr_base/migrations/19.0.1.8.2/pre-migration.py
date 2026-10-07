"""Tariff grades per company and period, with hourly rates only.

Until now `hr.tariff.grade` was one list for the whole database, with a
monthly salary or an hourly rate that payroll multiplied by the coefficient.
From now on the rate of a grade is paid as it stands. The grades are moved,
and recalculated only where the old payroll leaves no doubt:

* a grade used by versions or job positions goes to each company using it, in
  force from the earliest day that company could need a rate for; the first
  company keeps the record, every other one gets a copy and its versions and
  positions are pointed at it. The whole list goes along, unused grades
  included: they make up the rest of the typical set, which a company that
  has grades is not given again;
* when no company uses any grade, grades nobody put an amount on are the old
  seed data and are removed, and every company gets the typical set from the
  template on upgrade; grades with an amount go to every company;
* the coefficient. A grade whose rate equals the rate of grade 1 and whose
  coefficient is not 1 was paid by the coefficient, and its rate is
  multiplied so it pays what it paid. Any other grade with a coefficient may
  already hold the progressed rate, and multiplying it again would overpay:
  it is left as it is, and what the old payroll paid is written in its log;
* the amount of the monthly salary field. The form showed no other field, so
  hourly rates were typed into it, and payroll divided them by the hours of the
  month. The amount is set aside here; the post-migration, which can read the
  payroll parameters of each company, makes it the hourly rate where it can be
  nothing else and leaves the grade without a rate otherwise.
"""

import logging
from datetime import date as Date
from decimal import ROUND_HALF_UP, Decimal

from odoo import fields
from odoo.tools.sql import column_exists, table_exists

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_base 19.0.1.8.2'
MONTHLY_BACKUP = 'l10n_ua_tariff_grade_monthly_salary'
COEFFICIENT_BACKUP = 'l10n_ua_tariff_grade_coefficient'


def migrate(cr, version):
    if not version:
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
    _review_coefficients(cr)
    _from_shared_list(cr)
    _carry_notes_to_copies(cr)


def _keep_monthly_salaries(cr):
    """Set aside the amounts of the monthly salary field of grades with no rate.

    Whether such an amount is an hourly rate or a monthly salary depends on
    the subsistence minimum of the company that keeps the grade, and grades
    have no company until `_from_shared_list` gives them one: the
    post-migration decides.
    """
    cr.execute(f"""
        CREATE TABLE IF NOT EXISTS {MONTHLY_BACKUP}
            (grade_id INTEGER PRIMARY KEY, amount NUMERIC)
    """)
    cr.execute(f"""
        INSERT INTO {MONTHLY_BACKUP} (grade_id, amount)
        SELECT id, min_salary FROM hr_tariff_grade
         WHERE COALESCE(min_salary, 0) <> 0 AND COALESCE(hourly_rate, 0) = 0
            ON CONFLICT (grade_id) DO NOTHING
    """)
    if cr.rowcount:
        _logger.warning(
            '%s: %s tariff grade(s) held an amount in the monthly salary field '
            'and no hourly rate. The post-migration makes it the hourly rate '
            'where it can be nothing else and leaves the others without one.',
            PREFIX, cr.rowcount)


def _review_coefficients(cr):
    """Take the coefficient into the rate where it plainly carried the pay.

    The old payroll paid `hourly_rate * coefficient`; the new one pays the
    rate. Whether a stored rate is the base the coefficient multiplied or a
    rate already agreed for the grade, the data alone cannot say — except in
    one case: a grade whose rate equals the rate of grade 1 had nothing but
    the coefficient to set it apart, so its rate is multiplied and the grade
    pays what it paid, the rate rounded to the kopiyka. Every other grade with
    a coefficient keeps its rate: a grid agreed grade by grade already holds
    the progression, and multiplying it again would overpay by the
    coefficient. Both kinds are set aside for the post-migration, which
    writes in the log of each grade what the old payroll paid.
    """
    cr.execute(f"""
        CREATE TABLE IF NOT EXISTS {COEFFICIENT_BACKUP}
            (grade_id INTEGER PRIMARY KEY, rate NUMERIC, coefficient NUMERIC,
             paid NUMERIC, multiplied BOOLEAN)
    """)
    cr.execute("""
        SELECT hourly_rate FROM hr_tariff_grade
         WHERE grade = 1 AND COALESCE(hourly_rate, 0) <> 0
         LIMIT 1
    """)
    row = cr.fetchone()
    first_rate = Decimal(str(row[0])) if row else None
    cr.execute("""
        SELECT id, grade, hourly_rate, coefficient FROM hr_tariff_grade
         WHERE COALESCE(hourly_rate, 0) <> 0
           AND COALESCE(coefficient, 1) <> 1
      ORDER BY grade
    """)
    multiplied, kept = [], []
    for grade_id, grade, rate, coefficient in cr.fetchall():
        rate, coefficient = Decimal(str(rate)), Decimal(str(coefficient))
        paid = (rate * coefficient).quantize(Decimal('0.01'), ROUND_HALF_UP)
        plain = first_rate is not None and abs(rate - first_rate) < Decimal('0.005')
        if plain:
            cr.execute("UPDATE hr_tariff_grade SET hourly_rate = %s WHERE id = %s",
                       (paid, grade_id))
        cr.execute(f"""
            INSERT INTO {COEFFICIENT_BACKUP}
                 VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (grade_id) DO NOTHING
        """, (grade_id, rate, coefficient, paid, plain))
        (multiplied if plain else kept).append(
            f'{grade}: {rate} x {coefficient} = {paid}')
    if multiplied:
        _logger.warning(
            '%s: %s tariff grade(s) had the rate of grade 1 and were paid by '
            'the coefficient; the rate is multiplied, so they pay what they '
            'paid: %s', PREFIX, len(multiplied), '; '.join(multiplied))
    if kept:
        _logger.warning(
            '%s: %s tariff grade(s) have a coefficient and a rate of their '
            'own. Payroll paid the rate times the coefficient and now pays the '
            'rate. Check each against the collective agreement — the old pay '
            'is written in its log: %s', PREFIX, len(kept), '; '.join(kept))


def _carry_notes_to_copies(cr):
    """The copies made for the other companies carry the same notes.

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
    cr.execute(f"""
        INSERT INTO {COEFFICIENT_BACKUP}
             (grade_id, rate, coefficient, paid, multiplied)
        SELECT copy.id, backup.rate, backup.coefficient, backup.paid,
               backup.multiplied
          FROM {COEFFICIENT_BACKUP} backup
          JOIN hr_tariff_grade original ON original.id = backup.grade_id
          JOIN hr_tariff_grade copy ON copy.grade = original.grade
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
