from odoo import api, fields, models


class L10nUaOsv(models.Model):
    _name = 'l10n_ua.osv'
    _description = 'Trial Balance / OSV (Оборотно-сальдова відомість)'
    _order = 'period_start desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'l10n_ua.osv.line',
        'osv_id',
        string='Lines',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='State',
        default='draft',
    )
    osv_type = fields.Selection(
        selection=[
            ('synthetic', 'Synthetic'),
            ('analytic', 'Analytic'),
        ],
        string='Type',
        default='synthetic',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )

    @api.depends('period_start', 'period_end', 'osv_type')
    def _compute_name(self):
        for record in self:
            type_name = 'Synthetic' if record.osv_type == 'synthetic' else 'Analytic'
            if record.period_start:
                record.name = f'OSV {type_name} ({record.period_start} - {record.period_end})'
            else:
                record.name = 'New'

    def action_compute(self):
        """Compute OSV lines from account moves."""
        self.ensure_one()
        self.line_ids.unlink()
        # TODO: Implement computation logic
        return True

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})


class L10nUaOsvLine(models.Model):
    _name = 'l10n_ua.osv.line'
    _description = 'OSV Line'
    _order = 'account_id'

    osv_id = fields.Many2one(
        'l10n_ua.osv',
        string='OSV',
        required=True,
        ondelete='cascade',
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    opening_debit = fields.Monetary(
        string='Opening Debit',
        currency_field='currency_id',
    )
    opening_credit = fields.Monetary(
        string='Opening Credit',
        currency_field='currency_id',
    )
    turnover_debit = fields.Monetary(
        string='Turnover Debit',
        currency_field='currency_id',
    )
    turnover_credit = fields.Monetary(
        string='Turnover Credit',
        currency_field='currency_id',
    )
    closing_debit = fields.Monetary(
        string='Closing Debit',
        currency_field='currency_id',
    )
    closing_credit = fields.Monetary(
        string='Closing Credit',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='osv_id.currency_id',
    )
