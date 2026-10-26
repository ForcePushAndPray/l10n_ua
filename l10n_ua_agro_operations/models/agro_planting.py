from odoo import api, fields, models


class AgroPlanting(models.Model):
    _inherit = 'l10n_ua.agro.planting'

    work_order_ids = fields.One2many('l10n_ua.agro.work.order', 'planting_id', string='Work Orders')
    work_order_count = fields.Integer(compute='_compute_operation_costs')
    currency_id = fields.Many2one(related='company_id.currency_id')
    planned_cost = fields.Monetary(
        string='Planned Cost', compute='_compute_operation_costs',
        help='Собівартість за техкартою: витрати на 1 га × посівна площа.')
    actual_cost = fields.Monetary(
        string='Actual Cost', compute='_compute_operation_costs',
        help='Проведені наряди: матеріали, пальне й оплата праці механізаторів.')

    @api.depends('work_order_ids.state', 'work_order_ids.total_amount', 'area')
    def _compute_operation_costs(self):
        Card = self.env['l10n_ua.agro.tech.card']
        for planting in self:
            card = Card.search([
                ('crop_id', '=', planting.crop_id.id),
                ('season_id', '=', planting.season_id.id),
                ('company_id', '=', planting.company_id.id),
            ], limit=1) if planting.crop_id and planting.season_id else Card
            done = planting.work_order_ids.filtered(lambda o: o.state == 'done')
            planting.work_order_count = len(planting.work_order_ids)
            planting.planned_cost = card.cost_ha * planting.area
            planting.actual_cost = sum(done.mapped('total_amount'))

    def action_view_work_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'l10n_ua_agro_operations.l10n_ua_agro_work_order_action')
        action['domain'] = [('planting_id', '=', self.id)]
        action['context'] = {'default_planting_id': self.id}
        return action
