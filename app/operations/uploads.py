"""Photo / document uploads for operational records (legacy: save_upload / save_upload_validated).

Policy ported from the legacy officer register: .pdf .jpg .jpeg .png, 5 MB.  New: the file's leading bytes
must match its extension (a renamed .exe is refused), the stored name is server-generated (no path
traversal, no overwrite), and every file records who uploaded it.  A record may only reference the
uploader's own files, and a file may be opened only by someone who may view a record that references it.
"""
import os
import secrets
from typing import Tuple

from ..db import Actor
from ..identity.errors import NotFound, PermissionDenied, ValidationError
from .common import new_cursor

ALLOWED = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.pdf': 'application/pdf'}
MAGIC = {'.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff',), '.png': (b'\x89PNG\r\n\x1a\n',), '.pdf': (b'%PDF-',)}
MAX_BYTES = 5 * 1024 * 1024
NAME_RE = r'^[0-9a-f]{32}\.(jpg|jpeg|png|pdf)$'


def upload_dir() -> str:
    d = os.environ.get('SENTINEL_UPLOAD_DIR') or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'uploads')
    os.makedirs(d, exist_ok=True)
    return d


def store(conn, actor: Actor, filename: str, data: bytes, unit_code: str = None) -> dict:
    cur = new_cursor(conn, actor)
    cur.execute("SELECT authz_has(%(u)s,'person:create') OR authz_has(%(u)s,'checkpoint:create') "
                "OR authz_has(%(u)s,'incident:create') OR authz_has(%(u)s,'airport:create') "
                "OR authz_has(%(u)s,'clearance:create') OR authz_has(%(u)s,'case:update') "
                "OR authz_has(%(u)s,'officer:create') OR authz_has(%(u)s,'conduct:submit') AS ok", {'u': actor.user_id})
    if not cur.fetchone()['ok']:
        raise PermissionDenied('You are not allowed to upload files')
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in ALLOWED:
        raise ValidationError('Only PDF, JPG or PNG files are accepted', fields=['file'])
    if not data:
        raise ValidationError('The file is empty', fields=['file'])
    if len(data) > MAX_BYTES:
        raise ValidationError('The file is larger than 5 MB', fields=['file'])
    if not any(data.startswith(m) for m in MAGIC[ext]):
        raise ValidationError(f'The file content is not a valid {ext[1:].upper()}', fields=['file'])
    name = secrets.token_hex(16) + ('.jpg' if ext == '.jpeg' else ext)
    cur.execute('INSERT INTO uploads (name, original_name, content_type, size_bytes, uploaded_by, unit_id) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (name, os.path.basename(filename)[:200], ALLOWED[ext], len(data), actor.user_id, actor.unit_id))
    with open(os.path.join(upload_dir(), name), 'wb') as f:
        f.write(data)
    return {'name': name, 'content_type': ALLOWED[ext], 'size': len(data)}


def open_file(conn, actor: Actor, name: str) -> Tuple[bytes, str]:
    import re
    cur = new_cursor(conn, actor)
    if not re.match(NAME_RE, name or ''):
        raise NotFound('File not found')
    cur.execute('SELECT content_type FROM uploads WHERE name = %s', (name,))
    row = cur.fetchone()
    cur.execute('SELECT can_view_upload(%s, %s) AS ok', (actor.user_id, name))
    if not row or not cur.fetchone()['ok']:
        raise NotFound('File not found')              # 404, not 403: do not confirm that it exists
    with open(os.path.join(upload_dir(), name), 'rb') as f:
        return f.read(), row['content_type']
