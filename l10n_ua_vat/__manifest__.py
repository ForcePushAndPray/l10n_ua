{
    'name': 'Ukraine - VAT',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian VAT accounting',
    'description': """
Ukraine VAT Module
==================

Ukrainian VAT accounting providing:

* VAT register (received and issued tax invoices)
* Tax invoice (Податкова накладна)
* Adjustment calculation (Розрахунок коригування)
* VAT declaration
* XML export for ERPN registration

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
        'views/l10n_ua_vat_register_views.xml',
        'views/l10n_ua_tax_invoice_views.xml',
        'views/l10n_ua_vat_declaration_views.xml',
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
