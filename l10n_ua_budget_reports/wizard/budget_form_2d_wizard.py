"""Wizard for generating Form 2д report — execution of general fund."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


PERIOD_SELECTION = [
    ('q1', 'I квартал'),
    ('q2', 'II квартал'),
    ('q3', 'III квартал'),
    ('q4', 'IV квартал'),
    ('h1', 'I півріччя'),
    ('9m', '9 місяців'),
    ('year', 'Рік'),
]


class BudgetForm2DWizard(models.TransientModel):
    _name = 'l10n_ua.budget.form_2d.wizard'
    _description = 'Параметри звіту: Форма 2д'

    estimate_id = fields.Many2one(
        'l10n_ua.budget.estimate', string='Кошторис', required=True,
        domain="[('state', 'in', ('approved', 'executed', 'closed'))]")
    period = fields.Selection(
        PERIOD_SELECTION, string='Звітний період', default='year', required=True)
    date_from = fields.Date(
        string='Дата з', compute='_compute_dates', store=True, readonly=False)
    date_to = fields.Date(
        string='Дата до', compute='_compute_dates', store=True, readonly=False)

    @api.depends('estimate_id', 'period')
    def _compute_dates(self):
        for w in self:
            if not w.estimate_id:
                w.date_from = w.date_to = False
                continue
            year = w.estimate_id.year
            mapping = {
                'q1': (f'{year}-01-01', f'{year}-03-31'),
                'q2': (f'{year}-04-01', f'{year}-06-30'),
                'q3': (f'{year}-07-01', f'{year}-09-30'),
                'q4': (f'{year}-10-01', f'{year}-12-31'),
                'h1': (f'{year}-01-01', f'{year}-06-30'),
                '9m': (f'{year}-01-01', f'{year}-09-30'),
                'year': (f'{year}-01-01', f'{year}-12-31'),
            }
            df, dt = mapping.get(w.period, mapping['year'])
            w.date_from = fields.Date.from_string(df)
            w.date_to = fields.Date.from_string(dt)

    def action_print(self):
        self.ensure_one()
        if not self.estimate_id:
            raise UserError(_('Виберіть кошторис.'))
        data = {
            'estimate_id': self.estimate_id.id,
            'period': self.period,
            'period_label': dict(self._fields['period'].selection).get(self.period),
            'date_from': fields.Date.to_string(self.date_from),
            'date_to': fields.Date.to_string(self.date_to),
        }
        report = self.env.ref('l10n_ua_budget_reports.action_report_budget_form_2d')
        return report.report_action(self.estimate_id, data=data)

    def get_report_data(self):
        """Return computed lines for the QWeb template.

        Each line: dict(kekv_code, kekv_name, plan, actual, variance, variance_pct).
        Only general fund lines.
        """
        self.ensure_one()
        out = []
        general = self.estimate_id.line_ids.filtered(
            lambda l: l.fund_type == 'general')

        # Compute period-specific actual from account.move.line
        AML = self.env['account.move.line']
        for line in general:
            domain = [
                ('parent_state', '=', 'posted'),
                ('company_id', '=', self.estimate_id.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('ua_kekv_id', '=', line.kekv_id.id),
                ('ua_fund_type', '=', 'general'),
            ]
            if line.kpkvk_id:
                domain.append(('ua_kpkvk_id', '=', line.kpkvk_id.id))
            [(debit,)] = AML._read_group(domain, [], ['debit:sum'])
            actual = debit or 0.0
            plan = line.amount_planned
            variance = plan - actual
            out.append({
                'kekv_code': line.kekv_code,
                'kekv_name': line.kekv_id.name,
                'plan': plan,
                'actual': actual,
                'variance': variance,
                'variance_pct': (actual / plan * 100.0) if plan else 0.0,
            })
        return out
