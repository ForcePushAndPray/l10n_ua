import base64
import logging
import xml.etree.ElementTree as ET
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class L10nUaTaxCabinetSyncWizard(models.TransientModel):
    _name = 'l10n_ua.tax.cabinet.sync.wizard'
    _description = 'Tax Cabinet Sync Wizard'

    mode = fields.Selection(
        selection=[
            ('upload', 'Upload Documents'),
            ('sync', 'Sync from Cabinet'),
        ],
        string='Mode',
        default='upload',
        required=True,
    )

    # Upload mode fields
    file_ids = fields.One2many(
        'l10n_ua.tax.cabinet.sync.wizard.file',
        'wizard_id',
        string='Files',
    )

    # Sync mode fields
    config_id = fields.Many2one(
        'l10n_ua.tax.cabinet.config',
        string='Configuration',
    )
    sync_type = fields.Selection(
        selection=[
            ('reported', 'Reported Documents'),
            ('incoming', 'Incoming Correspondence'),
            ('sent', 'Sent Correspondence'),
        ],
        string='Document Type',
        default='reported',
    )
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.today().year,
    )
    month = fields.Selection(
        selection=[
            ('1', 'January'),
            ('2', 'February'),
            ('3', 'March'),
            ('4', 'April'),
            ('5', 'May'),
            ('6', 'June'),
            ('7', 'July'),
            ('8', 'August'),
            ('9', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'December'),
        ],
        string='Month',
        default=lambda self: str(fields.Date.today().month),
    )

    # Common
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            config = self.env['l10n_ua.tax.cabinet.config'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if config:
                self.config_id = config

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'sync' and not self.config_id:
            config = self.env['l10n_ua.tax.cabinet.config'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if config:
                self.config_id = config

    def action_process(self):
        """Process based on selected mode."""
        self.ensure_one()
        if self.mode == 'upload':
            return self._process_upload()
        elif self.mode == 'sync':
            return self._process_sync()

    def _process_upload(self):
        """Process uploaded files and create documents."""
        self.ensure_one()
        if not self.file_ids:
            raise UserError(_("Please add files to upload"))

        created_docs = self.env['l10n_ua.tax.cabinet.document']

        for file_line in self.file_ids:
            doc_vals = self._prepare_document_vals(file_line)
            doc = self.env['l10n_ua.tax.cabinet.document'].create(doc_vals)
            created_docs |= doc
            _logger.info("Created tax document: %s", doc.name)

        # Show created documents
        if len(created_docs) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tax Document'),
                'res_model': 'l10n_ua.tax.cabinet.document',
                'view_mode': 'form',
                'res_id': created_docs.id,
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tax Documents'),
                'res_model': 'l10n_ua.tax.cabinet.document',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_docs.ids)],
            }

    def _prepare_document_vals(self, file_line):
        """Prepare values for document creation from uploaded file."""
        vals = {
            'name': file_line.name or file_line.filename,
            'document_type_id': file_line.document_type_id.id,
            'document_date': file_line.document_date or fields.Date.today(),
            'year': file_line.year,
            'period': file_line.period,
            'company_id': self.company_id.id,
            'source': 'manual',
        }

        # Determine file type and attach
        filename = file_line.filename.lower() if file_line.filename else ''
        if filename.endswith('.xml'):
            vals['file_xml'] = file_line.file
            vals['file_xml_name'] = file_line.filename
            # Try to parse XML for additional info
            self._parse_xml_document(file_line.file, vals)
        elif filename.endswith('.pdf'):
            vals['file_pdf'] = file_line.file
            vals['file_pdf_name'] = file_line.filename
        else:
            # Treat as XML by default
            vals['file_xml'] = file_line.file
            vals['file_xml_name'] = file_line.filename

        return vals

    def _parse_xml_document(self, file_content, vals):
        """Try to parse XML and extract document info."""
        try:
            xml_data = base64.b64decode(file_content)
            root = ET.fromstring(xml_data)

            # Try to find common Ukrainian tax XML elements
            # HTIN - taxpayer code
            htin = root.find('.//HTIN') or root.find('.//TIN')
            if htin is not None and htin.text:
                vals['taxpayer_code'] = htin.text

            # HNAME - document name
            hname = root.find('.//HNAME')
            if hname is not None and hname.text:
                vals['name'] = hname.text

            # HNUM - document number
            hnum = root.find('.//HNUM')
            if hnum is not None and hnum.text:
                vals['document_number'] = hnum.text

            # Period info
            hper = root.find('.//HPER')
            if hper is not None and hper.text:
                period_map = {
                    '1': '01', '2': '02', '3': '03', '4': '04',
                    '5': '05', '6': '06', '7': '07', '8': '08',
                    '9': '09', '10': '10', '11': '11', '12': '12',
                }
                vals['period'] = period_map.get(hper.text, hper.text)

            hperu = root.find('.//HPERU')  # Period type
            if hperu is not None and hperu.text:
                period_type_map = {
                    '1': None,  # month - use HPER
                    '2': 'q1',  # quarter
                    '3': 'h1',  # half-year
                    '4': 'year',  # year
                }
                if hperu.text in period_type_map and period_type_map[hperu.text]:
                    vals['period'] = period_type_map[hperu.text]

            hreg = root.find('.//HREG')  # Year
            if hreg is not None and hreg.text:
                try:
                    vals['year'] = int(hreg.text)
                except ValueError:
                    pass

        except Exception as e:
            _logger.warning("Could not parse XML document: %s", str(e))

    def _process_sync(self):
        """Sync documents from cabinet.tax.gov.ua API."""
        self.ensure_one()

        if not self.config_id:
            raise UserError(_("Please select or create a Tax Cabinet configuration first."))

        # Validate authentication is configured
        if self.config_id.auth_method == 'kep':
            if not self.config_id.kep_key_file or not self.config_id.kep_password:
                raise UserError(_(
                    "KEP authentication not configured.\n\n"
                    "Please configure in the Tax Cabinet connection:\n"
                    "1. KEP Key File path (.dat, .jks, .pfx)\n"
                    "2. KEP Password\n"
                    "3. IIT Library and Certificates paths"
                ))
        elif self.config_id.auth_method == 'token':
            if not self.config_id.auth_token:
                raise UserError(_(
                    "No authorization token.\n\n"
                    "Please paste the signed authorization token from browser Developer Tools."
                ))

        created_docs = self.env['l10n_ua.tax.cabinet.document']

        try:
            if self.sync_type == 'reported':
                docs = self._sync_reported_documents()
            elif self.sync_type == 'incoming':
                docs = self._sync_incoming_documents()
            elif self.sync_type == 'sent':
                docs = self._sync_sent_documents()
            else:
                docs = self.env['l10n_ua.tax.cabinet.document']

            created_docs |= docs

            # Update last sync date
            self.config_id.last_sync_date = fields.Datetime.now()

        except Exception as e:
            _logger.error("Sync error: %s", str(e))
            raise UserError(_("Sync failed: %s") % str(e))

        # Show result
        if not created_docs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('No new documents found.'),
                    'type': 'info',
                }
            }
        elif len(created_docs) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tax Document'),
                'res_model': 'l10n_ua.tax.cabinet.document',
                'view_mode': 'form',
                'res_id': created_docs.id,
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tax Documents'),
                'res_model': 'l10n_ua.tax.cabinet.document',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_docs.ids)],
            }

    def _sync_reported_documents(self):
        """Sync reported documents from cabinet."""
        docs_data = self.config_id._api_get_document_list(self.year, int(self.month))
        return self._process_api_documents(docs_data, 'reg_doc')

    def _sync_incoming_documents(self):
        """Sync incoming correspondence from cabinet."""
        docs_data = self.config_id._api_get_incoming_documents()
        return self._process_api_documents(docs_data, 'incoming')

    def _sync_sent_documents(self):
        """Sync sent correspondence from cabinet."""
        docs_data = self.config_id._api_get_sent_documents()
        return self._process_api_documents(docs_data, 'sent')

    def _process_api_documents(self, docs_data, doc_type):
        """Process documents from API response."""
        created_docs = self.env['l10n_ua.tax.cabinet.document']
        Document = self.env['l10n_ua.tax.cabinet.document']

        if not docs_data:
            return created_docs

        # Handle paginated response from cabinet.tax.gov.ua
        if isinstance(docs_data, dict):
            docs_data = docs_data.get('content', docs_data.get('items', docs_data.get('data', [])))

        for doc_item in docs_data:
            # reg_doc uses 'codRegdoc', correspondence uses 'id'
            external_id = str(doc_item.get('codRegdoc') or doc_item.get('id', ''))
            if not external_id:
                continue

            # Check if already synced
            existing = Document.search([
                ('external_id', '=', external_id),
                ('source', '=', 'cabinet'),
            ], limit=1)

            if existing:
                _logger.debug("Document %s already synced", external_id)
                continue

            # Create document
            doc_vals = self._prepare_api_document_vals(doc_item, doc_type)
            doc = Document.create(doc_vals)
            created_docs |= doc

            # Download files
            year = doc_vals.get('year', self.year)
            if self.config_id.auto_download_xml and doc_type != 'sent':
                try:
                    xml_content = self.config_id._api_download_document_xml(year, external_id, doc_type)
                    if xml_content:
                        doc.write({
                            'file_xml': xml_content,
                            'file_xml_name': f"{external_id}.xml",
                        })
                except Exception as e:
                    _logger.warning("Could not download XML for %s: %s", external_id, str(e))

            if self.config_id.auto_download_pdf:
                try:
                    pdf_content = self.config_id._api_download_document_pdf(year, external_id, doc_type)
                    if pdf_content:
                        doc.write({
                            'file_pdf': pdf_content,
                            'file_pdf_name': f"{external_id}.pdf",
                        })
                except Exception as e:
                    _logger.warning("Could not download PDF for %s: %s", external_id, str(e))

            _logger.info("Synced tax document: %s", doc.name)

        return created_docs

    def _prepare_api_document_vals(self, doc_item, doc_type):
        """Prepare document values from API response.

        API fields:
        - reg_doc: codRegdoc, docName, doc (code), nreg, dget, periodYear, periodMonth
        - incoming: id, name/docName, cdoc, dateIn, periodYear
        - sent: id, name/docName, cdoc, dateOut, periodYear
        """
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

        # Parse date - API uses 'dget' for reg_doc, 'dateIn'/'dateOut' for correspondence
        doc_date_str = doc_item.get('dget') or doc_item.get('dateIn') or doc_item.get('dateOut')
        doc_date = fields.Date.today()
        if doc_date_str:
            try:
                # Format: "2024-04-09 20:37:54" or "2024-04-09"
                doc_date = fields.Date.from_string(doc_date_str[:10])
            except Exception:
                pass

        # Get external ID - reg_doc uses 'codRegdoc', correspondence uses 'id'
        external_id = str(doc_item.get('codRegdoc') or doc_item.get('id', ''))

        # Get document name
        doc_name = doc_item.get('docName') or doc_item.get('name') or f'Document {external_id}'

        # Get registration number
        reg_num = doc_item.get('nreg') or doc_item.get('text') or ''
        if reg_num:
            reg_num = str(reg_num)

        return {
            'name': doc_name,
            'document_type_id': doc_type_record.id if doc_type_record else False,
            'document_number': reg_num,
            'document_date': doc_date,
            'year': doc_item.get('periodYear', self.year),
            'period': str(doc_item.get('periodMonth', '')).zfill(2) if doc_item.get('periodMonth') else False,
            'company_id': self.company_id.id,
            'taxpayer_code': self.config_id.taxpayer_code,
            'source': 'cabinet',
            'external_id': external_id,
            'sync_date': fields.Datetime.now(),
            'state': 'accepted',  # Documents from cabinet are already accepted
        }


class L10nUaTaxCabinetSyncWizardFile(models.TransientModel):
    _name = 'l10n_ua.tax.cabinet.sync.wizard.file'
    _description = 'Tax Cabinet Sync Wizard File'

    wizard_id = fields.Many2one(
        'l10n_ua.tax.cabinet.sync.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    file = fields.Binary(
        string='File',
        required=True,
        attachment=False,
    )
    filename = fields.Char(
        string='Filename',
    )
    name = fields.Char(
        string='Document Name',
        help='Leave empty to extract from file',
    )
    document_type_id = fields.Many2one(
        'l10n_ua.tax.document.type',
        string='Document Type',
        required=True,
    )
    document_date = fields.Date(
        string='Document Date',
        default=fields.Date.today,
    )
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.today().year,
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
