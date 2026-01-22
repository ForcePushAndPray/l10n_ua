import base64
import logging
import os
import requests
import time
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Tax Cabinet API endpoints
TAX_CABINET_BASE_URL = "https://cabinet.tax.gov.ua"
TAX_CABINET_API_URL = f"{TAX_CABINET_BASE_URL}/ws/public_api"

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

    # KEP Authentication
    auth_method = fields.Selection(
        selection=[
            ('kep', 'KEP (Private Key)'),
            ('token', 'Manual Token'),
        ],
        string='Auth Method',
        default='kep',
        required=True,
    )

    # KEP settings
    kep_key_file = fields.Char(
        string='KEP Key File',
        help='Path to private key file (.dat, .jks, .pfx)',
    )
    kep_password = fields.Char(
        string='KEP Password',
        help='Password for the private key file',
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

    # Manual token auth (fallback)
    auth_token = fields.Char(
        string='Auth Token',
        help='Signed authorization token (for manual auth)',
    )

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

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', 'Only one configuration per company allowed!'),
    ]

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.taxpayer_code = self.company_id.vat or self.company_id.company_registry

    def _clear_auth_cache(self):
        """Clear cached auth header for this config."""
        if self.id in _AUTH_HEADER_CACHE:
            del _AUTH_HEADER_CACHE[self.id]
            _logger.debug("Cleared auth header cache for config %s", self.id)

    def _sign_with_kep(self, data):
        """Sign data using KEP (qualified electronic signature)."""
        self.ensure_one()

        if not self.kep_key_file or not self.kep_password:
            raise UserError(_("KEP key file and password are required for KEP authentication."))

        if not os.path.exists(self.kep_key_file):
            raise UserError(_("KEP key file not found: %s") % self.kep_key_file)

        try:
            from ..lib.tax_cabinet_auth import KEPSigner
        except ImportError as e:
            raise UserError(_("KEP signing library not available: %s") % str(e))

        lib_path = self.iit_lib_path or DEFAULT_IIT_LIB_PATH
        cert_path = self.iit_cert_path or DEFAULT_IIT_CERT_PATH

        # Set environment variables for the library
        os.environ['IIT_LIB_PATH'] = lib_path
        os.environ['IIT_CERT_PATH'] = cert_path

        try:
            with KEPSigner(lib_path=lib_path, cert_path=cert_path) as signer:
                signer.load_certificates()
                signer.load_private_key(self.kep_key_file, self.kep_password)
                return signer.sign_data(data)
        except Exception as e:
            _logger.error("KEP signing failed: %s", str(e))
            raise UserError(_("KEP signing failed: %s") % str(e))

    def _get_auth_headers(self, use_cache=True):
        """Get authorization headers for API requests.

        Args:
            use_cache: If True, use cached signed header (default). Set False to force re-sign.
        """
        self.ensure_one()

        if self.auth_method == 'kep':
            # Check cache first
            cache_key = self.id
            now = time.time()

            if use_cache and cache_key in _AUTH_HEADER_CACHE:
                cached = _AUTH_HEADER_CACHE[cache_key]
                if now - cached['timestamp'] < _AUTH_CACHE_TTL:
                    auth_header = cached['header']
                    _logger.debug("Using cached KEP auth header (age: %.1fs)", now - cached['timestamp'])
                else:
                    # Expired, remove from cache
                    del _AUTH_HEADER_CACHE[cache_key]
                    auth_header = None
            else:
                auth_header = None

            if not auth_header:
                # Sign taxpayer code with KEP
                signed_data = self._sign_with_kep(self.taxpayer_code)
                auth_header = signed_data
                # Cache it
                _AUTH_HEADER_CACHE[cache_key] = {
                    'header': auth_header,
                    'timestamp': now,
                }
                _logger.debug("Created and cached new KEP auth header")

        elif self.auth_method == 'token' and self.auth_token:
            auth_header = self.auth_token.strip()
        else:
            raise UserError(_(
                "No valid authorization. Configure KEP key or provide auth token."
            ))

        return {
            'Authorization': auth_header,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Lang': 'uk',
        }

    def action_test_connection(self):
        """Test API connection."""
        self.ensure_one()
        try:
            # Try to get payer card (basic info)
            headers = self._get_auth_headers()
            url = f"{TAX_CABINET_API_URL}/payer_card"

            _logger.info("Tax Cabinet API: Testing connection to %s", url)
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                # Extract name from response
                name = "Unknown"
                for item in data:
                    if item.get('values', {}).get('FULL_NAME'):
                        name = item['values']['FULL_NAME']
                        break

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connection successful! Taxpayer: %s') % name,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_("API error %s: %s") % (response.status_code, response.text))

        except Exception as e:
            raise UserError(_("Connection failed: %s") % str(e))

    def _api_get_document_list(self, year, month):
        """
        Get list of reported documents for period.

        GET /ws/public_api/reg_doc/list?periodYear=YYYY&periodMonth=MM
        """
        self.ensure_one()
        url = f"{TAX_CABINET_API_URL}/reg_doc/list"
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
        url = f"{TAX_CABINET_API_URL}/post/incoming"
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
        url = f"{TAX_CABINET_API_URL}/post/sent"
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

        if doc_type == 'reg_doc':
            url = f"{TAX_CABINET_API_URL}/reg_doc/doc/{year}/{doc_id}/pdf"
        elif doc_type == 'incoming':
            url = f"{TAX_CABINET_API_URL}/post/incoming/{year}/{doc_id}/pdf"
        elif doc_type == 'sent':
            url = f"{TAX_CABINET_API_URL}/post/sent/{year}/{doc_id}/pdf"
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

        if doc_type == 'reg_doc':
            url = f"{TAX_CABINET_API_URL}/reg_doc/doc/{year}/{doc_id}/xml"
        elif doc_type == 'incoming':
            url = f"{TAX_CABINET_API_URL}/post/incoming/{year}/{doc_id}/xml"
        else:
            raise ValueError(f"Unknown doc_type for XML: {doc_type}")

        headers = self._get_auth_headers()

        _logger.info("Tax Cabinet API: GET %s", url)
        response = requests.get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            _logger.warning("Failed to download XML: %s", response.status_code)
            return None

        return base64.b64encode(response.content)

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
