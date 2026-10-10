"""Store the LLM API key in the operating system's credential vault.

Windows Credential Manager, macOS Keychain or the Secret Service on Linux,
via the ``keyring`` package. The key is never written to settings.json. If no
secure backend is available, the key is kept in memory for the current session
only, rather than falling back to plain text on disk.
"""

from __future__ import annotations

import logging

from . import __app_name__

log = logging.getLogger(__name__)

SERVICE = __app_name__
ACCOUNT = "llm_api_key"

_session_fallback: str = ""


def _keyring():
    try:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001 - any import/backend problem means "unavailable"
        return None


def is_secure_storage_available() -> bool:
    return _keyring() is not None


def get_api_key() -> str:
    kr = _keyring()
    if kr is None:
        return _session_fallback
    try:
        return kr.get_password(SERVICE, ACCOUNT) or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read the API key from the credential store: %s", type(exc).__name__)
        return _session_fallback


def set_api_key(value: str) -> bool:
    """Save (or clear, when blank) the API key. Returns True if stored securely."""
    global _session_fallback
    value = value.strip()
    kr = _keyring()
    if kr is None:
        _session_fallback = value
        log.warning("No secure credential store available; the API key is kept for this session only.")
        return False
    try:
        if value:
            kr.set_password(SERVICE, ACCOUNT, value)
        else:
            from keyring.errors import PasswordDeleteError

            try:
                kr.delete_password(SERVICE, ACCOUNT)
            except PasswordDeleteError:
                log.debug("No stored API key to delete.")
        return True
    except Exception as exc:  # noqa: BLE001
        _session_fallback = value
        log.warning("Could not save the API key securely (%s); kept for this session only.", type(exc).__name__)
        return False
