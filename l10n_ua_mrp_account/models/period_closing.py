from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError


class L10nUaPeriodClosing(models.Model):
    _inherit = 'l10n_ua.period.closing'

    overhead_allocation_ids = fields.Many2many(
        'l10n_ua.overhead.allocation',
        string='Overhead Allocations',
        compute='_compute_overhead_allocation_ids',
        help='Production overhead allocations (91 → 23 / 90) of the period. '
             'Closing the period posts the draft ones, or creates one, before '
             'the 9x accounts are closed.',
    )

    def _compute_overhead_allocation_ids(self):
        for rec in self:
            if rec.period_id and rec.company_id:
                rec.overhead_allocation_ids = rec._get_overhead_allocations()
            else:
                rec.overhead_allocation_ids = False

    def _get_overhead_allocations(self, states=None):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_to', '>=', self.period_id.date_start),
            ('date_to', '<=', self.period_id.date_end),
        ]
        if states:
            domain.append(('state', 'in', states))
        return self.env['l10n_ua.overhead.allocation'].search(domain)

    def _overhead_balance(self):
        """Balance left on the overhead accounts (91) at the period end."""
        self.ensure_one()
        variable, fixed = self.company_id._l10n_ua_overhead_accounts()
        accounts = variable | fixed
        if not accounts:
            return 0.0
        groups = self.env['account.move.line']._read_group([
            ('account_id', 'in', accounts.ids),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', self.period_id.date_end),
        ], [], ['balance:sum'])
        return groups[0][0] or 0.0

    def _post_overhead_allocation(self):
        """Allocate production overhead before the 9x accounts are closed.

        Draft allocations of the period are posted. If overhead is still left
        on 91 afterwards, a new allocation for the whole period is created and
        posted when the company allows it, otherwise the closing is refused —
        the unallocated fixed overhead must reach 90x before 90x is closed
        (NP(S)BO 16, item 16).
        """
        self.ensure_one()
        Allocation = self.env['l10n_ua.overhead.allocation']
        posted = Allocation
        for allocation in self._get_overhead_allocations(states=['draft']):
            allocation.action_post()
            allocation.closing_id = self
            posted |= allocation
        currency = self.company_id.currency_id
        if currency.is_zero(self._overhead_balance()):
            return posted
        if not self.company_id.l10n_ua_overhead_auto_allocate:
            raise UserError(_(
                'Production overhead (account 91) is not allocated for %s. '
                'Post the overhead allocation before closing the period.',
                self.period_id.name))
        # Continue after an allocation already posted for part of the month.
        date_from = self.period_id.date_start
        last = self._get_overhead_allocations(states=['posted']).sorted('date_to')[-1:]
        if last and last.date_to >= date_from:
            date_from = last.date_to + timedelta(days=1)
        if date_from > self.period_id.date_end:
            raise UserError(_(
                'Production overhead (account 91) was posted after the overhead '
                'allocation %(allocation)s. Cancel it and post it again before '
                'closing %(period)s.',
                allocation=last.name, period=self.period_id.name))
        allocation = Allocation.create({
            'company_id': self.company_id.id,
            'date_from': date_from,
            'date_to': self.period_id.date_end,
            'base': self.company_id.l10n_ua_overhead_base or 'labour',
            'normal_base': self.company_id.l10n_ua_overhead_normal_base,
            'journal_id': (self.company_id.l10n_ua_overhead_journal_id or self.journal_id).id,
        })
        allocation.action_post()
        allocation.closing_id = self
        return posted | allocation

    def _post_deferral_entries(self):
        # Step 0 of the closing: deferrals (39/69), then overhead (91).
        res = super()._post_deferral_entries()
        self._post_overhead_allocation()
        return res

    def _reverse_deferral_entries(self):
        res = super()._reverse_deferral_entries()
        self.env['l10n_ua.overhead.allocation'].search([
            ('closing_id', '=', self.id),
        ])._cancel_from_closing(self)
        return res

    def action_open_overhead_allocations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overhead Allocation'),
            'res_model': 'l10n_ua.overhead.allocation',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.overhead_allocation_ids.ids)],
            'context': {
                'default_company_id': self.company_id.id,
                'default_date_from': self.period_id.date_start,
                'default_date_to': self.period_id.date_end,
            },
        }
