"""Додаток 1 (ЄСВ) — тепер окрема галочка; ЄСВ рахується лише з нею.

Декларації з кабінету — за ознакою HD1 / пов'язаним документом поданого XML;
решта — без додатка (раніше ЄСВ додавався до кожної декларації, а XML його не
містив). Збережені суми ЄСВ і «Всього до сплати» перераховуються.
"""
import base64

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Declaration = env['l10n_ua.fop.declaration'].with_context(l10n_ua_fop_declaration_unlock=True)
    declarations = Declaration.search([])
    for decl in declarations.filtered(lambda d: d.tax_document_id.file_xml):
        data = Declaration._parse_f0103309(base64.b64decode(decl.tax_document_id.file_xml))
        if data and data['esv_annex']:
            decl.esv_annex = True
    for fname in ('esv_base', 'esv_amount', 'total_payable'):
        env.add_to_compute(Declaration._fields[fname], declarations)
    declarations.flush_recordset()
