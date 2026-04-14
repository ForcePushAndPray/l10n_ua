from odoo import models, fields, api
from odoo.exceptions import UserError


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

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Auto-fill department and job position from employee."""
        if self.employee_id:
            self.department_id = self.employee_id.department_id
            self.job_id = self.employee_id.job_id

    subject = fields.Char(string='Subject', required=True, tracking=True, compute='_compute_subject', store=True, readonly=False)

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

    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                order_type = vals.get('order_type', 'other')
                sequence_code = f'hr.order.{order_type}'
                vals['name'] = self.env['ir.sequence'].next_by_code(sequence_code) or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

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
