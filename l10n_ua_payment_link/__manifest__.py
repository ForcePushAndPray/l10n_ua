{
    'name': 'Ukraine - Payment Links',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'NBU QR payment links + Monobank Acquiring',
    'description': """
Генерація платіжних посилань для українського бізнесу:
- QR-коди за стандартом НБУ (Постанова від 01.02.2021 №11)
- Інтеграція з Monobank Acquiring (еквайринг)
- Автоматичне підтвердження оплати через webhook
    """,
    'author': 'NDEV',
    'website': 'https://many2one.online',
    'license': 'LGPL-3',
    'depends': ['l10n_ua_account_base', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/nbu_qr_data.xml',
        'views/res_config_settings_views.xml',
        'views/account_journal_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'report/payment_link_report.xml',
        'report/report_invoice_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
