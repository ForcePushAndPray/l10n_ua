{
    'name': 'Ukraine - Education Scholarship',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Education',
    'summary': 'Стипендії учнів і студентів: типи, відомості виплати, lifecycle',
    'description': """
Ukraine Education Scholarship
=============================

Облік стипендій для учнів і студентів українських закладів освіти.

* Типи стипендій: академічна, соціальна, президентська, іменна,
  стипендія Верховної Ради, обласна.
* Відомості виплати стипендій з рядками по членах контингенту,
  state machine: draft → approved → paid → cancelled.
* Прив'язка до бюджетного обліку: КЕКВ 2720 (стипендії), фонд за вибором,
  опційно КПКВК.
* Інтеграція з l10n_ua_budget_treasury: якщо встановлено — спрацьовує
  контроль ліміту при проведенні платежу.

Регуляторна база:
* Постанова КМУ № 1146 від 28.12.2016 — Положення про порядок призначення
  і виплати стипендій (актуальну редакцію звіряти на rada.gov.ua)
* Постанова КМУ № 1101 — для академічних стипендій ВНЗ
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_education_base',
        'l10n_ua_budget_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/l10n_ua_scholarship_type_data.xml',
        'data/ir_sequence_data.xml',
        'views/l10n_ua_scholarship_type_views.xml',
        'views/l10n_ua_scholarship_payment_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
