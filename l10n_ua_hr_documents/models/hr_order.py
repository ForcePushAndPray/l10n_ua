from odoo import models, fields, api


class HrOrder(models.Model):
    _name = 'hr.order'
    _description = 'HR Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, number desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    number = fields.Char(
        string='Number',
        required=True,
        default='New',
        tracking=True
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    
    order_type_id = fields.Many2one(
        'hr.order.type',
        string='Order Type',
        required=True,
        tracking=True
    )
    category = fields.Selection(
        related='order_type_id.category',
        store=True
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        tracking=True
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        help='For group orders'
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contract'
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department'
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position'
    )
    
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    
    # For hiring orders
    hire_date = fields.Date(string='Hire Date')
    probation_days = fields.Integer(string='Probation Days')
    wage = fields.Float(string='Wage')
    
    # For termination orders
    termination_date = fields.Date(string='Termination Date')
    termination_reason_id = fields.Many2one(
        'hr.termination.reason',
        string='Termination Reason'
    )
    
    # For transfer orders
    new_department_id = fields.Many2one(
        'hr.department',
        string='New Department'
    )
    new_job_id = fields.Many2one(
        'hr.job',
        string='New Job Position'
    )
    new_wage = fields.Float(string='New Wage')
    
    # For bonus orders
    bonus_amount = fields.Float(string='Bonus Amount')
    bonus_reason = fields.Char(string='Bonus Reason')
    
    body = fields.Html(string='Order Body')
    basis = fields.Char(string='Basis')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('signed', 'Signed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    signed_by = fields.Many2one(
        'res.users',
        string='Signed By'
    )
    signed_date = fields.Date(string='Signed Date')
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    notes = fields.Text(string='Notes')

    @api.depends('number', 'date', 'order_type_id')
    def _compute_name(self):
        for order in self:
            if order.order_type_id and order.number:
                order.name = f'{order.order_type_id.name} № {order.number} від {order.date}'
            else:
                order.name = order.number or 'New'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('number', 'New') == 'New':
                order_type = self.env['hr.order.type'].browse(vals.get('order_type_id'))
                if order_type and order_type.sequence_id:
                    vals['number'] = order_type.sequence_id.next_by_id()
                else:
                    vals['number'] = self.env['ir.sequence'].next_by_code('hr.order') or 'New'
        return super().create(vals_list)

    @api.onchange('order_type_id')
    def _onchange_order_type(self):
        if self.order_type_id and self.order_type_id.template_body:
            self.body = self.order_type_id.template_body

    @api.onchange('employee_id')
    def _onchange_employee(self):
        if self.employee_id:
            self.department_id = self.employee_id.department_id
            self.job_id = self.employee_id.job_id
            # Get active contract
            contracts = self.employee_id.contract_ids.filtered(lambda c: c.state == 'open')
            if contracts:
                self.contract_id = contracts[0]
                self.wage = contracts[0].wage

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_sign(self):
        self.write({
            'state': 'signed',
            'signed_by': self.env.uid,
            'signed_date': fields.Date.today(),
        })

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        return self.env.ref('l10n_ua_hr_documents.action_report_hr_order').report_action(self)
