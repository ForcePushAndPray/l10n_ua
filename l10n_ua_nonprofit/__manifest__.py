{
    'name': 'Ukraine - Non-profit Organizations',
    'version': '19.0.1.0.1',
    'category': 'Accounting/Localization',
    'summary': 'Ukrainian NGOs and charities: target financing (account 48), '
               'income recognition under P(S)BO 15, report on the use of income',
    'description': """
Ukraine - Non-profit Organizations (громадські організації, благодійні фонди)
=============================================================================

* Company setting "Non-profit organization": non-profit attribute code
  (0031-0048, CMU resolution of 13.07.2016 No. 440) and the decision on
  inclusion into the Register of non-profit institutions and organizations.
* Target programs / funding sources (donor, grant, membership fees,
  humanitarian aid) with an analytic account each: receipts are booked to
  account 48 and expenses tagged with the program analytic.
* Income recognition from account 48 (P(S)BO 15 "Income", para. 17): the
  income equals the expenses incurred on the program and is capped by the
  balance of 48. Runs from the period closing or on demand.
* Report on the use of income (profits) of a non-profit organization
  (Ministry of Finance order of 17.06.2016 No. 553 as amended by order of
  28.04.2017 No. 469, DPS form J0101911) - computed from the ledger,
  printable in the official layout.
* Program report: receipts, spending and balance per program / donor.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'analytic',
        'l10n_ua_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/nonprofit_security.xml',
        'data/analytic_plan_data.xml',
        'views/res_company_views.xml',
        'views/npo_program_views.xml',
        'views/npo_recognition_views.xml',
        'views/l10n_ua_period_closing_views.xml',
        'report/npo_income_report.xml',
        'report/npo_program_report.xml',
        'views/npo_income_report_views.xml',
        'wizard/npo_program_report_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
