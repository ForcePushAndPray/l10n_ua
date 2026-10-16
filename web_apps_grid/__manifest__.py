{
    'name': 'Apps Grid Menu',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'Повноекранне меню додатків плитками для Odoo Community: пошук, закріплені, групи',
    'description': """
Apps Grid Menu
==============

Замінює випадний список додатків Odoo Community на повноекранну сітку плиток:

* пошук по додатках і пунктах меню, що розуміє неправильну розкладку
  («pdsn» → «звіт», «,fyr» → «банк»);
* закріплені (з перетягуванням) і нещодавні додатки;
* групи «Фінанси», «Кадри», «Продажі», «Склад і виробництво» або одна сітка;
* клавіатура: Alt+H — відкрити, стрілки, Enter, Esc;
* на /odoo без дії відкривається сама, як домашній екран;
* адаптивна верстка, кольори з теми.

Налаштування зберігаються в браузері для кожного користувача.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://many2one.online',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'web_apps_grid/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'web_apps_grid/static/tests/**/*',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
