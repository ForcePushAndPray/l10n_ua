{
    'name': 'Ukraine - Accounting',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian chart of accounts (P(S)BO)',
    'description': """
Ukraine Accounting Module
=========================

Ukrainian accounting localization providing:

* Chart of accounts according to P(S)BO (classes 0-9)
* Account extensions (ua_class, ua_subaccount, analytics_type)
* Document extensions (ua_doc_type, ua_doc_number)
* Journal orders (Журнали-ордери №1-7)
* General ledger (Головна книга)
* Trial balance / OSV (Оборотно-сальдова відомість)
* Balance sheet (Form №1)
* Income statement (Form №2)
* Cash book, PKO, VKO
* Advance reports

Requires l10n_ua_base module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_ua_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_chart_template_data.xml',
        'views/account_account_views.xml',
        'views/account_move_views.xml',
        'views/l10n_ua_journal_order_views.xml',
        'views/l10n_ua_osv_views.xml',
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
