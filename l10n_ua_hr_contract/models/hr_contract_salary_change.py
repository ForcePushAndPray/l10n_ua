from odoo import models, fields, api
from odoo.exceptions import UserError


class HrContractSalaryChange(models.Model):
    _name = 'hr.contract.salary.change'
    _description = 'Contract Salary Change'
    _order = 'effective_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    contract_id = fields.Many2one(
        'hr.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='contract_id.employee_id',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='contract_id.company_id',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='contract_id.currency_id'
    )

    old_wage = fields.Monetary(
        string='Previous Salary',
        required=True,
        currency_field='currency_id'
    )
    new_wage = fields.Monetary(
        string='New Salary',
        required=True,
        currency_field='currency_id'
    )
    change_amount = fields.Monetary(
        string='Change Amount',
        compute='_compute_change_amount',
        store=True,
        currency_field='currency_id'
    )
    change_percent = fields.Float(
        string='Change %',
        compute='_compute_change_amount',
        store=True
    )

    effective_date = fields.Date(
        string='Effective Date',
        required=True,
        tracking=True
    )
    reason = fields.Text(string='Reason for Change')

    # Order references
    order_number = fields.Char(string='Order Number', tracking=True)
    order_date = fields.Date(string='Order Date')
    order_id = fields.Many2one(
        'hr.order',
        string='Related Order',
        help='HR Order document for this salary change'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    notes = fields.Text(string='Notes')

    @api.depends('old_wage', 'new_wage')
    def _compute_change_amount(self):
        for record in self:
            record.change_amount = record.new_wage - record.old_wage
            if record.old_wage:
                record.change_percent = ((record.new_wage - record.old_wage) / record.old_wage) * 100
            else:
                record.change_percent = 0

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id:
            self.old_wage = self.contract_id.wage

    def action_confirm(self):
        """Confirm the salary change"""
        for record in self:
            if record.state != 'draft':
                raise UserError('Only draft salary changes can be confirmed.')
            record.state = 'confirmed'

    def action_apply(self):
        """Apply salary change to contract"""
        for record in self:
            if record.state != 'confirmed':
                raise UserError('Only confirmed salary changes can be applied.')
            if record.effective_date > fields.Date.today():
                raise UserError('Cannot apply salary change before its effective date.')

            # Update contract wage
            record.contract_id.wage = record.new_wage
            record.state = 'applied'

    def action_cancel(self):
        """Cancel the salary change"""
        for record in self:
            if record.state == 'applied':
                raise UserError('Cannot cancel an already applied salary change.')
            record.state = 'cancelled'

    def action_draft(self):
        """Reset to draft"""
        for record in self:
            if record.state == 'applied':
                raise UserError('Cannot reset an applied salary change to draft.')
            record.state = 'draft'
