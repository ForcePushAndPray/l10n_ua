from odoo import models, fields, api


class HrWorkSchedule(models.Model):
    _name = 'hr.work.schedule'
    _description = 'Work Schedule'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code')
    sequence = fields.Integer(string='Sequence', default=10)
    
    schedule_type = fields.Selection([
        ('standard', 'Standard (5-day week)'),
        ('shift', 'Shift Work'),
        ('flexible', 'Flexible Schedule'),
        ('summarized', 'Summarized Accounting'),
    ], string='Schedule Type', required=True, default='standard')
    
    hours_per_week = fields.Float(string='Hours per Week', default=40.0)
    hours_per_day = fields.Float(string='Hours per Day', default=8.0)
    working_days_per_week = fields.Integer(string='Working Days per Week', default=5)
    
    is_night_work = fields.Boolean(string='Includes Night Work')
    night_start_hour = fields.Float(string='Night Start Hour', default=22.0)
    night_end_hour = fields.Float(string='Night End Hour', default=6.0)
    
    is_hazardous = fields.Boolean(string='Hazardous Conditions')
    reduced_hours = fields.Boolean(string='Reduced Working Hours')
    
    line_ids = fields.One2many(
        'hr.work.schedule.line', 
        'schedule_id', 
        string='Schedule Lines'
    )
    
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        default=lambda self: self.env.company
    )


class HrWorkScheduleLine(models.Model):
    _name = 'hr.work.schedule.line'
    _description = 'Work Schedule Line'
    _order = 'day_of_week'

    schedule_id = fields.Many2one(
        'hr.work.schedule', 
        string='Schedule', 
        required=True, 
        ondelete='cascade'
    )
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', required=True)
    
    is_working_day = fields.Boolean(string='Working Day', default=True)
    work_from = fields.Float(string='Work From', default=9.0)
    work_to = fields.Float(string='Work To', default=18.0)
    break_from = fields.Float(string='Break From', default=13.0)
    break_to = fields.Float(string='Break To', default=14.0)
    
    working_hours = fields.Float(
        string='Working Hours', 
        compute='_compute_working_hours', 
        store=True
    )

    @api.depends('work_from', 'work_to', 'break_from', 'break_to', 'is_working_day')
    def _compute_working_hours(self):
        for line in self:
            if not line.is_working_day:
                line.working_hours = 0.0
            else:
                total = line.work_to - line.work_from
                break_time = line.break_to - line.break_from if line.break_from and line.break_to else 0.0
                line.working_hours = max(0.0, total - break_time)
