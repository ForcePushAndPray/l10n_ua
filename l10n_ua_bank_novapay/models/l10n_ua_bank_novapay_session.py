from odoo import fields, models


class L10nUaBankNovapaySession(models.Model):
    """Поточний стан авторизації NovaPay для підключення банку.

    Refresh-токен NovaPay одноразовий: кожна авторизація анулює попередній і
    повертає новий. Тому стан зберігається окремо від конфігу й записується
    власним курсором (див. `_novapay_session_env`) — відкат основної
    транзакції (помилка розбору виписки тощо) не має губити щойно виданий
    токен, інакше підключення довелося б налаштовувати заново.
    """
    _name = 'l10n_ua.bank.novapay.session'
    _description = 'NovaPay API Session'

    config_id = fields.Many2one(
        'l10n_ua.bank.sync.config',
        string='Configuration',
        required=True,
        index=True,
        ondelete='cascade',
    )
    # Токен, введений користувачем, від якого почався цей ланцюжок ротації.
    seed_token = fields.Char(string='Seed Refresh Token')
    refresh_token = fields.Char(string='Refresh Token')
    public_certificate = fields.Text(string='Public Certificate')
    jwt = fields.Text(string='JWT')
    jwt_expiration = fields.Datetime(string='JWT Expiration')

    _config_uniq = models.Constraint(
        'UNIQUE(config_id)',
        'Only one NovaPay session per configuration is allowed!',
    )
