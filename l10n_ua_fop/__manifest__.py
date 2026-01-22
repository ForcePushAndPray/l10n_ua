{
    'name': 'Ukraine - FOP (Single Tax)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian single tax for individual entrepreneurs (FOP)',
    'description': """
Ukraine FOP Module
==================

Ukrainian single tax accounting for individual entrepreneurs (FOP) providing:

* Income book (Книга обліку доходів)
* Single tax declaration (groups 1, 2, 3)
* ESV calculation for FOP
* Tax rates by groups
* Income limits by groups

Requires l10n_ua_tax module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_tax',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/l10n_ua_fop_group_data.xml',
        'views/l10n_ua_fop_income_book_views.xml',
        'views/l10n_ua_fop_declaration_views.xml',
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
