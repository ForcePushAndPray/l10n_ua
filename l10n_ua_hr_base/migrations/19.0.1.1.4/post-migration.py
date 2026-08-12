"""Добудувати ієрархію КП-2010 базам, які встановились без неї.

`post_init_hook` рятує лише нові установки. Бази, де модуль поставили після
міграції 19.0.1.1.0 і до появи хука, лишились із плоским класифікатором:
міграція для них уже відпрацювала колись давно, а хук не виконувався ніколи.

Викликаємо той самий метод, що й хук: він ідемпотентний, тож базам, де
ієрархія вже є, нічого не зробить.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hr.kp2010']._l10n_ua_build_hierarchy()
    _logger.info('l10n_ua_hr_base 19.0.1.1.4: ієрархію КП-2010 звірено')
