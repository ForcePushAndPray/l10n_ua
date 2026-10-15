"""The salary form decides how a version is paid.

'time' covered both a monthly salary and an hourly rate, and what actually
chose between them was whether the version carried a tariff grade. The form
now has a value for each: a version with a tariff grade was paid by the
hour, so it becomes 'hourly', and every other 'time' becomes 'salary'. Done
before the field's new definition is loaded, for which 'time' is no longer
a valid value. Piece rate stays as it is.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'hr_version' AND column_name = 'salary_form'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE hr_version SET salary_form = 'hourly'
         WHERE salary_form = 'time' AND tariff_grade_id IS NOT NULL
    """)
    hourly = cr.rowcount
    cr.execute("""
        UPDATE hr_version SET salary_form = 'salary'
         WHERE salary_form = 'time' OR salary_form IS NULL
    """)
    _logger.info('Salary form: %s versions moved to hourly, %s to monthly salary',
                 hourly, cr.rowcount)
