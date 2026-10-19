"""Синхронізація поданих звітів за всі місяці діапазону років одним підписом."""

from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..wizard import l10n_ua_tax_cabinet_sync_wizard as sync_wizard


@tagged('post_install', '-at_install')
class TestSyncRange(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        config = cls.env['l10n_ua.tax.cabinet.config'].with_context(
            active_test=False).search([('company_id', '=', company.id)], limit=1)
        vals = {'name': 'Кабінет (тест діапазону)', 'taxpayer_code': '1234567890',
                'active': True, 'auto_download_xml': False, 'auto_download_pdf': False}
        if config:
            config.write(vals)
        else:
            config = cls.env['l10n_ua.tax.cabinet.config'].create(
                {**vals, 'company_id': company.id})
        cls.config = config

    def _wizard(self, **kw):
        return self.env['l10n_ua.tax.cabinet.sync.wizard'].create({
            'mode': 'sync', 'config_id': self.config.id, 'sync_type': 'reported',
            'month': 'all', **kw})

    def _list(self, year, month, *, auth_signature):
        self.assertEqual(auth_signature, 'SIG')
        self.calls.append((year, month))
        if month in (3, 12):
            return [{'codRegdoc': '%d%02d' % (year, month), 'doc': 'F0103309',
                     'docName': 'Декларація %02d.%d' % (month, year),
                     'periodYear': year, 'periodMonth': month}]
        return []

    def test_all_months_of_years_with_one_signature(self):
        self.calls = []
        wizard = self._wizard(year_from=2023, year=2024)
        with patch.object(type(self.config), '_api_get_document_list', autospec=True,
                          side_effect=lambda cfg, y, m, auth_signature: self._list(
                              y, m, auth_signature=auth_signature)):
            result = wizard.kep_submit_signed([], auth_signature='SIG')
            self.assertEqual(len(self.calls), 24)
            self.assertIn('Імпортовано документів: 4', result['receipt'])
            docs = self.env['l10n_ua.tax.document'].search([
                ('source', '=', 'cabinet'), ('external_id', 'in', ['202303', '202412'])])
            self.assertEqual(len(docs), 2)

            # Повторний прогін нічого не дублює.
            self.calls = []
            result = wizard.kep_submit_signed([], auth_signature='SIG')
            self.assertIn('Імпортовано документів: 0', result['receipt'])

    def test_future_months_are_skipped(self):
        self.calls = []
        today = date.today()
        wizard = self._wizard(year_from=today.year, year=today.year)
        with patch.object(type(self.config), '_api_get_document_list', autospec=True,
                          side_effect=lambda cfg, y, m, auth_signature: self._list(
                              y, m, auth_signature=auth_signature)):
            wizard.kep_submit_signed([], auth_signature='SIG')
        self.assertEqual(len(self.calls), today.month)

    def test_stops_on_time_budget_and_says_where_to_resume(self):
        self.calls = []
        wizard = self._wizard(year_from=2022, year=2024)
        ticks = iter(range(0, 10_000, 10))
        with patch.object(type(self.config), '_api_get_document_list', autospec=True,
                          side_effect=lambda cfg, y, m, auth_signature: self._list(
                              y, m, auth_signature=auth_signature)), \
                patch.object(sync_wizard, 'SYNC_TIME_BUDGET', 75), \
                patch.object(sync_wizard, '_clock', side_effect=lambda: next(ticks)):
            result = wizard.kep_submit_signed([], auth_signature='SIG')
        # Початок 0, дедлайн 75; перевірки на 10..70 проходять, на 80 — стоп.
        self.assertEqual(len(self.calls), 7)
        self.assertIn('08.2022', result['receipt'])
        self.assertIn('«З року» = 2022', result['receipt'])

    def test_signing_window_says_what_is_synced(self):
        prepared = self._wizard(year_from=2019, year=2026).kep_prepare_signing()
        self.assertEqual(prepared['auth_subject'], '1234567890')
        self.assertFalse(prepared['documents'])
        self.assertIn('2019–2026', prepared['description'])
        one = self._wizard(month='3', year=2025).kep_prepare_signing()
        self.assertIn('03.2025', one['description'])

    def test_first_period_error_is_raised(self):
        wizard = self._wizard(year_from=2024, year=2024)
        with patch.object(type(self.config), '_api_get_document_list', autospec=True,
                          side_effect=UserError('API error 401')):
            with self.assertRaises(UserError):
                wizard.kep_submit_signed([], auth_signature='SIG')

    def test_later_period_error_is_reported(self):
        def flaky(cfg, y, m, auth_signature):
            if m == 5:
                raise UserError('API error 500')
            return []
        wizard = self._wizard(year_from=2024, year=2024)
        with patch.object(type(self.config), '_api_get_document_list', autospec=True,
                          side_effect=flaky):
            result = wizard.kep_submit_signed([], auth_signature='SIG')
        self.assertIn('05.2024', result['receipt'])
