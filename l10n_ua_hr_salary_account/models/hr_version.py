from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    salary_analytic_distribution = fields.Json(
        string='Аналітичний розподіл ЗП',
        help='Розподіл зарплатних витрат цього працівника за аналітичними '
             'рахунками (проєкти, центри витрат). Має пріоритет над розподілом '
             'підрозділу. Застосовується до рядків витрат (Дт 91/92/93/94, ЄСВ) '
             'у зарплатних проводках.',
    )
