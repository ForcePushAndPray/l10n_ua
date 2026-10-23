"""The vacation average now reads `is_basic_salary` (#290).

Until now the flag was never read: the vacation and sick-leave averages took
the whole gross of a payslip. The accrual types the module ships marked as
outside that base the bonus, the extra pay for overtime, night and holiday
work, the long-service allowance and the retro recalculation — all of them
wage that п. 3 of Порядок № 100 counts. With the flag now applied they would
fall out of the average, so they are corrected here; the types are under
noupdate. Only the module's own records are touched, and only from False.

The flag had no default before, so a type an accountant set up of their own
is almost always unmarked, and it counted in the average only because the
whole gross did. The types of theirs in the wage categories (wage, allowance,
bonus) are marked here, so their vacation pay does not drop silently on the
upgrade. Those of the other categories may be the payments of п. 4 and are
left as they are; they are listed in the log to be checked by hand.

The severance pay the module ships was in the base of the unified social
contribution, though the contribution is not charged on it (Перелік, КМУ
№ 1170 of 22.12.2010, розд. I, п. 1). The sick-leave average now reads that
base, so the record is corrected as well, only from True.
"""

import logging

_logger = logging.getLogger(__name__)

XMLIDS = (
    'accrual_type_bonus',
    'accrual_type_overtime',
    'accrual_type_night',
    'accrual_type_holiday',
    'accrual_type_seniority',
    'accrual_type_retro',
)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE hr_accrual_type t
           SET is_basic_salary = TRUE
          FROM ir_model_data d
         WHERE d.model = 'hr.accrual.type'
           AND d.module = 'l10n_ua_hr_salary'
           AND d.name IN %s
           AND d.res_id = t.id
           AND t.is_basic_salary IS NOT TRUE
     RETURNING t.code
    """, (XMLIDS,))
    codes = [row[0] for row in cr.fetchall()]
    _logger.info('Accrual types now in the vacation average: %s',
                 ', '.join(sorted(codes)) or 'none')

    cr.execute("""
        UPDATE hr_accrual_type t
           SET is_basic_salary = TRUE
         WHERE t.is_basic_salary IS NOT TRUE
           AND t.category IN ('wage', 'allowance', 'bonus')
           AND NOT EXISTS (
               SELECT 1 FROM ir_model_data d
                WHERE d.model = 'hr.accrual.type'
                  AND d.module = 'l10n_ua_hr_salary'
                  AND d.res_id = t.id)
     RETURNING t.code
    """)
    marked = [row[0] for row in cr.fetchall()]
    if marked:
        _logger.info('Accrual types of your own now in the vacation average: %s',
                     ', '.join(sorted(marked)))

    cr.execute("""
        UPDATE hr_accrual_type t
           SET is_esv_base = FALSE
          FROM ir_model_data d
         WHERE d.model = 'hr.accrual.type'
           AND d.module = 'l10n_ua_hr_salary'
           AND d.name = 'accrual_type_severance'
           AND d.res_id = t.id
           AND t.is_esv_base
    """)
    if cr.rowcount:
        _logger.info('Severance pay is no longer in the contribution base')

    cr.execute("""
        SELECT t.code
          FROM hr_accrual_type t
         WHERE t.is_basic_salary IS NOT TRUE
           AND t.category NOT IN ('vacation', 'sick')
           AND NOT EXISTS (
               SELECT 1 FROM ir_model_data d
                WHERE d.model = 'hr.accrual.type'
                  AND d.module = 'l10n_ua_hr_salary'
                  AND d.res_id = t.id)
         ORDER BY t.code
    """)
    custom = [row[0] for row in cr.fetchall()]
    if custom:
        _logger.warning(
            'Accrual types of your own not marked "Basic Salary Component" no '
            'longer count in the vacation average; mark those that are wage '
            '(Порядок № 100, п. 3): %s', ', '.join(custom))
