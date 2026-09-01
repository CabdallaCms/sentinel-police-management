#!/usr/bin/env python3
"""Sentinel backend.
Development-only API using the Python standard library + SQLite.
Supports central persons (with an optional linked case, universal identity
resolution and auto-create/merge), airport records, fingerprint clearance
applications (with file attachments), CID crime cases (participants +
evidence) and checkpoint screening events.

Identity matching tiers (used by /api/persons/resolve and every unit route):
  Tier 1 — exact National ID or Passport match            (auto merge / link)
  Tier 2 — exact 4-part name + date of birth match        (high-confidence link)
  Tier 3 — 3-part name + mother's name match              (fuzzy warning only)

Replace SQLite and demo authentication before any operational deployment.
"""
import hashlib, json, os, re, secrets, sqlite3, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DB_PATH = os.environ.get('SENTINEL_DB', os.path.join(ROOT, 'sentinel.db'))
UPLOAD_DIR = os.environ.get('SENTINEL_UPLOADS', os.path.join(ROOT, 'uploads'))
TOKENS = {}

def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=8000')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

# ---- schema -----------------------------------------------------------------
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL, role TEXT NOT NULL,
  branch TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS persons(
  id INTEGER PRIMARY KEY, person_id TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL, first_name TEXT, second_name TEXT, third_name TEXT, fourth_name TEXT,
  national_id TEXT UNIQUE, date_of_birth TEXT, phone TEXT,
  mother_name TEXT, place_of_birth TEXT, residence TEXT,
  occupation TEXT, passport_id TEXT, photo_path TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS airport_passengers(
  id INTEGER PRIMARY KEY, record_id TEXT UNIQUE NOT NULL,
  person_id INTEGER NOT NULL REFERENCES persons(id), movement TEXT NOT NULL,
  travel_date TEXT NOT NULL, flight_number TEXT NOT NULL,
  route TEXT NOT NULL, notes TEXT, created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS clearance_applications(
  id INTEGER PRIMARY KEY, application_id TEXT UNIQUE NOT NULL,
  person_id INTEGER NOT NULL REFERENCES persons(id), purpose TEXT NOT NULL,
  guardian_name TEXT, guardian_relationship TEXT, guardian_id TEXT,
  guardian_occupation TEXT, guardian_address TEXT, guardian_phone TEXT,
  legal_document_ref TEXT, notes TEXT,
  applicant_docs TEXT, guardian_docs TEXT, applicant_photo TEXT,
  status TEXT NOT NULL DEFAULT 'Pending Review',
  certificate_number TEXT, created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS crime_cases(
  id INTEGER PRIMARY KEY, case_id TEXT UNIQUE NOT NULL,
  category TEXT NOT NULL, location TEXT, status TEXT NOT NULL DEFAULT 'Reported',
  incident_summary TEXT, notes TEXT, created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS suspect_alerts(
  id INTEGER PRIMARY KEY, alert_id TEXT UNIQUE NOT NULL,
  person_id INTEGER NOT NULL REFERENCES persons(id),
  case_id INTEGER REFERENCES crime_cases(id),
  role TEXT NOT NULL DEFAULT 'Suspect',
  alert_status TEXT NOT NULL DEFAULT 'Active alert',
  origin TEXT NOT NULL DEFAULT 'Direct Intelligence Listing',
  notes TEXT, created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS case_evidence(
  id INTEGER PRIMARY KEY, evidence_id TEXT UNIQUE NOT NULL,
  case_id INTEGER NOT NULL REFERENCES crime_cases(id),
  caption TEXT, file_path TEXT, file_name TEXT, file_type TEXT,
  uploaded_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS checkpoint_events(
  id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
  person_id INTEGER NOT NULL REFERENCES persons(id),
  location TEXT NOT NULL, screening_result TEXT NOT NULL,
  action_taken TEXT NOT NULL DEFAULT 'Cleared', notes TEXT,
  purpose_of_visit TEXT, current_address TEXT, permanent_address TEXT,
  traveler_photo TEXT, traveler_docs TEXT,
  guardian_person_id INTEGER REFERENCES persons(id),
  guardian_name TEXT, guardian_relationship TEXT, guardian_phone TEXT,
  guardian_address TEXT, guardian_occupation TEXT,
  guardian_national_id TEXT, guardian_passport_id TEXT, guardian_docs TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT,
  details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
'''

# Columns added after the initial migration (applied to existing databases).
ADDED_COLUMNS = {
    'persons': [
        ('first_name', "ALTER TABLE persons ADD COLUMN first_name TEXT"),
        ('second_name', "ALTER TABLE persons ADD COLUMN second_name TEXT"),
        ('third_name', "ALTER TABLE persons ADD COLUMN third_name TEXT"),
        ('fourth_name', "ALTER TABLE persons ADD COLUMN fourth_name TEXT"),
        ('mother_name', "ALTER TABLE persons ADD COLUMN mother_name TEXT"),
        ('place_of_birth', "ALTER TABLE persons ADD COLUMN place_of_birth TEXT"),
        ('residence', "ALTER TABLE persons ADD COLUMN residence TEXT"),
        ('occupation', "ALTER TABLE persons ADD COLUMN occupation TEXT"),
        ('passport_id', "ALTER TABLE persons ADD COLUMN passport_id TEXT"),
        ('photo_path', "ALTER TABLE persons ADD COLUMN photo_path TEXT"),
    ],
    'clearance_applications': [
        ('guardian_id', "ALTER TABLE clearance_applications ADD COLUMN guardian_id TEXT"),
        ('guardian_occupation', "ALTER TABLE clearance_applications ADD COLUMN guardian_occupation TEXT"),
        ('guardian_address', "ALTER TABLE clearance_applications ADD COLUMN guardian_address TEXT"),
        ('guardian_phone', "ALTER TABLE clearance_applications ADD COLUMN guardian_phone TEXT"),
        ('applicant_docs', "ALTER TABLE clearance_applications ADD COLUMN applicant_docs TEXT"),
        ('guardian_docs', "ALTER TABLE clearance_applications ADD COLUMN guardian_docs TEXT"),
        ('applicant_photo', "ALTER TABLE clearance_applications ADD COLUMN applicant_photo TEXT"),
    ],
    'crime_cases': [
        ('incident_summary', "ALTER TABLE crime_cases ADD COLUMN incident_summary TEXT"),
    ],
    'suspect_alerts': [
        ('role', "ALTER TABLE suspect_alerts ADD COLUMN role TEXT NOT NULL DEFAULT 'Suspect'"),
        ('origin', "ALTER TABLE suspect_alerts ADD COLUMN origin TEXT NOT NULL DEFAULT 'Direct Intelligence Listing'"),
    ],
    'checkpoint_events': [
        ('purpose_of_visit', "ALTER TABLE checkpoint_events ADD COLUMN purpose_of_visit TEXT"),
        ('current_address', "ALTER TABLE checkpoint_events ADD COLUMN current_address TEXT"),
        ('permanent_address', "ALTER TABLE checkpoint_events ADD COLUMN permanent_address TEXT"),
        ('traveler_photo', "ALTER TABLE checkpoint_events ADD COLUMN traveler_photo TEXT"),
        ('traveler_docs', "ALTER TABLE checkpoint_events ADD COLUMN traveler_docs TEXT"),
        ('guardian_person_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_person_id INTEGER REFERENCES persons(id)"),
        ('guardian_name', "ALTER TABLE checkpoint_events ADD COLUMN guardian_name TEXT"),
        ('guardian_relationship', "ALTER TABLE checkpoint_events ADD COLUMN guardian_relationship TEXT"),
        ('guardian_phone', "ALTER TABLE checkpoint_events ADD COLUMN guardian_phone TEXT"),
        ('guardian_address', "ALTER TABLE checkpoint_events ADD COLUMN guardian_address TEXT"),
        ('guardian_occupation', "ALTER TABLE checkpoint_events ADD COLUMN guardian_occupation TEXT"),
        ('guardian_national_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_national_id TEXT"),
        ('guardian_passport_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_passport_id TEXT"),
        ('guardian_docs', "ALTER TABLE checkpoint_events ADD COLUMN guardian_docs TEXT"),
    ],
}

NAME_PART_FIELDS = ('first_name', 'second_name', 'third_name', 'fourth_name')
PERSON_FIELDS = NAME_PART_FIELDS + ('full_name', 'national_id', 'date_of_birth', 'phone',
                                    'mother_name', 'place_of_birth', 'residence',
                                    'occupation', 'passport_id', 'photo_path')

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

def has_notnull(c, table, col):
    for r in c.execute(f'PRAGMA table_info({table})'):
        if r['name'] == col:
            return bool(r['notnull'])
    return False

def rebuild_persons(c):
    """Rebuild persons so national_id/passport can be optional (dev migration)."""
    c.execute('''CREATE TABLE persons_new(
      id INTEGER PRIMARY KEY, person_id TEXT UNIQUE NOT NULL,
      full_name TEXT NOT NULL, first_name TEXT, second_name TEXT, third_name TEXT, fourth_name TEXT,
      national_id TEXT UNIQUE, date_of_birth TEXT, phone TEXT,
      mother_name TEXT, place_of_birth TEXT, residence TEXT,
      occupation TEXT, passport_id TEXT, photo_path TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''INSERT INTO persons_new(id,person_id,full_name,national_id,date_of_birth,phone,
        mother_name,place_of_birth,residence,occupation,passport_id,photo_path,created_at,updated_at)
      SELECT id,person_id,full_name,national_id,date_of_birth,phone,
        mother_name,place_of_birth,residence,occupation,passport_id,photo_path,created_at,updated_at
      FROM persons''')
    c.execute('DROP TABLE persons')
    c.execute('ALTER TABLE persons_new RENAME TO persons')

def rebuild_suspect_alerts(c):
    """Rebuild suspect_alerts so the linked case is optional (dev migration)."""
    c.execute('''CREATE TABLE suspect_alerts_new(
      id INTEGER PRIMARY KEY, alert_id TEXT UNIQUE NOT NULL,
      person_id INTEGER NOT NULL REFERENCES persons(id),
      case_id INTEGER REFERENCES crime_cases(id),
      role TEXT NOT NULL DEFAULT 'Suspect',
      alert_status TEXT NOT NULL DEFAULT 'Active alert',
      origin TEXT NOT NULL DEFAULT 'Direct Intelligence Listing',
      notes TEXT, created_by INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''INSERT INTO suspect_alerts_new(id,alert_id,person_id,case_id,role,alert_status,
        notes,created_by,created_at)
      SELECT id,alert_id,person_id,case_id,role,alert_status,notes,created_by,created_at
      FROM suspect_alerts''')
    c.execute("UPDATE suspect_alerts_new SET origin='Case Link' WHERE case_id IS NOT NULL")
    c.execute('DROP TABLE suspect_alerts')
    c.execute('ALTER TABLE suspect_alerts_new RENAME TO suspect_alerts')

def migrate(c):
    tables = {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # Table rebuilds must run with foreign keys off, then be validated after.
    c.execute('PRAGMA foreign_keys=OFF')
    try:
        if 'persons' in tables and has_notnull(c, 'persons', 'national_id'):
            rebuild_persons(c)
        if 'suspect_alerts' in tables and has_notnull(c, 'suspect_alerts', 'case_id'):
            rebuild_suspect_alerts(c)
        for table, cols in ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
            for col, sql in cols:
                if col not in existing:
                    c.execute(sql)
        # Existing case-linked suspects are recorded as case links.
        c.execute("UPDATE suspect_alerts SET origin='Case Link' "
                  "WHERE case_id IS NOT NULL AND origin='Direct Intelligence Listing'")
        # Backfill 4-part name columns from legacy full_name values.
        rows = c.execute("SELECT id,full_name FROM persons "
                         "WHERE TRIM(COALESCE(first_name,''))=''").fetchall()
        for r in rows:
            a, b, d, e = raw_parts(r['full_name'])
            c.execute('UPDATE persons SET first_name=?,second_name=?,third_name=?,fourth_name=? WHERE id=?',
                      (a, b, d, e, r['id']))
        violations = c.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Foreign key violations after migration: {violations[:3]}')
    finally:
        c.execute('PRAGMA foreign_keys=ON')

def init_db():
    c = db()
    c.executescript(SCHEMA)
    migrate(c)
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        c.execute('INSERT INTO users(username,display_name,role,branch,password_hash) VALUES(?,?,?,?,?)',
                  ('admin','Officer A. Hassan','Administrator','Central HQ', password_hash('ChangeMe123!')))
    if c.execute('SELECT COUNT(*) FROM persons').fetchone()[0] == 0:
        c.execute('''INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,fourth_name,
            national_id,date_of_birth,phone,mother_name,residence,occupation,passport_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  ('P-0001','Ayaan Cabdi Xasan Axmed','Ayaan','Cabdi','Xasan','Axmed',
                   '10012345','1997-04-18','+252 63 555 0199','Faadumo Cali',
                   'Hargeisa, Jigjiga Yar','Civil servant','P0011223'))
        c.execute('''INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,fourth_name,
            national_id,date_of_birth,phone,mother_name,residence,occupation)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                  ('P-0002','Maxamed Nuur Cali Awil','Maxamed','Nuur','Cali','Awil',
                   '10067890','1989-11-02','+252 63 555 0188','Khadra Jaamac',
                   'Hargeisa Central','Trader'))
        c.execute('''INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,fourth_name,
            national_id,date_of_birth,phone,mother_name,residence,occupation)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                  ('P-0003','Sahra Yuusuf Axmed Aadan','Sahra','Yuusuf','Axmed','Aadan',
                   '10024680','2001-02-26','+252 63 555 0144','Amina Maxamed',
                   'Hargeisa, 26 June','Student'))
        pid = c.execute("SELECT id FROM persons WHERE person_id='P-0001'").fetchone()[0]
        c.execute('INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,flight_number,route) VALUES(?,?,?,?,?,?)',
                  ('AR-1001',pid,'Arrival','2026-07-18','HL-118','Berbera / Hargeisa'))
        fp_pid = c.execute("SELECT id FROM persons WHERE person_id='P-0003'").fetchone()[0]
        c.execute("INSERT INTO clearance_applications(application_id,person_id,purpose,guardian_name,guardian_relationship,guardian_phone,status) VALUES(?,?,?,?,?,?,?)",
                  ('FP-2026-0042',fp_pid,'Education','Yuusuf Axmed','Father','+252 63 555 0200','Pending Review'))
        c.execute('INSERT INTO crime_cases(case_id,category,location,status,incident_summary) VALUES(?,?,?,?,?)',
                  ('CID-2026-008','Property crime','Hargeisa Central','Under Investigation','Shop burglary overnight; cash and goods reported missing.'))
        c.execute('INSERT INTO crime_cases(case_id,category,location,status,incident_summary) VALUES(?,?,?,?,?)',
                  ('CID-2026-009','Fraud','Jigjiga Yar','Submitted for Prosecution','Advance-fee fraud reported by a local business owner.'))
        susp_pid = c.execute("SELECT id FROM persons WHERE person_id='P-0002'").fetchone()[0]
        susp_case = c.execute("SELECT id FROM crime_cases WHERE case_id='CID-2026-008'").fetchone()[0]
        c.execute('INSERT INTO suspect_alerts(alert_id,person_id,case_id,role,alert_status,origin) VALUES(?,?,?,?,?,?)',
                  ('AL-'+secrets.token_hex(4),susp_pid,susp_case,'Suspect','Active alert','Case Link'))
        admin_id = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        c.execute("""INSERT INTO checkpoint_events(event_id,person_id,location,screening_result,
            action_taken,created_by,created_at) VALUES(?,?,?,?,?,?,?)""",
                  ('CP-'+secrets.token_hex(4),susp_pid,'South','Flagged match',
                   'Supervisor contacted',admin_id,'2026-08-30 08:42:00'))
    c.commit(); c.close()

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

def require_auth(handler):
    token = handler.headers.get('Authorization','').replace('Bearer ','')
    user_id = TOKENS.get(token)
    if not user_id: raise PermissionError('Authentication required')
    c = db()
    user = rowdict(c.execute('SELECT id,username,display_name,role,branch FROM users WHERE id=? AND active=1',(user_id,)).fetchone())
    c.close()
    if not user: raise PermissionError('Authentication required')
    return user

def audit(c, user, action, entity, entity_id, details=''):
    c.execute('INSERT INTO audit_events(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',
              (user['id'], action, entity, entity_id, details))

def new_person_id(c):
    while True:
        pid = 'P-' + str(int(time.time()*1000))[-8:]
        if not c.execute('SELECT 1 FROM persons WHERE person_id=?',(pid,)).fetchone():
            return pid

# ---- identity resolution (universal matching engine) ------------------------
TIER_LABELS = {
    1: 'Tier 1 · Exact National ID / Passport match (auto merge / link)',
    2: 'Tier 2 · Exact 4-part name + date of birth match (high-confidence link)',
    3: 'Tier 3 · 3-part name + mother\u2019s name (fuzzy warning only)',
    4: 'Tier 4 · Partial name match (2\u20134 parts) \u2014 select the record to auto-fill',
}

def find_by_id(c, data):
    """Tier 1: exact National ID or Passport match (case/space insensitive)."""
    national_id = norm(data.get('national_id'))
    passport_id = norm(data.get('passport_id'))
    if national_id:
        row = c.execute("SELECT * FROM persons WHERE LOWER(TRIM(COALESCE(national_id,''))) = ?",
                        (national_id,)).fetchone()
        if row: return rowdict(row), 1
    if passport_id:
        row = c.execute("SELECT * FROM persons WHERE LOWER(TRIM(COALESCE(passport_id,''))) = ?",
                        (passport_id,)).fetchone()
        if row: return rowdict(row), 1
    return None, 0

def name_parts_of(row):
    """Normalised name components of a stored person (4-part columns or legacy full_name)."""
    parts = [str(row.get(k) or '').strip() for k in NAME_PART_FIELDS]
    if any(parts):
        return [norm(p) for p in parts if p]
    return split_parts(row.get('full_name') or '')

def person_suggestions(c, data, limit=8):
    """Flexible, case-insensitive matching for the live dropdown.

    Scores each central person against the entered name components (2, 3 or 4
    parts must all be present in the stored name) and partial/exact National ID
    or Passport values; returns the best matches ordered by score.
    """
    entered = [norm(data.get(k)) for k in NAME_PART_FIELDS]
    entered = [p for p in entered if p]
    nat = norm(data.get('national_id'))
    pas = norm(data.get('passport_id'))
    dob = norm(data.get('date_of_birth'))
    mother = norm(data.get('mother_name'))
    scored = []
    for r in c.execute('SELECT * FROM persons'):
        row = rowdict(r)
        parts = name_parts_of(row)
        partset = set(parts)
        score = 0
        if nat:
            sid = norm(row.get('national_id'))
            if sid == nat:
                score += 60
            elif len(nat) >= 2 and sid.startswith(nat):
                score += 25
        if pas:
            spid = norm(row.get('passport_id'))
            if spid == pas:
                score += 60
            elif len(pas) >= 2 and spid.startswith(pas):
                score += 25
        if len(entered) >= 2 and all(p in partset for p in entered):
            score += len(entered) * 10
            if parts[:len(entered)] == entered:
                score += 8          # entered components are a prefix, in order
            if dob and norm(row.get('date_of_birth')) == dob:
                score += 12
            if mother and norm(row.get('mother_name')) == mother:
                score += 8
        if score >= 18:
            copied = dict(row)
            copied['suggestion_score'] = score
            scored.append(copied)
    scored.sort(key=lambda x: (-x['suggestion_score'], x['person_id']))
    out, seen = [], set()
    for row in scored:
        if row['person_id'] in seen:
            continue
        seen.add(row['person_id'])
        out.append(row)
        if len(out) >= limit:
            break
    return out

def resolve_person(c, data):
    """Universal matching engine.

    Returns (person_row_dict | None, tier, reason, suggestions).
    Tier 1 = exact ID/passport, Tier 2 = exact 4-part name + DOB,
    Tier 3 = fuzzy 3-part name + mother's name, Tier 4 = partial name match.
    """
    rows = [rowdict(r) for r in c.execute('SELECT * FROM persons')]
    row, tier = find_by_id(c, data)
    if row:
        return row, 1, 'Exact National ID / Passport match', []

    parts = [norm(data.get(k)) for k in NAME_PART_FIELDS]
    dob = norm(data.get('date_of_birth'))
    if all(parts) and dob:
        target = ' '.join(parts)
        for r in rows:
            if ' '.join(split_parts(r.get('full_name'))) == target and norm(r.get('date_of_birth')) == dob:
                return r, 2, 'Exact 4-part name + date of birth match', []

    mother = norm(data.get('mother_name'))
    entered = [p for p in parts if p]
    if mother and len(entered) >= 3:
        candidates = []
        for r in rows:
            stored = set(split_parts(r.get('full_name')))
            if norm(r.get('mother_name')) == mother and sum(1 for p in entered if p in stored) >= 3:
                candidates.append(r)
        if candidates:
            reason = ('Fuzzy 3-part name + mother\u2019s name match \u2014 '
                      f'{len(candidates)} candidate(s); officer confirmation required')
            return candidates[0], 3, reason, candidates

    suggestions = person_suggestions(c, data)
    strong = [s for s in suggestions if s['suggestion_score'] >= 30]
    if len(strong) == 1:
        matched = strong[0]
        n = len(entered) if entered else 0
        reason = (f'Partial name match ({n}-part) \u2014 matching Central Person found; '
                  'select it to auto-fill and link')
        return matched, 4, reason, suggestions
    if suggestions:
        return None, 0, 'Possible matches found \u2014 select a record from the matching list', suggestions
    return None, 0, 'No exact central record found \u2014 a new Central Person record will be created on save.', []

def resolve_identity(c, data):
    """JSON-safe response for /api/persons/resolve."""
    row, tier, reason, suggestions = resolve_person(c, data)
    for s in suggestions:
        s.pop('suggestion_score', None)
    return {
        'matched': row is not None,
        'tier': tier,
        'tier_label': TIER_LABELS.get(tier, 'No match'),
        'reason': reason,
        'person': row,
        'candidates': [dict(x) for x in suggestions],
        'suggestions': [dict(x) for x in suggestions],
        'auto_merge': tier in (1, 2),
    }

def create_person(c, data, photo_path=None, allow_no_id=False):
    """Create a new central person record. Returns (row, True)."""
    full_name = build_full_name(data)
    if not full_name:
        raise ValueError('Full name is required')
    national_id = (data.get('national_id') or '').strip().upper()
    passport_id = (data.get('passport_id') or '').strip().upper()
    if not national_id and not passport_id and not allow_no_id:
        raise ValueError('National ID or Passport ID is required')
    a, b, d, e = raw_parts(full_name)
    pid = new_person_id(c)
    c.execute('''INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,fourth_name,
        national_id,date_of_birth,phone,mother_name,place_of_birth,residence,occupation,
        passport_id,photo_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (pid, full_name, a, b, d, e, national_id,
               data.get('date_of_birth',''), data.get('phone',''),
               data.get('mother_name',''), data.get('place_of_birth',''),
               data.get('residence',''), data.get('occupation',''),
               passport_id, photo_path))
    return rowdict(c.execute('SELECT * FROM persons WHERE person_id=?', (pid,)).fetchone()), True

def upsert_person(c, data, photo_path=None, allow_no_id=False):
    """Smart identity resolution + merge.

    Tier 1 (exact ID/passport) and Tier 2 (exact 4-part name + DOB) records are
    merged automatically; otherwise a new Central Person is created.
    Returns (row, created).
    """
    row, tier = find_by_id(c, data)
    if not row:
        row, tier, _, _ = resolve_person(c, data)
    if row and tier in (1, 2):
        pid = row['id']
        updates, params = [], []
        for f in PERSON_FIELDS:
            val = data.get(f)
            if f == 'photo_path': val = photo_path or row.get('photo_path')
            if f in ('national_id', 'passport_id'): val = str(val or '').strip().upper()
            if val is not None and str(val).strip() != '' and str(val).strip() != str(row.get(f) or '').strip():
                updates.append(f'{f}=?'); params.append(str(val).strip())
        if updates:
            updates.append('updated_at=CURRENT_TIMESTAMP')
            params.append(pid)
            c.execute(f"UPDATE persons SET {', '.join(updates)} WHERE id=?", params)
        return rowdict(c.execute('SELECT * FROM persons WHERE id=?', (pid,)).fetchone()), False
    return create_person(c, data, photo_path, allow_no_id)

def ensure_person(c, data, photo_path=None, allow_no_id=False):
    """Resolve an existing person_id or auto-create the Central Person record
    from the identity fields carried by a unit request. Returns (row, created)."""
    pid = norm(data.get('person_id'))
    if pid:
        row = rowdict(c.execute('SELECT * FROM persons WHERE person_id=?', (pid,)).fetchone())
        if row: return row, False
    identity_present = any(str(data.get(k) or '').strip() for k in
                           ('first_name','second_name','third_name','fourth_name','full_name',
                            'national_id','passport_id','mother_name'))
    if identity_present:
        return upsert_person(c, data, photo_path, allow_no_id)
    raise ValueError('A person_id or person identity fields are required')

def identity_result(c, data, person):
    """Small match summary returned with unit record POST responses."""
    row, tier, reason, _ = resolve_person(c, data)
    matched = row is not None and row['person_id'] == person['person_id']
    return {'person_id': person['person_id'], 'matched': matched,
            'tier': tier if matched else 0, 'reason': reason}

class API(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print('%s - %s' % (self.address_string(), fmt % args))

    def send_json(self, status, data):
        out = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(out)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods','GET, POST, PATCH, OPTIONS')
        self.end_headers(); self.wfile.write(out)

    def send_file(self, path, ctype):
        try:
            with open(path,'rb') as f: data = f.read()
        except OSError:
            self.send_json(404, {'error':'Not found'}); return
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_OPTIONS(self): self.send_json(204, {})

    # ---- static pages & uploads --------------------------------------------
    def serve_static(self, path):
        p = urlparse(path)
        if p.path in ('/','/index.html'):
            return self.send_file(os.path.join(PROJECT_ROOT,'index.html'), 'text/html; charset=utf-8')
        if p.path in ('/application.html','/certificate.html'):
            return self.send_file(os.path.join(PROJECT_ROOT, p.path.lstrip('/')), 'text/html; charset=utf-8')
        if p.path.startswith('/uploads/'):
            name = os.path.basename(p.path)
            ext = os.path.splitext(name)[1].lower()
            ctype = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png',
                     '.gif':'image/gif','.webp':'image/webp','.pdf':'application/pdf'}.get(ext,'application/octet-stream')
            return self.send_file(os.path.join(UPLOAD_DIR, name), ctype)
        return None

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        if self.serve_static(self.path) is not None: return
        c = None
        try:
            p = urlparse(self.path)
            if p.path == '/api/health':
                return self.send_json(200, {'status':'ok','service':'sentinel-backend','database':'sqlite-development'})
            user = require_auth(self); c = db()
            if p.path == '/api/me': result = user
            elif p.path == '/api/persons':
                q = re.sub(r'\s+', ' ', parse_qs(p.query).get('q',[''])[0]).strip()
                like = f'%{q}%'
                rows = c.execute('''SELECT * FROM persons WHERE full_name LIKE ? OR person_id LIKE ?
                    OR national_id LIKE ? OR phone LIKE ? OR passport_id LIKE ? OR mother_name LIKE ?
                    OR first_name LIKE ? OR second_name LIKE ? OR third_name LIKE ? OR fourth_name LIKE ?
                    ORDER BY id DESC''', (like,like,like,like,like,like,like,like,like,like)).fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path.startswith('/api/persons/'):
                pid = p.path.split('/')[3]
                person = rowdict(c.execute('SELECT * FROM persons WHERE person_id=?',(pid,)).fetchone())
                if not person: self.send_json(404,{'error':'Person not found'}); c.close(); return
                person['airport'] = [dict(r) for r in c.execute('SELECT record_id,movement,travel_date,flight_number,route FROM airport_passengers WHERE person_id=?',(person['id'],)).fetchall()]
                person['clearance'] = [dict(r) for r in c.execute('SELECT application_id,purpose,status,certificate_number FROM clearance_applications WHERE person_id=?',(person['id'],)).fetchall()]
                person['alerts'] = [dict(r) for r in c.execute('''SELECT sa.alert_id,sa.role,sa.alert_status,sa.origin,cc.case_id
                    FROM suspect_alerts sa LEFT JOIN crime_cases cc ON cc.id=sa.case_id
                    WHERE sa.person_id=?''',(person['id'],)).fetchall()]
                person['checkpoints'] = [dict(r) for r in c.execute('''SELECT event_id,location,screening_result,action_taken,notes,created_at
                    FROM checkpoint_events WHERE person_id=? ORDER BY id DESC''',(person['id'],)).fetchall()]
                result = person
            elif p.path == '/api/airport-records':
                rows = c.execute('''SELECT a.record_id,a.movement,a.travel_date,a.flight_number,a.route,a.notes,
                    p.person_id,p.full_name,p.national_id FROM airport_passengers a
                    JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/clearance-applications':
                rows = c.execute('''SELECT a.application_id,a.purpose,a.status,a.certificate_number,a.created_at,
                    a.guardian_name,p.person_id,p.full_name,p.national_id,p.passport_id,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path.startswith('/api/clearance-applications/'):
                aid = p.path.split('/')[3]
                a = rowdict(c.execute('''SELECT a.*,p.full_name,p.national_id,p.date_of_birth,p.mother_name,
                    p.place_of_birth,p.residence,p.occupation,p.passport_id,p.photo_path,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id
                    WHERE a.application_id=?''',(aid,)).fetchone())
                if not a: self.send_json(404,{'error':'Application not found'}); c.close(); return
                result = a
            elif p.path == '/api/crime-cases':
                rows = c.execute('''SELECT cc.*, COUNT(sa.id) AS participant_count
                    FROM crime_cases cc LEFT JOIN suspect_alerts sa ON sa.case_id=cc.id
                    GROUP BY cc.id ORDER BY cc.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path.startswith('/api/crime-cases/'):
                cid = p.path.split('/')[3]
                case = rowdict(c.execute('SELECT * FROM crime_cases WHERE case_id=?',(cid,)).fetchone())
                if not case: self.send_json(404,{'error':'Case not found'}); c.close(); return
                case['participants'] = [dict(r) for r in c.execute('''SELECT sa.alert_id,sa.role,sa.notes,sa.alert_status,
                    sa.origin,cc.case_id,p.person_id,p.full_name,p.national_id,p.phone FROM suspect_alerts sa
                    JOIN persons p ON p.id=sa.person_id JOIN crime_cases cc ON cc.id=sa.case_id
                    WHERE sa.case_id=? ORDER BY sa.id''',(case['id'],)).fetchall()]
                case['evidence'] = [dict(r) for r in c.execute('''SELECT evidence_id,caption,file_path,file_name,file_type,created_at
                    FROM case_evidence WHERE case_id=? ORDER BY id DESC''',(case['id'],)).fetchall()]
                result = case
            elif p.path == '/api/suspect-alerts':
                rows = c.execute('''SELECT sa.alert_id,sa.role,sa.alert_status,sa.origin,sa.notes,
                    cc.case_id,cc.category,cc.status AS case_status,
                    p.person_id,p.full_name,p.national_id,p.passport_id FROM suspect_alerts sa
                    JOIN persons p ON p.id=sa.person_id
                    LEFT JOIN crime_cases cc ON cc.id=sa.case_id
                    ORDER BY sa.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/checkpoint-events':
                rows = c.execute('''SELECT ce.event_id,ce.location,ce.screening_result,ce.action_taken,
                    ce.notes,ce.created_at,ce.purpose_of_visit,ce.current_address,ce.permanent_address,
                    ce.traveler_photo,ce.traveler_docs,ce.guardian_person_id,ce.guardian_name,
                    ce.guardian_relationship,ce.guardian_phone,ce.guardian_address,ce.guardian_occupation,
                    ce.guardian_national_id,ce.guardian_passport_id,ce.guardian_docs,
                    p.person_id,p.full_name,p.national_id,p.passport_id FROM checkpoint_events ce
                    JOIN persons p ON p.id=ce.person_id ORDER BY ce.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(200, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        c = None
        try:
            p = urlparse(self.path)
            if p.path == '/api/login':
                data = body_json(self); c = db()
                u = c.execute('SELECT * FROM users WHERE username=? AND password_hash=? AND active=1',
                              (data.get('username'), password_hash(data.get('password','')))).fetchone(); c.close()
                if not u: self.send_json(401,{'error':'Invalid username or password'}); return
                token = secrets.token_urlsafe(32); TOKENS[token] = u['id']
                self.send_json(200,{'token':token,'user':{'id':u['id'],'username':u['username'],
                    'display_name':u['display_name'],'role':u['role'],'branch':u['branch']}}); return
            user = require_auth(self); c = db()
            if p.path == '/api/persons':
                data = body_json(self)
                if not build_full_name(data):
                    raise ValueError('full_name or a 4-part name is required')
                existing, _ = find_by_id(c, data)
                if existing:
                    self.send_json(409,{'error':'A person with this National ID / Passport already exists','person':existing}); c.close(); return
                person, _ = create_person(c, data); audit(c,user,'CREATE','person',person['person_id'])
                c.commit(); result = {'person':person}
            elif p.path == '/api/persons/resolve':
                data = body_json(self)
                result = resolve_identity(c, data)
            elif p.path == '/api/persons/upsert':
                data = body_json(self); person, created = upsert_person(c, data)
                audit(c,user,'CREATE' if created else 'UPSERT','person',person['person_id'])
                c.commit(); result = {'person':person,'created':created}
            elif p.path == '/api/airport-records':
                data = body_json(self)
                person, created = ensure_person(c, data)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from airport register')
                rid = 'AR-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,
                    flight_number,route,notes,created_by) VALUES(?,?,?,?,?,?,?,?)''',
                    (rid,person['id'],data.get('movement','Arrival'),data.get('travel_date',''),
                     data.get('flight_number',''),data.get('route',''),data.get('notes',''),user['id']))
                audit(c,user,'CREATE','airport_record',rid,person['person_id']); c.commit()
                result = {'record_id':rid,'identity':identity_result(c,data,person)}
            elif p.path == '/api/clearance-applications':
                ctype = self.headers.get('Content-Type','')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                if not build_full_name(fields):
                    raise ValueError('Applicant full name (4-part) is required')
                if not (fields.get('national_id') or '').strip() and not (fields.get('passport_id') or '').strip():
                    raise ValueError('Applicant National ID or Passport ID is required')
                photo = save_upload(files['photo']) if 'photo' in files else None
                person, created = ensure_person(c, fields, photo_path=(photo['path'] if photo else None))
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from clearance application')
                app_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_app_')]
                guard_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_guard_')]
                if len(app_docs) < 2: raise ValueError('At least 2 applicant documents are required')
                if not fields.get('guardian_name'): raise ValueError('Guardian full name is required')
                if len(guard_docs) < 2: raise ValueError('At least 2 guardian documents are required')
                aid = 'FP-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO clearance_applications(application_id,person_id,purpose,
                    guardian_name,guardian_relationship,guardian_id,guardian_occupation,guardian_address,
                    guardian_phone,legal_document_ref,notes,applicant_docs,guardian_docs,applicant_photo,created_by)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (aid,person['id'],fields.get('purpose','Other'),fields.get('guardian_name',''),
                     fields.get('guardian_relationship',''),fields.get('guardian_id',''),
                     fields.get('guardian_occupation',''),fields.get('guardian_address',''),
                     fields.get('guardian_phone',''),fields.get('legal_document_ref',''),
                     fields.get('notes',''),json.dumps(app_docs),json.dumps(guard_docs),
                     photo['path'] if photo else None,user['id']))
                audit(c,user,'CREATE','clearance_application',aid,person['person_id']); c.commit()
                result = {'application_id':aid,'person_id':person['person_id'],
                          'status':'Pending Review','identity':identity_result(c,fields,person)}
            elif p.path.startswith('/api/clearance-applications/') and p.path.endswith('/approve'):
                aid = p.path.split('/')[3]
                cert = 'CL-'+str(int(time.time()*1000))[-8:]
                c.execute("UPDATE clearance_applications SET status='Approved',certificate_number=?,reviewed_at=CURRENT_TIMESTAMP WHERE application_id=?",
                          (cert,aid))
                audit(c,user,'APPROVE','clearance_application',aid,cert); c.commit()
                result = {'application_id':aid,'certificate_number':cert,'status':'Approved'}
            elif p.path == '/api/crime-cases':
                data = body_json(self)
                if not data.get('category'): raise ValueError('category is required')
                nxt = c.execute('SELECT COUNT(*) FROM crime_cases').fetchone()[0]+8
                case_id = 'CID-2026-'+str(nxt).zfill(3)
                c.execute('''INSERT INTO crime_cases(case_id,category,location,status,incident_summary,notes,created_by)
                    VALUES(?,?,?,?,?,?,?)''',(case_id,data['category'],data.get('location','Not specified'),
                    data.get('status','Reported'),data.get('incident_summary',''),data.get('notes',''),user['id']))
                audit(c,user,'CREATE','crime_case',case_id); c.commit()
                result = {'case_id':case_id,'category':data['category'],'status':'Reported'}
            elif p.path.startswith('/api/crime-cases/') and p.path.endswith('/evidence'):
                cid = p.path.split('/')[3]
                case = c.execute('SELECT id FROM crime_cases WHERE case_id=?',(cid,)).fetchone()
                if not case: raise ValueError('case_id must refer to an existing case')
                fields, files = parse_multipart(self)
                if 'file' not in files: raise ValueError('An evidence file is required')
                meta = save_upload(files['file'])
                eid = 'EV-'+secrets.token_hex(4)
                c.execute('''INSERT INTO case_evidence(evidence_id,case_id,caption,file_path,file_name,file_type,uploaded_by)
                    VALUES(?,?,?,?,?,?,?)''',(eid,case['id'],fields.get('caption',''),meta['path'],
                    meta['name'],fields.get('file_type','Evidence'),user['id']))
                audit(c,user,'UPLOAD','evidence',eid,cid); c.commit()
                result = {'evidence_id':eid,'file_path':meta['path']}
            elif p.path == '/api/suspect-alerts':
                data = body_json(self)
                case = None
                case_id = (data.get('case_id') or '').strip()
                if case_id:
                    case = c.execute('SELECT id,case_id,category FROM crime_cases WHERE case_id=?',(case_id,)).fetchone()
                    if not case: raise ValueError('case_id must refer to an existing CID case')
                reason = (data.get('notes') or data.get('reason') or '').strip()
                if case and not reason:
                    # Case-linked suspects default the reason to the case details.
                    reason = f'Linked to CID case {case["case_id"]} \u2014 {case["category"]}'
                elif not case and not reason:
                    raise ValueError('Suspect reason / alert details is required for unlinked suspects '
                                     '(Direct Intelligence Listing / Manual Entry)')
                origin = (data.get('origin') or '').strip()
                if not origin: origin = 'Case Link' if case else 'Direct Intelligence Listing'
                person, created = ensure_person(c, data)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from suspect listing')
                if case:
                    dup = c.execute('SELECT alert_id FROM suspect_alerts WHERE person_id=? AND case_id=? AND alert_status=?',
                                    (person['id'],case['id'],'Active alert')).fetchone()
                else:
                    dup = c.execute('SELECT alert_id FROM suspect_alerts WHERE person_id=? AND case_id IS NULL AND alert_status=?',
                                    (person['id'],'Active alert')).fetchone()
                if dup:
                    self.send_json(409,{'error':'An active alert already links this person' +
                                        (' to that case' if case else ' without a linked case'),
                                        'alert_id':dup['alert_id']}); c.close(); return
                alert_id = 'AL-'+secrets.token_hex(4)
                c.execute('''INSERT INTO suspect_alerts(alert_id,person_id,case_id,role,alert_status,origin,notes,created_by)
                    VALUES(?,?,?,?,?,?,?,?)''',(alert_id,person['id'], case['id'] if case else None,
                    data.get('role','Suspect'),'Active alert',origin,reason,user['id']))
                audit(c,user,'CREATE','suspect_alert',alert_id,
                      data.get('case_id','') or ('no case - '+origin)); c.commit()
                result = {'alert_id':alert_id,'case_id':case_id or None,'person_id':person['person_id'],
                          'role':data.get('role','Suspect'),'alert_status':'Active alert',
                          'origin':origin,'reason':reason,'identity':identity_result(c,data,person)}
            elif p.path == '/api/checkpoint-events':
                ctype = self.headers.get('Content-Type','')
                if ctype.startswith('multipart/form-data'):
                    data, files = parse_multipart(self)
                else:
                    data, files = body_json(self), {}
                # ---- validate everything before any person/file writes ----
                if not build_full_name(data):
                    raise ValueError('Traveler full name (4-part) is required')
                if not (data.get('date_of_birth') or '').strip():
                    raise ValueError('Traveler date of birth is required')
                purpose = (data.get('purpose_of_visit') or '').strip()
                if not purpose: raise ValueError('Purpose of visit is required')
                current_addr = (data.get('current_address') or data.get('residence') or '').strip()
                if not current_addr: raise ValueError('Traveler current address is required')
                tr_keys = sorted(k for k in files if k.startswith('doc_tr_'))
                gd_keys = sorted(k for k in files if k.startswith('doc_gd_'))
                if len(tr_keys) < 1: raise ValueError('At least 1 traveler document is required')
                if 'photo' not in files: raise ValueError('Traveler real-time photo is required')
                guardian_parts = [str(data.get('guardian_'+k) or '').strip() for k in
                                  ('first_name','second_name','third_name','fourth_name')]
                guardian_name = ' '.join(p for p in guardian_parts if p) or (data.get('guardian_name') or '').strip()
                if not guardian_name:
                    raise ValueError('Guardian full name is required')
                if not (data.get('guardian_relationship') or '').strip():
                    raise ValueError('Guardian relationship is required')
                if not (data.get('guardian_phone') or '').strip():
                    raise ValueError('Guardian contact number is required')
                if not (data.get('guardian_address') or '').strip():
                    raise ValueError('Guardian permanent address is required')
                if not (data.get('guardian_occupation') or '').strip():
                    raise ValueError('Guardian occupation is required')
                if len(gd_keys) < 1: raise ValueError('At least 1 guardian document is required')
                # ---- traveler identity (auto-create/merge, IDs optional) ----
                photo = save_upload(files['photo'])
                person, created = ensure_person(c, data, photo_path=photo['path'], allow_no_id=True)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from checkpoint stop')
                tr_docs = [save_upload(files[k]) for k in tr_keys]
                gd_docs = [save_upload(files[k]) for k in gd_keys]
                gd_identity = {'national_id': data.get('guardian_national_id'),
                               'passport_id': data.get('guardian_passport_id'),
                               'first_name': data.get('guardian_first_name'),
                               'second_name': data.get('guardian_second_name'),
                               'third_name': data.get('guardian_third_name'),
                               'fourth_name': data.get('guardian_fourth_name')}
                guardian_person = None
                gd_pid = (data.get('guardian_person_id') or '').strip()
                if gd_pid:
                    guardian_person = c.execute('SELECT id FROM persons WHERE person_id=?',(gd_pid,)).fetchone()
                if not guardian_person:
                    match, _ = find_by_id(c, gd_identity)
                    guardian_person = c.execute('SELECT id FROM persons WHERE id=?',(match['id'],)).fetchone() if match else None
                location = (data.get('location') or '').strip()
                if not location: raise ValueError('location is required')
                alerted = c.execute('''SELECT 1 FROM suspect_alerts WHERE person_id=? AND role='Suspect'
                    AND alert_status='Active alert' LIMIT 1''',(person['id'],)).fetchone()
                screen = 'Flagged match' if alerted else 'No active alert'
                action = 'Supervisor contacted' if alerted else 'Cleared'
                event_id = 'CP-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO checkpoint_events(event_id,person_id,location,screening_result,
                    action_taken,notes,purpose_of_visit,current_address,permanent_address,traveler_photo,
                    traveler_docs,guardian_person_id,guardian_name,guardian_relationship,guardian_phone,
                    guardian_address,guardian_occupation,guardian_national_id,guardian_passport_id,
                    guardian_docs,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (event_id,person['id'],location,screen,action,(data.get('notes') or '').strip(),
                     purpose,current_addr,(data.get('permanent_address') or '').strip(),
                     photo['path'],json.dumps(tr_docs),
                     guardian_person['id'] if guardian_person else None,
                     guardian_name,(data.get('guardian_relationship') or '').strip(),
                     (data.get('guardian_phone') or '').strip(),
                     (data.get('guardian_address') or '').strip(),
                     (data.get('guardian_occupation') or '').strip(),
                     (data.get('guardian_national_id') or '').strip().upper(),
                     (data.get('guardian_passport_id') or '').strip().upper(),
                     json.dumps(gd_docs),user['id']))
                audit(c,user,'CREATE','checkpoint_event',event_id,
                      f"{location}:{screen} for {person['person_id']}"); c.commit()
                result = {'event_id':event_id,'person_id':person['person_id'],'location':location,
                          'screening_result':screen,'action_taken':action,'alerted':bool(alerted),
                          'guardian_person_id':guardian_person['person_id'] if guardian_person else None,
                          'traveler_docs':len(tr_docs),'guardian_docs':len(gd_docs),
                          'identity':identity_result(c,data,person)}
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(201, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except ValueError as e:
            if c: c.close()
            self.send_json(400,{'error':str(e)})
        except sqlite3.IntegrityError as e:
            if c: c.close()
            self.send_json(409,{'error':'Database constraint failed','details':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

    # ---- PATCH (profile updates / dynamic record updates) --------------------
    def do_PATCH(self):
        c = None
        try:
            p = urlparse(self.path)
            user = require_auth(self); data = body_json(self); c = db()
            if p.path.startswith('/api/persons/'):
                pid = p.path.split('/')[3]
                row = c.execute('SELECT * FROM persons WHERE person_id=?',(pid,)).fetchone()
                if not row: self.send_json(404,{'error':'Person not found'}); c.close(); return
                updates, params = [], []
                for f in PERSON_FIELDS:
                    val = data.get(f)
                    if val is not None and str(val).strip()!='':
                        updates.append(f'{f}=?'); params.append(str(val).strip())
                if updates:
                    updates.append('updated_at=CURRENT_TIMESTAMP'); params.append(row['id'])
                    c.execute(f"UPDATE persons SET {', '.join(updates)} WHERE id=?", params)
                    audit(c,user,'UPDATE','person',pid)
                c.commit()
                result = {'person': rowdict(c.execute('SELECT * FROM persons WHERE id=?',(row['id'],)).fetchone())}
            elif p.path.startswith('/api/crime-cases/'):
                cid = p.path.split('/')[3]
                row = c.execute('SELECT id FROM crime_cases WHERE case_id=?',(cid,)).fetchone()
                if not row: self.send_json(404,{'error':'Case not found'}); c.close(); return
                updates, params = [], []
                for f in ('category','location','status','incident_summary','notes'):
                    val = data.get(f)
                    if val is not None: updates.append(f'{f}=?'); params.append(val)
                if updates:
                    params.append(row['id'])
                    c.execute(f"UPDATE crime_cases SET {', '.join(updates)} WHERE id=?", params)
                    audit(c,user,'UPDATE','crime_case',cid)
                c.commit(); result = {'case_id':cid,'updated':True}
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(200, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except ValueError as e:
            if c: c.close()
            self.send_json(400,{'error':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT','8001'))
    print(f'Sentinel backend listening on 0.0.0.0:{port}')
    ThreadingHTTPServer(('0.0.0.0', port), API).serve_forever()
