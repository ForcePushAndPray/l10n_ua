from odoo import _, api, models, fields
from odoo.exceptions import ValidationError


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    koatuu_code = fields.Char(
        string='KOATUU Code', size=10,
        help='Code of the Classification of Administrative-Territorial Units of Ukraine')
    department_type = fields.Selection([
        ('head', 'Head Office'),
        ('branch', 'Branch'),
        ('representative', 'Representative Office'),
    ], string='Department Type', default='head')
    is_separate_unit = fields.Boolean(
        string='Separate Unit',
        help='Is a separate structural unit (for PFU reporting)')
    edrpou = fields.Char(
        string='EDRPOU', size=8,
        help='EDRPOU code if the branch is a separate legal entity')
    head_employee_id = fields.Many2one(
        'hr.employee', string='Department Head',
        domain="[('company_id', 'in', company_id and [company_id] or allowed_company_ids)]",
        help='Head of the department')

    @api.constrains('company_id', 'head_employee_id')
    def _check_head_employee_company(self):
        # Not check_company=True: an employee always has a company, so a
        # department without one could then have no head at all.
        for department in self:
            head = department.head_employee_id
            if department.company_id and head and head.company_id != department.company_id:
                raise ValidationError(_(
                    "The head of department %(department)s must belong to its "
                    "company %(company)s, but %(employee)s belongs to %(other)s.",
                    department=department.display_name,
                    company=department.company_id.name,
                    employee=head.name,
                    other=head.company_id.name,
                ))
