{
    'name': 'Ukraine - Agro Harvest',
    'version': '19.0.1.0.0',
    'category': 'Agriculture/Localization',
    'summary': 'Harvest receipts from fields: weighing, laboratory analysis, '
               'credit weight by basic conditions, batches, storage, yield',
    'description': """
Ukraine - Agro Harvest (збирання врожаю)
========================================

Part of the "Agro" industry solution (epic #477, issue #472).

* Basic conditions of each crop: moisture and impurity (Ukrainian
  standards: wheat 14 % / 1 %, sunflower 7 % / 1 %, ...).
* Harvest receipts (field weighing cards): planting, vehicle and driver,
  gross / tare / net weight, laboratory analysis (moisture, impurity,
  grain impurity, test weight, oil content, protein) and the credit weight
  by the Duval formula
  m = net x (100 - impurity) x (100 - moisture) /
  ((100 - base impurity) x (100 - base moisture)), without a bonus when
  the grain is better than the basic conditions.
* Validation receives the credit weight into the warehouse or the
  elevator (any location) into a batch (lot) of the field and season. The
  batch carries the weighted quality of all its receipts.
* Yield report: gross harvest and yield in centners per hectare by field,
  crop and season.

The accounting valuation of the harvest (Dt 27 / Ct 23, P(S)BO 30) is
done by ``l10n_ua_agro_account`` (#473).
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'l10n_ua_agro_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/agro_crop_basis_data.xml',
        'views/agro_crop_views.xml',
        'views/harvest_receipt_views.xml',
        'views/stock_lot_views.xml',
        'views/agro_planting_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
