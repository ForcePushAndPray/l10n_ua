{
    'name': 'Ukraine - Rozetka Marketplace',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Rozetka marketplace integration',
    'description': """
Ukraine Rozetka Marketplace
===========================

Rozetka marketplace integration providing:

* YML feed generation
* Stock synchronization
* Price synchronization
* Order import
* Order status updates
* Category mapping

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
