"""Інформаційні запити до ДПС (через кабінет, з КЕП-підписом).

Формування й подання з Odoo: J1300208 «Запит щодо отримання витягу з ІКС ДПС
про стан розрахунків платника» (додаток 1 до Порядку, наказ Мінфіну від
20.08.2025 № 416, чинний з 14.01.2026; до нього — J1300205). Модель наслідує
l10n_ua.dps.submit.mixin, тож підпис і подання — той самий універсальний потік,
що й для декларацій/накладних. Структуру XML звірено з офіційним XSD ДПС
(tests/schemas/J1300208.xsd, СКЗ 1.34.9.0).

Імпорт з Електронного кабінету: запит F1319104 «Відомості з ДРФО про доходи» і
відповідь на нього F1419104 — запит з'являється в «Запитах до ДПС», відповідь
прив'язується до нього за запитаним періодом (рядок R0401).
"""

import base64
import re
from datetime import date, datetime
from xml.sax.saxutils import escape

from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Реквізити форми запиту (fixed-значення з XSD ДПС).
REQUEST_FORMS = {
    'j1300208': {
        'c_doc': 'J13', 'c_doc_sub': '002', 'c_doc_ver': '8',
        'label': 'Стан розрахунків з бюджетом (витяг)',
    },
}
# Вид витягу: позначки M01–M05 бланка запиту в порядку їх розміщення.
# Без позначки — електронний витяг з кваліфікованою печаткою ДПС без пені.
EXTRACT_OPTIONS = [
    ('m01', 'Електронний з КЕП керівника ДПС — узагальнюючі показники'),
    ('m02', 'Електронний з КЕП керівника ДПС — у розрізі платежів'),
    ('m03', 'Паперовий — узагальнюючі показники'),
    ('m04', 'Паперовий — у розрізі платежів'),
    ('m05', 'Електронний з печаткою ДПС — з розрахунком пені'),
]
SOFTWARE = 'Odoo l10n_ua'

# Запити, які подаються в кабінеті й лише імпортуються: код форми запиту → тип,
# код форми відповіді → тип запиту, на який вона відповідає.
IMPORTED_REQUESTS = {'F1319104': 'f1319104'}
IMPORTED_RESPONSES = {'F1419104': 'f1319104'}
MONTHS_UK = {name: i for i, name in enumerate((
    'січень', 'лютий', 'березень', 'квітень', 'травень', 'червень', 'липень',
    'серпень', 'вересень', 'жовтень', 'листопад', 'грудень'), start=1)}


class L10nUaTaxRequest(models.Model):
    _name = 'l10n_ua.tax.request'
    _description = 'Інформаційний запит до ДПС'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'l10n_ua.dps.submit.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    request_type = fields.Selection(
        selection=[('j1300208', 'Стан розрахунків з бюджетом (J1300208)'),
                   ('j1300205', 'Стан розрахунків з бюджетом (J1300205, до 2026)'),
                   ('f1319104', 'Відомості з ДРФО про доходи (F1319104)')],
        string='Тип запиту', required=True, default='j1300208', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Компанія', required=True,
        default=lambda self: self.env.company)
    request_date = fields.Date(
        string='Дата запиту', required=True,
        default=fields.Date.context_today, tracking=True)
    state = fields.Selection(
        selection=[('draft', 'Чернетка'), ('generated', 'Сформовано'),
                   ('submitted', 'Подано'), ('answered', 'Отримано відповідь')],
        default='draft', tracking=True, copy=False)
    submission_date = fields.Date(string='Дата подання', copy=False)
    xml_file = fields.Binary(string='XML-файл', attachment=True, copy=False)
    xml_filename = fields.Char(copy=False)
    response_receipt = fields.Text(string='Квитанція', readonly=True, copy=False)
    period_from = fields.Date(string='Період з', copy=False)
    period_to = fields.Date(string='Період по', copy=False)
    extract_option = fields.Selection(
        EXTRACT_OPTIONS, string='Вид витягу',
        help='Порожньо — електронний витяг з кваліфікованою печаткою ДПС, без '
             'розрахунку пені. Пеня розраховується на дату формування запиту, '
             'якщо є податковий борг (крім ЄСВ).')
    tax_document_id = fields.Many2one(
        'l10n_ua.tax.document', string='Поданий запит', copy=False,
        index='btree_not_null', ondelete='set null')
    response_document_id = fields.Many2one(
        'l10n_ua.tax.document', string='Відповідь ДПС', copy=False,
        index='btree_not_null', ondelete='set null',
        help='Документ-відповідь із кабінету (XML і PDF).')

    @api.depends('request_type', 'request_date', 'period_from', 'period_to')
    def _compute_name(self):
        labels = dict(self._fields['request_type'].selection)
        for rec in self:
            label = labels.get(rec.request_type, _('Запит'))
            if rec.period_from and rec.period_to:
                rec.name = _('%(label)s за %(start)s–%(end)s',
                             label=label, start=rec.period_from.strftime('%m.%Y'),
                             end=rec.period_to.strftime('%m.%Y'))
            else:
                rec.name = '%s %s' % (label, rec.request_date or '')

    # --- генерація XML ---

    def action_generate_xml(self):
        for rec in self:
            if rec.request_type not in REQUEST_FORMS:
                raise UserError(_(
                    'Формування цього запиту в Odoo ще не підтримується. Подайте його в '
                    'Електронному кабінеті — запит і відповідь з\'являться тут після '
                    'синхронізації.'))
            xml = rec._render_request_xml(rec._request_vals())
            rec.xml_file = base64.b64encode(xml.encode('windows-1251'))
            form = REQUEST_FORMS[rec.request_type]
            edrpou = re.sub(r'\D', '', rec._request_edrpou(rec.company_id))
            rec.xml_filename = '%s%s%s_%s_%s.xml' % (
                form['c_doc'], form['c_doc_sub'], form['c_doc_ver'],
                edrpou, (rec.request_date or date.today()).strftime('%Y%m%d'))
            rec.state = 'generated'
        return True

    @staticmethod
    def _request_edrpou(company):
        """Код ЄДРПОУ компанії; `company_registry`/`vat` — запасні джерела."""
        return company.edrpou or company.company_registry or company.vat or ''

    def _request_vals(self):
        """Зібрати реквізити запиту (компанія + період). Відсутні обов'язкові —
        явний UserError (не підставляємо фейк у документ для ДПС)."""
        self.ensure_one()
        company = self.company_id
        edrpou = re.sub(r'\D', '', self._request_edrpou(company))
        office = company.tax_office_code or ''
        missing = []
        if not edrpou:
            missing.append(_('код ЄДРПОУ компанії'))
        if not office:
            missing.append(_('код ДПІ компанії (tax_office_code)'))
        if missing:
            raise UserError(_(
                'Для формування запиту заповніть: %s.') % ', '.join(missing))
        d = self.request_date or date.today()
        # Один запит — один рік: з першого дня місяця «з» до дати «по».
        start = self.period_from or date(d.year, 1, 1)
        end = self.period_to or d
        if end < start or end.year != start.year:
            raise UserError(_(
                'Період запиту має лежати в межах одного року і закінчуватися не '
                'раніше, ніж починається.'))
        office_name = company.l10n_ua_tax_office_id.name or self.env[
            'l10n_ua.tax.office'].search([('code', '=', office)], limit=1).name
        if not office_name:
            raise UserError(_(
                'Для формування запиту вкажіть податковий орган компанії '
                '(назва ДПС за основним місцем обліку).'))
        form = REQUEST_FORMS[self.request_type]
        return {
            'c_doc': form['c_doc'], 'c_doc_sub': form['c_doc_sub'],
            'c_doc_ver': form['c_doc_ver'],
            'tin': edrpou,
            'c_reg': int(office[:2]) if len(office) >= 2 else 0,
            'c_raj': int(office[2:4]) if len(office) >= 4 else 0,
            'period_month': d.month,
            'period_type': 1,
            'period_year': d.year,
            'c_sti_orig': office,
            'd_fill': d.strftime('%d%m%Y'),
            'hname': company._l10n_ua_dps_name(),
            'hsti': office_name,
            'month_from': start.month,
            'year_from': start.year,
            'date_to': end.strftime('%d%m%Y'),
            'option': self.extract_option and self.extract_option.upper(),
        }

    @api.model
    def _render_request_xml(self, vals):
        """Стейтлес-рендер XML запиту (J1300208 v8), валідний за XSD ДПС.

        Кодування windows-1251. Порядок елементів звірено з J1300208.xsd
        (DHead: fixed J13/002/8, D_FILL/SOFTWARE; DBody: HSTI, HMONTH1,
        HYEAR1, HDATE1, HNAME, HTIN, одна з позначок M01–M05).
        """
        def esc(v):
            return escape(str(v or ''))

        return '\n'.join([
            '<?xml version="1.0" encoding="windows-1251"?>',
            '<DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:noNamespaceSchemaLocation="%s%s%s.xsd">' % (
                vals['c_doc'], vals['c_doc_sub'], vals['c_doc_ver']),
            '    <DECLARHEAD>',
            '        <TIN>%s</TIN>' % esc(vals['tin']),
            '        <C_DOC>%s</C_DOC>' % vals['c_doc'],
            '        <C_DOC_SUB>%s</C_DOC_SUB>' % vals['c_doc_sub'],
            '        <C_DOC_VER>%s</C_DOC_VER>' % vals['c_doc_ver'],
            '        <C_DOC_TYPE>0</C_DOC_TYPE>',
            '        <C_DOC_CNT>1</C_DOC_CNT>',
            '        <C_REG>%s</C_REG>' % vals['c_reg'],
            '        <C_RAJ>%s</C_RAJ>' % vals['c_raj'],
            '        <PERIOD_MONTH>%s</PERIOD_MONTH>' % vals['period_month'],
            '        <PERIOD_TYPE>%s</PERIOD_TYPE>' % vals['period_type'],
            '        <PERIOD_YEAR>%s</PERIOD_YEAR>' % vals['period_year'],
            '        <C_STI_ORIG>%s</C_STI_ORIG>' % esc(vals['c_sti_orig']),
            '        <C_DOC_STAN>1</C_DOC_STAN>',
            '        <D_FILL>%s</D_FILL>' % vals['d_fill'],
            '        <SOFTWARE>%s</SOFTWARE>' % SOFTWARE,
            '    </DECLARHEAD>',
            '    <DECLARBODY>',
            '        <HSTI>%s</HSTI>' % esc(vals['hsti']),
            '        <HMONTH1>%s</HMONTH1>' % vals['month_from'],
            '        <HYEAR1>%s</HYEAR1>' % vals['year_from'],
            '        <HDATE1>%s</HDATE1>' % vals['date_to'],
            '        <HNAME>%s</HNAME>' % esc(vals['hname']),
            '        <HTIN>%s</HTIN>' % esc(vals['tin']),
        ] + (['        <%s>1</%s>' % (vals['option'], vals['option'])]
             if vals.get('option') else []) + [
            '    </DECLARBODY>',
            '</DECLAR>',
        ])

    # --- дії/стан ---

    def action_submit(self):
        """Відкрити КЕП-підпис і подання запиту до ДПС."""
        return self.action_kep_submit()

    def action_draft(self):
        self.write({'state': 'draft', 'submission_date': False})

    # --- контракт l10n_ua.dps.submit.mixin ---

    def _dps_ensure_xml(self):
        self.ensure_one()
        if not self.xml_file:
            self.action_generate_xml()

    def _dps_submit_label(self):
        return _('Подати запит до ДПС')

    def _dps_on_submitted(self, receipt):
        self.write({
            'state': 'submitted',
            'submission_date': fields.Date.context_today(self),
            'response_receipt': receipt,
        })
        self.message_post(body=_('Запит подано до ДПС. Квитанція: %s') % (receipt or '—'))

    def action_open_response(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ua.tax.document',
            'res_id': self.response_document_id.id,
            'view_mode': 'form',
        }

    # --- імпорт з Електронного кабінету ---

    @api.model
    def _parse_request_period(self, xml_bytes):
        """(дата запиту, період з, період по) з XML запиту/відповіді ДРФО (рядок R0401)."""
        root = etree.fromstring(xml_bytes)
        body = root.find('DECLARBODY')
        head = root.find('DECLARHEAD')
        if body is None:
            return None, None, None

        def text(node, tag):
            el = node.find(tag) if node is not None else None
            return (el.text or '').strip() if el is not None and el.text else ''

        def month(tag):
            value = text(body, tag) or text(body, tag + 'S')
            return int(value) if value.isdigit() else MONTHS_UK.get(value.lower())

        filled = text(head, 'D_FILL') or text(body, 'HFILL')
        try:
            filled = datetime.strptime(filled, '%d%m%Y').date() if filled else None
        except ValueError:
            filled = None
        m_from, y_from = month('R0401G1'), text(body, 'R0401G2')
        m_to, y_to = month('R0401G3'), text(body, 'R0401G4')
        if not (m_from and m_to and y_from.isdigit() and y_to.isdigit()):
            return filled, None, None
        start = date(int(y_from), m_from, 1)
        end = date(int(y_to) + m_to // 12, m_to % 12 + 1, 1)
        return filled, start, date.fromordinal(end.toordinal() - 1)

    @api.model
    def _import_from_tax_document(self, doc, code):
        """Запит ДРФО з кабінету → «Запити до ДПС»; відповідь — до свого запиту."""
        is_response = code in IMPORTED_RESPONSES
        request_type = IMPORTED_RESPONSES.get(code) or IMPORTED_REQUESTS.get(code)
        filled, start, end = self._parse_request_period(base64.b64decode(doc.file_xml))
        filled = filled or doc.document_date
        company = doc.company_id or self.env.company
        link = 'response_document_id' if is_response else 'tax_document_id'
        if self.search([(link, '=', doc.id)], limit=1):
            return self.browse()
        domain = [('company_id', '=', company.id), ('request_type', '=', request_type),
                  ('period_from', '=', start), ('period_to', '=', end),
                  (link, '=', False)]
        if is_response and filled:
            domain.append(('request_date', '<=', filled))
        request = self.search(domain, order='request_date desc, id desc', limit=1)
        if not request:
            request = self.create({
                'request_type': request_type,
                'company_id': company.id,
                'request_date': filled,
                'submission_date': filled,
                'period_from': start,
                'period_to': end,
                'state': 'submitted',
            })
        vals = {link: doc.id}
        if is_response:
            vals['state'] = 'answered'
        elif not request.xml_file:
            vals.update(xml_file=doc.file_xml, xml_filename=doc.file_xml_name)
        request.write(vals)
        number = doc.document_number and _(' № %s') % doc.document_number or ''
        request.message_post(body=(
            _('Отримано відповідь ДПС%s (імпортовано з Електронного кабінету).') if is_response
            else _('Запит подано в Електронному кабінеті%s (імпортовано).')) % number)
        return request
