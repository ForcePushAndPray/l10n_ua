{
    'name': 'Ukraine - Agro Field Operations',
    'version': '19.0.1.2.0',
    'category': 'Agriculture/Localization',
    'summary': 'Technological cards, field work orders, write-off of seeds, '
               'fertilizers, plant protection products and fuel to fields',
    'description': """
Ukraine - Agro Field Operations (польові роботи)
================================================

Part of the "Agro" industry solution (epic #477, issue #471).

* Machinery (tractors, combines, sprayers, trucks) with their fuel.
* Field operations: unit of work (ha, t, hour, km), piece rate of the
  machine operator and fuel consumption norm.
* Technological cards per crop and season: planned operations and
  application rates per hectare (seeds, fertilizers, plant protection
  products), planned cost per hectare and for the sown area.
* Field work orders: planting (field x season x crop), operation, area
  done, operators with machines and output, materials and fuel. Materials
  can be loaded from the technological card (rate x area) and fuel from
  the norm. Validation writes the materials off the warehouse and posts
  Dt 23 / Ct 20 with the field and crop analytics.
* Plan / actual cost report per field and crop.
* Printed forms from the selected work orders: act on fertilizers and plant
  protection products (VZSG-3) and on seeds (VZSG-4) - recommended forms of
  the Ministry of Agrarian Policy order No. 929 of 21.12.2007 - and the
  tractor operator record sheet (form No. 67-B) per operator; signatories
  (agronomist / foreman, storekeeper) on the work order.

The piece-rate pay of the operators goes to payroll through
``l10n_ua_agro_operations_salary``.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'analytic',
        'hr',
        'stock_account',
        'l10n_ua_agro_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/analytic_plan_data.xml',
        'data/stock_location_data.xml',
        'data/ir_sequence_data.xml',
        'data/agro_operation_type_data.xml',
        'views/agro_machine_views.xml',
        'views/agro_operation_type_views.xml',
        'views/agro_tech_card_views.xml',
        'views/agro_work_order_views.xml',
        'views/agro_planting_views.xml',
        'views/res_config_settings_views.xml',
        'report/agro_cost_report_views.xml',
        'report/agro_print_forms.xml',
        'views/product_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
