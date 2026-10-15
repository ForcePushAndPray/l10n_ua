"""Recognition of target financing as income (#374).

П(С)БО 15 «Дохід», п. 17: отримане цільове фінансування визнається доходом
протягом тих періодів, в яких були зазнані витрати, пов'язані з виконанням
умов цільового фінансування. Проводка: Дт 48 – Кт 718 (або інший рахунок
доходу програми) з аналітикою програми.

A recognition document covers all active programs of the company as of a
date; the period closing creates one automatically (see
``l10n_ua_period_closing.py``).
"""

from calendar import monthrange

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _month_end(day):
    return day.replace(day=monthrange(day.year, day.month)[1])


class L10nUaNpoRecognition(models.Model):
    _name = 'l10n_ua.npo.recognition'
    _description = 'Target Financing Income Recognition'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(
        string='Date',
        required=True,
        default=lambda self: _month_end(fields.Date.context_today(self)),
        tracking=True,
        help='Expenses and receipts up to this date are taken into account; '
             'the entry is dated on it.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        check_company=True,
        domain="[('type', '=', 'general')]",
        default=lambda self: self.env.company.l10n_ua_npo_journal_id,
    )
    program_ids = fields.Many2many(
        'l10n_ua.npo.program',
        string='Programs',
        check_company=True,
        help='Leave empty to process all active programs of the company.',
    )
    line_ids = fields.One2many(
        'l10n_ua.npo.recognition.line',
        'recognition_id',
        string='Lines',
    )
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )
    closing_id = fields.Many2one(
        'l10n_ua.period.closing',
        string='Period Closing',
        readonly=True,
        copy=False,
        index='btree_not_null',
        help='Period closing that posted this recognition; reversing the '
             'closing reverses it too.',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('cancelled', 'Cancelled')],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    amount_total = fields.Monetary(
        string='Recognised Income',
        compute='_compute_amount_total',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('date')
    def _compute_name(self):
        for rec in self:
            rec.name = _('Target income recognition %s',
                         rec.date.strftime('%d.%m.%Y')) if rec.date else _('New')

    @api.depends('line_ids.amount')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('amount'))

    def _get_programs(self):
        self.ensure_one()
        if self.program_ids:
            return self.program_ids.filtered(lambda p: p.state != 'draft')
        return self.env['l10n_ua.npo.program'].search([
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('active', 'closed')),
        ])

    def action_compute(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only a draft recognition can be recomputed.'))
            programs = rec._get_programs()
            amounts = programs._get_recognition_amounts(rec.date)
            lines = [(5, 0, 0)]
            for program in programs:
                data = amounts[program.id]
                if rec.currency_id.is_zero(data['amount']) \
                        and rec.currency_id.is_zero(data['spent']) \
                        and rec.currency_id.is_zero(data['balance']):
                    continue
                lines.append((0, 0, {
                    'program_id': program.id,
                    'expense_total': data['spent'],
                    'recognised_before': data['recognised'],
                    'balance_available': data['balance'],
                    'amount': data['amount'],
                }))
            rec.line_ids = lines
        return True

    def _get_journal(self):
        self.ensure_one()
        journal = self.journal_id or self.company_id.l10n_ua_npo_journal_id \
            or self.closing_id.journal_id
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not journal:
            raise UserError(_('Set the target financing journal of the company.'))
        return journal

    def _prepare_move_vals(self):
        self.ensure_one()
        line_vals = []
        for line in self.line_ids.filtered(
                lambda l: not l.currency_id.is_zero(l.amount)):
            program = line.program_id
            distribution = {str(program.analytic_account_id.id): 100.0}
            label = _('Target financing recognised as income: %s', program.name)
            amount = line.amount
            # amount > 0: Дт 48 – Кт 718; amount < 0: back, Дт 718 – Кт 48
            line_vals += [
                (0, 0, {
                    'name': label,
                    'account_id': program.account_id.id,
                    'partner_id': program.partner_id.id,
                    'debit': max(amount, 0.0),
                    'credit': max(-amount, 0.0),
                    'analytic_distribution': distribution,
                }),
                (0, 0, {
                    'name': label,
                    'account_id': program.income_account_id.id,
                    'partner_id': program.partner_id.id,
                    'debit': max(-amount, 0.0),
                    'credit': max(amount, 0.0),
                    'analytic_distribution': distribution,
                }),
            ]
        return {
            'move_type': 'entry',
            'journal_id': self._get_journal().id,
            'date': self.date,
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': line_vals,
        }

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only a draft recognition can be posted.'))
            if not rec.line_ids:
                rec.action_compute()
            if all(rec.currency_id.is_zero(a) for a in rec.line_ids.mapped('amount')):
                raise UserError(_(
                    'Nothing to recognise on %s: the programs have no expenses '
                    'not yet covered by income, or no balance on 48.',
                    rec.date.strftime('%d.%m.%Y')))
            move = self.env['account.move'].create(rec._prepare_move_vals())
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted'})
        return True

    def action_cancel(self):
        """Reverse the recognition entry (dated as the entry itself)."""
        for rec in self:
            if rec.state != 'posted':
                continue
            if rec.move_id.state == 'posted':
                rec.move_id._reverse_moves(
                    default_values_list=[{
                        'date': rec.move_id.date,
                        'ref': _('Reversal of: %s', rec.move_id.ref),
                    }],
                    cancel=True,
                )
            rec.state = 'cancelled'
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only a cancelled recognition can be reset to draft.'))
            rec.write({'state': 'draft', 'move_id': False, 'closing_id': False})
        return True

    def unlink(self):
        if any(rec.state == 'posted' for rec in self):
            raise UserError(_('Cancel the recognition before deleting it.'))
        return super().unlink()

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }


class L10nUaNpoRecognitionLine(models.Model):
    _name = 'l10n_ua.npo.recognition.line'
    _description = 'Target Financing Income Recognition Line'
    _order = 'recognition_id, id'

    recognition_id = fields.Many2one(
        'l10n_ua.npo.recognition',
        string='Recognition',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(related='recognition_id.company_id', store=True)
    currency_id = fields.Many2one(related='recognition_id.currency_id')
    program_id = fields.Many2one(
        'l10n_ua.npo.program',
        string='Program',
        required=True,
        ondelete='restrict',
    )
    partner_id = fields.Many2one(related='program_id.partner_id', string='Donor')
    expense_total = fields.Monetary(
        string='Program Expenses to Date', currency_field='currency_id')
    recognised_before = fields.Monetary(
        string='Recognised Before', currency_field='currency_id')
    balance_available = fields.Monetary(
        string='Balance on 48', currency_field='currency_id')
    amount = fields.Monetary(
        string='Income to Recognise', currency_field='currency_id')
