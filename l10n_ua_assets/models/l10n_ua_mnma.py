from odoo import api, fields, models


class L10nUaMnma(models.Model):
    _name = 'l10n_ua.mnma'
    _description = 'Low-Value Non-Current Tangible Assets (MNMA)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    inventory_number = fields.Char(
        string='Inventory Number',
        tracking=True,
    )
    date = fields.Date(
        string='Acquisition Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    commission_date = fields.Date(
        string='Commissioning Date',
        tracking=True,
    )
    original_value = fields.Monetary(
        string='Original Value',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    write_off_method = fields.Selection(
        selection=[
            ('50_50', '50/50 (50% on commissioning, 50% on write-off)'),
            ('100', '100% on commissioning'),
        ],
        string='Write-off Method',
        default='50_50',
        required=True,
        tracking=True,
    )
    depreciation_value = fields.Monetary(
        string='Depreciation',
        compute='_compute_depreciation',
        store=True,
        currency_field='currency_id',
    )
    residual_value = fields.Monetary(
        string='Residual Value',
        compute='_compute_depreciation',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_use', 'In Use'),
            ('written_off', 'Written Off'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
    )
    location = fields.Char(
        string='Location',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.depends('original_value', 'write_off_method', 'state')
    def _compute_depreciation(self):
        for record in self:
            if record.state == 'draft':
                record.depreciation_value = 0
                record.residual_value = record.original_value
            elif record.state == 'in_use':
                if record.write_off_method == '100':
                    record.depreciation_value = record.original_value
                    record.residual_value = 0
                else:
                    record.depreciation_value = record.original_value / 2
                    record.residual_value = record.original_value / 2
            else:
                record.depreciation_value = record.original_value
                record.residual_value = 0

    def action_commission(self):
        self.write({
            'state': 'in_use',
            'commission_date': fields.Date.context_today(self),
        })

    def action_write_off(self):
        self.write({'state': 'written_off'})

    def action_draft(self):
        self.write({
            'state': 'draft',
            'commission_date': False,
        })
