from odoo import models, fields


class HrLeaveTypeDefaultConfirm(models.TransientModel):
    _name = 'hr.leave.type.default.confirm'
    _description = 'Confirm Default Leave Type Change'

    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='New Default',
        required=True,
    )
    current_default_ids = fields.Many2many(
        'hr.leave.type',
        string='Current Default(s)',
        readonly=True,
    )

    def action_confirm(self):
        """Apply the new default and clear the flag on the company's other
        leave types."""
        self.ensure_one()
        self.leave_type_id._apply_default()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave.type',
            'res_id': self.leave_type_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

