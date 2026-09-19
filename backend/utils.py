"""Sentinel shared utilities.

Small, dependency-free helpers moved verbatim out of
``backend/server.py``: password hashing, row conversion, HTTP body parsing
(JSON + multipart), upload handling, name/choice normalisation, timestamp
helpers and per-entity ID generators.

Standard library only. Imports :mod:`config` for paths/constants.
"""
import datetime, hashlib, json, os, re, secrets, time
from config import *


def utc_now_stamp():
    """UTC 'YYYY-MM-DD HH:MM:SS' — the same shape as SQLite CURRENT_TIMESTAMP."""
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def parse_stamp(value):
    """Parse a SQLite / ISO-8601 timestamp into a POSIX timestamp, or None."""
    dt = parse_created_at(value)
    return dt.timestamp() if dt else None


def parse_created_at(value):
    """Parse a stored `created_at` into a timezone-aware UTC datetime.

    Accepts the SQLite shape ('YYYY-MM-DD HH:MM:SS' — stored in UTC), ISO-8601
    with or without a 'Z'/'offset' suffix, and date-only values. A naive value
    is assumed to be UTC. Returns None when nothing can be parsed.
    """
    s = (value or '').strip()
    if not s:
        return None
    candidate = s.replace('Z', '+00:00')
    dt = None
    try:
        dt = datetime.datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.datetime.strptime(s.split('.', 1)[0], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


# ---- migration --------------------------------------------------------------
def norm(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip().lower()

def split_parts(full_name):
    """Return up to four normalized name parts from a stored full name."""
    parts = re.split(r'\s+', norm(full_name))
    parts = [p for p in parts if p]
    return (parts + ['', '', '', ''])[:4]

def raw_parts(full_name):
    """Return up to four raw (case-preserving) name parts."""
    parts = [p for p in re.split(r'\s+', str(full_name or '').strip()) if p]
    return (parts + ['', '', '', ''])[:4]

def parts_from_fields(data):
    return [str(data.get(k) or '').strip() for k in NAME_PART_FIELDS]

def build_full_name(data):
    parts = parts_from_fields(data)
    if any(parts):
        return ' '.join(p for p in parts if p)
    return str(data.get('full_name') or '').strip()


# ---- helpers ----------------------------------------------------------------
def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()
def rowdict(row): return dict(row) if row else None

def body_json(handler):
    try: return json.loads(handler.rfile.read(int(handler.headers.get('Content-Length','0')) or 0) or b'{}')
    except Exception: raise ValueError('Request body must be valid JSON')

def parse_multipart(handler):
    ctype = handler.headers.get('Content-Type','')
    m = re.search(r'boundary=([^;]+)', ctype)
    if not m: raise ValueError('multipart/form-data required')
    boundary = m.group(1).strip().strip('"')
    length = int(handler.headers.get('Content-Length','0') or 0)
    raw = handler.rfile.read(length)
    delim = b'--' + boundary.encode()
    fields, files = {}, {}
    for part in raw.split(delim):
        part = part.strip(b'\r\n')
        if not part or part == b'--' or b'\r\n\r\n' not in part:
            continue
        header_blob, content = part.split(b'\r\n\r\n', 1)
        headers = header_blob.decode('utf-8','replace')
        nm = re.search(r'name="([^"]*)"', headers)
        fn = re.search(r'filename="([^"]*)"', headers)
        if not nm: continue
        if content.endswith(b'\r\n'): content = content[:-2]
        if fn and fn.group(1):
            files[nm.group(1)] = {'filename': fn.group(1), 'content': content}
        else:
            fields[nm.group(1)] = content.decode('utf-8','replace')
    return fields, files

def save_upload(f):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(f['filename'])) or 'file'
    ext = os.path.splitext(base)[1].lower()
    stored = 'f_' + secrets.token_hex(8) + ext
    with open(os.path.join(UPLOAD_DIR, stored), 'wb') as out:
        out.write(f['content'])
    return {'path': '/uploads/' + stored, 'name': base}


def new_person_id(c):
    while True:
        pid = 'P-' + str(int(time.time()*1000))[-8:]
        if not c.execute('SELECT 1 FROM persons WHERE person_id=?',(pid,)).fetchone():
            return pid

# ---- officer registration helpers -------------------------------------------

def normalise_choice(value, options):
    """Case-insensitive match against a fixed option list; returns the
    canonical option spelling or None. Empty input returns None."""
    v = str(value or '').strip()
    if not v:
        return None
    for o in options:
        if v.lower() == o.lower():
            return o
    return None


def new_station_id(c):
    """Auto-generated station identifier (ST-001, ST-002, …)."""
    row = c.execute('SELECT station_id FROM police_stations ORDER BY id DESC LIMIT 1').fetchone()
    n = 1
    if row:
        try:
            n = int(str(row['station_id']).rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            n = c.execute('SELECT COUNT(*) FROM police_stations').fetchone()[0] + 1
    return 'ST-' + str(n).zfill(3)


def new_service_id(c):
    """Auto-generated officer Service ID in the POL-YYYY-XXXX format."""
    year = datetime.date.today().year
    prefix = f'POL-{year}-'
    row = c.execute('SELECT service_id FROM officers WHERE service_id LIKE ? '
                    'ORDER BY service_id DESC LIMIT 1', (prefix + '%',)).fetchone()
    n = 1
    if row:
        try:
            n = int(str(row['service_id']).rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            n = 1
    return f'{prefix}{n:04d}'


def file_ext(name):
    return os.path.splitext(str(name or ''))[1].lower()


def save_upload_validated(f, allowed_exts, label, required=False):
    """Validate and persist an uploaded file.

    Enforces the allowed extensions and the 5 MB size cap before writing the
    file to disk (returning the same {path, name} dict as save_upload).
    `required` makes a missing file a hard validation error (e.g. the
    mandatory officer photo and Document Slot 1)."""
    if not f:
        if required:
            raise ValueError(f'{label} is required')
        return None
    ext = file_ext(f['filename'])
    if allowed_exts and ext not in allowed_exts:
        raise ValueError(f'{label} must be one of {", ".join(sorted(allowed_exts))} '
                         f'(got {ext or "no extension"})')
    if len(f['content']) > OFFICER_MAX_UPLOAD_BYTES:
        raise ValueError(f'{label} exceeds the '
                         f'{OFFICER_MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit')
    return save_upload(f)


def new_station_code(c, region):
    prefix = f"STN-{REGION_CODES[region]}-"
    n = 1
    for row in c.execute('SELECT code FROM police_stations WHERE code LIKE ?', (prefix + '%',)):
        try:
            n = max(n, int(str(row['code']).rsplit('-', 1)[1]) + 1)
        except (ValueError, IndexError):
            pass
    return f'{prefix}{n:03d}'


def new_crime_file_number(c, station_code):
    year = datetime.datetime.now(datetime.timezone.utc).year
    token = re.sub(r'[^A-Za-z0-9-]', '', station_code or 'STN')
    prefix = f'CRM-{year}-{token}-'
    n = 1
    for row in c.execute('SELECT file_number FROM crime_incidents WHERE file_number LIKE ?', (prefix + '%',)):
        try:
            n = max(n, int(str(row['file_number']).rsplit('-', 1)[1]) + 1)
        except (ValueError, IndexError):
            pass
    return f'{prefix}{n:04d}'


# ---- officer conduct, promotions & disciplinary management ------------------
# Police Officer Registration Office (HR Directorate) module. Station
# commanders submit promotion recommendations / misconduct reports
# (POST /api/conduct/submit, default status 'Submitted to HR'); HR staff
# review, verify and approve or reject them (POST /api/conduct/<id>/review).
# Approving a Rank Advancement / Rank Demotion automatically updates
# officers.rank and writes an immutable officer_service_history row.

def new_conduct_action_id(c):
    """Auto-generated conduct action file identifier (ACT-YYYY-XXXX)."""
    year = datetime.datetime.now(datetime.timezone.utc).year
    prefix = f'ACT-{year}-'
    row = c.execute('SELECT action_id FROM officer_conduct_actions WHERE action_id LIKE ? '
                    'ORDER BY action_id DESC LIMIT 1', (prefix + '%',)).fetchone()
    n = 1
    if row:
        try:
            n = int(str(row['action_id']).rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            n = 1
    return f'{prefix}{n:04d}'


# ---- 5) Police Officers Registration Office (HR Directorate) ---------------
def new_promotion_id(c):
    year = datetime.datetime.now(datetime.timezone.utc).year
    prefix = f'PRM-{year}-'
    n = 1
    for row in c.execute('SELECT nomination_id FROM officer_promotions WHERE nomination_id LIKE ?',
                         (prefix + '%',)):
        try:
            n = max(n, int(str(row['nomination_id']).rsplit('-', 1)[1]) + 1)
        except (ValueError, IndexError):
            pass
    return f'{prefix}{n:04d}'


def new_discipline_id(c):
    year = datetime.datetime.now(datetime.timezone.utc).year
    prefix = f'DSC-{year}-'
    n = 1
    for row in c.execute('SELECT action_id FROM officer_discipline WHERE action_id LIKE ?',
                         (prefix + '%',)):
        try:
            n = max(n, int(str(row['action_id']).rsplit('-', 1)[1]) + 1)
        except (ValueError, IndexError):
            pass
    return f'{prefix}{n:04d}'
