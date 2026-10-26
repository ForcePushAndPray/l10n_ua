"""Назва табеля тепер українською («Табель за жовтень 2026 — усі підрозділи»)
замість «Табель October 2026 - All»: перерахувати збережені назви."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hr.timesheet'].with_context(active_test=False).search([])._compute_name()
