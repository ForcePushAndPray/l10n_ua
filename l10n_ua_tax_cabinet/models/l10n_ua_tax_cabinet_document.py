import base64
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nUaTaxCabinetDocument(models.Model):
    _name = 'l10n_ua.tax.cabinet.document'
    _description = 'Tax Cabinet Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'document_date desc, id desc'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    document_type_id = fields.Many2one(
        'l10n_ua.tax.document.type',
        string='Document Type',
        required=True,
        tracking=True,
    )
    document_number = fields.Char(
        string='Document Number',
        tracking=True,
    )
    document_date = fields.Date(
        string='Document Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )

    # Period info
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.context_today(self).year,
    )
    period = fields.Selection(
        selection=[
            ('01', 'January'),
            ('02', 'February'),
            ('03', 'March'),
            ('04', 'April'),
            ('05', 'May'),
            ('06', 'June'),
            ('07', 'July'),
            ('08', 'August'),
            ('09', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'December'),
            ('q1', 'Q1'),
            ('q2', 'Q2'),
            ('q3', 'Q3'),
            ('q4', 'Q4'),
            ('h1', 'H1'),
            ('h2', 'H2'),
            ('year', 'Year'),
        ],
        string='Period',
    )

    # Company / FOP
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    taxpayer_code = fields.Char(
        string='Taxpayer Code',
        help='EDRPOU or RNOKPP',
    )

    # File attachments
    file_xml = fields.Binary(
        string='XML File',
        attachment=True,
    )
    file_xml_name = fields.Char(
        string='XML Filename',
    )
    file_pdf = fields.Binary(
        string='PDF File',
        attachment=True,
    )
    file_pdf_name = fields.Char(
        string='PDF Filename',
    )
    file_signed = fields.Binary(
        string='Signed File',
        attachment=True,
        help='KEP-signed document ready for submission',
    )
    file_signed_name = fields.Char(
        string='Signed Filename',
    )

    # Computed fields for viewing
    file_xml_content = fields.Text(
        string='XML Content',
        compute='_compute_file_xml_content',
        inverse='_inverse_file_xml_content',
    )

    @api.depends('file_xml')
    def _compute_file_xml_content(self):
        for record in self:
            if record.file_xml:
                try:
                    content = base64.b64decode(record.file_xml)
                    record.file_xml_content = content.decode('utf-8')
                except Exception:
                    record.file_xml_content = False
            else:
                record.file_xml_content = False

    def _inverse_file_xml_content(self):
        for record in self:
            if record.file_xml_content:
                record.file_xml = base64.b64encode(record.file_xml_content.encode('utf-8'))
            else:
                record.file_xml = False

    # Source info
    source = fields.Selection(
        selection=[
            ('manual', 'Manual Upload'),
            ('cabinet', 'Tax Cabinet API'),
            ('medoc', 'M.E.Doc'),
            ('fredo', 'FREDO'),
        ],
        string='Source',
        default='manual',
        required=True,
    )
    external_id = fields.Char(
        string='External ID',
        help='Document ID from external system',
    )
    sync_date = fields.Datetime(
        string='Sync Date',
        help='Date when document was synced from external system',
    )

    # Status
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    status_message = fields.Text(
        string='Status Message',
        help='Message from tax authority',
    )

    # Notes
    notes = fields.Text(
        string='Notes',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('taxpayer_code') and vals.get('company_id'):
                company = self.env['res.company'].browse(vals['company_id'])
                vals['taxpayer_code'] = company.vat or company.company_registry
        return super().create(vals_list)

    def write(self, vals):
        # Prevent modifications to accepted documents (except file re-downloads)
        allowed_fields = {'file_pdf', 'file_pdf_name', 'file_xml', 'file_xml_name', 'file_signed', 'file_signed_name'}
        is_file_only = set(vals.keys()).issubset(allowed_fields)

        for record in self:
            if record.state == 'accepted' and not is_file_only:
                raise UserError(_("Cannot modify accepted document '%s'. Accepted documents are read-only.") % record.name)
        return super().write(vals)

    def unlink(self):
        # Prevent deletion of accepted documents
        for record in self:
            if record.state == 'accepted':
                raise UserError(_("Cannot delete accepted document '%s'.") % record.name)
        return super().unlink()

    def action_mark_submitted(self):
        self.write({'state': 'submitted'})

    def action_mark_accepted(self):
        self.write({'state': 'accepted'})

    def action_mark_rejected(self):
        self.write({'state': 'rejected'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_fill_data(self):
        """Open wizard to fill document data based on document type."""
        self.ensure_one()
        if not self.document_type_id:
            raise UserError(_("Please select a document type first."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Fill Document Data'),
            'res_model': 'l10n_ua.tax.document.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
                'default_document_type_id': self.document_type_id.id,
                'default_company_id': self.company_id.id,
                'default_year': self.year,
                'default_period': self.period,
            },
        }

    def action_redownload_files(self):
        """Open password wizard to re-download PDF/XML from Tax Cabinet."""
        self.ensure_one()

        if self.source != 'cabinet' or not self.external_id:
            raise UserError(_("Can only re-download documents synced from Tax Cabinet."))

        # Get tax cabinet config for company
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

    def _do_redownload_files(self, config):
        """Re-download PDF and XML files from Tax Cabinet. Config should have password in context."""
        self.ensure_one()

        if not self.external_id:
            raise UserError(_("No external ID - cannot re-download."))

        doc_year = self.year or fields.Date.today().year
        external_id = self.external_id

        # Determine document type for API
        # Default to reg_doc, could be enhanced based on document metadata
        doc_type = 'reg_doc'

        downloaded = []

        # Download XML
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

        # Download PDF
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

    def action_sign_document(self):
        """Open password wizard to sign the XML document with KEP."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to sign"))

        # Get tax cabinet config for company
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

        # TODO: Implement signing via password wizard
        raise UserError(_("Document signing requires password wizard - not yet implemented."))

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

    def action_export_for_submission(self):
        """Export document for external submission (sign if needed and download)."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to export"))

        # Sign if not already signed
        if not self.file_signed:
            self.action_sign_document()

        # Download the signed file
        return self.action_download_signed()

    def action_submit_to_cabinet(self):
        """Submit signed document to cabinet.tax.gov.ua."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to submit"))

        # Get tax cabinet config for company
        config = self.env['l10n_ua.tax.cabinet.config'].search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not config:
            raise UserError(_("No KEP configuration found for company %s.") % self.company_id.name)

        if not config.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        # TODO: Implement submission via password wizard
        raise UserError(_("Document submission requires password wizard - not yet implemented."))

    # ========== Sync methods (called from password wizard) ==========

    @api.model
    def _sync_reported_documents(self, config, year, month):
        """Sync reported documents from cabinet. Config should have password in context."""
        docs_data = config._api_get_document_list(year, month)
        return self._process_api_documents(config, docs_data, 'reg_doc', year)

    @api.model
    def _sync_incoming_documents(self, config):
        """Sync incoming correspondence from cabinet. Config should have password in context."""
        docs_data = config._api_get_incoming_documents()
        return self._process_api_documents(config, docs_data, 'incoming')

    @api.model
    def _sync_sent_documents(self, config):
        """Sync sent correspondence from cabinet. Config should have password in context."""
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

        # Handle paginated response from cabinet.tax.gov.ua
        if isinstance(docs_data, dict):
            docs_data = docs_data.get('content', docs_data.get('items', docs_data.get('data', [])))

        for doc_item in docs_data:
            # reg_doc uses 'codRegdoc', correspondence uses 'id'
            external_id = str(doc_item.get('codRegdoc') or doc_item.get('id', ''))
            if not external_id:
                continue

            # Check if already synced
            existing = self.search([
                ('external_id', '=', external_id),
                ('source', '=', 'cabinet'),
            ], limit=1)

            if existing:
                _logger.debug("Document %s already synced", external_id)
                continue

            # Create document
            doc_vals = self._prepare_api_document_vals(config, doc_item, doc_type, year)
            doc = self.create(doc_vals)
            created_count += 1

            # Download files (config already has password in context)
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
        # Get document code
        doc_code = doc_item.get('doc') or doc_item.get('cdoc') or 'OTHER'

        # Try to find document type by code
        doc_type_record = self.env['l10n_ua.tax.document.type'].search([
            ('code', '=', doc_code)
        ], limit=1)

        if not doc_type_record:
            doc_type_record = self.env.ref(
                'l10n_ua_tax_cabinet.tax_document_type_other',
                raise_if_not_found=False
            ) or self.env['l10n_ua.tax.document.type'].search([], limit=1)

        # Parse date
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
