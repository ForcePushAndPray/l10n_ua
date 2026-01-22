from odoo import fields, models


class L10nUaBankStatement(models.Model):
    _inherit = 'l10n_ua.bank.statement'

    sync_provider = fields.Selection(
        selection_add=[('mono', 'monobank')],
        ondelete={'mono': 'set default'},
    )
