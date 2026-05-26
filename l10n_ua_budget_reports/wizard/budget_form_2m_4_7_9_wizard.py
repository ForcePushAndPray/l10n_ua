"""Universal wizard for budget reports 2м, 4-1д, 4-2д, 7д, 9д.

Шаблон single QWeb-template з умовним рендерингом дізнається тип за полем
`form_kind`. Логіка агрегації:
* 2м, 4-1д, 4-2д: фільтр по фонду + рік + опційний КПКВК
* 7д: заборгованість по `account.move.line` зі станом 'posted' і
  залишком (debit - credit) > 0
* 9д: дебіторська заборгованість на `asset_receivable` рахунках
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


FORM_KIND = [
    ('2m', 'Форма 2м (загальний фонд місцевого бюджету)'),
    ('4_1d', 'Форма 4-1д (спеціальний фонд)'),
    ('4_2d', 'Форма 4-2д (інші надходження)'),
    ('7d', 'Форма 7д (заборгованість за бюджетними коштами)'),
    ('9d', 'Форма 9д (дебіторська заборгованість)'),
]


PERIOD_SELECTION = [
    ('q1', 'I квартал'),
    ('q2', 'II квартал'),
    ('q3', 'III квартал'),
    ('q4', 'IV квартал'),
    ('h1', 'I півріччя'),
    ('9m', '9 місяців'),
    ('year', 'Рік'),
]


class BudgetMultiFormWizard(models.TransientModel):
    _name = 'l10n_ua.budget.multi_form.wizard'
    _description = 'Параметри: 2м / 4-1д / 4-2д / 7д / 9д'

    form_kind = fields.Selection(FORM_KIND, required=True, default='4_1d')
    estimate_id = fields.Many2one(
        'l10n_ua.budget.estimate', string='Кошторис', required=True,
        domain="[('state', 'in', ('approved', 'executed', 'closed'))]")
    period = fields.Selection(PERIOD_SELECTION, default='year', required=True)
    date_from = fields.Date(compute='_compute_dates', store=True, readonly=False)
    date_to = fields.Date(compute='_compute_dates', store=True, readonly=False)

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
            'form_kind': self.form_kind,
            'form_label': dict(self._fields['form_kind'].selection).get(self.form_kind),
            'period_label': dict(self._fields['period'].selection).get(self.period),
            'date_from': fields.Date.to_string(self.date_from),
            'date_to': fields.Date.to_string(self.date_to),
        }
        report = self.env.ref('l10n_ua_budget_reports.action_report_budget_multi_form')
        return report.report_action(self.estimate_id, data=data)

    def get_report_data(self):
        """Return rows for the selected form kind."""
        self.ensure_one()
        if self.form_kind in ('2m', '4_1d', '4_2d'):
            return self._data_execution_by_fund()
        if self.form_kind == '7d':
            return self._data_payable_debt()
        if self.form_kind == '9d':
            return self._data_receivable_debt()
        return []

    def _data_execution_by_fund(self):
        """План vs факт по фонду — форми 2м, 4-1д, 4-2д."""
        fund_filter = {
            '2m': 'general',
            '4_1d': 'special',
            '4_2d': 'special',  # «інші надходження» — теж спецфонд
        }.get(self.form_kind, 'general')

        AML = self.env['account.move.line']
        out = []
        lines = self.estimate_id.line_ids.filtered(lambda l: l.fund_type == fund_filter)
        for line in lines:
            domain = [
                ('parent_state', '=', 'posted'),
                ('company_id', '=', self.estimate_id.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('ua_kekv_id', '=', line.kekv_id.id),
                ('ua_fund_type', '=', fund_filter),
            ]
            if line.kpkvk_id:
                domain.append(('ua_kpkvk_id', '=', line.kpkvk_id.id))
            agg = AML.read_group(domain, ['debit:sum', 'credit:sum'], [])
            debit = (agg[0]['debit'] if agg else 0.0) or 0.0
            credit = (agg[0]['credit'] if agg else 0.0) or 0.0
            # Для «інших надходжень» (4-2д) — показуємо кредит (надходження), для видатків — дебет
            actual = credit if self.form_kind == '4_2d' else debit
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

    def _data_payable_debt(self):
        """Форма 7д — заборгованість за бюджетними коштами.

        Підраховуємо незакриті зобов'язання на рахунках liability_payable за
        обраний період.
        """
        AML = self.env['account.move.line']
        domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.estimate_id.company_id.id),
            ('date', '<=', self.date_to),
            ('account_id.account_type', '=', 'liability_payable'),
            ('ua_fund_type', '!=', False),
        ]
        agg = AML.read_group(domain, ['debit:sum', 'credit:sum'],
                              ['ua_kekv_id', 'ua_fund_type'], lazy=False)
        out = []
        Kekv = self.env['l10n_ua.kekv']
        for row in agg:
            kekv = Kekv.browse(row['ua_kekv_id'][0]) if row.get('ua_kekv_id') else None
            if not kekv:
                continue
            balance = (row['credit'] or 0) - (row['debit'] or 0)
            if balance == 0:
                continue
            out.append({
                'kekv_code': kekv.code,
                'kekv_name': kekv.name,
                'fund': dict([('general', 'Загальний'), ('special', 'Спеціальний')])
                         .get(row['ua_fund_type'], '—'),
                'balance': balance,
            })
        return out

    def _data_receivable_debt(self):
        """Форма 9д — дебіторська заборгованість."""
        AML = self.env['account.move.line']
        domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.estimate_id.company_id.id),
            ('date', '<=', self.date_to),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('ua_fund_type', '!=', False),
        ]
        agg = AML.read_group(domain, ['debit:sum', 'credit:sum'],
                              ['ua_kekv_id', 'ua_fund_type'], lazy=False)
        out = []
        Kekv = self.env['l10n_ua.kekv']
        for row in agg:
            kekv = Kekv.browse(row['ua_kekv_id'][0]) if row.get('ua_kekv_id') else None
            if not kekv:
                continue
            balance = (row['debit'] or 0) - (row['credit'] or 0)
            if balance == 0:
                continue
            out.append({
                'kekv_code': kekv.code,
                'kekv_name': kekv.name,
                'fund': dict([('general', 'Загальний'), ('special', 'Спеціальний')])
                         .get(row['ua_fund_type'], '—'),
                'balance': balance,
            })
        return out
