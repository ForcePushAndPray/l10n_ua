"""Декларації ЄП, уже завантажені з кабінету до цієї версії, — у «Декларації ЄП».

Синхронізація зберігала XML лише в журнал поданих документів; тепер кожна
F0103309 стає записом декларації. Повтор безпечний: наявні не дублюються.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    docs = env['l10n_ua.tax.document'].search([('document_type_id.code', '=', 'F0103309')])
    docs._l10n_ua_after_import()
