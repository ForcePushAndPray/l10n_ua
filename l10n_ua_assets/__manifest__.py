{
    'name': 'Ukraine - Fixed Assets',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian fixed assets and low-value assets (MNMA)',
    'description': """
Ukraine Fixed Assets Module
===========================

Ukrainian fixed assets localization providing:

* Fixed asset groups (1-16 according to Tax Code)
* Depreciation methods (straight-line, declining balance, production, cumulative)
* Inventory card OZ-6
* MNMA (low-value non-current tangible assets) with 50/50 or 100% write-off
* Commissioning act
* Write-off act

Requires l10n_ua_accounting module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'account_asset',
        'l10n_ua_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/l10n_ua_asset_group_data.xml',
        'views/account_asset_views.xml',
        'views/l10n_ua_mnma_views.xml',
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
