"""Ukrainian Balance Sheet (Баланс, Форма №1) wizard."""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BalanceReportWizard(models.TransientModel):
    """Wizard for generating Ukrainian Balance Sheet (Form №1).

    Баланс (Звіт про фінансовий стан) - форма №1 фінансової звітності.
    Shows assets, liabilities and equity at a specific date.
    """
    _name = 'l10n_ua.balance.report.wizard'
    _description = 'Balance Sheet Wizard (Form №1)'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string='Period Start',
        required=True,
        help='Start of reporting period (for comparison)',
    )
    date_to = fields.Date(
        string='Report Date',
        required=True,
        default=fields.Date.context_today,
        help='Balance sheet date (end of period)',
    )
    comparison_date = fields.Date(
        string='Comparison Date',
        help='Date for comparison column (typically end of previous year)',
    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """Set comparison date to end of previous year."""
        if self.date_from:
            # Previous year end
            prev_year = self.date_from.year - 1
            self.comparison_date = fields.Date.from_string(f'{prev_year}-12-31')

    def action_print(self):
        """Generate and print Balance Sheet report."""
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_('Period Start must be before or equal to Report Date.'))

        return self.env.ref(
            'l10n_ua_accounting.action_report_balance_sheet'
        ).report_action(self)

    def action_export_xlsx(self):
        """Export Balance Sheet to XLSX format."""
        self.ensure_one()
        # TODO: Implement XLSX export
        raise UserError(_('XLSX export is not yet implemented.'))

    def _get_account_balance(self, account_codes, date, balance_type='balance'):
        """Get balance for accounts matching codes at specific date.

        Args:
            account_codes: List of account code prefixes (e.g., ['10', '11'])
            date: Date for balance calculation
            balance_type: 'debit', 'credit', or 'balance'

        Returns:
            float: Sum of balances
        """
        domain = [
            ('date', '<=', date),
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

        if balance_type == 'debit':
            return sum(lines.mapped('debit'))
        elif balance_type == 'credit':
            return sum(lines.mapped('credit'))
        else:
            return sum(lines.mapped('balance'))

    def _get_report_data(self):
        """Get data for Balance Sheet report.

        Ukrainian Balance Sheet structure:
        I. Необоротні активи (Non-current assets) - accounts 10-19
        II. Оборотні активи (Current assets) - accounts 20-39
        III. Необоротні активи для продажу (Non-current assets held for sale) - account 286
        I. Власний капітал (Equity) - accounts 40-49
        II. Довгострокові зобов'язання (Non-current liabilities) - accounts 50-59
        III. Поточні зобов'язання (Current liabilities) - accounts 60-69
        IV. Зобов'язання пов'язані з необоротними активами (Liabilities for assets held for sale)
        """
        self.ensure_one()

        date_end = self.date_to
        date_comp = self.comparison_date or fields.Date.from_string(
            f'{self.date_to.year - 1}-12-31'
        )

        # Assets (Активи)
        assets = {
            # I. Необоротні активи
            'intangible_assets': {
                'name': 'Нематеріальні активи',
                'code': '1000',
                'current': abs(self._get_account_balance(['12'], date_end)),
                'previous': abs(self._get_account_balance(['12'], date_comp)),
            },
            'unfinished_capex': {
                'name': 'Незавершені капітальні інвестиції',
                'code': '1005',
                'current': abs(self._get_account_balance(['15'], date_end)),
                'previous': abs(self._get_account_balance(['15'], date_comp)),
            },
            'fixed_assets': {
                'name': 'Основні засоби',
                'code': '1010',
                'current': abs(self._get_account_balance(['10', '11'], date_end)),
                'previous': abs(self._get_account_balance(['10', '11'], date_comp)),
            },
            'investment_property': {
                'name': 'Інвестиційна нерухомість',
                'code': '1015',
                'current': abs(self._get_account_balance(['100'], date_end)),  # subset
                'previous': abs(self._get_account_balance(['100'], date_comp)),
            },
            'long_term_receivables': {
                'name': 'Довгострокова дебіторська заборгованість',
                'code': '1040',
                'current': abs(self._get_account_balance(['18'], date_end)),
                'previous': abs(self._get_account_balance(['18'], date_comp)),
            },
            'deferred_tax_assets': {
                'name': 'Відстрочені податкові активи',
                'code': '1045',
                'current': abs(self._get_account_balance(['17'], date_end)),
                'previous': abs(self._get_account_balance(['17'], date_comp)),
            },

            # II. Оборотні активи
            'inventories': {
                'name': 'Запаси',
                'code': '1100',
                'current': abs(self._get_account_balance(['20', '21', '22', '23', '24', '25', '26', '27', '28'], date_end)),
                'previous': abs(self._get_account_balance(['20', '21', '22', '23', '24', '25', '26', '27', '28'], date_comp)),
            },
            'receivables_goods': {
                'name': 'Дебіторська заборгованість за товари',
                'code': '1125',
                'current': abs(self._get_account_balance(['36'], date_end)),
                'previous': abs(self._get_account_balance(['36'], date_comp)),
            },
            'receivables_budget': {
                'name': 'Дебіторська заборгованість за розрахунками з бюджетом',
                'code': '1135',
                'current': abs(self._get_account_balance(['641', '642'], date_end)),
                'previous': abs(self._get_account_balance(['641', '642'], date_comp)),
            },
            'other_current_receivables': {
                'name': 'Інша поточна дебіторська заборгованість',
                'code': '1155',
                'current': abs(self._get_account_balance(['37', '63'], date_end)),
                'previous': abs(self._get_account_balance(['37', '63'], date_comp)),
            },
            'cash': {
                'name': 'Гроші та їх еквіваленти',
                'code': '1165',
                'current': abs(self._get_account_balance(['30', '31', '33', '35'], date_end)),
                'previous': abs(self._get_account_balance(['30', '31', '33', '35'], date_comp)),
            },
            'prepaid_expenses': {
                'name': 'Витрати майбутніх періодів',
                'code': '1170',
                'current': abs(self._get_account_balance(['39'], date_end)),
                'previous': abs(self._get_account_balance(['39'], date_comp)),
            },
        }

        # Liabilities & Equity (Пасиви)
        liabilities = {
            # I. Власний капітал
            'registered_capital': {
                'name': 'Зареєстрований капітал',
                'code': '1400',
                'current': abs(self._get_account_balance(['40'], date_end)),
                'previous': abs(self._get_account_balance(['40'], date_comp)),
            },
            'additional_capital': {
                'name': 'Додатковий капітал',
                'code': '1410',
                'current': abs(self._get_account_balance(['41', '42'], date_end)),
                'previous': abs(self._get_account_balance(['41', '42'], date_comp)),
            },
            'reserve_capital': {
                'name': 'Резервний капітал',
                'code': '1415',
                'current': abs(self._get_account_balance(['43'], date_end)),
                'previous': abs(self._get_account_balance(['43'], date_comp)),
            },
            'retained_earnings': {
                'name': 'Нерозподілений прибуток (непокритий збиток)',
                'code': '1420',
                'current': self._get_account_balance(['44'], date_end),
                'previous': self._get_account_balance(['44'], date_comp),
            },

            # II. Довгострокові зобов'язання
            'long_term_loans': {
                'name': 'Довгострокові кредити банків',
                'code': '1510',
                'current': abs(self._get_account_balance(['50'], date_end)),
                'previous': abs(self._get_account_balance(['50'], date_comp)),
            },
            'long_term_liabilities': {
                'name': "Інші довгострокові зобов'язання",
                'code': '1515',
                'current': abs(self._get_account_balance(['51', '52', '53', '54', '55'], date_end)),
                'previous': abs(self._get_account_balance(['51', '52', '53', '54', '55'], date_comp)),
            },

            # III. Поточні зобов'язання
            'short_term_loans': {
                'name': 'Короткострокові кредити банків',
                'code': '1600',
                'current': abs(self._get_account_balance(['60'], date_end)),
                'previous': abs(self._get_account_balance(['60'], date_comp)),
            },
            'payables_goods': {
                'name': 'Кредиторська заборгованість за товари',
                'code': '1615',
                'current': abs(self._get_account_balance(['63'], date_end)),
                'previous': abs(self._get_account_balance(['63'], date_comp)),
            },
            'payables_budget': {
                'name': "Поточні зобов'язання за розрахунками з бюджетом",
                'code': '1620',
                'current': abs(self._get_account_balance(['641', '642'], date_end)),
                'previous': abs(self._get_account_balance(['641', '642'], date_comp)),
            },
            'payables_insurance': {
                'name': "Поточні зобов'язання зі страхування",
                'code': '1625',
                'current': abs(self._get_account_balance(['65'], date_end)),
                'previous': abs(self._get_account_balance(['65'], date_comp)),
            },
            'payables_wages': {
                'name': "Поточні зобов'язання з оплати праці",
                'code': '1630',
                'current': abs(self._get_account_balance(['66'], date_end)),
                'previous': abs(self._get_account_balance(['66'], date_comp)),
            },
            'other_current_liabilities': {
                'name': "Інші поточні зобов'язання",
                'code': '1690',
                'current': abs(self._get_account_balance(['67', '68', '69'], date_end)),
                'previous': abs(self._get_account_balance(['67', '68', '69'], date_comp)),
            },
        }

        # Calculate totals
        total_non_current_assets = sum(
            v['current'] for k, v in assets.items()
            if k in ['intangible_assets', 'unfinished_capex', 'fixed_assets',
                     'investment_property', 'long_term_receivables', 'deferred_tax_assets']
        )
        total_current_assets = sum(
            v['current'] for k, v in assets.items()
            if k in ['inventories', 'receivables_goods', 'receivables_budget',
                     'other_current_receivables', 'cash', 'prepaid_expenses']
        )
        total_assets = total_non_current_assets + total_current_assets

        total_equity = sum(
            v['current'] for k, v in liabilities.items()
            if k in ['registered_capital', 'additional_capital', 'reserve_capital', 'retained_earnings']
        )
        total_long_term_liabilities = sum(
            v['current'] for k, v in liabilities.items()
            if k in ['long_term_loans', 'long_term_liabilities']
        )
        total_current_liabilities = sum(
            v['current'] for k, v in liabilities.items()
            if k in ['short_term_loans', 'payables_goods', 'payables_budget',
                     'payables_insurance', 'payables_wages', 'other_current_liabilities']
        )
        total_liabilities = total_equity + total_long_term_liabilities + total_current_liabilities

        return {
            'assets': assets,
            'liabilities': liabilities,
            'totals': {
                'non_current_assets': total_non_current_assets,
                'current_assets': total_current_assets,
                'total_assets': total_assets,
                'equity': total_equity,
                'long_term_liabilities': total_long_term_liabilities,
                'current_liabilities': total_current_liabilities,
                'total_liabilities': total_liabilities,
            },
            'date_end': self.date_to,
            'date_comp': date_comp,
        }
