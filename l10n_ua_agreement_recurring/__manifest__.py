{
    'name': 'Ukraine - Agreements: Recurring Invoices',
    'version': '19.0.1.0.0',
    'category': 'Sales/Localization',
    'summary': 'Monthly, quarterly or yearly invoices under an agreement, without OCA',
    'description': """
Ukraine Agreements: Recurring Invoices (Періодичні рахунки за договором)
=======================================================================

Абонентські договори (супровід, оренда, підписка) виставляють рахунки самі:

* на договорі — вкладка «Періодичні рахунки»: кожні N місяців / кварталів /
  років, дата наступного рахунку, рахунок за поточний період (передоплата) чи
  за минулий (післяоплата), проводити одразу чи лишати чернеткою;
* рядки: послуга чи товар, кількість, ціна, податки; в описі — період
  (``#PERIOD#`` → «жовтень 2026», «IV квартал 2026», «2026 рік»; ``#START#`` /
  ``#END#`` — дати);
* щоденний крон: для підписаних договорів — рахунок клієнту або постачальника
  на дату періоду, прив'язаний до договору (взаєморозрахунки
  ``l10n_ua_agreement_account``); пропущені періоди доганяються; після дати
  завершення договору рахунки не створюються;
* кнопка «Створити рахунок зараз» і лічильник рахунків договору.

Лише ядро Odoo й модулі l10n_ua — без OCA ``contract``.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'l10n_ua_agreement_account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/agreement_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
