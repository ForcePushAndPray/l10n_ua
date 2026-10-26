from odoo import fields, models, tools


class AgroCostReport(models.Model):
    """План / факт витрат по посівах: план — техкарта (витрати на 1 га ×
    посівна площа), факт — проведені наряди (матеріали, пальне, праця)."""
    _name = 'l10n_ua.agro.cost.report'
    _description = 'Field Cost Analysis'
    _auto = False
    _order = 'season_id desc, field_id'

    planting_id = fields.Many2one('l10n_ua.agro.planting', string='Planting', readonly=True)
    field_id = fields.Many2one('l10n_ua.agro.field', string='Field', readonly=True)
    season_id = fields.Many2one('l10n_ua.agro.season', string='Season', readonly=True)
    crop_id = fields.Many2one('l10n_ua.agro.crop', string='Crop', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    date = fields.Date(readonly=True)
    kind = fields.Selection([('plan', 'Plan'), ('actual', 'Actual')], readonly=True)
    cost_type = fields.Selection([
        ('material', 'Materials'),
        ('fuel', 'Fuel'),
        ('labor', 'Labor'),
        ('operation', 'Operations'),
    ], string='Cost Type', readonly=True)
    planned_amount = fields.Monetary(string='Plan', readonly=True)
    actual_amount = fields.Monetary(string='Actual', readonly=True)
    area = fields.Float(string='Area (ha)', digits=(16, 4), readonly=True, aggregator='max')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT row_number() OVER () AS id, t.* FROM (
                    SELECT p.id AS planting_id, p.field_id, p.season_id, p.crop_id, p.company_id,
                           c.currency_id, s.date_start AS date, 'plan' AS kind, 'material' AS cost_type,
                           SUM(m.cost_ha) * p.area AS planned_amount, 0.0 AS actual_amount, p.area
                      FROM l10n_ua_agro_planting p
                      JOIN l10n_ua_agro_season s ON s.id = p.season_id
                      JOIN res_company c ON c.id = p.company_id
                      JOIN l10n_ua_agro_tech_card tc ON tc.crop_id = p.crop_id AND tc.season_id = p.season_id
                                                     AND tc.company_id = p.company_id AND tc.active
                      JOIN l10n_ua_agro_tech_card_material m ON m.card_id = tc.id
                     GROUP BY p.id, c.currency_id, s.date_start
                    UNION ALL
                    SELECT p.id, p.field_id, p.season_id, p.crop_id, p.company_id,
                           c.currency_id, s.date_start, 'plan', 'operation',
                           SUM(o.cost_ha) * p.area, 0.0, p.area
                      FROM l10n_ua_agro_planting p
                      JOIN l10n_ua_agro_season s ON s.id = p.season_id
                      JOIN res_company c ON c.id = p.company_id
                      JOIN l10n_ua_agro_tech_card tc ON tc.crop_id = p.crop_id AND tc.season_id = p.season_id
                                                     AND tc.company_id = p.company_id AND tc.active
                      JOIN l10n_ua_agro_tech_card_operation o ON o.card_id = tc.id
                     GROUP BY p.id, c.currency_id, s.date_start
                    UNION ALL
                    SELECT w.planting_id, w.field_id, w.season_id, w.crop_id, w.company_id,
                           c.currency_id, w.date, 'actual',
                           CASE WHEN m.is_fuel THEN 'fuel' ELSE 'material' END,
                           0.0, m.amount, p.area
                      FROM l10n_ua_agro_work_order_material m
                      JOIN l10n_ua_agro_work_order w ON w.id = m.order_id
                      JOIN l10n_ua_agro_planting p ON p.id = w.planting_id
                      JOIN res_company c ON c.id = w.company_id
                     WHERE w.state = 'done'
                    UNION ALL
                    SELECT w.planting_id, w.field_id, w.season_id, w.crop_id, w.company_id,
                           c.currency_id, w.date, 'actual', 'labor', 0.0, l.amount, p.area
                      FROM l10n_ua_agro_work_order_worker l
                      JOIN l10n_ua_agro_work_order w ON w.id = l.order_id
                      JOIN l10n_ua_agro_planting p ON p.id = w.planting_id
                      JOIN res_company c ON c.id = w.company_id
                     WHERE w.state = 'done'
                ) t
            )
        """)
