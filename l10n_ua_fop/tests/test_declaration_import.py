"""Подані в Електронному кабінеті декларації ЄП (F0103309) → «Декларації ЄП».

XML — тієї ж структури, що й справжні прийняті ДПС декларації (I квартал і
півріччя 2026, 3 група), з вигаданими реквізитами.
"""

import base64
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def f0103309(period_type, marker, income, tax, military, tax_prev=0.0, military_prev=0.0,
             year=2026, kind='HZ', filled='16042026'):
    rows = [
        f'<R006G3>{income:.2f}</R006G3>', f'<R008G3>{income:.2f}</R008G3>',
        f'<R011G3>{tax:.2f}</R011G3>', f'<R012G3>{tax:.2f}</R012G3>',
    ]
    if tax_prev:
        rows.append(f'<R013G3>{tax_prev:.2f}</R013G3>')
    rows += [f'<R0141G3>{tax - tax_prev:.2f}</R0141G3>', f'<R014G3>{tax - tax_prev:.2f}</R014G3>',
             f'<R023G3>{military:.2f}</R023G3>']
    if military_prev:
        rows.append(f'<R024G3>{military_prev:.2f}</R024G3>')
    rows.append(f'<R025G3>{military - military_prev:.2f}</R025G3>')
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>\n'
        '        <DECLAR xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="F0103309.XSD">\n<DECLARHEAD>\n'
        '    <TIN>1234567890</TIN>\n    <C_DOC>F01</C_DOC>\n    <C_DOC_SUB>033</C_DOC_SUB>\n'
        '    <C_DOC_VER>9</C_DOC_VER>\n    <C_DOC_TYPE>0</C_DOC_TYPE>\n'
        f'    <PERIOD_MONTH>{ {"2": 3, "3": 6, "4": 9, "5": 12}[period_type] }</PERIOD_MONTH>\n'
        f'    <PERIOD_TYPE>{period_type}</PERIOD_TYPE>\n    <PERIOD_YEAR>{year}</PERIOD_YEAR>\n'
        f'<D_FILL>{filled}</D_FILL>\n</DECLARHEAD>\n        <DECLARBODY>\n'
        f'<{kind}>1</{kind}>\n<{marker}>1</{marker}>\n<HZY>{year}</HZY>\n'
        '<T1RXXXXG1S ROWNUM="1" >62.01</T1RXXXXG1S>\n'
        '<T1RXXXXG2S ROWNUM="1" >Комп\'ютерне програмування</T1RXXXXG2S>\n'
        + '\n'.join(rows) + f'\n<HFILL>{filled}</HFILL>\n</DECLARBODY>\n</DECLAR>'
    )
    return xml.encode('windows-1251')


Q1 = dict(period_type='2', marker='H1KV', income=700000.0, tax=35000.0, military=7000.0)
H1 = dict(period_type='3', marker='HHY', income=1400000.0, tax=70000.0, military=14000.0,
          tax_prev=35000.0, military_prev=7000.0, filled='15072026')


class DeclarationImportCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Declaration = cls.env['l10n_ua.fop.declaration']
        cls.f0103309 = cls.env['l10n_ua.tax.document.type'].search([('code', '=', 'F0103309')])
        Group = cls.env['l10n_ua.fop.group']
        cls.group_3 = Group.search([('code', '=', '3')]) or Group.create(
            {'code': '3', 'name': '3 група', 'tax_rate': 5.0, 'limit_min_wages': 1167})
        cls.group_3_vat = Group.search([('code', '=', '3_vat')]) or Group.create(
            {'code': '3_vat', 'name': '3 група (ПДВ)', 'tax_rate': 3.0, 'limit_min_wages': 1167})

    def _doc(self, xml, number='9101395121'):
        return self.env['l10n_ua.tax.document'].create({
            'name': 'Податкова декларація платника єдиного податку',
            'document_type_id': self.f0103309.id,
            'document_number': number,
            'company_id': self.company.id,
            'source': 'cabinet',
            'file_xml': base64.b64encode(xml),
            'file_xml_name': f'{number}.xml',
        })

    def _declarations(self):
        return self.Declaration.search([('company_id', '=', self.company.id), ('year', '=', 2026)])


@tagged('post_install', '-at_install')
class TestDeclarationImport(DeclarationImportCase):

    def test_filed_declarations_become_accepted_records(self):
        q1_doc = self._doc(f0103309(**Q1))
        h1_doc = self._doc(f0103309(**H1), number='9213825182')
        (q1_doc | h1_doc)._l10n_ua_after_import()

        q1 = self._declarations().filtered(lambda d: d.period == 'q1')
        h1 = self._declarations().filtered(lambda d: d.period == 'h1')
        self.assertEqual(q1.state, 'accepted')
        self.assertEqual(q1.fop_group_id, self.group_3)
        self.assertEqual(q1.total_income, 700000.0)
        self.assertEqual(q1.single_tax, 35000.0)
        self.assertEqual(q1.military_levy, 7000.0)
        self.assertEqual(q1.submission_date, date(2026, 4, 16))
        self.assertEqual(q1.tax_document_id, q1_doc)
        self.assertTrue(q1.xml_file)
        self.assertEqual(h1.total_income, 1400000.0)
        self.assertEqual(h1.submission_date, date(2026, 7, 15))

        # Повторний імпорт нічого не дублює.
        (q1_doc | h1_doc)._l10n_ua_after_import()
        self.assertEqual(len(self._declarations()), 2)

    def test_existing_draft_takes_filed_figures(self):
        draft = self.Declaration.create({
            'year': 2026, 'period': 'q1', 'fop_group_id': self.group_3.id,
            'company_id': self.company.id, 'total_income': 1.0})
        doc = self._doc(f0103309(**Q1))
        doc._l10n_ua_after_import()
        self.assertEqual(len(self._declarations()), 1)
        self.assertEqual(draft.state, 'accepted')
        self.assertEqual(draft.total_income, 700000.0)
        self.assertEqual(draft.tax_document_id, doc)

    def test_vat_payer_rate_picks_group_3_vat(self):
        self._doc(f0103309(period_type='2', marker='H1KV', income=100000.0, tax=3000.0,
                           military=1000.0))._l10n_ua_after_import()
        self.assertEqual(self._declarations().fop_group_id, self.group_3_vat)

    def test_correction_is_not_imported_as_declaration(self):
        self._doc(f0103309(kind='HZU', **Q1))._l10n_ua_after_import()
        self.assertFalse(self._declarations())

    def test_cabinet_sync_fills_declarations(self):
        config = self.env['l10n_ua.tax.cabinet.config'].with_context(active_test=False).search(
            [('company_id', '=', self.company.id)], limit=1) or self.env[
            'l10n_ua.tax.cabinet.config'].create({'name': 'Кабінет', 'company_id': self.company.id,
                                                   'taxpayer_code': '1234567890'})
        config.write({'taxpayer_code': '1234567890', 'auto_download_xml': True,
                      'auto_download_pdf': False, 'active': True})
        item = {'codRegdoc': '171624590296915', 'doc': 'F0103309', 'nreg': '9101395121',
                'docName': 'Податкова декларація платника єдиного податку',
                'periodYear': 2026, 'periodMonth': 3}
        with patch.object(type(config), '_api_download_document_xml', autospec=True,
                          return_value=base64.b64encode(f0103309(**Q1))):
            self.env['l10n_ua.tax.document']._process_api_documents(
                config, [item], 'reg_doc', 2026, auth_signature='SIG')
        q1 = self._declarations()
        self.assertEqual(q1.period, 'q1')
        self.assertEqual(q1.tax_document_id.external_id, '171624590296915')

    def test_next_declaration_deducts_previous_period(self):
        """Півріччя після поданого I кварталу: R013/R024 — нараховане за квартал."""
        self._doc(f0103309(**Q1))._l10n_ua_after_import()
        h1 = self.Declaration.create({
            'year': 2026, 'period': 'h1', 'fop_group_id': self.group_3.id,
            'company_id': self.company.id, 'total_income': 1400000.0, 'state': 'calculated'})
        h1.action_generate_xml()
        xml = base64.b64decode(h1.xml_file).decode('windows-1251')
        self.assertIn('<R011G3>70000.00</R011G3>', xml)
        self.assertIn('<R013G3>35000.00</R013G3>', xml)
        self.assertIn('<R0141G3>35000.00</R0141G3>', xml)
        self.assertIn('<R024G3>7000.00</R024G3>', xml)
        self.assertIn('<R025G3>7000.00</R025G3>', xml)


NINE_MONTHS = dict(period_type='4', marker='H3KV', income=2100000.0, tax=105000.0,
                   military=21000.0, tax_prev=70000.0, military_prev=14000.0, filled='19102026')


@tagged('post_install', '-at_install')
class TestCheckDps(DeclarationImportCase):
    """Кнопка «Перевірити в ДПС» на поданій декларації."""

    def setUp(self):
        super().setUp()
        Config = self.env['l10n_ua.tax.cabinet.config']
        self.config = Config.with_context(active_test=False).search(
            [('company_id', '=', self.company.id)], limit=1) or Config.create(
            {'name': 'Кабінет', 'company_id': self.company.id, 'taxpayer_code': '1234567890'})
        self.config.write({'taxpayer_code': '1234567890', 'auto_download_xml': True,
                           'auto_download_pdf': False, 'active': True})
        self.decl = self.Declaration.create({
            'year': 2026, 'period': '9m', 'fop_group_id': self.group_3.id,
            'company_id': self.company.id, 'total_income': 2100000.0})
        self.decl.with_context(l10n_ua_fop_declaration_unlock=True).write({'state': 'submitted'})

    def _check(self, listed):
        Config = type(self.config)
        with patch.object(Config, '_api_get_document_list', autospec=True,
                          return_value=listed) as get_list, \
                patch.object(Config, '_api_download_document_xml', autospec=True,
                             return_value=base64.b64encode(f0103309(**NINE_MONTHS))):
            result = self.decl.with_context(kep_mode='check').kep_submit_signed({}, 'SIG')
        return result['receipt'], get_list

    def test_check_mode_signs_only_authorisation(self):
        spec = self.decl.with_context(kep_mode='check').kep_prepare_signing()
        self.assertEqual(spec['documents'], [])
        self.assertEqual(spec['auth_subject'], '1234567890')
        self.assertEqual(self.decl.action_check_dps()['params']['mode'], 'check')

    def test_registered_declaration_becomes_accepted(self):
        item = {'codRegdoc': '171671355306358', 'doc': 'F0103309', 'nreg': '9437123456',
                'docName': 'Податкова декларація платника єдиного податку',
                'periodYear': 2026, 'periodMonth': 9}
        receipt, get_list = self._check([item])
        # Звітний період 9 міс. — у кабінеті це місяць 09.
        self.assertEqual(get_list.call_args.args[1:], (2026, 9))
        self.assertEqual(self.decl.state, 'accepted')
        self.assertEqual(self.decl.tax_document_id.external_id, '171671355306358')
        self.assertIn('9437123456', receipt)
        self.assertEqual(len(self._declarations().filtered(lambda d: d.period == '9m')), 1)

    def test_not_registered_yet_stays_submitted(self):
        receipt, _get_list = self._check([])
        self.assertEqual(self.decl.state, 'submitted')
        self.assertFalse(self.decl.tax_document_id)
        self.assertIn('ще немає', receipt)

    def test_document_synced_earlier_is_linked(self):
        doc = self._doc(f0103309(**NINE_MONTHS), number='9437123456')
        receipt, _get_list = self._check([])
        self.assertEqual(self.decl.state, 'accepted')
        self.assertEqual(self.decl.tax_document_id, doc)
        self.assertIn('9437123456', receipt)

    def test_only_submitted_can_be_checked(self):
        self.decl.with_context(l10n_ua_fop_declaration_unlock=True).write({'state': 'calculated'})
        with self.assertRaises(UserError):
            self.decl.action_check_dps()
