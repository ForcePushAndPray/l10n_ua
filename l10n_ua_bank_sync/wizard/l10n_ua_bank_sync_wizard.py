from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nUaBankSyncWizard(models.TransientModel):
    _name = 'l10n_ua.bank.sync.wizard'
    _description = 'Bank Sync Wizard'

    config_id = fields.Many2one(
        'l10n_ua.bank.sync.config',
        string='Bank Configuration',
        required=True,
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today() - timedelta(days=7),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=fields.Date.today,
    )

    # Quick select buttons
    period = fields.Selection(
        selection=[
            ('custom', 'Custom Period'),
            ('today', 'Today'),
            ('yesterday', 'Yesterday'),
            ('last_7_days', 'Last 7 Days'),
            ('last_30_days', 'Last 30 Days'),
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
        ],
        string='Quick Select',
        default='custom',
    )

    @api.onchange('period')
    def _onchange_period(self):
        today = fields.Date.today()

        if self.period == 'today':
            self.date_from = today
            self.date_to = today
        elif self.period == 'yesterday':
            yesterday = today - timedelta(days=1)
            self.date_from = yesterday
            self.date_to = yesterday
        elif self.period == 'last_7_days':
            self.date_from = today - timedelta(days=7)
            self.date_to = today
        elif self.period == 'last_30_days':
            self.date_from = today - timedelta(days=30)
            self.date_to = today
        elif self.period == 'this_month':
            self.date_from = today.replace(day=1)
            self.date_to = today
        elif self.period == 'last_month':
            first_of_this_month = today.replace(day=1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            self.date_from = last_of_prev_month.replace(day=1)
            self.date_to = last_of_prev_month

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise UserError(_("Date From must be before Date To"))

    def action_sync(self):
        """Create and run sync job."""
        self.ensure_one()
        return self.config_id._create_and_run_job(self.date_from, self.date_to)
