"""Count the occupancy of every staffing position again.

`filled_units` is stored, and nothing recomputes it unless a version or a
line of the position changes. Until this version a re-hired employee whose
earlier employment still carried a `departure_date` was counted as gone, so
the lines of such positions hold a figure that is too low and would keep it
until somebody happened to touch them.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Staffing = env['hr.staffing.table']
    positions = Staffing.with_context(active_test=False).search([])._positions()
    Staffing._recompute_occupancy(positions)
    env.flush_all()
    _logger.info(
        'l10n_ua_hr_base 19.0.1.7.1: occupancy recounted on %s staffing '
        'position(s)', len(positions))
