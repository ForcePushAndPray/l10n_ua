{
    'name': 'Ukraine - Agro Operator Piece Pay',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Piece-rate pay of machine operators from field work orders',
    'description': """
Ukraine - Agro Operator Piece Pay
=================================

Bridge between ``l10n_ua_agro_operations`` and ``l10n_ua_hr_salary``
(issue #471), installed automatically when both are present.

Validating a field work order creates a piece-work entry
(``hr.piece.work.entry``) for every operator: output x piece rate. Payroll
sums the entries of the month into the "Piece-rate pay" accrual of the
employees paid by the piece. Cancelling the work order removes the entries,
unless a validated payslip already covers that day.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_agro_operations',
        'l10n_ua_hr_salary',
    ],
    'data': [],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': True,
    'price': 0,
    'currency': 'EUR',
}
