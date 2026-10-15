"""The maximum ESV base is the minimum wage times a multiplier of the period.

It was 15 minimum wages in the code. The ESV law sets 15, but the State
Budget laws for 2025 and 2026 raised it to 20 (#378). The new field got the
law's 15 on every company record; the periods of 2025 and 2026 get 20, and
the stored maximum base is recomputed. A company that edited its records by
hand keeps its minimum wage; only the multiplier is set.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE hr_psp_parameters SET max_esv_base_multiplier = 20
         WHERE date_from >= '2025-01-01' AND date_from < '2027-01-01'
    """)
    _logger.info('Max ESV base of 20 minimum wages set on %s periods', cr.rowcount)
    cr.execute("""
        UPDATE hr_psp_parameters SET max_esv_base = min_wage * max_esv_base_multiplier
    """)
