from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    mono_acquiring_token = fields.Char(
        string="Monobank Acquiring Token",
        help="X-Token для Monobank Merchant API (еквайринг). "
             "Отримати можна в особистому кабінеті https://fop.monobank.ua",
    )
