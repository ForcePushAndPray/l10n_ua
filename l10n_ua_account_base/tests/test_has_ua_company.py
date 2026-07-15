"""Tests for auto-managed group_has_ua_company + UA-company flag — issue #178."""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHasUaCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref('l10n_ua_account_base.group_has_ua_company')
        cls.ua = cls.env.ref('base.ua')
        cls.us = cls.env.ref('base.us')
        Company = cls.env['res.company']
        cls.ua_co = Company.create({'name': 'ТОВ Тест-UA', 'country_id': cls.ua.id})
        cls.non_ua_co = Company.create({'name': 'Foreign LLC', 'country_id': cls.us.id})

    def _user(self, company):
        return self.env['res.users'].create({
            'name': 'U ' + company.name,
            'login': 'u_%d' % company.id,
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
        })

    def test_company_flag(self):
        self.assertTrue(self.ua_co.l10n_ua_is_ua_company)
        self.assertFalse(self.non_ua_co.l10n_ua_is_ua_company)
        self.assertTrue(self.ua_co._l10n_ua_is_ukrainian())
        self.assertFalse(self.non_ua_co._l10n_ua_is_ukrainian())

    def test_flag_recomputes_on_country_change(self):
        self.non_ua_co.country_id = self.ua
        self.assertTrue(self.non_ua_co.l10n_ua_is_ua_company)

    def test_user_without_ua_company_not_in_group(self):
        u = self._user(self.non_ua_co)
        self.assertNotIn(self.group, u.group_ids)

    def test_user_with_ua_company_in_group(self):
        u = self._user(self.ua_co)
        self.assertIn(self.group, u.group_ids)

    def test_group_follows_company_country_change(self):
        u = self._user(self.non_ua_co)
        self.assertNotIn(self.group, u.group_ids)
        # foreign company becomes Ukrainian -> user gains the group
        self.non_ua_co.country_id = self.ua
        self.assertIn(self.group, u.group_ids)

    def test_move_gate_flag_follows_company(self):
        """account.move.l10n_ua_is_ua_company mirrors its company (drives UI gate)."""
        Journal = self.env['account.journal']
        j_ua = Journal.create({'name': 'M UA', 'code': 'MUA',
                               'type': 'general', 'company_id': self.ua_co.id})
        j_fo = Journal.create({'name': 'M FO', 'code': 'MFO',
                               'type': 'general', 'company_id': self.non_ua_co.id})
        Move = self.env['account.move']
        m_ua = Move.create({'move_type': 'entry', 'journal_id': j_ua.id,
                            'company_id': self.ua_co.id})
        m_fo = Move.create({'move_type': 'entry', 'journal_id': j_fo.id,
                            'company_id': self.non_ua_co.id})
        self.assertTrue(m_ua.l10n_ua_is_ua_company)
        self.assertFalse(m_fo.l10n_ua_is_ua_company)

    def test_group_follows_company_ids_change(self):
        u = self._user(self.non_ua_co)
        self.assertNotIn(self.group, u.group_ids)
        # grant access to a UA company -> gains the group
        u.write({'company_ids': [(4, self.ua_co.id)]})
        self.assertIn(self.group, u.group_ids)
        # revoke it -> loses the group
        u.write({'company_ids': [(3, self.ua_co.id)]})
        self.assertNotIn(self.group, u.group_ids)
