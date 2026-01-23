{
    'name': 'Ukraine - Tax Cabinet Integration',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Integration with cabinet.tax.gov.ua for document sync',
    'description': """
Ukraine Tax Cabinet Integration
===============================

Integration with cabinet.tax.gov.ua (Electronic Tax Cabinet) providing:

* Tax document storage (declarations, reports, receipts)
* Manual document upload (XML, PDF)
* Document categorization by type and period
* API sync with KEP authentication (token-based)

Allows FOP and companies to store and manage their tax documents
downloaded from the electronic tax cabinet.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_tax',
        'l10n_ua_account_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/l10n_ua_tax_document_type_data.xml',
        'wizard/l10n_ua_tax_cabinet_sync_wizard_views.xml',
        'wizard/l10n_ua_tax_cabinet_password_wizard_views.xml',
        'wizard/l10n_ua_tax_document_wizard_views.xml',
        'views/res_company_views.xml',
        'views/l10n_ua_tax_cabinet_document_views.xml',
        'views/l10n_ua_tax_cabinet_config_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'assets': {
        'web.assets_backend': [
            'l10n_ua_tax_cabinet/static/src/css/xml_viewer.css',
            'l10n_ua_tax_cabinet/static/src/js/xml_viewer_field.js',
            'l10n_ua_tax_cabinet/static/src/xml/xml_viewer_field.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
