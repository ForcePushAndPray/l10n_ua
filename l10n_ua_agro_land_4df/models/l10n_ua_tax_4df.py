from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Код ознаки доходу «доходи від надання в оренду земельної ділянки
# сільськогосподарського призначення, земельної частки (паю)…»
RENT_INCOME_CODE = '106'


class L10nUaTax4DF(models.Model):
    _inherit = 'l10n_ua.tax.4df'

    @api.depends('line_4df_ids.partner_id')
    def _compute_totals(self):
        super()._compute_totals()
        for rec in self:
            partners = rec.line_4df_ids.filtered(lambda l: not l.employee_id).partner_id
            rec.total_employees += len(partners)

    def _generate_appendix_4df(self):
        super()._generate_appendix_4df()
        self._generate_appendix_4df_land_rent()

    def _generate_appendix_4df_land_rent(self):
        """Орендна плата фізособам за квартал: нараховано й утримано — з
        проведених нарахувань, виплачено — з проведених виплат (у сумі доходу
        до утримання, пропорційно виплаченій сумі «на руки»)."""
        self.ensure_one()
        date_from, date_to = self._get_quarter_dates()
        company = self.company_id
        accrual_lines = self.env['l10n_ua.agro.rent.accrual.line'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('pdfo_amount', '!=', 0),
        ])
        payment_lines = self.env['l10n_ua.agro.rent.payment.line'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('accrual_line_id.pdfo_amount', '!=', 0),
        ])
        by_lessor = defaultdict(lambda: {'accrued': 0.0, 'paid': 0.0, 'pdfo': 0.0, 'military': 0.0})
        for line in accrual_lines:
            data = by_lessor[line.lessor_id]
            data['accrued'] += line.amount
            data['pdfo'] += line.pdfo_amount
            data['military'] += line.military_amount
        for line in payment_lines:
            accrual_line = line.accrual_line_id
            if accrual_line.net_amount:
                by_lessor[line.lessor_id]['paid'] += company.currency_id.round(
                    accrual_line.amount * line.amount / accrual_line.net_amount)
        if not by_lessor:
            return
        missing = [partner.name for partner in by_lessor if not partner.ipn]
        if missing:
            raise UserError(self.env._(
                'Fill in the RNOKPP of the lessors to include their land rent in 4DF: %s.',
                ', '.join(sorted(missing))))
        self.env['l10n_ua.tax.4df.line.4df'].create([{
            'report_id': self.id,
            'partner_id': partner.id,
            'rnokpp': partner.ipn,
            'income_type': RENT_INCOME_CODE,
            'income_sign': '0' if data['paid'] else '1',
            'accrued_amount': data['accrued'],
            'paid_amount': data['paid'],
            'pdfo_amount': data['pdfo'],
            'military_amount': data['military'],
        } for partner, data in by_lessor.items()])


class L10nUaTax4DFLine4DF(models.Model):
    _inherit = 'l10n_ua.tax.4df.line.4df'

    employee_id = fields.Many2one(required=False)
    partner_id = fields.Many2one(
        'res.partner', string='Individual',
        help='Фізособа, яка не є працівником (орендодавець паю).')

    @api.constrains('employee_id', 'partner_id')
    def _check_person(self):
        for line in self:
            if not line.employee_id and not line.partner_id:
                raise ValidationError(self.env._(
                    'A 4DF line must belong to an employee or an individual.'))
