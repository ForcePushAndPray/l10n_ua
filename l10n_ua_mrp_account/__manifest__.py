{
    'name': 'Ukraine - Manufacturing Overhead Allocation',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Localization',
    'summary': 'Allocation of production overhead (account 91) and cost '
               'calculation of manufacturing orders under NP(S)BO 16',
    'description': """
Ukraine - Manufacturing Overhead Allocation
===========================================

Allocation of production overhead (загальновиробничі витрати, account 91)
under the Ukrainian accounting standard NP(S)BO 16 "Expenses", items 15-16:

* Variable overhead is allocated in full to work in progress (23).
* Fixed overhead is allocated at normal capacity:
  allocated = fixed x min(1, actual base / normal base);
  the unallocated part goes to the cost of sales (90x).
* Allocation base per company: direct labour cost (work centers), machine
  hours, direct material cost or quantity produced.
* The amount allocated to 23 is spread over the period's manufacturing orders
  in proportion to their base and added to the value of their finished
  products (stock move value, average / FIFO cost), Dt 26 Ct 23; the share
  already sold goes to the cost of sales.
* The period closing allocates the overhead automatically before the 9x
  accounts are closed (or refuses, if automatic allocation is off).
* Printable cost calculation (калькуляція собівартості) of a manufacturing
  order: materials, work centers, allocated overhead, unit cost.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'mrp_account',
        'l10n_ua_accounting',
        'l10n_ua_doc_reports',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/overhead_security.xml',
        'data/overhead_data.xml',
        'report/cost_calculation_report.xml',
        'views/overhead_allocation_views.xml',
        'views/res_company_views.xml',
        'views/period_closing_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
