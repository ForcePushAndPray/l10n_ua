"""Consolidated statements 1-к / 2-к of a two-company group (issue #375).

Parent P owns 80 % of subsidiary S (acquired 10.01.2025):

* P: capital 1000; investment in S 800 (141, partner S); buys goods 600
  externally; sells them to S for 1000 (361/701, partner S); external
  service 300.
* S: capital 1000 (800 from P, 200 from outsiders); buys the goods from P
  (281/631, partner P) and resells them externally for 1500.

Expected group: revenue 1800, cost of sales 600, net profit 1200 of which
NCI 100 (20 % × S's 500); balance 3000 with NCI 300 (20 % × S's equity 1500).
"""

from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'l10n_ua_consolidation')
class TestConsolidation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ua = cls.env.ref('base.ua')
        uah = cls.env.ref('base.UAH')
        uah.active = True
        Company = cls.env['res.company']
        cls.parent = Company.create({'name': 'Холдинг П (тест)', 'currency_id': uah.id, 'country_id': ua.id})
        cls.sub = Company.create({'name': 'Дочірнє С (тест)', 'currency_id': uah.id, 'country_id': ua.id})
        cls.env.user.company_ids |= cls.parent | cls.sub
        cls.customer = cls.env['res.partner'].create({'name': 'Зовнішній покупець'})
        cls.supplier = cls.env['res.partner'].create({'name': 'Зовнішній постачальник'})
        cls.outsider = cls.env['res.partner'].create({'name': 'Міноритарний учасник'})

        cls.acc = {}
        for company in (cls.parent, cls.sub):
            for code, name, account_type in (
                ('141', 'Інвестиції пов’язаним сторонам', 'asset_non_current'),
                ('281', 'Товари на складі', 'asset_current'),
                ('311', 'Поточні рахунки в нац. валюті', 'asset_cash'),
                ('361', 'Розрахунки з вітчизняними покупцями', 'asset_receivable'),
                ('401', 'Статутний капітал', 'equity'),
                ('631', 'Розрахунки з вітчизняними постачальниками', 'liability_payable'),
                ('701', 'Дохід від реалізації', 'income'),
                ('902', 'Собівартість реалізованих товарів', 'expense_direct_cost'),
            ):
                cls.acc[(company, code)] = cls.env['account.account'].with_company(company).create({
                    'code': code,
                    'name': name,
                    'account_type': account_type,
                    'company_ids': [(6, 0, company.ids)],
                    'reconcile': account_type in ('asset_receivable', 'liability_payable'),
                })
        cls.journal = {
            company: cls.env['account.journal'].with_company(company).create({
                'name': 'Різне (консолідація)', 'code': 'CNS', 'type': 'general',
                'company_id': company.id,
            })
            for company in (cls.parent, cls.sub)
        }

        P, S = cls.parent, cls.sub
        p_partner, s_partner = P.partner_id, S.partner_id
        # Capital and investment
        cls._post(P, date(2025, 1, 5), [('311', 1000, 0, None), ('401', 0, 1000, None)])
        cls._post(P, date(2025, 1, 10), [('141', 800, 0, s_partner), ('311', 0, 800, s_partner)])
        cls._post(S, date(2025, 1, 10), [('311', 1000, 0, None),
                                          ('401', 0, 800, p_partner), ('401', 0, 200, cls.outsider)])
        # Parent buys goods and sells them to the subsidiary
        cls._post(P, date(2025, 2, 1), [('281', 600, 0, cls.supplier), ('631', 0, 600, cls.supplier)])
        cls._post(P, date(2025, 3, 1), [('361', 1000, 0, s_partner), ('701', 0, 1000, s_partner)])
        cls._post(P, date(2025, 3, 1), [('902', 600, 0, None), ('281', 0, 600, None)])
        cls._post(S, date(2025, 3, 1), [('281', 1000, 0, p_partner), ('631', 0, 1000, p_partner)])
        # External sales
        cls._post(P, date(2025, 4, 1), [('311', 300, 0, cls.customer), ('701', 0, 300, cls.customer)])
        cls._post(S, date(2025, 5, 1), [('361', 1500, 0, cls.customer), ('701', 0, 1500, cls.customer)])
        cls._post(S, date(2025, 5, 1), [('902', 1000, 0, None), ('281', 0, 1000, None)])

        cls.group = cls.env['l10n_ua.consolidation.group'].create({
            'name': 'Група П',
            'parent_company_id': P.id,
            'member_ids': [(0, 0, {
                'company_id': S.id,
                'ownership_pct': 80.0,
                'acquisition_date': date(2025, 1, 10),
            })],
        })

    @classmethod
    def _post(cls, company, on_date, lines):
        move = cls.env['account.move'].with_company(company).create({
            'move_type': 'entry',
            'journal_id': cls.journal[company].id,
            'date': on_date,
            'line_ids': [
                (0, 0, {
                    'account_id': cls.acc[(company, code)].id,
                    'debit': debit,
                    'credit': credit,
                    'partner_id': partner.id if partner else False,
                    'name': code,
                })
                for code, debit, credit, partner in lines
            ],
        })
        move.action_post()
        return move

    def _report(self, **vals):
        values = {
            'group_id': self.group.id,
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        }
        values.update(vals)
        report = self.env['l10n_ua.consolidation.report'].create(values)
        report.action_compute()
        return report

    @staticmethod
    def _line(report, form, key):
        return report.line_ids.filtered(lambda l: l.form == form and l.row_key == key)

    def _cell(self, report, form, key, company=None, kind=None, column_type=None):
        cells = report.cell_ids.filtered(
            lambda c: c.line_id.form == form and c.line_id.row_key == key and c.period == 'current')
        if company is not None:
            cells = cells.filtered(lambda c: c.column_type == 'company' and c.company_id == company)
        if kind is not None:
            cells = cells.filtered(lambda c: c.elimination_kind == kind)
        if column_type is not None:
            cells = cells.filtered(lambda c: c.column_type == column_type)
        return sum(cells.mapped('amount'))

    # ── Tests ───────────────────────────────────────────────

    def test_group_defaults(self):
        self.assertEqual(self.group.company_ids, self.parent | self.sub)
        self.assertEqual(self.group.intragroup_partner_ids, self.parent.partner_id | self.sub.partner_id)
        self.assertAlmostEqual(self.group.member_ids.nci_pct, 20.0)

    def test_company_columns(self):
        report = self._report()
        # Parent: 1030 800, 1125 1000, 1165 500 = 2300; equity 1000 + 700, payables 600
        self.assertAlmostEqual(self._cell(report, 'balance', 'lt_financial_investments', self.parent), 800)
        self.assertAlmostEqual(self._cell(report, 'balance', 'total_assets', self.parent), 2300)
        self.assertAlmostEqual(self._cell(report, 'balance', 'total_liabilities', self.parent), 2300)
        self.assertAlmostEqual(self._cell(report, 'balance', 'retained_earnings', self.parent), 700)
        self.assertAlmostEqual(self._cell(report, 'balance', 'total_assets', self.sub), 2500)
        self.assertAlmostEqual(self._cell(report, 'balance', 'total_liabilities', self.sub), 2500)
        # Company P&L columns follow Form 2 of l10n_ua_accounting exactly
        # (Form 2 reads company-dependent account codes of the active company)
        for company in (self.parent, self.sub):
            form2 = self.env['l10n_ua.pnl.report'].with_company(company).create({
                'company_id': company.id,
                'date_from': date(2025, 1, 1),
                'date_to': date(2025, 12, 31),
            })
            form2.action_compute()
            self.assertAlmostEqual(self._cell(report, 'pnl', 'net_profit', company), form2.net_profit)
        self.assertAlmostEqual(self._cell(report, 'pnl', 'net_profit', self.parent), 700)
        self.assertAlmostEqual(self._cell(report, 'pnl', 'net_profit', self.sub), 500)

    def test_balance_eliminations(self):
        report = self._report()
        line = lambda key: self._line(report, 'balance', key)  # noqa: E731
        # consolidated = sum of companies + eliminations, on every row
        for row in report.line_ids.filtered(lambda l: l.form == 'balance' and l.line_type != 'section'):
            self.assertAlmostEqual(row.current_amount, row.companies_amount + row.elimination_amount,
                                   msg=row.code)
        # intra-group receivable/payable eliminated
        self.assertAlmostEqual(self._cell(report, 'balance', 'receivables_goods', kind='intragroup'), -1000)
        self.assertAlmostEqual(self._cell(report, 'balance', 'payables_goods', kind='intragroup'), -1000)
        self.assertAlmostEqual(line('receivables_goods').current_amount, 1500)
        self.assertAlmostEqual(line('payables_goods').current_amount, 600)
        # investment vs equity at acquisition; goodwill 800 − 80 % × 1000 = 0
        self.assertAlmostEqual(line('lt_financial_investments').current_amount, 0)
        self.assertAlmostEqual(self._cell(report, 'balance', 'registered_capital', kind='investment'), -1000)
        self.assertAlmostEqual(line('registered_capital').current_amount, 1000)
        self.assertAlmostEqual(line('goodwill').current_amount, 0)
        # NCI: 20 % × (1000 at acquisition + 500 profit since)
        self.assertAlmostEqual(line('nci').current_amount, 300)
        self.assertAlmostEqual(report.nci_equity, 300)
        self.assertAlmostEqual(line('retained_earnings').current_amount, 700 + 0.8 * 500)
        # the balance still balances
        self.assertAlmostEqual(report.total_assets, 3000)
        self.assertAlmostEqual(report.total_liabilities, 3000)
        self.assertAlmostEqual(report.balance_difference, 0)
        self.assertFalse(report.warning_text)

    def test_pnl_eliminations(self):
        report = self._report()
        line = lambda key: self._line(report, 'pnl', key)  # noqa: E731
        self.assertAlmostEqual(line('net_revenue').companies_amount, 2800)
        self.assertAlmostEqual(self._cell(report, 'pnl', 'net_revenue', kind='intragroup'), -1000)
        self.assertAlmostEqual(self._cell(report, 'pnl', 'cost_of_sales', kind='cost_of_sales'), -1000)
        self.assertAlmostEqual(line('net_revenue').current_amount, 1800)
        self.assertAlmostEqual(line('cost_of_sales').current_amount, 600)
        self.assertAlmostEqual(line('net_profit').current_amount, 1200)
        self.assertAlmostEqual(line('np_nci').current_amount, 100)
        self.assertAlmostEqual(line('np_owners').current_amount, 1100)
        self.assertAlmostEqual(report.nci_profit, 100)
        # Owners' profit equals the change of group retained earnings in 1-к
        self.assertAlmostEqual(self._line(report, 'balance', 'retained_earnings').current_amount,
                               line('np_owners').current_amount)

    def test_manual_adjustment_unrealised_profit(self):
        report = self.env['l10n_ua.consolidation.report'].create({
            'group_id': self.group.id,
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
            'adjustment_ids': [
                (0, 0, {'form': 'balance', 'row_key': 'b_inventories', 'amount': -50,
                        'name': 'Нереалізований прибуток у запасах'}),
                (0, 0, {'form': 'balance', 'row_key': 'b_retained_earnings', 'amount': -50,
                        'name': 'Нереалізований прибуток у запасах'}),
                (0, 0, {'form': 'pnl', 'row_key': 'p_cost_of_sales', 'amount': 50,
                        'name': 'Нереалізований прибуток у запасах'}),
            ],
        })
        report.action_compute()
        self.assertAlmostEqual(self._line(report, 'balance', 'inventories').current_amount, -50)
        self.assertAlmostEqual(report.total_assets, 2950)
        self.assertAlmostEqual(report.balance_difference, 0)
        self.assertAlmostEqual(report.net_profit, 1150)
        self.assertAlmostEqual(self._cell(report, 'pnl', 'cost_of_sales', kind='manual'), 50)

    def test_comparison_before_acquisition(self):
        """At 31.12.2024 nothing is consolidated yet; members acquired later are skipped."""
        report = self._report()
        self.assertAlmostEqual(self._line(report, 'balance', 'total_assets').previous_amount, 0)
        self.assertFalse(report.cell_ids.filtered(
            lambda c: c.period == 'previous' and c.company_id == self.sub))

    def test_access_requires_all_companies(self):
        report = self._report()
        user = self.env['res.users'].create({
            'name': 'Бухгалтер лише материнської',
            'login': 'cons_parent_only',
            'company_id': self.parent.id,
            'company_ids': [(6, 0, self.parent.ids)],
            'group_ids': [(6, 0, [self.env.ref('account.group_account_manager').id,
                                  self.env.ref('base.group_user').id])],
        })
        Report = self.env['l10n_ua.consolidation.report'].with_user(user)
        self.assertFalse(Report.search([('id', '=', report.id)]))
        with self.assertRaises(AccessError):
            self.group.with_user(user)._check_user_companies()
        user.company_ids |= self.sub
        self.assertTrue(Report.search([('id', '=', report.id)]))
        Report.browse(report.id).with_context(allowed_company_ids=self.parent.ids).action_compute()

    def test_foreign_currency_member_refused(self):
        usd = self.env.ref('base.USD')
        usd.active = True
        foreign = self.env['res.company'].create({'name': 'Foreign Sub', 'currency_id': usd.id})
        self.env.user.company_ids |= foreign
        self.group.member_ids = [(0, 0, {
            'company_id': foreign.id, 'ownership_pct': 100, 'acquisition_date': date(2025, 1, 1),
            'investment_source': 'manual', 'investment_amount_manual': 0,
        })]
        with self.assertRaises(ValidationError):
            self._report()

    def test_reports_render(self):
        report = self._report()
        for xmlid in ('l10n_ua_consolidation.action_report_consolidated_balance',
                      'l10n_ua_consolidation.action_report_consolidated_pnl'):
            html = self.env['ir.actions.report']._render_qweb_html(xmlid, report.ids)[0]
            self.assertIn(b'1490' if 'balance' in xmlid else b'2475', html)
        html = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_consolidation.action_report_consolidated_balance', report.ids)[0]
        self.assertIn('КОНСОЛІДОВАНИЙ БАЛАНС'.encode(), html)
        action = report.action_open_worksheet()
        self.assertEqual(action['res_model'], 'l10n_ua.consolidation.cell')
