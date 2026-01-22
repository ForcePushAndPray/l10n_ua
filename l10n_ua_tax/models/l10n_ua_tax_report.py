from odoo import api, fields, models


class L10nUaTaxReport(models.Model):
    _name = 'l10n_ua.tax.report'
    _description = 'Tax Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc, report_type'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    report_type = fields.Selection(
        selection=[
            ('vat', 'VAT Declaration'),
            ('ep', 'Single Tax Declaration'),
            ('4df', '4DF Report'),
            ('esv', 'ESV Report'),
            ('profit', 'Profit Tax Declaration'),
        ],
        string='Report Type',
        required=True,
        tracking=True,
    )
    period_id = fields.Many2one(
        'l10n_ua.tax.period',
        string='Tax Period',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('calculated', 'Calculated'),
            ('submitted', 'Submitted'),
            ('accepted', 'Accepted'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    submission_date = fields.Date(
        string='Submission Date',
        tracking=True,
    )
    acceptance_date = fields.Date(
        string='Acceptance Date',
        tracking=True,
    )
    xml_file = fields.Binary(
        string='XML File',
    )
    xml_filename = fields.Char(
        string='XML Filename',
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.depends('report_type', 'period_id')
    def _compute_name(self):
        report_names = {
            'vat': 'VAT Declaration',
            'ep': 'Single Tax Declaration',
            '4df': '4DF Report',
            'esv': 'ESV Report',
            'profit': 'Profit Tax Declaration',
        }
        for record in self:
            report_name = report_names.get(record.report_type, 'Report')
            period_name = record.period_id.name if record.period_id else ''
            record.name = f'{report_name} {period_name}'

    def action_calculate(self):
        self.write({'state': 'calculated'})

    def action_submit(self):
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
        })

    def action_accept(self):
        self.write({
            'state': 'accepted',
            'acceptance_date': fields.Date.context_today(self),
        })

    def action_draft(self):
        self.write({
            'state': 'draft',
            'submission_date': False,
            'acceptance_date': False,
        })

    def action_generate_xml(self):
        # TODO: Implement XML generation
        pass
