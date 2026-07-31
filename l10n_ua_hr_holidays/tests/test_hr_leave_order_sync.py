from odoo.tests import common
from datetime import date
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestHrLeaveOrderSync(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create a test employee
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
        })

        # Create a leave type that issues vacation orders
        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Annual Basic Leave',
            'time_type': 'leave',
            'requires_allocation': 'yes',
            'create_order': True,
            'is_paid': True,
        })

        # Allocate leave days to the employee so validation passes
        cls.allocation = cls.env['hr.leave.allocation'].create({
            'name': 'Test Leave Allocation',
            'employee_id': cls.employee.id,
            'holiday_status_id': cls.leave_type.id,
            'number_of_days': 100,
        })
        cls.allocation.action_approve()
        if cls.allocation.state == 'validate1':
            cls.allocation.action_validate()

    def _make_leave(self, day_from, day_to):
        return self.env['hr.leave'].create({
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'request_date_from': day_from,
            'request_date_to': day_to,
        })

    def _create_order_via_button(self, leave):
        """Simulate the 'Create Order' button: it returns an action opening a
        pre-filled order form; here we replay the form save by creating the
        order from the action's default_* context."""
        ctx = leave.action_create_order()['context']
        return self.env['hr.order'].create({
            'order_type': ctx['default_order_type'],
            'employee_id': ctx['default_employee_id'],
            'department_id': ctx['default_department_id'],
            'job_id': ctx['default_job_id'],
            'leave_id': ctx['default_leave_id'],
            'vacation_date_from': ctx['default_vacation_date_from'],
            'vacation_date_to': ctx['default_vacation_date_to'],
            'subject': ctx['default_subject'],
        })

    def test_bidirectional_create_from_order(self):
        """Creating an order still creates exactly 1 leave and no duplicate
        order (the order -> leave direction is unchanged)."""
        order = self.env['hr.order'].create({
            'order_type': 'vacation',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'vacation_date_from': date(2027, 8, 1),
            'vacation_date_to': date(2027, 8, 5),
            'date': date(2027, 8, 1),
            'subject': 'Vacation',
        })

        orders_count = self.env['hr.order'].search_count(
            [('employee_id', '=', self.employee.id)])
        self.assertEqual(orders_count, 1, "Order creation generated a duplicate.")

        leaves = self.env['hr.leave'].search(
            [('employee_id', '=', self.employee.id)])
        self.assertEqual(len(leaves), 1, "Exactly one leave must be created.")

        self.assertEqual(order.leave_id.id, leaves.id)
        self.assertEqual(leaves.order_id.id, order.id)

    def test_no_order_created_on_save(self):
        """Saving a leave must NOT auto-create an order anymore."""
        leave = self._make_leave(date(2027, 9, 1), date(2027, 9, 5))
        self.assertFalse(leave.order_id, "Saving a leave should not create an order.")
        orders = self.env['hr.order'].search(
            [('employee_id', '=', self.employee.id)])
        self.assertEqual(len(orders), 0, "No order should exist after saving a leave.")
        self.assertTrue(leave.can_create_order,
                        "The 'Create Order' button should be available.")

    def test_manual_create_order_action(self):
        """The button returns an action opening the order form pre-filled from
        the leave, and does NOT create the order itself."""
        leave = self._make_leave(date(2027, 9, 10), date(2027, 9, 15))
        action = leave.action_create_order()

        self.assertEqual(action['res_model'], 'hr.order')
        self.assertEqual(action['view_mode'], 'form')
        ctx = action['context']
        self.assertEqual(ctx['default_leave_id'], leave.id)
        self.assertEqual(ctx['default_employee_id'], self.employee.id)
        self.assertEqual(ctx['default_order_type'], 'vacation')
        self.assertEqual(ctx['default_vacation_date_from'], date(2027, 9, 10))
        self.assertEqual(ctx['default_vacation_date_to'], date(2027, 9, 15))

        # Nothing is created until the user saves the form.
        self.assertFalse(leave.order_id)
        self.assertEqual(self.env['hr.order'].search_count(
            [('employee_id', '=', self.employee.id)]), 0)

    def test_manual_create_order_saved_links_no_duplicate(self):
        """Saving the pre-filled order links it to the leave as a draft and
        does not spawn a second leave or order."""
        leave = self._make_leave(date(2027, 9, 10), date(2027, 9, 15))
        order = self._create_order_via_button(leave)

        self.assertEqual(order.state, 'draft',
                         "Order for an unapproved leave must be a draft.")
        self.assertEqual(order.leave_id, leave)
        self.assertEqual(leave.order_id, order)
        self.assertFalse(leave.can_create_order,
                         "Button must hide once an order exists.")
        self.assertEqual(leave.order_count, 1)
        self.assertEqual(self.env['hr.leave'].search_count(
            [('employee_id', '=', self.employee.id)]), 1,
            "No duplicate leave must be created.")
        self.assertEqual(self.env['hr.order'].search_count([
            ('employee_id', '=', self.employee.id),
            ('order_type', '=', 'vacation'),
        ]), 1, "No duplicate order must be created.")

    def test_smart_buttons_scoped_to_this_document(self):
        """The Orders / Time Off smart buttons count and open the documents
        linked to THIS record — a second leave with its own order must not
        inflate the first one's count."""
        leave_a = self._make_leave(date(2028, 5, 10), date(2028, 5, 15))
        order_a = self._create_order_via_button(leave_a)
        leave_b = self._make_leave(date(2028, 8, 10), date(2028, 8, 15))
        order_b = self._create_order_via_button(leave_b)

        # The employee has two vacation orders overall...
        self.assertEqual(self.env['hr.order'].search_count([
            ('employee_id', '=', self.employee.id),
            ('order_type', '=', 'vacation'),
        ]), 2)

        # ...but each leave sees only its own.
        (leave_a | leave_b).invalidate_recordset(['order_count'])
        self.assertEqual(leave_a.order_count, 1)
        self.assertEqual(leave_b.order_count, 1)
        self.assertEqual(leave_a.action_view_orders().get('res_id'), order_a.id)
        self.assertEqual(leave_b.action_view_orders().get('res_id'), order_b.id)

        # Same scoping from the order side.
        (order_a | order_b).invalidate_recordset(['leave_count'])
        self.assertEqual(order_a.leave_count, 1)
        self.assertEqual(order_a.action_view_leaves().get('res_id'), leave_a.id)
        self.assertEqual(order_b.action_view_leaves().get('res_id'), leave_b.id)

    def test_button_blocked_when_order_exists(self):
        """Once an order is linked, the button raises instead of starting a
        second one."""
        leave = self._make_leave(date(2027, 9, 20), date(2027, 9, 25))
        self._create_order_via_button(leave)
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            leave.action_create_order()

    def test_manual_order_date_sync(self):
        """Editing the leave dates flows through to the linked draft order."""
        leave = self._make_leave(date(2027, 10, 10), date(2027, 10, 15))
        order = self._create_order_via_button(leave)

        leave.write({
            'request_date_from': date(2027, 10, 12),
            'request_date_to': date(2027, 10, 18),
        })
        self.assertEqual(order.vacation_date_from, date(2027, 10, 12))
        self.assertEqual(order.vacation_date_to, date(2027, 10, 18))

    def test_validation_never_issues_an_order(self):
        """Approving a leave issues no order — orders come only from the
        "New Order" button."""
        leave = self._make_leave(date(2027, 10, 1), date(2027, 10, 5))
        self.assertFalse(leave.order_id)

        leave._action_validate()

        self.assertFalse(leave.order_id,
                         "Approving a leave must not create an order.")
        self.assertEqual(self.env['hr.order'].search_count([
            ('employee_id', '=', self.employee.id),
            ('order_type', '=', 'vacation'),
        ]), 0)

    def test_validation_leaves_existing_draft_untouched(self):
        """A draft order keeps its state when its leave is approved: only the
        order's own buttons move it."""
        leave = self._make_leave(date(2027, 11, 10), date(2027, 11, 15))
        draft = self._create_order_via_button(leave)
        self.assertEqual(draft.state, 'draft')

        leave._action_validate()

        self.assertEqual(leave.order_id, draft, "Order must not be replaced.")
        self.assertEqual(draft.state, 'draft',
                         "Approving the leave must not confirm the order.")

    def test_order_confirm_does_not_approve_leave(self):
        """Confirming a vacation order does not move the leave: states are
        changed only through their own buttons. The leave can still be
        approved afterwards, when the order was issued first."""
        order = self.env['hr.order'].create({
            'order_type': 'vacation',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'vacation_date_from': date(2028, 3, 1),
            'vacation_date_to': date(2028, 3, 5),
            'date': date(2028, 3, 1),
            'subject': 'Vacation',
        })
        leave = order.leave_id
        self.assertTrue(leave, "Order must auto-create its leave.")
        state_before = leave.state

        order.action_confirm()

        self.assertEqual(order.state, 'confirmed')
        self.assertEqual(leave.state, state_before,
                         "Confirming the order must not move the leave.")

        # Approving the leave later is still allowed — the whole point of
        # keeping Approve active once an order exists.
        leave._action_validate()
        self.assertEqual(leave.state, 'validate')

    def test_confirmed_order_blocks_undoing_the_leave(self):
        """A confirmed order is the legal document obliging the employee to
        take the leave, so the leave can no longer be refused or sent back to
        approval."""
        from odoo.exceptions import UserError
        leave = self._make_leave(date(2028, 9, 1), date(2028, 9, 5))
        order = self._create_order_via_button(leave)
        order.action_confirm()
        leave.invalidate_recordset(['has_confirmed_order'])
        self.assertTrue(leave.has_confirmed_order)

        with self.assertRaises(UserError):
            leave.action_refuse()
        with self.assertRaises(UserError):
            leave.action_back_to_approval()

    def test_draft_order_does_not_block_the_leave(self):
        """Only a CONFIRMED order locks the leave: a draft one leaves refusing
        available."""
        leave = self._make_leave(date(2028, 10, 1), date(2028, 10, 5))
        self._create_order_via_button(leave)
        leave.invalidate_recordset(['has_confirmed_order'])
        self.assertFalse(leave.has_confirmed_order)

        leave.action_refuse()
        self.assertEqual(leave.state, 'refuse')

    def _user_with(self, groups, login):
        # Odoo 19 renamed res.users.groups_id -> group_ids.
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'group_ids': [(6, 0, [self.env.ref(g).id for g in groups])],
        })

    def test_vacation_confirm_requires_hr_officer(self):
        """Confirming a vacation order is what grants the leave, so it needs
        Ukraine HR Officer rights — a plain HR user cannot do it."""
        from odoo.exceptions import UserError
        order = self.env['hr.order'].create({
            'order_type': 'vacation',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'vacation_date_from': date(2028, 3, 1),
            'vacation_date_to': date(2028, 3, 5),
            'date': date(2028, 3, 1),
            'subject': 'Vacation',
        })
        clerk = self._user_with(['base.group_user', 'hr.group_hr_user'],
                                'plain_hr_user')
        with self.assertRaises(UserError):
            order.with_user(clerk).action_confirm()
        self.assertEqual(order.state, 'draft')
        self.assertNotEqual(order.leave_id.state, 'validate')

    def test_vacation_confirm_by_officer_is_audited(self):
        """An HR officer may confirm; the order records who confirmed it and
        when."""
        order = self.env['hr.order'].create({
            'order_type': 'vacation',
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'vacation_date_from': date(2028, 4, 1),
            'vacation_date_to': date(2028, 4, 5),
            'date': date(2028, 4, 1),
            'subject': 'Vacation',
        })
        officer = self._user_with(
            ['base.group_user', 'l10n_ua_hr_base.group_hr_ua_officer'],
            'ua_hr_officer')

        order.with_user(officer).action_confirm()

        self.assertEqual(order.state, 'confirmed')
        self.assertEqual(order.confirmed_by_id, officer)
        self.assertTrue(order.confirmed_date)

    def test_officer_may_read_company_leaves(self):
        """The Ukraine HR Officer record rule lets an officer read another
        employee's time off in their company — core alone would hide it, and
        the order flow depends on that access."""
        from odoo.exceptions import AccessError
        leave = self._make_leave(date(2028, 6, 1), date(2028, 6, 5))
        officer = self._user_with(
            ['base.group_user', 'l10n_ua_hr_base.group_hr_ua_officer'],
            'ua_hr_officer_read')
        # The leave belongs to another employee, so a plain user cannot see it.
        plain = self._user_with(['base.group_user'], 'plain_employee_read')
        with self.assertRaises(AccessError):
            leave.with_user(plain).read(['state'])
        # The officer can.
        self.assertTrue(leave.with_user(officer).read(['state']))

    def test_refuse_leaves_a_draft_order_alone(self):
        """Refusing a leave neither deletes its draft order nor changes its
        state — orders move only through their own buttons."""
        leave = self._make_leave(date(2027, 12, 1), date(2027, 12, 5))
        order = self._create_order_via_button(leave)
        self.assertEqual(order.state, 'draft')

        leave.action_refuse()

        self.assertEqual(order.state, 'draft',
                         "Refusing the leave must not change the order state.")
        self.assertEqual(leave.order_id, order, "The link must survive.")

    def test_cascade_delete(self):
        """Unlinking a draft leave also unlinks its draft order."""
        leave = self._make_leave(date(2027, 11, 1), date(2027, 11, 5))
        order = self._create_order_via_button(leave)
        self.assertTrue(order.exists())

        leave.unlink()

        self.assertFalse(order.exists(),
                         "The draft order was not cascade deleted with the leave.")
