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
        self.assertEqual(self.env['hr.order'].search_count([
            ('employee_id', '=', self.employee.id),
            ('order_type', '=', 'vacation'),
        ]), 1, "No duplicate order must be created.")

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

    def test_order_created_at_validation(self):
        """No order on save; validation creates and confirms it."""
        leave = self._make_leave(date(2027, 10, 1), date(2027, 10, 5))
        self.assertFalse(leave.order_id)

        leave._action_validate()

        order = leave.order_id
        self.assertTrue(order, "Validation must create the order.")
        self.assertEqual(order.state, 'confirmed',
                         "Order must be confirmed once the leave is validated.")

    def test_validation_confirms_existing_draft(self):
        """A pre-created draft order is confirmed at validation, not
        duplicated."""
        leave = self._make_leave(date(2027, 11, 10), date(2027, 11, 15))
        draft = self._create_order_via_button(leave)
        self.assertEqual(draft.state, 'draft')

        leave._action_validate()

        self.assertEqual(leave.order_id, draft, "Order must not be replaced.")
        self.assertEqual(draft.state, 'confirmed')
        self.assertEqual(self.env['hr.order'].search_count([
            ('employee_id', '=', self.employee.id),
            ('order_type', '=', 'vacation'),
        ]), 1, "Validation must not create a duplicate order.")

    def test_order_confirm_approves_leave(self):
        """Confirming a vacation order approves (validates) its linked leave —
        the order -> leave state sync."""
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
        self.assertNotEqual(leave.state, 'validate',
                            "Leave must start unapproved.")

        order.action_confirm()

        self.assertEqual(order.state, 'confirmed')
        self.assertEqual(leave.state, 'validate',
                         "Leave must be validated when its order is confirmed.")

    def test_back_to_approval_reverts_order_to_draft(self):
        """Returning a validated leave to approval puts its confirmed order
        back to draft."""
        leave = self._make_leave(date(2027, 12, 1), date(2027, 12, 5))
        leave._action_validate()
        order = leave.order_id
        self.assertEqual(order.state, 'confirmed')

        leave.action_back_to_approval()

        self.assertEqual(order.state, 'draft',
                         "Order must return to draft when the leave does.")

    def test_cascade_delete(self):
        """Unlinking a draft leave also unlinks its draft order."""
        leave = self._make_leave(date(2027, 11, 1), date(2027, 11, 5))
        order = self._create_order_via_button(leave)
        self.assertTrue(order.exists())

        leave.unlink()

        self.assertFalse(order.exists(),
                         "The draft order was not cascade deleted with the leave.")
