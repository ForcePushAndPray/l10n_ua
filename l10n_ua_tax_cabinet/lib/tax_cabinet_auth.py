"""
Cabinet.tax.gov.ua KEP authentication module.

This module implements OAuth2 authentication with the Ukrainian Tax Cabinet
using qualified electronic signature (KEP/КЕП).
"""

import base64
import ctypes
import glob
import logging
import os
import requests
import time

_logger = logging.getLogger(__name__)

# Default paths
DEFAULT_LIB_PATH = '/opt/iit/eu/sw'
DEFAULT_CERT_PATH = '/opt/iit/certificates'

TAX_CABINET_BASE_URL = "https://cabinet.tax.gov.ua"
TAX_CABINET_AUTH_URL = f"{TAX_CABINET_BASE_URL}/ws/auth/oauth/token"


class TaxCabinetAuthError(Exception):
    """Authentication error."""
    pass


class KEPSigner:
    """
    KEP (qualified electronic signature) signer using IIT EUSignCP library.
    """

    def __init__(self, lib_path=None, cert_path=None):
        self.lib_path = lib_path or os.environ.get('IIT_LIB_PATH', DEFAULT_LIB_PATH)
        self.cert_path = cert_path or os.environ.get('IIT_CERT_PATH', DEFAULT_CERT_PATH)
        self._lib = None
        self._initialized = False
        self._key_loaded = False

    def __enter__(self):
        self._load_library()
        self._initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._finalize()
        return False

    def _load_library(self):
        """Load the EUSignCP shared library."""
        if self._lib is not None:
            return

        lib_file = os.path.join(self.lib_path, 'euscp.so')
        if not os.path.exists(lib_file):
            raise TaxCabinetAuthError(f"IIT library not found: {lib_file}")

        try:
            self._lib = ctypes.CDLL(lib_file)
        except OSError as e:
            raise TaxCabinetAuthError(f"Failed to load IIT library: {e}")

    def _initialize(self):
        """Initialize the library."""
        if self._initialized:
            return

        self._lib.EUSetUIMode(0)
        err = self._lib.EUInitialize()
        if err != 0:
            raise TaxCabinetAuthError(f"Library initialization failed: error {err}")

        # Set file store settings
        self._lib.EUSetFileStoreSettings.argtypes = [
            ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
        ]
        self._lib.EUSetFileStoreSettings.restype = ctypes.c_uint
        self._lib.EUSetFileStoreSettings(
            self.cert_path.encode(), 0, 0, 0, 1, 0, 1, 3600
        )

        self._initialized = True

    def _finalize(self):
        """Finalize the library."""
        if self._lib and self._initialized:
            self._lib.EUResetPrivateKey()
            self._lib.EUFinalize()
            self._initialized = False
            self._key_loaded = False

    def load_certificates(self):
        """Load CA and user certificates from cert_path."""
        # Load CA bundle
        ca_bundle = os.path.join(self.cert_path, 'CACertificates.p7b')
        if os.path.exists(ca_bundle):
            self._lib.EUSaveCertificates.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            self._lib.EUSaveCertificates.restype = ctypes.c_uint
            with open(ca_bundle, 'rb') as f:
                data = f.read()
                self._lib.EUSaveCertificates(data, len(data))

        # Load user certificates
        self._lib.EUSaveCertificate.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._lib.EUSaveCertificate.restype = ctypes.c_uint
        for cert_file in glob.glob(os.path.join(self.cert_path, '*.cer')):
            with open(cert_file, 'rb') as f:
                data = f.read()
                self._lib.EUSaveCertificate(data, len(data))

        # Refresh store
        self._lib.EURefreshFileStore.argtypes = [ctypes.c_int]
        self._lib.EURefreshFileStore.restype = ctypes.c_uint
        self._lib.EURefreshFileStore(1)

    def load_private_key(self, key_path, password):
        """Load private key from file."""
        self._lib.EUReadPrivateKeyFile.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p
        ]
        self._lib.EUReadPrivateKeyFile.restype = ctypes.c_uint

        err = self._lib.EUReadPrivateKeyFile(
            key_path.encode() if isinstance(key_path, str) else key_path,
            password.encode() if isinstance(password, str) else password,
            None
        )

        if err != 0:
            self._lib.EUGetErrorDesc.argtypes = [ctypes.c_uint]
            self._lib.EUGetErrorDesc.restype = ctypes.c_char_p
            desc = self._lib.EUGetErrorDesc(err)
            error_msg = desc.decode('cp1251', errors='replace') if desc else f"Error {err}"
            raise TaxCabinetAuthError(f"Failed to load private key: {error_msg}")

        self._key_loaded = True

    def sign_data(self, data, append_cert=True):
        """
        Sign data with the loaded private key.

        Args:
            data: Data to sign (str or bytes)
            append_cert: Whether to include certificate in signature

        Returns:
            Base64-encoded signature string
        """
        if not self._key_loaded:
            raise TaxCabinetAuthError("Private key not loaded")

        if isinstance(data, str):
            data = data.encode('utf-8')

        self._lib.EUSignDataInternal.argtypes = [
            ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint)
        ]
        self._lib.EUSignDataInternal.restype = ctypes.c_uint

        signed_str = ctypes.c_char_p()
        signed_bin = ctypes.c_void_p()
        signed_len = ctypes.c_uint()

        err = self._lib.EUSignDataInternal(
            1 if append_cert else 0,
            data, len(data),
            ctypes.byref(signed_str),
            ctypes.byref(signed_bin),
            ctypes.byref(signed_len)
        )

        if err != 0:
            self._lib.EUGetErrorDesc.argtypes = [ctypes.c_uint]
            self._lib.EUGetErrorDesc.restype = ctypes.c_char_p
            desc = self._lib.EUGetErrorDesc(err)
            error_msg = desc.decode('cp1251', errors='replace') if desc else f"Error {err}"
            raise TaxCabinetAuthError(f"Failed to sign data: {error_msg}")

        if signed_str.value:
            result = signed_str.value.decode('utf-8')
            self._lib.EUFreeMemory.argtypes = [ctypes.c_void_p]
            self._lib.EUFreeMemory(signed_str)
            return result
        else:
            # Binary result - convert to base64
            result = ctypes.string_at(signed_bin, signed_len.value)
            self._lib.EUFreeMemory.argtypes = [ctypes.c_void_p]
            self._lib.EUFreeMemory(signed_bin)
            return base64.b64encode(result).decode('utf-8')

    def envelope_data(self, recipient_cert, data):
        """
        Envelope (encrypt) data for a recipient using raw envelope.

        Args:
            recipient_cert: Recipient's certificate data (bytes)
            data: Data to envelope (bytes or string)

        Returns:
            Enveloped data as bytes
        """
        if isinstance(data, str):
            data = data.encode('utf-8')

        # Setup EURawEnvelopData
        self._lib.EURawEnvelopData.argtypes = [
            ctypes.c_void_p,  # pbRecipientCert
            ctypes.c_uint,    # dwRecipientCertLength
            ctypes.c_void_p,  # pbData
            ctypes.c_uint,    # dwDataLength
            ctypes.POINTER(ctypes.c_char_p),   # ppszEnvelopedData
            ctypes.POINTER(ctypes.c_void_p),   # ppbEnvelopedData
            ctypes.POINTER(ctypes.c_uint)      # pdwEnvelopedDataLength
        ]
        self._lib.EURawEnvelopData.restype = ctypes.c_uint

        env_data_str = ctypes.c_char_p()
        env_data_bin = ctypes.c_void_p()
        env_data_len = ctypes.c_uint()

        err = self._lib.EURawEnvelopData(
            recipient_cert,
            len(recipient_cert),
            data,
            len(data),
            ctypes.byref(env_data_str),
            ctypes.byref(env_data_bin),
            ctypes.byref(env_data_len)
        )

        if err != 0:
            self._lib.EUGetErrorDesc.argtypes = [ctypes.c_uint]
            self._lib.EUGetErrorDesc.restype = ctypes.c_char_p
            desc = self._lib.EUGetErrorDesc(err)
            error_msg = desc.decode('cp1251', errors='replace') if desc else f"Error {err}"
            raise TaxCabinetAuthError(f"Failed to envelope data: {error_msg}")

        # Get the result
        if env_data_str.value:
            result = env_data_str.value
            self._lib.EUFreeMemory.argtypes = [ctypes.c_void_p]
            self._lib.EUFreeMemory(env_data_str)
            return result
        else:
            result = ctypes.string_at(env_data_bin, env_data_len.value)
            self._lib.EUFreeMemory.argtypes = [ctypes.c_void_p]
            self._lib.EUFreeMemory(env_data_bin)
            return result

    def sign_and_envelope(self, data, recipient_cert):
        """
        Sign data and then envelope (encrypt) for recipient.

        Args:
            data: Data to sign and envelope (bytes or string)
            recipient_cert: Recipient's certificate data (bytes)

        Returns:
            Signed and enveloped data as bytes
        """
        # First sign the data
        signed_data = self.sign_data(data)

        # Then envelope it for the recipient
        return self.envelope_data(recipient_cert, signed_data)

