import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TelegramSendWizard(models.TransientModel):
    _name = 'telegram.send.wizard'
    _description = 'Send Telegram Message'

    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    chat_id = fields.Many2one(
        'telegram.bot.chat', string='Telegram Chat', required=True,
        domain="[('partner_id', '=', partner_id)]",
    )
    recipient_label = fields.Char(string='To', compute='_compute_recipient_label')
    message_text = fields.Text(string='Message', required=True)

    @api.depends('chat_id')
    def _compute_recipient_label(self):
        for wiz in self:
            chat = wiz.chat_id
            if chat:
                name = ('@' + chat.user_name) if chat.user_name else (chat.telegram_chat_id or '')
                wiz.recipient_label = '%s · @%s' % (name, chat.bot_id.username or 'bot')
            else:
                wiz.recipient_label = ''

    def action_send(self):
        self.ensure_one()
        chat = self.chat_id
        if not chat:
            raise UserError(_("No Telegram chat selected."))
        if chat.state == 'blocked':
            raise UserError(_("This user has blocked the bot — the message cannot be delivered."))
        if not chat.bot_id:
            raise UserError(_("This chat has no bot configured."))
        text = (self.message_text or '').strip()
        if not text:
            raise UserError(_("The message is empty."))
        # send_message (log_message=True) delivers to Telegram, stores a
        # telegram.bot.message(outgoing) and posts it to the contact chatter.
        # Run as sudo: the bot is a system actor (like the webhook), so any
        # internal user with the button may send without telegram.bot.* rights.
        result = chat.bot_id.sudo().send_message(chat.telegram_chat_id, text, parse_mode=None)
        if not result:
            raise UserError(_("Failed to send the Telegram message. See the bot log for details."))
        return {'type': 'ir.actions.act_window_close'}
