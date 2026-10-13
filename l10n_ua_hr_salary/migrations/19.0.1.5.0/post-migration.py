"""The salary is now calculated by the hours worked; the payslips closed before
that keep their days-based figures. The date of the change is kept in a system
parameter, so that a retro recalculation does not recompute those months by the
new method and carry the difference of the methods into a current payslip. Set
once: a later upgrade from this version does not move it.

The sickness benefit paid by the fund and the maternity benefit are part of
the base of the unified social contribution, as the employer's first days
of sickness already are.

The accrual types the module ships marked them as outside the base. Nothing
created lines of these types until the payslip began to accrue the benefits
itself; the types are under noupdate, so they are corrected here. Only the
module's own records are touched, and only from False: a type an accountant
set up of their own stays as it is.
"""

import logging

_logger = logging.getLogger(__name__)

XMLIDS = ('accrual_type_sick_fss', 'accrual_type_maternity')
METHOD_DATE_KEY = 'l10n_ua_hr_salary.hours_method_date'


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE hr_accrual_type t
           SET is_esv_base = TRUE
          FROM ir_model_data d
         WHERE d.model = 'hr.accrual.type'
           AND d.module = 'l10n_ua_hr_salary'
           AND d.name IN %s
           AND d.res_id = t.id
           AND t.is_esv_base IS NOT TRUE
     RETURNING t.code
    """, (XMLIDS,))
    codes = [row[0] for row in cr.fetchall()]
    _logger.info('Accrual types now in the contribution base: %s',
                 ', '.join(codes) or 'none')

    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
        SELECT %s, CURRENT_DATE::text, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
         WHERE NOT EXISTS (SELECT 1 FROM ir_config_parameter WHERE key = %s)
    """, (METHOD_DATE_KEY, METHOD_DATE_KEY))
    _logger.info('Hours-worked salary from: %s', 'set today' if cr.rowcount else 'kept')
