from odoo import models, fields, api


class HrContractAllowance(models.Model):
    _name = 'hr.contract.allowance'
    _description = 'Contract Allowance'
    _order = 'sequence, id'

    contract_id = fields.Many2one(
        'hr.contract',
        string='Contract',
        required=True,
        ondelete='cascade'
    )
    allowance_type_id = fields.Many2one(
        'hr.allowance.type',
        string='Allowance Type',
        required=True
    )
    sequence = fields.Integer(
        string='Sequence',
        related='allowance_type_id.sequence',
        store=True
    )
    
    calculation_method = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('percent_salary', 'Percent of Salary'),
        ('percent_min_wage', 'Percent of Minimum Wage'),
    ], string='Calculation Method', required=True, default='fixed')
    
    amount = fields.Float(string='Amount', help='Fixed amount if calculation method is fixed')
    percent = fields.Float(string='Percent', help='Percentage if calculation method is percent')
    
    calculated_amount = fields.Monetary(
        string='Calculated Amount',
        compute='_compute_calculated_amount',
        store=True,
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='contract_id.currency_id'
    )
    
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    
    is_active = fields.Boolean(
        string='Active',
        compute='_compute_is_active',
        store=True
    )
    
    notes = fields.Text(string='Notes')

    def _get_minimum_wage(self):
        """Get current minimum wage from PSP parameters or fallback to default"""
        # Try to get from hr.psp.parameters (l10n_ua_hr_salary module)
        if 'hr.psp.parameters' in self.env:
            current_year = fields.Date.today().year
            psp_params = self.env['hr.psp.parameters'].search([
                ('year', '=', current_year)
            ], limit=1)
            if psp_params:
                return psp_params.min_wage
        # Fallback to system parameter
        param = self.env['ir.config_parameter'].sudo().get_param(
            'l10n_ua_hr.minimum_wage', '8000'
        )
        return float(param)

    @api.depends('calculation_method', 'amount', 'percent', 'contract_id.wage')
    def _compute_calculated_amount(self):
        min_wage = self._get_minimum_wage()
        for allowance in self:
            if allowance.calculation_method == 'fixed':
                allowance.calculated_amount = allowance.amount
            elif allowance.calculation_method == 'percent_salary':
                allowance.calculated_amount = (allowance.contract_id.wage or 0) * (allowance.percent or 0) / 100
            elif allowance.calculation_method == 'percent_min_wage':
                allowance.calculated_amount = min_wage * (allowance.percent or 0) / 100
            else:
                allowance.calculated_amount = 0

    @api.depends('date_from', 'date_to')
    def _compute_is_active(self):
        today = fields.Date.today()
        for allowance in self:
            date_from_ok = not allowance.date_from or allowance.date_from <= today
            date_to_ok = not allowance.date_to or allowance.date_to >= today
            allowance.is_active = date_from_ok and date_to_ok
