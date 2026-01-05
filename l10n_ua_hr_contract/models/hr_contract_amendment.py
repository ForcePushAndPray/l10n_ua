from odoo import models, fields, api
from odoo.exceptions import UserError


class HrContractAmendment(models.Model):
    _name = 'hr.contract.amendment'
    _description = 'Contract Amendment'
    _order = 'amendment_date desc, id desc'
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

    amendment_number = fields.Char(
        string='Amendment Number',
        tracking=True
    )
    amendment_date = fields.Date(
        string='Amendment Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    effective_date = fields.Date(
        string='Effective Date',
        required=True,
        tracking=True
    )

    amendment_type = fields.Selection([
        ('salary', 'Salary Change'),
        ('position', 'Position Change'),
        ('schedule', 'Schedule Change'),
        ('conditions', 'Work Conditions Change'),
        ('extension', 'Contract Extension'),
        ('other', 'Other'),
    ], string='Amendment Type', required=True, tracking=True)

    description = fields.Text(
        string='Description',
        required=True,
        help='Detailed description of changes made'
    )

    # Snapshot of changed values (JSON format)
    old_values = fields.Text(
        string='Previous Values',
        help='Previous field values before amendment'
    )
    new_values = fields.Text(
        string='New Values',
        help='New field values after amendment'
    )

    # Order references
    order_number = fields.Char(string='Order Number', tracking=True)
    order_date = fields.Date(string='Order Date')
    order_id = fields.Many2one(
        'hr.order',
        string='Related Order',
        help='HR Order document for this amendment'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', tracking=True)

    notes = fields.Text(string='Notes')

    def action_confirm(self):
        """Confirm the amendment"""
        for record in self:
            if record.state != 'draft':
                raise UserError('Only draft amendments can be confirmed.')
            record.state = 'confirmed'

    def action_draft(self):
        """Reset to draft"""
        for record in self:
            record.state = 'draft'

    @api.model
    def create_from_change(self, contract, amendment_type, description, old_vals, new_vals):
        """Helper method to create amendment from contract changes"""
        import json
        return self.create({
            'contract_id': contract.id,
            'amendment_type': amendment_type,
            'description': description,
            'effective_date': fields.Date.today(),
            'old_values': json.dumps(old_vals, default=str, ensure_ascii=False),
            'new_values': json.dumps(new_vals, default=str, ensure_ascii=False),
        })
