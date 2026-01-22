{
    'name': 'Ukraine - Base Localization',
    'version': '19.0.1.0.0',
    'category': 'Localization',
    'summary': 'Ukrainian localization base module',
    'description': """
Ukraine Base Localization Module
================================

Foundation module for all Ukrainian localization modules providing:

* Partner extensions (EDRPOU, IPN/RNOKPP validation)
* KOATUU/KATOTTG directory (19000+ records)
* KVED-2010 classifier (1500+ records)
* Tax offices (ДПІ) directory
* Ukrainian address format mixin
* Document formatting mixin (dates, amounts in Ukrainian)
* Validators (EDRPOU, IPN, IBAN)
* Formatters (dates, money, numbers to words)

This module is required for all other l10n_ua_* modules.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/res_country_state_data.xml',
        'data/l10n_ua_koatuu_data.xml',
        'data/l10n_ua_kved_data.xml',
        'data/l10n_ua_tax_office_data.xml',
        'data/l10n_ua_legal_form_data.xml',
        'views/res_partner_views.xml',
        'views/l10n_ua_koatuu_views.xml',
        'views/l10n_ua_kved_views.xml',
        'views/l10n_ua_tax_office_views.xml',
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
