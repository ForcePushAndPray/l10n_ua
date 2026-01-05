from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    contract_ua_ids = fields.One2many(
        'hr.contract.ua',
        'employee_id',
        string='UA Contracts'
    )
    contract_ua_id = fields.Many2one(
        'hr.contract.ua',
        string='Current UA Contract',
        compute='_compute_contract_ua_id',
        store=True,
        help='Current running Ukrainian contract'
    )
    contracts_ua_count = fields.Integer(
        string='UA Contracts Count',
        compute='_compute_contracts_ua_count'
    )

    @api.depends('contract_ua_ids', 'contract_ua_ids.state', 'contract_ua_ids.date_start')
    def _compute_contract_ua_id(self):
        for employee in self:
            contracts = employee.contract_ua_ids.filtered(lambda c: c.state == 'open')
            if contracts:
                employee.contract_ua_id = contracts.sorted('date_start', reverse=True)[0]
            else:
                employee.contract_ua_id = False

    def _compute_contracts_ua_count(self):
        for employee in self:
            employee.contracts_ua_count = len(employee.contract_ua_ids)

    def action_open_contracts_ua(self):
        self.ensure_one()
        return {
            'name': 'Contracts',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.ua',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
