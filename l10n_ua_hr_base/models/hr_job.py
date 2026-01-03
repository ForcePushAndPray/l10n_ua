from odoo import models, fields, api


class HrJob(models.Model):
    _inherit = 'hr.job'

    kp_code = fields.Char(
        string='KP Code', size=10,
        help='Code from Classifier of Professions (KP 2010)')
    kp_name = fields.Char(
        string='KP Name',
        help='Name according to Classifier of Professions')
    kp_id = fields.Many2one(
        'hr.kp2010', string='Profession (KP)',
        help='Profession from Classifier of Professions 2010')
    work_conditions = fields.Selection([
        ('normal', 'Normal'),
        ('hazardous', 'Hazardous'),
        ('heavy', 'Heavy'),
    ], string='Work Conditions', default='normal')
    hazard_class = fields.Selection([
        ('1', 'Class 1 (Optimal)'),
        ('2', 'Class 2 (Acceptable)'),
        ('3.1', 'Class 3.1 (Harmful)'),
        ('3.2', 'Class 3.2 (Harmful)'),
        ('3.3', 'Class 3.3 (Harmful)'),
        ('3.4', 'Class 3.4 (Harmful)'),
        ('4', 'Class 4 (Dangerous)'),
    ], string='Hazard Class')
    tariff_grade_id = fields.Many2one(
        'hr.tariff.grade', string='Tariff Grade')
    min_salary = fields.Monetary(
        string='Minimum Salary', currency_field='currency_id',
        help='Minimum salary for this position')
    max_salary = fields.Monetary(
        string='Maximum Salary', currency_field='currency_id',
        help='Maximum salary for this position')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    probation_days = fields.Integer(
        string='Probation Period (days)',
        help='Default probation period in days')

    @api.onchange('kp_id')
    def _onchange_kp_id(self):
        if self.kp_id:
            self.kp_code = self.kp_id.code
            self.kp_name = self.kp_id.name
            if self.kp_id.work_conditions:
                self.work_conditions = self.kp_id.work_conditions
