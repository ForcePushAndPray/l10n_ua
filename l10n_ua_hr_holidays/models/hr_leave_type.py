from odoo import models, fields


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    ua_leave_category = fields.Selection([
        ('annual_basic', 'Annual Basic Leave'),
        ('annual_additional', 'Annual Additional Leave'),
        ('educational', 'Educational Leave'),
        ('creative', 'Creative Leave'),
        ('social', 'Social Leave'),
        ('unpaid', 'Unpaid Leave'),
        ('maternity', 'Maternity Leave'),
        ('childcare', 'Childcare Leave'),
        ('other', 'Other'),
    ], string='UA Leave Category')
    
    annual_days = fields.Integer(
        string='Days per Year',
        default=24,
        help='Number of vacation days per year (24 is standard)'
    )
    is_calendar_days = fields.Boolean(
        string='Calendar Days',
        default=True,
        help='If checked, vacation is counted in calendar days'
    )
    is_transferable = fields.Boolean(
        string='Transferable',
        default=True,
        help='Can unused days be transferred to next year'
    )
    max_transfer_days = fields.Integer(
        string='Max Transfer Days',
        help='Maximum days that can be transferred'
    )
    requires_experience = fields.Boolean(
        string='Requires Work Experience',
        help='Requires 6 months of work experience'
    )
    min_experience_months = fields.Integer(
        string='Min Experience (months)',
        default=6
    )
    is_paid = fields.Boolean(
        string='Paid Leave',
        default=True
    )
    payment_source = fields.Selection([
        ('employer', 'Employer'),
        ('fss', 'Social Insurance Fund'),
        ('mixed', 'Mixed'),
    ], string='Payment Source', default='employer')
    
    min_continuous_days = fields.Integer(
        string='Min Continuous Days',
        default=14,
        help='Minimum continuous vacation days (14 for annual)'
    )
    
    accrual_type_id = fields.Many2one(
        'hr.accrual.type',
        string='Accrual Type',
        help='Payroll accrual type for this leave'
    )
