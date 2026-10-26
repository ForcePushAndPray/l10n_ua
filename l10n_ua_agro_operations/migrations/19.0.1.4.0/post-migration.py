"""Проводки нарядів, проведених до 19.0.1.3.0, не мали товару в рядку витрат
на 23, і статзвітність (50-сг) не могла відрізнити насіння від добрив — усе
йшло в «решту матеріальних витрат». Проставляємо товар з рядків матеріалів
наряду: за назвою рядка проводки («<наряд>: <товар>»), інакше за єдиною
сумою. Пряме оновлення — проводки проведені, а товар на суми не впливає."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['l10n_ua.agro.work.order'].with_context(active_test=False).search([('move_id', '!=', False)])
    updates = []
    for order in orders:
        currency = order.company_id.currency_id
        free = order.move_id.line_ids.filtered(
            lambda l: l.l10n_ua_agro_planting_id and not l.product_id and l.debit)
        for material in order.material_ids.filtered(lambda m: m.amount):
            by_name = free.filtered(lambda l: l.name and l.name.endswith(material.product_id.display_name))
            by_amount = free.filtered(lambda l: currency.compare_amounts(l.debit, material.amount) == 0)
            line = (by_name & by_amount)[:1] or (by_name if len(by_name) == 1 else by_amount if len(by_amount) == 1
                                                   else env['account.move.line'])
            if line:
                updates.append((material.product_id.id, line.id))
                free -= line
    for product_id, line_id in updates:
        cr.execute('UPDATE account_move_line SET product_id = %s WHERE id = %s', (product_id, line_id))
