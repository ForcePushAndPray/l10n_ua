{
    'name': 'Ukraine - Agro Base',
    'version': '19.0.1.0.0',
    'category': 'Agriculture/Localization',
    'summary': 'Agriculture for Ukrainian crop farms: fields, crops, seasons, '
               'crop rotation and sown area structure',
    'description': """
Ukraine - Agro Base (рослинництво)
==================================

Base of the "Agro" industry solution (epic #477), shared by all
``l10n_ua_agro_*`` modules:

* Fields: area in hectares, land type (arable land, hayfields, pastures,
  perennial plantings, fallow), optional contour (GeoJSON).
* Crops: group (cereals, oilseeds, legumes, ...), winter / spring /
  perennial, main and by-product.
* Seasons (harvest years) with their stage: planning, sowing, harvest,
  closed.
* Plantings: field x season x crop with sown area, variety / hybrid and
  sowing date; the predecessor crop of the field is shown for crop
  rotation. The sown area of a field in a season cannot exceed its area.
* Sown area structure report (pivot / graph) and the "Agro" application
  menu with its own access groups.
    """,
    'author': 'Svyatoslav Nadozirny',
    'website': 'https://1c-to-odoo.many2one.online',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'l10n_ua_account_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/agro_crop_data.xml',
        'views/agro_crop_views.xml',
        'views/agro_season_views.xml',
        'views/agro_field_views.xml',
        'views/agro_planting_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': 0,
    'currency': 'EUR',
}
