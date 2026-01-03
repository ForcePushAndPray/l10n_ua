from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date
from dateutil.relativedelta import relativedelta


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # === Personal Documents ===
    rnokpp = fields.Char(
        string='RNOKPP (IPN)', size=10,
        help='Registration Number of the Taxpayer Account Card (Individual Tax Number)')
    document_type = fields.Selection([
        ('passport', 'Passport (old format)'),
        ('id_card', 'ID Card'),
        ('other', 'Other'),
    ], string='Document Type', default='id_card')
    passport_series = fields.Char(string='Passport Series', size=2,
                                   help='For old format passports only')
    passport_number = fields.Char(string='Passport/ID Number', size=9)
    passport_issued_by = fields.Char(string='Issued By', size=100)
    passport_issued_date = fields.Date(string='Issue Date')
    passport_valid_until = fields.Date(string='Valid Until',
                                        help='For ID cards only')
    passport_record_number = fields.Char(string='Record Number', size=14,
                                          help='Unique record number in the register (for ID cards)')

    # === Registration Address ===
    registration_address = fields.Text(string='Registration Address')
    registration_region_id = fields.Many2one(
        'res.country.state', string='Registration Region',
        domain="[('country_id.code', '=', 'UA')]")
    registration_city = fields.Char(string='Registration City')
    registration_zip = fields.Char(string='Registration ZIP', size=5)

    # === Actual Address ===
    actual_address = fields.Text(string='Actual Address')
    actual_same_as_registration = fields.Boolean(
        string='Same as Registration',
        help='Actual address is the same as registration address')

    # === Education ===
    education_level_id = fields.Many2one('hr.education.level', string='Education Level')
    education_institution = fields.Char(string='Educational Institution')
    education_specialty = fields.Char(string='Specialty')
    diploma_series = fields.Char(string='Diploma Series')
    diploma_number = fields.Char(string='Diploma Number')
    diploma_date = fields.Date(string='Diploma Date')

    # === Military Accounting ===
    military_status = fields.Selection([
        ('liable', 'Liable for Military Service'),
        ('reserved', 'Reserved'),
        ('exempt', 'Exempt'),
        ('not_applicable', 'Not Applicable'),
    ], string='Military Status', default='not_applicable')
    military_category = fields.Selection([
        ('1', 'Category 1'),
        ('2', 'Category 2'),
        ('removed', 'Removed from Register'),
    ], string='Military Category')
    military_rank_id = fields.Many2one('hr.military.rank', string='Military Rank')
    military_specialty = fields.Char(string='Military Specialty (VOS)',
                                      help='Military Occupational Specialty')
    military_fitness = fields.Selection([
        ('fit', 'Fit for Service'),
        ('limited', 'Limited Fitness'),
        ('unfit', 'Unfit for Service'),
    ], string='Military Fitness')
    military_document_number = fields.Char(string='Military Document Number')
    military_tcc_id = fields.Many2one('hr.military.tcc', string='TCC',
                                       help='Territorial Recruitment Center')
    military_reservation = fields.Boolean(string='Reserved (Booking)')
    military_reservation_until = fields.Date(string='Reserved Until')

    # === Benefits ===
    benefit_ids = fields.Many2many('hr.employee.benefit', string='Benefits')
    disability_group = fields.Selection([
        ('1', 'Group I'),
        ('2', 'Group II'),
        ('3', 'Group III'),
        ('none', 'None'),
    ], string='Disability Group', default='none')
    disability_reason = fields.Char(string='Disability Reason')
    disability_document = fields.Char(string='MSEC Document',
                                       help='Medical-Social Expert Commission document')
    disability_date_from = fields.Date(string='Disability From')
    disability_date_to = fields.Date(string='Disability Until')
    chornobyl_category = fields.Selection([
        ('1', 'Category 1'),
        ('2', 'Category 2'),
        ('3', 'Category 3'),
        ('4', 'Category 4'),
        ('none', 'None'),
    ], string='Chornobyl Category', default='none')
    veteran_status = fields.Selection([
        ('combat', 'Combat Veteran'),
        ('war', 'War Veteran'),
        ('labor', 'Labor Veteran'),
        ('none', 'None'),
    ], string='Veteran Status', default='none')

    # === Family ===
    marital_status_ua = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ], string='Marital Status (UA)')
    spouse_name = fields.Char(string='Spouse Name')
    spouse_rnokpp = fields.Char(string='Spouse RNOKPP', size=10)
    children_ids = fields.One2many('hr.employee.child', 'employee_id', string='Children')
    children_count = fields.Integer(string='Children Count', compute='_compute_children_count', store=True)
    dependents_count = fields.Integer(string='Dependents Count', compute='_compute_dependents_count', store=True,
                                       help='Number of dependents for PSP calculation')

    # === Work Experience & Bank ===
    hire_date = fields.Date(string='Hire Date')
    work_experience_total = fields.Float(string='Total Work Experience (years)',
                                          help='Total work experience in years')
    work_experience_company = fields.Float(string='Company Experience (years)',
                                            compute='_compute_work_experience_company', store=True)
    insurance_experience = fields.Float(string='Insurance Experience (years)',
                                         help='Insurance experience for sick leave calculation')
    bank_account_id = fields.Many2one('res.partner.bank', string='Bank Account',
                                       help='Bank account for salary payment')

    @api.depends('children_ids')
    def _compute_children_count(self):
        for employee in self:
            employee.children_count = len(employee.children_ids)

    @api.depends('children_ids', 'children_ids.is_dependent')
    def _compute_dependents_count(self):
        for employee in self:
            employee.dependents_count = len(employee.children_ids.filtered('is_dependent'))

    @api.depends('hire_date')
    def _compute_work_experience_company(self):
        today = date.today()
        for employee in self:
            if employee.hire_date:
                delta = relativedelta(today, employee.hire_date)
                employee.work_experience_company = delta.years + delta.months / 12.0
            else:
                employee.work_experience_company = 0.0

    @api.onchange('actual_same_as_registration')
    def _onchange_actual_same_as_registration(self):
        if self.actual_same_as_registration:
            self.actual_address = self.registration_address

    @api.constrains('rnokpp')
    def _check_rnokpp(self):
        validate_rnokpp = self.env['ir.config_parameter'].sudo().get_param(
            'hr_ua.validate_rnokpp', 'True')
        if validate_rnokpp.lower() == 'true':
            for employee in self:
                if employee.rnokpp and not self._validate_rnokpp(employee.rnokpp):
                    raise ValidationError('Invalid RNOKPP (IPN) checksum!')

    @staticmethod
    def _validate_rnokpp(rnokpp):
        """Validate Ukrainian RNOKPP (IPN) checksum."""
        if not rnokpp or len(rnokpp) != 10 or not rnokpp.isdigit():
            return False
        weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
        checksum = sum(int(rnokpp[i]) * weights[i] for i in range(9))
        control = (checksum % 11) % 10
        return control == int(rnokpp[9])

    @api.constrains('passport_number', 'document_type')
    def _check_passport_number(self):
        for employee in self:
            if employee.passport_number:
                if employee.document_type == 'passport' and len(employee.passport_number) != 6:
                    raise ValidationError('Old passport number must be 6 digits!')
                if employee.document_type == 'id_card' and len(employee.passport_number) != 9:
                    raise ValidationError('ID card number must be 9 digits!')

    _rnokpp_uniq = models.Constraint(
        'unique(rnokpp)',
        'RNOKPP (IPN) must be unique!',
    )
