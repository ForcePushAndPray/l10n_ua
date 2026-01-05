from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    certificate_ids = fields.One2many(
        'hr.certificate',
        'employee_id',
        string='Certificates'
    )
    certificates_count = fields.Integer(
        string='Certificates Count',
        compute='_compute_certificates_count'
    )

    def _compute_certificates_count(self):
        for employee in self:
            employee.certificates_count = len(employee.certificate_ids)

    def action_open_certificates(self):
        """Open certificates for this employee"""
        self.ensure_one()
        return {
            'name': 'Certificates',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.certificate',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
