{
    'name': 'Ukraine - Single Tax Declaration (Legal Entities, Group 3)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localization',
    'summary': 'Декларація платника єдиного податку третьої групи (юридичної особи), J0103509',
    'description': """
Декларація платника єдиного податку третьої групи для ТОВ, ПП та інших юросіб
(наказ Мінфіну № 578 у редакції наказу № 57 від 31.01.2025):

* дохід касовим методом — оплати покупців з бухобліку, без ПДВ для ставки 3 %;
* розрахунок єдиного податку й військового збору наростаючим підсумком;
* XML J0103509 за XSD ДПС, підпис КЕП у браузері й подання через Електронний кабінет.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_ua_tax',
        'l10n_ua_tax_cabinet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/multicompany_security.xml',
        'views/l10n_ua_single_tax_declaration_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
