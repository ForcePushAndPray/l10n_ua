"""Імпорт виписки ПриватБанку з XLS (Приват24 Бізнес)."""

import base64
import io
from datetime import date

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError

try:
    import xlwt
except ImportError:  # pragma: no cover
    xlwt = None


@tagged('post_install', '-at_install')
class TestPrivatXls(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env['account.journal'].create({
            'name': 'Privat XLS', 'type': 'bank', 'code': 'PXLS',
            'company_id': cls.env.company.id})
        cls.cfg = cls.env['l10n_ua.bank.sync.config'].create({
            'name': 'Privat XLS', 'provider': 'privat_xls',
            'journal_id': cls.journal.id})

    def _make_xls(self):
        """Мінімальна виписка у форматі Приват24 Бізнес (BIFF8)."""
        wb = xlwt.Workbook()
        sh = wb.add_sheet('Лист1')
        sh.write(0, 0, 'АТ КБ "ПРИВАТБАНК"')  # шапка-шум
        headers = ['№ документа', 'Дата операції', 'Час операції', 'Сума',
                   'Валюта', 'Призначення платежу', 'ЄДРПОУ/РНОКПП',
                   'Назва контрагента', 'Рахунок контрагента',
                   'МФО контрагента', 'Референс']
        hr = 2
        for c, h in enumerate(headers):
            sh.write(hr, c, h)
        rows = [
            ['Q1', '22.07.2026', '11:33:00', -100000.0, 'UAH', 'Видача готівки',
             14360570, 'Каса', 'UA5030529900000100250207', 305299, 'REF1'],
            ['Q2', '21.07.2026', '09:00:00', 750.0, 'UAH', 'Оплата послуг',
             12345678, 'ТОВ Контрагент', 'UA1112223334445556667', '305299', 'REF2'],
            ['Q3', '20.11.2021', '16:57:00', 500.0, 'UAH', '#ПЕРЕНЕСЕННЯ ЗАЛИШКУ',
             2940910418, 'ФОП', 'UA263333910000026007', 333391, 'REFB'],
        ]
        for i, row in enumerate(rows):
            for c, v in enumerate(row):
                sh.write(hr + 1 + i, c, v)
        bio = io.BytesIO()
        wb.save(bio)
        return bio.getvalue()

    def test_source_type_is_file(self):
        self.assertEqual(self.cfg._source_type(), 'file')
        self.assertEqual(self.cfg.exchange_type, 'file')

    def test_fetch_from_bank_blocked(self):
        # Файловий провайдер не синхронізується онлайн.
        with self.assertRaises(UserError):
            self.cfg._fetch_from_bank(date(2026, 7, 1), date(2026, 7, 31))

    def test_file_to_payload_base64(self):
        if xlwt is None:
            self.skipTest('xlwt not installed')
        payload = self.cfg._file_to_payload(self._make_xls(), 'stmt.xls')
        self.assertIn('privat_xls_b64', payload)
        # JSON-безпечний (рядок base64)
        self.assertIsInstance(payload['privat_xls_b64'], str)
        base64.b64decode(payload['privat_xls_b64'])  # не кидає

    def test_parse_transactions(self):
        if xlwt is None:
            self.skipTest('xlwt not installed')
        payload = self.cfg._file_to_payload(self._make_xls(), 'stmt.xls')
        txs = self.cfg._parse_transactions(payload)
        # 2 реальні операції; рядок #ПЕРЕНЕСЕННЯ ЗАЛИШКУ пропущено
        self.assertEqual(len(txs), 2)
        self.assertFalse(any('ПЕРЕНЕСЕННЯ' in t['description'] for t in txs))

        t0 = txs[0]
        self.assertEqual(t0['date'], '2026-07-22')
        self.assertAlmostEqual(t0['amount'], -100000.0, places=2)
        self.assertEqual(t0['id'], 'REF1')
        self.assertEqual(t0['description'], 'Видача готівки')
        # Числовий ЄДРПОУ → рядок без '.0'
        self.assertEqual(t0['partner_edrpou'], '14360570')
        self.assertEqual(t0['partner_iban'], 'UA5030529900000100250207')

        # Знаки: списання (−) і надходження (+) присутні
        self.assertTrue(any(t['amount'] < 0 for t in txs))
        self.assertTrue(any(t['amount'] > 0 for t in txs))
