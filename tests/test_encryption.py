"""Application-layer encryption of stored screenplays and records."""

import importlib

from cryptography.fernet import Fernet


def _storage(monkeypatch, key):
    if key:
        monkeypatch.setenv("ENCRYPTION_KEY", key)
    else:
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    import greenlight.storage as s

    importlib.reload(s)
    return s


def test_seal_roundtrip_and_ciphertext(monkeypatch):
    key = Fernet.generate_key().decode()
    s = _storage(monkeypatch, key)
    secret = b"INT. UNPUBLISHED MASTERPIECE - NIGHT"
    sealed = s._seal(secret)
    assert sealed != secret and secret not in sealed  # actually ciphertext
    assert s._unseal(sealed) == secret


def test_legacy_plaintext_still_loads(monkeypatch):
    key = Fernet.generate_key().decode()
    s = _storage(monkeypatch, key)
    assert s._unseal(b'{"legacy": true}') == b'{"legacy": true}'


def test_no_key_degrades_to_plaintext(monkeypatch):
    s = _storage(monkeypatch, None)
    assert s._seal(b"x") == b"x"
    assert s._unseal(b"x") == b"x"
