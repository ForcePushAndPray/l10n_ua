from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    contract_ids = fields.One2many(
        'hr.contract',
        'employee_id',
        string='Contracts'
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string='Current Contract',
        compute='_compute_contract_id',
        store=True,
        help='Current running contract'
    )
    contracts_count = fields.Integer(
        string='Contracts Count',
        compute='_compute_contracts_count'
    )

    @api.depends('contract_ids', 'contract_ids.state', 'contract_ids.date_start')
    def _compute_contract_id(self):
        for employee in self:
            contracts = employee.contract_ids.filtered(lambda c: c.state == 'open')
            if contracts:
                employee.contract_id = contracts.sorted('date_start', reverse=True)[0]
            else:
                employee.contract_id = False

    def _compute_contracts_count(self):
        for employee in self:
            employee.contracts_count = len(employee.contract_ids)

    def action_open_contracts(self):
        self.ensure_one()
        return {
            'name': 'Contracts',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
