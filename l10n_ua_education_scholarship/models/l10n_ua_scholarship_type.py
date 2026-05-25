from odoo import api, fields, models


class L10nUaScholarshipType(models.Model):
    """Тип стипендії.

    Регулюється Постановою КМУ № 1146 від 28.12.2016 та галузевими актами.
    Розміри встановлюються щорічно у Законі про Державний бюджет.
    """
    _name = 'l10n_ua.scholarship.type'
    _description = 'Тип стипендії'
    _order = 'sequence, code'

    name = fields.Char(string='Назва', required=True, translate=True)
    code = fields.Char(string='Код', required=True, index=True)
    sequence = fields.Integer(default=10)
    kind = fields.Selection([
        ('academic', 'Академічна'),
        ('social', 'Соціальна'),
        ('presidential', 'Президентська'),
        ('rada', 'Верховної Ради'),
        ('regional', 'Обласна / місцева'),
        ('named', 'Іменна'),
        ('other', 'Інша'),
    ], string='Категорія', required=True, default='academic')
    monthly_amount = fields.Monetary(
        string='Місячна сума за замовчуванням',
        currency_field='currency_id',
        help='Базовий розмір на місяць. Можна перевизначити на рівні рядка виплати.')
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    default_kekv_id = fields.Many2one(
        'l10n_ua.kekv', string='КЕКВ за замовчуванням',
        domain="[('child_ids', '=', False)]",
        help='Зазвичай КЕКВ 2720 «Стипендії»')
    is_taxable_pdfo = fields.Boolean(
        string='Оподатковується ПДФО',
        help='Чи підлягає стипендія оподаткуванню податком на доходи фізосіб '
             '(зазвичай стипендії в межах прожиткового мінімуму не оподатковуються).')
    description = fields.Html(string='Опис / нормативне обґрунтування')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        'Код типу стипендії має бути унікальним!',
    )
