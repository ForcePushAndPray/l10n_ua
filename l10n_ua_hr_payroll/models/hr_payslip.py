from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
import calendar


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _description = 'Payslip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, employee_id'

    name = fields.Char(
        string='Reference',
        required=True,
        default='New',
        tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contract',
        compute='_compute_contract_id',
        store=True,
        readonly=False
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        related='employee_id.job_id',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id'
    )
    
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Payslip Batch'
    )
    
    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        tracking=True
    )
    
    # Employee data (snapshot)
    rnokpp = fields.Char(
        string='RNOKPP',
        related='employee_id.rnokpp'
    )
    
    # Working time
    scheduled_days = fields.Integer(
        string='Scheduled Days',
        help='Working days in period according to calendar'
    )
    scheduled_hours = fields.Float(
        string='Scheduled Hours'
    )
    worked_days = fields.Integer(
        string='Worked Days',
        default=0
    )
    worked_hours = fields.Float(
        string='Worked Hours',
        default=0.0
    )
    
    # Accruals
    accrual_ids = fields.One2many(
        'hr.payslip.accrual',
        'payslip_id',
        string='Accruals'
    )
    gross_salary = fields.Monetary(
        string='Gross Salary',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # PSP (Tax Social Benefit)
    psp_eligible = fields.Boolean(
        string='PSP Eligible',
        compute='_compute_psp',
        store=True
    )
    psp_type = fields.Selection([
        ('none', 'None'),
        ('standard', 'Standard (50%)'),
        ('150', '150%'),
        ('200', '200%'),
    ], string='PSP Type', default='none')
    psp_amount = fields.Monetary(
        string='PSP Amount',
        compute='_compute_psp',
        store=True,
        currency_field='currency_id'
    )
    
    # Taxes
    pdfo_base = fields.Monetary(
        string='PDFO Base',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    pdfo_rate = fields.Float(
        string='PDFO Rate (%)',
        default=18.0
    )
    pdfo_amount = fields.Monetary(
        string='PDFO Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    military_tax_base = fields.Monetary(
        string='Military Tax Base',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    military_tax_rate = fields.Float(
        string='Military Tax Rate (%)',
        default=5.0
    )
    military_tax_amount = fields.Monetary(
        string='Military Tax Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # ESV (employer)
    esv_base = fields.Monetary(
        string='ESV Base',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    esv_rate = fields.Float(
        string='ESV Rate (%)',
        default=22.0
    )
    esv_amount = fields.Monetary(
        string='ESV Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # Deductions
    deduction_ids = fields.One2many(
        'hr.payslip.deduction',
        'payslip_id',
        string='Deductions'
    )
    total_deductions = fields.Monetary(
        string='Total Deductions',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    other_deductions = fields.Monetary(
        string='Other Deductions',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # Net
    net_salary = fields.Monetary(
        string='Net Salary',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes')

    @api.depends('employee_id', 'date_from')
    def _compute_contract_id(self):
        for payslip in self:
            if payslip.employee_id:
                contracts = payslip.employee_id.contract_ids.filtered(
                    lambda c: c.state == 'open' and 
                    c.date_start <= (payslip.date_from or fields.Date.today()) and
                    (not c.date_end or c.date_end >= (payslip.date_from or fields.Date.today()))
                )
                payslip.contract_id = contracts[0] if contracts else False
            else:
                payslip.contract_id = False

    @api.depends('gross_salary', 'psp_type')
    def _compute_psp(self):
        for payslip in self:
            params = self.env['hr.psp.parameters'].get_parameters(payslip.date_to)
            if not params:
                payslip.psp_eligible = False
                payslip.psp_amount = 0.0
                continue
            
            payslip.psp_eligible = payslip.gross_salary <= params.income_limit
            
            if payslip.psp_eligible and payslip.psp_type != 'none':
                if payslip.psp_type == 'standard':
                    payslip.psp_amount = params.psp_standard
                elif payslip.psp_type == '150':
                    payslip.psp_amount = params.psp_150
                elif payslip.psp_type == '200':
                    payslip.psp_amount = params.psp_200
                else:
                    payslip.psp_amount = 0.0
            else:
                payslip.psp_amount = 0.0

    @api.depends(
        'accrual_ids.amount',
        'deduction_ids.amount',
        'psp_amount',
        'pdfo_rate',
        'military_tax_rate',
        'esv_rate'
    )
    def _compute_amounts(self):
        for payslip in self:
            # Gross salary
            gross = sum(a.amount for a in payslip.accrual_ids)
            payslip.gross_salary = gross
            
            # PDFO base and amount
            pdfo_taxable = sum(
                a.amount for a in payslip.accrual_ids 
                if a.is_taxable_pdfo
            )
            payslip.pdfo_base = max(0, pdfo_taxable - payslip.psp_amount)
            payslip.pdfo_amount = round(payslip.pdfo_base * payslip.pdfo_rate / 100, 2)
            
            # Military tax
            military_taxable = sum(
                a.amount for a in payslip.accrual_ids 
                if a.is_military_tax
            )
            payslip.military_tax_base = military_taxable
            payslip.military_tax_amount = round(military_taxable * payslip.military_tax_rate / 100, 2)
            
            # ESV (employer contribution)
            params = self.env['hr.psp.parameters'].get_parameters(payslip.date_to)
            esv_taxable = sum(
                a.amount for a in payslip.accrual_ids 
                if a.is_esv_base
            )
            min_esv_base = params.min_wage if params else 8000
            max_esv_base = params.max_esv_base if params else 120000
            
            payslip.esv_base = min(max(esv_taxable, min_esv_base), max_esv_base)
            payslip.esv_amount = round(payslip.esv_base * payslip.esv_rate / 100, 2)
            
            # Other deductions (excluding taxes)
            other_ded = sum(
                d.amount for d in payslip.deduction_ids 
                if d.deduction_type_id.category not in ('tax',)
            )
            payslip.other_deductions = other_ded
            
            # Total deductions
            payslip.total_deductions = (
                payslip.pdfo_amount + 
                payslip.military_tax_amount + 
                payslip.other_deductions
            )
            
            # Net salary
            payslip.net_salary = gross - payslip.total_deductions

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.payslip') or 'New'
        return super().create(vals_list)

    def action_compute_sheet(self):
        """Compute payslip amounts"""
        for payslip in self:
            if payslip.state != 'draft':
                continue
            
            payslip._compute_working_days()
            payslip._generate_accruals()
            payslip._generate_deductions()
        
        return True

    def _compute_working_days(self):
        """Calculate scheduled and worked days"""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return
        
        # Simple calculation - count weekdays
        current = self.date_from
        scheduled = 0
        while current <= self.date_to:
            if current.weekday() < 5:  # Monday to Friday
                scheduled += 1
            current += relativedelta(days=1)
        
        self.scheduled_days = scheduled
        self.scheduled_hours = scheduled * 8.0
        
        # Default: all scheduled days worked
        if not self.worked_days:
            self.worked_days = scheduled
            self.worked_hours = scheduled * 8.0

    def _generate_accruals(self):
        """Generate accrual lines based on contract"""
        self.ensure_one()
        self.accrual_ids.unlink()
        
        if not self.contract_id:
            return
        
        contract = self.contract_id
        
        # Base salary
        salary_type = self.env['hr.accrual.type'].search([('code', '=', 'SALARY')], limit=1)
        if salary_type and contract.wage:
            # Prorate salary based on worked days
            if self.scheduled_days > 0:
                amount = contract.wage * self.worked_days / self.scheduled_days
            else:
                amount = contract.wage
            
            self.env['hr.payslip.accrual'].create({
                'payslip_id': self.id,
                'accrual_type_id': salary_type.id,
                'quantity': self.worked_days,
                'rate': contract.wage / self.scheduled_days if self.scheduled_days else 0,
                'amount': round(amount, 2),
            })
        
        # Contract allowances
        allowance_type = self.env['hr.accrual.type'].search([('code', '=', 'ALLOWANCE')], limit=1)
        if allowance_type:
            for allowance in contract.allowance_ids.filtered('is_active'):
                self.env['hr.payslip.accrual'].create({
                    'payslip_id': self.id,
                    'accrual_type_id': allowance_type.id,
                    'quantity': 1,
                    'amount': allowance.calculated_amount,
                    'notes': allowance.allowance_type_id.name,
                })

    def _generate_deductions(self):
        """Generate deduction lines"""
        self.ensure_one()
        self.deduction_ids.unlink()
        
        # Execution documents
        exec_docs = self.env['hr.execution.document'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'active'),
            ('date_from', '<=', self.date_to),
            '|', ('date_to', '>=', self.date_from), ('date_to', '=', False),
        ])
        
        alimony_type = self.env['hr.deduction.type'].search([('code', '=', 'ALIMONY')], limit=1)
        
        for doc in exec_docs:
            if doc.calculation_method == 'percent':
                amount = self.gross_salary * doc.percent_value / 100
            elif doc.calculation_method == 'fixed':
                amount = doc.fixed_amount
            else:
                params = self.env['hr.psp.parameters'].get_parameters(self.date_to)
                min_wage = params.min_wage if params else 8000
                amount = min_wage * doc.percent_value / 100
            
            self.env['hr.payslip.deduction'].create({
                'payslip_id': self.id,
                'deduction_type_id': alimony_type.id if alimony_type else False,
                'base_amount': self.gross_salary,
                'rate': doc.percent_value if doc.calculation_method == 'percent' else 0,
                'amount': round(amount, 2),
                'execution_doc_id': doc.id,
            })

    def action_payslip_verify(self):
        self.write({'state': 'verify'})

    def action_payslip_done(self):
        self.write({'state': 'done'})

    def action_payslip_cancel(self):
        self.write({'state': 'cancel'})

    def action_payslip_draft(self):
        self.write({'state': 'draft'})

    def action_print_payslip(self):
        return self.env.ref('l10n_ua_hr_payroll.action_report_payslip').report_action(self)
