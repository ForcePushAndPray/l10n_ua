import logging

from odoo import models

_logger = logging.getLogger(__name__)

F0103309 = 'F0103309'


class L10nUaTaxDocument(models.Model):
    _inherit = 'l10n_ua.tax.document'

    def _l10n_ua_after_import(self):
        """Подана декларація ЄП із журналу → «Декларації ЄП»."""
        res = super()._l10n_ua_after_import()
        Declaration = self.env['l10n_ua.fop.declaration']
        for doc in self.filtered(lambda d: d.file_xml and d.document_type_id.code == F0103309):
            try:
                with self.env.cr.savepoint():
                    Declaration._import_from_tax_document(doc)
            except Exception:  # noqa: BLE001 — збій розбору не має зривати імпорт документа
                _logger.exception("F0103309: не вдалося імпортувати декларацію з %s",
                                  doc.display_name)
        return res
