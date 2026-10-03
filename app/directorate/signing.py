"""Clearance-certificate signing (Ed25519).

* The PRIVATE key never enters the database or the repository.  It lives in the environment of the
  service that runs for the national Fingerprint directorate:
      SENTINEL_SIGNING_KEY      base64 of the 32-byte Ed25519 seed        (python -m app.directorate.signing generate)
      SENTINEL_SIGNING_KEY_ID   e.g. 'fp-2026-1'
* The PUBLIC key is registered once, by the database owner, in `signing_keys`
  (python -m app.directorate.signing register) — app roles cannot write that table, so nobody can swap in a key.
* Verification needs only the public key and is open to anyone (GET /api/verify/<certificate number>).
* Fail closed: with no key configured an approval is REFUSED (503), never signed with a placeholder.
  Development (SENTINEL_DEV_AUTH=1) derives a fixed, publicly-known key named 'dev-1' — NEVER for production.
"""
import base64
import hashlib
import json
import os
import sys
from typing import Dict, Optional, Tuple

from ..identity.errors import IdentityError

try:                                                      # one third-party dependency: `pip install cryptography`
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except ImportError:                                       # pragma: no cover
    Ed25519PrivateKey = None

DEV_KEY_ID = 'dev-1'


class SigningUnavailable(IdentityError):
    status, code = 503, 'signing_unavailable'


def canonical(payload: Dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str).encode('utf-8')


def _seed() -> Tuple[bytes, str]:
    raw = os.environ.get('SENTINEL_SIGNING_KEY', '').strip()
    if raw:
        seed = base64.b64decode(raw)
        if len(seed) != 32:
            raise SigningUnavailable('SENTINEL_SIGNING_KEY must be the base64 of a 32-byte Ed25519 seed')
        return seed, os.environ.get('SENTINEL_SIGNING_KEY_ID', '').strip() or 'key-1'
    if os.environ.get('SENTINEL_DEV_AUTH') == '1':
        return hashlib.sha256(b'sentinel-dev-signing-key / NOT FOR PRODUCTION').digest(), DEV_KEY_ID
    raise SigningUnavailable('No signing key is configured on this server, so certificates cannot be issued. '
                             'Set SENTINEL_SIGNING_KEY (see app/directorate/signing.py).')


def _private() -> Tuple['Ed25519PrivateKey', str]:
    if Ed25519PrivateKey is None:
        raise SigningUnavailable('The `cryptography` package is not installed, so certificates cannot be signed')
    seed, key_id = _seed()
    return Ed25519PrivateKey.from_private_bytes(seed), key_id


def public_b64(priv) -> str:
    return base64.b64encode(priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def active_key(cur) -> Tuple['Ed25519PrivateKey', str]:
    """The configured private key, proven to match the PUBLIC key registered for its id."""
    priv, key_id = _private()
    cur.execute('SELECT public_key, status FROM signing_keys WHERE key_id = %s', (key_id,))
    row = cur.fetchone()
    if not row or row['status'] != 'active' or row['public_key'] != public_b64(priv):
        raise SigningUnavailable(f'Signing key "{key_id}" is not registered as an active key in the database '
                                 '(run: python -m app.directorate.signing register)')
    return priv, key_id


def sign(priv, payload: Dict) -> str:
    return base64.b64encode(priv.sign(canonical(payload))).decode()


def verify(payload: Dict, signature_b64: str, public_key_b64: str) -> bool:
    if Ed25519PrivateKey is None:                          # pragma: no cover
        raise SigningUnavailable('The `cryptography` package is not installed')
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)).verify(
            base64.b64decode(signature_b64), canonical(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


def register_public_key(conn) -> str:
    """Owner-level operation: record the PUBLIC half of the configured key.  Idempotent."""
    priv, key_id = _private()
    pub = public_b64(priv)
    cur = conn.cursor()
    cur.execute('SELECT public_key FROM signing_keys WHERE key_id = %s', (key_id,))
    row = cur.fetchone()
    if row and row[0] != pub:
        raise RuntimeError(f'key id {key_id} is already registered with a DIFFERENT public key; use a new id')
    if not row:
        cur.execute("INSERT INTO signing_keys (key_id, algorithm, public_key) VALUES (%s, 'ed25519', %s)", (key_id, pub))
    conn.commit()
    return key_id


def register_dev_key(conn) -> str:
    """DEV / TEST ONLY: register the publicly-known development key ('dev-1'), whatever the environment says."""
    seed = hashlib.sha256(b'sentinel-dev-signing-key / NOT FOR PRODUCTION').digest()
    pub = public_b64(Ed25519PrivateKey.from_private_bytes(seed))
    cur = conn.cursor()
    cur.execute("INSERT INTO signing_keys (key_id, algorithm, public_key) VALUES (%s, 'ed25519', %s) ON CONFLICT DO NOTHING",
                (DEV_KEY_ID, pub))
    return DEV_KEY_ID


def main(argv=None):                                       # pragma: no cover
    argv = argv or sys.argv[1:]
    if argv[:1] == ['generate']:
        seed = base64.b64encode(os.urandom(32)).decode()
        print(f'SENTINEL_SIGNING_KEY={seed}\nSENTINEL_SIGNING_KEY_ID=fp-{__import__("datetime").date.today().year}-1')
        print('# Keep the seed secret (secret manager / env of the signing service). Then run: python -m app.directorate.signing register')
    elif argv[:1] == ['register']:
        from ..db import connect
        conn = connect()
        print('registered public key', register_public_key(conn))
    else:
        print('usage: python -m app.directorate.signing generate | register')


if __name__ == '__main__':
    main()
