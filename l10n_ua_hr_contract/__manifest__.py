{
    'name': 'Ukraine - HR Contracts',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Localization',
    'summary': 'Ukrainian HR contracts localization',
    'description': """
Ukraine HR Contracts Module
===========================

Extension of HR contracts for Ukrainian localization:

* Contract types (permanent, fixed-term, civil, gig-contract)
* Main workplace / part-time work tracking
* Work modes (full-time, part-time, flexible, remote)
* Work schedules (5-day, shift work, etc.)
* Probation period management
* Contract allowances (seniority, hazard, intensity)
* Termination reasons according to Ukrainian Labor Code
* Staffing table integration
* Tariff grade support
* Diia.City employee support

Requires l10n_ua_hr_base module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_hr_base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_allowance_type_data.xml',
        'data/hr_work_schedule_data.xml',
        'data/hr_termination_reason_data.xml',
        'views/hr_allowance_type_views.xml',
        'views/hr_contract_allowance_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_contract_salary_change_views.xml',
        'views/hr_job_combining_views.xml',
        'views/hr_contract_amendment_views.xml',
        'views/hr_work_schedule_views.xml',
        'views/hr_termination_reason_views.xml',
        'views/hr_employee_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [
        'demo/hr_contract_demo.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 19,
    'currency': 'EUR',
}
