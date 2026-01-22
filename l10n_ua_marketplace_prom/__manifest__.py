{
    'name': 'Ukraine - Prom.ua Marketplace',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Prom.ua marketplace integration',
    'description': """
Ukraine Prom.ua Marketplace
===========================

Prom.ua marketplace integration providing:

* Feed generation (YML or Prom XML)
* Product sync via API
* Order import
* Order status updates
* Stock management

Requires l10n_ua_marketplace_base module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_marketplace_base',
    ],
    'data': [],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
