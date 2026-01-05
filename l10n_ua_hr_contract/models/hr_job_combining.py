from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class HrJobCombining(models.Model):
    _name = 'hr.job.combining'
    _description = 'Job Combining'
    _order = 'date_from desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )
    main_contract_id = fields.Many2one(
        'hr.contract',
        string='Main Contract',
        required=True,
        tracking=True,
        domain="[('employee_id', '=', employee_id), ('state', '=', 'open')]"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='main_contract_id.company_id',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='main_contract_id.currency_id'
    )

    combined_job_id = fields.Many2one(
        'hr.job',
        string='Combined Position',
        required=True,
        tracking=True
    )
    combined_department_id = fields.Many2one(
        'hr.department',
        string='Combined Department',
        tracking=True
    )

    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True
    )
    date_to = fields.Date(
        string='Date To',
        tracking=True
    )

    # Compensation
    surcharge_type = fields.Selection([
        ('percent', 'Percent of Salary'),
        ('fixed', 'Fixed Amount'),
    ], string='Surcharge Type', default='percent', required=True)

    surcharge_percent = fields.Float(
        string='Surcharge %',
        default=50.0,
        help='Percentage of main salary as surcharge'
    )
    surcharge_amount = fields.Monetary(
        string='Surcharge Amount',
        currency_field='currency_id',
        help='Fixed surcharge amount'
    )
    calculated_surcharge = fields.Monetary(
        string='Calculated Surcharge',
        compute='_compute_calculated_surcharge',
        store=True,
        currency_field='currency_id'
    )

    # Order references
    order_number = fields.Char(string='Order Number', tracking=True)
    order_date = fields.Date(string='Order Date')
    cancellation_order_number = fields.Char(string='Cancellation Order')
    cancellation_order_date = fields.Date(string='Cancellation Order Date')

    # Related allowance
    allowance_id = fields.Many2one(
        'hr.contract.allowance',
        string='Contract Allowance',
        help='Automatically created allowance for this job combining'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    notes = fields.Text(string='Notes')

    @api.depends('surcharge_type', 'surcharge_percent', 'surcharge_amount', 'main_contract_id.wage')
    def _compute_calculated_surcharge(self):
        for record in self:
            if record.surcharge_type == 'percent':
                record.calculated_surcharge = (record.main_contract_id.wage or 0) * (record.surcharge_percent or 0) / 100
            else:
                record.calculated_surcharge = record.surcharge_amount or 0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError('End date must be after start date!')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            # Find active contract
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'open')
            ], limit=1)
            if contract:
                self.main_contract_id = contract.id

    def action_activate(self):
        """Activate job combining and create allowance"""
        for record in self:
            if record.state != 'draft':
                raise UserError('Only draft job combining can be activated.')

            # Create allowance on main contract
            combining_type = self.env['hr.allowance.type'].search([
                ('code', '=', 'COMBINING')
            ], limit=1)

            if combining_type:
                allowance_vals = {
                    'contract_id': record.main_contract_id.id,
                    'allowance_type_id': combining_type.id,
                    'calculation_method': 'percent_salary' if record.surcharge_type == 'percent' else 'fixed',
                    'percent': record.surcharge_percent if record.surcharge_type == 'percent' else 0,
                    'amount': record.surcharge_amount if record.surcharge_type == 'fixed' else 0,
                    'date_from': record.date_from,
                    'date_to': record.date_to,
                    'notes': f'Job combining: {record.combined_job_id.name}',
                }
                allowance = self.env['hr.contract.allowance'].create(allowance_vals)
                record.allowance_id = allowance.id

            record.state = 'active'

    def action_cancel(self):
        """Cancel job combining and deactivate allowance"""
        for record in self:
            if record.state != 'active':
                raise UserError('Only active job combining can be cancelled.')

            # Deactivate related allowance by setting end date
            if record.allowance_id:
                record.allowance_id.date_to = fields.Date.today()

            record.state = 'cancelled'

    def action_draft(self):
        """Reset to draft"""
        for record in self:
            if record.state == 'active':
                raise UserError('Cannot reset an active job combining to draft. Cancel it first.')
            record.state = 'draft'
