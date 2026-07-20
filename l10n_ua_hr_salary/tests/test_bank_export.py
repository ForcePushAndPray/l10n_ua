"""Тести експорту зарплатного файлу для клієнт-банку (#152)."""

import base64
import struct
from datetime import date

from lxml import etree

from .common import SalaryTestCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestBankExport(SalaryTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Вимкнути перевірку контрольної суми РНОКПП у тестах.
        cls.env['ir.config_parameter'].sudo().set_param(
            'hr_ua.validate_rnokpp', 'False')
        cls.employee.rnokpp = '1234567890'
        partner = cls.env['res.partner'].create({'name': 'Петренко О.М.'})
        cls.bank = cls.env['res.partner.bank'].create({
            'acc_number': '26001234567890',
            'partner_id': partner.id,
        })
        cls.employee.bank_account_id = cls.bank.id

    def _done_payslip(self):
        slip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'version_id': self.version.id,
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
        })
        slip.action_compute_sheet()
        slip.write({'state': 'done'})
        return slip

    def _wizard(self, **kw):
        vals = {
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
            'payment_purpose': 'Заробітна плата за {period}',
        }
        vals.update(kw)
        return self.env['hr.payslip.bank.export'].create(vals)

    def test_xml_export(self):
        slip = self._done_payslip()
        wiz = self._wizard(file_format='xml')
        wiz.action_generate()
        self.assertEqual(wiz.state, 'done')
        self.assertTrue(wiz.file_name.endswith('.xml'))
        content = base64.b64decode(wiz.file_data)
        root = etree.fromstring(content)
        self.assertEqual(root.tag, 'PaymentPackage')
        payments = root.findall('Payment')
        self.assertEqual(len(payments), 1)
        p = payments[0]
        self.assertEqual(p.findtext('Rnokpp'), '1234567890')
        self.assertEqual(p.findtext('Account'), '26001234567890')
        self.assertEqual(p.findtext('Amount'), f'{slip.net_salary:.2f}')
        self.assertEqual(p.findtext('Purpose'), 'Заробітна плата за 06.2025')
        self.assertEqual(root.get('count'), '1')

    def test_dbf_export(self):
        slip = self._done_payslip()
        wiz = self._wizard(file_format='dbf')
        wiz.action_generate()
        self.assertTrue(wiz.file_name.endswith('.dbf'))
        b = base64.b64decode(wiz.file_data)
        version, = struct.unpack('<B', b[:1])
        nrec, = struct.unpack('<I', b[4:8])
        hlen, = struct.unpack('<H', b[8:10])
        self.assertEqual(version, 0x03)
        self.assertEqual(nrec, 1)
        # Перший запис: прапорець(1) + NN(5) + OKPO(10) → OKPO у 6..16.
        rec = b[hlen:]
        okpo = rec[6:16].decode('cp1251').strip()
        self.assertEqual(okpo, '1234567890')

    def test_missing_account_raises(self):
        self._done_payslip()
        self.employee.bank_account_id = False
        wiz = self._wizard(file_format='xml')
        with self.assertRaises(UserError):
            wiz.action_generate()

    def test_no_done_payslip_raises(self):
        # Листок у чернетці — не потрапляє у вибірку.
        self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'version_id': self.version.id,
            'date_from': date(2025, 6, 1),
            'date_to': date(2025, 6, 30),
        })
        wiz = self._wizard(file_format='xml')
        with self.assertRaises(UserError):
            wiz.action_generate()

    def test_run_defaults_period(self):
        run = self.env['hr.payslip.run'].create({
            'name': 'Червень 2025',
            'date_start': date(2025, 6, 1),
            'date_end': date(2025, 6, 30),
        })
        slip = self._done_payslip()
        slip.payslip_run_id = run.id
        wiz = self.env['hr.payslip.bank.export'].create({
            'payslip_run_id': run.id, 'file_format': 'xml'})
        wiz.action_generate()
        root = etree.fromstring(base64.b64decode(wiz.file_data))
        self.assertEqual(len(root.findall('Payment')), 1)
