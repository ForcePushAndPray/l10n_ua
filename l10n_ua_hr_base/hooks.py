"""Те, що має статись один раз при встановленні модуля.

Ієрархію класифікатора професій будувала лише міграція, а міграції на чистій
установці не виконуються — і кожна нова база отримувала плоский список із
9144 позицій. Хук закриває саме цей шлях; для наявних баз те саме зробила
міграція 19.0.1.0.5.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    kp2010 = env['hr.kp2010']
    kp2010._l10n_ua_build_hierarchy()
    _logger.info(
        'l10n_ua_hr_base: ієрархію КП-2010 побудовано — %s розділів, '
        '%s підрозділів, %s класів',
        kp2010.search_count([('level', '=', '1')]),
        kp2010.search_count([('level', '=', '2')]),
        kp2010.search_count([('level', '=', '3')]))

    # The companies already in the database get the typical tariff grades
    # here, the ones created later get them from `res.company.create`. The
    # data file does not seed: it runs on every update of the module and
    # would give back the grid a company deliberately deleted.
    seeded = env['hr.tariff.grade']._seed_company_grades()
    _logger.info('l10n_ua_hr_base: typical tariff grades given to %s '
                 'company(ies)', len(seeded.company_id))
