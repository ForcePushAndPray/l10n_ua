"""Запит про стан розрахунків — нова форма J1300208 (наказ Мінфіну № 416, #419).

З 14.01.2026 запит подається за новою формою; J1300205 ДПС більше не приймає.
Ще не подані запити (чернетки й сформовані) переводяться на J1300208, а XML
сформованих стирається: його треба сформувати наново. Подані лишаються як є.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE l10n_ua_tax_request
           SET request_type = 'j1300208',
               state = 'draft',
               xml_filename = NULL
         WHERE request_type = 'j1300205'
           AND state IN ('draft', 'generated')
     RETURNING id
    """)
    ids = [row[0] for row in cr.fetchall()]
    if ids:
        cr.execute("""
            DELETE FROM ir_attachment
             WHERE res_model = 'l10n_ua.tax.request'
               AND res_field = 'xml_file'
               AND res_id IN %s
        """, (tuple(ids),))
    _logger.info('Tax requests moved to J1300208: %s', len(ids))
