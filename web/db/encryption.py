"""Fernet encryption helpers for sensitive fields (OAuth tokens)."""

from cryptography.fernet import Fernet

from web.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.fernet_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the ciphertext as a UTF-8 string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string back to plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
