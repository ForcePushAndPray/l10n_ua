"""Книги обліку доходів за всі квартали, де на рахунки ФОП надходили кошти.

Чернетки: користувач переглядає записи «не дохід», звіряє з поданими
деклараціями (повідомлення в книзі) і підтверджує.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['l10n_ua.fop.income.book']._backfill_all()
