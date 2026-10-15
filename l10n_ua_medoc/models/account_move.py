"""Рахунок клієнта → первинний документ M.E.Doc (акт або рахунок-фактура)."""
from odoo import models, _
from odoo.exceptions import UserError

from odoo.addons.l10n_ua_account_base.tools.formatters import amount_to_words_ua

from ..tools.medoc_xml import MedocCard, fmt_date, fmt_number
from .l10n_ua_tax_invoice import medoc_company_code, medoc_docid

# Вид документа → (CHARCODE шаблону, SDOCTYPE, назва, поля назви та одиниці рядка)
MEDOC_PRIMARY_DOCS = {
    'act': ('AKT_pdv', '10104', 'Акт на загальних підставах з ПДВ',
            'TAB1_SPR1_NAME', 'TAB1_SPR2_NAME'),
    'invoice': ('RAH_pdv', '10103', 'Рахунок-фактура на загальних підставах з ПДВ',
                'TAB1_A1', 'TAB1_A2'),
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _medoc_bank_rows(self, card, partner, names):
        """names — (назва банку, МФО, рахунок) у термінах шаблону M.E.Doc."""
        bank = partner.bank_ids[:1]
        if not bank:
            return
        iban = (bank.acc_number or '').replace(' ', '')
        card.add(names[0], bank.bank_id.name)
        # МФО — позиції 5-10 українського IBAN
        if iban.upper().startswith('UA') and len(iban) == 29:
            card.add(names[1], iban[4:10])
        card.add(names[2], iban)

    def _medoc_primary_card(self, doc_kind):
        """Картка акту (``act``) чи рахунку-фактури (``invoice``) з ПДВ."""
        self.ensure_one()
        if self.move_type != 'out_invoice':
            raise UserError(_(
                'У M.E.Doc вивантажуються лише рахунки клієнтам; '
                '%(name)s до них не належить.', name=self.display_name))
        if self.state != 'posted':
            raise UserError(_(
                'У M.E.Doc вивантажуються лише проведені рахунки; '
                'проведіть %(name)s.', name=self.display_name))
        company = self.company_id
        code = medoc_company_code(company)
        if not code:
            raise UserError(_(
                'Заповніть ЄДРПОУ у налаштуваннях компанії %(company)s.',
                company=company.display_name))
        charcode, sdoctype, docname, name_field, uom_field = (
            MEDOC_PRIMARY_DOCS[doc_kind])
        doc_date = self.invoice_date or self.date
        card = MedocCard([
            ('DOCID', medoc_docid(self)),
            ('DOCNAME', docname),
            ('CHARCODE', charcode),
            ('PARTCODE', '7'),
            ('NOTATION', ''),
            ('SDOCTYPE', sdoctype),
        ], primary=True)

        firm = company.partner_id
        firm_address = company.legal_address or firm._display_address(
            without_company=True).replace('\n', ', ')
        card.add('DOCDATE', fmt_date(doc_date) + ' 00:00:00')
        card.add('NUM', self.name if self.name != '/' else '')
        card.add('DOCSUM', fmt_number(self.amount_total))
        if self.currency_id.name == 'UAH':
            card.add('DOCSUM_TEXT', amount_to_words_ua(self.amount_total))
        card.add('SUMWITHOUTPDV', fmt_number(self.amount_untaxed))
        card.add('SUMPDV', fmt_number(self.amount_tax))
        card.add('FIRM_EDRPOU', code)
        card.add('FIRM_INN', company.l10n_ua_vat_ipn or firm.ipn)
        card.add('FIRM_NAME', company.name)
        card.add('FIRM_NM', company.name)
        card.add('FIRM_ADR', firm_address)
        card.add('FIRM_TELORG', company.phone)
        card.add('FIRM_EMAILORG', company.email)
        self._medoc_bank_rows(card, firm, ('FIRM_NMBANK', 'FIRM_CBANK', 'FIRM_RS'))

        side = self.commercial_partner_id
        side_address = side.l10n_ua_legal_address or side._display_address(
            without_company=True).replace('\n', ', ')
        card.add('SIDE_CD_K', side.name)
        card.add('SIDE_SHORTNAME_K', side.name)
        card.add('SIDE_EDRPOU_K', side.edrpou or side.ipn)
        card.add('SIDE_CDINDTAXNUM_K', side.ipn)
        card.add('SIDE_CDADR_K', side_address)
        card.add('SIDE_TEL_K', side.phone)
        self._medoc_bank_rows(
            card, side, ('SIDE_BANK_K', 'SIDE_MFO_K', 'SIDE_CDSHR_K'))

        lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note'))
        for idx, line in enumerate(lines):
            quantity = line.quantity
            card.add(name_field, line.name or line.product_id.display_name,
                     tab=1, line=idx)
            card.add(uom_field, line.product_uom_id.name, tab=1, line=idx)
            card.add('TAB1_A3', fmt_number(quantity, 6), tab=1, line=idx)
            # Ціна без ПДВ і з урахуванням знижки, щоб кількість × ціна = сума
            card.add('TAB1_A4', fmt_number(
                line.price_subtotal / quantity if quantity else 0.0, 6),
                tab=1, line=idx)
            card.add('TAB1_A5', fmt_number(line.price_subtotal), tab=1, line=idx)
        return card
