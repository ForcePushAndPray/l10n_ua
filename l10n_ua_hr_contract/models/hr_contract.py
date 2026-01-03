from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class HrContract(models.Model):
    _name = 'hr.contract'
    _description = 'Employment Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Contract Reference', 
        required=True, 
        tracking=True,
        default='New'
    )
    employee_id = fields.Many2one(
        'hr.employee', 
        string='Employee', 
        required=True, 
        tracking=True,
        ondelete='cascade'
    )
    department_id = fields.Many2one(
        'hr.department', 
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=False
    )
    job_id = fields.Many2one(
        'hr.job', 
        string='Job Position',
        related='employee_id.job_id',
        store=True,
        readonly=False
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    contract_type_ua = fields.Selection([
        ('permanent', 'Permanent (Indefinite)'),
        ('fixed_term', 'Fixed Term'),
        ('contract', 'Contract'),
        ('civil', 'Civil Law Contract'),
        ('gig', 'Gig Contract (Diia.City)'),
        ('author', 'Author Contract'),
        ('seasonal', 'Seasonal Work'),
        ('temporary', 'Temporary Work'),
    ], string='Contract Type', required=True, default='permanent', tracking=True)
    
    is_main_workplace = fields.Boolean(
        string='Main Workplace', 
        default=True,
        tracking=True
    )
    is_part_time = fields.Boolean(
        string='Part-time Work',
        tracking=True
    )
    part_time_type = fields.Selection([
        ('internal', 'Internal Part-time'),
        ('external', 'External Part-time'),
    ], string='Part-time Type')
    
    work_mode = fields.Selection([
        ('full_time', 'Full-time'),
        ('part_time', 'Part-time'),
        ('flexible', 'Flexible Schedule'),
        ('remote', 'Remote Work'),
        ('hybrid', 'Hybrid'),
    ], string='Work Mode', default='full_time', tracking=True)
    
    working_hours_week = fields.Float(
        string='Hours per Week', 
        default=40.0,
        tracking=True
    )
    work_rate = fields.Float(
        string='Work Rate', 
        default=1.0,
        help='1.0 = full rate, 0.5 = half rate, etc.',
        tracking=True
    )
    
    date_start = fields.Date(
        string='Start Date', 
        required=True,
        tracking=True
    )
    date_end = fields.Date(
        string='End Date',
        tracking=True
    )
    
    probation_period_days = fields.Integer(
        string='Probation Period (days)',
        tracking=True
    )
    probation_end_date = fields.Date(
        string='Probation End Date',
        compute='_compute_probation_end_date',
        store=True
    )
    
    wage = fields.Monetary(
        string='Wage',
        required=True,
        tracking=True,
        help='Monthly gross salary'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    staffing_line_id = fields.Many2one(
        'hr.staffing.table',
        string='Staffing Position',
        tracking=True
    )
    tariff_grade_id = fields.Many2one(
        'hr.tariff.grade',
        string='Tariff Grade',
        tracking=True
    )
    
    work_schedule_id = fields.Many2one(
        'hr.work.schedule',
        string='Work Schedule',
        tracking=True
    )
    
    allowance_ids = fields.One2many(
        'hr.contract.allowance',
        'contract_id',
        string='Allowances'
    )
    total_allowances = fields.Monetary(
        string='Total Allowances',
        compute='_compute_total_allowances',
        store=True
    )
    total_wage = fields.Monetary(
        string='Total Wage',
        compute='_compute_total_wage',
        store=True
    )
    
    termination_reason_id = fields.Many2one(
        'hr.termination.reason',
        string='Termination Reason',
        tracking=True
    )
    termination_date = fields.Date(
        string='Termination Date',
        tracking=True
    )
    
    hire_order_number = fields.Char(string='Hire Order Number')
    hire_order_date = fields.Date(string='Hire Order Date')
    termination_order_number = fields.Char(string='Termination Order Number')
    termination_order_date = fields.Date(string='Termination Order Date')
    
    diia_city_employee = fields.Boolean(
        string='Diia.City Employee',
        help='Employee under Diia.City special tax regime'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Running'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes')

    @api.depends('date_start', 'probation_period_days')
    def _compute_probation_end_date(self):
        for contract in self:
            if contract.date_start and contract.probation_period_days:
                contract.probation_end_date = contract.date_start + relativedelta(days=contract.probation_period_days)
            else:
                contract.probation_end_date = False

    @api.depends('allowance_ids.amount', 'allowance_ids.calculated_amount')
    def _compute_total_allowances(self):
        for contract in self:
            contract.total_allowances = sum(
                a.calculated_amount for a in contract.allowance_ids
            )

    @api.depends('wage', 'total_allowances')
    def _compute_total_wage(self):
        for contract in self:
            contract.total_wage = contract.wage + contract.total_allowances

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_end and contract.date_start > contract.date_end:
                raise ValidationError('Contract start date must be before end date.')

    @api.constrains('work_rate')
    def _check_work_rate(self):
        for contract in self:
            if contract.work_rate <= 0 or contract.work_rate > 2:
                raise ValidationError('Work rate must be between 0 and 2.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.contract') or 'New'
        return super().create(vals_list)

    def action_open(self):
        self.write({'state': 'open'})

    def action_close(self):
        self.write({'state': 'close'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})
