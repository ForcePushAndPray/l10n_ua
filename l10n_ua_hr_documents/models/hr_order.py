import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from psycopg2 import IntegrityError

_SYNC_EXC = (UserError, ValidationError, IntegrityError)
_logger = logging.getLogger(__name__)

class HrOrder(models.Model):
    _name = 'hr.order'
    _description = 'HR Order'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Number', readonly=True, copy=False, default='New')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, tracking=True)
    order_type = fields.Selection([
        ('hiring', 'Hiring'),
        ('dismissal', 'Dismissal'),
        ('transfer', 'Transfer'),
        ('vacation', 'Vacation'),
        ('bonus', 'Bonus'),
        ('sick_leave', 'Sick Leave'),
        ('business_trip', 'Business Trip'),
        ('other', 'Other'),
    ], string='Order Type', required=True, default='other', tracking=True)

    employee_id = fields.Many2one('hr.employee', string='Employee', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    job_id = fields.Many2one('hr.job', string='Job Position', tracking=True)

    # Hiring-specific fields
    date_start = fields.Date(
        string='Employment Start Date',
        tracking=True,
        help='Date when employment begins'
    )
    date_end = fields.Date(
        string='Employment End Date',
        tracking=True,
        help='Contract end date (for fixed-term contracts)'
    )
    is_fixed_term = fields.Boolean(
        string='Fixed-term Contract',
        help='Check if this is a fixed-term (строковий) contract'
    )
    employment_form = fields.Selection([
        ('main', 'Main place of work'),
        ('secondary', 'Concurrent employment'),
    ], string='Employment Type', tracking=True)

    # Dismissal-specific fields
    date_dismissal = fields.Date(
        string='Dismissal Date',
        tracking=True,
        help='Effective date of employment termination'
    )
    dismissal_reason = fields.Text(
        string='Dismissal Reason',
        help='Legal basis for dismissal (e.g., "за власним бажанням, ст. 38 КЗпП України")'
    )
    previous_departure_date = fields.Date(
        string='Previous Departure Date (backup)',
        copy=False,
        readonly=True,
        help='Internal: saves employee.departure_date before this dismissal '
             'order was applied, so cancellation can restore it.',
    )
    previous_departure_date_saved = fields.Boolean(
        copy=False,
        readonly=True,
        default=False,
        help='Internal: True if previous_departure_date holds a backed-up value '
             '(needed because False is a legitimate previous value).',
    )
    termination_reason_id = fields.Many2one(
        'hr.termination.reason',
        string='Termination Reason (from catalog)',
        tracking=True,
        help='Pick a structured termination reason from the legal catalog. '
             'When set, the dismissal order will use its full_text and render '
             'description_html (legal explanation) in the print template.',
    )
    include_vacation_compensation = fields.Boolean(
        string='Compensate Unused Vacation',
        default=True,
        help='Add the standard "виплатити компенсацію за N календарних днів '
             'невикористаної відпустки" phrase to the dismissal order.',
    )
    unused_vacation_days = fields.Float(
        string='Unused Vacation Days',
        compute='_compute_unused_vacation_days',
        store=True,
        readonly=False,
        help='Calendar days of unused vacation to compensate on dismissal. '
             'Auto-filled from the vacation balance; editable.',
    )

    @api.depends('order_type', 'employee_id', 'date_dismissal', 'date')
    def _compute_unused_vacation_days(self):
        has_balance = 'hr.vacation.balance' in self.env
        for order in self:
            days = 0.0
            if (has_balance and order.order_type == 'dismissal'
                    and order.employee_id):
                ref_date = (order.date_dismissal or order.date
                            or fields.Date.context_today(order))
                balances = self.env['hr.vacation.balance'].search([
                    ('employee_id', '=', order.employee_id.id),
                    ('year', '=', ref_date.year),
                ])
                days = sum(balances.mapped('remaining_days'))
            order.unused_vacation_days = max(0.0, days)

    # Vacation-specific fields
    vacation_date_from = fields.Date(string='Vacation Start Date', tracking=True)
    vacation_date_to = fields.Date(string='Vacation End Date', tracking=True)
    leave_id = fields.Many2one(
        'hr.leave',
        string='Leave Record',
        ondelete='set null',
        copy=False,
        index=True,
    )
    leave_count = fields.Integer(
        string='Time Off',
        compute='_compute_leave_count',
        help='Number of time off records tied to THIS order (0 or 1 — the '
             'order and its leave reference each other). Drives the "Time '
             'Off" smart button on vacation orders.'
    )

    can_create_leave = fields.Boolean(
        string='Can Create Time Off',
        compute='_compute_can_create_leave',
        help='Technical: true when the "New Time Off" button should be shown — '
             'a vacation order with all its details filled in and no time off '
             'linked yet.'
    )

    @api.depends('order_type', 'leave_id', 'employee_id', 'holiday_status_id',
                 'vacation_date_from', 'vacation_date_to')
    def _compute_can_create_leave(self):
        for order in self:
            order.can_create_leave = bool(
                order.order_type == 'vacation' and not order.leave_id
                and order.employee_id and order.holiday_status_id
                and order.vacation_date_from and order.vacation_date_to)

    def action_create_leave(self):
        """"New Time Off" button. Opens a leave form pre-filled from this
        order so the user can review and save it — the same explicit flow the
        leave form uses to issue an order. Nothing is created until they save;
        default_order_id links the two sides back together."""
        self.ensure_one()
        if self.leave_id:
            raise UserError(_('This order already has a linked time off.'))
        if self.order_type != 'vacation':
            raise UserError(_('Only a vacation order records time off.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Time Off'),
            'res_model': 'hr.leave',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_holiday_status_id': self.holiday_status_id.id,
                'default_request_date_from': self.vacation_date_from,
                'default_request_date_to': self.vacation_date_to,
                'default_order_id': self.id,
            },
        }

    @api.depends('leave_id')
    def _compute_leave_count(self):
        # Elevated: HR officers can read their companies' time off, but a
        # plain HR user may also open a vacation order, and for them the core
        # rule hides another employee's leave. A stat number on a smart button
        # must never make the form unopenable.
        for order in self:
            order.leave_count = len(order.sudo()._linked_leaves())

    def _linked_leaves(self):
        """Leaves tied to THIS order — not the employee's whole time off
        history. Normally exactly the order's own leave_id; the reverse link
        (hr.leave.order_id) is unioned in as well so a leave pointing here
        without the back-link having been written yet is still surfaced."""
        self.ensure_one()
        leaves = self.leave_id
        origin_id = self._origin.id
        if origin_id:
            leaves |= self.env['hr.leave'].search(
                [('order_id', '=', origin_id)])
        return leaves

    def action_view_leaves(self):
        """Smart button: open the time off record(s) tied to THIS order —
        opening the form directly when there is just one (the normal case)."""
        self.ensure_one()
        leaves = self._linked_leaves()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Time Off'),
            'res_model': 'hr.leave',
            'context': {'default_employee_id': self.employee_id.id},
        }
        if len(leaves) == 1:
            action.update({'view_mode': 'form', 'res_id': leaves.id})
        else:
            action.update({'view_mode': 'list,form',
                           'domain': [('id', 'in', leaves.ids)]})
        return action

    # Related field — eliminates duplication 
    holiday_status_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        related='leave_id.holiday_status_id',
        store=True,
        readonly=False,   # writable for orders being created standalone before leave is linked
        precompute=True,
        tracking=True,
    )

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Auto-fill department and job position from employee."""
        if self.employee_id:
            self.department_id = self.employee_id.department_id
            self.job_id = self.employee_id.job_id

    @api.onchange('termination_reason_id')
    def _onchange_termination_reason_id(self):
        """Auto-fill dismissal_reason text from the picked catalog entry."""
        if self.termination_reason_id and self.termination_reason_id.full_text:
            self.dismissal_reason = self.termination_reason_id.full_text

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Reset cross-company employee/department/job when company changes."""
        if self.employee_id and self.employee_id.company_id \
                and self.employee_id.company_id != self.company_id:
            self.employee_id = False
        if self.department_id and self.department_id.company_id \
                and self.department_id.company_id != self.company_id:
            self.department_id = False
        if self.job_id and self.job_id.company_id \
                and self.job_id.company_id != self.company_id:
            self.job_id = False

    subject = fields.Char(string='Subject', required=True, tracking=True, compute='_compute_subject', store=True, readonly=False, precompute=True)



    ORDER_TYPE_SUBJECTS = {
        'hiring': 'Про прийняття на роботу',
        'dismissal': 'Про припинення трудового договору',
        'transfer': 'Про переведення на іншу роботу',
        'vacation': 'Про надання відпустки',
        'bonus': 'Про преміювання',
        'sick_leave': 'Про оплату листка непрацездатності',
        'business_trip': 'Про направлення у службове відрядження',
        'other': 'Наказ',
    }

    @api.depends('order_type')
    def _compute_subject(self):
        for order in self:
            if not order.subject:
                order.subject = self.ORDER_TYPE_SUBJECTS.get(order.order_type, 'Наказ')

    content = fields.Html(string='Content')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    confirmed_by_id = fields.Many2one(
        'res.users',
        string='Confirmed By',
        readonly=True,
        copy=False,
        help='User who confirmed this order in the system — the HR officer '
             'recording that the printed order was signed. Kept as the audit '
             'trail of the act the order performs (e.g. granting a leave).',
    )
    confirmed_date = fields.Datetime(
        string='Confirmed On',
        readonly=True,
        copy=False,
        help='When the order was confirmed in the system.',
    )

    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                  default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                order_type = vals.get('order_type', 'other')
                sequence_code = f'hr.order.{order_type}'
                vals['name'] = self.env['ir.sequence'].next_by_code(sequence_code) or 'New'

        # No time off is auto-created for a vacation order. It is created only
        # through the "New Time Off" button, which opens a leave form
        # pre-filled from the order for the user to review and save.

        # An order opened from a leave's "New Order" button carries the leave
        # in the context. Re-apply it: navigating away from the unsaved form
        # and back can drop the field, which would save an unlinked order and
        # let the leave offer to create a second one.
        leave_from_ctx = self.env.context.get('default_leave_id')
        if leave_from_ctx:
            for vals in vals_list:
                vals.setdefault('leave_id', leave_from_ctx)

        # Add _sync_order_leave context to prevent duplicate orders on inverse
        # related fields write. leave_skip_state_check lets the order write to
        # its own linked leave (e.g. the related holiday_status_id inverse)
        # without hr_holidays raising "modification not allowed in the current
        # state" when the leave is past draft/confirm.
        orders = super(HrOrder, self.with_context(
            _sync_order_leave=True, leave_skip_state_check=True)).create(vals_list)

        # Back-link leaves → orders in a single write per leave
        for order in orders:
            if order.leave_id and not order.leave_id.order_id:
                order.leave_id.with_context(
                    _sync_order_leave=True, leave_skip_state_check=True
                ).write({'order_id': order.id})
        orders._sync_hiring_to_employee()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('_sync_order_leave'):
            if {'vacation_date_from', 'vacation_date_to'} & vals.keys():
                for order in self.filtered(
                    lambda o: o.order_type == 'vacation'
                    and o.leave_id
                    # Only push dates onto a still-editable leave; an approved,
                    # refused or cancelled leave must not be silently rewritten
                    # (and hr_holidays would block it anyway).
                    and o.leave_id.state in ('draft', 'confirm')
                ):
                    order.leave_id.with_context(
                        _sync_order_leave=True, leave_skip_state_check=True
                    ).write({
                        'date_from': fields.Datetime.from_string(str(order.vacation_date_from)) if order.vacation_date_from else False,
                        'date_to': fields.Datetime.from_string(str(order.vacation_date_to)) if order.vacation_date_to else False,
                    })
        if vals.keys() & {'order_type', 'employee_id', 'job_id', 'date', 'date_start', 'date_end', 'is_fixed_term', 'name'}:
            self._sync_hiring_to_employee()

        return result

    def _sync_failure(self, exc):
        """Convert a sync exception into a UserError so it surfaces as a modal
        dialog the user must dismiss before continuing. Overlapping-contract
        failures get a tailored, actionable message."""
        text = str(exc)
        if 'contract running' in text or 'active versions' in text \
                or 'overlap' in text.lower():
            return UserError(_(
                "Cannot update the employee contract: this employee already "
                "has an active contract during the selected period.\n\n"
                "Please either:\n"
                "- Change the start date so that it does not overlap with the "
                "existing contract, or\n"
                "- Create a new employee if this employee should have multiple "
                "active contracts."
            ))
        return UserError(_(
            "Failed to sync hiring order data to the employee record.\n\n"
            "Details: %s",
            text,
        ))

    def _sync_hiring_to_employee(self):
        """Sync hiring order data to the employee record.

        Three writes happen, each guarded by its own savepoint so a failure in
        one does not abort the order transaction or the other writes:

        1. Employee-level fields (``job_id``, ``hire_date``).
        2. Current version metadata (``hire_order_number``, ``hire_order_date``,
           ``job_id``) — so the employee form immediately reflects the latest
           order; these fields do not interact with contract period overlap
           checks.
        3. A dedicated contract version covering the order's period
           (``contract_date_start``/``contract_date_end``) — created or updated
           in place, matched first by ``hire_order_number`` and then by
           ``date_version``.
        """
        Version = self.env['hr.version']
        for order in self.filtered(lambda o: o.order_type == 'hiring' and o.employee_id):
            order_no = order.name if order.name and order.name != 'New' else False

            # 1. Employee-level fields
            emp_vals = {}
            if order.job_id:
                emp_vals['job_id'] = order.job_id.id
            hire_date_val = order.date_start or order.date
            if hire_date_val:
                emp_vals['hire_date'] = hire_date_val
            if emp_vals:
                try:
                    with self.env.cr.savepoint():
                        order.employee_id.write(emp_vals)
                except _SYNC_EXC as exc:
                    _logger.warning(
                        "Hiring order %s: cannot sync to employee %s: %s",
                        order.name, order.employee_id.display_name, exc,
                    )
                    raise self._sync_failure(exc) from exc

            # 2. Current version metadata (visible on the employee form)
            current = order.employee_id.current_version_id
            if current:
                current_vals = {}
                if order_no:
                    current_vals['hire_order_number'] = order_no
                if order.date:
                    current_vals['hire_order_date'] = order.date
                if order.job_id:
                    current_vals['job_id'] = order.job_id.id
                if current_vals:
                    try:
                        with self.env.cr.savepoint():
                            current.sudo().write(current_vals)
                    except _SYNC_EXC as exc:
                        _logger.warning(
                            "Hiring order %s: cannot sync metadata to current version of %s: %s",
                            order.name, order.employee_id.display_name, exc,
                        )
                        raise self._sync_failure(exc) from exc

            # 3. Contract version for the new employment period
            version_start = order.date_start or order.date
            if not version_start:
                continue

            version_vals = {
                'contract_date_start': order.date_start or False,
                'hire_order_date': order.date or False,
            }
            if order_no:
                version_vals['hire_order_number'] = order_no
            if order.job_id:
                version_vals['job_id'] = order.job_id.id
            if order.is_fixed_term:
                version_vals['contract_date_end'] = order.date_end or False
            else:
                version_vals['contract_date_end'] = False

            existing = Version.browse()
            if order_no:
                existing = Version.search([
                    ('employee_id', '=', order.employee_id.id),
                    ('hire_order_number', '=', order_no),
                ], limit=1)
            if not existing:
                existing = Version.search([
                    ('employee_id', '=', order.employee_id.id),
                    ('date_version', '=', version_start),
                ], limit=1)

            try:
                with self.env.cr.savepoint():
                    if existing:
                        version_vals['date_version'] = version_start
                        existing.sudo().write(version_vals)
                    else:
                        version_vals['date_version'] = version_start
                        version_vals['employee_id'] = order.employee_id.id
                        template = order.employee_id.current_version_id
                        if template:
                            template.sudo().copy(version_vals)
                        else:
                            version_vals.setdefault('company_id', order.company_id.id)
                            Version.sudo().create(version_vals)
            except _SYNC_EXC as exc:
                _logger.warning(
                    "Hiring order %s: cannot sync to contract version of %s: %s",
                    order.name, order.employee_id.display_name, exc,
                )
                raise self._sync_failure(exc) from exc

    def _check_vacation_confirm_rights(self):
        """Confirming a vacation order records that the printed, signed order
        was issued — the legal act that obliges the employee to take the leave,
        and which locks the leave against being refused afterwards.

        HR officers prepare and confirm orders (the director signs the printed
        document), hence the Ukraine HR Officer group: plain HR users, who may
        only maintain employee data, cannot issue one."""
        if self.env.su:
            return
        if self.env.user.has_group('l10n_ua_hr_base.group_hr_ua_officer'):
            return
        raise UserError(_(
            'Confirming a vacation order grants the leave, which requires the '
            '"Ukraine HR: Officer" access rights. Ask an HR officer to confirm '
            'this order.'))

    def action_confirm(self):
        if self.filtered(lambda o: o.order_type == 'vacation'):
            self._check_vacation_confirm_rights()
        self.write({
            'state': 'confirmed',
            'confirmed_by_id': self.env.user.id,
            'confirmed_date': fields.Datetime.now(),
        })
        for order in self.filtered(lambda o: o.order_type == 'dismissal' and o.employee_id):
            order._apply_dismissal()
        # The linked leave is deliberately NOT touched: leave and order states
        # are moved only through their own buttons. Confirming the order does
        # lock the leave though — it can no longer be refused or sent back to
        # approval (see hr.leave._check_order_allows_cancelling).

    def _apply_dismissal(self):
        """Apply a confirmed dismissal order to the employee:
        close ALL contract versions and archive the employee.

        We write contract_date_end to every hr.version of the employee:
        Odoo core syncs contract_date_end across versions only on
        `create_version`, not on direct `write`. Historical versions
        would otherwise keep `contract_date_end = False` and slip
        through the report filter `('contract_date_end', '=', False)`.
        """
        self.ensure_one()
        employee = self.employee_id
        dismissal_date = self.date_dismissal or self.date
        versions = employee.with_context(active_test=False).version_ids
        if versions:
            versions.write({
                'contract_date_end': dismissal_date,
                'termination_order_number': self.name,
                'termination_order_date': self.date,
            })
        if hasattr(employee, 'departure_date'):
            # Back up the previous value once per apply/revert cycle so revert
            # restores exactly what was there before this order — independent of
            # later manual edits.
            if not self.previous_departure_date_saved:
                self.write({
                    'previous_departure_date': employee.departure_date or False,
                    'previous_departure_date_saved': True,
                })
            employee.departure_date = dismissal_date
        if employee.active:
            employee.active = False

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        for order in self.filtered(lambda o: o.leave_id):
            order.leave_id.message_post(
                body=_('Linked vacation order %s was cancelled. Leave state is unchanged.', order.name)
            )
        for order in self.filtered(lambda o: o.order_type == 'dismissal' and o.employee_id):
            order._revert_dismissal()
        return True

    def _revert_dismissal(self):
        """Revert the effects of a previously confirmed dismissal order.

        We match versions by termination_order_number == self.name so revert
        is safe when several dismissal orders existed for the same employee.
        """
        self.ensure_one()
        employee = self.employee_id
        versions = employee.with_context(active_test=False).version_ids.filtered(
            lambda v: v.termination_order_number == self.name
        )
        if versions:
            versions.write({
                'contract_date_end': False,
                'termination_order_number': False,
                'termination_order_date': False,
            })
        if hasattr(employee, 'departure_date') and self.previous_departure_date_saved:
            employee.with_context(active_test=False).departure_date = \
                self.previous_departure_date or False
            self.write({
                'previous_departure_date': False,
                'previous_departure_date_saved': False,
            })
        if not employee.active:
            employee.with_context(active_test=False).active = True

    def unlink(self):
        leaves = self.mapped('leave_id')
        res = super().unlink()
        for leave in leaves.exists():
            leave.message_post(body=_('Linked vacation order was deleted.'))
        return res

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_load_template(self):
        self.ensure_one()
        return {
            'name': 'Select Template',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.order.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_order_type': self.order_type},
        }
