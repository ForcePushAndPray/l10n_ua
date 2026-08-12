from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


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

    def _l10n_ua_first_payment_date(self):
        """Дата найранішого фактичного погашення або False, якщо його немає.

        Рахуємо із зіставлення рядків розрахунків, а не з
        `matched_payment_ids`: погашення випискою напряму, залік кредит-ноти
        чи взаємозалік не мають об'єкта `account.payment`, і касовий метод
        вважав би такий документ неоплаченим — з відмовою створити ПН на
        операцію, за якою зобов'язання вже виникло.

        Дата — це дата проводки з того боку зіставлення, тобто самого
        платежу. Не `max_date` часткового зіставлення: там пізніша з двох
        дат, і передоплата отримала б дату рахунка замість дати грошей.

        Критерій — саме факт погашення рядка розрахунків, а не стан платежу:
        чернетка нічого не зіставляє й сюди не потрапляє в принципі.

        Зарахованим вважається будь-яке зіставлення, бо п. 187.10 визнає не
        лише кошти, а й «інші види компенсацій» — залік, бартер, погашення
        кредит-нотою. Списання безнадійного боргу під це не підпадає, але
        відрізнити його від заліку можна хіба що за наміром користувача, а
        зайва ПН на списаний борг — менша шкода, ніж пропущене зобов'язання
        за заліком.
        """
        self.ensure_one()
        settlement_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'))
        partials = (settlement_lines.matched_debit_ids
                    | settlement_lines.matched_credit_ids)
        counterparts = (partials.debit_move_id
                        | partials.credit_move_id) - settlement_lines
        dates = counterparts.mapped('date')
        return min(dates) if dates else False

    def _l10n_ua_tax_invoice_rule(self):
        """Правило, за яким визначається дата ПН для цієї операції.

        Правило визнання визначає дату лише **наших власних** ПН:

        * вхідна ПН — чужий документ, її дату склав постачальник за своїм
          правилом. Наша неоплата не може бути перешкодою: ПН від
          постачальника вже існує, а касовий метод впливає на період
          податкового кредиту, а не на її дату;
        * РК складається на дату коригуючої події — повернення товару чи
          коштів, зміни ціни. Дата першої події оригіналу тут ні до чого,
          бо від дати РК рахується власний строк реєстрації в ЄРПН.

        В обох випадках дата береться з документа ('document').
        """
        self.ensure_one()
        if self.move_type in ('in_invoice', 'in_refund', 'out_refund'):
            return 'document'
        if self.partner_id.with_company(self.company_id).l10n_ua_vat_cash_method:
            return 'cash'
        return 'first_event'

    def _l10n_ua_tax_invoice_date(self):
        """Дата ПН за правилом визнання, застосовним до цієї операції.

        Касовий метод (п. 187.10 ПКУ): дата руху коштів. Поки оплати немає,
        податкове зобовʼязання не виникло і ПН складати нема на що.

        Перша подія (загальне правило, ст. 187): раніша з дати відвантаження
        і дати оплати. Дату відвантаження беремо як дату документа —
        окремого обліку відвантажень тут немає, і для післяоплати це та сама
        дата; для передоплати раніший саме платіж, тому й порівнюємо.
        """
        self.ensure_one()
        rule = self._l10n_ua_tax_invoice_rule()
        doc_date = self.invoice_date or self.date
        if rule == 'document':
            return doc_date

        payment_date = self._l10n_ua_first_payment_date()

        if rule == 'cash':
            if not payment_date:
                raise UserError(_(
                    'За контрагентом «%s» застосовується касовий метод ПДВ, '
                    'тож ПН складається за датою оплати. Документ ще не оплачений.',
                    self.partner_id.display_name))
            # За п. 187.10 зобов'язання виникає на суму кожного надходження,
            # а розбиття ПН по погашеннях ще не реалізоване. На частково
            # оплаченому документі вийшла б одна ПН на повну суму датою
            # першої оплати — завищене зобов'язання в періоді й жодної ПН на
            # решту. Краще відмовити, ніж мовчки видати такий документ.
            if not self.currency_id.is_zero(self.amount_residual):
                raise UserError(_(
                    'Документ оплачений частково: залишок %(residual)s. За касовим '
                    'методом ПН складається на суму кожного надходження, а такий '
                    'поділ ще не реалізовано — ПН вийшла б на повну суму документа '
                    'датою першої оплати. Складіть ПН після повної оплати або '
                    'заведіть її вручну.',
                    residual=formatLang(self.env, self.amount_residual,
                                        currency_obj=self.currency_id)))
            return payment_date

        if payment_date and payment_date < doc_date:
            return payment_date
        return doc_date

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
            # Дата ПН — дата виникнення податкового зобовʼязання, а не день
            # натискання кнопки: від неї рахується строк реєстрації в ЄРПН і
            # період декларації.
            'date': self._l10n_ua_tax_invoice_date(),
            'vat_method': self._l10n_ua_tax_invoice_rule(),
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
