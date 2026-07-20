import base64

from lxml import etree

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .dbf import build_dbf


class HrPayslipBankExport(models.TransientModel):
    """Майстер формування зарплатного файлу для клієнт-банку (#152).

    Збирає закриті розрахункові листки за період (або з обраної відомості),
    валідує реквізити й суми та формує один пакетний файл (XML або DBF) для
    масової виплати: РНОКПП, ПІБ, IBAN, сума до виплати, призначення платежу.
    """
    _name = 'hr.payslip.bank.export'
    _description = 'Payroll Bank File Export'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    payslip_run_id = fields.Many2one(
        'hr.payslip.run', string='Payslip Batch',
        help='Якщо задано — беруться листки цієї відомості; інакше — за період.')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    file_format = fields.Selection(
        [('xml', 'XML'), ('dbf', 'DBF')], string='Format', required=True,
        default=lambda self: self.env.company.payroll_bank_file_format or 'xml')
    payer_account_id = fields.Many2one(
        'res.partner.bank', string='Payer Account',
        default=lambda self: self.env.company.payroll_bank_account_id)
    payment_purpose = fields.Char(
        string='Payment Purpose',
        default=lambda self: self.env.company.payroll_payment_purpose
        or 'Заробітна плата за {period}')

    file_data = fields.Binary(string='File', readonly=True, attachment=False)
    file_name = fields.Char(string='File Name', readonly=True)
    state = fields.Selection(
        [('choose', 'Choose'), ('done', 'Done')], default='choose')

    @api.onchange('payslip_run_id')
    def _onchange_run(self):
        if self.payslip_run_id:
            self.date_from = self.payslip_run_id.date_start
            self.date_to = self.payslip_run_id.date_end

    def _get_payslips(self):
        self.ensure_one()
        if self.payslip_run_id:
            slips = self.payslip_run_id.slip_ids
        else:
            if not (self.date_from and self.date_to):
                raise UserError(_('Вкажіть період або відомість.'))
            slips = self.env['hr.payslip'].search([
                ('company_id', '=', self.company_id.id),
                ('date_from', '>=', self.date_from),
                ('date_to', '<=', self.date_to),
            ])
        return slips.filtered(lambda s: s.state == 'done')

    def _period_label(self):
        d = self.date_to or (self.payslip_run_id and self.payslip_run_id.date_end)
        return d.strftime('%m.%Y') if d else ''

    def _build_rows(self, slips):
        """Побудувати рядки виплат + валідація реквізитів і сум."""
        period = self._period_label()
        rows = []
        missing_account = []
        skipped_zero = 0
        for slip in slips:
            employee = slip.employee_id
            amount = round(slip.net_salary, 2)
            if amount <= 0:
                skipped_zero += 1
                continue
            bank = employee.bank_account_id
            if not bank or not bank.acc_number:
                missing_account.append(employee.name)
                continue
            purpose = (self.payment_purpose or '').format(
                period=period, employee=employee.name or '',
                rnokpp=employee.rnokpp or '')
            rows.append({
                'rnokpp': employee.rnokpp or '',
                'name': employee.name or '',
                'account': (bank.acc_number or '').replace(' ', ''),
                'amount': amount,
                'purpose': purpose,
            })
        if missing_account:
            raise UserError(_(
                'Немає банківського рахунку (IBAN) у працівників:\n- %s'
            ) % '\n- '.join(missing_account))
        if not rows:
            raise UserError(_(
                'Немає рядків для виплати (усі суми нульові або немає '
                'закритих листків за період).'))
        return rows, skipped_zero

    def _render_xml(self, rows):
        period = self._period_label()
        total = sum(r['amount'] for r in rows)
        root = etree.Element('PaymentPackage')
        root.set('company', self.company_id.name or '')
        root.set('payer_account',
                 (self.payer_account_id.acc_number or '').replace(' ', ''))
        root.set('period', period)
        root.set('count', str(len(rows)))
        root.set('total', f'{total:.2f}')
        for r in rows:
            p = etree.SubElement(root, 'Payment')
            etree.SubElement(p, 'Rnokpp').text = r['rnokpp']
            etree.SubElement(p, 'Name').text = r['name']
            etree.SubElement(p, 'Account').text = r['account']
            etree.SubElement(p, 'Amount').text = f"{r['amount']:.2f}"
            etree.SubElement(p, 'Purpose').text = r['purpose']
        return etree.tostring(
            root, xml_declaration=True, encoding='windows-1251', pretty_print=True)

    def _render_dbf(self, rows):
        field_defs = [
            ('NN', 'N', 5, 0),
            ('OKPO', 'C', 10, 0),
            ('NAME', 'C', 60, 0),
            ('IBAN', 'C', 34, 0),
            ('SUMMA', 'N', 15, 2),
            ('DETAILS', 'C', 160, 0),
        ]
        dbf_rows = []
        for i, r in enumerate(rows, start=1):
            dbf_rows.append({
                'NN': i,
                'OKPO': r['rnokpp'],
                'NAME': r['name'],
                'IBAN': r['account'],
                'SUMMA': r['amount'],
                'DETAILS': r['purpose'],
            })
        return build_dbf(field_defs, dbf_rows)

    def action_generate(self):
        self.ensure_one()
        slips = self._get_payslips()
        if not slips:
            raise UserError(_('Немає закритих (Done) листків за вибором.'))
        rows, _skipped = self._build_rows(slips)
        if self.file_format == 'dbf':
            content = self._render_dbf(rows)
            ext = 'dbf'
        else:
            content = self._render_xml(rows)
            ext = 'xml'
        self.file_data = base64.b64encode(content)
        self.file_name = 'salary_%s.%s' % (
            self._period_label().replace('.', '_') or 'export', ext)
        self.state = 'done'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
