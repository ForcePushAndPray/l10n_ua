import base64
import logging
import os
import time
from datetime import datetime

import httpx
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Tax Cabinet API endpoints
TAX_CABINET_BASE_URL = "https://cabinet.tax.gov.ua"
TAX_CABINET_TEST_URL = "https://cabinet.tax.gov.ua:9443"  # Test environment (not fiscal)
TAX_CABINET_API_PATH = "/ws/public_api"

# DPS Server certificates for encryption
# Updated August 2025, see: https://tax.gov.ua/media-tsentr/novini/920738.html
DPS_ENCRYPT_CERT_URL = "https://cabinet.tax.gov.ua/cabinet/resources/js/sign/data/EK_C_NEW.cer"
DPS_SIGN_CERT_URL = "https://cabinet.tax.gov.ua/cabinet/resources/js/sign/data/EK_S_NEW.cer"

# Default IIT library paths
DEFAULT_IIT_LIB_PATH = '/opt/iit/eu/sw'
DEFAULT_IIT_CERT_PATH = '/opt/iit/certificates'

# Auth header cache: {config_id: {'header': str, 'timestamp': float}}
# Signatures are valid for ~10 min, cache for 5 min to be safe
_AUTH_HEADER_CACHE = {}
_AUTH_CACHE_TTL = 300  # 5 minutes


class L10nUaTaxCabinetConfig(models.Model):
    _name = 'l10n_ua.tax.cabinet.config'
    _description = 'Tax Cabinet Configuration'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Name',
        required=True,
        default='Tax Cabinet Connection',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    taxpayer_code = fields.Char(
        string='Taxpayer Code',
        required=True,
        help='EDRPOU (for companies) or RNOKPP (for FOP)',
    )
    active = fields.Boolean(
        default=True,
    )

    # KEP settings
    kep_key_file = fields.Binary(
        string='KEP Key File',
        attachment=True,
        help='Private key file (.dat, .jks, .pfx)',
    )
    kep_key_filename = fields.Char(
        string='Key Filename',
    )
    iit_lib_path = fields.Char(
        string='IIT Library Path',
        default=DEFAULT_IIT_LIB_PATH,
        help='Path to IIT EUSignCP library',
    )
    iit_cert_path = fields.Char(
        string='IIT Certificates Path',
        default=DEFAULT_IIT_CERT_PATH,
        help='Path to certificates directory (CA certs, user certs)',
    )
    # Note: Password is NOT stored - always requested via wizard

    # Sync settings
    last_sync_date = fields.Datetime(
        string='Last Sync',
        readonly=True,
    )
    auto_download_pdf = fields.Boolean(
        string='Auto Download PDF',
        default=True,
        help='Automatically download PDF version of documents',
    )
    auto_download_xml = fields.Boolean(
        string='Auto Download XML',
        default=True,
        help='Automatically download XML version of documents',
    )

    # Environment settings
    use_test_environment = fields.Boolean(
        string='Use Test Environment',
        default=False,
        help='Use test API (cabinet.tax.gov.ua:9443). '
             'Documents submitted to test environment are NOT fiscal - '
             'they do not go to the real tax office. '
             'Use this for testing before real submission.',
    )

    _unique_company = models.Constraint(
        'UNIQUE(company_id)',
        'Only one configuration per company allowed!',
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.taxpayer_code = self.company_id.vat or self.company_id.company_registry

    def _get_api_url(self):
        """Get API URL based on environment setting."""
        self.ensure_one()
        base_url = TAX_CABINET_TEST_URL if self.use_test_environment else TAX_CABINET_BASE_URL
        return f"{base_url}{TAX_CABINET_API_PATH}"

    def _get_base_url(self):
        """Get base URL based on environment setting."""
        self.ensure_one()
        return TAX_CABINET_TEST_URL if self.use_test_environment else TAX_CABINET_BASE_URL

    def _clear_auth_cache(self):
        """Clear cached auth header for this config."""
        if self.id in _AUTH_HEADER_CACHE:
            del _AUTH_HEADER_CACHE[self.id]
            _logger.debug("Cleared auth header cache for config %s", self.id)

    def _sign_with_kep(self, data, password):
        """Sign data using KEP (qualified electronic signature).

        Args:
            data: Data to sign
            password: KEP password (not stored, passed from wizard)
        """
        self.ensure_one()

        if not self.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        if not password:
            raise UserError(_("KEP password is required for signing."))

        try:
            from ..lib.tax_cabinet_auth import KEPSigner
        except ImportError as e:
            raise UserError(_("KEP signing library not available: %s") % str(e))

        lib_path = self.iit_lib_path or DEFAULT_IIT_LIB_PATH
        cert_path = self.iit_cert_path or DEFAULT_IIT_CERT_PATH

        # Set environment variables for the library
        os.environ['IIT_LIB_PATH'] = lib_path
        os.environ['IIT_CERT_PATH'] = cert_path

        # Decode binary key file to temp file
        import tempfile
        key_data = base64.b64decode(self.kep_key_file)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.dat') as tmp_key:
            tmp_key.write(key_data)
            tmp_key_path = tmp_key.name

        try:
            with KEPSigner(lib_path=lib_path, cert_path=cert_path) as signer:
                signer.load_certificates()
                signer.load_private_key(tmp_key_path, password)
                return signer.sign_data(data)
        except Exception as e:
            _logger.error("KEP signing failed: %s", str(e))
            raise UserError(_("KEP signing failed: %s") % str(e))
        finally:
            # Always clean up temp file
            if os.path.exists(tmp_key_path):
                os.unlink(tmp_key_path)

    def _get_dps_encrypt_certificate(self):
        """Download and cache DPS encryption certificate.

        The certificate is used to encrypt documents before submission.
        Certificate URL: https://cabinet.tax.gov.ua/cabinet/resources/js/sign/data/EK_C_NEW.cer
        """
        # Check if we have a cached certificate in the attachment
        attachment = self.env['ir.attachment'].search([
            ('name', '=', 'DPS_EK_C_NEW.cer'),
            ('res_model', '=', 'l10n_ua.tax.cabinet.config'),
            ('res_id', '=', self.id),
        ], limit=1)

        if attachment:
            return base64.b64decode(attachment.datas)

        # Download certificate
        _logger.info("Downloading DPS encryption certificate from %s", DPS_ENCRYPT_CERT_URL)
        try:
            response = requests.get(DPS_ENCRYPT_CERT_URL, timeout=30)
            if response.status_code == 200:
                cert_data = response.content

                # Cache as attachment
                self.env['ir.attachment'].create({
                    'name': 'DPS_EK_C_NEW.cer',
                    'type': 'binary',
                    'datas': base64.b64encode(cert_data),
                    'res_model': 'l10n_ua.tax.cabinet.config',
                    'res_id': self.id,
                })

                return cert_data
            else:
                raise UserError(_("Failed to download DPS certificate: HTTP %s") % response.status_code)
        except requests.RequestException as e:
            raise UserError(_("Failed to download DPS certificate: %s") % str(e))

    def _sign_and_encrypt_for_dps(self, data, password):
        """Sign data with KEP and encrypt for DPS server.

        Args:
            data: Data to sign and encrypt (bytes or string)
            password: KEP password

        Returns:
            Base64-encoded signed and encrypted data
        """
        self.ensure_one()

        if not self.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        if not password:
            raise UserError(_("KEP password is required for signing."))

        try:
            from ..lib.tax_cabinet_auth import KEPSigner
        except ImportError as e:
            raise UserError(_("KEP signing library not available: %s") % str(e))

        lib_path = self.iit_lib_path or DEFAULT_IIT_LIB_PATH
        cert_path = self.iit_cert_path or DEFAULT_IIT_CERT_PATH

        os.environ['IIT_LIB_PATH'] = lib_path
        os.environ['IIT_CERT_PATH'] = cert_path

        # Get DPS encryption certificate
        dps_cert = self._get_dps_encrypt_certificate()

        # Decode binary key file to temp file
        import tempfile
        key_data = base64.b64decode(self.kep_key_file)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.dat') as tmp_key:
            tmp_key.write(key_data)
            tmp_key_path = tmp_key.name

        try:
            with KEPSigner(lib_path=lib_path, cert_path=cert_path) as signer:
                signer.load_certificates()
                signer.load_private_key(tmp_key_path, password)

                # Sign and then encrypt for DPS
                signed_and_encrypted = signer.sign_and_envelope(data, dps_cert)

                # Return as base64 string
                if isinstance(signed_and_encrypted, bytes):
                    return base64.b64encode(signed_and_encrypted).decode('utf-8')
                return signed_and_encrypted

        except Exception as e:
            _logger.error("Sign and encrypt failed: %s", str(e))
            raise UserError(_("Sign and encrypt failed: %s") % str(e))
        finally:
            if os.path.exists(tmp_key_path):
                os.unlink(tmp_key_path)

    def _get_auth_headers(self, password=None, use_cache=True):
        """Get authorization headers for API requests.

        Args:
            password: KEP password (required if cache is empty/expired). Can also be in context.
            use_cache: If True, use cached signed header (default). Set False to force re-sign.
        """
        self.ensure_one()

        if not self.kep_key_file:
            raise UserError(_("KEP key file is required. Please upload your private key."))

        # Get password from argument or context
        if not password:
            password = self.env.context.get('kep_password')

        # Check cache first
        cache_key = self.id
        now = time.time()

        if use_cache and cache_key in _AUTH_HEADER_CACHE:
            cached = _AUTH_HEADER_CACHE[cache_key]
            if now - cached['timestamp'] < _AUTH_CACHE_TTL:
                auth_header = cached['header']
                _logger.debug("Using cached KEP auth header (age: %.1fs)", now - cached['timestamp'])
                return {
                    'Authorization': auth_header,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/plain, */*',
                    'Lang': 'uk',
                }
            else:
                # Expired, remove from cache
                del _AUTH_HEADER_CACHE[cache_key]

        # Need password to sign
        if not password:
            raise UserError(_("KEP password is required for signing."))

        # Sign taxpayer code with KEP
        signed_data = self._sign_with_kep(self.taxpayer_code, password)
        auth_header = signed_data

        # Cache it
        _AUTH_HEADER_CACHE[cache_key] = {
            'header': auth_header,
            'timestamp': now,
        }
        _logger.debug("Created and cached new KEP auth header")

        return {
            'Authorization': auth_header,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Lang': 'uk',
        }

    def action_test_connection(self):
        """Open password wizard to test API connection."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enter KEP Password'),
            'res_model': 'l10n_ua.tax.cabinet.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_action': 'test',
            },
        }

    def _do_test_connection(self, password):
        """Actually test API connection with provided password."""
        self.ensure_one()
        try:
            # Try to get payer card (basic info)
            headers = self._get_auth_headers(password=password)
            api_url = self._get_api_url()
            url = f"{api_url}/payer_card"

            env_name = "TEST" if self.use_test_environment else "PRODUCTION"
            _logger.info("Tax Cabinet API [%s]: Testing connection to %s", env_name, url)
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                # Extract name from response
                name = "Unknown"
                for item in data:
                    if item.get('values', {}).get('FULL_NAME'):
                        name = item['values']['FULL_NAME']
                        break
                return True, name
            else:
                return False, _("API error %s: %s") % (response.status_code, response.text)

        except Exception as e:
            return False, str(e)

    def _api_get_document_list(self, year, month):
        """
        Get list of reported documents for period.

        GET /ws/public_api/reg_doc/list?periodYear=YYYY&periodMonth=MM
        """
        self.ensure_one()
        api_url = self._get_api_url()
        url = f"{api_url}/reg_doc/list"
        params = {
            'periodYear': year,
            'periodMonth': month,
        }
        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s params=%s", url, params)
        response = requests.get(url, params=params, headers=headers, timeout=30)

        if response.status_code != 200:
            raise UserError(_("API error %s: %s") % (response.status_code, response.text))

        return response.json()

    def _api_get_incoming_documents(self, page=1):
        """
        Get incoming correspondence.

        GET /ws/public_api/post/incoming?page=N
        """
        self.ensure_one()
        api_url = self._get_api_url()
        url = f"{api_url}/post/incoming"
        params = {'page': page}
        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s params=%s", url, params)
        response = requests.get(url, params=params, headers=headers, timeout=30)

        if response.status_code != 200:
            raise UserError(_("API error %s: %s") % (response.status_code, response.text))

        return response.json()

    def _api_get_sent_documents(self, page=1):
        """
        Get outgoing correspondence.

        GET /ws/public_api/post/sent?page=N
        """
        self.ensure_one()
        api_url = self._get_api_url()
        url = f"{api_url}/post/sent"
        params = {'page': page}
        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s params=%s", url, params)
        response = requests.get(url, params=params, headers=headers, timeout=30)

        if response.status_code != 200:
            raise UserError(_("API error %s: %s") % (response.status_code, response.text))

        return response.json()

    def _api_download_document_pdf(self, year, doc_id, doc_type='reg_doc'):
        """
        Download document PDF.

        GET /ws/public_api/reg_doc/doc/{year}/{id}/pdf
        GET /ws/public_api/post/incoming/{year}/{id}/pdf
        GET /ws/public_api/post/sent/{year}/{id}/pdf
        """
        self.ensure_one()
        api_url = self._get_api_url()

        if doc_type == 'reg_doc':
            url = f"{api_url}/reg_doc/doc/{year}/{doc_id}/pdf"
        elif doc_type == 'incoming':
            url = f"{api_url}/post/incoming/{year}/{doc_id}/pdf"
        elif doc_type == 'sent':
            url = f"{api_url}/post/sent/{year}/{doc_id}/pdf"
        else:
            raise ValueError(f"Unknown doc_type: {doc_type}")

        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s", url)
        response = requests.get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            _logger.warning("Failed to download PDF: %s", response.status_code)
            return None

        return base64.b64encode(response.content)

    def _api_download_document_xml(self, year, doc_id, doc_type='reg_doc'):
        """
        Download document XML.

        GET /ws/public_api/reg_doc/doc/{year}/{id}/xml
        GET /ws/public_api/post/incoming/{year}/{id}/xml
        """
        self.ensure_one()
        api_url = self._get_api_url()

        if doc_type == 'reg_doc':
            url = f"{api_url}/reg_doc/doc/{year}/{doc_id}/xml"
        elif doc_type == 'incoming':
            url = f"{api_url}/post/incoming/{year}/{doc_id}/xml"
        else:
            raise ValueError(f"Unknown doc_type for XML: {doc_type}")

        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s", url)
        response = requests.get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            _logger.warning("Failed to download XML: %s", response.status_code)
            return None

        return base64.b64encode(response.content)

    def _api_submit_document(self, signed_content, filename, password):
        """
        Submit signed document to Tax Cabinet.

        POST /cabinet/public/api/exchange/report
        Content-Type: application/json

        Request body format:
        {
            "list": [
                {
                    "contentBase64": "...",
                    "fname": "..."
                }
            ]
        }

        The document must be signed, encrypted and Base64 encoded.

        NOTE: Test environment (port 9443) is ONLY for PRRO (cash registers).
        Report submission always uses production endpoint.

        Args:
            signed_content: Base64-encoded signed and encrypted document
            filename: Document filename (e.g., F0103309_2025_Q3.xml)
            password: KEP password for authentication
        """
        self.ensure_one()

        # IMPORTANT: Test environment (port 9443) only supports PRRO operations.
        # Report submission must use production endpoint.
        # See: https://cabinet.tax.gov.ua/help/api.html
        base_url = TAX_CABINET_BASE_URL  # Always use production for reports

        if self.use_test_environment:
            _logger.warning(
                "Test environment is only for PRRO (cash registers). "
                "Report submission will use production: %s", base_url
            )

        # Use the exchange/report endpoint for document submission
        url = f"{base_url}/cabinet/public/api/exchange/report"
        headers = self._get_auth_headers(password=password)
        # Don't set Content-Type explicitly - let requests library handle it
        # when using json= parameter (it will set application/json automatically)
        # Remove any pre-set Content-Type that might conflict
        headers.pop('Content-Type', None)
        headers['Accept'] = 'application/json, */*'

        # Prepare JSON payload with list array as per API spec
        content_b64 = signed_content if isinstance(signed_content, str) else signed_content.decode('utf-8')
        payload = {
            'list': [
                {
                    'contentBase64': content_b64,
                    'fname': filename,
                }
            ]
        }

        _logger.info("Tax Cabinet API [PRODUCTION]: POST %s", url)
        _logger.info("Payload filename: %s, content length: %d chars", filename, len(content_b64))

        # Remove Content-Type - let requests set it properly for json=
        submit_headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}

        try:
            # According to docs: POST /cabinet/public/api/exchange/report
            # Body: {"list": [{"contentBase64": "...", "fname": "..."}]}
            # Content-Type: application/json

            _logger.info("Request headers (without Content-Type): %s",
                        {k: (v[:50] + '...' if len(str(v)) > 50 else v)
                         for k, v in submit_headers.items()})

            response = requests.post(
                url,
                json=payload,
                headers=submit_headers,
                timeout=120,
            )

            _logger.info("Response status: %s", response.status_code)
            _logger.info("Response headers: %s", dict(response.headers))
            _logger.info("Response body (first 500 chars): %s", response.text[:500] if response.text else "empty")

        except requests.RequestException as e:
            _logger.error("Request failed: %s", str(e))
            raise UserError(_("Connection failed: %s") % str(e))

        if response.status_code in (200, 201, 202):
            _logger.info("Document submitted successfully")
            try:
                result = response.json()
            except Exception:
                result = {'message': response.text}
            return result
        else:
            error_msg = response.text
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_data.get('error', str(error_data)))
            except Exception:
                pass
            raise UserError(_("Submission failed (%s): %s") % (response.status_code, error_msg))

    def action_open_sync_wizard(self):
        """Open sync wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync with Tax Cabinet'),
            'res_model': 'l10n_ua.tax.cabinet.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_mode': 'sync',
            },
        }
