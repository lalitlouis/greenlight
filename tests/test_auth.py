"""Session cookie integrity. OAuth itself needs Google; the cookie must not."""

import importlib

import greenlight.auth as auth_module


def _fresh(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-1234")
    importlib.reload(auth_module)
    return auth_module


def test_session_roundtrip(monkeypatch):
    auth = _fresh(monkeypatch)
    cookie = auth.make_session({"sub": "u1", "email": "a@b.c", "name": "A"})
    user = auth.read_session(cookie)
    assert user["sub"] == "u1" and user["email"] == "a@b.c"


def test_tampered_session_rejected(monkeypatch):
    auth = _fresh(monkeypatch)
    cookie = auth.make_session({"sub": "u1", "email": "a@b.c", "name": "A"})
    payload, sig = cookie.rsplit(".", 1)
    assert auth.read_session(payload + "x." + sig) is None
    assert auth.read_session(payload + "." + "0" * len(sig)) is None
    assert auth.read_session(None) is None


def test_state_roundtrip_and_garbage(monkeypatch):
    auth = _fresh(monkeypatch)
    nonce = auth.new_nonce()
    assert auth.check_state(auth.make_state(nonce), nonce)
    assert not auth.check_state("garbage", nonce)
    assert not auth.check_state(None, nonce)


def test_state_is_bound_to_one_browser(monkeypatch):
    """Login CSRF: a validly-signed, unexpired state minted for the ATTACKER's
    browser must not authorize a callback in the VICTIM's browser. Without the
    nonce leg the victim gets silently signed into the attacker's account and
    everything they upload lands under the attacker's sub."""
    auth = _fresh(monkeypatch)
    attacker_state = auth.make_state(auth.new_nonce())  # attacker's own login
    victim_nonce = auth.new_nonce()  # victim's browser, different value
    assert not auth.check_state(attacker_state, victim_nonce)
    # a victim with no login in flight has no cookie at all
    assert not auth.check_state(attacker_state, "")
    assert not auth.check_state(attacker_state, None)
    # and a state with no nonce in it (pre-fix shape) never validates
    import base64
    import json

    legacy = base64.urlsafe_b64encode(json.dumps({"ts": 9999999999}).encode())
    assert not auth.check_state(legacy.decode() + "." + auth._sign(legacy), "anything")


def test_unconfigured_status(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    importlib.reload(auth_module)
    assert not auth_module.configured()


def test_admin_allowlist(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com, second@example.com")
    import importlib

    importlib.reload(auth_module)
    assert auth_module.is_admin({"email": "Boss@Example.com"})
    assert not auth_module.is_admin({"email": "rando@example.com"})
    assert not auth_module.is_admin(None)
