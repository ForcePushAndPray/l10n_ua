{
    'name': 'Ukraine - Tax',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian tax accounting base module',
    'description': """
Ukraine Tax Module
==================

Ukrainian tax accounting base module providing:

* Tax extensions (ua_tax_type, ua_tax_code, ua_budget_code)
* Base taxes: PDFO 18%, Military tax 5%, ESV 22%, VAT 20%/7%/0%
* Tax periods (month, quarter, year)
* Base tax reporting model
* Budget classification codes

Requires l10n_ua_accounting module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_tax_data.xml',
        'data/l10n_ua_budget_code_data.xml',
        'views/account_tax_views.xml',
        'views/l10n_ua_tax_period_views.xml',
        'views/l10n_ua_tax_report_views.xml',
        'views/res_company_views.xml',
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
