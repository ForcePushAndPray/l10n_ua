{
    'name': 'Ukraine - monobank Payment Provider',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': 'Оплата карткою на сайті та в порталі через monobank (plata by mono)',
    'description': """
Платіжний провайдер monobank (plata by mono)
============================================

Стандартний платіжний провайдер Odoo (``payment.provider``) для інтернет-еквайрингу
monobank: працює в eCommerce, на порталі клієнта та в платіжних посиланнях.

* рахунок monobank створюється під час оплати, покупець переходить на сторінку оплати;
* статус підтверджується запитом до API monobank (webhook лише сигналізує про зміну);
* рахунок у валюті замовлення (UAH, USD, EUR) або з конвертацією в гривню за курсом Odoo;
* тестовий і бойовий режими — за токеном.

Незалежний від l10n_ua_mono_acquiring (посилання на оплату з журналу) та
l10n_ua_bank_mono (виписки).
    """,
    'author': 'NDEV',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': ['payment'],
    'data': [
        'views/payment_mono_templates.xml',
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
