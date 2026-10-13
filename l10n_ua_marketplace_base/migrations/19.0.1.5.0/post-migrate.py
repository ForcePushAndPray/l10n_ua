"""Перерахувати ознаку «Опубліковано в маркетплейсах».

До 19.0.1.5.0 це була ручна галочка, і колонка в базі вже існує зі значеннями
False. Odoo перераховує збережене обчислюване поле лише тоді, коли створює
колонку, тож без цієї міграції всі наявні товари лишились би «не опублікованими».
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE product_template pt
           SET marketplace_published = EXISTS (
                   SELECT 1
                     FROM marketplace_pricelist_item i
                    WHERE i.product_tmpl_id = pt.id
                      AND i.active
               )
    """)
