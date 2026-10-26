from odoo import fields, models


class AgroLandPlot(models.Model):
    _inherit = 'l10n_ua.agro.land.plot'

    l10n_ua_tax4_mountain_zone = fields.Boolean(
        string='Гірська / поліська зона',
        help='Знижена ставка ЄП 4 групи (ПКУ п. 293.9).')
    l10n_ua_tax4_excluded = fields.Boolean(
        string='Не включати в ЄП 4 групи',
        help='Землі запасу, у межах населених пунктів, непридатні тощо.')
    l10n_ua_tax4_arable_share = fields.Float(
        string='Частка ріллі, %', digits=(5, 2), default=100.0,
        help='Для мінімального податкового зобов\'язання: мінімум 1400 грн/га, якщо '
             'частка ріллі не менше 50 %, інакше 700 грн/га.')
    l10n_ua_tax4_ngo_done = fields.Boolean(
        string='НГО проведена', default=True,
        help='Вимкніть, якщо нормативна грошова оцінка ділянки не проведена — МПЗ тоді '
             'від НГО 1 га ріллі по області.')
