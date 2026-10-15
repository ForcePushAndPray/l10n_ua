"""Майстер експорту документів у файл обміну M.E.Doc."""
import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.l10n_ua_tax_invoice import medoc_company_code
from ..tools.medoc_xml import build_zvit


class L10nUaMedocExport(models.TransientModel):
    _name = 'l10n_ua.medoc.export'
    _description = 'Експорт у M.E.Doc (XML)'

    doc_kind = fields.Selection(
        selection=[
            ('pn', 'Податкова накладна / розрахунок коригування'),
            ('act', 'Акт (з ПДВ)'),
            ('invoice', 'Рахунок-фактура (з ПДВ)'),
        ],
        string='Вид документа',
        required=True,
    )
    tax_invoice_ids = fields.Many2many(
        'l10n_ua.tax.invoice', string='Податкові накладні')
    move_ids = fields.Many2many('account.move', string='Рахунки')
    file_data = fields.Binary(string='Файл', readonly=True)
    file_name = fields.Char(string='Назва файлу', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        active_model = self.env.context.get('active_model')
        if active_model == 'l10n_ua.tax.invoice':
            res.update(doc_kind='pn', tax_invoice_ids=[(6, 0, active_ids)])
        elif active_model == 'account.move':
            res.update(doc_kind=res.get('doc_kind') or 'act',
                       move_ids=[(6, 0, active_ids)])
        return res

    def _medoc_cards(self):
        self.ensure_one()
        if self.doc_kind == 'pn':
            records = self.tax_invoice_ids
            cards = [rec._medoc_card() for rec in records]
        else:
            records = self.move_ids
            cards = [rec._medoc_primary_card(self.doc_kind) for rec in records]
        if not records:
            raise UserError(_('Не вибрано жодного документа для експорту.'))
        if len(records.company_id) > 1:
            raise UserError(_(
                'Файл M.E.Doc містить документи однієї організації — '
                'виберіть документи однієї компанії.'))
        return records.company_id, cards

    def action_export(self):
        self.ensure_one()
        company, cards = self._medoc_cards()
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        content = build_zvit(medoc_company_code(company), cards, now.date())
        self.write({
            'file_data': base64.b64encode(content),
            'file_name': 'medoc_%s_%s.xml' % (
                self.doc_kind, now.strftime('%Y%m%d_%H%M%S')),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
