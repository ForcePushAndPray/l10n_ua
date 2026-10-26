{
    'name': 'Ukraine - Export (Foreign Trade)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Export sales: foreign trade contracts, export customs declarations, '
               'VAT 0 % tax invoices, currency control, bilingual invoice and packing list',
    'description': """
Ukraine - Export (зовнішньоекономічні продажі)
==============================================

Issue #476 (epic #477 "Agro"), generic for any exporter.

* Foreign trade contract: the agreement gets the foreign trade flag, the
  Incoterms basis and the settlement deadline in days (currency control).
* Export customs declaration (ЕК-10): number, date, customs value, buyer,
  contract, the export invoices and deliveries, the phytosanitary
  certificate, the certificate of origin and the quality certificate.
* Tax invoice for the export: VAT 0 %, not given to the buyer, reason type
  07, dated the customs declaration (first event, p. 187.1 of the Tax
  Code), base - the contract value at the NBU rate of that date; it goes to
  row 2.1 of the VAT return.
* Currency control: settlement deadline from the date of the customs
  declaration, unpaid balance in the contract currency, states open / due
  soon / overdue / settled, a reminder 30 days before the deadline.
* Printed bilingual (English / Ukrainian) commercial invoice and packing
  list with lots and weights.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'l10n_ua_agreement_account',
        'l10n_ua_account_vat',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_cron_data.xml',
        'views/agreement_views.xml',
        'views/customs_declaration_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'report/export_reports.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
