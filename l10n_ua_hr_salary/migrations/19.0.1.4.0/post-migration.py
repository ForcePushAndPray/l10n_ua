"""Перерахувати чернетки авансів, збережені за неконвертованим окладом.

`gross_amount` — збережене обчислюване поле, тож суми, пораховані до
переходу на курс, лишаються в базі як є: працівник із окладом 1000 USD має
в чернетці аванс 500 грн замість двадцяти з гаком тисяч. Нове обчислення
саме по собі їх не зачепить — воно спрацює лише коли зміниться якась із
залежностей.

Чіпаємо винятково чернетки: підтверджений чи виплачений аванс — це вже
факт, а не розрахунок, і переписувати його заднім числом не можна.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Advance = env['hr.salary.advance']
    drafts = Advance.search([('state', '=', 'draft')])
    if not drafts:
        return
    env.add_to_compute(Advance._fields['gross_amount'], drafts)
    drafts.flush_recordset(['gross_amount'])
    _logger.info(
        'l10n_ua_hr_salary 19.0.1.4.0: перераховано %s чернеток авансу',
        len(drafts))
