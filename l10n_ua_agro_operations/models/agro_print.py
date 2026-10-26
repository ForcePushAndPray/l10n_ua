from collections import OrderedDict

from odoo import fields, models


class AgroWorkOrder(models.Model):
    """Дані друкованих форм польових робіт: акти ВЗСГ-3 і ВЗСГ-4 (наказ
    Мінагрополітики № 929 від 21.12.2007, рекомендаційні) і обліковий лист
    тракториста-машиніста (ф. № 67-Б) — з проведених нарядів."""
    _inherit = 'l10n_ua.agro.work.order'

    responsible_id = fields.Many2one(
        'hr.employee', string='Agronomist / Foreman', tracking=True,
        help='Хто склав наряд і підписує акти списання.')
    storekeeper_id = fields.Many2one(
        'hr.employee', string='Storekeeper', tracking=True,
        help='Хто видав матеріали зі складу.')

    def _print_orders(self):
        return self.filtered(lambda o: o.state == 'done').sorted(lambda o: (o.date, o.id))

    def _print_header(self):
        orders = self._print_orders()
        company = (orders[:1] or self[:1]).company_id
        partner = company.partner_id
        return {
            'company': company,
            'edrpou': (company.edrpou if 'edrpou' in company._fields else '') or partner.edrpou or '',
            'chief': partner.l10n_ua_chief_name or '',
            'chief_position': partner.l10n_ua_chief_position or '',
            'date_from': min(orders.mapped('date')) if orders else False,
            'date_to': max(orders.mapped('date')) if orders else False,
            'years': ', '.join(str(y) for y in sorted(set(orders.mapped('season_id.year')))),
            'responsible': orders.responsible_id,
            'storekeepers': orders.storekeeper_id,
        }

    def _print_material_rows(self, material_types):
        """Рядки акта: поле × культура × матеріал за вибрані наряди."""
        rows = OrderedDict()
        for order in self._print_orders():
            card = order._tech_card()
            debit = order.company_id._l10n_ua_agro_ops_account(
                'l10n_ua_agro_production_account_id', ('231', '23'))
            for line in order.material_ids:
                if line.product_id.l10n_ua_agro_material_type not in material_types:
                    continue
                key = (order.planting_id, line.product_id)
                row = rows.setdefault(key, {
                    'field': order.field_id, 'crop': order.crop_id, 'planting': order.planting_id,
                    'product': line.product_id, 'uom': line.product_id.uom_id,
                    'ai': line.product_id.l10n_ua_agro_active_ingredient,
                    'debit': debit.code or '', 'credit': line._stock_account().code or '',
                    'norm_ha': sum(card.material_ids.filtered(
                        lambda m: m.product_id == line.product_id).mapped('rate_ha')),
                    'area': 0.0, 'quantity': 0.0, 'amount': 0.0, 'orders': self.browse(),
                })
                if order not in row['orders']:
                    row['area'] += order.area_done
                    row['orders'] |= order
                row['quantity'] += line.quantity
                row['amount'] += line.amount
        result = []
        for row in rows.values():
            row['quantity_ai'] = row['quantity'] * row['ai'] / 100.0 if row['ai'] else 0.0
            row['price'] = row['amount'] / row['quantity'] if row['quantity'] else 0.0
            row['actual_ha'] = row['quantity'] / row['area'] if row['area'] else 0.0
            row['dates'] = ', '.join(sorted({d.strftime('%d.%m') for d in row['orders'].mapped('date')}))
            result.append(row)
        return result

    def _print_operator_sheets(self):
        """Облікові листи (ф. 67-Б): по механізатору — рядки нарядів, пальне
        наряду ділиться між механізаторами пропорційно виробітку."""
        sheets = OrderedDict()
        for order in self._print_orders():
            total_volume = sum(order.worker_ids.mapped('volume'))
            fuel = order.material_ids.filtered('is_fuel')
            fuel_norm = sum(fuel.mapped('norm_quantity'))
            fuel_fact = sum(fuel.mapped('quantity'))
            for worker in order.worker_ids:
                share = worker.volume / total_volume if total_volume else 0.0
                sheet = sheets.setdefault(worker.employee_id, {
                    'employee': worker.employee_id, 'rows': [], 'days': set(),
                    'volume': 0.0, 'hours': 0.0, 'fuel_norm': 0.0, 'fuel_fact': 0.0, 'amount': 0.0})
                row = {
                    'date': order.date, 'order': order, 'operation': order.operation_type_id,
                    'unit': dict(order.operation_type_id._fields['unit']._description_selection(self.env)).get(
                        order.operation_type_id.unit, ''),
                    'field': order.field_id, 'crop': order.crop_id, 'machine': worker.machine_id,
                    'volume': worker.volume, 'hours': worker.hours, 'rate': worker.rate,
                    'fuel_norm': fuel_norm * share, 'fuel_fact': fuel_fact * share, 'amount': worker.amount,
                }
                sheet['rows'].append(row)
                sheet['days'].add(order.date)
                for key in ('volume', 'hours', 'fuel_norm', 'fuel_fact', 'amount'):
                    sheet[key] += row[key]
        for sheet in sheets.values():
            sheet['machine_days'] = len(sheet['days'])
        return list(sheets.values())
