"""Спільне налаштування тестів польових робіт (#471)."""

from datetime import date

from odoo.tests import TransactionCase


class AgroOperationsTestCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.fiscalyear_lock_date = False
        cls.acc_231 = cls._account('231', 'Основне виробництво', 'asset_current')
        cls.acc_201 = cls._account('201', 'Сировина й матеріали', 'asset_current')
        cls.acc_203 = cls._account('203', 'Паливо', 'asset_current')
        cls.journal = cls.env['account.journal'].create({
            'name': 'Польові роботи (тест)', 'code': 'AGRT', 'type': 'general',
            'company_id': cls.company.id})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.company.write({
            'l10n_ua_agro_operations_journal_id': cls.journal.id,
            'l10n_ua_agro_production_account_id': cls.acc_231.id,
            'l10n_ua_agro_warehouse_id': cls.warehouse.id,
        })
        categ = cls.env['product.category'].create({'name': 'Агро матеріали (тест)'})
        categ.property_stock_valuation_account_id = cls.acc_201
        cls.env.ref('l10n_ua_agro_operations.product_category_fuel').property_stock_valuation_account_id = cls.acc_203
        kg = cls.env.ref('uom.product_uom_kgm')
        cls.seed = cls.env['product.product'].create({
            'name': 'Насіння пшениці (тест)', 'is_storable': True, 'uom_id': kg.id,
            'standard_price': 20.0, 'categ_id': categ.id})
        cls.fertilizer = cls.env['product.product'].create({
            'name': 'Аміачна селітра (тест)', 'is_storable': True, 'uom_id': kg.id,
            'standard_price': 25.0, 'categ_id': categ.id})
        cls.diesel = cls.env.ref('l10n_ua_agro_operations.product_diesel')
        cls.diesel.standard_price = 55.0
        stock = cls.warehouse.lot_stock_id
        for product, qty in ((cls.seed, 20000), (cls.fertilizer, 20000), (cls.diesel, 10000)):
            cls.env['stock.quant']._update_available_quantity(product, stock, qty)

        cls.season = cls.env['l10n_ua.agro.season'].create({
            'year': 2097, 'date_start': date(2096, 8, 1), 'date_end': date(2097, 12, 31)})
        cls.field = cls.env['l10n_ua.agro.field'].create({'name': 'За фермою', 'code': 'T-01', 'area': 100.0})
        cls.wheat = cls.env.ref('l10n_ua_agro_base.crop_wheat_winter')
        cls.planting = cls.env['l10n_ua.agro.planting'].create({
            'field_id': cls.field.id, 'season_id': cls.season.id, 'crop_id': cls.wheat.id, 'area': 100.0})
        cls.op_sow = cls.env.ref('l10n_ua_agro_operations.operation_sow')        # 90 грн/га, 6 л/га
        cls.op_fert = cls.env.ref('l10n_ua_agro_operations.operation_fert')      # 45 грн/га, 3 л/га
        cls.card = cls.env['l10n_ua.agro.tech.card'].create({
            'name': 'Пшениця озима 2097', 'crop_id': cls.wheat.id, 'season_id': cls.season.id,
            'operation_ids': [(0, 0, {'operation_type_id': cls.op_sow.id}),
                              (0, 0, {'operation_type_id': cls.op_fert.id})],
            'material_ids': [
                (0, 0, {'operation_type_id': cls.op_sow.id, 'product_id': cls.seed.id, 'rate_ha': 220.0}),
                (0, 0, {'operation_type_id': cls.op_fert.id, 'product_id': cls.fertilizer.id, 'rate_ha': 150.0}),
            ]})
        cls.card.action_approve()
        cls.tractor = cls.env['l10n_ua.agro.machine'].create({
            'name': 'John Deere 8R', 'code': '01', 'fuel_product_id': cls.diesel.id, 'fuel_factor': 1.1})
        cls.operator = cls.env['hr.employee'].create({'name': 'Мельник Іван Степанович'})

    @classmethod
    def _account(cls, code, name, account_type):
        Account = cls.env['account.account']
        return Account.search([('code', '=', code), ('company_ids', 'in', cls.company.id)], limit=1) \
            or Account.create({'code': code, 'name': name, 'account_type': account_type,
                               'company_ids': [(6, 0, cls.company.ids)]})

    def _order(self, operation, area=60.0, **vals):
        return self.env['l10n_ua.agro.work.order'].create(dict({
            'date': date(2096, 9, 25),
            'planting_id': self.planting.id,
            'operation_type_id': operation.id,
            'area_done': area,
            'worker_ids': [(0, 0, {'employee_id': self.operator.id, 'machine_id': self.tractor.id,
                                   'volume': area, 'hours': 8})],
        }, **vals))
