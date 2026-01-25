from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ua_doc_type = fields.Selection(
        selection=[
            ('invoice', 'Invoice (Рахунок)'),
            ('tax_invoice', 'Tax Invoice (Податкова накладна)'),
            ('adjustment', 'Adjustment (Розрахунок коригування)'),
            ('act', 'Act (Акт виконаних робіт)'),
            ('ttn', 'TTN (Товарно-транспортна накладна)'),
            ('pko', 'PKO (Прибутковий касовий ордер)'),
            ('vko', 'VKO (Видатковий касовий ордер)'),
            ('bank', 'Bank Statement (Банківська виписка)'),
            ('advance', 'Advance Report (Авансовий звіт)'),
            ('other', 'Other'),
        ],
        string='UA Document Type',
    )
    ua_doc_number = fields.Char(
        string='UA Document Number',
        help='Document number in Ukrainian format',
    )
    ua_doc_date = fields.Date(
        string='UA Document Date',
        help='Document date (may differ from accounting date)',
    )
    ua_counterparty_doc = fields.Char(
        string='Counterparty Document',
        help='Counterparty document number',
    )
