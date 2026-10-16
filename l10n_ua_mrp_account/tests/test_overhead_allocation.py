"""Розподіл загальновиробничих витрат (П(С)БО 16, п. 15–16) — issue #373.

Рахунки 91/23/26/90x/79x/44x створюються тут, тож тести не пропускаються в
базі без плану рахунків. Продукція оцінюється за середньою собівартістю
(періодична оцінка — без вимог до складського журналу), тож розподілені ЗВВ
видно у вартості руху випуску і в собівартості товару.
"""

from datetime import date, datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.l10n_ua_accounting.tests.common import AccountingTestCase


@tagged('post_install', '-at_install', 'l10n_ua_mrp_account')
class TestOverheadAllocation(AccountingTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acc_911 = cls._account('911', 'ЗВВ змінні', 'expense')
        cls.acc_912 = cls._account('912', 'ЗВВ постійні', 'expense')
        cls.acc_23 = cls._account('23', 'Виробництво', 'asset_current')
        cls.acc_26 = cls._account('26', 'Готова продукція', 'asset_current')
        cls.acc_901 = cls._account('901', 'Собівартість реалізованої продукції',
                                   'expense_direct_cost')
        cls.acc_631 = cls._account('631', 'Розрахунки з постачальниками', 'liability_payable')
        cls.acc_791 = cls._account('791', 'Результат операційної діяльності', 'equity')
        cls.acc_792 = cls._account('792', 'Результат фінансових операцій', 'equity')
        cls.acc_793 = cls._account('793', 'Результат іншої діяльності', 'equity')
        cls.acc_441 = cls._account('4411', 'Нерозподілений прибуток', 'equity')
        cls.acc_442 = cls._account('4421', 'Непокриті збитки', 'equity')
        cls.company.write({
            'fiscalyear_lock_date': False,
            'l10n_ua_overhead_base': 'quantity',
            'l10n_ua_overhead_normal_quantity': 0.0,
            'l10n_ua_overhead_variable_account_ids': [(6, 0, cls.acc_911.ids)],
            'l10n_ua_overhead_fixed_account_ids': [(6, 0, cls.acc_912.ids)],
            'l10n_ua_overhead_wip_account_id': cls.acc_23.id,
            'l10n_ua_overhead_unallocated_account_id': cls.acc_901.id,
            'l10n_ua_overhead_finished_account_id': cls.acc_26.id,
            'l10n_ua_overhead_cogs_account_id': cls.acc_901.id,
            'l10n_ua_overhead_journal_id': cls.misc_journal.id,
            'l10n_ua_overhead_auto_allocate': True,
        })

        cls.categ = cls.env['product.category'].create({
            'name': 'Продукція (AVCO)',
            'property_cost_method': 'average',
            'property_valuation': 'periodic',
        })
        cls.component = cls.env['product.product'].create({
            'name': 'Заготовка',
            'is_storable': True,
            'categ_id': cls.categ.id,
            'standard_price': 10.0,
        })
        cls.product_a = cls.env['product.product'].create({
            'name': 'Виріб А',
            'is_storable': True,
            'categ_id': cls.categ.id,
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Виріб Б',
            'is_storable': True,
            'categ_id': cls.categ.id,
        })
        cls.bom_a = cls._bom(cls.product_a, 1.0)
        cls.bom_b = cls._bom(cls.product_b, 2.0)
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(
            cls.component, cls.warehouse.lot_stock_id, 10000.0)

    @classmethod
    def _account(cls, code, name, account_type):
        Account = cls.env['account.account']
        account = Account.search([
            ('code', '=', code), ('company_ids', 'in', cls.company.id)], limit=1)
        return account or Account.create({
            'code': code,
            'name': name,
            'account_type': account_type,
            'company_ids': [(6, 0, cls.company.ids)],
            'reconcile': account_type == 'liability_payable',
        })

    @classmethod
    def _bom(cls, product, component_qty):
        return cls.env['mrp.bom'].create({
            'product_id': product.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'normal',
            'bom_line_ids': [(0, 0, {
                'product_id': cls.component.id,
                'product_qty': component_qty,
            })],
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _produce(self, bom, qty, finished=datetime(2034, 3, 15, 10, 0)):
        production = self.env['mrp.production'].create({
            'product_id': bom.product_id.id,
            'bom_id': bom.id,
            'product_qty': qty,
        })
        production.action_confirm()
        mo_form = Form(production)
        mo_form.qty_producing = qty
        production = mo_form.save()
        production.button_mark_done()
        self.assertEqual(production.state, 'done')
        production.date_finished = finished
        return production

    def _overhead(self, account, amount, on_date=date(2034, 3, 10)):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.misc_journal.id,
            'date': on_date,
            'line_ids': [
                (0, 0, {'account_id': account.id, 'debit': amount,
                        'partner_id': self.partner.id}),
                (0, 0, {'account_id': self.acc_631.id, 'credit': amount,
                        'partner_id': self.partner.id}),
            ],
        })
        move.action_post()
        return move

    def _allocation(self, **vals):
        values = {
            'company_id': self.company.id,
            'date_from': date(2034, 3, 1),
            'date_to': date(2034, 3, 31),
        }
        values.update(vals)
        return self.env['l10n_ua.overhead.allocation'].create(values)

    def _balance(self, account, to_date=date(2034, 3, 31)):
        lines = self.env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('company_id', '=', self.company.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', to_date),
        ])
        return sum(lines.mapped('balance'))

    def _finished_move(self, production):
        return production._l10n_ua_finished_moves()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_defaults_from_company(self):
        allocation = self._allocation()
        self.assertNotEqual(allocation.name, '/')
        self.assertEqual(allocation.base, 'quantity')
        self.assertEqual(allocation.variable_account_ids, self.acc_911)
        self.assertEqual(allocation.fixed_account_ids, self.acc_912)
        self.assertEqual(allocation.wip_account_id, self.acc_23)
        self.assertEqual(allocation.unallocated_account_id, self.acc_901)
        self.assertEqual(allocation.journal_id, self.misc_journal)

    def test_variable_fully_allocated(self):
        production = self._produce(self.bom_a, 10)
        finished = self._finished_move(production)
        self.assertAlmostEqual(finished.value, 100.0)
        self._overhead(self.acc_911, 1000.0)

        allocation = self._allocation(normal_base=1000.0)
        allocation.action_post()

        self.assertEqual(allocation.state, 'posted')
        self.assertAlmostEqual(allocation.variable_amount, 1000.0)
        self.assertAlmostEqual(allocation.allocated_amount, 1000.0)
        self.assertAlmostEqual(allocation.unallocated_amount, 0.0)
        self.assertAlmostEqual(allocation.line_ids.amount, 1000.0)
        # 91 is zero, 23 passes the amount through to 26
        self.assertAlmostEqual(self._balance(self.acc_911), 0.0)
        self.assertAlmostEqual(self._balance(self.acc_23), 0.0)
        self.assertAlmostEqual(self._balance(self.acc_26), 1000.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 0.0)
        # the overhead is in the finished product cost
        self.assertTrue(allocation.line_ids.valuation_adjusted)
        self.assertAlmostEqual(finished.value, 1100.0)
        self.assertAlmostEqual(self.product_a.standard_price, 110.0)
        self.assertAlmostEqual(production.l10n_ua_overhead_amount, 1000.0)

    def test_fixed_below_normal_capacity(self):
        self._produce(self.bom_a, 40)
        self._overhead(self.acc_912, 2000.0)

        allocation = self._allocation(normal_base=100.0)
        allocation.action_post()

        self.assertAlmostEqual(allocation.actual_base, 40.0)
        self.assertAlmostEqual(allocation.allocation_rate, 0.4)
        self.assertAlmostEqual(allocation.fixed_allocated_amount, 800.0)
        self.assertAlmostEqual(allocation.allocated_amount, 800.0)
        self.assertAlmostEqual(allocation.unallocated_amount, 1200.0)
        self.assertAlmostEqual(self._balance(self.acc_912), 0.0)
        self.assertAlmostEqual(self._balance(self.acc_23), 0.0)
        self.assertAlmostEqual(self._balance(self.acc_26), 800.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 1200.0)

    def test_fixed_at_or_above_normal_capacity(self):
        self._produce(self.bom_a, 120)
        self._overhead(self.acc_912, 2000.0)
        self._overhead(self.acc_911, 500.0)

        allocation = self._allocation(normal_base=100.0)
        allocation.action_post()

        self.assertAlmostEqual(allocation.allocation_rate, 1.0)
        self.assertAlmostEqual(allocation.allocated_amount, 2500.0)
        self.assertAlmostEqual(allocation.unallocated_amount, 0.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 0.0)
        self.assertAlmostEqual(self._balance(self.acc_26), 2500.0)
        self.assertAlmostEqual(self._balance(self.acc_911) + self._balance(self.acc_912), 0.0)

    def test_split_between_orders_by_base(self):
        mo_a = self._produce(self.bom_a, 10)
        mo_b = self._produce(self.bom_b, 20)
        # outside the period: not allocated
        self._produce(self.bom_a, 5, finished=datetime(2034, 4, 2, 10, 0))
        self._overhead(self.acc_911, 900.0)

        allocation = self._allocation()
        allocation.action_compute()
        lines = {line.production_id: line for line in allocation.line_ids}
        self.assertEqual(set(lines), {mo_a, mo_b})
        self.assertAlmostEqual(lines[mo_a].amount, 300.0)
        self.assertAlmostEqual(lines[mo_b].amount, 600.0)

        # material base: A 10 x 10 = 100, B 20 x 2 x 10 = 400
        allocation.base = 'material'
        allocation.action_post()
        lines = {line.production_id: line for line in allocation.line_ids}
        self.assertAlmostEqual(lines[mo_a].base_value, 100.0)
        self.assertAlmostEqual(lines[mo_b].base_value, 400.0)
        self.assertAlmostEqual(lines[mo_a].amount, 180.0)
        self.assertAlmostEqual(lines[mo_b].amount, 720.0)
        self.assertAlmostEqual(self._finished_move(mo_a).value, 100.0 + 180.0)
        self.assertAlmostEqual(self._finished_move(mo_b).value, 400.0 + 720.0)

    def test_labour_and_machine_hours_base(self):
        workcenter = self.env['mrp.workcenter'].create({
            'name': 'Верстат',
            'costs_hour': 120.0,
            'time_efficiency': 100,
        })
        bom = self._bom(self.product_b, 1.0)
        bom.operation_ids = [(0, 0, {
            'name': 'Обробка', 'workcenter_id': workcenter.id, 'time_cycle': 30.0,
        })]
        production = self.env['mrp.production'].create({
            'product_id': self.product_b.id,
            'bom_id': bom.id,
            'product_qty': 2,
        })
        production.action_confirm()
        production.workorder_ids.duration = 90.0
        mo_form = Form(production)
        mo_form.qty_producing = 2
        production = mo_form.save()
        production.button_mark_done()
        self.assertEqual(production.state, 'done')
        production.date_finished = datetime(2034, 3, 15, 10, 0)
        self.assertAlmostEqual(production._l10n_ua_machine_hours(), 1.5)
        self.assertAlmostEqual(production._l10n_ua_labour_cost(), 180.0)
        self._overhead(self.acc_911, 360.0)

        allocation = self._allocation(base='machine_hours')
        allocation.action_compute()
        self.assertAlmostEqual(allocation.actual_base, 1.5)
        allocation.base = 'labour'
        allocation.action_post()
        self.assertAlmostEqual(allocation.actual_base, 180.0)
        self.assertAlmostEqual(allocation.line_ids.labour_cost, 180.0)
        self.assertAlmostEqual(allocation.line_ids.amount, 360.0)
        calc = production._l10n_ua_cost_calculation()
        self.assertAlmostEqual(calc['labour_cost'], 180.0)
        self.assertAlmostEqual(calc['total'], 20.0 + 180.0 + 360.0)

    def test_sold_share_goes_to_cost_of_sales(self):
        production = self._produce(self.bom_a, 10)
        customer = self.env.ref('stock.stock_location_customers')
        out = self.env['stock.move'].create({
            'product_id': self.product_a.id,
            'product_uom_qty': 4.0,
            'product_uom': self.product_a.uom_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': customer.id,
        })
        out._action_confirm()
        out._action_assign()
        out.quantity = 4.0
        out.picked = True
        out._action_done()
        self._overhead(self.acc_911, 1000.0)
        self.env.invalidate_all()
        self.assertAlmostEqual(self.product_a.total_value, 60.0)

        allocation = self._allocation()
        allocation.action_post()

        line = allocation.line_ids
        self.assertEqual(line.production_id, production)
        self.assertAlmostEqual(line.amount_stock, 600.0)
        self.assertAlmostEqual(line.amount_sold, 400.0)
        self.assertAlmostEqual(self._balance(self.acc_26), 600.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 400.0)
        self.assertAlmostEqual(self._balance(self.acc_23), 0.0)
        # the stock still on hand gains exactly the stock share (600), not
        # the whole overhead added to the finished move (1000): AVCO spreads
        # the move value over the issued 4 units too
        self.env.invalidate_all()
        self.assertAlmostEqual(self._finished_move(production).value, 1100.0)
        self.assertAlmostEqual(self.product_a.total_value, 60.0 + 600.0)
        self.assertAlmostEqual(self.product_a.standard_price, 110.0)

    def _backdate(self, moves, when):
        moves.write({'date': when})
        moves.move_line_ids.write({'date': when})

    def test_sold_after_period_end_stays_in_stock(self):
        """The stock / cost of sales split is taken as of the period end,
        not as of the posting date."""
        production = self._produce(self.bom_a, 10, finished=datetime(2025, 3, 15, 10, 0))
        self._backdate(self._finished_move(production), datetime(2025, 3, 15, 10, 0))
        customer = self.env.ref('stock.stock_location_customers')
        out = self.env['stock.move'].create({
            'product_id': self.product_a.id,
            'product_uom_qty': 4.0,
            'product_uom': self.product_a.uom_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': customer.id,
        })
        out._action_confirm()
        out._action_assign()
        out.quantity = 4.0
        out.picked = True
        out._action_done()
        # sold in April, after the allocated period
        self._backdate(out, datetime(2025, 4, 5, 10, 0))
        self._overhead(self.acc_911, 1000.0, on_date=date(2025, 3, 10))

        allocation = self._allocation(date_from=date(2025, 3, 1), date_to=date(2025, 3, 31))
        allocation.action_post()

        line = allocation.line_ids
        self.assertEqual(line.production_id, production)
        self.assertAlmostEqual(line.amount_stock, 1000.0)
        self.assertAlmostEqual(line.amount_sold, 0.0)
        self.assertAlmostEqual(self._balance(self.acc_26, date(2025, 3, 31)), 1000.0)
        self.assertAlmostEqual(self._balance(self.acc_901, date(2025, 3, 31)), 0.0)

    # ------------------------------------------------------------------
    # Allocation base: zero base, normal capacity per base
    # ------------------------------------------------------------------

    def test_zero_base_falls_back_to_quantity(self):
        """Labour base without work centers: the overhead still reaches the
        orders (by quantity), it is not sent to the cost of sales."""
        self.company.write({
            'l10n_ua_overhead_normal_labour': 5000.0,
            'l10n_ua_overhead_normal_quantity': 0.0,
        })
        mo_a = self._produce(self.bom_a, 10)
        mo_b = self._produce(self.bom_b, 30)
        self._overhead(self.acc_911, 800.0)
        self._overhead(self.acc_912, 400.0)

        allocation = self._allocation(base='labour')
        self.assertAlmostEqual(allocation.normal_base, 5000.0)
        allocation.action_post()

        self.assertEqual(allocation.base, 'quantity')
        self.assertTrue(allocation.base_fallback)
        # the labour capacity (UAH) is not applied to a quantity base
        self.assertAlmostEqual(allocation.normal_base, 0.0)
        self.assertAlmostEqual(allocation.actual_base, 40.0)
        self.assertAlmostEqual(allocation.allocated_amount, 1200.0)
        self.assertAlmostEqual(allocation.unallocated_amount, 0.0)
        lines = {line.production_id: line for line in allocation.line_ids}
        self.assertAlmostEqual(lines[mo_a].amount, 300.0)
        self.assertAlmostEqual(lines[mo_b].amount, 900.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 0.0)
        self.assertTrue(any(
            'quantity produced' in (m.body or '') or 'обсягу виробництва' in (m.body or '')
            for m in allocation.message_ids))

        # choosing a base again clears the flag
        allocation.action_cancel()
        allocation.action_draft()
        allocation.base = 'material'
        self.assertFalse(allocation.base_fallback)

    def test_zero_base_without_quantity_refused(self):
        self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 500.0)
        allocation = self._allocation(base='labour')
        Production = type(self.env['mrp.production'])
        with patch.object(Production, '_l10n_ua_overhead_base_value', return_value=0.0):
            with self.assertRaises(UserError):
                allocation.action_post()
        self.assertEqual(allocation.state, 'draft')
        self.assertAlmostEqual(self._balance(self.acc_911), 500.0)

    def test_normal_base_follows_base(self):
        self.company.write({
            'l10n_ua_overhead_normal_labour': 5000.0,
            'l10n_ua_overhead_normal_machine_hours': 160.0,
            'l10n_ua_overhead_normal_quantity': 100.0,
        })
        allocation = self._allocation()
        self.assertEqual(allocation.base, 'quantity')
        self.assertAlmostEqual(allocation.normal_base, 100.0)
        allocation.base = 'machine_hours'
        self.assertAlmostEqual(allocation.normal_base, 160.0)
        allocation.write({'base': 'labour', 'normal_base': 4500.0})
        self.assertAlmostEqual(allocation.normal_base, 4500.0)
        # same base written again: the figure entered by the user is kept
        allocation.base = 'labour'
        self.assertAlmostEqual(allocation.normal_base, 4500.0)
        self.assertAlmostEqual(
            self._allocation(base='machine_hours', normal_base=150.0).normal_base, 150.0)

    def test_nothing_produced_goes_to_cost_of_sales(self):
        self._overhead(self.acc_911, 300.0)
        self._overhead(self.acc_912, 700.0)
        allocation = self._allocation(normal_base=100.0)
        allocation.action_post()
        self.assertFalse(allocation.line_ids)
        self.assertAlmostEqual(allocation.allocated_amount, 0.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 1000.0)
        self.assertAlmostEqual(self._balance(self.acc_911) + self._balance(self.acc_912), 0.0)

    def test_cancel_reverses(self):
        production = self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 1000.0)
        allocation = self._allocation()
        allocation.action_post()
        self.assertAlmostEqual(self._finished_move(production).value, 1100.0)

        allocation.action_cancel()
        self.assertEqual(allocation.state, 'cancelled')
        self.assertTrue(allocation.reversal_move_id)
        self.assertEqual(allocation.reversal_move_id.state, 'posted')
        self.assertAlmostEqual(self._balance(self.acc_911), 1000.0)
        self.assertAlmostEqual(self._balance(self.acc_26), 0.0)
        self.assertAlmostEqual(self._finished_move(production).value, 100.0)
        self.assertAlmostEqual(self.product_a.standard_price, 10.0)
        self.assertAlmostEqual(production.l10n_ua_overhead_amount, 0.0)

        # a second allocation of the same period can be posted again
        allocation.action_draft()
        allocation.action_post()
        self.assertAlmostEqual(self._finished_move(production).value, 1100.0)

    def test_overlapping_posted_allocation_refused(self):
        self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 1000.0)
        self._allocation().action_post()
        self._overhead(self.acc_911, 100.0, on_date=date(2034, 3, 20))
        with self.assertRaises(UserError):
            self._allocation(date_from=date(2034, 3, 16)).action_post()

    # ------------------------------------------------------------------
    # Period closing
    # ------------------------------------------------------------------

    def _period(self):
        return self.env['l10n_ua.tax.period'].create({
            'period_type': 'month',
            'date_start': date(2034, 3, 1),
            'date_end': date(2034, 3, 31),
            'company_id': self.company.id,
        })

    def _closing(self, period):
        return self.env['l10n_ua.period.closing'].create({
            'period_id': period.id,
            'company_id': self.company.id,
            'journal_id': self.misc_journal.id,
            'account_791_id': self.acc_791.id,
            'account_792_id': self.acc_792.id,
            'account_793_id': self.acc_793.id,
            'account_profit_id': self.acc_441.id,
            'account_loss_id': self.acc_442.id,
        })

    def test_period_closing_allocates_automatically(self):
        production = self._produce(self.bom_a, 40)
        self._overhead(self.acc_912, 2000.0)
        self.company.l10n_ua_overhead_normal_quantity = 100.0
        closing = self._closing(self._period())

        closing.action_close()

        self.assertEqual(closing.state, 'closed')
        allocation = closing.overhead_allocation_ids
        self.assertEqual(len(allocation), 1)
        self.assertEqual(allocation.state, 'posted')
        self.assertEqual(allocation.closing_id, closing)
        self.assertAlmostEqual(allocation.unallocated_amount, 1200.0)
        self.assertAlmostEqual(self._balance(self.acc_912), 0.0)
        # the unallocated overhead on 901 is closed to 791 in the same run
        closed_901 = closing.closing_line_ids.filtered(lambda l: l.account_id == self.acc_901)
        self.assertAlmostEqual(closed_901.balance, 1200.0)
        self.assertAlmostEqual(self._balance(self.acc_901), 0.0)
        self.assertAlmostEqual(self._finished_move(production).value, 400.0 + 800.0)

        # a posted allocation of a closed period cannot be cancelled directly
        with self.assertRaises(UserError):
            allocation.action_cancel()

        closing.action_reverse()
        self.assertEqual(allocation.state, 'cancelled')
        self.assertAlmostEqual(self._balance(self.acc_912), 2000.0)
        self.assertAlmostEqual(self._finished_move(production).value, 400.0)

    def test_period_closing_posts_draft_allocation(self):
        self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 500.0)
        # some cost of sales, so that the closing has a 9x balance to close
        self._overhead(self.acc_901, 50.0)
        draft = self._allocation()
        closing = self._closing(self._period())
        self.assertIn(draft, closing.overhead_allocation_ids)
        closing.action_close()
        self.assertEqual(draft.state, 'posted')
        self.assertEqual(draft.closing_id, closing)
        self.assertEqual(len(closing.overhead_allocation_ids), 1)

    def test_period_closing_continues_after_partial_allocation(self):
        self._produce(self.bom_a, 10, finished=datetime(2034, 3, 5, 10, 0))
        mo_late = self._produce(self.bom_a, 10, finished=datetime(2034, 3, 25, 10, 0))
        self._overhead(self.acc_911, 400.0, on_date=date(2034, 3, 5))
        first = self._allocation(date_to=date(2034, 3, 15))
        first.action_post()
        self._overhead(self.acc_911, 300.0, on_date=date(2034, 3, 20))
        self._overhead(self.acc_901, 50.0)
        closing = self._closing(self._period())
        closing.action_close()
        second = closing.overhead_allocation_ids - first
        self.assertEqual(len(second), 1)
        self.assertEqual(second.date_from, date(2034, 3, 16))
        self.assertEqual(second.line_ids.production_id, mo_late)
        self.assertAlmostEqual(second.allocated_amount, 300.0)
        self.assertAlmostEqual(self._balance(self.acc_911), 0.0)

    def test_period_closing_refuses_without_auto_allocation(self):
        self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 500.0)
        self.company.l10n_ua_overhead_auto_allocate = False
        closing = self._closing(self._period())
        with self.assertRaises(UserError):
            closing.action_close()
        self.assertEqual(closing.state, 'draft')

    def test_period_closing_notes_zero_base(self):
        """Auto-allocation on closing with a zero base is not silent."""
        self.company.l10n_ua_overhead_base = 'labour'
        production = self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 500.0)
        self._overhead(self.acc_901, 50.0)
        closing = self._closing(self._period())
        closing.action_close()
        allocation = closing.overhead_allocation_ids
        self.assertEqual(allocation.state, 'posted')
        self.assertEqual(allocation.base, 'quantity')
        self.assertTrue(allocation.base_fallback)
        self.assertAlmostEqual(allocation.allocated_amount, 500.0)
        self.assertAlmostEqual(self._finished_move(production).value, 100.0 + 500.0)
        self.assertTrue(any(allocation.name in (m.body or '') for m in closing.message_ids))

    def test_period_closing_without_overhead_is_unchanged(self):
        self._overhead(self.acc_901, 100.0)
        closing = self._closing(self._period())
        closing.action_close()
        self.assertEqual(closing.state, 'closed')
        self.assertFalse(closing.overhead_allocation_ids)

    # ------------------------------------------------------------------
    # Printed cost calculation
    # ------------------------------------------------------------------

    def test_cost_calculation_report(self):
        production = self._produce(self.bom_a, 10)
        self._overhead(self.acc_911, 1000.0)
        self._allocation().action_post()

        calc = production._l10n_ua_cost_calculation()
        self.assertAlmostEqual(calc['material_cost'], 100.0)
        self.assertAlmostEqual(calc['overhead_cost'], 1000.0)
        self.assertAlmostEqual(calc['total'], 1100.0)
        self.assertAlmostEqual(calc['unit_cost'], 110.0)

        html, _type = self.env['ir.actions.report']._render_qweb_html(
            'l10n_ua_mrp_account.report_cost_calculation', production.ids)
        html = html.decode()
        self.assertIn('КАЛЬКУЛЯЦІЯ', html)
        self.assertIn(production.name, html)
        self.assertIn('1 100.00', html)
        self.assertIn('110.00', html)
