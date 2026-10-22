import logging

from odoo import models

from .l10n_ua_fop_declaration import DECLARATION_CODES, KVT2_RE

_logger = logging.getLogger(__name__)


class L10nUaTaxDocument(models.Model):
    _inherit = 'l10n_ua.tax.document'

    def _l10n_ua_after_import(self):
        """Подана декларація ЄП або квитанція № 2 на неї із журналу → «Декларації ЄП»."""
        res = super()._l10n_ua_after_import()
        Declaration = self.env['l10n_ua.fop.declaration']
        kvt2 = self.filtered(lambda d: d.file_xml and KVT2_RE.search(d.name or ''))
        for doc in (self - kvt2).filtered(
                lambda d: d.file_xml and d.document_type_id.code in DECLARATION_CODES):
            try:
                with self.env.cr.savepoint():
                    Declaration._import_from_tax_document(doc)
            except Exception:  # noqa: BLE001 — збій розбору не має зривати імпорт документа
                _logger.exception("ЄП: не вдалося імпортувати декларацію з %s",
                                  doc.display_name)
        for doc in kvt2:
            try:
                with self.env.cr.savepoint():
                    Declaration._link_kvt2_document(doc)
            except Exception:  # noqa: BLE001 — збій розбору не має зривати імпорт документа
                _logger.exception("J1499202: не вдалося прив'язати квитанцію %s",
                                  doc.display_name)
        return res
