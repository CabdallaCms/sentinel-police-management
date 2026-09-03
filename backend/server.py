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
import datetime, hashlib, json, os, re, secrets, sqlite3, time
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
CREATE TABLE IF NOT EXISTS locations(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL, kind TEXT NOT NULL
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
  airline TEXT, origin_city TEXT, destination_city TEXT,
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
  location TEXT NOT NULL, location_code TEXT, checkpoint_location TEXT,
  screening_result TEXT NOT NULL,
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
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
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
    'users': [
        ('location_scope', "ALTER TABLE users ADD COLUMN location_scope TEXT"),
    ],
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
    'airport_passengers': [
        ('airline', "ALTER TABLE airport_passengers ADD COLUMN airline TEXT"),
        ('origin_city', "ALTER TABLE airport_passengers ADD COLUMN origin_city TEXT"),
        ('destination_city', "ALTER TABLE airport_passengers ADD COLUMN destination_city TEXT"),
    ],
    'clearance_applications': [
        ('guardian_id', "ALTER TABLE clearance_applications ADD COLUMN guardian_id TEXT"),
        ('guardian_occupation', "ALTER TABLE clearance_applications ADD COLUMN guardian_occupation TEXT"),
        ('guardian_address', "ALTER TABLE clearance_applications ADD COLUMN guardian_address TEXT"),
        ('guardian_phone', "ALTER TABLE clearance_applications ADD COLUMN guardian_phone TEXT"),
        ('applicant_docs', "ALTER TABLE clearance_applications ADD COLUMN applicant_docs TEXT"),
        ('guardian_docs', "ALTER TABLE clearance_applications ADD COLUMN guardian_docs TEXT"),
        ('applicant_photo', "ALTER TABLE clearance_applications ADD COLUMN applicant_photo TEXT"),
        # Printable-application extras (Section 01 of the Good Conduct form).
        ('sex', "ALTER TABLE clearance_applications ADD COLUMN sex TEXT"),
        ('email', "ALTER TABLE clearance_applications ADD COLUMN email TEXT"),
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
        # Explicit location metadata: 'location_code' is the canonical short code
        # (South / East / West); 'checkpoint_location' is the human-friendly label
        # (e.g. 'South Checkpoint'). Both are written on every create so dashboards,
        # the identity profile, and the activity feed can show the exact location
        # without joining the locations table.
        ('location_code', "ALTER TABLE checkpoint_events ADD COLUMN location_code TEXT"),
        ('checkpoint_location', "ALTER TABLE checkpoint_events ADD COLUMN checkpoint_location TEXT"),
    ],
}

NAME_PART_FIELDS = ('first_name', 'second_name', 'third_name', 'fourth_name')
PERSON_FIELDS = NAME_PART_FIELDS + ('full_name', 'national_id', 'date_of_birth', 'phone',
                                    'mother_name', 'place_of_birth', 'residence',
                                    'occupation', 'passport_id', 'photo_path')

# ---------------------------------------------------------------------------
# Fingerprint / clearance-application policy.
# ---------------------------------------------------------------------------
# The mandatory `clearance_reason` values offered by the application form.
# Submissions are validated against exactly this list (case-insensitive) and
# the printable application template prints the selected reason verbatim.
CLEARANCE_REASONS = ('Education', 'Travel', 'Employment', 'Citizenship', 'Licence')

# A clearance application may only be approved once the mandatory review
# window has elapsed. System Administrators bypass the gate entirely;
# Fingerprint Officers (and every other non-admin reviewer) must wait.
FINGERPRINT_REVIEW_WINDOW_HOURS = 12

# Accepted spellings for the two roles the approval gate cares about. The
# stored role is canonical ('SystemAdmin' / 'FingerprintUnit') but the API
# also tolerates the spec's snake_case aliases ('admin',
# 'fingerprint_officer') and the historical compound forms.
ADMIN_ROLE_KEYS = {'admin', 'systemadmin', 'systemadministrator'}
FINGERPRINT_ROLE_KEYS = {'fingerprint', 'fingerprintunit', 'fingerprintofficer',
                         'fingerprintunitofficer', 'fpofficer'}

# Build marker — surfaced by /api/health and printed on startup so an operator
# can confirm the running process carries the review-lock rules.
BUILD_TAG = 'sentinel-fingerprint-review-lock-12h'

# /api/fingerprint/applications* is the spec-facing alias for the clearance
# register; both prefixes resolve to the same handler and module gate.
FINGERPRINT_API_ALIAS = '/api/fingerprint/applications'
CLEARANCE_API = '/api/clearance-applications'


def canonical_api_path(path):
    """Resolve the /api/fingerprint/applications alias onto /api/clearance-applications."""
    if path == FINGERPRINT_API_ALIAS or path.startswith(FINGERPRINT_API_ALIAS + '/'):
        return CLEARANCE_API + path[len(FINGERPRINT_API_ALIAS):]
    return path


def _role_key(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def is_fingerprint_officer(user):
    """True for Fingerprint Unit officers (canonical role or the spec alias)."""
    if not user:
        return False
    keys = {_role_key(user.get('role')), _role_key(user.get('role_alias'))}
    keys.add(_role_key(normalize_role(user.get('role') or '')))
    return bool(keys & FINGERPRINT_ROLE_KEYS)


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


# The exact rejection text mandated by the spec for a non-admin approving
# inside the mandatory review window.
REVIEW_LOCK_MESSAGE = ('Review period active. Standard officers must wait 12 hours '
                       'before approving.')


def is_admin_user(user):
    """True only for administrators — the ONLY role allowed to bypass the
    mandatory 12-hour fingerprint review window.

    Accepts the canonical 'SystemAdmin' role and the spec's 'admin' alias
    (case/format-insensitive). Everything else (`FingerprintUnit`,
    `fingerprint_officer`, …) is a standard officer and is gated.
    """
    if not user:
        return False
    role = user.get('role')
    keys = {_role_key(role), _role_key(user.get('role_alias')),
            _role_key(normalize_role(role or ''))}
    return bool(keys & ADMIN_ROLE_KEYS)


def review_gate_decision(app_row, user):
    """Gate an approval request. Returns None when it may proceed, otherwise
    (status_code, payload) for the rejection.

    FAIL-CLOSED — mirroring the mandated implementation:

        is_admin  = user.role in ('admin', 'SystemAdmin')
        if not is_admin:
            if not created_at:                -> 400 (missing stamp = locked)
            hours_elapsed = (utc_now - created_at) / 3600
            if hours_elapsed < 12.0:          -> 400

    The decision uses ONLY the stored row and the server-side role, never
    anything the client supplied.
    """
    if is_admin_user(user):
        return None
    created_at = parse_created_at((app_row or {}).get('created_at'))
    reason = 'submission timestamp missing' if created_at is None else 'review window open'
    if created_at is not None:
        hours_elapsed = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds() / 3600.0
        if hours_elapsed >= float(FINGERPRINT_REVIEW_WINDOW_HOURS):
            return None
    payload = {
        'detail': REVIEW_LOCK_MESSAGE,
        'error': REVIEW_LOCK_MESSAGE,
        'code': 'review_period_active',
        'reason': reason,
        'review_window_hours': FINGERPRINT_REVIEW_WINDOW_HOURS,
        'submitted_at': (app_row or {}).get('created_at'),
    }
    if created_at is not None:
        payload['hours_elapsed'] = round(max(0.0, hours_elapsed), 2)
        payload['hours_remaining'] = round(float(FINGERPRINT_REVIEW_WINDOW_HOURS) - max(0.0, hours_elapsed), 2)
        payload['review_eligible_at'] = (created_at + datetime.timedelta(
            hours=FINGERPRINT_REVIEW_WINDOW_HOURS)).strftime('%Y-%m-%dT%H:%M:%SZ')
    if (app_row or {}).get('application_id'):
        payload['application_id'] = app_row['application_id']
    return 400, payload


def review_lock_self_test():
    """Prove at boot that the mandatory review gate is armed. Returns a log line."""
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = lambda **kw: (now - datetime.timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')
    officer = {'role': 'FingerprintUnit'}
    alias_officer = {'role': 'fingerprint_officer'}
    admin = {'role': 'SystemAdmin'}
    admin_alias = {'role': 'admin'}
    cases = [
        ('officer @0h blocked', {'application_id': 'X', 'created_at': stamp(hours=0)}, officer, True),
        ('officer @11.5h blocked', {'application_id': 'X', 'created_at': stamp(hours=11.5)}, officer, True),
        ('officer @13h allowed', {'application_id': 'X', 'created_at': stamp(hours=13)}, officer, False),
        ('officer, missing stamp blocked', {'application_id': 'X', 'created_at': None}, officer, True),
        ('officer, bad stamp blocked', {'application_id': 'X', 'created_at': 'not-a-date'}, officer, True),
        ('fingerprint_officer alias blocked', {'application_id': 'X', 'created_at': stamp(hours=1)}, alias_officer, True),
        ('SystemAdmin bypasses', {'application_id': 'X', 'created_at': stamp(hours=0)}, admin, False),
        ('admin alias bypasses', {'application_id': 'X', 'created_at': stamp(hours=0)}, admin_alias, False),
    ]
    failures = []
    for name, row, user, expect_rejected in cases:
        rejected = review_gate_decision(row, user) is not None
        if rejected != expect_rejected:
            failures.append(name)
    return ('review lock self-test: PASS (8/8 cases)' if not failures
            else 'review lock self-test: FAILED -> ' + ', '.join(failures))


def normalise_reason(value):
    """Return the canonical CLEARANCE_REASONS spelling for `value`, or None."""
    s = (value or '').strip()
    for reason in CLEARANCE_REASONS:
        if s.lower() == reason.lower():
            return reason
    return None


def fingerprint_review_state(app, now=None):
    """12-hour review-window state for a clearance application row.

    `review_locked` is True while `created_at + 12h` is still in the future.
    Fail-closed: a row with a missing / unparseable `created_at` cannot prove
    that the mandatory window has elapsed, so it stays locked. Admins remain
    exempt — the bypass is applied by the caller, not by this helper.
    """
    hours = FINGERPRINT_REVIEW_WINDOW_HOURS
    created = parse_stamp(app.get('created_at') if app else None)
    if created is None:
        return {'review_window_hours': hours, 'review_eligible_at': None,
                'hours_elapsed': None, 'hours_remaining': float(hours),
                'review_locked': True, 'submitted_at_missing': True,
                'submitted_at': app.get('created_at') if app else None}
    now_ts = time.time() if now is None else now
    elapsed = max(0.0, (now_ts - created) / 3600.0)
    remaining = max(0.0, hours - elapsed)
    return {
        'review_window_hours': hours,
        'submitted_at': app.get('created_at'),
        'review_eligible_at': datetime.datetime.fromtimestamp(
            created + hours * 3600, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hours_elapsed': round(elapsed, 2),
        'hours_remaining': round(remaining, 2),
        'review_locked': remaining > 0,
    }

# ---------------------------------------------------------------------------
# Role-Based Access Control (RBAC) — central definition of roles, the modules
# they are allowed to use, and any data-scoping (e.g. checkpoint location).
# ---------------------------------------------------------------------------
# Canonical role identifiers (stored in users.role and seed data).
ROLE_ADMIN = 'SystemAdmin'
ROLE_FINGERPRINT = 'FingerprintUnit'
ROLE_AIRPORT = 'AirportControl'
ROLE_CID = 'CIDUnit'
ROLE_CHECKPOINT_SOUTH = 'CheckpointSouth'
ROLE_CHECKPOINT_EAST = 'CheckpointEast'
ROLE_CHECKPOINT_WEST = 'CheckpointWest'

# Canonical normalized alias for any Checkpoint officer regardless of
# location. The spec mandates that role-checking logic accept BOTH the
# legacy compound form ('CheckpointSouth' / 'CheckpointEast' /
# 'CheckpointWest') AND the canonical normalized form
# ('checkpoint_officer'). The session payload always surfaces the
# normalized form so the frontend never has to special-case the
# compound role strings.
ROLE_CHECKPOINT_OFFICER = 'checkpoint_officer'

# Map every accepted Checkpoint-officer spelling to the normalized
# alias. /api/login, /api/me, and every module gate consult this
# alias so a token whose role is 'CheckpointSouth' is treated
# exactly like one whose role is 'checkpoint_officer'.
CHECKPOINT_ROLE_ALIASES = {
    ROLE_CHECKPOINT_SOUTH: ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_EAST: ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_WEST: ROLE_CHECKPOINT_OFFICER,
    'CheckpointSouth': ROLE_CHECKPOINT_OFFICER,
    'CheckpointEast': ROLE_CHECKPOINT_OFFICER,
    'CheckpointWest': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_south': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_east': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_west': ROLE_CHECKPOINT_OFFICER,
    'cp_south': ROLE_CHECKPOINT_OFFICER,
    'cp_east': ROLE_CHECKPOINT_OFFICER,
    'cp_west': ROLE_CHECKPOINT_OFFICER,
    'cp.south': ROLE_CHECKPOINT_OFFICER,
    'cp.east': ROLE_CHECKPOINT_OFFICER,
    'cp.west': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (South)': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (East)': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (West)': ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_OFFICER: ROLE_CHECKPOINT_OFFICER,
}

# A role is a Checkpoint officer iff:
#   - it normalises to ROLE_CHECKPOINT_OFFICER (any accepted spelling), OR
#   - it starts with 'Checkpoint' (legacy compound form), OR
#   - it includes the 'cp' / 'Checkpoint' substring (defensive against
#     future role names that follow the same family).
def is_checkpoint_role(role):
    if not role:
        return False
    r = str(role)
    if r in CHECKPOINT_ROLE_ALIASES:
        return True
    if r.lower() in CHECKPOINT_ROLE_ALIASES:
        return True
    if r.startswith('Checkpoint') or r.startswith('checkpoint'):
        return True
    if 'cp' in r.lower().split('_') or 'checkpoint' in r.lower():
        return True
    return False

def canonical_unit_role(role):
    """Resolve a unit-role alias ('admin', 'fingerprint_officer', ...) to the
    canonical stored role ('SystemAdmin', 'FingerprintUnit', ...).

    The spec refers to the reviewer roles by their snake_case names
    (`admin` / `fingerprint_officer`), so a user row stored in either
    spelling must resolve to the same canonical role everywhere —
    module gates, visibility flags, role labels and the 12-hour review
    window. Unknown roles pass through unchanged.
    """
    if not role:
        return role
    r = str(role).strip()
    if r in UNIT_ROLE_ALIASES:
        return UNIT_ROLE_ALIASES[r]
    key = _role_key(r)
    for alias, canonical in UNIT_ROLE_ALIASES.items():
        if _role_key(alias) == key:
            return canonical
    return r


def normalize_role(role):
    """Map any accepted Checkpoint-officer spelling to the canonical
    normalised form ('checkpoint_officer') and any unit alias
    ('fingerprint_officer', 'admin', ...) to its canonical role.
    All other roles pass through unchanged. This is the single source
    of truth for the spec-mandated role string normalization.
    """
    if not role:
        return role
    r = str(role)
    # Unit aliases first: 'fingerprint_officer' -> 'FingerprintUnit', ...
    canonical = canonical_unit_role(r)
    if canonical != r:
        return canonical
    if r in CHECKPOINT_ROLE_ALIASES:
        return CHECKPOINT_ROLE_ALIASES[r]
    if r.lower() in CHECKPOINT_ROLE_ALIASES:
        return CHECKPOINT_ROLE_ALIASES[r.lower()]
    # Defensive: any 'Checkpoint*' / 'checkpoint_*' / 'cp.*' spelling.
    if r.startswith('Checkpoint') and r.endswith(('South', 'East', 'West')):
        return ROLE_CHECKPOINT_OFFICER
    if r.lower().startswith('checkpoint') or 'cp' in r.lower().split('_'):
        return ROLE_CHECKPOINT_OFFICER
    return r

ALL_ROLES = (ROLE_ADMIN, ROLE_FINGERPRINT, ROLE_AIRPORT, ROLE_CID,
             ROLE_CHECKPOINT_SOUTH, ROLE_CHECKPOINT_EAST, ROLE_CHECKPOINT_WEST)

# Spec-facing snake_case name for every canonical role. Surfaced by
# /api/me as `role_alias` (and `spec_role`) so a client can key its UI off
# `fingerprint_officer` / `admin` exactly as the spec describes, while the
# stored `role` stays canonical.
SPEC_ROLE_ALIASES = {
    ROLE_ADMIN: 'admin',
    ROLE_FINGERPRINT: 'fingerprint_officer',
    ROLE_AIRPORT: 'airport_officer',
    ROLE_CID: 'cid_officer',
}
SPEC_ROLE_DEFAULT = 'fingerprint_officer'


def spec_role_for(role):
    """Snake-case spec alias for a canonical role (never defaults to admin)."""
    canonical = canonical_unit_role(role)
    if canonical in SPEC_ROLE_ALIASES:
        return SPEC_ROLE_ALIASES[canonical]
    if is_checkpoint_role(role):
        return ROLE_CHECKPOINT_OFFICER
    return SPEC_ROLE_DEFAULT

# Spec-facing / snake_case aliases for the unit roles. A user stored as
# 'fingerprint_officer' (or signed in as `admin`) must behave exactly like
# the canonical 'FingerprintUnit' / 'SystemAdmin' row: same modules, same
# RBAC gates, same role label, same 12-hour review rule.
UNIT_ROLE_ALIASES = {
    ROLE_ADMIN: ROLE_ADMIN,
    'admin': ROLE_ADMIN,
    'system_admin': ROLE_ADMIN,
    'systemadministrator': ROLE_ADMIN,
    'administrator': ROLE_ADMIN,
    ROLE_FINGERPRINT: ROLE_FINGERPRINT,
    'fingerprint_officer': ROLE_FINGERPRINT,
    'fingerprintofficer': ROLE_FINGERPRINT,
    'fingerprint_unit': ROLE_FINGERPRINT,
    'fp_officer': ROLE_FINGERPRINT,
    'fp.officer': ROLE_FINGERPRINT,
    ROLE_AIRPORT: ROLE_AIRPORT,
    'airport_officer': ROLE_AIRPORT,
    'airport_control': ROLE_AIRPORT,
    'ap_officer': ROLE_AIRPORT,
    ROLE_CID: ROLE_CID,
    'cid_officer': ROLE_CID,
    'cidunit': ROLE_CID,
    'criminal_investigation': ROLE_CID,
}

# Canonical checkpoint location codes. The data uses the short codes ('South',
# 'East', 'West') so the scoping stays in sync with existing seed data.
CHECKPOINT_LOCATIONS = ('South', 'East', 'West')

ROLE_LABELS = {
    ROLE_ADMIN: 'System Administrator',
    ROLE_FINGERPRINT: 'Fingerprint Unit Officer',
    ROLE_AIRPORT: 'Airport Control Officer',
    ROLE_CID: 'CID Criminal Unit Officer',
    ROLE_CHECKPOINT_SOUTH: 'Checkpoint Officer (South)',
    ROLE_CHECKPOINT_EAST: 'Checkpoint Officer (East)',
    ROLE_CHECKPOINT_WEST: 'Checkpoint Officer (West)',
}

# Map a role to the operational modules it is allowed to use. Admins get
# everything; unit users get their single module; checkpoint users only get
# the Checkpoint module and their own location scope.
ROLE_MODULES = {
    ROLE_ADMIN: {'dashboard', 'analytics', 'admin', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints'},
    ROLE_FINGERPRINT: {'dashboard', 'people', 'fingerprint'},
    ROLE_AIRPORT: {'dashboard', 'people', 'airport'},
    ROLE_CID: {'dashboard', 'people', 'cid'},
    ROLE_CHECKPOINT_SOUTH: {'dashboard', 'checkpoints'},
    ROLE_CHECKPOINT_EAST: {'dashboard', 'checkpoints'},
    ROLE_CHECKPOINT_WEST: {'dashboard', 'checkpoints'},
    # Spec step 1: the canonical normalized alias is also a first-class
    # role. Whether the stored role is 'CheckpointSouth' or
    # 'checkpoint_officer', the module set and scope lookup resolve to
    # the same answer.
    ROLE_CHECKPOINT_OFFICER: {'dashboard', 'checkpoints'},
}

# Map a role to the checkpoint location it is scoped to (or None for non-checkpoint roles).
ROLE_LOCATION_SCOPE = {
    ROLE_ADMIN: None,
    ROLE_FINGERPRINT: None,
    ROLE_AIRPORT: None,
    ROLE_CID: None,
    ROLE_CHECKPOINT_SOUTH: 'South',
    ROLE_CHECKPOINT_EAST: 'East',
    ROLE_CHECKPOINT_WEST: 'West',
    # Spec step 3: 'checkpoint_officer' is the canonical normalised
    # alias; its default scope is empty so the SQL filter never
    # leaks other locations. The CheckpointSouth/East/West seed
    # users keep their explicit location_scope from the users table.
    ROLE_CHECKPOINT_OFFICER: '',
}

# Every unit alias inherits the modules / scope / label of the canonical
# role it resolves to, so a row stored as 'fingerprint_officer' (or a token
# issued for 'admin') is never left with an empty module list.
for _alias, _canonical in UNIT_ROLE_ALIASES.items():
    ROLE_MODULES.setdefault(_alias, ROLE_MODULES[_canonical])
    ROLE_LOCATION_SCOPE.setdefault(_alias, ROLE_LOCATION_SCOPE[_canonical])
    ROLE_LABELS.setdefault(_alias, ROLE_LABELS[_canonical])


def canonical_location_scope(scope):
    """Map a location value ('south', 'South Checkpoint', ' SOUTH '...) to the
    canonical short code ('South' / 'East' / 'West'). Returns the trimmed
    original when it does not match any known location (callers validate)."""
    s = str(scope or '').strip()
    if not s:
        return None
    for code in CHECKPOINT_LOCATIONS:
        if s.lower() == code.lower():
            return code
    first = s.split()[0]
    for code in CHECKPOINT_LOCATIONS:
        if first.lower() == code.lower():
            return code
    return s


def normalize_incoming_role(role):
    """Normalise a role string supplied on user create/update.

    Every accepted Checkpoint-officer spelling ('CheckpointSouth',
    'checkpoint_south', 'cp_south', 'cp.east', 'Checkpoint Officer
    (West)', 'checkpoint_officer', ...) is mapped to the canonical
    'checkpoint_officer'. All other canonical roles pass through
    unchanged. Returns (canonical_role, derived_location_scope_or_None)
    — the derived scope is pulled from the alias itself ('cp_south' ->
    'South') so normalizing NEVER loses the officer's location.
    Unit aliases are canonicalised too: 'fingerprint_officer' is stored as
    'FingerprintUnit' and 'admin' as 'SystemAdmin'.
    """
    r = str(role or '').strip()
    if not r:
        return r, None
    # 'fingerprint_officer' -> 'FingerprintUnit', 'admin' -> 'SystemAdmin', ...
    canonical = canonical_unit_role(r)
    if canonical != r:
        return canonical, None
    if r in set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}:
        derived = ROLE_LOCATION_SCOPE.get(r) or None
        if is_checkpoint_role(r):
            return ROLE_CHECKPOINT_OFFICER, derived
        return r, None
    if is_checkpoint_role(r):
        derived = None
        rl = r.lower()
        for code in CHECKPOINT_LOCATIONS:
            if code.lower() in rl:
                derived = code
                break
        return ROLE_CHECKPOINT_OFFICER, derived
    return r, None


def user_view(user):
    """Return the public-facing user payload (no password hash) with RBAC info.

    Surfaces BOTH the raw stored role (e.g. 'CheckpointSouth') AND the
    normalised alias ('checkpoint_officer') so the frontend can use
    either form. The raw role is preserved in 'role' for back-compat
    (existing checks use role === 'CheckpointSouth' etc.); the
    canonical normalized form is in 'role_alias' for the spec-mandated
    unified checks.
    """
    raw_role = user.get('role') or ''
    # Spec step 1: normalise the role string. The session payload now
    # carries the canonical 'checkpoint_officer' alias as 'role_alias'
    # for any Checkpoint officer, regardless of the underlying
    # storage form.
    role_alias = normalize_role(raw_role)
    # Snake-case spec alias ('fingerprint_officer' / 'admin' / ...).
    spec_role = spec_role_for(raw_role)
    scope = user.get('location_scope') or ROLE_LOCATION_SCOPE.get(raw_role)
    # Normalise legacy/derived scope for display: checkpoint users see a
    # human-friendly location label, everyone else sees their branch.
    if raw_role.startswith('Checkpoint') and raw_role.endswith(('South', 'East', 'West')):
        location = raw_role[len('Checkpoint'):]
    else:
        location = scope or user.get('branch') or ''
    # The module set must resolve for BOTH the raw stored role AND the
    # normalised alias. Without the alias lookup a user stored as
    # 'cp_south' / 'checkpoint_officer' would get modules: [] and the
    # frontend would never fetch /api/checkpoint-events (the "0 records"
    # bug).
    modules = set(ROLE_MODULES.get(raw_role, set())) | \
        set(ROLE_MODULES.get(role_alias, set())) | \
        set(ROLE_MODULES.get(spec_role, set()))
    return {
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'role': raw_role,
        'role_alias': role_alias,
        # Spec-facing snake_case name ('fingerprint_officer', 'admin', ...).
        # Never defaults to 'admin': an unknown role is treated as a standard
        # officer, which keeps the 12-hour review lock fail-closed.
        'role_spec': spec_role,
        'spec_role': spec_role,
        'role_label': ROLE_LABELS.get(raw_role, raw_role),
        'branch': user.get('branch') or '',
        'location_scope': scope,
        'location': location,
        'modules': sorted(modules),
        'active': bool(user.get('active', 1)),
    }


def require_role(user, role):
    """Raise PermissionError unless the user's role matches."""
    if user.get('role') != role:
        raise PermissionError(f'Requires {ROLE_LABELS.get(role, role)} role')


def require_module(user, module):
    """Raise PermissionError unless the user can access the given module/page.

    Spec step 1: the module check is now also performed against the
    normalised role alias. A Checkpoint officer whose stored role is
    'CheckpointSouth' (or 'cp_south' or any other accepted spelling)
    is treated exactly like one whose role is 'checkpoint_officer'.
    """
    role = user.get('role') or ''
    # Try the raw role first, then the normalised alias — so the
    # module set is resolved for both spellings of the same logical
    # role.
    modules = ROLE_MODULES.get(role, set())
    if module in modules:
        return
    normalised = normalize_role(role)
    modules = ROLE_MODULES.get(normalised, set())
    if module in modules:
        return
    raise PermissionError(
        f'Restricted to {ROLE_LABELS.get(role, role)}')


def checkpoint_scope(user):
    """Return the location code this user is allowed to see for checkpoint data.

    Admins see all locations (None). Checkpoint users see only their own.
    Other unit users see no checkpoint data (empty string).
    """
    role = user.get('role') or ''
    if role == ROLE_ADMIN:
        return None
    # Spec step 3: prefer the stored location_scope on the user
    # record over the role-based derivation. A PATCH from
    # 'CheckpointSouth' to 'checkpoint_officer' must NOT wipe the
    # officer's location. The location_scope column is the
    # authoritative source for any Checkpoint officer.
    stored_scope = user.get('location_scope')
    if stored_scope and stored_scope in CHECKPOINT_LOCATIONS:
        return stored_scope
    # Otherwise, derive the scope from the role (legacy code path).
    aliases_to_try = [role, role.lower(), normalize_role(role)]
    for r in aliases_to_try:
        if r in ROLE_LOCATION_SCOPE:
            return ROLE_LOCATION_SCOPE[r] or ''
    # Last-ditch: if the role is a Checkpoint officer but the scope
    # lookup failed, derive the scope from the role string itself
    # ('CheckpointSouth' -> 'South', 'CheckpointEast' -> 'East',
    # 'CheckpointWest' -> 'West', 'cp_west' -> 'West', etc.).
    if is_checkpoint_role(role):
        rl = role.lower()
        for code in CHECKPOINT_LOCATIONS:
            if code.lower() in rl:
                return code
    return ''


def filter_visibility(user):
    """Small dict of RBAC booleans used by the /api/me view and frontend."""
    role = user.get('role') or ''
    # Resolve aliases first so 'admin' / 'system_admin' behave like the
    # canonical SystemAdmin row.
    is_admin = canonical_unit_role(role) == ROLE_ADMIN
    return {
        'is_admin': is_admin,
        'can_manage_users': is_admin,
        'can_view_analytics': is_admin,
        'checkpoint_scope': checkpoint_scope(user),
    }

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
        # Backfill the explicit checkpoint location metadata so the dashboard
        # and identity profile can show 'Checkpoint (South)' for legacy rows
        # where only the short 'location' code is present.
        cp_rows = c.execute(
            "SELECT id, location FROM checkpoint_events "
            "WHERE TRIM(COALESCE(location_code,''))='' OR TRIM(COALESCE(checkpoint_location,''))=''"
        ).fetchall()
        for r in cp_rows:
            short = (r['location'] or '').strip()
            if not short: continue
            # Normalise the legacy short code into a canonical short code
            # (e.g. 'South Checkpoint' -> 'South') and a friendly label.
            canonical = short if short in CHECKPOINT_LOCATIONS else short.split()[0]
            label = f'{canonical} Checkpoint'
            c.execute('UPDATE checkpoint_events SET location_code=?, checkpoint_location=? WHERE id=?',
                      (canonical, label, r['id']))
        violations = c.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Foreign key violations after migration: {violations[:3]}')
    finally:
        c.execute('PRAGMA foreign_keys=ON')

def init_db():
    c = db()
    c.executescript(SCHEMA)
    migrate(c)
    # Canonical checkpoint locations — referenced by both the data and the RBAC layer.
    if c.execute('SELECT COUNT(*) FROM locations').fetchone()[0] == 0:
        for code, label in (('South', 'South Checkpoint'),
                             ('East', 'East Checkpoint'),
                             ('West', 'West Checkpoint')):
            c.execute('INSERT INTO locations(code,label,kind) VALUES(?,?,?)',
                      (code, label, 'Checkpoint'))
    # Normalise the legacy admin account + seed a representative user per role
    # so the RBAC flow is exercised by default. The existing admin keeps its
    # password (idempotent — we only re-tag it on first run).
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        seeds = [
            ('admin',       'Officer A. Hassan',     ROLE_ADMIN,           'Central HQ',      None,                 'ChangeMe123!'),
            ('fp.officer',  'Officer H. Xasan',      ROLE_FINGERPRINT,     'Fingerprint Unit', None,                'ChangeMe123!'),
            ('ap.officer',  'Officer S. Cabdi',      ROLE_AIRPORT,         'Airport Control', None,                 'ChangeMe123!'),
            ('cid.officer', 'Officer M. Nuur',       ROLE_CID,             'CID Unit',         None,                'ChangeMe123!'),
            ('cp.south',    'Officer F. Cali',       ROLE_CHECKPOINT_SOUTH,'Checkpoint South', 'South',             'ChangeMe123!'),
            ('cp.east',     'Officer A. Maxamed',    ROLE_CHECKPOINT_EAST, 'Checkpoint East',  'East',              'ChangeMe123!'),
            ('cp.west',     'Officer N. Yuusuf',     ROLE_CHECKPOINT_WEST, 'Checkpoint West',  'West',              'ChangeMe123!'),
        ]
        for u, dn, role, branch, scope, pw in seeds:
            c.execute('INSERT INTO users(username,display_name,role,branch,location_scope,password_hash) '
                      'VALUES(?,?,?,?,?,?)',
                      (u, dn, role, branch, scope, password_hash(pw)))
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
        c.execute('''INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,flight_number,
            airline,origin_city,destination_city,route) VALUES(?,?,?,?,?,?,?,?,?)''',
                  ('AR-1001',pid,'Arrival','2026-07-18','HL-118','Sentinel Air','Berbera','Hargeisa','Berbera / Hargeisa'))
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
        c.execute("""INSERT INTO checkpoint_events(event_id,person_id,location,location_code,
            checkpoint_location,screening_result,action_taken,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                  ('CP-'+secrets.token_hex(4),susp_pid,'South','South','South Checkpoint',
                   'Flagged match','Supervisor contacted',admin_id,'2026-08-30 08:42:00'))
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

def session_token_from_cookie(handler):
    """Read the sentinel_session cookie (fallback to the Bearer header)."""
    raw = handler.headers.get('Cookie','') or ''
    for part in raw.split(';'):
        name, _, value = part.partition('=')
        if name.strip() == 'sentinel_session':
            return value.strip()
    return ''


def lookup_session(token):
    """Resolve a token from the persistent sessions table.

    Sessions used to live only in the in-memory TOKENS map, so every server
    restart invalidated every signed-in browser and /api/me started answering
    401 — which pushed the frontends into their offline fallbacks. Sessions
    are now stored in SQLite and survive a restart.
    """
    if not token:
        return None
    c = db()
    try:
        row = c.execute('SELECT user_id FROM sessions WHERE token=?', (token,)).fetchone()
    finally:
        c.close()
    return row['user_id'] if row else None


def create_session(user_id):
    """Issue a new session token (memory cache + persistent row)."""
    token = secrets.token_urlsafe(32)
    TOKENS[token] = user_id
    c = db()
    try:
        c.execute('INSERT OR REPLACE INTO sessions(token,user_id) VALUES(?,?)', (token, user_id))
        c.commit()
    finally:
        c.close()
    return token


def destroy_session(token):
    """Revoke a session (logout / stale-token cleanup)."""
    if not token:
        return
    TOKENS.pop(token, None)
    c = db()
    try:
        c.execute('DELETE FROM sessions WHERE token=?', (token,))
        c.commit()
    finally:
        c.close()


def require_auth(handler):
    token = (handler.headers.get('Authorization','') or '').replace('Bearer ','')
    if not token:
        token = session_token_from_cookie(handler)
    if not token: raise PermissionError('Authentication required')
    user_id = TOKENS.get(token)
    if not user_id:
        user_id = lookup_session(token)
        if user_id: TOKENS[token] = user_id
    if not user_id: raise PermissionError('Authentication required')
    c = db()
    user = rowdict(c.execute(
        'SELECT id,username,display_name,role,branch,location_scope,active '
        'FROM users WHERE id=? AND active=1',(user_id,)).fetchone())
    c.close()
    if not user: raise PermissionError('Authentication required')
    return user_view(user)

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
    national_id = (data.get('national_id') or '').strip().upper() or None
    passport_id = (data.get('passport_id') or '').strip().upper() or None
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

def enrich_person(c, data, person, photo_path=None):
    """Fill any empty/null central-person fields from incoming unit request data.

    Never overwrites existing non-null values. This lets an officer complete
    missing profile details (mother's name, phone, occupation, address,
    passport, photo, etc.) while recording a unit event, and enriches the
    linked Central Person record in SQLite. Returns (updated_row, changed).
    """
    updates, params = [], []
    for f in PERSON_FIELDS:
        if f == 'photo_path':
            incoming = photo_path or ''
        else:
            raw = data.get(f)
            incoming = str(raw or '').strip() if raw is not None else ''
        if f in ('national_id', 'passport_id'):
            incoming = incoming.upper()
        stored = str(person.get(f) or '').strip()
        if incoming and not stored:
            updates.append(f'{f}=?'); params.append(incoming)
    if updates:
        updates.append('updated_at=CURRENT_TIMESTAMP')
        params.append(person['id'])
        c.execute(f"UPDATE persons SET {', '.join(updates)} WHERE id=?", params)
        return rowdict(c.execute('SELECT * FROM persons WHERE id=?', (person['id'],)).fetchone()), True
    return person, False

def upsert_person(c, data, photo_path=None, allow_no_id=False):
    """Smart identity resolution + merge.

    Tier 1 (exact ID/passport) and Tier 2 (exact 4-part name + DOB) records are
    merged automatically, enriching any empty fields without overwriting
    existing non-null data; otherwise a new Central Person is created.
    Returns (row, created).
    """
    row, tier = find_by_id(c, data)
    if not row:
        row, tier, _, _ = resolve_person(c, data)
    if row and tier in (1, 2):
        row, _ = enrich_person(c, data, row, photo_path)
        return row, False
    return create_person(c, data, photo_path, allow_no_id)

def ensure_person(c, data, photo_path=None, allow_no_id=False):
    """Resolve an existing person_id or auto-create the Central Person record
    from the identity fields carried by a unit request. When a unit record links
    to an existing Central Person ID, any non-empty incoming values for fields
    that are still null/empty are used to enrich the profile (never overwriting
    existing non-null data). Returns (row, created)."""
    pid = norm(data.get('person_id'))
    if pid:
        row = rowdict(c.execute('SELECT * FROM persons WHERE person_id=?', (pid,)).fetchone())
        if row:
            row, _ = enrich_person(c, data, row, photo_path)
            return row, False
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

def build_analytics(c, user):
    """Aggregate analytics for the Executive Dashboard (admin only)."""
    # --- 1) Operational summary metrics ----------------------------------
    total_persons = c.execute('SELECT COUNT(*) FROM persons').fetchone()[0]
    active_alerts = c.execute(
        "SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0]
    airport_records = c.execute('SELECT COUNT(*) FROM airport_passengers').fetchone()[0]
    fingerprint_records = c.execute('SELECT COUNT(*) FROM clearance_applications').fetchone()[0]
    case_total = c.execute('SELECT COUNT(*) FROM crime_cases').fetchone()[0]
    open_cases = c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0]
    checkpoint_total = c.execute('SELECT COUNT(*) FROM checkpoint_events').fetchone()[0]
    checkpoint_flagged = c.execute(
        "SELECT COUNT(*) FROM checkpoint_events WHERE screening_result='Flagged match'").fetchone()[0]
    summary = {
        'total_central_persons': total_persons,
        'active_suspect_alerts': active_alerts,
        'airport_movements': airport_records,
        'fingerprint_records': fingerprint_records,
        'crime_cases_total': case_total,
        'crime_cases_open': open_cases,
        'checkpoint_events': checkpoint_total,
        'checkpoint_flagged': checkpoint_flagged,
    }

    # --- 2) Crime distribution by location and time-of-day bucket --------
    # "location" of a crime is the location stored on the crime_cases row.
    # time-of-day is bucketed from the created_at timestamp (24h clock).
    crime_rows = c.execute(
        "SELECT location, created_at FROM crime_cases").fetchall()
    by_location = {}
    by_time = {'Morning (06-12)': 0, 'Afternoon (12-18)': 0,
               'Evening (18-24)': 0, 'Night (00-06)': 0}
    for r in crime_rows:
        loc = (r['location'] or 'Unspecified').strip() or 'Unspecified'
        by_location[loc] = by_location.get(loc, 0) + 1
        # created_at is a SQLite 'YYYY-MM-DD HH:MM:SS' string
        ts = (r['created_at'] or '').strip()
        hour = None
        if len(ts) >= 13 and ts[11:13].isdigit():
            hour = int(ts[11:13])
        if hour is None:
            bucket = 'Unspecified'
        elif 6 <= hour < 12:
            bucket = 'Morning (06-12)'
        elif 12 <= hour < 18:
            bucket = 'Afternoon (12-18)'
        elif 18 <= hour < 24:
            bucket = 'Evening (18-24)'
        else:
            bucket = 'Night (00-06)'
        by_time[bucket] = by_time.get(bucket, 0) + 1
    # Pad the matrix so the dashboard has stable axes.
    location_order = sorted(by_location.items(), key=lambda x: -x[1])
    crime_distribution = {
        'by_location': [{'label': k, 'count': v} for k, v in location_order],
        'by_time_of_day': [{'label': k, 'count': by_time.get(k, 0)} for k in
                            ('Morning (06-12)', 'Afternoon (12-18)',
                             'Evening (18-24)', 'Night (00-06)')],
    }

    # --- 3) Checkpoint volume by location and traveler demographics ------
    # Travelers link to a central person; we use the stored date_of_birth
    # to bucket their age at the time of travel.
    def age_to_bucket(age):
        if age is None: return 'Unknown'
        if age < 18: return '<18'
        if age <= 30: return '18-30'
        if age <= 50: return '31-50'
        return '50+'
    today = time.gmtime()
    current_year = today.tm_year
    by_loc = {code: 0 for code in CHECKPOINT_LOCATIONS}
    by_loc_age = {code: {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0}
                  for code in CHECKPOINT_LOCATIONS}
    rows = c.execute('''SELECT ce.location, p.date_of_birth
        FROM checkpoint_events ce JOIN persons p ON p.id=ce.person_id''').fetchall()
    for r in rows:
        loc = (r['location'] or '').strip()
        if loc not in by_loc:
            by_loc[loc] = 0
            by_loc_age[loc] = {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0}
        by_loc[loc] = by_loc.get(loc, 0) + 1
        dob = (r['date_of_birth'] or '').strip()
        age = None
        if len(dob) >= 4 and dob[:4].isdigit():
            age = current_year - int(dob[:4])
        bucket = age_to_bucket(age)
        by_loc_age.setdefault(loc, {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0})
        by_loc_age[loc][bucket] = by_loc_age[loc].get(bucket, 0) + 1
    volume = {
        'by_location': [{'label': k, 'count': by_loc.get(k, 0)} for k in CHECKPOINT_LOCATIONS],
        'demographics': {loc: [{'label': k, 'count': v.get(k, 0)} for k in
                                ('<18', '18-30', '31-50', '50+', 'Unknown')]
                         for loc, v in by_loc_age.items()},
    }

    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', today),
        'summary': summary,
        'crime_distribution': crime_distribution,
        'checkpoint_volume': volume,
    }


def build_dashboard(c, user):
    """Role- and location-scoped operations dashboard payload.

    Returns a single JSON envelope the frontend renders as KPI cards,
    quick-action buttons, and a real-time activity feed. Every field
    is filtered to the caller's modules and (for Checkpoint users)
    their assigned location scope, so the dashboard can never leak
    metrics for a unit or location the officer is not authorised to
    see.

    Each unit role receives a tailored set of mini-analytics that
    summarise their specific operational responsibilities (e.g.
    'Peak Travel Hour' for Checkpoint officers, 'Open investigation
    cases' for CID, 'Today's passenger movements' for Airport). The
    activity feed is enriched with the actual screened-person /
    traveller / suspect name and a human-friendly "N mins ago" stamp
    so the real-time feed reads like a live operations log.

    Spec step 2: the dashboard ALWAYS returns HTTP 200 for any
    authenticated user — no 404, no role-rejection. The response
    payload surfaces BOTH the role-specific cards AND the spec's
    mandated alias keys (screenings_today, travelers_flagged,
    total_travelers, peak_travel_hour, activity_feed) for Checkpoint
    officers so any frontend that reads those flat keys still works.
    """
    role = (user.get('role') or '') if user else ''
    is_admin = (role == ROLE_ADMIN)
    # Spec step 1: normalise the role string. A token whose role is
    # 'CheckpointSouth' (or 'cp_south' or 'checkpoint_officer') is
    # treated exactly like the canonical normalised form for the
    # downstream branching below.
    role_alias = normalize_role(role)
    scope = checkpoint_scope(user) if user else None
    now_ts = time.time()
    today = time.strftime('%Y-%m-%d', time.gmtime(now_ts))
    # Spec step 1: is_checkpoint now also recognises every accepted
    # Checkpoint-officer spelling — 'CheckpointSouth',
    # 'CheckpointEast', 'CheckpointWest', 'checkpoint_officer', and
    # any other accepted alias. The role_alias doubles as a safety
    # net: even if the stored role string drifts in the future, as
    # long as it normalises to ROLE_CHECKPOINT_OFFICER this branch
    # fires correctly.
    is_checkpoint = bool(role and (
        role in (ROLE_CHECKPOINT_SOUTH, ROLE_CHECKPOINT_EAST, ROLE_CHECKPOINT_WEST)
        or role_alias == ROLE_CHECKPOINT_OFFICER
    ))

    def cp_scope_sql():
        """Flexible case-insensitive match against any of the four
        location columns so a row that was just saved with the friendly
        checkpoint label is returned in the very next poll even if
        `location_code` was not populated. Adds a LIKE '%scope%'
        fallback so any trailing space, casing, or punctuation variation
        in 'location' / 'checkpoint_location' is still caught.
        """
        if not scope: return ("", ())
        sql = ("WHERE (LOWER(TRIM(COALESCE(ce.location_code,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.location,''))) LIKE ? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,''))) LIKE ?)")
        return (sql, (scope.lower(), scope.lower(), f"{scope.lower()} checkpoint",
                      scope.lower(), f"%{scope.lower()}%", f"%{scope.lower()}%"))

    # ---- KPI cards (mini-analytics) ---------------------------------------
    cards = []
    if is_admin:
        cards.extend(_admin_dashboard_cards(c))
    elif is_checkpoint:
        cards.extend(_checkpoint_dashboard_cards(c, scope, today, cp_scope_sql))
    elif role == ROLE_FINGERPRINT or role_alias == ROLE_FINGERPRINT:
        cards.extend(_fingerprint_dashboard_cards(c, today))
    elif role == ROLE_AIRPORT or role_alias == ROLE_AIRPORT:
        cards.extend(_airport_dashboard_cards(c, today))
    elif role == ROLE_CID or role_alias == ROLE_CID:
        cards.extend(_cid_dashboard_cards(c, today))
    else:
        # Spec step 2: a token whose role is not one of the canonical
        # units still gets an empty-but-valid dashboard so the
        # endpoint NEVER 404s. The frontend can render an empty state
        # instead of a "Not Found" placeholder.
        cards = []

    # ---- Quick-registration buttons ----------------------------------------
    quick = []
    if is_admin or role == ROLE_AIRPORT or role_alias == ROLE_AIRPORT:
        quick.append({'id':'add_airport','label':'+ Airport passenger','kind':'primary','page':'airport','module':'airport'})
    if is_admin or role == ROLE_FINGERPRINT or role_alias == ROLE_FINGERPRINT:
        quick.append({'id':'add_clearance','label':'+ Clearance application','kind':'secondary','page':'fingerprint','module':'fingerprint'})
    if is_admin or role == ROLE_CID or role_alias == ROLE_CID:
        quick.append({'id':'add_case','label':'+ New crime case','kind':'secondary','page':'cid','module':'cid'})
    if is_admin or is_checkpoint:
        quick.append({'id':'add_checkpoint','label':'+ Record checkpoint stop','kind':'primary','page':'checkpoints','module':'checkpoints'})

    # ---- Real-time activity stream (filtered to the user's scope) ---------
    events = _build_activity_feed(c, role, is_admin, scope, is_checkpoint, now_ts, cp_scope_sql)

    # ---- Spec step 2 alias keys --------------------------------------------
    # The spec's mandated top-level keys for the Checkpoint-officer
    # dashboard (screenings_today, travelers_flagged,
    # total_travelers, peak_travel_hour, activity_feed) are also
    # surfaced as flat top-level fields. Any frontend that reads
    # those keys (instead of cards[].id) works out of the box.
    screenings_today = 0
    travelers_flagged = 0
    total_travelers = 0
    peak_travel_hour = '—'
    if is_checkpoint:
        for card in cards:
            if card.get('id') == 'cp_screenings_today':
                screenings_today = card.get('value', 0)
            elif card.get('id') == 'cp_travelers_flagged':
                travelers_flagged = card.get('value', 0)
            elif card.get('id') == 'cp_total_travelers':
                total_travelers = card.get('value', 0)
            elif card.get('id') == 'cp_peak_hour':
                peak_travel_hour = card.get('value', '—')

    # Spec step 1: also surface the modules list under the
    # normalized role so the frontend can gate on either form.
    modules_raw = sorted(ROLE_MODULES.get(role, set()))
    modules_alias = sorted(ROLE_MODULES.get(role_alias, set()))
    modules = sorted(set(modules_raw) | set(modules_alias))

    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ts)),
        'role': role,
        'role_alias': role_alias,
        'is_admin': is_admin,
        'location_scope': scope,
        'modules': modules,
        'cards': cards,
        'quick_actions': quick,
        'activity': events,
        'stream': events[:8],
        # Spec step 2: alias keys at the top level for Checkpoint
        # officers (and zeroed for other roles so the keys exist).
        'screenings_today': screenings_today,
        'travelers_flagged': travelers_flagged,
        'total_travelers': total_travelers,
        'peak_travel_hour': peak_travel_hour,
        'activity_feed': events,
        'subhead': (
            'System overview · all units' if is_admin else
            (f'{scope} Checkpoint operations · live' if is_checkpoint else
             f'{ROLE_LABELS.get(role, role)} · live operations feed')
        ),
    }


def _admin_dashboard_cards(c):
    return [
        {'id':'central_persons','label':'Central persons','icon':'◉',
         'value':c.execute('SELECT COUNT(*) FROM persons').fetchone()[0],
         'trend':'Unified identity records','module':'people'},
        {'id':'open_cases','label':'Open crime cases','icon':'⌂',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0],
         'trend':'Active investigations','module':'cid'},
        {'id':'pending_clearances','label':'Pending clearances','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Pending Review'").fetchone()[0],
         'trend':'Require officer review','module':'fingerprint'},
        {'id':'active_alerts','label':'Active suspect alerts','icon':'!',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0],
         'trend':'Restricted operational data','trend_kind':'alert','module':'cid'},
    ]


def _checkpoint_dashboard_cards(c, scope, today, cp_scope_sql):
    """Tailored mini-analytics for Checkpoint South / East / West officers.

    4 compact stat cards, all filtered to the officer's assigned
    location: 'Screenings today', 'Travelers flagged', 'Total
    location travelers', and 'Peak travel hour' (the 2-hour bucket
    with the most events in the last 7 days).
    """
    cards = []
    filter_sql, filter_args = cp_scope_sql()
    # If the officer has no scope (shouldn't happen for checkpoint users),
    # fall back to the most permissive filter so the cards still render
    # rather than throwing a 500.
    if not filter_sql:
        filter_sql, filter_args = "WHERE 1=1", ()

    screenings_today = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql} "
        f"AND substr(ce.created_at,1,10)=?",
        (*filter_args, today)).fetchone()[0]
    flagged_today = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql} "
        f"AND ce.screening_result='Flagged match' "
        f"AND substr(ce.created_at,1,10)=?",
        (*filter_args, today)).fetchone()[0]
    total_local = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql}", filter_args).fetchone()[0]
    unique_travelers = c.execute(
        f"SELECT COUNT(DISTINCT ce.person_id) FROM checkpoint_events ce {filter_sql}",
        filter_args).fetchone()[0]

    # Peak travel hour — bucket created_at into 2-hour slices for the
    # last 7 days. SQLite has no native date arithmetic on TEXT so we
    # use a LIKE prefix on the YYYY-MM-DD portion.
    seven_days_ago = time.strftime('%Y-%m-%d', time.gmtime(time.time() - 7 * 86400))
    peak_row = c.execute(
        f"SELECT substr(ce.created_at,12,2) AS hh, COUNT(*) AS n "
        f"FROM checkpoint_events ce {filter_sql} "
        f"AND substr(ce.created_at,1,10) >= ? "
        f"GROUP BY hh ORDER BY n DESC, hh ASC LIMIT 1",
        (*filter_args, seven_days_ago)).fetchone()
    if peak_row and peak_row['hh']:
        hh = int(peak_row['hh'])
        bucket_end = (hh + 2) % 24
        peak_label = f'{hh:02d}:00 – {bucket_end:02d}:00'
        peak_value = peak_row['n']
    else:
        peak_label = '—'
        peak_value = 0

    cards.append({
        'id': 'cp_screenings_today',
        'label': f'{scope} · screenings today',
        'icon': '⊙',
        'value': screenings_today,
        'trend': f'Stops recorded at {scope} Checkpoint · {today}',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_screenings_today',
    })
    cards.append({
        'id': 'cp_travelers_flagged',
        'label': f'{scope} · travelers flagged',
        'icon': '!',
        'value': flagged_today,
        'trend': f'Flagged matches at {scope} Checkpoint today',
        'trend_kind': 'alert',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_travelers_flagged',
    })
    cards.append({
        'id': 'cp_total_travelers',
        'label': f'{scope} · total travelers',
        'icon': '◉',
        'value': unique_travelers,
        'trend': f'Distinct Central Persons screened at {scope} · {total_local} screening(s)',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_total_travelers',
    })
    cards.append({
        'id': 'cp_peak_hour',
        'label': f'{scope} · peak travel hour',
        'icon': '⌁',
        'value': peak_label,
        'trend': f'{peak_value} stop(s) in the last 7 days',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_peak_hour',
    })
    return cards


def _fingerprint_dashboard_cards(c, today):
    return [
        {'id':'fp_pending','label':'Pending clearances','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Pending Review'").fetchone()[0],
         'trend':'Require officer review','module':'fingerprint'},
        {'id':'fp_today','label':'Applications today','icon':'◉',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
         'trend':f'New intake · {today}','module':'fingerprint'},
        {'id':'fp_approved','label':'Approved clearances','icon':'✓',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Approved'").fetchone()[0],
         'trend':'Certificates issued','module':'fingerprint'},
        {'id':'fp_total','label':'Total applications','icon':'⌂',
         'value':c.execute('SELECT COUNT(*) FROM clearance_applications').fetchone()[0],
         'trend':'All-time clearance volume','module':'fingerprint'},
    ]


def _airport_dashboard_cards(c, today):
    total = c.execute('SELECT COUNT(*) FROM airport_passengers').fetchone()[0]
    arrivals = c.execute("SELECT COUNT(*) FROM airport_passengers WHERE movement='Arrival'").fetchone()[0]
    departures = c.execute("SELECT COUNT(*) FROM airport_passengers WHERE movement='Departure'").fetchone()[0]
    today_movements = c.execute(
        "SELECT COUNT(*) FROM airport_passengers WHERE travel_date=?", (today,)).fetchone()[0]
    return [
        {'id':'ap_today','label':'Movements today','icon':'✈',
         'value':today_movements,'trend':f'Travel date {today}','module':'airport'},
        {'id':'ap_arrivals','label':'Arrivals (all-time)','icon':'↓',
         'value':arrivals,'trend':'Inbound movements on register','module':'airport'},
        {'id':'ap_departures','label':'Departures (all-time)','icon':'↑',
         'value':departures,'trend':'Outbound movements on register','module':'airport'},
        {'id':'ap_total','label':'Total movements','icon':'◉',
         'value':total,'trend':'All-time passenger register','module':'airport'},
    ]


def _cid_dashboard_cards(c, today):
    return [
        {'id':'cid_open','label':'Open crime cases','icon':'⌂',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0],
         'trend':'Active investigations','module':'cid'},
        {'id':'cid_active_alerts','label':'Active suspect alerts','icon':'!',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0],
         'trend':'Restricted operational data','trend_kind':'alert','module':'cid'},
        {'id':'cid_cases_today','label':'Cases reported today','icon':'◉',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
         'trend':f'New intake · {today}','module':'cid'},
        {'id':'cid_suspects','label':'Suspects on file','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect'").fetchone()[0],
         'trend':'All-time suspect listings','module':'cid'},
    ]


def _time_ago(iso_ts, now_ts):
    """Best-effort "N mins ago" formatter for the live activity feed.

    Accepts SQLite CURRENT_TIMESTAMP-style strings ("YYYY-MM-DD HH:MM:SS")
    or date-only strings ("YYYY-MM-DD"). Returns '' on parse failure.
    """
    if not iso_ts:
        return ''
    s = str(iso_ts).strip().replace('T', ' ')
    try:
        if len(s) >= 19 and s[10] == ' ':
            tm = time.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
        elif len(s) == 10:
            tm = time.strptime(s + ' 12:00:00', '%Y-%m-%d %H:%M:%S')
        else:
            return ''
        ts = time.mktime(tm)
    except Exception:
        return ''
    delta = max(0, int(now_ts - ts))
    if delta < 60: return 'just now'
    if delta < 3600: return f'{delta // 60} min ago'
    if delta < 86400: return f'{delta // 3600} hr ago'
    return f'{delta // 86400} d ago'


def _build_activity_feed(c, role, is_admin, scope, is_checkpoint, now_ts, cp_scope_sql):
    """Build the real-time activity stream for the dashboard.

    Each entry is a dict with:
      module       'fingerprint' | 'airport' | 'cid' | 'checkpoints'
      kind         short identifier
      id           record id
      title        human-friendly headline (e.g. 'Screened Jama Abdi')
      subtitle     status / location context
      at           raw ISO-ish timestamp
      time_ago     formatted 'N mins ago' string
      dot_color    'blue' | 'cyan' | 'amber' | 'green' | 'red'
      location_code  (checkpoint only) 'South' / 'East' / 'West'
    """
    events = []

    if is_admin or role == ROLE_FINGERPRINT:
        for r in c.execute('''SELECT a.application_id AS id, a.purpose AS title,
            a.status AS subtitle, a.created_at AS at,
            p.full_name AS person_name
            FROM clearance_applications a
            JOIN persons p ON p.id=a.person_id
            ORDER BY a.id DESC LIMIT 8''').fetchall():
            name = r['person_name'] or 'applicant'
            events.append({
                'module': 'fingerprint',
                'kind': 'clearance',
                'id': r['id'],
                'title': f'Clearance · {name}',
                'subtitle': f'{r["title"]} · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'blue',
            })

    if is_admin or role == ROLE_AIRPORT:
        for r in c.execute('''SELECT a.record_id AS id, a.route AS route,
            a.movement AS movement, a.travel_date AS at,
            p.full_name AS person_name
            FROM airport_passengers a
            JOIN persons p ON p.id=a.person_id
            ORDER BY a.id DESC LIMIT 8''').fetchall():
            name = r['person_name'] or 'traveller'
            events.append({
                'module': 'airport',
                'kind': 'airport',
                'id': r['id'],
                'title': f'{r["movement"]} · {name}',
                'subtitle': r['route'] or '',
                'at': r['at'] or '',
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'cyan',
            })

    if is_admin or role == ROLE_CID:
        for r in c.execute('''SELECT cc.case_id AS id, cc.category AS title,
            cc.status AS subtitle, cc.created_at AS at
            FROM crime_cases cc ORDER BY cc.id DESC LIMIT 8''').fetchall():
            events.append({
                'module': 'cid',
                'kind': 'case',
                'id': r['id'],
                'title': f'Case · {r["title"]}',
                'subtitle': f'CID · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'amber',
            })

    if is_admin or is_checkpoint:
        cp_filter, cp_args = cp_scope_sql()
        for r in c.execute(
            f"SELECT ce.event_id AS id, ce.checkpoint_location AS location_label, "
            f"ce.location_code, ce.screening_result AS subtitle, ce.created_at AS at, "
            f"ce.action_taken, "
            f"p.full_name AS person_name, p.person_id AS person_code "
            f"FROM checkpoint_events ce JOIN persons p ON p.id=ce.person_id "
            f"{cp_filter} ORDER BY ce.id DESC LIMIT 10",
            cp_args).fetchall():
            loc_label = r['location_label'] or (f"{(r['location_code'] or '')} Checkpoint" if r['location_code'] else 'Checkpoint')
            name = r['person_name'] or r['person_code'] or 'traveller'
            verb = 'Flagged' if r['subtitle'] == 'Flagged match' else 'Screened'
            events.append({
                'module': 'checkpoints',
                'kind': 'checkpoint',
                'id': r['id'],
                'title': f'{verb} {name}',
                'subtitle': f'{loc_label} · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'red' if r['subtitle'] == 'Flagged match' else 'green',
                'location_code': r['location_code'],
            })

    events.sort(key=lambda e: e.get('at') or '', reverse=True)
    return events[:16]


class API(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print('%s - %s' % (self.address_string(), fmt % args))

    def send_json(self, status, data, extra_headers=None):
        out = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(out)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods','GET, POST, PATCH, OPTIONS')
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers(); self.wfile.write(out)

    def send_file(self, path, ctype):
        try:
            with open(path,'rb') as f: data = f.read()
        except OSError:
            self.send_json(404, {'error':'Not found'}); return
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        # Development server: never let a browser serve a stale copy of a
        # template (the printable pages are edited frequently and a cached
        # application.html shows an outdated layout).
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.end_headers(); self.wfile.write(data)
        # Truthy => the caller (serve_static) stops and does NOT fall through
        # to the JSON API, which would append a second response to the body.
        return True

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
        # Brand assets for the printable templates — the police emblem used as
        # both the letterhead logo and the page watermark. '/static/images/x'
        # and '/images/x' resolve to the project-root images/ folder.
        for prefix in ('/images/', '/static/images/'):
            if p.path.startswith(prefix):
                rel = os.path.normpath(p.path[len(prefix):]).lstrip('/\\')
                if rel.startswith('..') or os.path.isabs(rel):
                    self.send_json(404, {'error':'Not found'}); return True
                ext = os.path.splitext(rel)[1].lower()
                ctype = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
                         '.gif':'image/gif','.webp':'image/webp','.svg':'image/svg+xml'}.get(ext,'application/octet-stream')
                return self.send_file(os.path.join(PROJECT_ROOT, 'images', rel), ctype)
        return None

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        if self.serve_static(self.path) is not None: return
        c = None
        try:
            p = urlparse(self.path)
            # /api/fingerprint/applications* is served by the clearance handlers.
            if canonical_api_path(p.path) != p.path:
                p = p._replace(path=canonical_api_path(p.path))
            if p.path == '/api/health':
                # The build marker lets an operator confirm at a glance that
                # the running process really is the build with the 12-hour
                # fingerprint review lock (a stale process is the usual cause
                # of "the fix did not take effect").
                return self.send_json(200, {'status':'ok','service':'sentinel-backend',
                                            'database':'sqlite-development',
                                            'build':BUILD_TAG,
                                            'fingerprint_review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                                            'clearance_reasons':list(CLEARANCE_REASONS)})
            user = require_auth(self); c = db()
            # RBAC module-gating. Every authenticated user can see /api/me and
            # the central /api/persons registry, but each unit endpoint is
            # restricted to the roles that operate that module.
            module_for_path = {
                '/api/airport-records': 'airport',
                '/api/clearance-applications': 'fingerprint',
                '/api/fingerprint/applications': 'fingerprint',
                '/api/crime-cases': 'cid',
                '/api/suspect-alerts': 'cid',
                '/api/checkpoint-events': 'checkpoints',
                '/api/admin/users': 'admin',
                '/api/admin/analytics': 'analytics',
            }
            base = '/' + p.path.split('/')[1] + '/' + (p.path.split('/')[2] if len(p.path.split('/')) > 2 else '')
            for prefix, mod in module_for_path.items():
                if p.path == prefix or p.path.startswith(prefix + '/'):
                    require_module(user, mod)
                    break
            if p.path == '/api/me':
                result = {**user, 'visibility': filter_visibility(user),
                          'roles': list(ALL_ROLES),
                          'role_labels': ROLE_LABELS,
                          'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
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
                person['checkpoints'] = [dict(r) for r in c.execute('''SELECT event_id,location,location_code,checkpoint_location,
                    screening_result,action_taken,notes,created_at
                    FROM checkpoint_events WHERE person_id=? ORDER BY id DESC''',(person['id'],)).fetchall()]
                result = person
            elif p.path == '/api/airport-records':
                rows = c.execute('''SELECT a.record_id,a.movement,a.travel_date,a.flight_number,a.airline,
                    a.origin_city,a.destination_city,a.route,a.notes,
                    p.person_id,p.full_name,p.national_id FROM airport_passengers a
                    JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/clearance-applications':
                rows = c.execute('''SELECT a.application_id,a.purpose,a.status,a.certificate_number,a.created_at,
                    a.guardian_name,p.person_id,p.full_name,p.national_id,p.passport_id,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                items = []
                for r in rows:
                    item = rowdict(r)
                    # 12-hour mandatory review window — admins bypass it, so
                    # `can_approve` is resolved per caller.
                    item['review'] = fingerprint_review_state(item)
                    item['can_approve'] = bool(is_admin_user(user) or not item['review']['review_locked'])
                    items.append(item)
                result = {'items': items, 'review_window_hours': FINGERPRINT_REVIEW_WINDOW_HOURS}
            elif p.path.startswith('/api/clearance-applications/'):
                aid = p.path.split('/')[3]
                a = rowdict(c.execute('''SELECT a.*,p.full_name,p.national_id,p.date_of_birth,p.mother_name,
                    p.place_of_birth,p.residence,p.occupation,p.passport_id,p.photo_path,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id
                    WHERE a.application_id=?''',(aid,)).fetchone())
                if not a: self.send_json(404,{'error':'Application not found'}); c.close(); return
                # 12-hour mandatory review window metadata for the printable page.
                a['review'] = fingerprint_review_state(a)
                a['can_approve'] = bool(is_admin_user(user) or not a['review']['review_locked'])
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
            elif p.path == '/api/admin/users' or p.path.startswith('/api/admin/users/'):
                if p.path == '/api/admin/users':
                    rows = c.execute('''SELECT id,username,display_name,role,branch,location_scope,active
                        FROM users ORDER BY id ASC''').fetchall()
                    result = {'items':[user_view(rowdict(r)) for r in rows],
                              'roles': list(ALL_ROLES),
                              'role_labels': ROLE_LABELS,
                              'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
                else:
                    uid = p.path.split('/')[4]
                    if not uid or not uid.isdigit():
                        self.send_json(400, {'error': 'user id required'}); c.close(); return
                    row = c.execute('''SELECT id,username,display_name,role,branch,location_scope,active
                        FROM users WHERE id=?''', (int(uid),)).fetchone()
                    if not row: self.send_json(404, {'error': 'User not found'}); c.close(); return
                    result = {'user': user_view(rowdict(row)),
                              'roles': list(ALL_ROLES),
                              'role_labels': ROLE_LABELS,
                              'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
            elif p.path == '/api/admin/analytics':
                # Aggregate analytics — admin only (module gate above).
                result = build_analytics(c, user)
            elif p.path == '/api/dashboard' or p.path.startswith('/api/dashboard/'):
                # Role- and location-scoped operations dashboard. Every
                # authenticated user can call this; the response is filtered
                # to the modules / location scope their role can access.
                # The route is a prefix-match so any trailing path (e.g.
                # /api/dashboard/, /api/dashboard/refresh) is accepted and
                # never returns 404 — guards against router regressions on
                # the frontend.
                try:
                    result = build_dashboard(c, user)
                except Exception as e:
                    # Defensive: never let a transient query error make the
                    # dashboard unreachable. Fall back to an empty payload so
                    # the frontend can still render its offline view.
                    r_role = (user.get('role') or '') if user else ''
                    result = {
                        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'role': r_role,
                        'role_alias': normalize_role(r_role) if user else '',
                        'is_admin': (r_role == ROLE_ADMIN),
                        'location_scope': checkpoint_scope(user) if user else None,
                        'modules': sorted(ROLE_MODULES.get(r_role, set())),
                        'cards': [],
                        'quick_actions': [],
                        'activity': [],
                        'stream': [],
                        # Spec step 2 alias keys — always present even in degraded mode.
                        'screenings_today': 0,
                        'travelers_flagged': 0,
                        'total_travelers': 0,
                        'peak_travel_hour': '—',
                        'activity_feed': [],
                        'subhead': 'Dashboard temporarily unavailable',
                        'degraded': True,
                        'degraded_reason': str(e),
                    }
            elif p.path == '/api/suspect-alerts':
                rows = c.execute('''SELECT sa.alert_id,sa.role,sa.alert_status,sa.origin,sa.notes,
                    cc.case_id,cc.category,cc.status AS case_status,
                    p.person_id,p.full_name,p.national_id,p.passport_id FROM suspect_alerts sa
                    JOIN persons p ON p.id=sa.person_id
                    LEFT JOIN crime_cases cc ON cc.id=sa.case_id
                    ORDER BY sa.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/checkpoint-events':
                # RBAC: Checkpoint users only see events at their own location.
                # Admins see all; non-checkpoint users see all but the frontend
                # won't render the page for them either.
                #
                # The scope filter is matched flexibly against every
                # location-related column so a row that was just saved with
                # the friendly checkpoint label ('South Checkpoint') is
                # returned in the very next poll even if 'location_code' was
                # not populated. The match is also case-insensitive (LOWER
                # on both sides) and uses a LIKE '%south%' fallback so any
                # trailing space, casing, or punctuation variation in
                # 'location' / 'checkpoint_location' is still caught.
                scope = checkpoint_scope(user)
                base_cols = '''ce.event_id,ce.location,ce.location_code,ce.checkpoint_location,
                    ce.screening_result,ce.action_taken,ce.notes,ce.created_at,
                    ce.purpose_of_visit,ce.current_address,ce.permanent_address,
                    ce.traveler_photo,ce.traveler_docs,ce.guardian_person_id,ce.guardian_name,
                    ce.guardian_relationship,ce.guardian_phone,ce.guardian_address,ce.guardian_occupation,
                    ce.guardian_national_id,ce.guardian_passport_id,ce.guardian_docs,
                    p.person_id,p.full_name,p.national_id,p.passport_id'''
                if scope:
                    # Case-insensitive match against all four location columns
                    # plus a LIKE '%scope%' fallback. The OR-clause catches
                    # any combination the data layer might have written
                    # (short code, friendly label, or trailing spaces).
                    rows = c.execute(
                        f"SELECT {base_cols} FROM checkpoint_events ce "
                        f"JOIN persons p ON p.id=ce.person_id "
                        f"WHERE (LOWER(TRIM(COALESCE(ce.location_code,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.location,''))) LIKE ? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,''))) LIKE ?) "
                        f"ORDER BY ce.id DESC",
                        (scope.lower(), scope.lower(), f"{scope.lower()} checkpoint",
                         scope.lower(), f"%{scope.lower()}%", f"%{scope.lower()}%")).fetchall()
                else:
                    rows = c.execute(f"SELECT {base_cols} FROM checkpoint_events ce "
                                     f"JOIN persons p ON p.id=ce.person_id ORDER BY ce.id DESC").fetchall()
                # Surface the explicit location metadata in every response item
                # so the frontend can render the friendly label without re-deriving it.
                items = []
                for r in rows:
                    item = rowdict(r)
                    if not item.get('location_code'):
                        item['location_code'] = (item.get('location') or '').split()[0] or None
                    if not item.get('checkpoint_location') and item.get('location_code'):
                        item['checkpoint_location'] = f"{item['location_code']} Checkpoint"
                    items.append(item)
                result = {'items': items,
                          'scope': scope,
                          'visible_locations': [scope] if scope else list(CHECKPOINT_LOCATIONS)}
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
            # /api/fingerprint/applications* is handled by the clearance routes.
            if canonical_api_path(p.path) != p.path:
                p = p._replace(path=canonical_api_path(p.path))
            if p.path == '/api/login':
                data = body_json(self); c = db()
                u = c.execute('SELECT * FROM users WHERE username=? AND password_hash=? AND active=1',
                              (data.get('username'), password_hash(data.get('password','')))).fetchone(); c.close()
                if not u: self.send_json(401,{'error':'Invalid username or password'}); return
                # Persistent session: the token survives a server restart, so
                # /api/me keeps answering 200 for a signed-in officer.
                token = create_session(u['id'])
                self.send_json(200,{'token':token,'user':user_view(rowdict(u))},
                               extra_headers=[('Set-Cookie',
                                               f'sentinel_session={token}; Path=/; HttpOnly; SameSite=Lax')])
                return
            if p.path == '/api/logout':
                # Revoke the session (both transports) so the client is forced
                # into a clean re-login instead of a broken offline state.
                token = (self.headers.get('Authorization','') or '').replace('Bearer ','') \
                    or session_token_from_cookie(self)
                destroy_session(token)
                self.send_json(200, {'ok': True},
                               extra_headers=[('Set-Cookie',
                                               'sentinel_session=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax')])
                return
            user = require_auth(self); c = db()
            # RBAC: same module gate for the POST/PATCH handlers.
            post_module_for_path = {
                '/api/airport-records': 'airport',
                '/api/clearance-applications': 'fingerprint',
                '/api/fingerprint/applications': 'fingerprint',
                '/api/crime-cases': 'cid',
                '/api/suspect-alerts': 'cid',
                '/api/checkpoint-events': 'checkpoints',
                '/api/admin/users': 'admin',
            }
            for prefix, mod in post_module_for_path.items():
                if p.path == prefix or p.path.startswith(prefix + '/'):
                    require_module(user, mod)
                    break
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
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'airport register filled missing details')
                origin = (data.get('origin_city') or data.get('origin') or '').strip()
                destination = (data.get('destination_city') or data.get('destination') or '').strip()
                route = (data.get('route') or '').strip()
                if not route and (origin or destination):
                    route = (origin + ' / ' + destination) if origin and destination else (origin or destination)
                rid = 'AR-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,
                    flight_number,airline,origin_city,destination_city,route,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid,person['id'],data.get('movement','Arrival'),data.get('travel_date',''),
                     data.get('flight_number',''),data.get('airline',''),origin,destination,
                     route,data.get('notes',''),user['id']))
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
                # Mandatory clearance reason — must be one of the approved
                # dropdown options (case-insensitive, legacy values mapped).
                purpose = normalise_reason(fields.get('purpose'))
                if not purpose:
                    raise ValueError('Clearance reason is required and must be one of: '
                                     + ', '.join(CLEARANCE_REASONS))
                photo = save_upload(files['photo']) if 'photo' in files else None
                person, created = ensure_person(c, fields, photo_path=(photo['path'] if photo else None))
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from clearance application')
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'clearance application filled missing details')
                app_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_app_')]
                guard_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_guard_')]
                if len(app_docs) < 2: raise ValueError('At least 2 applicant documents are required')
                if not fields.get('guardian_name'): raise ValueError('Guardian full name is required')
                if len(guard_docs) < 2: raise ValueError('At least 2 guardian documents are required')
                aid = 'FP-'+str(int(time.time()*1000))[-8:]
                # The submission timestamp is stored explicitly (UTC) so the
                # 12-hour mandatory review window can be evaluated against it.
                submitted_at = utc_now_stamp()
                c.execute('''INSERT INTO clearance_applications(application_id,person_id,purpose,
                    guardian_name,guardian_relationship,guardian_id,guardian_occupation,guardian_address,
                    guardian_phone,legal_document_ref,notes,applicant_docs,guardian_docs,applicant_photo,
                    sex,email,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (aid,person['id'],purpose,fields.get('guardian_name',''),
                     fields.get('guardian_relationship',''),fields.get('guardian_id',''),
                     fields.get('guardian_occupation',''),fields.get('guardian_address',''),
                     fields.get('guardian_phone',''),fields.get('legal_document_ref',''),
                     fields.get('notes',''),json.dumps(app_docs),json.dumps(guard_docs),
                     photo['path'] if photo else None,
                     (fields.get('sex') or '').strip(),(fields.get('email') or '').strip(),
                     user['id'],submitted_at))
                audit(c,user,'CREATE','clearance_application',aid,person['person_id']); c.commit()
                result = {'application_id':aid,'person_id':person['person_id'],
                          'status':'Pending Review','created_at':submitted_at,'purpose':purpose,
                          'review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                          'review_eligible_at':fingerprint_review_state({'created_at':submitted_at})['review_eligible_at'],
                          'identity':identity_result(c,fields,person)}
            elif p.path.startswith('/api/clearance-applications/') and p.path.endswith('/approve'):
                aid = p.path.split('/')[3]
                row = c.execute('SELECT application_id,status,certificate_number,created_at '
                                'FROM clearance_applications WHERE application_id=?', (aid,)).fetchone()
                if not row:
                    self.send_json(404, {'error':'Application not found'}); c.close(); return
                app_row = rowdict(row)
                # ---- 12-hour mandatory review period ----------------------
                # HARD LOCK, evaluated purely server-side from the stored row
                # and the caller's role. System Administrators bypass the gate;
                # every other role must wait until created_at + 12h, and a row
                # without a usable timestamp stays locked (fail-closed).
                verdict = review_gate_decision(app_row, user)
                if verdict is not None:
                    self.send_json(verdict[0], verdict[1]); c.close(); return
                bypassed = is_admin_user(user)
                cert = app_row['certificate_number'] or ('CL-'+str(int(time.time()*1000))[-8:])
                c.execute("UPDATE clearance_applications SET status='Approved',certificate_number=?,reviewed_at=CURRENT_TIMESTAMP WHERE application_id=?",
                          (cert,aid))
                audit(c,user,'APPROVE','clearance_application',aid,
                      f"{cert} by {user.get('role')}"
                      + (' (review period bypassed)' if bypassed else '')); c.commit()
                result = {'application_id':aid,'certificate_number':cert,'status':'Approved',
                          'review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                          'review_period_bypassed':bypassed,
                          'approved_by_role':user.get('role'),
                          'reviewer_is_fingerprint_officer':is_fingerprint_officer(user)}
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
            elif p.path == '/api/admin/users':
                # Create a new officer / admin user. Admin only (module gate above).
                data = body_json(self)
                username = (data.get('username') or '').strip()
                display_name = (data.get('display_name') or '').strip()
                password = data.get('password') or ''
                role = (data.get('role') or '').strip()
                branch = (data.get('branch') or '').strip() or 'Central HQ'
                if not username: raise ValueError('username is required')
                if not display_name: raise ValueError('display_name is required')
                if not password or len(password) < 6:
                    raise ValueError('password must be at least 6 characters')
                # Spec step 1: accept both the legacy compound forms and
                # the canonical 'checkpoint_officer' alias — and ANY
                # accepted checkpoint spelling ('cp_south',
                # 'checkpoint_south', 'Checkpoint Officer (South)', ...).
                # Aliases are normalised to 'checkpoint_officer' here so
                # the stored role is canonical; the location is derived
                # from the alias ('cp_south' -> 'South') when the caller
                # does not pass an explicit location_scope, so
                # normalizing never loses the officer's location.
                role, derived_scope = normalize_incoming_role(role)
                accepted_roles = set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}
                if role not in accepted_roles:
                    raise ValueError(f'role must be one of {", ".join(sorted(accepted_roles))} '
                                     '(Checkpoint aliases such as CheckpointSouth / cp_south are also accepted)')
                scope = canonical_location_scope(
                    data.get('location_scope') or derived_scope or ROLE_LOCATION_SCOPE.get(role))
                if is_checkpoint_role(role) and not scope:
                    raise ValueError('location_scope is required for Checkpoint roles')
                if scope and scope not in CHECKPOINT_LOCATIONS:
                    raise ValueError(f'location_scope must be one of {", ".join(CHECKPOINT_LOCATIONS)}')
                if c.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                    self.send_json(409, {'error': f'Username "{username}" already exists'}); c.close(); return
                c.execute('''INSERT INTO users(username,display_name,role,branch,location_scope,password_hash,active)
                    VALUES(?,?,?,?,?,?,?)''',
                    (username, display_name, role, branch, scope, password_hash(password),
                     1 if data.get('active', True) else 0))
                new = rowdict(c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone())
                audit(c, user, 'CREATE', 'user', str(new['id']), username)
                c.commit()
                result = {'user': user_view(new)}
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
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'suspect listing filled missing details')
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
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'checkpoint stop filled missing details')
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
                # Normalise casing / trailing whitespace to the canonical
                # short code so every row stored on disk has a clean
                # 'South' / 'East' / 'West' short code in BOTH the legacy
                # 'location' column and the 'location_code' column. The
                # case-insensitive SQL then matches every row and the
                # badge display stays consistent across officers.
                location_lower = location.lower()
                if location_lower in [c.lower() for c in CHECKPOINT_LOCATIONS]:
                    location_code = next(c for c in CHECKPOINT_LOCATIONS
                                          if c.lower() == location_lower)
                else:
                    # 'south checkpoint' / 'South Checkpoint' / etc. -> the
                    # canonical short code (e.g. 'South' / 'East' / 'West').
                    first_token = location_lower.split()[0].strip()
                    matched = next((c for c in CHECKPOINT_LOCATIONS
                                    if c.lower() == first_token), None)
                    if matched:
                        location_code = matched
                    else:
                        # Unknown location: keep the original (lowercased)
                        # token so the error message is informative and the
                        # row can still be stored for audit purposes.
                        location_code = first_token
                # The legacy 'location' column is also normalised to the
                # short code so all three columns agree.
                location = location_code
                # RBAC: a Checkpoint user can only create events at their own
                # location. Admins (and any non-checkpoint officer) may post
                # to any valid checkpoint code.
                scope = checkpoint_scope(user)
                if scope and location != scope:
                    raise ValueError(
                        f'Checkpoint officers can only record stops at their assigned location ({scope})')
                alerted = c.execute('''SELECT 1 FROM suspect_alerts WHERE person_id=? AND role='Suspect'
                    AND alert_status='Active alert' LIMIT 1''',(person['id'],)).fetchone()
                screen = 'Flagged match' if alerted else 'No active alert'
                action = 'Supervisor contacted' if alerted else 'Cleared'
                # Explicit location metadata: 'location_code' is the canonical
                # short code (South/East/West), 'checkpoint_location' is the
                # human-friendly label (e.g. 'South Checkpoint'). The legacy
                # 'location' column is kept for back-compat and mirrors the
                # short code. When the user picks 'South', both fields line up
                # so the dashboard, identity profile, and activity feed can
                # show the exact originating location without re-joining.
                # (location_code is computed earlier from the normalised
                # location string so even lowercase / trailing-space input is
                # persisted in canonical form.)
                checkpoint_location = f'{location_code} Checkpoint'
                event_id = 'CP-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO checkpoint_events(event_id,person_id,location,location_code,
                    checkpoint_location,screening_result,action_taken,notes,purpose_of_visit,
                    current_address,permanent_address,traveler_photo,traveler_docs,
                    guardian_person_id,guardian_name,guardian_relationship,guardian_phone,
                    guardian_address,guardian_occupation,guardian_national_id,guardian_passport_id,
                    guardian_docs,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (event_id,person['id'],location,location_code,checkpoint_location,
                     screen,action,(data.get('notes') or '').strip(),
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
                          'location_code':location_code,
                          'checkpoint_location':checkpoint_location,
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
            # RBAC: only admins can edit user records; CID module updates CID cases.
            if p.path.startswith('/api/admin/users'):
                require_module(user, 'admin')
            elif p.path.startswith('/api/crime-cases'):
                require_module(user, 'cid')
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
            elif p.path.startswith('/api/admin/users/'):
                # Update an existing user — change role, branch, location, password, active.
                # /api/admin/users/<id> -> split('/') -> ['', 'api', 'admin', 'users', '<id>']
                parts = p.path.split('/')
                uid = parts[4] if len(parts) > 4 else ''
                if not uid or not uid.isdigit():
                    self.send_json(400, {'error': 'user id required'}); c.close(); return
                row = c.execute('SELECT * FROM users WHERE id=?', (int(uid),)).fetchone()
                if not row: self.send_json(404, {'error': 'User not found'}); c.close(); return
                updates, params = [], []
                for f in ('display_name', 'branch'):
                    if f in data and str(data[f]).strip():
                        updates.append(f'{f}=?'); params.append(str(data[f]).strip())
                if 'role' in data:
                    # Spec step 1: accept both the legacy compound forms
                    # and the canonical 'checkpoint_officer' alias — and
                    # ANY accepted checkpoint spelling. Aliases are
                    # normalised to 'checkpoint_officer'; the location
                    # embedded in the alias ('CheckpointWest' -> 'West')
                    # is carried into location_scope so it is preserved.
                    role, derived_scope = normalize_incoming_role(str(data['role']).strip())
                    accepted_roles = set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}
                    if role not in accepted_roles:
                        raise ValueError(f'role must be one of {", ".join(sorted(accepted_roles))} '
                                         '(Checkpoint aliases such as CheckpointSouth / cp_south are also accepted)')
                    updates.append('role=?'); params.append(role)
                    # If the new role dictates a location_scope, refresh
                    # it. For 'checkpoint_officer' (the canonical alias)
                    # the table-lookup default is empty; in that case
                    # PRESERVE the existing location_scope so a PATCH
                    # from 'CheckpointSouth' -> 'checkpoint_officer'
                    # does not wipe the officer's location. The
                    # caller can still pass an explicit
                    # 'location_scope' to override.
                    if 'location_scope' not in data:
                        default_scope = derived_scope or ROLE_LOCATION_SCOPE.get(role)
                        if default_scope:
                            updates.append('location_scope=?'); params.append(default_scope)
                        # else: keep the existing scope (no-op).
                if 'location_scope' in data:
                    scope = canonical_location_scope(data['location_scope'])
                    if scope and scope not in CHECKPOINT_LOCATIONS:
                        raise ValueError(f'location_scope must be one of {", ".join(CHECKPOINT_LOCATIONS)}')
                    updates.append('location_scope=?'); params.append(scope)
                if 'active' in data:
                    updates.append('active=?'); params.append(1 if data['active'] else 0)
                if data.get('password'):
                    if len(str(data['password'])) < 6:
                        raise ValueError('password must be at least 6 characters')
                    updates.append('password_hash=?'); params.append(password_hash(str(data['password'])))
                if updates:
                    params.append(int(uid))
                    c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
                    audit(c, user, 'UPDATE', 'user', uid)
                c.commit()
                updated = rowdict(c.execute('SELECT * FROM users WHERE id=?', (int(uid),)).fetchone())
                result = {'user': user_view(updated)}
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
    print(f'  build {BUILD_TAG}')
    print(f'  fingerprint review window: {FINGERPRINT_REVIEW_WINDOW_HOURS}h '
          f'(admin/SystemAdmin bypasses, every other role is locked)')
    print(f'  {review_lock_self_test()}')
    print(f'  clearance reasons: {", ".join(CLEARANCE_REASONS)}')
    ThreadingHTTPServer(('0.0.0.0', port), API).serve_forever()
