"""Period closing of a non-profit organization (#374).

Before the income and expense accounts are closed, the month's target
financing is recognised as income (Дт 48 – Кт 718, П(С)БО 15 п. 17), the same
way ``l10n_ua_accounting`` posts the deferral recognitions (39/69) in
``_post_deferral_entries``. Reversing the closing reverses the recognition.
"""

from odoo import fields, models


class L10nUaPeriodClosing(models.Model):
    _inherit = 'l10n_ua.period.closing'

    npo_recognition_ids = fields.One2many(
        'l10n_ua.npo.recognition',
        'closing_id',
        string='Target Income Recognition',
        readonly=True,
    )
    l10n_ua_is_nonprofit = fields.Boolean(related='company_id.l10n_ua_is_nonprofit')

    def _post_deferral_entries(self):
        res = super()._post_deferral_entries()
        self._post_npo_recognition()
        return res

    def _reverse_deferral_entries(self):
        res = super()._reverse_deferral_entries()
        self.npo_recognition_ids.filtered(
            lambda r: r.state == 'posted').action_cancel()
        return res

    def _post_npo_recognition(self):
        """Recognise target financing of a non-profit up to the period end.

        Idempotent: a closing that already has a posted recognition is left
        alone, and the amounts are computed from the ledger (expenses not yet
        covered by income), so a second run finds nothing to recognise.
        """
        self.ensure_one()
        company = self.company_id
        if not company.l10n_ua_is_nonprofit \
                or not company.l10n_ua_npo_recognise_on_closing:
            return self.env['l10n_ua.npo.recognition']
        if self.npo_recognition_ids.filtered(lambda r: r.state == 'posted'):
            return self.env['l10n_ua.npo.recognition']
        Recognition = self.env['l10n_ua.npo.recognition']
        recognition = Recognition.create({
            'company_id': company.id,
            'date': self.date,
            'closing_id': self.id,
            'journal_id': (company.l10n_ua_npo_journal_id or self.journal_id).id,
        })
        recognition.action_compute()
        if all(recognition.currency_id.is_zero(amount)
               for amount in recognition.line_ids.mapped('amount')):
            recognition.unlink()
            return Recognition
        recognition.action_post()
        return recognition
