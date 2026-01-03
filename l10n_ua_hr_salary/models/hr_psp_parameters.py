from odoo import models, fields, api


class HrPspParameters(models.Model):
    _name = 'hr.psp.parameters'
    _description = 'PSP Parameters'
    _order = 'year desc, date_from desc'
    _rec_name = 'display_name'

    year = fields.Integer(string='Year', required=True)
    date_from = fields.Date(string='Date From', required=True)
    date_to = fields.Date(string='Date To')
    
    subsistence_minimum = fields.Float(
        string='Subsistence Minimum',
        required=True,
        help='Прожитковий мінімум для працездатних осіб'
    )
    min_wage = fields.Float(
        string='Minimum Wage',
        required=True,
        help='Мінімальна заробітна плата'
    )
    
    psp_standard = fields.Float(
        string='PSP Standard (50%)',
        compute='_compute_psp_amounts',
        store=True,
        help='Податкова соціальна пільга 50% ПМ'
    )
    psp_150 = fields.Float(
        string='PSP 150%',
        compute='_compute_psp_amounts',
        store=True,
        help='Податкова соціальна пільга 150% (75% ПМ)'
    )
    psp_200 = fields.Float(
        string='PSP 200%',
        compute='_compute_psp_amounts',
        store=True,
        help='Податкова соціальна пільга 200% (100% ПМ)'
    )
    income_limit = fields.Float(
        string='Income Limit for PSP',
        compute='_compute_income_limit',
        store=True,
        help='Граничний дохід для застосування ПСП'
    )
    
    max_esv_base = fields.Float(
        string='Max ESV Base',
        compute='_compute_max_esv_base',
        store=True,
        help='Максимальна база нарахування ЄСВ (15 мін. зарплат)'
    )
    
    pdfo_rate = fields.Float(
        string='PDFO Rate (%)',
        default=18.0,
        help='Ставка податку на доходи фізичних осіб'
    )
    military_tax_rate = fields.Float(
        string='Military Tax Rate (%)',
        default=5.0,
        help='Ставка військового збору'
    )
    esv_rate = fields.Float(
        string='ESV Rate (%)',
        default=22.0,
        help='Ставка єдиного соціального внеску'
    )
    
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    display_name = fields.Char(
        string='Name',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('subsistence_minimum')
    def _compute_psp_amounts(self):
        for rec in self:
            rec.psp_standard = rec.subsistence_minimum * 0.5
            rec.psp_150 = rec.subsistence_minimum * 0.75
            rec.psp_200 = rec.subsistence_minimum

    @api.depends('subsistence_minimum')
    def _compute_income_limit(self):
        for rec in self:
            rec.income_limit = rec.subsistence_minimum * 1.4 * 10

    @api.depends('min_wage')
    def _compute_max_esv_base(self):
        for rec in self:
            rec.max_esv_base = rec.min_wage * 15

    @api.depends('year', 'date_from')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.year} ({rec.date_from})'

    @api.model
    def get_parameters(self, date=None, company_id=None):
        """Get PSP parameters for given date and company"""
        if date is None:
            date = fields.Date.today()
        if company_id is None:
            company_id = self.env.company.id
        
        params = self.search([
            ('date_from', '<=', date),
            '|', ('date_to', '>=', date), ('date_to', '=', False),
            '|', ('company_id', '=', company_id), ('company_id', '=', False),
            ('active', '=', True),
        ], order='date_from desc', limit=1)
        
        return params or self.browse()

    _unique_year_date_from_company_id = models.Constraint(
        'unique(year, date_from, company_id)',
        'Parameters for this period already exist!',
    )
