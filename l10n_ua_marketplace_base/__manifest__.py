{
    'name': 'Ukraine - Marketplace Base',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Ukrainian marketplace integrations base module',
    'description': """
Ukraine Marketplace Base Module
===============================

Base module for Ukrainian marketplace integrations providing:

* Product extensions for marketplace publishing
* Abstract mixin for marketplace providers
* Feed generation (YML/XML)
* Order import base
* Category mapping

Requires l10n_ua_account_base module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'stock',
        'l10n_ua_account_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/l10n_ua_marketplace_category_views.xml',
        'views/l10n_ua_marketplace_order_views.xml',
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
