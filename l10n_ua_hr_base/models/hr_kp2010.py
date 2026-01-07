from odoo import models, fields, api


class HrKp2010(models.Model):
    _name = 'hr.kp2010'
    _description = 'Classifier of Professions (KP 2010)'
    _order = 'code'

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

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.code and record.name:
                record.display_name = f"[{record.code}] {record.name}"
            elif record.code:
                record.display_name = record.code
            elif record.name:
                record.display_name = record.name
            else:
                record.display_name = ''
