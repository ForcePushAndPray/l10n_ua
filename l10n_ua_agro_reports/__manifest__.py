{
    'name': 'Ukraine - Agro Statistical Reports (4-sg, 29-sg, 50-sg)',
    'version': '19.0.1.0.1',
    'category': 'Accounting/Localization',
    'summary': 'Annual State Statistics Service reports of an agricultural enterprise: '
               'sown areas (4-sg), harvest (29-sg), economic indicators (50-sg)',
    'description': """
Ukraine - Agro Statistical Reports (статзвітність с/г підприємства)
===================================================================

Part of the "Agro" industry solution (epic #477, issue #475).

Annual forms of the State Statistics Service (Держстат), filed through the
«Кабінет респондента» (https://statzvit.ukrstat.gov.ua):

* **№ 4-сг** «Звіт про посівні площі сільськогосподарських культур»
  (order № 69 of 19.03.2026, from the report for the 2027 harvest): sown
  areas by crop row code from the plantings of the season, agricultural land
  by land type from the fields.
* **№ 29-сг** «Звіт про площі та валові збори сільськогосподарських
  культур, плодів, ягід і винограду» (order № 69, from the report for 2026):
  harvested area and gross harvest by crop from the harvest receipts, winter
  crops sown for the next year.
* **№ 50-сг** «Звіт про основні економічні показники роботи
  сільськогосподарських підприємств» (order № 174 of 09.07.2026, from the
  report for 2026): cost structure of the crop products from the posted
  season cost calculations, costs of the year by element (account 23 and 91),
  stocks and movement of the produce in quintals from the stock moves.

Every cell can be overridden by hand; cells Odoo has no data for (irrigated and
organic land, autumn tillage, livestock) are manual. Printed form and XLSX for
keying into the «Кабінет респондента».
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_company_base',
        'l10n_ua_agro_account',
        'l10n_ua_agro_land',
    ],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/agro_crop_data.xml',
        'views/agro_stat_report_views.xml',
        'views/agro_crop_views.xml',
        'views/res_partner_views.xml',
        'report/agro_stat_report.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
