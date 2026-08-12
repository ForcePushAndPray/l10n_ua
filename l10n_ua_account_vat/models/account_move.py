from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_ids = fields.One2many(
        'l10n_ua.tax.invoice',
        'move_id',
        string='Податкові накладні',
    )
    tax_invoice_count = fields.Integer(
        string='Кількість ПН',
        compute='_compute_tax_invoice_count',
    )

    @api.depends('tax_invoice_ids')
    def _compute_tax_invoice_count(self):
        for move in self:
            move.tax_invoice_count = len(move.tax_invoice_ids)

    # Ставки ПДВ, передбачені ПКУ. Ключ — `amount` відсоткового податку.
    _L10N_UA_VAT_RATES = {20.0: '20', 14.0: '14', 7.0: '7', 0.0: '0'}

    @api.model
    def _l10n_ua_vat_rate_for_line(self, invoice_line):
        """Ставка ПДВ рядка ПН за податками рядка документа.

        Повертає 'exempt', якщо ПДВ на рядку немає взагалі. Раніше тут стояв
        дефолт '20', тобто рядок без ПДВ потрапляв у ПН як оподаткований за
        основною ставкою — помилка, яка завищує зобовʼязання.

        Розрізнити звільнення (ст. 197) і необ'єкт (ст. 196) за самим фактом
        відсутності податку неможливо; для цього потрібні окремі податки з
        явною ознакою.
        """
        return self._l10n_ua_vat_rate_from_taxes(invoice_line.tax_ids)

    @api.model
    def _l10n_ua_vat_rate_from_taxes(self, taxes):
        """Перший відсотковий податок зі ставкою ПКУ, інакше 'exempt'.

        Групу податків розкриваємо: ПДВ часто входить до групи разом з іншим
        податком (акциз, збір), і без цього кроку оподаткований рядок мовчки
        ставав би звільненим з нульовою сумою.
        """
        for tax in taxes:
            if tax.amount_type == 'group':
                rate = self._l10n_ua_vat_rate_from_taxes(tax.children_tax_ids)
                if rate != 'exempt':
                    return rate
            elif tax.amount_type == 'percent' and tax.amount in self._L10N_UA_VAT_RATES:
                return self._L10N_UA_VAT_RATES[tax.amount]
        return 'exempt'

    def action_create_tax_invoice(self):
        """Create a tax invoice (ПН) from customer/vendor invoice."""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('Створити ПН можна тільки для проведеного документа.'))

        if self.move_type in ('out_invoice', 'out_refund'):
            invoice_type = 'issued'
        elif self.move_type in ('in_invoice', 'in_refund'):
            invoice_type = 'received'
        else:
            raise UserError(_('ПН можна створити тільки для рахунків.'))

        is_refund = self.move_type in ('out_refund', 'in_refund')

        # Build lines from invoice lines.
        #
        # Фільтр саме `display_type == 'product'`: у Odoo 17+ звичайний рядок
        # має display_type 'product', а не порожній, тож умова `not display_type`
        # (написана під Odoo <=16) відкидала геть усі рядки й ПН виходила
        # порожньою. `invoice_line_ids` містить ще секції та примітки — їм у ПН
        # робити нічого.
        # РК зменшує зобов'язання: за Порядком 1307 у гр. 6 стоїть від'ємна
        # кількість при незмінній ціні. Доки цикл не виконувався, гілка refund
        # була безпечно порожньою; тепер вона створює документ, і без знаку РК
        # збільшував би зобов'язання замість зменшувати.
        sign = -1 if is_refund else 1

        line_vals = []
        seq = 10
        for iline in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            # Суму беремо з проводки, а не з `price_subtotal`: ПН завжди у
            # гривні (`currency_id` — related на валюту компанії), а проводка
            # вже перерахована за курсом документа. Перераховувати кожен рядок
            # окремо не варто — округлення дало б копійчаний дрейф від суми
            # документа. `direction_sign` знімає знак дебету/кредиту.
            subtotal = iline.balance * self.direction_sign
            # Ціна за одиницю після знижки й без ПДВ. Зберігати сирий
            # `price_unit` не можна: рядок ПН рахує базу як quantity *
            # price_unit, і знижка зникла б. Для <CINA> в XML ЄРПН потрібна
            # саме фактична ціна постачання.
            net_unit_price = subtotal / iline.quantity if iline.quantity else 0.0

            line_vals.append((0, 0, {
                'sequence': seq,
                'product_id': iline.product_id.id if iline.product_id else False,
                'name': iline.name or iline.product_id.display_name or '',
                'uktzed_code': iline.product_id.l10n_ua_uktzed if hasattr(iline.product_id, 'l10n_ua_uktzed') else '',
                'quantity': sign * iline.quantity,
                'uom_id': iline.product_uom_id.id if iline.product_uom_id else False,
                'price_unit': net_unit_price,
                'vat_rate': self._l10n_ua_vat_rate_for_line(iline),
            }))
            seq += 10

        # Get next number
        seq_code = f'l10n_ua.tax.invoice.{invoice_type}'
        number = self.env['ir.sequence'].next_by_code(seq_code) or _('Новий')

        vals = {
            'invoice_type': invoice_type,
            'doc_type': 'rk' if is_refund else 'pn',
            'number': number,
            'date': fields.Date.context_today(self),
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'move_id': self.id,
            'line_ids': line_vals,
        }
        if is_refund:
            # РК без посилання на оригінал ЄРПН не приймає. Знаходимо ПН
            # сторнованого документа; якщо її немає (ПН виписана поза
            # системою), поле лишається порожнім для ручного заповнення.
            original = self.reversed_entry_id.tax_invoice_ids[:1]
            vals.update({
                'original_invoice_id': original.id,
                'reason': self.ref or '',
            })

        tax_invoice = self.env['l10n_ua.tax.invoice'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.tax.invoice',
            'res_id': tax_invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_tax_invoices(self):
        """Open related tax invoices."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Податкові накладні'),
            'res_model': 'l10n_ua.tax.invoice',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }
        if self.tax_invoice_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.tax_invoice_ids[0].id
        return action
