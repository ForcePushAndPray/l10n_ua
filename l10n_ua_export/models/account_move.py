from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ua_customs_declaration_ids = fields.Many2many(
        'l10n_ua.customs.declaration', 'l10n_ua_customs_declaration_move_rel', 'move_id', 'declaration_id',
        string='Customs Declarations', copy=False)

    def action_view_l10n_ua_customs_declarations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.customs.declaration',
            'name': self.env._('Customs Declarations'),
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.l10n_ua_customs_declaration_ids.ids)],
            'context': {'default_invoice_ids': [(6, 0, self.ids)], 'default_partner_id': self.commercial_partner_id.id,
                        'default_agreement_id': self.l10n_ua_agreement_id.id},
        }

    def _l10n_ua_export_lines(self):
        """Рядки інвойсу для друку: опис, кількість, одиниця, ціна, сума."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
