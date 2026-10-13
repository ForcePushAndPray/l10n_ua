"""Податкова накладна → картка формату обміну M.E.Doc."""
import uuid

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

from ..tools.medoc_xml import MedocCard, fmt_date, fmt_number

# Версія форми ПН за Реєстром електронних форм ДПС (наказ Мінфіну № 1307
# у редакції наказу № 400 від 09.08.2024).
MEDOC_PN_FORM = '1201016'
MEDOC_RK_FORM = '1201216'

# Умовний ІПН і тип причини для ПН, складеної на неплатника ПДВ
# (Порядок № 1307, пп. 8, 12).
NON_PAYER_IPN = '100000000000'
NON_PAYER_REASON = '02'

# Ставка ПДВ рядка → (код ставки, поле обсягу, поле суми ПДВ) у шапці ПН
_RATE_TOTALS = {
    '20': ('20', 'A5_7', 'A6_7'),
    '7': ('7', 'A5_71', 'A6_71'),
    '14': ('14', 'A5_72', 'A6_72'),
    'exempt': ('903', 'A5_10', None),
}
_ZERO_EXPORT = ('901', 'A5_9', None)
_ZERO_DOMESTIC = ('902', 'A5_8', None)

# Те саме для розрахунку коригування (додаток 2). Поля підсумку за ставкою
# 14 % опис формату обміну M.E.Doc не наводить, тому її тут немає.
_RK_RATE_TOTALS = {
    '20': ('20', 'A1_9', 'A2_9'),
    '7': ('7', 'A1_91', 'A2_91'),
    'exempt': ('903', 'A1_11', None),
}
_RK_ZERO_EXPORT = ('901', 'A1_101', None)
_RK_ZERO_DOMESTIC = ('902', 'A1_10', None)


def medoc_docid(record):
    """Стабільний DOCID: повторний імпорт того ж запису не плодить дублікати."""
    dbuuid = record.env['ir.config_parameter'].sudo().get_param('database.uuid')
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, f'{dbuuid}/{record._name}/{record.id}')).upper()


def medoc_company_code(company):
    """Код, за яким M.E.Doc знаходить установу: ЄДРПОУ або РНОКПП ФОП."""
    return (company.edrpou or company.company_registry
            or company.partner_id.ipn or '').strip()


class L10nUaTaxInvoice(models.Model):
    _inherit = 'l10n_ua.tax.invoice'

    def _medoc_is_export(self):
        country = self.partner_id.country_id
        return bool(country) and country.code != 'UA'

    def _medoc_rate(self, line):
        """(код ставки, поле обсягу, поле суми ПДВ) рядка ПН або РК."""
        is_rk = self.doc_type == 'rk'
        if line.vat_rate == '0':
            if self._medoc_is_export():
                return _RK_ZERO_EXPORT if is_rk else _ZERO_EXPORT
            return _RK_ZERO_DOMESTIC if is_rk else _ZERO_DOMESTIC
        rate = (_RK_RATE_TOTALS if is_rk else _RATE_TOTALS).get(line.vat_rate)
        if not rate:
            # Мовчазна підстановка 20 % дала б у ЄРПН чужу суму ПДВ
            raise UserError(_(
                '%(name)s: експорт у M.E.Doc не підтримує ставку ПДВ '
                'рядка «%(line)s».',
                name=self.display_name, line=line.name))
        return rate

    def _medoc_buyer_ipn(self):
        """ІПН покупця-платника ПДВ; порожній — покупець неплатник.

        Платника визначає позначка контрагента, а не заповнений код:
        ``ipn`` — це й РНОКПП фізособи чи ФОП-неплатника, на яких ПН
        складається з умовним ІПН.
        """
        partner = self.partner_id
        # partner.ipn приймає лише 10 цифр, тож 12-значний ІПН юрособи — у vat
        ipn = (partner.ipn or partner.vat or '').strip()
        if partner.is_vat_payer:
            if not ipn:
                raise UserError(_(
                    '%(name)s: контрагент %(partner)s позначений платником '
                    'ПДВ, але не має ІПН.',
                    name=self.display_name, partner=partner.display_name))
            return ipn
        # 12-значний ІПН видається лише платникам ПДВ: без позначки ПН пішла
        # б на «Неплатника», і покупець втратив би податковий кредит.
        if len(ipn) == 12 and ipn.isdigit():
            raise UserError(_(
                '%(name)s: контрагент %(partner)s має 12-значний ІПН, але не '
                'позначений платником ПДВ. Поставте позначку «Платник ПДВ» '
                'або приберіть ІПН.',
                name=self.display_name, partner=partner.display_name))
        return ''

    def _medoc_new_card(self, form):
        """Картка з реквізитами продавця, спільними для ПН і РК."""
        company = self.company_id
        code = medoc_company_code(company)
        seller_ipn = company.l10n_ua_vat_ipn or company.partner_id.ipn or ''
        if not code or not seller_ipn:
            raise UserError(_(
                'Заповніть ЄДРПОУ та ІПН платника ПДВ у налаштуваннях '
                'компанії %(company)s.', company=company.display_name))
        # Юрособа має 8-значний ЄДРПОУ, ФОП — 10-значний РНОКПП
        prefix = 'J' if len(code) <= 8 else 'F'
        card = MedocCard([
            ('PERTYPE', '0'),
            ('PERDATE', fmt_date(self.date.replace(day=1))),
            ('DOCID', medoc_docid(self)),
            ('NOTATION', ''),
            ('CHARCODE', prefix + form),
        ])
        card.add('FIRM_EDRPOU', code)
        card.add('FIRM_INN', seller_ipn)
        card.add('FIRM_NAME', company.name)
        return card

    def _medoc_card(self):
        """Картка ПН або РК у форматі «для обміну звітністю»."""
        self.ensure_one()
        if self.invoice_type != 'issued':
            raise UserError(_(
                'У M.E.Doc вивантажуються лише видані документи; '
                '%(name)s — отриманий.', name=self.display_name))
        # Чернетка вивантажується: саме з M.E.Doc її реєструють у ЄРПН
        if self.state == 'cancelled':
            raise UserError(_(
                '%(name)s скасовано — у M.E.Doc такий документ не '
                'вивантажується.', name=self.display_name))
        if self.doc_type == 'rk':
            return self._medoc_rk_card()
        return self._medoc_pn_card()

    def _medoc_pn_card(self):
        """Податкова накладна (CHARCODE J/F1201016)."""
        card = self._medoc_new_card(MEDOC_PN_FORM)
        partner = self.partner_id
        card.add('N11', fmt_date(self.date))
        card.add('N2_1', self.number)
        card.add('N2_11', self.number)
        buyer_ipn = self._medoc_buyer_ipn()
        if buyer_ipn:
            card.add('N3', partner.name)
            card.add('N4', buyer_ipn)
            card.add('EDR_POK', partner.edrpou)
        else:
            card.add('N3', 'Неплатник')
            card.add('N4', NON_PAYER_IPN)
            card.add('N13', '1')
            card.add('N14', NON_PAYER_REASON)

        totals = {}
        vat_by_field = {}
        for idx, line in enumerate(self.line_ids):
            rate_code, base_field, vat_field = self._medoc_rate(line)
            totals[base_field] = totals.get(base_field, 0.0) + line.base_amount
            if vat_field:
                vat_by_field[vat_field] = (
                    vat_by_field.get(vat_field, 0.0) + line.vat_amount)
            card.add('TAB1_A1', idx + 1, tab=1, line=idx)
            card.add('TAB1_A13', line.name, tab=1, line=idx)
            card.add('TAB1_A131', line.uktzed_code, tab=1, line=idx)
            if line.is_import:
                card.add('TAB1_A132', '1', tab=1, line=idx)
            card.add('TAB1_A133', line.dkpp_code, tab=1, line=idx)
            card.add('TAB1_A14', line.uom_id.name, tab=1, line=idx)
            card.add('TAB1_A15', fmt_number(line.quantity, 6), tab=1, line=idx)
            card.add('TAB1_A16', fmt_number(line.price_unit, 6), tab=1, line=idx)
            card.add('TAB1_A8', rate_code, tab=1, line=idx)
            card.add('TAB1_A9', line.benefit_code, tab=1, line=idx)
            card.add('TAB1_A10', fmt_number(line.base_amount), tab=1, line=idx)
            if vat_field:
                card.add('TAB1_A20', fmt_number(line.vat_amount), tab=1, line=idx)

        for field_name, amount in {**totals, **vat_by_field}.items():
            card.add(field_name, fmt_number(amount))
        card.add('A6_11', fmt_number(self.total_vat))
        card.add('A7_11', fmt_number(self.total_amount))
        return card

    def _medoc_original_line_numbers(self):
        """Рядок РК → номер рядка ПН, що коригується (гр. 1 додатка 2).

        Зіставляємо за номенклатурою, а без неї — за описом: інакше РК не
        знає, який рядок оригіналу змінює, і ЄРПН його не прийме. Один товар
        може стояти в ПН кількома рядками, тому серед збігів беремо ще не
        зайнятий рядок, найперше — з тією самою ціною (РК змінює кількість
        за незмінної ціни).
        """
        numbers = {}
        used = set()
        unmatched = self.env['l10n_ua.tax.invoice.line']
        originals = list(enumerate(self.original_invoice_id.line_ids, 1))
        for line in self.line_ids:
            candidates = [
                (number, orig) for number, orig in originals
                if (line.product_id and orig.product_id == line.product_id)
                or (not line.product_id and orig.name == line.name)]
            if not candidates:
                unmatched |= line
                continue
            # False сортується перед True: вільний рядок, потім та сама ціна
            match = min(candidates, key=lambda item: (
                item[0] in used,
                float_compare(item[1].price_unit, line.price_unit,
                              precision_digits=6) != 0,
                item[0]))[0]
            used.add(match)
            numbers[line.id] = match
        if unmatched:
            raise UserError(_(
                '%(name)s: рядків немає в оригінальній ПН, тож невідомо, '
                'який її рядок вони коригують:\n%(lines)s',
                name=self.display_name,
                lines='\n'.join('— %s' % line.name for line in unmatched)))
        return numbers

    def _medoc_rk_card(self):
        """Розрахунок коригування (CHARCODE J/F1201216).

        Рядок РК у нас — це зміна кількості за незмінної ціни (гр. 5 і 6
        додатка 2); коригування ціни модель не зберігає.
        """
        original = self.original_invoice_id
        if not original:
            raise UserError(_(
                '%(name)s: вкажіть оригінальну ПН — без її номера й дати '
                'розрахунок коригування не складається.',
                name=self.display_name))
        line_numbers = self._medoc_original_line_numbers()
        card = self._medoc_new_card(MEDOC_RK_FORM)
        partner = self.partner_id
        card.add('N15', fmt_date(self.date))
        card.add('N1', self.number)
        card.add('N1_11', self.number)
        card.add('N2', fmt_date(original.date))
        card.add('N2_1', original.number)
        card.add('N2_11', original.number)
        buyer_ipn = self._medoc_buyer_ipn()
        if buyer_ipn:
            card.add('N3', partner.name)
            card.add('N4', buyer_ipn)
            card.add('EDR_POK', partner.edrpou)
        else:
            card.add('N3', 'Неплатник')
            card.add('N4', NON_PAYER_IPN)
            card.add('N17', '1')
            card.add('N18', NON_PAYER_REASON)
        # Зменшення суми компенсації реєструє покупець-платник ПДВ, решту
        # РК — постачальник (п. 192.1 ПКУ).
        by_buyer = bool(buyer_ipn) and self.total_base < 0
        card.add('N16' if by_buyer else 'N26', '1')

        totals = {}
        vat_by_field = {}
        for idx, line in enumerate(self.line_ids):
            rate_code, base_field, vat_field = self._medoc_rate(line)
            totals[base_field] = totals.get(base_field, 0.0) + line.base_amount
            if vat_field:
                vat_by_field[vat_field] = (
                    vat_by_field.get(vat_field, 0.0) + line.vat_amount)
            card.add('TAB1_A01', line_numbers[line.id], tab=1, line=idx)
            card.add('TAB1_A2', self.reason, tab=1, line=idx)
            card.add('TAB1_A3', line.name, tab=1, line=idx)
            card.add('TAB1_A31', line.uktzed_code, tab=1, line=idx)
            if line.is_import:
                card.add('TAB1_A32', '1', tab=1, line=idx)
            card.add('TAB1_A33', line.dkpp_code, tab=1, line=idx)
            card.add('TAB1_A4', line.uom_id.name, tab=1, line=idx)
            card.add('TAB1_A5', fmt_number(line.quantity, 6), tab=1, line=idx)
            card.add('TAB1_A6', fmt_number(line.price_unit, 6), tab=1, line=idx)
            card.add('TAB1_A011', rate_code, tab=1, line=idx)
            card.add('TAB1_A012', line.benefit_code, tab=1, line=idx)
            card.add('TAB1_A013', fmt_number(line.base_amount), tab=1, line=idx)

        for field_name, amount in {**totals, **vat_by_field}.items():
            card.add(field_name, fmt_number(amount))
        card.add('A2_92', fmt_number(self.total_vat))
        return card
