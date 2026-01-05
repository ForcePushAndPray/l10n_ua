{
    'name': 'Ukraine - HR Timesheet',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Localization',
    'summary': 'Ukrainian timesheet management (Табель обліку робочого часу)',
    'description': """
Ukraine HR Timesheet Module
===========================

Timesheet management for Ukrainian localization (Табель П-5):

* Monthly timesheet (Табель обліку робочого часу)
* Standard Ukrainian timesheet codes (Я, В, Х, ВД, etc.)
* Automatic timesheet generation
* Integration with holidays and sick leaves
* Production calendar support
* Night hours tracking
* Overtime tracking
* Timesheet report (form П-5)

Requires l10n_ua_hr_base module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_hr_base',
        'l10n_ua_hr_holidays',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/hr_timesheet_code_data.xml',
        'views/hr_timesheet_views.xml',
        'views/hr_timesheet_code_views.xml',
        'views/hr_production_calendar_views.xml',
        'views/menu_views.xml',
        'report/hr_timesheet_report.xml',
    ],
    'demo': [
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 99,
    'currency': 'EUR',
}
