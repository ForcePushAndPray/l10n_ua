from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    edrpou = fields.Char(
        string='EDRPOU', size=8,
        help='Unified State Register of Enterprises and Organizations of Ukraine code')
    koatuu = fields.Char(
        string='KOATUU', size=10,
        help='Code of the Classification of Administrative-Territorial Units of Ukraine')
    katottg = fields.Char(
        string='KATOTTG', size=19,
        help='Код КАТОТТГ (кодифікатор адміністративно-територіальних одиниць), '
             'формат UA + 17 цифр. Потрібен для звітності 4ДФ/об\'єднаного розрахунку.')
    legal_address = fields.Text(string='Legal Address')
    director_id = fields.Many2one(
        'hr.employee', string='Director',
        help='Company director for document signing')
    accountant_id = fields.Many2one(
        'hr.employee', string='Chief Accountant',
        help='Chief accountant for document signing')
    hr_manager_id = fields.Many2one(
        'hr.employee', string='HR Manager',
        help='HR department head for document signing')
    military_officer_id = fields.Many2one(
        'hr.employee', string='Відповідальний за військовий облік',
        help='Особа, відповідальна за ведення військового обліку. Підписує '
             'Списки персонального військового обліку та відомість '
             'оперативного обліку (п. 40 Порядку № 1487), і саме її кадровий '
             'модуль підставляє у друковані форми за замовчуванням.')
    tax_office_code = fields.Char(
        string='Tax Office Code',
        help='Code of the tax office (DPI)')
    pension_fund_code = fields.Char(
        string='Pension Fund Code',
        help='Code of the pension fund office (PFU)')
    kved_main = fields.Char(
        string='Main KVED',
        help='Main economic activity code (KVED)')
    ownership_form = fields.Selection([
        ('private', 'Private'),
        ('state', 'State'),
        ('communal', 'Communal'),
        ('collective', 'Collective'),
        ('mixed', 'Mixed'),
    ], string='Ownership Form')

    # Staffing table settings
    wage_from_staffing = fields.Selection([
        ('none', 'Do not use'),
        ('suggest', 'Suggest (fill on selection)'),
        ('fallback', 'Fallback (use if wage is 0)'),
        ('both', 'Both (suggest + fallback)'),
    ], string='Wage from Staffing Table',
       default='both',
       help='How to use salary from staffing table:\n'
            '- Do not use: ignore staffing table salary\n'
            '- Suggest: auto-fill wage when selecting staffing position\n'
            '- Fallback: use staffing salary in payslip if contract wage is 0\n'
            '- Both: suggest on selection + fallback in payslip')
