"""What the tariff grades still need once the registry holds the new model.

The amounts the pre-migration set aside from the monthly salary field become
hourly rates where they can be nothing else, and the rest wait for the rate in
the log of their grade; the old pay of grades with a coefficient is written in
their log, and the companies that had no grades to move are given the typical
set.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)

PREFIX = 'l10n_ua_hr_base 19.0.1.8.2'
MONTHLY_BACKUP = 'l10n_ua_tariff_grade_monthly_salary'
COEFFICIENT_BACKUP = 'l10n_ua_tariff_grade_coefficient'


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _carry_monthly_amounts(env, cr)
    _log_coefficients(env, cr)
    _seed_companies_without_grades(env)


def _amount_bounds(env, cr, company):
    """(lowest hourly rate, lowest monthly amount) the law allows, or None.

    The subsistence minimum for able-bodied persons is the floor of a monthly
    tariff rate (art. 6 of the Law on Remuneration of Labour), and a monthly
    salary for full time cannot be below it either; spread over the hours of
    an average month it is the floor of an hourly rate. The lowest minimum
    the company has parameters for is taken, so that no lawful amount of any
    year falls outside. The parameters belong to `l10n_ua_hr_salary`, which is
    not loaded yet when this runs, so they are read from their table.
    """
    if not table_exists(cr, 'hr_psp_parameters'):
        return None
    cr.execute("""
        SELECT subsistence_minimum, date_from FROM hr_psp_parameters
         WHERE company_id = %s AND COALESCE(subsistence_minimum, 0) > 0
      ORDER BY subsistence_minimum, date_from
         LIMIT 1
    """, (company.id,))
    row = cr.fetchone()
    if not row:
        return None
    minimum, since = float(row[0]), row[1]
    hours = env['hr.tariff.grade']._average_monthly_hours(company, since.year)
    return minimum / hours, minimum


def _carry_monthly_amounts(env, cr):
    """Make the amounts of the monthly salary field hourly rates where they can only be that.

    The form showed nothing but the monthly salary field, so hourly rates were
    typed into it — and payroll divided them by the hours of the month. An
    amount below the subsistence minimum cannot be a monthly salary, and one
    at or above its hourly share can be an hourly rate: such an amount is an
    hourly rate entered in the wrong field, and it becomes the rate of the
    grade. Anything else — a figure a monthly salary may well be, one too
    small even for an hourly rate, or a company with no parameters to tell —
    leaves the grade without a rate, and payroll stops on it and says so.
    Either way the log of the grade says what happened, in the language of
    the company that keeps it.

    The rate is written as it stood: the other grades are not filled in from
    it, and the coefficient is not applied — the old payroll never paid this
    amount times the coefficient as an hourly rate.
    """
    if not table_exists(cr, MONTHLY_BACKUP):
        return
    cr.execute(f'SELECT grade_id, amount FROM {MONTHLY_BACKUP}')
    amounts = dict(cr.fetchall())
    grades = env['hr.tariff.grade'].with_context(active_test=False).browse(
        list(amounts)).exists()
    bounds, carried, left = {}, 0, 0
    for grade in grades:
        amount = float(amounts[grade.id])
        if grade.company_id not in bounds:
            bounds[grade.company_id] = _amount_bounds(env, cr, grade.company_id)
        limits = bounds[grade.company_id]
        grade = grade.with_context(
            lang=grade.company_id.partner_id.lang or env.lang)
        if limits and limits[0] <= amount < limits[1]:
            cr.execute("UPDATE hr_tariff_grade SET hourly_rate = %s WHERE id = %s",
                       (amount, grade.id))
            grade.invalidate_recordset(['hourly_rate'])
            carried += 1
            body = grade.env._(
                'Until this upgrade the grade held %(amount).2f in its monthly '
                'salary field and no hourly rate. That field was the only one '
                'the form showed, and %(amount).2f is below the subsistence '
                'minimum of %(minimum).2f, too little for a monthly salary: it '
                'is an hourly rate entered there, and it is now the hourly rate '
                'of the grade. Check it against the collective agreement.',
                amount=amount, minimum=limits[1])
        else:
            left += 1
            body = grade.env._(
                'Until this upgrade the grade held %(amount).2f in its monthly '
                'salary field and no hourly rate. That field was the only one the '
                'form showed, so it may hold an hourly rate entered there as well '
                'as a monthly salary, and the upgrade cannot tell which. The grade '
                'is left without a rate: payroll stops on it and says so. If '
                '%(amount).2f is the hourly rate of the collective agreement, '
                'enter it as the rate; if it is a monthly salary, enter the hourly '
                'rate of the agreement instead — the monthly salary of a position '
                'belongs in the staffing table.', amount=amount)
        grade.message_post(body=body)
    cr.execute(f'DROP TABLE {MONTHLY_BACKUP}')
    if carried:
        _logger.warning(
            '%s: %s tariff grade(s) held an hourly rate in the monthly salary '
            'field; it is now their hourly rate, and the log of each of them '
            'says so.', PREFIX, carried)
    if left:
        _logger.warning(
            '%s: %s tariff grade(s) are without an hourly rate: the amount of '
            'their monthly salary field could not be taken for one. The amount '
            'is in the log of each of them.', PREFIX, left)


def _log_coefficients(env, cr):
    """Tell each grade with a coefficient what the old payroll paid for it.

    The old payroll multiplied the rate by the coefficient, the new one pays
    the rate. The pre-migration multiplied the rates where that was plainly the
    intent and left the others; either way the officer who opens the grade
    finds there what an hour of it cost before the upgrade and what it costs
    now, in the language of the company that keeps it.
    """
    if not table_exists(cr, COEFFICIENT_BACKUP):
        return
    cr.execute(f"""
        SELECT grade_id, rate, coefficient, paid, multiplied
          FROM {COEFFICIENT_BACKUP}
    """)
    rows = {row[0]: row[1:] for row in cr.fetchall()}
    grades = env['hr.tariff.grade'].with_context(active_test=False).browse(
        list(rows)).exists()
    for grade in grades:
        rate, coefficient, paid, multiplied = rows[grade.id]
        grade = grade.with_context(
            lang=grade.company_id.partner_id.lang or env.lang)
        values = {'rate': float(rate), 'coefficient': float(coefficient),
                  'paid': float(paid)}
        if multiplied:
            body = grade.env._(
                'Until this upgrade payroll paid this grade its rate '
                '%(rate).2f times the coefficient %(coefficient)s, that is '
                '%(paid).2f an hour. A rate is now paid as it stands. This one '
                'equalled the rate of grade 1, so the coefficient was what set '
                'the grade apart: the rate is now %(paid).2f, and the grade '
                'pays what it paid, the rate rounded to the kopiyka.', **values)
        else:
            body = grade.env._(
                'Until this upgrade payroll paid this grade its rate '
                '%(rate).2f times the coefficient %(coefficient)s, that is '
                '%(paid).2f an hour. A rate is now paid as it stands, '
                '%(rate).2f an hour. If the collective agreement states '
                '%(paid).2f for this grade, correct the rate; if it states '
                '%(rate).2f, nothing is to be done.', **values)
        grade.message_post(body=body)
    cr.execute(f'DROP TABLE {COEFFICIENT_BACKUP}')


def _seed_companies_without_grades(env):
    """The companies that had no grades to move get the typical set.

    The data file no longer seeds on every update — it gave back the grid a
    company had deliberately deleted — so the upgrade says it here, once.
    """
    seeded = env['hr.tariff.grade']._seed_company_grades()
    if seeded:
        _logger.info('%s: typical tariff grades given to %s company(ies).',
                     PREFIX, len(seeded.company_id))
