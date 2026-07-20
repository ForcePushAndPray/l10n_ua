from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    payroll_bank_account_id = fields.Many2one(
        'res.partner.bank', string='Payroll Payer Account',
        help='Рахунок компанії-платника для зарплатного банк-файлу.')
    payroll_bank_file_format = fields.Selection(
        [('xml', 'XML'), ('dbf', 'DBF')],
        string='Payroll Bank File Format', default='xml',
        help='Типовий формат зарплатного файлу для клієнт-банку.')
    payroll_payment_purpose = fields.Char(
        string='Payroll Payment Purpose',
        default='Заробітна плата за {period}',
        help='Шаблон призначення платежу. Плейсхолдери: {period}, '
             '{employee}, {rnokpp}.')
