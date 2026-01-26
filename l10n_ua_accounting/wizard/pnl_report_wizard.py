"""Ukrainian Profit & Loss Statement (Звіт про фінансові результати, Форма №2) wizard."""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PnLReportWizard(models.TransientModel):
    """Wizard for generating Ukrainian P&L Statement (Form №2).

    Звіт про фінансові результати (Звіт про сукупний дохід) - форма №2.
    Shows income, expenses and profit/loss for a period.
    """
    _name = 'l10n_ua.pnl.report.wizard'
    _description = 'P&L Report Wizard (Form №2)'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.context_today,
    )
    comparison_date_from = fields.Date(
        string='Comparison Period Start',
        help='Start date for comparison period (typically same period of previous year)',
    )
    comparison_date_to = fields.Date(
        string='Comparison Period End',
        help='End date for comparison period',
    )

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        """Set comparison period to same period of previous year."""
        if self.date_from and self.date_to:
            from dateutil.relativedelta import relativedelta
            self.comparison_date_from = self.date_from - relativedelta(years=1)
            self.comparison_date_to = self.date_to - relativedelta(years=1)

    def action_print(self):
        """Generate and print P&L report."""
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before or equal to Date To.'))

        return self.env.ref(
            'l10n_ua_accounting.action_report_pnl'
        ).report_action(self)

    def action_export_xlsx(self):
        """Export P&L to XLSX format."""
        self.ensure_one()
        # TODO: Implement XLSX export
        raise UserError(_('XLSX export is not yet implemented.'))

    def _get_account_turnover(self, account_codes, date_from, date_to, turnover_type='credit'):
        """Get turnover for accounts matching codes for a period.

        Args:
            account_codes: List of account code prefixes
            date_from: Period start date
            date_to: Period end date
            turnover_type: 'debit', 'credit', or 'net' (credit - debit)

        Returns:
            float: Sum of turnovers
        """
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ]

        # Build account code domain
        account_domain = []
        for code in account_codes:
            if account_domain:
                account_domain = ['|'] + account_domain
            account_domain.append(('account_id.code', '=like', f'{code}%'))

        if account_domain:
            domain.extend(account_domain)

        lines = self.env['account.move.line'].search(domain)

        if turnover_type == 'debit':
            return sum(lines.mapped('debit'))
        elif turnover_type == 'credit':
            return sum(lines.mapped('credit'))
        else:  # net
            return sum(lines.mapped('credit')) - sum(lines.mapped('debit'))

    def _get_report_data(self):
        """Get data for P&L report.

        Ukrainian P&L structure (simplified):
        - Чистий дохід від реалізації (Net revenue) - account 70
        - Собівартість реалізації (Cost of sales) - account 90
        - Валовий прибуток (Gross profit)
        - Інші операційні доходи (Other operating income) - account 71
        - Адміністративні витрати (Administrative expenses) - account 92
        - Витрати на збут (Selling expenses) - account 93
        - Інші операційні витрати (Other operating expenses) - account 94
        - Фінансовий результат від операційної діяльності (Operating profit)
        - Фінансові доходи/витрати (Financial income/expenses) - accounts 72, 73, 95, 96
        - Прибуток до оподаткування (Profit before tax)
        - Витрати з податку на прибуток (Income tax expense) - account 98
        - Чистий прибуток (Net profit)
        """
        self.ensure_one()

        date_from = self.date_from
        date_to = self.date_to
        comp_from = self.comparison_date_from
        comp_to = self.comparison_date_to

        def get_current(codes, turnover_type='credit'):
            return self._get_account_turnover(codes, date_from, date_to, turnover_type)

        def get_comparison(codes, turnover_type='credit'):
            if comp_from and comp_to:
                return self._get_account_turnover(codes, comp_from, comp_to, turnover_type)
            return 0.0

        # Income and expenses
        data = {
            'net_revenue': {
                'name': 'Чистий дохід від реалізації продукції (товарів, робіт, послуг)',
                'code': '2000',
                'current': get_current(['70']),
                'previous': get_comparison(['70']),
            },
            'cost_of_sales': {
                'name': 'Собівартість реалізованої продукції (товарів, робіт, послуг)',
                'code': '2050',
                'current': get_current(['90'], 'debit'),
                'previous': get_comparison(['90'], 'debit'),
            },
            'other_operating_income': {
                'name': 'Інші операційні доходи',
                'code': '2120',
                'current': get_current(['71']),
                'previous': get_comparison(['71']),
            },
            'administrative_expenses': {
                'name': 'Адміністративні витрати',
                'code': '2130',
                'current': get_current(['92'], 'debit'),
                'previous': get_comparison(['92'], 'debit'),
            },
            'selling_expenses': {
                'name': 'Витрати на збут',
                'code': '2150',
                'current': get_current(['93'], 'debit'),
                'previous': get_comparison(['93'], 'debit'),
            },
            'other_operating_expenses': {
                'name': 'Інші операційні витрати',
                'code': '2180',
                'current': get_current(['94'], 'debit'),
                'previous': get_comparison(['94'], 'debit'),
            },
            'financial_income': {
                'name': 'Фінансові доходи',
                'code': '2220',
                'current': get_current(['72', '73']),
                'previous': get_comparison(['72', '73']),
            },
            'financial_expenses': {
                'name': 'Фінансові витрати',
                'code': '2250',
                'current': get_current(['95', '96'], 'debit'),
                'previous': get_comparison(['95', '96'], 'debit'),
            },
            'other_income': {
                'name': 'Інші доходи',
                'code': '2240',
                'current': get_current(['74']),
                'previous': get_comparison(['74']),
            },
            'other_expenses': {
                'name': 'Інші витрати',
                'code': '2270',
                'current': get_current(['97'], 'debit'),
                'previous': get_comparison(['97'], 'debit'),
            },
            'income_tax_expense': {
                'name': 'Витрати (дохід) з податку на прибуток',
                'code': '2300',
                'current': get_current(['98'], 'debit'),
                'previous': get_comparison(['98'], 'debit'),
            },
        }

        # Calculate computed lines
        gross_profit_current = data['net_revenue']['current'] - data['cost_of_sales']['current']
        gross_profit_previous = data['net_revenue']['previous'] - data['cost_of_sales']['previous']

        operating_profit_current = (
            gross_profit_current
            + data['other_operating_income']['current']
            - data['administrative_expenses']['current']
            - data['selling_expenses']['current']
            - data['other_operating_expenses']['current']
        )
        operating_profit_previous = (
            gross_profit_previous
            + data['other_operating_income']['previous']
            - data['administrative_expenses']['previous']
            - data['selling_expenses']['previous']
            - data['other_operating_expenses']['previous']
        )

        profit_before_tax_current = (
            operating_profit_current
            + data['financial_income']['current']
            - data['financial_expenses']['current']
            + data['other_income']['current']
            - data['other_expenses']['current']
        )
        profit_before_tax_previous = (
            operating_profit_previous
            + data['financial_income']['previous']
            - data['financial_expenses']['previous']
            + data['other_income']['previous']
            - data['other_expenses']['previous']
        )

        net_profit_current = profit_before_tax_current - data['income_tax_expense']['current']
        net_profit_previous = profit_before_tax_previous - data['income_tax_expense']['previous']

        data['gross_profit'] = {
            'name': 'Валовий прибуток (збиток)',
            'code': '2090',
            'current': gross_profit_current,
            'previous': gross_profit_previous,
        }
        data['operating_profit'] = {
            'name': 'Фінансовий результат від операційної діяльності',
            'code': '2190',
            'current': operating_profit_current,
            'previous': operating_profit_previous,
        }
        data['profit_before_tax'] = {
            'name': 'Фінансовий результат до оподаткування',
            'code': '2290',
            'current': profit_before_tax_current,
            'previous': profit_before_tax_previous,
        }
        data['net_profit'] = {
            'name': 'Чистий фінансовий результат',
            'code': '2350',
            'current': net_profit_current,
            'previous': net_profit_previous,
        }

        return {
            'lines': data,
            'date_from': date_from,
            'date_to': date_to,
            'comp_from': comp_from,
            'comp_to': comp_to,
        }
