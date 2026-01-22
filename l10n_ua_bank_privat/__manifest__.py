{
    'name': 'Ukraine - PrivatBank Integration',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'PrivatBank API integration for bank statements',
    'description': """
Ukraine PrivatBank Integration
==============================

PrivatBank API integration providing:

* Privat24 Business Autoclient API support
* Legacy Merchant API support (for older integrations)
* Automatic bank statement import
* Corporate card support

Extends l10n_ua_bank_sync with PrivatBank-specific functionality.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_bank_sync',
    ],
    'data': [
        'views/l10n_ua_bank_privat_config_views.xml',
    ],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
