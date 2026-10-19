"""Запити ДРФО і відповіді, вже завантажені з кабінету, — у «Запити до ДПС»."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    docs = env['l10n_ua.tax.document'].search(
        [('document_type_id.code', 'in', ('F1319104', 'F1419104'))], order='id')
    # Спершу запити, потім відповіді — так відповідь знайде свій запит.
    docs.sorted(lambda d: d.document_type_id.code != 'F1319104')._l10n_ua_after_import()
