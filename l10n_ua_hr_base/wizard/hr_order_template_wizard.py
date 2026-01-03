from odoo import models, fields, api


class HrOrderTemplateWizard(models.TransientModel):
    _name = 'hr.order.template.wizard'
    _description = 'HR Order Template Selection Wizard'

    order_id = fields.Many2one('hr.order', string='Order', required=True)
    order_type = fields.Selection([
        ('hiring', 'Hiring'),
        ('dismissal', 'Dismissal'),
        ('transfer', 'Transfer'),
        ('vacation', 'Vacation'),
        ('bonus', 'Bonus'),
        ('sick_leave', 'Sick Leave'),
        ('business_trip', 'Business Trip'),
        ('other', 'Other'),
    ], string='Order Type')
    
    template_id = fields.Many2one(
        'hr.order.template', 
        string='Template', 
        required=True,
        domain="[('order_type', '=', order_type), ('active', '=', True)]"
    )

    def action_apply_template(self):
        self.ensure_one()
        template = self.template_id
        order = self.order_id
        vals = {}
        
        if template.subject:
            vals['subject'] = self._render_template_string(template.subject, order)
        
        if template.body:
            vals['content'] = self._render_template_string(template.body, order)
        
        if vals:
            order.write(vals)
        
        return {'type': 'ir.actions.act_window_close'}
    
    def _render_template_string(self, template_str, order):
        employee = order.employee_id
        company = order.company_id
        
        replacements = {
            '{company_name}': company.name or '_______________',
            '{order_number}': order.name or '______',
            '{order_date}': order.date.strftime('%d.%m.%Y') if order.date else '____________',
            '{order_date_day}': str(order.date.day) if order.date else '___',
            '{order_date_month}': self._get_month_name(order.date.month) if order.date else '____________',
            '{order_date_year}': str(order.date.year) if order.date else '20__',
            '{employee_name}': employee.name if employee else '________________________________',
            '{employee_barcode}': employee.barcode or '____________' if employee else '____________',
            '{department_name}': order.department_id.name if order.department_id else (employee.department_id.name if employee and employee.department_id else '________________________________'),
            '{job_name}': order.job_id.name if order.job_id else (employee.job_id.name if employee and employee.job_id else '________________________________'),
            '{director_name}': '________________',
        }
        
        result = template_str
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, str(value))
        
        return result
    
    def _get_month_name(self, month):
        months = {
            1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
            5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
            9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
        }
        return months.get(month, '____________')
