import base64
import json

from odoo import models, fields, _
from odoo.exceptions import UserError


class L10nUaBankVstImport(models.TransientModel):
    """Майстер імпорту CSV-виписки iBank 2 UA (VST Bank) — #196."""
    _name = 'l10n_ua.bank.vst.import'
    _description = 'VST Bank Statement Import (iBank 2 UA CSV)'

    config_id = fields.Many2one(
        'l10n_ua.bank.sync.config', string='Bank Config', required=True,
        domain="[('provider', '=', 'vst')]")
    statement_file = fields.Binary(string='CSV Statement', required=True)
    file_name = fields.Char(string='File Name')
    date_from = fields.Date(
        string='Date From', default=fields.Date.context_today)
    date_to = fields.Date(
        string='Date To', default=fields.Date.context_today)

    def action_import(self):
        self.ensure_one()
        if self.config_id.provider != 'vst':
            raise UserError(_('Оберіть конфігурацію з провайдером VST Bank.'))
        try:
            content = base64.b64decode(self.statement_file).decode(
                'cp1251', 'replace')
        except Exception as exc:  # noqa: BLE001
            raise UserError(_('Не вдалося прочитати файл: %s') % exc)

        job = self.env['l10n_ua.bank.sync.job'].create({
            'config_id': self.config_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'raw_payload': json.dumps({'csv': content}, ensure_ascii=False),
            'payload_fetched_at': fields.Datetime.now(),
            'source_type': 'file',
            'source_ref': self.file_name or 'iBank2.csv',
            'state': 'fetched',
        })
        job.action_process()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Statement Import'),
            'res_model': 'l10n_ua.bank.sync.job',
            'res_id': job.id,
            'view_mode': 'form',
            'target': 'current',
        }
