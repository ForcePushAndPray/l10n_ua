"""Extension of tax document model with Tax Cabinet integration."""
import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nUaTaxDocumentCabinet(models.Model):
    """Extends tax document with Tax Cabinet (cabinet.tax.gov.ua) integration."""
    _inherit = 'l10n_ua.tax.document'

    # Source info
    source = fields.Selection(
        selection=[
            ('manual', 'Manual'),
            ('cabinet', 'Tax Cabinet'),
            ('medoc', 'M.E.Doc'),
            ('fredo', 'FREDO'),
        ],
        string='Source',
        default='manual',
    )
    external_id = fields.Char(
        string='Cabinet Document ID',
        help='Document ID in cabinet.tax.gov.ua',
        index=True,
    )
    sync_date = fields.Datetime(
        string='Sync Date',
        help='Date when document was synced from Tax Cabinet',
    )

    # Signed file for submission
    file_signed = fields.Binary(
        string='Signed File (P7S)',
        attachment=True,
        help='KEP-signed document ready for submission',
    )
    file_signed_name = fields.Char(
        string='Signed Filename',
    )

    # Override state to add 'signed' state
    state = fields.Selection(
        selection_add=[
            ('signed', 'Signed'),
        ],
        ondelete={'signed': 'set default'},
    )

    def action_sign_document(self):
        """Open password wizard to sign the XML document with KEP."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to sign"))

        config = self.env['l10n_ua.tax.cabinet.config'].search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not config:
            raise UserError(_(
                "No KEP configuration found for company %s. "
                "Please configure Tax Cabinet connection."
            ) % self.company_id.name)

        if not config.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enter KEP Password'),
            'res_model': 'l10n_ua.tax.cabinet.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': config.id,
                'default_action': 'sign',
                'default_document_id': self.id,
            },
        }

    def action_submit_to_cabinet(self):
        """Submit signed document to cabinet.tax.gov.ua."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to submit"))

        config = self.env['l10n_ua.tax.cabinet.config'].search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not config:
            raise UserError(_("No KEP configuration found for company %s.") % self.company_id.name)

        if not config.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enter KEP Password'),
            'res_model': 'l10n_ua.tax.cabinet.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': config.id,
                'default_action': 'submit',
                'default_document_id': self.id,
            },
        }

    def action_redownload_files(self):
        """Open password wizard to re-download PDF/XML from Tax Cabinet."""
        self.ensure_one()

        if self.source != 'cabinet' or not self.external_id:
            raise UserError(_("Can only re-download documents synced from Tax Cabinet."))

        config = self.env['l10n_ua.tax.cabinet.config'].search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not config:
            raise UserError(_("No Tax Cabinet configuration found for company %s.") % self.company_id.name)

        if not config.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enter KEP Password'),
            'res_model': 'l10n_ua.tax.cabinet.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': config.id,
                'default_action': 'redownload',
                'default_document_id': self.id,
            },
        }

    def action_download_signed(self):
        """Download signed document."""
        self.ensure_one()
        if not self.file_signed:
            raise UserError(_("No signed file. Please sign the document first."))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/file_signed/{self.file_signed_name}?download=true',
            'target': 'new',
        }

    def _do_sign_document(self, config, password):
        """Sign document with KEP. Called from password wizard."""
        self.ensure_one()

        if not self.file_xml:
            raise UserError(_("No XML file to sign"))

        xml_content = base64.b64decode(self.file_xml)
        signed_content = config._sign_with_kep(xml_content, password)

        if signed_content:
            filename = self.file_xml_name or 'document.xml'
            signed_filename = filename.replace('.xml', '.p7s')
            if not signed_filename.endswith('.p7s'):
                signed_filename += '.p7s'

            if isinstance(signed_content, str):
                signed_content = signed_content.encode('ascii')

            self.write({
                'file_signed': signed_content,
                'file_signed_name': signed_filename,
                'state': 'signed',
            })
            return True
        else:
            raise UserError(_("Signing failed - no signed content returned"))

    def _do_submit_to_cabinet(self, config, password):
        """Submit document to cabinet.tax.gov.ua. Called from password wizard."""
        self.ensure_one()

        if not self.file_xml:
            raise UserError(_("No XML file to submit"))

        xml_content = base64.b64decode(self.file_xml)
        signed_encrypted_b64 = config._sign_and_encrypt_for_dps(xml_content, password)
        filename = self._generate_filename()
        result = config._api_submit_document(signed_encrypted_b64, filename, password)

        return result

    def _do_redownload_files(self, config):
        """Re-download PDF and XML files from Tax Cabinet."""
        self.ensure_one()

        if not self.external_id:
            raise UserError(_("No external ID - cannot re-download."))

        doc_year = self.year or fields.Date.today().year
        external_id = self.external_id
        doc_type = 'reg_doc'

        downloaded = []

        try:
            xml_content = config._api_download_document_xml(doc_year, external_id, doc_type)
            if xml_content:
                self.write({
                    'file_xml': xml_content,
                    'file_xml_name': self.file_xml_name or f"{external_id}.xml",
                })
                downloaded.append('XML')
        except Exception as e:
            _logger.warning("Could not download XML for %s: %s", external_id, str(e))

        try:
            pdf_content = config._api_download_document_pdf(doc_year, external_id, doc_type)
            if pdf_content:
                self.write({
                    'file_pdf': pdf_content,
                    'file_pdf_name': self.file_pdf_name or f"{external_id}.pdf",
                })
                downloaded.append('PDF')
        except Exception as e:
            _logger.warning("Could not download PDF for %s: %s", external_id, str(e))

        return downloaded

    # ========== Sync methods ==========

    @api.model
    def _sync_reported_documents(self, config, year, month):
        """Sync reported documents from cabinet."""
        docs_data = config._api_get_document_list(year, month)
        return self._process_api_documents(config, docs_data, 'reg_doc', year)

    @api.model
    def _sync_incoming_documents(self, config):
        """Sync incoming correspondence from cabinet."""
        docs_data = config._api_get_incoming_documents()
        return self._process_api_documents(config, docs_data, 'incoming')

    @api.model
    def _sync_sent_documents(self, config):
        """Sync sent correspondence from cabinet."""
        docs_data = config._api_get_sent_documents()
        return self._process_api_documents(config, docs_data, 'sent')

    @api.model
    def _process_api_documents(self, config, docs_data, doc_type, year=None):
        """Process documents from API response."""
        if year is None:
            year = fields.Date.today().year

        created_count = 0

        if not docs_data:
            return created_count

        if isinstance(docs_data, dict):
            docs_data = docs_data.get('content', docs_data.get('items', docs_data.get('data', [])))

        for doc_item in docs_data:
            external_id = str(doc_item.get('codRegdoc') or doc_item.get('id', ''))
            if not external_id:
                continue

            existing = self.search([
                ('external_id', '=', external_id),
                ('source', '=', 'cabinet'),
            ], limit=1)

            if existing:
                _logger.debug("Document %s already synced", external_id)
                continue

            doc_vals = self._prepare_api_document_vals(config, doc_item, doc_type, year)
            doc = self.create(doc_vals)
            created_count += 1

            doc_year = doc_vals.get('year', year)

            if config.auto_download_xml and doc_type != 'sent':
                try:
                    xml_content = config._api_download_document_xml(doc_year, external_id, doc_type)
                    if xml_content:
                        doc.write({
                            'file_xml': xml_content,
                            'file_xml_name': f"{external_id}.xml",
                        })
                except Exception as e:
                    _logger.warning("Could not download XML for %s: %s", external_id, str(e))

            if config.auto_download_pdf:
                try:
                    pdf_content = config._api_download_document_pdf(doc_year, external_id, doc_type)
                    if pdf_content:
                        doc.write({
                            'file_pdf': pdf_content,
                            'file_pdf_name': f"{external_id}.pdf",
                        })
                except Exception as e:
                    _logger.warning("Could not download PDF for %s: %s", external_id, str(e))

            _logger.info("Synced tax document: %s", doc.name)

        return created_count

    @api.model
    def _prepare_api_document_vals(self, config, doc_item, doc_type, year):
        """Prepare document values from API response."""
        doc_code = doc_item.get('doc') or doc_item.get('cdoc') or 'OTHER'

        doc_type_record = self.env['l10n_ua.tax.document.type'].search([
            ('code', '=', doc_code)
        ], limit=1)

        if not doc_type_record:
            doc_type_record = self.env.ref(
                'l10n_ua_tax.tax_document_type_other',
                raise_if_not_found=False
            ) or self.env['l10n_ua.tax.document.type'].search([], limit=1)

        doc_date_str = doc_item.get('dget') or doc_item.get('dateIn') or doc_item.get('dateOut')
        doc_date = fields.Date.today()
        if doc_date_str:
            try:
                doc_date = fields.Date.from_string(doc_date_str[:10])
            except Exception:
                pass

        external_id = str(doc_item.get('codRegdoc') or doc_item.get('id', ''))
        doc_name = doc_item.get('docName') or doc_item.get('name') or f'Document {external_id}'
        reg_num = str(doc_item.get('nreg') or doc_item.get('text') or '')

        return {
            'name': doc_name,
            'document_type_id': doc_type_record.id if doc_type_record else False,
            'document_number': reg_num,
            'document_date': doc_date,
            'year': doc_item.get('periodYear', year),
            'period': str(doc_item.get('periodMonth', '')).zfill(2) if doc_item.get('periodMonth') else False,
            'company_id': config.company_id.id,
            'taxpayer_code': config.taxpayer_code,
            'source': 'cabinet',
            'external_id': external_id,
            'sync_date': fields.Datetime.now(),
            'state': 'accepted',
        }
