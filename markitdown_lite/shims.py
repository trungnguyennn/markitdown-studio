"""Tiny stand-ins for heavy modules that markitdown imports but the Lite edition
does not need. They must be installed BEFORE `import markitdown`.

* magika   (+ onnxruntime + numpy, ~70 MB) - AI file-type sniffing. markitdown
  only uses it to refine the guess made from the file extension; the stand-in
  reports "no opinion" so markitdown keeps the extension-based guess.
* requests (+ urllib3, certifi, OpenSSL, ~10 MB) - only used for converting
  URLs. The Lite edition converts local files only, so it never goes online.
* cryptography (~20 MB) - pdfminer uses it only to decrypt AES-encrypted PDFs.
  Such PDFs fail with a clear message; everything else works.

Each stand-in is used only if the real package is not installed, so running
the Lite UI inside the Full edition's environment still uses the real ones.
"""

from __future__ import annotations

import importlib.util
import sys
import types


def _missing(name: str) -> bool:
    return name not in sys.modules and importlib.util.find_spec(name) is None


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    mod.__lite_shim__ = True
    sys.modules[name] = mod
    return mod


# --------------------------------------------------------------------- magika
class _NoPrediction:
    status = "lite_disabled"  # anything but "ok" -> markitdown keeps its own guess
    prediction = None


class _Magika:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def identify_stream(self, stream):
        return _NoPrediction()

    identify_bytes = identify_stream
    identify_path = identify_stream


# ------------------------------------------------------------------- requests
class _NetworkDisabled(RuntimeError):
    pass


def _offline(*args, **kwargs):
    raise _NetworkDisabled("Network access is not available in MarkItDown Studio Lite.")


class _Response:  # only used in isinstance() checks
    pass


class _Session:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    get = post = head = request = staticmethod(_offline)

    def close(self) -> None:
        pass


# --------------------------------------------------------------- cryptography
class _CryptoUnavailable(RuntimeError):
    pass


def _no_crypto(*args, **kwargs):
    raise _CryptoUnavailable(
        "This PDF uses AES encryption, which MarkItDown Studio Lite cannot decrypt. "
        "Use the full edition for encrypted PDFs."
    )


def install() -> list[str]:
    """Install whichever stand-ins are needed. Returns the names installed."""
    installed: list[str] = []

    if _missing("magika"):
        _module("magika", Magika=_Magika)
        installed.append("magika")

    if _missing("requests"):
        exceptions = _module(
            "requests.exceptions",
            RequestException=_NetworkDisabled,
            HTTPError=_NetworkDisabled,
            ConnectionError=_NetworkDisabled,
        )
        _module(
            "requests",
            Session=_Session,
            Response=_Response,
            get=_offline,
            post=_offline,
            head=_offline,
            request=_offline,
            exceptions=exceptions,
            RequestException=_NetworkDisabled,
        )
        installed.append("requests")

    if _missing("cryptography"):
        root = _module("cryptography")
        hazmat = _module("cryptography.hazmat")
        backends = _module("cryptography.hazmat.backends", default_backend=_no_crypto)
        primitives = _module("cryptography.hazmat.primitives")
        ciphers = _module(
            "cryptography.hazmat.primitives.ciphers",
            Cipher=_no_crypto,
            algorithms=types.SimpleNamespace(AES=_no_crypto, ARC4=_no_crypto),
            modes=types.SimpleNamespace(CBC=_no_crypto, ECB=_no_crypto),
        )
        root.hazmat, hazmat.backends, hazmat.primitives, primitives.ciphers = (
            hazmat,
            backends,
            primitives,
            ciphers,
        )
        installed.append("cryptography")

    return installed
