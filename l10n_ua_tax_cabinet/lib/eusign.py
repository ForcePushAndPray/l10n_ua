"""
Python wrapper for IIT EUSignCP library (Ukrainian qualified electronic signature).

This module provides a Python interface to the IIT End User library for working
with Ukrainian KEP (qualified electronic signature).
"""

import ctypes
import os
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)

# Library paths
IIT_LIB_PATH = os.environ.get('IIT_LIB_PATH', '/opt/iit/eu/sw')
IIT_CERT_PATH = os.environ.get('IIT_CERT_PATH', '/data/certificates')


class EUSignError(Exception):
    """Exception raised for EUSign library errors."""
    def __init__(self, error_code, message=None):
        self.error_code = error_code
        self.message = message or f"EUSign error {error_code}"
        super().__init__(self.message)


class EU_CERT_OWNER_INFO(ctypes.Structure):
    """Certificate owner information structure."""
    _fields_ = [
        ("filled", ctypes.c_int),
        ("issuer", ctypes.c_char_p),
        ("issuerCN", ctypes.c_char_p),
        ("serial", ctypes.c_char_p),
        ("subject", ctypes.c_char_p),
        ("subjCN", ctypes.c_char_p),
        ("subjOrg", ctypes.c_char_p),
        ("subjOrgUnit", ctypes.c_char_p),
        ("subjTitle", ctypes.c_char_p),
        ("subjState", ctypes.c_char_p),
        ("subjLocality", ctypes.c_char_p),
        ("subjFullName", ctypes.c_char_p),
        ("subjAddress", ctypes.c_char_p),
        ("subjPhone", ctypes.c_char_p),
        ("subjEMail", ctypes.c_char_p),
        ("subjDNS", ctypes.c_char_p),
        ("subjEDRPOUCode", ctypes.c_char_p),
        ("subjDRFOCode", ctypes.c_char_p),
    ]


class EU_KEY_MEDIA(ctypes.Structure):
    """Key media (file or hardware token) structure."""
    _fields_ = [
        ("sourceType", ctypes.c_uint),  # 1=file, 2=token
        ("showErrors", ctypes.c_int),
        ("devIndex", ctypes.c_uint),
        ("typeIndex", ctypes.c_uint),
        ("password", ctypes.c_char_p),
        ("path", ctypes.c_char_p),
    ]


class EUSign:
    """
    Wrapper for IIT EUSignCP library.

    Usage:
        with EUSign() as eu:
            eu.read_private_key('/path/to/key.dat', 'password')
            signed_data = eu.sign_data(data)
    """

    # Key media source types
    SOURCE_TYPE_UNKNOWN = 0
    SOURCE_TYPE_OPERATOR = 1
    SOURCE_TYPE_FILE = 2
    SOURCE_TYPE_PKCS11 = 3
    SOURCE_TYPE_HARDWARE = 4

    def __init__(self, lib_path=None, cert_path=None):
        self.lib_path = lib_path or IIT_LIB_PATH
        self.cert_path = cert_path or IIT_CERT_PATH
        self._lib = None
        self._initialized = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finalize()
        return False

    def _load_library(self):
        """Load the EUSignCP shared library."""
        if self._lib is not None:
            return

        lib_file = os.path.join(self.lib_path, 'euscp.so')
        if not os.path.exists(lib_file):
            raise EUSignError(0, f"Library not found: {lib_file}")

        # Set library search path
        os.environ['LD_LIBRARY_PATH'] = self.lib_path + ':' + os.environ.get('LD_LIBRARY_PATH', '')

        try:
            self._lib = ctypes.CDLL(lib_file)
            _logger.info("Loaded EUSignCP library from %s", lib_file)
        except OSError as e:
            raise EUSignError(0, f"Failed to load library: {e}")

        # Setup function signatures
        self._setup_functions()

    def _setup_functions(self):
        """Setup ctypes function signatures."""
        # EUSetUIMode
        self._lib.EUSetUIMode.argtypes = [ctypes.c_int]
        self._lib.EUSetUIMode.restype = None

        # EUInitialize
        self._lib.EUInitialize.argtypes = []
        self._lib.EUInitialize.restype = ctypes.c_uint

        # EUIsInitialized
        self._lib.EUIsInitialized.argtypes = []
        self._lib.EUIsInitialized.restype = ctypes.c_int

        # EUFinalize
        self._lib.EUFinalize.argtypes = []
        self._lib.EUFinalize.restype = None

        # EUGetErrorDesc
        self._lib.EUGetErrorDesc.argtypes = [ctypes.c_uint]
        self._lib.EUGetErrorDesc.restype = ctypes.c_char_p

        # EUReadPrivateKey
        self._lib.EUReadPrivateKey.argtypes = [
            ctypes.POINTER(EU_KEY_MEDIA),
            ctypes.POINTER(EU_CERT_OWNER_INFO)
        ]
        self._lib.EUReadPrivateKey.restype = ctypes.c_uint

        # EUIsPrivateKeyReaded
        self._lib.EUIsPrivateKeyReaded.argtypes = []
        self._lib.EUIsPrivateKeyReaded.restype = ctypes.c_int

        # EUResetPrivateKey
        self._lib.EUResetPrivateKey.argtypes = []
        self._lib.EUResetPrivateKey.restype = None

        # EUSignDataInternal
        self._lib.EUSignDataInternal.argtypes = [
            ctypes.c_int,  # bAppendCert
            ctypes.c_void_p,  # pbData
            ctypes.c_uint,  # dwDataLength
            ctypes.POINTER(ctypes.c_char_p),  # ppszSignedData
            ctypes.POINTER(ctypes.c_void_p),  # ppbSignedData
            ctypes.POINTER(ctypes.c_uint)  # pdwSignedDataLength
        ]
        self._lib.EUSignDataInternal.restype = ctypes.c_uint

        # EUFreeMemory
        self._lib.EUFreeMemory.argtypes = [ctypes.c_void_p]
        self._lib.EUFreeMemory.restype = None

        # EUSaveCertificate
        self._lib.EUSaveCertificate.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._lib.EUSaveCertificate.restype = ctypes.c_uint

        # EURefreshFileStore
        self._lib.EURefreshFileStore.argtypes = [ctypes.c_int]
        self._lib.EURefreshFileStore.restype = ctypes.c_uint

        # EUSetFileStoreSettings
        self._lib.EUSetFileStoreSettings.argtypes = [
            ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
        ]
        self._lib.EUSetFileStoreSettings.restype = ctypes.c_uint

        # EUEnvelopDataEx - envelope (encrypt) data for recipient
        self._lib.EUEnvelopDataEx.argtypes = [
            ctypes.c_void_p,  # pbRecipientCert
            ctypes.c_uint,    # dwRecipientCertLength
            ctypes.c_int,     # bSignData
            ctypes.c_void_p,  # pbData
            ctypes.c_uint,    # dwDataLength
            ctypes.POINTER(ctypes.c_char_p),   # ppszEnvelopedData
            ctypes.POINTER(ctypes.c_void_p),   # ppbEnvelopedData
            ctypes.POINTER(ctypes.c_uint)      # pdwEnvelopedDataLength
        ]
        self._lib.EUEnvelopDataEx.restype = ctypes.c_uint

        # EUReadPrivateKeyFile
        self._lib.EUReadPrivateKeyFile.argtypes = [
            ctypes.c_char_p,  # pszFileName
            ctypes.c_char_p,  # pszPassword
            ctypes.c_void_p   # ppCertOwnerInfo (can be NULL)
        ]
        self._lib.EUReadPrivateKeyFile.restype = ctypes.c_uint

        # EURawEnvelopData - raw envelope (encrypt) data for recipient
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

    def _check_error(self, error_code, operation="Operation"):
        """Check error code and raise exception if needed."""
        if error_code != 0:
            error_desc = self._lib.EUGetErrorDesc(error_code)
            if error_desc:
                error_desc = error_desc.decode('utf-8', errors='replace')
            raise EUSignError(error_code, f"{operation} failed: {error_desc}")

    def initialize(self):
        """Initialize the EUSign library."""
        if self._initialized:
            return

        self._load_library()

        # Disable UI mode (for server usage)
        self._lib.EUSetUIMode(0)

        # Initialize
        error = self._lib.EUInitialize()
        self._check_error(error, "Initialize")

        self._initialized = True
        _logger.info("EUSignCP library initialized")

    def finalize(self):
        """Finalize the EUSign library."""
        if not self._initialized:
            return

        self._lib.EUResetPrivateKey()
        self._lib.EUFinalize()
        self._initialized = False
        _logger.info("EUSignCP library finalized")

    def read_private_key(self, key_path, password):
        """
        Read private key from file.

        Args:
            key_path: Path to the key file (.dat, .jks, .pfx, etc.)
            password: Password for the key file

        Returns:
            EU_CERT_OWNER_INFO structure with certificate info
        """
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")

        # Prepare key media structure
        key_media = EU_KEY_MEDIA()
        key_media.sourceType = self.SOURCE_TYPE_FILE
        key_media.showErrors = 0
        key_media.devIndex = 0
        key_media.typeIndex = 0
        key_media.password = password.encode('utf-8')
        key_media.path = key_path.encode('utf-8')

        # Prepare certificate owner info
        cert_owner = EU_CERT_OWNER_INFO()

        # Read the key
        error = self._lib.EUReadPrivateKey(
            ctypes.byref(key_media),
            ctypes.byref(cert_owner)
        )
        self._check_error(error, "Read private key")

        _logger.info("Private key loaded successfully")
        return cert_owner

    def is_private_key_loaded(self):
        """Check if private key is loaded."""
        if not self._initialized:
            return False
        return bool(self._lib.EUIsPrivateKeyReaded())

    def sign_data(self, data, append_cert=True):
        """
        Sign data with loaded private key.

        Args:
            data: Data to sign (bytes)
            append_cert: Whether to append certificate to signature

        Returns:
            Signed data as base64 string
        """
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")

        if not self.is_private_key_loaded():
            raise EUSignError(0, "Private key not loaded")

        if isinstance(data, str):
            data = data.encode('utf-8')

        # Prepare output pointers
        signed_data_str = ctypes.c_char_p()
        signed_data_bin = ctypes.c_void_p()
        signed_data_len = ctypes.c_uint()

        # Sign the data
        error = self._lib.EUSignDataInternal(
            1 if append_cert else 0,
            data,
            len(data),
            ctypes.byref(signed_data_str),
            ctypes.byref(signed_data_bin),
            ctypes.byref(signed_data_len)
        )
        self._check_error(error, "Sign data")

        # Get the result
        if signed_data_str.value:
            result = signed_data_str.value.decode('utf-8')
            self._lib.EUFreeMemory(signed_data_str)
        else:
            # Binary result
            result = ctypes.string_at(signed_data_bin, signed_data_len.value)
            self._lib.EUFreeMemory(signed_data_bin)
            import base64
            result = base64.b64encode(result).decode('utf-8')

        return result

    def load_certificate(self, cert_data):
        """
        Load a certificate into the file store.

        Args:
            cert_data: Certificate data (bytes)
        """
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")

        error = self._lib.EUSaveCertificate(cert_data, len(cert_data))
        if error != 0:
            _logger.warning("Failed to save certificate: error %s", error)

    def load_certificate_file(self, cert_path):
        """
        Load a certificate from file into the file store.

        Args:
            cert_path: Path to the certificate file
        """
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
        self.load_certificate(cert_data)

    def refresh_file_store(self):
        """Refresh the certificate file store."""
        if not self._initialized:
            return
        self._lib.EURefreshFileStore(1)

    def set_file_store_path(self, path):
        """Set the certificate file store path."""
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")
        error = self._lib.EUSetFileStoreSettings(
            path.encode('utf-8'), 0, 0, 0, 1, 0, 1, 3600
        )
        if error != 0:
            _logger.warning("Failed to set file store path: error %s", error)

    def read_private_key_file(self, key_path, password):
        """
        Read private key from file (simpler API).

        Args:
            key_path: Path to the key file
            password: Password for the key file
        """
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")

        error = self._lib.EUReadPrivateKeyFile(
            key_path.encode('utf-8'),
            password.encode('utf-8'),
            None
        )
        self._check_error(error, "Read private key file")
        _logger.info("Private key loaded from file")

    def envelope_data(self, recipient_cert, data):
        """
        Envelope (encrypt) data for a recipient using raw envelope.

        Args:
            recipient_cert: Recipient's certificate data (bytes)
            data: Data to envelope (bytes or string)

        Returns:
            Enveloped data as base64 string
        """
        if not self._initialized:
            raise EUSignError(0, "Library not initialized")

        if isinstance(data, str):
            data = data.encode('utf-8')

        # Prepare output pointers
        env_data_str = ctypes.c_char_p()
        env_data_bin = ctypes.c_void_p()
        env_data_len = ctypes.c_uint()

        # Envelope the data using EURawEnvelopData
        error = self._lib.EURawEnvelopData(
            recipient_cert,
            len(recipient_cert),
            data,
            len(data),
            ctypes.byref(env_data_str),
            ctypes.byref(env_data_bin),
            ctypes.byref(env_data_len)
        )
        self._check_error(error, "Envelope data")

        # Get the result
        if env_data_str.value:
            result = env_data_str.value.decode('utf-8')
            self._lib.EUFreeMemory(env_data_str)
        else:
            # Binary result - convert to base64
            result = ctypes.string_at(env_data_bin, env_data_len.value)
            self._lib.EUFreeMemory(env_data_bin)
            import base64
            result = base64.b64encode(result).decode('utf-8')

        return result

    def sign_and_envelope(self, data, recipient_cert):
        """
        Sign data and then envelope (encrypt) for recipient.

        Args:
            data: Data to sign and envelope
            recipient_cert: Recipient's certificate data (bytes)

        Returns:
            Signed and enveloped data as base64 string
        """
        # First sign the data
        signed_data = self.sign_data(data)

        # Then envelope it for the recipient
        return self.envelope_data(recipient_cert, signed_data, sign_data=False)


def sign_data_with_key(key_path, password, data, lib_path=None, cert_path=None):
    """
    Convenience function to sign data with a key file.

    Args:
        key_path: Path to the key file
        password: Password for the key
        data: Data to sign
        lib_path: Optional path to IIT library
        cert_path: Optional path to certificates

    Returns:
        Signed data as base64 string
    """
    with EUSign(lib_path=lib_path, cert_path=cert_path) as eu:
        eu.read_private_key(key_path, password)
        return eu.sign_data(data)
