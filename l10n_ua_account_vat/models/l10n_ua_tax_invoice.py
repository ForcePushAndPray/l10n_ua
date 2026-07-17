import base64
import calendar
import io
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

VAT_RATE_SELECTION = [
    ('20', '20%'),
    ('14', '14%'),
    ('7', '7%'),
    ('0', '0%'),
    ('exempt', 'Звільнено'),
]


class L10nUaTaxInvoice(models.Model):
    _name = 'l10n_ua.tax.invoice'
    _description = 'Tax Invoice (Податкова накладна)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, number desc'

    name = fields.Char(
        string='Назва',
        compute='_compute_name',
        store=True,
    )
    doc_type = fields.Selection(
        selection=[
            ('pn', 'ПН (Податкова накладна)'),
            ('rk', 'РК (Розрахунок коригування)'),
        ],
        string='Тип документа',
        default='pn',
        required=True,
        tracking=True,
    )
    number = fields.Char(
        string='Номер',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Дата складання',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    invoice_type = fields.Selection(
        selection=[
            ('issued', 'Видана'),
            ('received', 'Отримана'),
        ],
        string='Тип',
        required=True,
        default='issued',
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Контрагент',
        required=True,
        tracking=True,
    )
    partner_ipn = fields.Char(
        related='partner_id.ipn',
        string='ІПН контрагента',
    )
    partner_name = fields.Char(
        related='partner_id.name',
        string='Назва контрагента',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Компанія',
        required=True,
        default=lambda self: self.env.company,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Пов\'язаний рахунок',
    )
    # RK (correction) fields
    original_invoice_id = fields.Many2one(
        'l10n_ua.tax.invoice',
        string='Оригінальна ПН',
        help='Посилання на оригінальну ПН для розрахунку коригування',
    )
    reason = fields.Char(
        string='Причина коригування',
    )
    is_import = fields.Boolean(
        string='Імпортна операція',
        default=False,
    )
    # Lines
    line_ids = fields.One2many(
        'l10n_ua.tax.invoice.line',
        'tax_invoice_id',
        string='Рядки',
    )
    # Totals
    total_base = fields.Monetary(
        string='База оподаткування',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_vat = fields.Monetary(
        string='Сума ПДВ',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_amount = fields.Monetary(
        string='Загальна сума',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    # State
    state = fields.Selection(
        selection=[
            ('draft', 'Чернетка'),
            ('registered', 'Зареєстровано в ЄРПН'),
            ('cancelled', 'Скасовано'),
        ],
        string='Стан',
        default='draft',
        tracking=True,
    )
    # ERPN
    erpn_number = fields.Char(
        string='Номер реєстрації ЄРПН',
        tracking=True,
    )
    erpn_date = fields.Datetime(
        string='Дата реєстрації ЄРПН',
    )
    registration_deadline = fields.Date(
        string='Граничний строк реєстрації',
        compute='_compute_registration_deadline',
        store=True,
        help='Граничний строк реєстрації в ЄРПН (воєнний час)',
    )
    # Received PN tracking
    received_status = fields.Selection(
        selection=[
            ('expected', 'Очікується'),
            ('received', 'Отримано'),
            ('erpn_verified', 'Перевірено в ЄРПН'),
            ('included', 'Включено в декларацію'),
        ],
        string='Статус отримання',
        default='expected',
        tracking=True,
    )
    received_date = fields.Date(
        string='Дата отримання',
        tracking=True,
    )
    erpn_verified_date = fields.Date(
        string='Дата перевірки ЄРПН',
        tracking=True,
    )
    erpn_receipt = fields.Text(
        string='Квитанція ЄРПН',
        readonly=True,
        copy=False,
        help='Відповідь/квитанція кабінету ДПС про реєстрацію податкової накладної.',
    )
    is_overdue = fields.Boolean(
        string='Прострочено',
        compute='_compute_is_overdue',
        store=True,
    )

    # XML
    file_xml = fields.Binary(
        string='XML файл',
        attachment=True,
    )
    file_xml_name = fields.Char(
        string='Ім\'я XML файлу',
    )

    @api.depends('doc_type', 'number', 'date')
    def _compute_name(self):
        for rec in self:
            prefix = 'ПН' if rec.doc_type == 'pn' else 'РК'
            if rec.number and rec.date:
                rec.name = f'{prefix} {rec.number} від {rec.date}'
            else:
                rec.name = _('Нова')

    @api.depends('line_ids.base_amount', 'line_ids.vat_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_base = sum(rec.line_ids.mapped('base_amount'))
            rec.total_vat = sum(rec.line_ids.mapped('vat_amount'))
            rec.total_amount = rec.total_base + rec.total_vat

    @api.depends('date', 'company_id.l10n_ua_erpn_deadline_mode')
    def _compute_registration_deadline(self):
        """ERPN registration deadlines depending on company mode.

        Wartime (default):
        - 1st-15th of month → 5th of next month
        - 16th-end of month → 18th of next month

        Peacetime:
        - 1st-15th of month → last day of same month
        - 16th-end of month → 15th of next month
        """
        for rec in self:
            if not rec.date:
                rec.registration_deadline = False
                continue
            d = rec.date
            mode = rec.company_id.l10n_ua_erpn_deadline_mode or 'wartime'
            next_month_first = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            if mode == 'wartime':
                if d.day <= 15:
                    rec.registration_deadline = next_month_first.replace(day=5)
                else:
                    rec.registration_deadline = next_month_first.replace(day=18)
            else:  # peacetime
                if d.day <= 15:
                    last_day = calendar.monthrange(d.year, d.month)[1]
                    rec.registration_deadline = d.replace(day=last_day)
                else:
                    rec.registration_deadline = next_month_first.replace(day=15)

    @api.depends('registration_deadline', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = (
                rec.state == 'draft'
                and rec.registration_deadline
                and rec.registration_deadline < today
            )

    def action_mark_received(self):
        """Mark received PN as received with today's date."""
        self.write({
            'received_status': 'received',
            'received_date': fields.Date.context_today(self),
        })

    def action_mark_erpn_verified(self):
        """Mark received PN as verified in ERPN."""
        self.write({
            'received_status': 'erpn_verified',
            'erpn_verified_date': fields.Date.context_today(self),
        })

    def _get_cabinet_config(self):
        """Активна конфігурація кабінету ДПС для компанії накладної (або UserError)."""
        self.ensure_one()
        Config = self.env.get('l10n_ua.tax.cabinet.config')
        if Config is None:
            raise UserError(_(
                'Модуль інтеграції з кабінетом ДПС (l10n_ua_tax_cabinet) '
                'не встановлено — реєстрація в ЄРПН неможлива.'))
        config = Config.search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ], limit=1)
        if not config:
            raise UserError(_(
                'Не налаштовано кабінет ДПС / КЕП для компанії «%s». '
                'Створіть конфігурацію (Кабінет ДПС) перед реєстрацією в ЄРПН.'
            ) % self.company_id.display_name)
        return config

    def action_register_erpn(self):
        """Відкрити клієнтське КЕП-підписування для реальної реєстрації в ЄРПН (#146).

        Більше не фейковий фліп статусу: гарантує наявність XML і конфігурації
        кабінету, а далі відкриває браузерний віджет підпису. Статус
        'registered' виставляється лише після квитанції ДПС у erpn_submit_signed.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Можна реєструвати тільки чернетки.'))
        if not self.file_xml:
            self.action_generate_xml()
        self._get_cabinet_config()  # валідація: інакше чіткий UserError
        return {
            'type': 'ir.actions.client',
            'tag': 'l10n_ua_tax_cabinet.erpn_sign',
            'params': {'model': self._name, 'res_id': self.id},
        }

    def erpn_prepare_signing(self):
        """Дані для браузерного підпису: XML, taxpayer_code, сертифікат ДПС, ім'я файлу.

        Викликається OWL-віджетом через ORM. Приватний ключ/пароль тут не
        фігурують — підпис робиться в браузері.
        """
        self.ensure_one()
        if not self.file_xml:
            self.action_generate_xml()
        config = self._get_cabinet_config()
        # Сертифікат шифрування ДПС потрібен лише для конверта (envelope).
        # Поточний клієнтський потік підписує (SignData) без шифрування, тож
        # недоступність cert (напр. застарілий URL → 404) не має блокувати
        # підпис — повертаємо порожньо й логуємо.
        dps_cert = None
        try:
            dps_cert = config._get_dps_encrypt_certificate()
        except Exception as e:
            _logger.warning(
                'DPS cert недоступний (%s) — підпис без конверта.', e)
        return {
            'xml_b64': (self.file_xml or b'').decode()
            if isinstance(self.file_xml, bytes) else (self.file_xml or ''),
            'taxpayer_code': config.taxpayer_code or '',
            'dps_cert_b64': base64.b64encode(dps_cert).decode() if dps_cert else '',
            'filename': self._generate_xml_filename(),
        }

    def erpn_submit_signed(self, auth_signature_b64, envelope_b64, filename):
        """Релей підписаного в браузері конверта до ЄРПН і фіксація результату.

        auth_signature_b64 — підпис taxpayer_code (заголовок Authorization),
        envelope_b64 — sign+encrypt конверт на сертифікат ДПС. Обидва створені
        в браузері. Статус 'registered' — лише за успішною квитанцією.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Можна реєструвати тільки чернетки.'))
        config = self._get_cabinet_config()
        result = config._api_submit_document_presigned(
            envelope_b64, filename, auth_signature_b64)
        receipt = result.get('message') if isinstance(result, dict) else str(result)
        self.write({
            'state': 'registered',
            'erpn_date': fields.Datetime.now(),
            'erpn_receipt': receipt,
        })
        self.message_post(body=_('Зареєстровано в ЄРПН. Квитанція: %s') % (receipt or '—'))
        return {'state': 'registered', 'receipt': receipt}

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_generate_xml(self):
        """Generate XML for tax invoice per Наказ Мінфіну №1307."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('XML можна генерувати тільки для чернеток.'))

        xml = self._build_xml()
        xml_bytes = xml.encode('windows-1251')
        self.write({
            'file_xml': base64.b64encode(xml_bytes),
            'file_xml_name': self._generate_xml_filename(),
        })

    def _generate_xml_filename(self):
        """Generate filename per Order №729 pattern."""
        self.ensure_one()
        company = self.company_id
        edrpou = company.company_registry or company.vat or '000000000'
        # J for legal entity, F for FOP
        entity = 'J' if company.company_registry else 'F'
        date_str = (self.date or fields.Date.today()).strftime('%Y%m%d%H%M%S')
        return f'{entity}1201011_{edrpou}_{date_str}_1.xml'

    def _build_xml(self):
        """Build basic XML structure for tax invoice."""
        self.ensure_one()
        company = self.company_id
        seller_ipn = company.l10n_ua_vat_ipn or company.vat or company.company_registry or ''
        buyer_ipn = self.partner_ipn or ''

        lines_xml = []
        for i, line in enumerate(self.line_ids, 1):
            rate_code = {
                '20': '20',
                '14': '14',
                '7': '7',
                '0': '0',
                'exempt': '903',  # code for exempt
            }.get(line.vat_rate, '20')
            lines_xml.append(
                f'    <RYADOK ROWNUM="{i}">'
                f'<OBSAG>{line.name or ""}</OBSAG>'
                f'<KODU>{line.uktzed_code or ""}</KODU>'
                f'<KODP>{line.dkpp_code or ""}</KODP>'
                f'<ODINICI>{line.uom_id.name if line.uom_id else "шт."}</ODINICI>'
                f'<KILK>{line.quantity:.6f}</KILK>'
                f'<CINA>{line.price_unit:.2f}</CINA>'
                f'<KOD_STAVKI>{rate_code}</KOD_STAVKI>'
                f'<KOD_PILGI>{line.benefit_code or ""}</KOD_PILGI>'
                f'<OBSAG_BEZ_PDV>{line.base_amount:.2f}</OBSAG_BEZ_PDV>'
                f'<SUMA_PDV>{line.vat_amount:.2f}</SUMA_PDV>'
                f'</RYADOK>'
            )
        lines_str = '\n'.join(lines_xml)

        xml = f"""<?xml version="1.0" encoding="windows-1251"?>
<DECLAR>
  <DECLARBODY>
    <HNUM>{self.number}</HNUM>
    <HDATE>{self.date.strftime('%d%m%Y')}</HDATE>
    <HTYPE>{'00' if self.doc_type == 'pn' else '01'}</HTYPE>
    <SELLER_IPN>{seller_ipn}</SELLER_IPN>
    <SELLER_NAME>{company.name}</SELLER_NAME>
    <BUYER_IPN>{buyer_ipn}</BUYER_IPN>
    <BUYER_NAME>{self.partner_id.name}</BUYER_NAME>
    <IS_IMPORT>{'1' if self.is_import else '0'}</IS_IMPORT>
    <RYADKI>
{lines_str}
    </RYADKI>
    <ZAGALNA_SUMA_BEZ_PDV>{self.total_base:.2f}</ZAGALNA_SUMA_BEZ_PDV>
    <ZAGALNA_SUMA_PDV>{self.total_vat:.2f}</ZAGALNA_SUMA_PDV>
    <ZAGALNA_SUMA>{self.total_amount:.2f}</ZAGALNA_SUMA>
  </DECLARBODY>
</DECLAR>"""
        return xml


class L10nUaTaxInvoiceLine(models.Model):
    _name = 'l10n_ua.tax.invoice.line'
    _description = 'Tax Invoice Line'
    _order = 'sequence, id'

    tax_invoice_id = fields.Many2one(
        'l10n_ua.tax.invoice',
        string='Податкова накладна',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(
        string='Послідовність',
        default=10,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Товар/Послуга',
    )
    name = fields.Char(
        string='Опис (номенклатура)',
        required=True,
    )
    uktzed_code = fields.Char(
        string='Код УКТ ЗЕД',
        help='Код товару згідно з УКТ ЗЕД (для товарів)',
    )
    dkpp_code = fields.Char(
        string='Код ДКПП',
        help='Код послуги згідно з ДКПП (для послуг)',
    )
    is_import = fields.Boolean(
        string='Імпорт',
        default=False,
    )
    is_own_agro = fields.Boolean(
        string='Власна с/г продукція',
        default=False,
    )
    benefit_code = fields.Char(
        string='Код пільги',
    )
    quantity = fields.Float(
        string='Кількість',
        default=1.0,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Одиниця виміру',
    )
    price_unit = fields.Monetary(
        string='Ціна без ПДВ',
        currency_field='currency_id',
    )
    base_amount = fields.Monetary(
        string='База оподаткування',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    vat_rate = fields.Selection(
        selection=VAT_RATE_SELECTION,
        string='Ставка ПДВ',
        default='20',
    )
    vat_amount = fields.Monetary(
        string='Сума ПДВ',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='tax_invoice_id.currency_id',
    )

    @api.depends('quantity', 'price_unit', 'vat_rate')
    def _compute_amounts(self):
        rates = {'20': 0.20, '14': 0.14, '7': 0.07, '0': 0.0}
        for line in self:
            line.base_amount = line.quantity * line.price_unit
            rate = rates.get(line.vat_rate, 0.0)
            line.vat_amount = line.base_amount * rate
