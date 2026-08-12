"""Перерахувати надбавки, збережені від неконвертованого валютного окладу.

`calculated_amount` — збережене обчислюване поле, тож надбавка «10% від
окладу» у працівника з окладом 1000 USD лежить у базі як 100 грн. Нова
формула сама по собі її не зачепить: вона спрацює лише коли зміниться
котрась із залежностей.

Чіпаємо лише відсоток від окладу — фіксовані суми й відсоток від
мінімалки гривневі за побудовою, перераховувати там нема чого. Кожен запис
окремо: перерахунок без курсу кидає UserError, а невдале оновлення модуля
гірше за неточну суму в картці договору.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Allowance = env['hr.version.allowance']
    affected = Allowance.search([('calculation_method', '=', 'percent_salary')])
    if not affected:
        return

    recomputed = skipped = 0
    for allowance in affected:
        try:
            with env.cr.savepoint():
                env.add_to_compute(
                    Allowance._fields['calculated_amount'], allowance)
                allowance.flush_recordset(['calculated_amount'])
        except UserError:
            skipped += 1
        else:
            recomputed += 1

    _logger.info(
        'l10n_ua_hr_contract 19.0.5.0.0: перераховано %s надбавок '
        '«відсоток від окладу»', recomputed)
    if skipped:
        _logger.warning(
            'l10n_ua_hr_contract 19.0.5.0.0: %s надбавок лишились без '
            'перерахунку — немає курсу валюти окладу на їхню дату', skipped)
