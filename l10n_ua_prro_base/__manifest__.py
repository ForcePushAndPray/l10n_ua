{
    'name': 'Ukraine - PRRO Base',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian PRRO (fiscal registrar) base module',
    'description': """
Ukraine PRRO Base Module
========================

Base module for Ukrainian PRRO (fiscal registrar) integrations providing:

* PRRO configuration model
* Fiscal receipt model
* Shift management
* Abstract mixin for PRRO providers

Requires l10n_ua_accounting module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_accounting',
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/l10n_ua_prro_config_views.xml',
        'views/l10n_ua_prro_receipt_views.xml',
        'views/l10n_ua_prro_shift_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
