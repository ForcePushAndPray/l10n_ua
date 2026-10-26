{
    'name': 'Ukraine - Agro Land Rent in 4DF',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Land rent paid to individuals in the quarterly 4DF report '
               '(income code 106)',
    'description': """
Ukraine - Agro Land Rent in 4DF
===============================

Bridge between ``l10n_ua_agro_land`` and ``l10n_ua_tax_4df`` (issue #470),
installed automatically when both are present.

* Appendix 4DF lines can belong to a partner (lessor) instead of an
  employee.
* Generating the 4DF adds the land rent of individual lessors for the
  quarter with income code 106: accrued and withheld amounts from the
  posted rent accruals, the paid income from the rent payments (gross
  amount corresponding to the net paid).
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_agro_land',
        'l10n_ua_tax_4df',
    ],
    'data': [
        'views/l10n_ua_tax_4df_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'price': 0,
    'currency': 'EUR',
}
