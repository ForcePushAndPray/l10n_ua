"""Договір у взаємозаліку (#371).

Договір на проводці (`account.move.agreement_id`) один на весь документ, а
рядок проводки успадковує його через related-поле. Тож залік між різними
договорами однією проводкою в розрізі договорів не розкладеш: договір
проставляється на проводку заліку, лише коли він однозначний — вказаний у
документі або спільний для всіх обраних рахунків.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class L10nUaDebtNetting(models.Model):
    _inherit = 'l10n_ua.debt.netting'

    agreement_id = fields.Many2one(
        'agreement',
        string='Договір',
        tracking=True,
        domain="[('partner_id', 'child_of', commercial_partner_id)]",
        help='Обмежити залік документами одного договору. Договір '
             'проставляється на проводку заліку, тож потрапляє в ОСВ і акт '
             'звірки в розрізі договорів.',
    )

    def _get_candidate_domain(self):
        domain = super()._get_candidate_domain()
        if self.agreement_id:
            domain.append(('agreement_id', '=', self.agreement_id.id))
        return domain

    def _get_move_agreement(self):
        """Договір для проводки заліку: явний або єдиний серед документів."""
        self.ensure_one()
        if self.agreement_id:
            return self.agreement_id
        lines = self.line_ids.filtered(
            lambda l: not self.currency_id.is_zero(l.amount_offset))
        agreements = lines.move_line_id.agreement_id
        if len(agreements) == 1 and all(ml.agreement_id for ml in lines.move_line_id):
            return agreements
        return self.env['agreement']

    @api.constrains('agreement_id')
    def _check_lines_agreement(self):
        self.line_ids._check_agreement()

    def _prepare_move_vals(self, prepared):
        vals = super()._prepare_move_vals(prepared)
        agreement = self._get_move_agreement()
        if agreement:
            vals['agreement_id'] = agreement.id
        return vals


class L10nUaDebtNettingLine(models.Model):
    _inherit = 'l10n_ua.debt.netting.line'

    agreement_id = fields.Many2one(
        related='move_line_id.agreement_id', string='Договір')

    @api.constrains('move_line_id')
    def _check_agreement(self):
        for line in self:
            agreement = line.netting_id.agreement_id
            if agreement and line.move_line_id.agreement_id != agreement:
                raise ValidationError(
                    'Документ %s не належить до договору %s.'
                    % (line.move_id.display_name, agreement.display_name))
