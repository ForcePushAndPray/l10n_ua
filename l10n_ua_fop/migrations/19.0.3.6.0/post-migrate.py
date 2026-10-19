"""Квитанції № 2, уже завантажені з вхідної кореспонденції, — до їхніх декларацій ЄП."""

from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_ua_fop.models.l10n_ua_fop_declaration import KVT2_RE


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Declaration = env['l10n_ua.fop.declaration']
    docs = env['l10n_ua.tax.document'].search([('file_xml', '!=', False)])
    for doc in docs.filtered(lambda d: KVT2_RE.search(d.name or '')):
        Declaration._link_kvt2_document(doc)
