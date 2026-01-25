from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nUaTaxCabinetPasswordWizard(models.TransientModel):
    """Wizard to request KEP password for secure operations."""
    _name = 'l10n_ua.tax.cabinet.password.wizard'
    _description = 'KEP Password Wizard'

    config_id = fields.Many2one(
        'l10n_ua.tax.cabinet.config',
        string='Configuration',
        required=True,
    )
    action = fields.Selection(
        selection=[
            ('test', 'Test Connection'),
            ('sync', 'Sync Documents'),
            ('redownload', 'Re-download Files'),
            ('sign', 'Sign Document'),
            ('submit', 'Submit to Cabinet'),
        ],
        string='Action',
        required=True,
        default='test',
    )
    password = fields.Char(
        string='KEP Password',
        required=True,
        help='Password for your private key (not stored)',
    )

    # For redownload action
    document_id = fields.Many2one(
        'l10n_ua.tax.document',
        string='Document',
    )

    # For sync action
    sync_mode = fields.Selection(
        selection=[
            ('reported', 'Reported Documents'),
            ('incoming', 'Incoming Correspondence'),
            ('sent', 'Sent Correspondence'),
            ('all', 'All Documents'),
        ],
        string='Sync Mode',
        default='all',
    )
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.today().year,
    )
    month = fields.Integer(
        string='Month',
        default=lambda self: fields.Date.today().month,
    )

    def action_confirm(self):
        """Execute the action with provided password."""
        self.ensure_one()

        if self.action == 'test':
            return self._do_test_connection()
        elif self.action == 'sync':
            return self._do_sync_documents()
        elif self.action == 'redownload':
            return self._do_redownload_files()
        elif self.action == 'sign':
            return self._do_sign_document()
        elif self.action == 'submit':
            return self._do_submit_document()

    def _do_test_connection(self):
        """Test connection with provided password."""
        success, result = self.config_id._do_test_connection(self.password)

        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Connection successful! Taxpayer: %s') % result,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_("Connection failed: %s") % result)

    def _do_sync_documents(self):
        """Sync documents with provided password."""
        # Pass password in context for all operations
        ctx = dict(self.env.context, kep_password=self.password)
        config = self.config_id.with_context(ctx)
        Document = self.env['l10n_ua.tax.document'].with_context(ctx)

        imported = 0

        try:
            if self.sync_mode in ('reported', 'all'):
                count = Document._sync_reported_documents(config, self.year, self.month)
                imported += count

            if self.sync_mode in ('incoming', 'all'):
                count = Document._sync_incoming_documents(config)
                imported += count

            if self.sync_mode in ('sent', 'all'):
                count = Document._sync_sent_documents(config)
                imported += count

            # Update last sync date
            self.config_id.write({'last_sync_date': fields.Datetime.now()})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sync Complete'),
                    'message': _('Imported %d documents') % imported,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            raise UserError(_("Sync failed: %s") % str(e))

    def _do_redownload_files(self):
        """Re-download files for a document."""
        if not self.document_id:
            raise UserError(_("No document specified for re-download."))

        # Pass password in context
        ctx = dict(self.env.context, kep_password=self.password)
        config = self.config_id.with_context(ctx)

        try:
            downloaded = self.document_id._do_redownload_files(config)

            if downloaded:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Download Complete'),
                        'message': _('Downloaded: %s') % ', '.join(downloaded),
                        'type': 'success',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window',
                            'res_model': 'l10n_ua.tax.document',
                            'res_id': self.document_id.id,
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                        },
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Files'),
                        'message': _('Could not download any files. Check logs for details.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }

        except Exception as e:
            raise UserError(_("Download failed: %s") % str(e))

    def _do_sign_document(self):
        """Sign document XML with KEP."""
        if not self.document_id:
            raise UserError(_("No document specified for signing."))

        if not self.document_id.file_xml:
            raise UserError(_("Document has no XML file to sign."))

        # Pass password in context
        ctx = dict(self.env.context, kep_password=self.password)
        config = self.config_id.with_context(ctx)

        try:
            # Sign the document
            self.document_id._do_sign_document(config, self.password)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Document Signed'),
                    'message': _('Document has been signed with KEP.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'l10n_ua.tax.document',
                        'res_id': self.document_id.id,
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                    },
                }
            }

        except Exception as e:
            raise UserError(_("Signing failed: %s") % str(e))

    def _do_submit_document(self):
        """Submit signed document to cabinet.tax.gov.ua."""
        if not self.document_id:
            raise UserError(_("No document specified for submission."))

        if not self.document_id.file_signed:
            raise UserError(_("Document must be signed first. Use 'Sign Document' button."))

        # Pass password in context
        ctx = dict(self.env.context, kep_password=self.password)
        config = self.config_id.with_context(ctx)

        try:
            # Submit to cabinet (document already signed)
            result = self.document_id._do_submit_to_cabinet(config, self.password)

            # Update document state
            self.document_id.write({
                'state': 'submitted',
                'status_message': result.get('message', _('Submitted successfully')),
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Document Submitted'),
                    'message': _('Document has been submitted to Tax Cabinet.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'l10n_ua.tax.document',
                        'res_id': self.document_id.id,
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                    },
                }
            }

        except Exception as e:
            raise UserError(_("Submission failed: %s") % str(e))
