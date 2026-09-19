"""Sentinel SQLite storage layer.

Connection factory (:func:`db`), full schema (:data:`SCHEMA` plus the
vehicle tables), idempotent migrations and first-run seeding
(:func:`init_db`) — moved verbatim out of ``backend/server.py``.

SQLite stays active. For the future PostgreSQL move see
``backend/postgres_settings.example.py``; only :func:`db` and the
``%s``/``?`` paramstyle need to change, behind this module's boundary.

Standard library only (+ :mod:`vehicles` schema fragment).
"""
import secrets, sqlite3
from vehicles import VEHICLES_SCHEMA
from config import *
from utils import *


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
CREATE TABLE IF NOT EXISTS police_stations(
  id INTEGER PRIMARY KEY, station_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
  region TEXT NOT NULL, district TEXT NOT NULL, village TEXT,
  station_tier TEXT, commander_id INTEGER REFERENCES officers(id),
  deputy_id INTEGER REFERENCES officers(id), contact_phone TEXT,
  cell_capacity INTEGER, operational_status TEXT DEFAULT 'Active',
  notes TEXT, created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS officers(
  id INTEGER PRIMARY KEY, service_id TEXT UNIQUE NOT NULL,
  -- Section 1: Official & System identifiers
  rank TEXT NOT NULL, unit TEXT NOT NULL,
  station_id INTEGER NOT NULL REFERENCES police_stations(id),
  date_of_enlistment TEXT NOT NULL,
  duty_status TEXT NOT NULL DEFAULT 'Active',
  -- Section 2: Personal identification
  full_name TEXT NOT NULL, mother_name TEXT NOT NULL,
  date_of_birth TEXT NOT NULL, place_of_birth TEXT NOT NULL,
  contact_number TEXT NOT NULL,
  height_cm TEXT, weight_kg TEXT, blood_group TEXT,
  photo_path TEXT,
  -- Section 3: Regional & origin data
  region_of_origin TEXT, district_of_origin TEXT, town_village TEXT,
  -- Section 4: Guarantor / emergency contact
  guarantor_name TEXT NOT NULL, guarantor_address TEXT NOT NULL,
  guarantor_occupation TEXT, guarantor_relationship TEXT,
  guarantor_contact TEXT NOT NULL, guarantor_photo TEXT,
  -- Section 5: Verification & supporting documents
  doc1_type TEXT NOT NULL, doc1_path TEXT NOT NULL,
  doc2_type TEXT, doc2_path TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crime_incidents(
  id INTEGER PRIMARY KEY, file_number TEXT UNIQUE NOT NULL,
  station_id INTEGER NOT NULL REFERENCES police_stations(id),
  officer_id INTEGER NOT NULL REFERENCES officers(id),
  category TEXT NOT NULL, incident_at TEXT NOT NULL,
  location_of_occurrence TEXT, severity TEXT,
  description TEXT NOT NULL,
  case_status TEXT NOT NULL DEFAULT 'Reported / Open',
  reporting_party_type TEXT,
  victim_anonymous INTEGER DEFAULT 0,
  victim_full_name TEXT, victim_contact TEXT, victim_national_id TEXT,
  victim_gender TEXT, victim_age INTEGER, victim_address TEXT,
  statement TEXT,
  evidence1_type TEXT, evidence1_path TEXT,
  evidence2_type TEXT, evidence2_path TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS officer_promotions(
  id INTEGER PRIMARY KEY, nomination_id TEXT UNIQUE NOT NULL,
  officer_id INTEGER NOT NULL REFERENCES officers(id),
  current_rank TEXT NOT NULL, proposed_rank TEXT NOT NULL,
  reason TEXT, effective_date TEXT,
  verification_status TEXT NOT NULL DEFAULT 'Awaiting Verification',
  nominated_by INTEGER REFERENCES users(id),
  verified_by INTEGER REFERENCES users(id), verified_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS officer_discipline(
  id INTEGER PRIMARY KEY, action_id TEXT UNIQUE NOT NULL,
  officer_id INTEGER NOT NULL REFERENCES officers(id),
  action_type TEXT NOT NULL,
  severity TEXT,
  status TEXT NOT NULL DEFAULT 'Pending',
  from_rank TEXT, to_rank TEXT,
  suspension_start TEXT, suspension_end TEXT,
  incident_summary TEXT,
  reported_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS officer_conduct_actions(
  id INTEGER PRIMARY KEY, action_id TEXT UNIQUE NOT NULL,
  officer_id INTEGER NOT NULL REFERENCES officers(id),
  action_type TEXT NOT NULL,
  classification TEXT NOT NULL,
  proposed_rank TEXT,
  narrative TEXT NOT NULL,
  station_id INTEGER REFERENCES police_stations(id),
  reporting_officer_id INTEGER REFERENCES officers(id),
  submitted_at TEXT,
  status TEXT NOT NULL DEFAULT 'Submitted to HR',
  reviewer_officer_id INTEGER REFERENCES officers(id),
  reviewer_notes TEXT, reviewed_at TEXT,
  rank_applied INTEGER NOT NULL DEFAULT 0,
  documents TEXT,
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
    c.executescript(VEHICLES_SCHEMA)
    migrate(c)
    # Canonical checkpoint locations — referenced by both the data and the RBAC layer.
    if c.execute('SELECT COUNT(*) FROM locations').fetchone()[0] == 0:
        for code, label in (('South', 'South Checkpoint'),
                             ('East', 'East Checkpoint'),
                             ('West', 'West Checkpoint')):
            c.execute('INSERT INTO locations(code,label,kind) VALUES(?,?,?)',
                      (code, label, 'Checkpoint'))
    # Seed the Station Registration table so the officer form's "Assigned
    # Station" dropdown is populated on first run. Mirrors the frontend seed
    # gazetteer (Sool / Sanaag / East Togdheer).
    if c.execute('SELECT COUNT(*) FROM police_stations').fetchone()[0] == 0:
        # station_tier + cell_capacity are seeded too so the Station Master
        # Registry analytics (operational capacity by tier) has real axes on
        # first run instead of eight "Unclassified" stations.
        for sid, name, code, region, district, village, tier, cells in (
                ('ST-001', 'Ceerigaabo Central Station', 'SAN-C-01', 'Sanaag', 'Ceerigaabo', 'Ceerigaabo', 'Regional HQ', 24),
                ('ST-002', 'Badhan Station',           'SAN-C-02', 'Sanaag', 'Badhan',     'Badhan',     'District HQ', 12),
                ('ST-003', 'Caynabo Station',          'SOO-C-03', 'Sool',   'Caynabo',    'Caynabo',    'District HQ', 10),
                ('ST-004', 'Las Anod Station',         'SOO-C-01', 'Sool',   'Laascaanood','Laascaanood','Regional HQ', 20),
                ('ST-005', 'Burao Station',            'TOG-C-01', 'East Togdheer', 'Burao', 'Burao',     'Regional HQ', 24),
                ('ST-006', 'Oodweyne Station',         'TOG-C-02', 'East Togdheer', 'Oodweyne', 'Oodweyne','District HQ', 12),
                ('ST-007', 'Buuhoodle Station',        'ETG-C-03', 'East Togdheer', 'Buuhoodle', 'Widh Widh','Outpost', 6),
                ('ST-008', 'Adhi Cadeeye Outpost',     'SOO-C-02', 'Sool',   'Laascaanood','Adhi Cadeeye','Checkpoint', 4)):
            c.execute('INSERT INTO police_stations(station_id,name,code,region,district,village,'
                      'station_tier,cell_capacity) VALUES(?,?,?,?,?,?,?,?)',
                      (sid, name, code, region, district, village, tier, cells))
    # Normalise the legacy admin account + seed a representative user per role
    # so the RBAC flow is exercised by default. The existing admin keeps its
    # password (idempotent — we only re-tag it on first run).
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        seeds = [
            ('admin',       'Officer A. Hassan',     ROLE_ADMIN,           'Central HQ',      None,                 'ChangeMe123!'),
            ('fp.officer',  'Officer H. Xasan',      ROLE_FINGERPRINT,     'Fingerprint Unit', None,                'ChangeMe123!'),
            ('ap.officer',  'Officer S. Cabdi',      ROLE_AIRPORT,         'Airport Control', None,                 'ChangeMe123!'),
            ('cid.officer', 'Officer M. Nuur',       ROLE_CID,             'CID Unit',         None,                'ChangeMe123!'),
            ('hr.officer',  'Officer S. Warsame',    ROLE_HR,              'HR Directorate',   None,                'ChangeMe123!'),
            ('cp.south',    'Officer F. Cali',       ROLE_CHECKPOINT_SOUTH,'Checkpoint South', 'South',             'ChangeMe123!'),
            ('cp.east',     'Officer A. Maxamed',    ROLE_CHECKPOINT_EAST, 'Checkpoint East',  'East',              'ChangeMe123!'),
            ('cp.west',     'Officer N. Yuusuf',     ROLE_CHECKPOINT_WEST, 'Checkpoint West',  'West',              'ChangeMe123!'),
            ('chief',       'Gen. C. Warsame',       ROLE_CHIEF,           'Police HQ / Command', None,             'ChangeMe123!'),
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
