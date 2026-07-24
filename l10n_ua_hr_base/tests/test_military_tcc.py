"""Тести експорту військового обліку до ТЦК (#156)."""

import base64
from datetime import date

from odoo.tests import tagged

from .common import TestHrUaBase


@tagged('post_install', '-at_install')
class TestMilitaryTcc(TestHrUaBase):

    def _military_employee(self):
        return self._create_employee(
            name='Військовий Іван',
            rnokpp=self.get_unique_rnokpp(),
            birthday=date(1990, 5, 20),
            military_register_category='liable',
            military_specialty='100',
            military_document_number='АА123456')

    def test_export_military_csv(self):
        emp = self._military_employee()
        report = self.env['hr.employee.military.report'].create({
            'company_id': self.company.id, 'date': date(2026, 1, 31)})
        report.write({'employee_ids': [(6, 0, emp.ids)], 'state': 'generated'})
        report.action_export_csv()
        self.assertTrue(report.export_data)
        self.assertTrue(report.export_filename.endswith('.csv'))
        text = base64.b64decode(report.export_data).decode('cp1251')
        self.assertIn('РНОКПП', text)
        self.assertIn(emp.rnokpp, text)
        self.assertIn('Військовий Іван', text)

    def test_notification_submit(self):
        emp = self._military_employee()
        notif = self.env['hr.military.notification'].create({
            'notification_type': 'hire',
            'employee_id': emp.id,
            'event_date': date(2026, 1, 15),
        })
        self.assertTrue(notif.name.startswith('ТЦК/'))
        self.assertEqual(notif.state, 'draft')
        notif.action_submit()
        self.assertEqual(notif.state, 'submitted')
        self.assertEqual(notif.snapshot_rnokpp, emp.rnokpp)
        self.assertTrue(notif.submitted_date)
        # Файл повідомлення сформовано і містить реквізити.
        text = base64.b64decode(notif.export_data).decode('cp1251')
        self.assertIn('Прийняття на роботу', text)
        self.assertIn(emp.rnokpp, text)

    def test_notification_type_dismissal(self):
        emp = self._military_employee()
        notif = self.env['hr.military.notification'].create({
            'notification_type': 'dismissal', 'employee_id': emp.id})
        notif.action_submit()
        text = base64.b64decode(notif.export_data).decode('cp1251')
        self.assertIn('Звільнення', text)
