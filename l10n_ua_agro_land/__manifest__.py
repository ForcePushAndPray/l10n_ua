{
    'name': 'Ukraine - Agro Land Bank and Land Share Lease',
    'version': '19.0.1.0.0',
    'category': 'Agriculture/Localization',
    'summary': 'Land plots, lease of land shares from individuals, rent accrual '
               'with PIT and military levy withholding, payment in money or in kind',
    'description': """
Ukraine - Agro Land Bank (земельний банк, оренда паїв)
======================================================

Part of the "Agro" industry solution (epic #477, issue #470).

* Land plots: cadastral number (validated), area, normative monetary
  valuation (NMV / НГО), land purpose code, ownership, owner, community
  (KATOTTG) and the field the plot belongs to.
* Land lease contracts: lessor, plots, term, state registration of the
  lease right, rent as a percentage of the NMV or a fixed amount, preferred
  payment form (money / in kind). One plot cannot be leased twice at the
  same time. Expiring contracts get an activity 90 days before the end and
  expire automatically.
* Rent accrual for a period: amounts prorated by days, withholding of the
  personal income tax (18 %) and the military levy (5 %) from individuals
  as a tax agent (Tax Code art. 168, income code 106), journal entry
  Dt expense / Ct 685, 6411, 642.
* Rent payment in money (cash / bank journal) or in kind (agricultural
  products: Dt 685 / Ct 712 and a delivery order from the warehouse);
  payments are reconciled with the accrual.
* Reports: lease register, area by owner, rent debts, withheld PIT by the
  community where the plot is located.

In-kind payment is booked as the sale of other current assets; VAT on
in-kind payments of VAT payers is not computed yet.
The 4DF bridge (``l10n_ua_agro_land_4df``) puts the rent into the
quarterly 4DF report with income code 106.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'stock',
        'l10n_ua_agro_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/land_plot_views.xml',
        'views/land_lease_views.xml',
        'views/rent_accrual_views.xml',
        'views/rent_payment_views.xml',
        'views/agro_field_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
