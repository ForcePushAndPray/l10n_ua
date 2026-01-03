{
    'name': 'Ukraine - HR Payroll',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Localization',
    'summary': 'Ukrainian payroll calculation',
    'description': """
Ukraine HR Payroll Module
=========================

Payroll calculation for Ukrainian localization:

* Salary calculation based on worked days/hours
* PDFO (personal income tax) - 18%
* Military tax - 5%
* ESV (unified social contribution) - 22%
* PSP (tax social benefit) calculation
* Allowances and bonuses
* Deductions (alimony, union fees, etc.)
* Execution documents support
* Minimum wage validation
* Maximum ESV base (15 minimum wages)
* Payslip generation and printing
* Bank payment registers

Requires l10n_ua_hr_contract module.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://ndev.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_hr_contract',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_accrual_type_data.xml',
        'data/hr_deduction_type_data.xml',
        'data/hr_psp_parameters_data.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/hr_accrual_type_views.xml',
        'views/hr_deduction_type_views.xml',
        'views/hr_psp_parameters_views.xml',
        'views/hr_execution_document_views.xml',
        'views/menu_views.xml',
        'report/hr_payslip_report.xml',
    ],
    'demo': [
        'demo/hr_payroll_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 299,
    'currency': 'EUR',
}
