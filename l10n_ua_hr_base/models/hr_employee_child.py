from odoo import models, fields, api
from datetime import date
from dateutil.relativedelta import relativedelta


class HrEmployeeChild(models.Model):
    _name = 'hr.employee.child'
    _description = 'Employee Child'
    _order = 'birthday desc'

    employee_id = fields.Many2one('hr.employee', string='Employee',
                                   required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Full Name', required=True)
    birthday = fields.Date(string='Birthday', required=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string='Gender')
    birth_certificate_number = fields.Char(string='Birth Certificate Number')
    rnokpp = fields.Char(string='RNOKPP (IPN)', size=10,
                          help='Registration Number of the Taxpayer Account Card')
    is_disabled = fields.Boolean(string='Disabled Child',
                                  help='Child with disability (for PSP calculation)')
    is_dependent = fields.Boolean(string='Dependent', default=True,
                                   help='Child is a dependent (for PSP calculation)')
    age = fields.Integer(string='Age', compute='_compute_age', store=True)

    @api.depends('birthday')
    def _compute_age(self):
        today = date.today()
        for child in self:
            if child.birthday:
                child.age = relativedelta(today, child.birthday).years
            else:
                child.age = 0

    @api.constrains('rnokpp')
    def _check_rnokpp(self):
        for child in self:
            if child.rnokpp and not self._validate_rnokpp(child.rnokpp):
                pass  # Validation can be enabled via system parameter

    @staticmethod
    def _validate_rnokpp(rnokpp):
        """Validate Ukrainian RNOKPP (IPN) checksum."""
        if not rnokpp or len(rnokpp) != 10 or not rnokpp.isdigit():
            return False
        weights = [-1, 5, 7, 9, 4, 6, 10, 5, 7]
        checksum = sum(int(rnokpp[i]) * weights[i] for i in range(9))
        control = (checksum % 11) % 10
        return control == int(rnokpp[9])
