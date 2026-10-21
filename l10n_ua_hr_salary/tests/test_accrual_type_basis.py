"""Which shipped accrual types make the vacation average (#290).

Порядок № 100, п. 3 counts every accrued wage — bonuses and extra pay
included — and п. 4 names what stays out: one-off payments, social payments,
payments in kind. Vacation pay and sickness benefits are not in the flag:
the vacation average takes them by their category, the two-month average
does not take them at all.
"""
import importlib.util
import os

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAccrualTypeBasis(TransactionCase):

    def _flag(self, xmlid):
        return self.env.ref('l10n_ua_hr_salary.%s' % xmlid).is_basic_salary

    def test_wage_types_are_in_the_average(self):
        for xmlid in ('accrual_type_salary', 'accrual_type_allowance',
                      'accrual_type_bonus', 'accrual_type_overtime',
                      'accrual_type_night', 'accrual_type_holiday',
                      'accrual_type_indexation', 'accrual_type_seniority',
                      'accrual_type_piece', 'accrual_type_retro'):
            self.assertTrue(self._flag(xmlid), xmlid)

    def test_paragraph_4_payments_are_not(self):
        for xmlid in ('accrual_type_compensation', 'accrual_type_severance',
                      'accrual_type_material_aid', 'accrual_type_in_kind',
                      'accrual_type_maternity', 'accrual_type_vacation',
                      'accrual_type_sick_employer', 'accrual_type_sick_fss'):
            self.assertFalse(self._flag(xmlid), xmlid)

    def test_a_new_type_is_in_the_average(self):
        kind = self.env['hr.accrual.type'].create({
            'name': 'Доплата за суміщення', 'code': 'TEST290_COMBINE',
            'category': 'allowance',
        })
        self.assertTrue(kind.is_basic_salary)

    def test_severance_is_outside_the_contribution_base(self):
        # Перелік КМУ № 1170, розд. I, п. 1: no contribution on severance pay,
        # so it is not in the sick-leave average either (Порядок № 1266).
        self.assertFalse(self.env.ref(
            'l10n_ua_hr_salary.accrual_type_severance').is_esv_base)

    def test_migration_keeps_own_wage_types_in_the_average(self):
        Type = self.env['hr.accrual.type']
        own_wage = Type.create({'name': 'Власна доплата', 'code': 'TEST290_OWN',
                                'category': 'allowance', 'is_basic_salary': False})
        own_other = Type.create({'name': 'Власна виплата', 'code': 'TEST290_OTHER',
                                 'category': 'other', 'is_basic_salary': False})
        severance = self.env.ref('l10n_ua_hr_salary.accrual_type_severance')
        severance.is_esv_base = True
        self.env.flush_all()

        path = os.path.join(os.path.dirname(__file__), os.pardir, 'migrations',
                            '19.0.1.5.3', 'post-migration.py')
        spec = importlib.util.spec_from_file_location('mig_19_0_1_5_3', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.1.5.2')
        self.env.invalidate_all()

        self.assertTrue(own_wage.is_basic_salary)
        self.assertFalse(own_other.is_basic_salary)
        self.assertFalse(severance.is_esv_base)
