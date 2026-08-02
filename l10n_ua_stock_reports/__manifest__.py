{
    'name': 'Ukraine - Stock Reports',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Localization',
    'summary': 'Ukrainian warehouse forms: material report М-19',
    'description': """
Ukraine - Stock Reports
=======================

Ukrainian warehouse paperwork on top of the standard Inventory app, without
pulling in the accounting localization.

* Матеріальний звіт (form М-19) — opening balance, receipts, issues and
  closing balance per product for one storage location and period.

The М-19 order (Мінстат No 193 of 21.06.1996) has been repealed, but the
obligation to account for materials held by a person in charge has not, so
the form is still what Ukrainian accountants ask for.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/m19_material_report.xml',
        'wizard/m19_material_report_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
