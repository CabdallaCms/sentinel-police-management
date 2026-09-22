"""
Enterprise Scaling Refactor — Zero-Code Provisioning Prototype
Branch: arena/enterprise-scaling-refactor
Date: 2026-09-22

Implements dynamic relational model:
  Region -> District -> Village
  Facility Types (STATIC_HQ, SPECIALIZED_BRANCH, STATION, CHECKPOINT)
  Facilities (generic abstraction for stations, checkpoints, airport/CID/fingerprint branches)
  User Facility Assignments

This module is imported by server.py and provides:
  - ENTERPRISE_SCHEMA (DDL)
  - Seed data for Sool, Sanaag, East Togdheer + districts
  - CRUD helpers
  - Views
  - Scope helpers
"""

import re
import time
import json
import datetime

# ---------------------------------------------------------------------------
# Facility categories and types
# ---------------------------------------------------------------------------
FACILITY_CATEGORIES = ('STATIC_HQ', 'SPECIALIZED_BRANCH', 'STATION', 'CHECKPOINT')

FACILITY_TYPE_SEED = (
    ('CENTRAL_REGISTRATION', 'Central Police Registration Office', 'STATIC_HQ', True, 'Single national-level office, never scales geographically'),
    ('CENTRAL_VEHICLE', 'Central Vehicle Police Car Registration', 'STATIC_HQ', True, 'Single national-level vehicle registration'),
    ('CID_BRANCH', 'CID Branch', 'SPECIALIZED_BRANCH', False, 'Criminal Investigation Department regional branch, e.g., Erigavo CID, Lasanod CID'),
    ('FINGERPRINT_BRANCH', 'Fingerprint Branch', 'SPECIALIZED_BRANCH', False, 'Fingerprint / Good Conduct regional branch'),
    ('AIRPORT_BRANCH', 'Airport Branch', 'SPECIALIZED_BRANCH', False, 'Airport Control regional branch, e.g., Lasanod Airport, Buuhoodle Airport'),
    ('POLICE_STATION', 'Local Police Station', 'STATION', False, 'Multiple per district across regions'),
    ('CHECKPOINT', 'Checkpoint', 'CHECKPOINT', False, 'Multiple per region/district, e.g., Hudun Checkpoint, Lasqoray Checkpoint'),
)

FACILITY_TIERS = ('Regional HQ', 'District HQ', 'Outpost', 'Checkpoint', 'Border Post', 'Branch Office', 'Sub-Station')
FACILITY_STATUSES = ('Active', 'Inactive', 'Maintenance', 'Planned', 'Closed')

# Generic roles for new provisioning (decoupled from location)
ENTERPRISE_ROLES = (
    'station_officer',
    'checkpoint_officer',
    'airport_officer',
    'cid_officer',
    'fingerprint_officer',
    'hr_officer',
    'admin',
    'chief_commander',
)

# ---------------------------------------------------------------------------
# DDL Schema
# ---------------------------------------------------------------------------
ENTERPRISE_SCHEMA = """
CREATE TABLE IF NOT EXISTS regions(
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS districts(
  id SERIAL PRIMARY KEY,
  region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  UNIQUE(region_id, name)
);

CREATE TABLE IF NOT EXISTS villages(
  id SERIAL PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  village_type TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  UNIQUE(district_id, name)
);

CREATE TABLE IF NOT EXISTS facility_types(
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT,
  is_global BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS facilities(
  id SERIAL PRIMARY KEY,
  facility_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  code TEXT UNIQUE NOT NULL,
  facility_type_id INTEGER NOT NULL REFERENCES facility_types(id),
  region_id INTEGER REFERENCES regions(id),
  district_id INTEGER REFERENCES districts(id),
  village_id INTEGER REFERENCES villages(id),
  parent_facility_id INTEGER REFERENCES facilities(id),
  station_tier TEXT,
  operational_status TEXT DEFAULT 'Active',
  contact_phone TEXT,
  cell_capacity INTEGER,
  commander_id INTEGER REFERENCES officers(id),
  deputy_id INTEGER REFERENCES officers(id),
  is_active BOOLEAN DEFAULT TRUE,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  legacy_region TEXT,
  legacy_district TEXT,
  legacy_village TEXT
);

CREATE INDEX IF NOT EXISTS idx_facilities_region ON facilities(region_id);
CREATE INDEX IF NOT EXISTS idx_facilities_district ON facilities(district_id);
CREATE INDEX IF NOT EXISTS idx_facilities_type ON facilities(facility_type_id);
CREATE INDEX IF NOT EXISTS idx_facilities_parent ON facilities(parent_facility_id);
CREATE INDEX IF NOT EXISTS idx_facilities_code ON facilities(code);

CREATE TABLE IF NOT EXISTS user_facility_assignments(
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  is_primary BOOLEAN DEFAULT FALSE,
  assigned_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  assigned_by INTEGER REFERENCES users(id),
  UNIQUE(user_id, facility_id)
);

-- Add enterprise columns to existing tables if not exists (handled also via ADDED_COLUMNS, but keep here for fresh DBs)
-- These are applied via ALTER in migrate, but for fresh DBs we can attempt:
-- Note: PostgreSQL doesn't support IF NOT EXISTS for ADD COLUMN in older versions, so we handle in migrate()
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalise_choice(value, options):
    v = str(value or '').strip()
    if not v:
        return None
    for o in options:
        if v.lower() == o.lower():
            return o
    return None

def utc_now_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def rowdict(row):
    return dict(row) if row else None

def region_view(row):
    if not row:
        return None
    return {
        'id': row['id'],
        'code': row['code'],
        'name': row['name'],
        'description': row.get('description') or rowdict(row).get('description'),
        'is_active': bool(row.get('is_active', 1)),
        'created_at': row.get('created_at'),
    }

def district_view(row):
    if not row:
        return None
    return {
        'id': row['id'],
        'region_id': row['region_id'],
        'region_name': row.get('region_name'),
        'region_code': row.get('region_code'),
        'code': row['code'],
        'name': row['name'],
        'description': row.get('description'),
        'is_active': bool(row.get('is_active', 1)),
        'created_at': row.get('created_at'),
    }

def facility_type_view(row):
    if not row:
        return None
    return {
        'id': row['id'],
        'code': row['code'],
        'name': row['name'],
        'category': row['category'],
        'description': row.get('description'),
        'is_global': bool(row.get('is_global')),
        'is_active': bool(row.get('is_active', 1)),
    }

def facility_view(row):
    if not row:
        return None
    d = dict(row)
    # Enrich with joined names if available
    return {
        'id': d['id'],
        'facility_id': d['facility_id'],
        'name': d['name'],
        'code': d['code'],
        'facility_type_id': d['facility_type_id'],
        'facility_type_code': d.get('facility_type_code') or d.get('ft_code'),
        'facility_type_name': d.get('facility_type_name') or d.get('ft_name'),
        'facility_category': d.get('facility_category') or d.get('ft_category'),
        'region_id': d.get('region_id'),
        'region_name': d.get('region_name'),
        'region_code': d.get('region_code'),
        'district_id': d.get('district_id'),
        'district_name': d.get('district_name'),
        'village_id': d.get('village_id'),
        'village_name': d.get('village_name'),
        'parent_facility_id': d.get('parent_facility_id'),
        'parent_facility_name': d.get('parent_facility_name'),
        'station_tier': d.get('station_tier'),
        'operational_status': d.get('operational_status') or 'Active',
        'contact_phone': d.get('contact_phone'),
        'cell_capacity': d.get('cell_capacity'),
        'commander_id': d.get('commander_id'),
        'deputy_id': d.get('deputy_id'),
        'is_active': bool(d.get('is_active', 1)),
        'notes': d.get('notes'),
        'created_at': d.get('created_at'),
        'legacy_region': d.get('legacy_region'),
        'legacy_district': d.get('legacy_district'),
    }

# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

def generate_region_code(name):
    # Simple code generation: first 3 letters upper + maybe number
    base = re.sub(r'[^A-Za-z]', '', name)[:3].upper() or 'REG'
    return base

def generate_district_code(region_code, district_name):
    base = re.sub(r'[^A-Za-z]', '', district_name)[:3].upper() or 'DIS'
    return f"{region_code}-{base}"

def generate_facility_id(c, prefix="FAC"):
    # Auto-generate FAC-001 style, but with type prefix if needed
    # Look for max existing with prefix
    year = datetime.datetime.now(datetime.timezone.utc).year
    # Try FAC-YYYY-XXXX
    p = f"{prefix}-{year}-"
    row = c.execute("SELECT facility_id FROM facilities WHERE facility_id ILIKE %s ORDER BY facility_id DESC LIMIT 1", (p + '%',)).fetchone()
    n = 1
    if row:
        try:
            n = int(str(row['facility_id']).rsplit('-', 1)[1]) + 1
        except:
            n = c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] + 1
    return f"{p}{n:04d}"

def create_region(c, user, data):
    name = str(data.get('name') or '').strip()
    if not name:
        raise ValueError('Region name is required')
    if len(name) < 2:
        raise ValueError('Region name must be at least 2 characters')
    code = str(data.get('code') or '').strip().upper() or generate_region_code(name)
    # Ensure code unique, if exists append number
    base_code = code
    counter = 1
    while c.execute("SELECT 1 FROM regions WHERE code=%s", (code,)).fetchone():
        counter += 1
        code = f"{base_code}{counter}"
    # Check name unique
    if c.execute("SELECT 1 FROM regions WHERE LOWER(name)=LOWER(%s)", (name,)).fetchone():
        raise ValueError(f'Region "{name}" already exists')
    description = str(data.get('description') or '').strip() or None
    c.execute("INSERT INTO regions(code,name,description,created_by) VALUES(%s,%s,%s,%s)",
              (code, name, description, user['id']))
    row = c.execute("SELECT * FROM regions WHERE code=%s", (code,)).fetchone()
    return region_view(row)

def create_district(c, user, data):
    region_ref = str(data.get('region_id') or data.get('region') or '').strip()
    if not region_ref:
        raise ValueError('region_id or region name is required')
    # Resolve region
    region = None
    if region_ref.isdigit():
        region = c.execute("SELECT * FROM regions WHERE id=%s", (int(region_ref),)).fetchone()
    else:
        # Try code or name
        region = c.execute("SELECT * FROM regions WHERE code=%s OR LOWER(name)=LOWER(%s)", (region_ref, region_ref)).fetchone()
        if not region:
            # Try id as string?
            try:
                region = c.execute("SELECT * FROM regions WHERE id=%s", (int(region_ref),)).fetchone()
            except:
                pass
    if not region:
        raise ValueError(f'Region "{region_ref}" does not exist')
    name = str(data.get('name') or '').strip()
    if not name:
        raise ValueError('District name is required')
    # Check duplicate in region
    if c.execute("SELECT 1 FROM districts WHERE region_id=%s AND LOWER(name)=LOWER(%s)", (region['id'], name)).fetchone():
        raise ValueError(f'District "{name}" already exists in region "{region["name"]}"')
    code = str(data.get('code') or '').strip().upper() or generate_district_code(region['code'], name)
    base_code = code
    counter = 1
    while c.execute("SELECT 1 FROM districts WHERE code=%s", (code,)).fetchone():
        counter += 1
        code = f"{base_code}{counter}"
    description = str(data.get('description') or '').strip() or None
    c.execute("INSERT INTO districts(region_id,code,name,description,created_by) VALUES(%s,%s,%s,%s,%s)",
              (region['id'], code, name, description, user['id']))
    row = c.execute("""SELECT d.*, r.name AS region_name, r.code AS region_code
                       FROM districts d JOIN regions r ON r.id=d.region_id WHERE d.code=%s""", (code,)).fetchone()
    return district_view(row)

def create_village(c, user, data):
    district_ref = str(data.get('district_id') or data.get('district') or '').strip()
    if not district_ref:
        raise ValueError('district_id or district name is required')
    district = None
    if district_ref.isdigit():
        district = c.execute("SELECT * FROM districts WHERE id=%s", (int(district_ref),)).fetchone()
    else:
        district = c.execute("SELECT * FROM districts WHERE code=%s OR LOWER(name)=LOWER(%s)", (district_ref, district_ref)).fetchone()
    if not district:
        raise ValueError(f'District "{district_ref}" does not exist')
    name = str(data.get('name') or '').strip()
    if not name:
        raise ValueError('Village/Town name is required')
    if c.execute("SELECT 1 FROM villages WHERE district_id=%s AND LOWER(name)=LOWER(%s)", (district['id'], name)).fetchone():
        raise ValueError(f'Village/Town "{name}" already exists in district "{district["name"]}"')
    vtype = str(data.get('village_type') or data.get('type') or '').strip() or None
    c.execute("INSERT INTO villages(district_id,name,village_type,created_by) VALUES(%s,%s,%s,%s)",
              (district['id'], name, vtype, user['id']))
    row = c.execute("SELECT * FROM villages WHERE district_id=%s AND LOWER(name)=LOWER(%s)", (district['id'], name)).fetchone()
    return dict(row) if row else None

def resolve_region(c, ref):
    if not ref:
        return None
    r = str(ref).strip()
    if not r:
        return None
    if r.isdigit():
        return c.execute("SELECT * FROM regions WHERE id=%s", (int(r),)).fetchone()
    return c.execute("SELECT * FROM regions WHERE code=%s OR LOWER(name)=LOWER(%s)", (r, r)).fetchone()

def resolve_district(c, ref, region_id=None):
    if not ref:
        return None
    r = str(ref).strip()
    if not r:
        return None
    if r.isdigit():
        row = c.execute("SELECT * FROM districts WHERE id=%s", (int(r),)).fetchone()
        if row and region_id and row['region_id'] != region_id:
            return None
        return row
    # Try code or name, optionally filtered by region
    if region_id:
        row = c.execute("SELECT * FROM districts WHERE region_id=%s AND (code=%s OR LOWER(name)=LOWER(%s))", (region_id, r, r)).fetchone()
        return row
    return c.execute("SELECT * FROM districts WHERE code=%s OR LOWER(name)=LOWER(%s)", (r, r)).fetchone()

def resolve_facility_type(c, ref):
    if not ref:
        return None
    r = str(ref).strip()
    if not r:
        return None
    if r.isdigit():
        return c.execute("SELECT * FROM facility_types WHERE id=%s", (int(r),)).fetchone()
    return c.execute("SELECT * FROM facility_types WHERE code=%s OR LOWER(name)=LOWER(%s)", (r, r)).fetchone()

def resolve_facility(c, ref):
    if not ref:
        return None
    r = str(ref).strip()
    if not r:
        return None
    if r.isdigit():
        return c.execute("SELECT * FROM facilities WHERE id=%s", (int(r),)).fetchone()
    # Try facility_id, code, or name
    row = c.execute("SELECT * FROM facilities WHERE facility_id=%s OR code=%s", (r, r)).fetchone()
    if not row:
        row = c.execute("SELECT * FROM facilities WHERE LOWER(name)=LOWER(%s)", (r,)).fetchone()
    return row

def create_facility(c, user, data):
    """
    Create a facility (station, checkpoint, airport branch, CID branch, etc.)
    Required: name, facility_type (code or id), region, district
    Optional: village, parent_facility, tier, operational_status, contact_phone, cell_capacity, notes
    """
    name = str(data.get('name') or '').strip()
    if not name:
        raise ValueError('Facility name is required')
    if len(name) < 3:
        raise ValueError('Facility name must be at least 3 characters')

    # Facility type
    ft_ref = str(data.get('facility_type_id') or data.get('facility_type') or data.get('type') or '').strip()
    if not ft_ref:
        raise ValueError('facility_type is required (e.g., POLICE_STATION, CHECKPOINT, AIRPORT_BRANCH, CID_BRANCH, FINGERPRINT_BRANCH)')
    ft = resolve_facility_type(c, ft_ref)
    if not ft:
        raise ValueError(f'Facility type "{ft_ref}" does not exist. Valid types: {", ".join([t[0] for t in FACILITY_TYPE_SEED])}')

    # Region
    region_ref = str(data.get('region_id') or data.get('region') or '').strip()
    region = None
    if region_ref:
        region = resolve_region(c, region_ref)
        if not region:
            raise ValueError(f'Region "{region_ref}" does not exist. Create it first via /api/regions')
    else:
        # If facility type is global (STATIC_HQ), region can be null
        if not ft['is_global']:
            raise ValueError('Region is required for non-global facilities')

    # District
    district_ref = str(data.get('district_id') or data.get('district') or '').strip()
    district = None
    if district_ref:
        district = resolve_district(c, district_ref, region_id=region['id'] if region else None)
        if not district:
            raise ValueError(f'District "{district_ref}" does not exist in region "{region["name"] if region else ""}". Create it first via /api/districts')
    else:
        if not ft['is_global']:
            raise ValueError('District is required for non-global facilities')

    # Village (optional)
    village = None
    village_ref = str(data.get('village_id') or data.get('village') or '').strip()
    if village_ref:
        if village_ref.isdigit():
            village = c.execute("SELECT * FROM villages WHERE id=%s", (int(village_ref),)).fetchone()
        else:
            # Try name within district
            if district:
                village = c.execute("SELECT * FROM villages WHERE district_id=%s AND LOWER(name)=LOWER(%s)", (district['id'], village_ref)).fetchone()
            else:
                village = c.execute("SELECT * FROM villages WHERE LOWER(name)=LOWER(%s)", (village_ref,)).fetchone()
        if not village:
            # Auto-create village if district exists? For zero-code provisioning, allow auto-create
            if district:
                c.execute("INSERT INTO villages(district_id,name,created_by) VALUES(%s,%s,%s)", (district['id'], village_ref, user['id']))
                village = c.execute("SELECT * FROM villages WHERE district_id=%s AND LOWER(name)=LOWER(%s)", (district['id'], village_ref)).fetchone()
            else:
                raise ValueError(f'Village "{village_ref}" does not exist')

    # Parent facility (optional, for hierarchy)
    parent = None
    parent_ref = str(data.get('parent_facility_id') or data.get('parent_facility') or '').strip()
    if parent_ref:
        parent = resolve_facility(c, parent_ref)
        if not parent:
            raise ValueError(f'Parent facility "{parent_ref}" does not exist')

    # Tier and status
    tier = normalise_choice(data.get('station_tier') or data.get('tier'), FACILITY_TIERS) or str(data.get('station_tier') or data.get('tier') or '').strip() or None
    if (data.get('station_tier') or data.get('tier')) and not tier:
        # Allow any tier if not in list? For flexibility, allow free text but warn
        tier = str(data.get('station_tier') or data.get('tier')).strip()

    status = normalise_choice(data.get('operational_status') or data.get('status'), FACILITY_STATUSES) or 'Active'

    phone = str(data.get('contact_phone') or data.get('phone') or '').strip() or None
    if not phone and not ft['is_global']:
        raise ValueError('Contact phone is required for operational facilities')

    cell_cap = None
    cap_raw = data.get('cell_capacity')
    if cap_raw not in (None, ''):
        try:
            cell_cap = int(cap_raw)
        except:
            raise ValueError('cell_capacity must be an integer')
        if cell_cap < 0:
            raise ValueError('cell_capacity must be >=0')

    # Code generation
    code = str(data.get('code') or '').strip().upper()
    if not code:
        # Generate from region code + district + type
        # e.g., SOL-TAL-ST-001, SAN-ERI-CID-01, ETG-BUH-AP-01
        region_code = region['code'] if region else 'HQ'
        district_code = district['code'].split('-')[-1] if district and '-' in district['code'] else (district['name'][:3].upper() if district else 'GEN')
        type_suffix = {
            'POLICE_STATION': 'ST',
            'CHECKPOINT': 'CP',
            'AIRPORT_BRANCH': 'AP',
            'CID_BRANCH': 'CID',
            'FINGERPRINT_BRANCH': 'FP',
            'CENTRAL_REGISTRATION': 'CR',
            'CENTRAL_VEHICLE': 'CV',
        }.get(ft['code'], 'FAC')
        # Find next number
        prefix = f"{region_code}-{district_code}-{type_suffix}-"
        n = 1
        for row in c.execute("SELECT code FROM facilities WHERE code ILIKE %s", (prefix + '%',)):
            try:
                n = max(n, int(str(row['code']).rsplit('-', 1)[1]) + 1)
            except:
                pass
        code = f"{prefix}{n:03d}"

    # Facility_id generation
    facility_id = str(data.get('facility_id') or '').strip()
    if not facility_id:
        # Use code as facility_id if code looks like FAC, otherwise generate
        if code.startswith('ST-') or code.startswith('FAC-'):
            facility_id = code
        else:
            # Map type to prefix
            prefix_map = {
                'POLICE_STATION': 'ST',
                'CHECKPOINT': 'CP',
                'AIRPORT_BRANCH': 'AP',
                'CID_BRANCH': 'CID',
                'FINGERPRINT_BRANCH': 'FP',
                'CENTRAL_REGISTRATION': 'HQ-REG',
                'CENTRAL_VEHICLE': 'HQ-VEH',
            }
            pfx = prefix_map.get(ft['code'], 'FAC')
            facility_id = generate_facility_id(c, prefix=pfx)

    # Ensure unique
    if c.execute("SELECT 1 FROM facilities WHERE facility_id=%s", (facility_id,)).fetchone():
        raise ValueError(f'Facility ID "{facility_id}" already exists')
    if c.execute("SELECT 1 FROM facilities WHERE code=%s", (code,)).fetchone():
        raise ValueError(f'Facility code "{code}" already exists')

    notes = str(data.get('notes') or '').strip() or None

    c.execute("""INSERT INTO facilities(
        facility_id,name,code,facility_type_id,region_id,district_id,village_id,
        parent_facility_id,station_tier,operational_status,contact_phone,cell_capacity,notes,created_by,
        legacy_region,legacy_district,legacy_village)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (facility_id, name, code, ft['id'],
         region['id'] if region else None,
         district['id'] if district else None,
         village['id'] if village else None,
         parent['id'] if parent else None,
         tier, status, phone, cell_cap, notes, user['id'],
         region['name'] if region else None,
         district['name'] if district else None,
         village['name'] if village else None))

    row = c.execute("""SELECT f.*, ft.code AS facility_type_code, ft.name AS facility_type_name, ft.category AS facility_category,
                       r.name AS region_name, r.code AS region_code,
                       d.name AS district_name,
                       v.name AS village_name,
                       pf.name AS parent_facility_name
                       FROM facilities f
                       JOIN facility_types ft ON ft.id=f.facility_type_id
                       LEFT JOIN regions r ON r.id=f.region_id
                       LEFT JOIN districts d ON d.id=f.district_id
                       LEFT JOIN villages v ON v.id=f.village_id
                       LEFT JOIN facilities pf ON pf.id=f.parent_facility_id
                       WHERE f.facility_id=%s""", (facility_id,)).fetchone()
    return facility_view(row)

def update_facility(c, user, facility_ref, data):
    facility = resolve_facility(c, facility_ref)
    if not facility:
        raise ValueError(f'Facility "{facility_ref}" not found')
    updates = []
    params = []

    # Allow updating name, tier, status, phone, cell_capacity, notes, commander, parent, is_active
    if 'name' in data and str(data['name']).strip():
        updates.append("name=%s")
        params.append(str(data['name']).strip())
    if 'station_tier' in data or 'tier' in data:
        tier_val = str(data.get('station_tier') or data.get('tier') or '').strip()
        if tier_val:
            updates.append("station_tier=%s")
            params.append(tier_val)
    if 'operational_status' in data or 'status' in data:
        status_val = str(data.get('operational_status') or data.get('status') or '').strip()
        if status_val:
            s = normalise_choice(status_val, FACILITY_STATUSES) or status_val
            updates.append("operational_status=%s")
            params.append(s)
    if 'contact_phone' in data or 'phone' in data:
        phone_val = str(data.get('contact_phone') or data.get('phone') or '').strip()
        if phone_val:
            updates.append("contact_phone=%s")
            params.append(phone_val)
    if 'cell_capacity' in data:
        cap = data['cell_capacity']
        if cap in (None, ''):
            updates.append("cell_capacity=%s")
            params.append(None)
        else:
            try:
                cap_int = int(cap)
                updates.append("cell_capacity=%s")
                params.append(cap_int)
            except:
                raise ValueError('cell_capacity must be integer')
    if 'notes' in data:
        updates.append("notes=%s")
        params.append(str(data['notes']).strip() or None)
    if 'is_active' in data:
        updates.append("is_active=%s")
        params.append(bool(data['is_active']))
    if 'parent_facility_id' in data or 'parent_facility' in data:
        parent_ref = str(data.get('parent_facility_id') or data.get('parent_facility') or '').strip()
        if parent_ref:
            parent = resolve_facility(c, parent_ref)
            if not parent:
                raise ValueError(f'Parent facility "{parent_ref}" not found')
            if parent['id'] == facility['id']:
                raise ValueError('Facility cannot be parent of itself')
            updates.append("parent_facility_id=%s")
            params.append(parent['id'])
        else:
            updates.append("parent_facility_id=%s")
            params.append(None)

    if not updates:
        raise ValueError('No valid fields to update')

    params.append(facility['id'])
    c.execute(f"UPDATE facilities SET {', '.join(updates)} WHERE id=%s", params)
    row = c.execute("""SELECT f.*, ft.code AS facility_type_code, ft.name AS facility_type_name, ft.category AS facility_category,
                       r.name AS region_name, r.code AS region_code,
                       d.name AS district_name,
                       v.name AS village_name,
                       pf.name AS parent_facility_name
                       FROM facilities f
                       JOIN facility_types ft ON ft.id=f.facility_type_id
                       LEFT JOIN regions r ON r.id=f.region_id
                       LEFT JOIN districts d ON d.id=f.district_id
                       LEFT JOIN villages v ON v.id=f.village_id
                       LEFT JOIN facilities pf ON pf.id=f.parent_facility_id
                       WHERE f.id=%s""", (facility['id'],)).fetchone()
    return facility_view(row)

def list_regions(c, active_only=False, search=''):
    sql = "SELECT * FROM regions"
    where = []
    params = []
    if active_only:
        where.append("is_active=TRUE")
    if search:
        where.append("(name ILIKE %s OR code ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name ASC"
    rows = c.execute(sql, params).fetchall()
    return [region_view(r) for r in rows]

def list_districts(c, region_id=None, search=''):
    sql = """SELECT d.*, r.name AS region_name, r.code AS region_code
             FROM districts d JOIN regions r ON r.id=d.region_id"""
    where = []
    params = []
    if region_id:
        # region_id can be id, code, or name
        if str(region_id).isdigit():
            where.append("d.region_id=%s")
            params.append(int(region_id))
        else:
            where.append("(r.code=%s OR LOWER(r.name)=LOWER(%s))")
            params.extend([region_id, region_id])
    if search:
        where.append("(d.name ILIKE %s OR d.code ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.name ASC, d.name ASC"
    rows = c.execute(sql, params).fetchall()
    return [district_view(r) for r in rows]

def list_facility_types(c):
    rows = c.execute("SELECT * FROM facility_types ORDER BY category, name").fetchall()
    return [facility_type_view(r) for r in rows]

def list_facilities(c, region_id=None, district_id=None, facility_type=None, search='', active_only=False, category=None):
    sql = """SELECT f.*, ft.code AS facility_type_code, ft.name AS facility_type_name, ft.category AS facility_category,
                    r.name AS region_name, r.code AS region_code,
                    d.name AS district_name,
                    v.name AS village_name,
                    pf.name AS parent_facility_name
             FROM facilities f
             JOIN facility_types ft ON ft.id=f.facility_type_id
             LEFT JOIN regions r ON r.id=f.region_id
             LEFT JOIN districts d ON d.id=f.district_id
             LEFT JOIN villages v ON v.id=f.village_id
             LEFT JOIN facilities pf ON pf.id=f.parent_facility_id"""
    where = []
    params = []
    if region_id:
        if str(region_id).isdigit():
            where.append("f.region_id=%s")
            params.append(int(region_id))
        else:
            where.append("(r.code=%s OR LOWER(r.name)=LOWER(%s))")
            params.extend([region_id, region_id])
    if district_id:
        if str(district_id).isdigit():
            where.append("f.district_id=%s")
            params.append(int(district_id))
        else:
            where.append("(d.code=%s OR LOWER(d.name)=LOWER(%s))")
            params.extend([district_id, district_id])
    if facility_type:
        if str(facility_type).isdigit():
            where.append("f.facility_type_id=%s")
            params.append(int(facility_type))
        else:
            where.append("(ft.code=%s OR LOWER(ft.name)=LOWER(%s))")
            params.extend([facility_type, facility_type])
    if category:
        where.append("ft.category=%s")
        params.append(category)
    if active_only:
        where.append("f.is_active=TRUE")
    if search:
        where.append("(f.name ILIKE %s OR f.code ILIKE %s OR f.facility_id ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.name ASC, d.name ASC, f.name ASC"
    rows = c.execute(sql, params).fetchall()
    return [facility_view(r) for r in rows]

def seed_enterprise(c):
    """Seed facility_types and initial geography for Sool, Sanaag, East Togdheer"""
    # Facility types
    for code, name, category, is_global, desc in FACILITY_TYPE_SEED:
        if not c.execute("SELECT 1 FROM facility_types WHERE code=%s", (code,)).fetchone():
            c.execute("INSERT INTO facility_types(code,name,category,is_global,description) VALUES(%s,%s,%s,%s,%s)",
                      (code, name, category, is_global, desc))
    # Regions
    regions_seed = (
        ('SOL', 'Sool', 'Sool Region — Lasanod, Taleh, Hudun, Caynabo, Boocame, etc.'),
        ('SAN', 'Sanaag', 'Sanaag Region — Erigavo, Lasqoray, Badhan, Dhahar, Ceel Afweyn, Garadag'),
        ('ETG', 'East Togdheer', 'East Togdheer — Buhoodle, Burao, Oodweyne'),
    )
    for code, name, desc in regions_seed:
        if not c.execute("SELECT 1 FROM regions WHERE code=%s OR LOWER(name)=LOWER(%s)", (code, name)).fetchone():
            c.execute("INSERT INTO regions(code,name,description) VALUES(%s,%s,%s)", (code, name, desc))

    # Districts per region (comprehensive)
    districts_seed = (
        ('SOL', 'SOL-LAS', 'Laascaanood', 'Capital of Sool'),
        ('SOL', 'SOL-TAL', 'Taleh', 'Taleh District'),
        ('SOL', 'SOL-HUD', 'Hudun', 'Hudun District'),
        ('SOL', 'SOL-CAY', 'Caynabo', 'Caynabo District'),
        ('SOL', 'SOL-BOO', 'Boocame', 'Boocame District'),
        ('SOL', 'SOL-LAS-2', 'Las Anod', 'Alternative spelling for Laascaanood'),
        ('SAN', 'SAN-ERI', 'Ceerigaabo', 'Erigavo — Capital of Sanaag'),
        ('SAN', 'SAN-LASQ', 'Lasqoray', 'Lasqoray District'),
        ('SAN', 'SAN-BAD', 'Badhan', 'Badhan District'),
        ('SAN', 'SAN-DHA', 'Dhahar', 'Dhahar District'),
        ('SAN', 'SAN-CEEL', 'Ceel Afweyn', 'Ceel Afweyn District'),
        ('SAN', 'SAN-GAR', 'Garadag', 'Garadag District'),
        ('ETG', 'ETG-BUH', 'Buuhoodle', 'Buuhoodle District'),
        ('ETG', 'ETG-BUR', 'Burao', 'Burao District'),
        ('ETG', 'ETG-OOD', 'Oodweyne', 'Oodweyne District'),
    )
    for region_code, d_code, d_name, d_desc in districts_seed:
        region = c.execute("SELECT id FROM regions WHERE code=%s", (region_code,)).fetchone()
        if not region:
            continue
        if not c.execute("SELECT 1 FROM districts WHERE code=%s", (d_code,)).fetchone():
            # Avoid duplicate name in same region
            if not c.execute("SELECT 1 FROM districts WHERE region_id=%s AND LOWER(name)=LOWER(%s)", (region['id'], d_name)).fetchone():
                c.execute("INSERT INTO districts(region_id,code,name,description) VALUES(%s,%s,%s,%s)",
                          (region['id'], d_code, d_name, d_desc))

    # Migrate existing police_stations into facilities if facilities empty
    if c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 0:
        # Check if police_stations has data
        if c.execute("SELECT COUNT(*) FROM police_stations").fetchone()[0] > 0:
            for ps in c.execute("SELECT * FROM police_stations").fetchall():
                # Resolve region/district FKs
                region = c.execute("SELECT id FROM regions WHERE LOWER(name)=LOWER(%s) OR code=%s", (ps['region'], ps['region'])).fetchone()
                district = None
                if region:
                    district = c.execute("SELECT id FROM districts WHERE region_id=%s AND LOWER(name)=LOWER(%s)", (region['id'], ps['district'])).fetchone()
                ft = c.execute("SELECT id FROM facility_types WHERE code='POLICE_STATION'").fetchone()
                if not ft:
                    continue
                # Avoid duplicate facility_id
                if c.execute("SELECT 1 FROM facilities WHERE facility_id=%s", (ps['station_id'],)).fetchone():
                    continue
                c.execute("""INSERT INTO facilities(
                    facility_id,name,code,facility_type_id,region_id,district_id,
                    station_tier,operational_status,contact_phone,cell_capacity,notes,created_by,
                    legacy_region,legacy_district,legacy_village)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (ps['station_id'], ps['name'], ps['code'], ft['id'],
                     region['id'] if region else None,
                     district['id'] if district else None,
                     ps['station_tier'], ps['operational_status'], ps['contact_phone'], ps['cell_capacity'], ps['notes'], ps['created_by'],
                     ps['region'], ps['district'], ps['village']))

def facility_scope(user):
    """
    New scope helper for enterprise model.
    Returns dict with facility_id, region_id, district_id, or None for global.
    For backward compat, also supports old checkpoint_scope logic.
    """
    if not user:
        return {'facility_id': None, 'region_id': None, 'district_id': None, 'scope_type': 'none'}
    # Admin and chief have global scope
    role = str(user.get('role') or '').lower()
    if role in ('systemadmin', 'admin', 'chief_commander', 'chiefcommander'):
        return {'facility_id': None, 'region_id': None, 'district_id': None, 'scope_type': 'global'}

    # Try enterprise fields
    facility_id = user.get('facility_id')
    region_id = user.get('region_id')
    district_id = user.get('district_id')

    # If user has facility assignment via user_facility_assignments, use primary
    # (This is resolved in user_view if needed)

    if facility_id or region_id or district_id:
        return {
            'facility_id': facility_id,
            'region_id': region_id,
            'district_id': district_id,
            'scope_type': 'facility' if facility_id else ('district' if district_id else 'region')
        }

    # Fallback to old checkpoint_scope
    scope = user.get('location_scope')
    if scope:
        return {'facility_id': None, 'region_id': None, 'district_id': None, 'scope_type': 'legacy_checkpoint', 'location_scope': scope}

    return {'facility_id': None, 'region_id': None, 'district_id': None, 'scope_type': 'none'}
