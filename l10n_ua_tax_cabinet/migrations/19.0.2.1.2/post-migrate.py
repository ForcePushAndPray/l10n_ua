"""Документи з кабінету, записані як «Інше», — за кодом форми з їхнього XML.

Так були імпортовані, напр., запит і відповідь з ДРФО (F1319104 / F1419104),
доки їх не було в довіднику типів.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    docs = env['l10n_ua.tax.document'].with_context(active_test=False).search([
        ('source', '=', 'cabinet'),
        '|', ('document_type_id', '=', False),
        ('document_type_id.code', '=', 'OTHER'),
    ])
    docs._retype_from_xml()
