"""Program report: receipts vs spending vs balance per program / donor (#374)."""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class L10nUaNpoProgramReport(models.TransientModel):
    _name = 'l10n_ua.npo.program.report'
    _description = 'Target Programs Report'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(
        string='From',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='To',
        required=True,
        default=fields.Date.context_today,
    )
    program_ids = fields.Many2many(
        'l10n_ua.npo.program',
        string='Programs',
        help='Leave empty for all programs of the company.',
    )
    partner_id = fields.Many2one('res.partner', string='Donor')
    line_ids = fields.One2many(
        'l10n_ua.npo.program.report.line',
        'report_id',
        string='Lines',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_('The start date is after the end date.'))

    def _get_programs(self):
        self.ensure_one()
        if self.program_ids:
            return self.program_ids
        domain = [('company_id', '=', self.company_id.id),
                  ('state', '!=', 'draft')]
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        return self.env['l10n_ua.npo.program'].with_context(
            active_test=False).search(domain)

    def _compute_lines(self):
        self.ensure_one()
        programs = self._get_programs()
        before = programs._get_ledger_figures(self.date_from - timedelta(days=1))
        period = programs._get_ledger_figures(self.date_to, self.date_from)
        to_date = programs._get_ledger_figures(self.date_to)
        commands = [(5, 0, 0)]
        for program in programs:
            b, p, t = before[program.id], period[program.id], to_date[program.id]
            opening = b['received'] - b['other_debit'] - b['transferred']
            closing = t['received'] - t['other_debit'] - t['transferred']
            commands.append((0, 0, {
                'program_id': program.id,
                'budget_amount': program.budget_amount,
                'opening_balance': opening,
                'received': p['received'],
                'recognised': p['transferred'],
                'other_debit': p['other_debit'],
                'closing_balance': closing,
                'spent': p['spent'],
                'spent_to_date': t['spent'],
                'uncovered': t['spent'] - t['recognised'],
            }))
        self.line_ids = commands

    def action_compute(self):
        self.ensure_one()
        self._compute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Target Programs Report'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print(self):
        self.ensure_one()
        self._compute_lines()
        return self.env.ref(
            'l10n_ua_nonprofit.action_report_npo_program').report_action(self)


class L10nUaNpoProgramReportLine(models.TransientModel):
    _name = 'l10n_ua.npo.program.report.line'
    _description = 'Target Programs Report Line'
    _order = 'id'

    report_id = fields.Many2one(
        'l10n_ua.npo.program.report', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='report_id.currency_id')
    program_id = fields.Many2one('l10n_ua.npo.program', string='Program', readonly=True)
    partner_id = fields.Many2one(related='program_id.partner_id', string='Donor')
    budget_amount = fields.Monetary(string='Budget', readonly=True)
    opening_balance = fields.Monetary(string='Opening Balance', readonly=True)
    received = fields.Monetary(string='Received', readonly=True)
    recognised = fields.Monetary(string='Recognised as Income', readonly=True)
    other_debit = fields.Monetary(
        string='Returned / Other', readonly=True,
        help='Debits of 48 other than the recognition: refunds to the donor, '
             'direct write-offs.')
    closing_balance = fields.Monetary(string='Closing Balance', readonly=True)
    spent = fields.Monetary(string='Spent in Period', readonly=True)
    spent_to_date = fields.Monetary(string='Spent to Date', readonly=True)
    uncovered = fields.Monetary(
        string='Expenses Not Yet Covered', readonly=True,
        help='Program expenses to date not matched by recognised income.')
    budget_used = fields.Float(
        string='Budget Used (%)', compute='_compute_budget_used')

    @api.depends('budget_amount', 'spent_to_date')
    def _compute_budget_used(self):
        for line in self:
            line.budget_used = (line.spent_to_date / line.budget_amount * 100.0) \
                if line.budget_amount else 0.0
