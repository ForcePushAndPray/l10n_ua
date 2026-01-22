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
        # Prevent modifications to accepted documents
        for record in self:
            if record.state == 'accepted':
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

    def action_sign_document(self):
        """Sign the XML document with KEP."""
        self.ensure_one()
        if not self.file_xml:
            raise UserError(_("No XML file to sign"))

        # Get tax cabinet config for company
        config = self.env['l10n_ua.tax.cabinet.config'].search([
            ('company_id', '=', self.company_id.id),
            ('auth_method', '=', 'kep'),
        ], limit=1)

        if not config:
            raise UserError(_(
                "No KEP configuration found for company %s. "
                "Please configure Tax Cabinet connection with KEP authentication."
            ) % self.company_id.name)

        if not config.kep_key_file or not config.kep_password:
            raise UserError(_("KEP key file and password are required for signing."))

        try:
            from ..lib.tax_cabinet_auth import KEPSigner
        except ImportError as e:
            raise UserError(_("KEP signing library not available: %s") % str(e))

        import os
        lib_path = config.iit_lib_path or '/opt/iit/eu/sw'
        cert_path = config.iit_cert_path or '/opt/iit/certificates'

        os.environ['IIT_LIB_PATH'] = lib_path
        os.environ['IIT_CERT_PATH'] = cert_path

        # Decode XML content
        xml_content = base64.b64decode(self.file_xml)

        try:
            with KEPSigner(lib_path=lib_path, cert_path=cert_path) as signer:
                signer.load_certificates()
                signer.load_private_key(config.kep_key_file, config.kep_password)
                signed_data = signer.sign_data(xml_content)

            # Generate filename
            base_name = self.file_xml_name or f'document_{self.id}'
            if base_name.lower().endswith('.xml'):
                base_name = base_name[:-4]
            signed_filename = f'{base_name}.p7s'

            # Store signed document
            self.write({
                'file_signed': base64.b64encode(signed_data.encode('utf-8')),
                'file_signed_name': signed_filename,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Document signed successfully! Download the signed file.'),
                    'type': 'success',
                }
            }

        except Exception as e:
            _logger.error("Signing failed: %s", str(e))
            raise UserError(_("Signing failed: %s") % str(e))

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
            ('auth_method', '=', 'kep'),
        ], limit=1)

        if not config:
            raise UserError(_("No KEP configuration found for company %s.") % self.company_id.name)

        if not config.kep_key_file or not config.kep_password:
            raise UserError(_("KEP key file and password are required for submission."))

        try:
            from ..lib.tax_cabinet_auth import KEPSigner, TaxCabinetAuthError
        except ImportError as e:
            raise UserError(_("KEP signing library not available: %s") % str(e))

        import os
        import requests

        lib_path = config.iit_lib_path or '/opt/iit/eu/sw'
        cert_path = config.iit_cert_path or '/opt/iit/certificates'

        os.environ['IIT_LIB_PATH'] = lib_path
        os.environ['IIT_CERT_PATH'] = cert_path

        # Find DPS encryption certificate
        dps_cert_path = os.path.join(cert_path, 'Шлюз ДПС (Сервіс обміну з державними установами -2).cer')
        if not os.path.exists(dps_cert_path):
            # Try alternative name
            import glob
            cert_files = glob.glob(os.path.join(cert_path, '*Шлюз*ДПС*.cer'))
            if cert_files:
                dps_cert_path = cert_files[0]
            else:
                raise UserError(_("DPS encryption certificate not found in %s") % cert_path)

        with open(dps_cert_path, 'rb') as f:
            dps_cert = f.read()

        # Decode XML content
        xml_content = base64.b64decode(self.file_xml)

        try:
            with KEPSigner(lib_path=lib_path, cert_path=cert_path) as signer:
                signer.load_certificates()
                signer.load_private_key(config.kep_key_file, config.kep_password)

                # Sign and envelope the document
                enveloped_data = signer.sign_and_envelope(xml_content, dps_cert)

            # Get auth headers
            auth_header = config._get_auth_headers()

            # Submit to cabinet API
            submit_url = "https://cabinet.tax.gov.ua/cabinet/public/api/exchange/report"

            headers = {
                'Authorization': auth_header,
                'Content-Type': 'application/octet-stream',
                'Accept': 'application/json',
            }

            # Submit as binary data
            response = requests.post(
                submit_url,
                headers=headers,
                data=enveloped_data,
                timeout=60
            )

            _logger.info("Cabinet submission response: %s %s", response.status_code, response.text[:500])

            if response.status_code in (200, 201, 202):
                # Success
                self.write({
                    'state': 'submitted',
                    'status_message': _("Submitted successfully: %s") % response.text[:200],
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Document submitted to cabinet.tax.gov.ua!'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("Submission failed: %s %s") % (response.status_code, response.text))

        except TaxCabinetAuthError as e:
            _logger.error("Submission failed: %s", str(e))
            raise UserError(_("Submission failed: %s") % str(e))
        except Exception as e:
            _logger.error("Submission failed: %s", str(e))
            raise UserError(_("Submission failed: %s") % str(e))
