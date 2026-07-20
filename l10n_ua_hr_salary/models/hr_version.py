from odoo import models, fields


class HrVersion(models.Model):
    _inherit = 'hr.version'

    indexation_enabled = fields.Boolean(
        string='Індексувати ЗП',
        default=True,
        help='Проводити індексацію заробітної плати згідно із Законом '
             'про індексацію грошових доходів населення.'
    )
    indexation_base_month = fields.Date(
        string='Базовий місяць індексації',
        help='Місяць останнього підвищення посадового окладу / тарифної '
             'ставки. Накопичення індексу споживчих цін починається з '
             'наступного місяця. Оновлюється при кожному підвищенні зарплати.'
    )
