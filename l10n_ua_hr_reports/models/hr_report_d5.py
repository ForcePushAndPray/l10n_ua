from odoo import models, fields, api


class HrReportD5(models.Model):
    _name = 'hr.report.d5'
    _description = 'D5 ESV Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
        tracking=True
    )
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', required=True, tracking=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    line_ids = fields.One2many(
        'hr.report.d5.line',
        'report_id',
        string='Report Lines (D1)'
    )
    
    total_employees = fields.Integer(
        string='Total Employees',
        compute='_compute_totals',
        store=True
    )
    total_esv_base = fields.Float(
        string='Total ESV Base',
        compute='_compute_totals',
        store=True
    )
    total_esv = fields.Float(
        string='Total ESV',
        compute='_compute_totals',
        store=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('submitted', 'Submitted'),
    ], string='Status', default='draft', tracking=True)
    
    submission_date = fields.Date(string='Submission Date')
    notes = fields.Text(string='Notes')

    @api.depends('year', 'month')
    def _compute_name(self):
        month_names = dict(self._fields['month'].selection)
        for rec in self:
            rec.name = f'Д5 {month_names.get(rec.month, "")} {rec.year}'

    @api.depends('line_ids.esv_base', 'line_ids.esv_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_employees = len(rec.line_ids)
            rec.total_esv_base = sum(rec.line_ids.mapped('esv_base'))
            rec.total_esv = sum(rec.line_ids.mapped('esv_amount'))

    def action_generate(self):
        """Generate report lines from payslips"""
        self.ensure_one()
        self.line_ids.unlink()
        
        month = int(self.month)
        date_from = fields.Date.from_string(f'{self.year}-{month:02d}-01')
        
        if month == 12:
            date_to = fields.Date.from_string(f'{self.year + 1}-01-01')
        else:
            date_to = fields.Date.from_string(f'{self.year}-{month + 1:02d}-01')
        
        payslips = self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<', date_to),
            ('state', '=', 'done'),
        ])
        
        for slip in payslips:
            employee = slip.employee_id
            contract = slip.contract_id
            
            self.env['hr.report.d5.line'].create({
                'report_id': self.id,
                'employee_id': employee.id,
                'rnokpp': employee.rnokpp or '',
                'last_name': employee.name.split()[0] if employee.name else '',
                'first_name': employee.name.split()[1] if employee.name and len(employee.name.split()) > 1 else '',
                'middle_name': employee.name.split()[2] if employee.name and len(employee.name.split()) > 2 else '',
                'category': '1',
                'esv_base': slip.esv_base,
                'esv_amount': slip.esv_amount,
                'worked_days': slip.worked_days,
                'worked_hours': slip.worked_hours,
            })
        
        self.write({'state': 'generated'})
        return True

    def action_submit(self):
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.today(),
        })

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_export_xml(self):
        """Export report to XML format for submission"""
        # TODO: Implement XML export
        pass

    _unique_year_month_company_id = models.Constraint(
        'unique(year, month, company_id)',
        'D5 report for this period already exists!',
    )


class HrReportD5Line(models.Model):
    _name = 'hr.report.d5.line'
    _description = 'D5 Report Line (D1 Appendix)'
    _order = 'employee_id'

    report_id = fields.Many2one(
        'hr.report.d5',
        string='Report',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )
    
    rnokpp = fields.Char(string='RNOKPP', required=True)
    last_name = fields.Char(string='Last Name')
    first_name = fields.Char(string='First Name')
    middle_name = fields.Char(string='Middle Name')
    
    category = fields.Selection([
        ('1', '1 - Employee'),
        ('2', '2 - Civil Contract'),
        ('3', '3 - Disabled'),
        ('4', '4 - Maternity'),
    ], string='Category', default='1')
    
    esv_base = fields.Float(string='ESV Base')
    esv_amount = fields.Float(string='ESV Amount')
    
    worked_days = fields.Integer(string='Worked Days')
    worked_hours = fields.Float(string='Worked Hours')
    
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    termination_reason = fields.Char(string='Termination Reason')
    
    notes = fields.Char(string='Notes')
