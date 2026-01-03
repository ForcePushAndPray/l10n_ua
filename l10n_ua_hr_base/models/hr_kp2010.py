from odoo import models, fields


class HrKp2010(models.Model):
    _name = 'hr.kp2010'
    _description = 'Classifier of Professions (KP 2010)'
    _order = 'code'
    _rec_name = 'display_name'

    code = fields.Char(string='Code', required=True, index=True)
    name = fields.Char(string='Name', required=True, translate=True)
    group_code = fields.Char(string='Group Code', size=1,
                              help='Major group code (1-9)')
    section_code = fields.Char(string='Section Code', size=2)
    work_conditions = fields.Selection([
        ('normal', 'Normal'),
        ('hazardous', 'Hazardous'),
        ('heavy', 'Heavy'),
    ], string='Typical Work Conditions', default='normal')
    active = fields.Boolean(string='Active', default=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)


    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}" if record.code else record.name
