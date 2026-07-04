from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Finish the switch to period-based vacation accounting.

    Runs AFTER the ORM has loaded the new schema (vacation_balance_id on
    hr_leave exists, period_type is stored on the balance):

    1. Realigns work-year balances: pre-migration backfilled everything
       as calendar years; rows whose leave type accrues per work year get
       their bounds re-anchored to the employee's hire_date anniversary.
       The mapping keeps the row's original year as the anniversary year,
       so `year` (= period_start.year) and year-based reports stay stable.
    2. Links legacy leaves to their balance row — first by an explicitly
       set vacation_year, then by date containment.
    3. Recomputes the stored rollups and labels through the ORM so the
       values reflect the corrected periods.
    """
    # 1. Work-year balances: re-anchor bounds to the hire anniversary
    cr.execute("""
        UPDATE hr_vacation_balance vb
           SET period_start = (e.hire_date
                   + make_interval(years =>
                       vb.year - EXTRACT(YEAR FROM e.hire_date)::int)),
               period_end = (e.hire_date
                   + make_interval(years =>
                       vb.year - EXTRACT(YEAR FROM e.hire_date)::int + 1)
                   - interval '1 day'),
               period_index =
                   vb.year - EXTRACT(YEAR FROM e.hire_date)::int + 1
          FROM hr_employee e,
               hr_leave_type lt
         WHERE e.id = vb.employee_id
           AND lt.id = vb.leave_type_id
           AND lt.period_type = 'work'
           AND e.hire_date IS NOT NULL
           AND vb.year >= EXTRACT(YEAR FROM e.hire_date)::int
    """)

    # 2a. Link leaves with an explicit vacation_year to that year's balance
    cr.execute("""
        UPDATE hr_leave l
           SET vacation_balance_id = vb.id
          FROM hr_vacation_balance vb
         WHERE vb.employee_id = l.employee_id
           AND vb.leave_type_id = l.holiday_status_id
           AND l.vacation_balance_id IS NULL
           AND l.vacation_year IS NOT NULL
           AND l.vacation_year != 0
           AND l.vacation_year = vb.year
    """)

    # 2b. Link remaining leaves by date containment
    cr.execute("""
        UPDATE hr_leave l
           SET vacation_balance_id = vb.id
          FROM hr_vacation_balance vb
         WHERE vb.employee_id = l.employee_id
           AND vb.leave_type_id = l.holiday_status_id
           AND l.vacation_balance_id IS NULL
           AND l.request_date_from IS NOT NULL
           AND l.request_date_from BETWEEN vb.period_start AND vb.period_end
    """)

    # 3. Refresh stored computes affected by the SQL updates above
    env = api.Environment(cr, SUPERUSER_ID, {})
    balances = env['hr.vacation.balance'].search([])
    if balances:
        balances.invalidate_recordset()
        balances._compute_year()
        balances._compute_period_label()
        balances._compute_display_name()
        balances._compute_used_days()
        balances._compute_totals()

