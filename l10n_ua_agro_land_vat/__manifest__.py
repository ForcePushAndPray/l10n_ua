{
    'name': 'Ukraine - Agro VAT on In-kind Land Rent',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'VAT on land rent paid in kind by a VAT payer: tax liability and tax '
               'invoices to the lessors (non-payers, reason type 02)',
    'description': """
Ukraine - Agro VAT on In-kind Land Rent
=======================================

Bridge between ``l10n_ua_agro_land`` and ``l10n_ua_account_vat`` (issue #488),
installed automatically when both are present.

For a VAT payer, handing over produce as land rent is a supply of goods (Tax
Code subp. 14.1.191): posting an in-kind rent payment

* computes VAT at the rate of the product's sales tax (14 % for the grain
  and oilseeds of p. 193.1 "в", 20 % otherwise);
* posts the tax liability - VAT included in the value of the produce
  (Dt 712 / Ct 641) or charged on top of it as an expense (Dt 94 / Ct 641),
  as set in the company;
* creates a tax invoice for every lessor - not given to the buyer, reason
  type 02 (supply to a non-payer), buyer "Неплатник" 100000000000 - which
  goes to the register of issued tax invoices and the VAT return.

Cancelling the payment cancels the draft tax invoices and reverses the VAT
entry; a tax invoice already registered in the ERPN has to be corrected by
an adjustment calculation first.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_agro_land',
        'l10n_ua_account_vat',
    ],
    'data': [
        'views/rent_payment_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'price': 0,
    'currency': 'EUR',
}
