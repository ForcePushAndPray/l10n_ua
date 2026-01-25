{
    'name': 'Ukraine - Full Accounting Suite',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Complete Ukrainian accounting localization (cumulative module)',
    'description': """
Ukraine Full Accounting Suite
=============================

This is a cumulative module that installs the complete Ukrainian
accounting localization for Odoo.

Includes:
* l10n_ua_account_base - Base localization (directories, chart of accounts)
* l10n_ua_tax - Tax management (periods, reports, budget codes)
* l10n_ua_tax_cabinet - Tax Cabinet integration (cabinet.tax.gov.ua)
* l10n_ua_bank_sync - Bank synchronization (PrivatBank, Mono, PUMB)
* l10n_ua_bank_currency_sync - Currency rates (NBU, PrivatBank, Mono)

Install this module to get all Ukrainian accounting features at once.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_account_base',
        'l10n_ua_tax',
        'l10n_ua_tax_cabinet',
        'l10n_ua_bank_sync',
        'l10n_ua_bank_currency_sync',
    ],
    'data': [],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
