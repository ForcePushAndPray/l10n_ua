{
    'name': 'Ukraine - HR',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Localization',
    'summary': 'Українська локалізація HR для Odoo',
    'description': """
Українська локалізація HR
=========================

Мета-модуль, що встановлює всі необхідні компоненти для українського кадрового обліку:

* l10n_ua_hr_base - базовий модуль HR
* l10n_ua_hr_holidays - відпустки (планується)
* l10n_ua_hr_payroll - розрахунок заробітної плати (планується)

    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_hr_base',
    ],
    'data': [],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'price': 199,
    'currency': 'EUR'
}
