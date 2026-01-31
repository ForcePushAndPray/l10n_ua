{
    'name': 'Ukraine - Accounting Suite',
    'version': '19.0.3.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian accounting: PKO/VKO, Cash Book, Balance Sheet, P&L',
    'description': """
Ukraine Accounting Suite
========================

Complete Ukrainian accounting functionality for Odoo:

**Cash Operations (ПКО/ВКО):**
* Cash Receipt Orders (Прибуткові касові ордери, форма КО-1)
* Cash Disbursement Orders (Видаткові касові ордери, форма КО-2)
* Automatic numbering sequences per cash journal
* Ukrainian printed forms

**Cash Book (Касова книга):**
* Daily cash movements report
* Opening/closing balances
* Automatic calculations from posted payments
* Printable format

**Reconciliation Acts (Акти звірки):**
* Partner balance reconciliation
* Receivable/Payable filtering
* Opening/closing balances
* Printable format for signing

**Financial Statements:**
* Balance Sheet (Баланс, Форма №1)
* Profit & Loss Statement (Звіт про фінансові результати, Форма №2)
* Automatic calculation from Chart of Accounts
* Comparison with previous period
* PDF export

**Menu "Бухгалтерія UA":**
* Root menu with sequence 51
* Documents, Cash, Reports, Settings sections
* Links to OSV, Journal Orders from l10n_ua_account_base

Dependencies:
* l10n_ua_account_base - Base localization (directories, validators)
* l10n_ua_tax - Tax management
* l10n_ua_bank_sync - Bank synchronization
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'mail',
        'hr',
        'product',
        'uom',
        'l10n_ua_account_base',
        'l10n_ua_tax',
        'l10n_ua_tax_cabinet',
        'l10n_ua_bank_sync',
        'l10n_ua_bank_currency_sync',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Views
        'views/account_payment_views.xml',
        'views/account_journal_views.xml',
        'views/service_act_views.xml',
        'views/advance_report_views.xml',
        # Wizards
        'wizard/cash_book_wizard_views.xml',
        'wizard/reconciliation_act_wizard_views.xml',
        'wizard/balance_report_wizard_views.xml',
        'wizard/pnl_report_wizard_views.xml',
        # Menu
        'views/menu_views.xml',
        # Reports
        'report/report_templates.xml',
        'report/pko_report.xml',
        'report/vko_report.xml',
        'report/cash_book_report.xml',
        'report/reconciliation_act_report.xml',
        'report/balance_sheet_report.xml',
        'report/pnl_report.xml',
        'report/service_act_report.xml',
        'report/advance_report_report.xml',
        'report/invoice_report_inherit.xml',
    ],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
