"""What the tariff grades still need after they have been moved.

Three things, each of which is only possible once the registry holds the new
model: the gaps between periods are reported, the monthly salaries that
19.0.1.8.1 set aside are written in the log of their grade, and the companies
that had no grades to move are given the typical set.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_base 19.0.1.8.2'
MONTHLY_BACKUP = 'l10n_ua_tariff_grade_monthly_salary'


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _report_gaps(cr)
    _log_monthly_salaries(env, cr)
    _seed_companies_without_grades(env)


def _report_gaps(cr):
    """Report the gaps between the periods of a tariff grade.

    From now on a gap cannot be saved, but one entered before is still in the
    database, and it is found only when payroll stops in the middle of the
    month it is computed for. They are listed here once, so that they are
    corrected before that happens.
    """
    cr.execute("""
        SELECT g.company_id, c.name, g.grade, g.date_to,
               MIN(n.date_from) AS next_from
          FROM hr_tariff_grade g
          JOIN res_company c ON c.id = g.company_id
          JOIN hr_tariff_grade n
            ON n.company_id = g.company_id AND n.grade = g.grade
           AND n.date_from > g.date_from AND COALESCE(n.active, TRUE)
         WHERE g.date_to IS NOT NULL AND COALESCE(g.active, TRUE)
      GROUP BY g.company_id, c.name, g.grade, g.date_to
        HAVING MIN(n.date_from) > g.date_to + 1
      ORDER BY g.company_id, g.grade, g.date_to
    """)
    for company_id, company, grade, date_to, next_from in cr.fetchall():
        _logger.warning(
            '%s: company "%s" (id %s), tariff grade %s: no rate in force '
            'between %s and %s. Payroll for that time stops until the periods '
            'meet.', PREFIX, company, company_id, grade, date_to, next_from)


def _log_monthly_salaries(env, cr):
    """Tell each grade, in its own log, what it used to hold.

    19.0.1.8.1 set the monthly salaries aside instead of taking them for
    hourly rates. The amount is of no use to payroll any more, but it is the
    only trace of what the employer agreed, and the log of the grade is where
    whoever has to enter the rate will look. In the language of the company
    that keeps the grade: the note is read by its own payroll officer.
    """
    if not table_exists(cr, MONTHLY_BACKUP):
        return
    cr.execute(f'SELECT grade_id, amount FROM {MONTHLY_BACKUP}')
    amounts = dict(cr.fetchall())
    grades = env['hr.tariff.grade'].with_context(active_test=False).browse(
        list(amounts)).exists()
    for grade in grades:
        grade = grade.with_context(
            lang=grade.company_id.partner_id.lang or env.lang)
        grade.message_post(body=grade.env._(
            'Until this upgrade the grade held a monthly salary of '
            '%(amount).2f and no hourly rate. Payroll multiplies the rate by '
            'the hours worked, so a monthly salary could not be taken for '
            'one, and the grade is left without a rate: payroll stops on it '
            'and says so. Enter the hourly rate of the collective agreement — '
            'the monthly salary of a position belongs in the staffing table.',
            amount=float(amounts[grade.id])))
    cr.execute(f'DROP TABLE {MONTHLY_BACKUP}')
    if grades:
        _logger.warning(
            '%s: %s tariff grade(s) are without an hourly rate because they '
            'held a monthly salary; the amount is in the log of each of them.',
            PREFIX, len(grades))


def _seed_companies_without_grades(env):
    """The companies that had no grades to move get the typical set.

    The data file no longer seeds on every update — it gave back the grid a
    company had deliberately deleted — so the upgrade says it here, once.
    """
    seeded = env['hr.tariff.grade']._seed_company_grades()
    if seeded:
        _logger.info('%s: typical tariff grades given to %s company(ies).',
                     PREFIX, len(seeded.company_id))
