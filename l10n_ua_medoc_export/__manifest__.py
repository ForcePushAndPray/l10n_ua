{
    'name': 'Ukraine - M.E.Doc XML Export',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Експорт ПН, РК, актів і рахунків-фактур у XML для імпорту в M.E.Doc',
    'description': """
Ukraine - M.E.Doc XML Export
============================

Формує XML-файли формату обміну M.E.Doc (кореневий елемент ``ZVIT``,
версія 4.1, windows-1251) для імпорту в ПК «M.E.Doc»:

* Податкова накладна (J1201016 / F1201016) — з ``l10n_ua.tax.invoice``
* Розрахунок коригування (J1201216 / F1201216) — з ``l10n_ua.tax.invoice``
* Акт на загальних підставах з ПДВ (``AKT_pdv``) — з рахунку клієнта
* Рахунок-фактура на загальних підставах з ПДВ (``RAH_pdv``) — з рахунку клієнта

Кілька документів одного виду вивантажуються одним файлом. Специфікації:
https://medoc.ua/page/integrationxml
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_account_vat',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/l10n_ua_medoc_export_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
