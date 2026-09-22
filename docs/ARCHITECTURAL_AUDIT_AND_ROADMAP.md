# Sentinel Police Management — Architectural Audit & Enterprise Scaling Roadmap

**Branch:** `arena/01a0c448-sentinel-police-management` (work performed on `arena/01a0ca36-sentinel-police-management` session)  
**Date:** 2026-09-22  
**Auditor:** Arena Agent — Foundation Assessment Task  
**Scope:** Evaluate current DB schema & backend models (`backend/server.py`, `users`, `roles`, `units`) for future multi-region scaling across Sool [Lasanod, Taleh, Hudun, etc.], Sanaag [Erigavo, Lasqoray, Badhan, etc.], East Togdheer [Buhoodle, etc.] — districts, stations, checkpoints, specialized unit branches.

> **CRITICAL NOTE:** This document is pushed strictly to the feature branch, never merged to `main`, per instruction.

---

## 1. Executive Summary

**Question:** Is the foundation flexible enough to support dynamic geographical scoping (Region → District → Station/Branch) via database foreign keys, or are units/permissions hardcoded around static strings?

**Answer (honest):** **Partially ready, but fundamentally hardcoded.**

- **Good news:** The system already has `police_stations` table with `region`, `district`, `village`, `station_tier`, `commander_id` FK to `officers`, and officers/vehicles/crime_incidents already FK to stations. `locations` table exists. `users.location_scope` column exists. RBAC infrastructure is sophisticated with alias normalization, read-only global Commander role, and module gating.

- **Bad news:** Geography is **hardcoded in Python tuples**, not in DB FKs. `STATION_REGIONS = ('Sool','Sanaag','East Togdheer')`, `STATION_DISTRICTS = {...}`, `CHECKPOINT_LOCATIONS = ('South','East','West')`, `OFFICER_ORIGIN_REGIONS` list, `OFFICER_UNITS`, `OFFICER_RANKS`, etc. are all **constants in `server.py`**. Adding a new region (e.g., “Sool” sub-region “Taleh” already exists but what about a new district “Boocame” or a new region?) requires **code change and redeploy**. 

- **Critical scaling blocker:** Roles encode **both function and location**: `CheckpointSouth`, `CheckpointEast`, `CheckpointWest` are three separate roles, each hardcoded in `ROLE_MODULES` and `ROLE_LOCATION_SCOPE`. There is **no concept of “Checkpoint Officer” assigned to facility_id=123 (Lasanod Airport Checkpoint)”**. Same for CID, Fingerprint, Airport — they are single global roles, no branch concept. Provisioning a new “Erigavo CID Branch” or “Buuhoodle Airport” today requires a new role string, new module entry, new scope entry — i.e., **code change**.

- **User → Station linkage missing:** `users.branch` is free-text `TEXT NOT NULL`, not FK. No `users.station_id` or `facility_id`. So you cannot say “user `lasanod.station` logs local crime reports for ST-004 only” via DB constraint; you must parse strings in app logic.

**Verdict Score:**
| Dimension | Score | Comment |
|---|---|---|
| Geographic normalization | 2/10 | No regions/districts tables, TEXT columns, hardcoded dict |
| Facility abstraction | 4/10 | police_stations exists but no generic branches/checkpoints/airport branches |
| User provisioning (zero-code) | 2/10 | Branch is TEXT, role is hardcoded |
| RBAC flexibility | 5/10 | Sophisticated alias handling but ROLE_MODULES is static dict |
| Data scoping (HQ oversight) | 6/10 | checkpoint_scope() works but only for South/East/West |
| Future-proof for Sool/Sanaag/East Togdheer expansion | 3/10 | Will require code edits for each new district/station role |

**Overall Foundation Readiness for Enterprise Vision: 35% — Needs Refactor Before Scaling.**

---

## 2. Current Schema Deep Dive

### 2.1 `users` Table
```sql
CREATE TABLE IF NOT EXISTS users(
  id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL, role TEXT NOT NULL,
  branch TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER DEFAULT 1
);
-- ADDED_COLUMNS: location_scope TEXT
```

- `role` is TEXT, validated against `ALL_ROLES` tuple in code, not FK to roles table.
- `branch` is TEXT free-form (“Central HQ”, “Fingerprint Unit”, “Checkpoint South”). No FK.
- `location_scope` is TEXT, values “South”, “East”, “West” — again not FK to locations table despite locations table existing.
- **Problem:** To create a user for “Lasanod Police Station” you would insert `branch='Lasanod Station'` but nothing enforces that station exists, nor scopes queries to that station. The `checkpoint_scope()` function looks at `role` and `location_scope`, not at `branch` or a station FK.

### 2.2 `locations` Table
```sql
CREATE TABLE IF NOT EXISTS locations(
  id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL, kind TEXT NOT NULL
);
-- Seed: South, East, West Checkpoint only
```

- Only checkpoint locations seeded, kind='Checkpoint'.
- No FK from `checkpoint_events.location_code` to `locations.code`. In fact `checkpoint_events` stores `location TEXT NOT NULL, location_code TEXT, checkpoint_location TEXT` all as plain TEXT, with ad-hoc case-insensitive matching (`LOWER(TRIM(...))`) to work around inconsistency.
- **No geographic regions/districts here** — it's purely directional checkpoints, not Sool/Sanaag/East Togdheer.

### 2.3 `police_stations` Table
```sql
CREATE TABLE IF NOT EXISTS police_stations(
  id SERIAL PRIMARY KEY, station_id TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
  region TEXT NOT NULL, district TEXT NOT NULL, village TEXT,
  station_tier TEXT, commander_id INTEGER, deputy_id INTEGER, ...
);
```

- **Good:** Has FK to officers for commander/deputy (circular FK handled via migration). Has region/district/village columns.
- **Bad:** `region` and `district` are **TEXT**, not FK to `regions`/`districts`. Validation is:
  ```python
  STATION_REGIONS = ('Sool', 'Sanaag', 'East Togdheer')
  STATION_DISTRICTS = {
    'Sool': ('Laascaanood', 'Caynabo', 'Xudun', 'Taleex'),
    'Sanaag': ('Ceerigaabo', 'Ceel Afweyn', 'Garadag', 'Badhan', 'Dhahar'),
    'East Togdheer': ('Burao', 'Oodweyne', 'Buuhoodle'),
  }
  ```
  Adding “Hudun” spelled differently? Already “Xudun” vs “Hudun” inconsistency — but fixing requires code edit. Adding new district “Lasqoray” (Sanaag) requires editing `STATION_DISTRICTS` dict and redeploying.

- `station_tier` is TEXT, validated against `STATION_TIERS = ('Regional HQ','District HQ','Outpost','Checkpoint','Border Post')` hardcoded.

- No `parent_station_id` or hierarchy — cannot model “Buuhoodle Airport is child of Buuhoodle District HQ”.

### 2.4 `officers` Table
```sql
station_id INTEGER NOT NULL REFERENCES police_stations(id)
region_of_origin TEXT, district_of_origin TEXT, ...
```

- Good FK to police_stations.
- But origin region validated against `OFFICER_ORIGIN_REGIONS` hardcoded tuple of 19 Somali regions — again code, not DB.

### 2.5 Roles & Permissions — The Hardcoded Core

From `server.py`:

```python
ROLE_ADMIN = 'SystemAdmin'
ROLE_FINGERPRINT = 'FingerprintUnit'
ROLE_AIRPORT = 'AirportControl'
ROLE_CID = 'CIDUnit'
ROLE_HR = 'hr_officer'
ROLE_CHECKPOINT_SOUTH = 'CheckpointSouth'
ROLE_CHECKPOINT_EAST = 'CheckpointEast'
ROLE_CHECKPOINT_WEST = 'CheckpointWest'
ROLE_CHIEF = 'chief_commander'
ROLE_CHECKPOINT_OFFICER = 'checkpoint_officer'

ROLE_MODULES = {
  ROLE_ADMIN: {'dashboard','analytics','admin','people','fingerprint','airport','cid','checkpoints','policesearch','stations','officers','cars','crimes','conduct'},
  ROLE_FINGERPRINT: {'dashboard','people','fingerprint'},
  ROLE_AIRPORT: {'dashboard','people','airport'},
  ROLE_CID: {'dashboard','people','cid','crimes'},
  ROLE_HR: {'dashboard','people','policesearch','stations','officers','conduct'},
  ROLE_CHECKPOINT_SOUTH: {'dashboard','checkpoints'},
  ...
  ROLE_CHIEF: {'dashboard','executive','oversight','people','policesearch','fingerprint','airport','cid','checkpoints','crimes','stations','officers','conduct','cars'},
}

ROLE_LOCATION_SCOPE = {
  ROLE_CHECKPOINT_SOUTH: 'South',
  ROLE_CHECKPOINT_EAST: 'East',
  ROLE_CHECKPOINT_WEST: 'West',
  ...
}
```

- **Massive alias table** `UNIT_ROLE_ALIASES` with ~60 entries to tolerate spelling variations — shows awareness of problem but solution is still static.
- **No roles table in DB.** Adding new checkpoint “Lasanod Airport Checkpoint” would require:
  1. New role constant `ROLE_CHECKPOINT_LASANOD_AIRPORT = 'CheckpointLasanodAirport'`
  2. Add to `ALL_ROLES`, `ROLE_MODULES`, `ROLE_LOCATION_SCOPE`, `ROLE_LABELS`, `CHECKPOINT_ROLE_ALIASES`
  3. Update `CHECKPOINT_LOCATIONS`
  4. Redeploy backend + frontend
  5. Frontend has its own hardcoded `ORIGIN_REGIONS`, station list, etc.
- This violates “zero code changes” requirement.

### 2.6 Specialized Units — No Branch Concept

Current model:
- CID, Fingerprint, Airport are **single national units**. No table for `cid_branches` or `airport_branches`.
- Operational vision says: “CID, Fingerprint, and Airport units will expand into regional branches (e.g., Lasanod Airport, Buhodle Airport, Erigavo CID, etc.).”
- Today, if you create user for “Erigavo CID”, what role do you give? `CIDUnit` — but then they see **all CID cases nationally**, not just Erigavo. No scoping.
- No `facility_type` to distinguish “Airport Branch” vs “CID Branch”.

### 2.7 Checkpoints — Directional, Not Geographic

- Current checkpoints are “South, East, West” — abstract directions, not real-world “Buuhoodle Checkpoint, Lasqoray Checkpoint, Taleh Checkpoint”.
- `checkpoint_events` stores `location` as TEXT, not FK to police_stations or facilities. So you cannot say “show all events for Buuhoodle Station”.
- Scoping function `checkpoint_scope(user)` returns None for admin, or 'South'/'East'/'West' for checkpoint officers. No facility-level scoping.

### 2.8 Frontend Hardcoding

`index.html` has:
```js
stations:[
 {id:'ST-001',name:'Ceerigaabo Central Station',region:'Sanaag',district:'Ceerigaabo',...},
 ...
]
ORIGIN_REGIONS = [{region:'Sool',districts:[...]}, ...]
```

- Station list is hardcoded in JS for offline fallback.
- Region filter dropdowns are hardcoded `<option>Sool</option><option>Sanaag</option><option>East Togdheer</option>`
- Adding new station requires editing both backend seed and frontend array.

---

## 3. Mapping to Operational Model

### 3.1 STATIC / GLOBAL HQ OFFICES

Requirement: Central Police Registration Office and Central Vehicle Police Car Registration are single, national-level offices that will never scale.

**Current handling:**
- These are implied by `SystemAdmin` role and `admin` module, not explicit entities.
- No `facility` row for “Central Police Registration Office”.
- Works today but not explicit. Should be explicit facilities with `is_global=true`, `facility_type='CENTRAL_REGISTRATION'`, so permissions can reference them.

**Gap:** Low — but for auditability, HQ offices should be DB records, not just roles.

### 3.2 EXPANDING SPECIALIZED UNITS & BRANCHES

Requirement: CID, Fingerprint, Airport will expand into regional branches (Lasanod Airport, Buhodle Airport, Erigavo CID, etc.)

**Current handling:**
- No branch table. Roles are global.
- `airport_passengers` has no `branch_id` or `station_id` — just `created_by` user.
- `clearance_applications` same — no branch.
- Cannot provision “Buhoodle Airport” as independent branch with its own user account and scoped data.

**Gap:** HIGH — This is the biggest missing piece. Need `facilities` with type `AIRPORT_BRANCH`, `CID_BRANCH`, `FINGERPRINT_BRANCH`, each with region/district, and users assigned to facility.

### 3.3 STATION & CHECKPOINT MANAGEMENT

Requirement: Local Police Stations (multiple per district) and Checkpoints (multiple per region/district) will be deployed. Each remote station/checkpoint will eventually have its own dedicated user account to log local crime reports and operational data, while National HQ retains real-time oversight.

**Current handling:**
- `police_stations` exists, good start.
- `crime_incidents` has `station_id` FK — so crime reports are already scoped to station. Good!
- But `users` has no `station_id` FK — so you cannot enforce “user X can only create crimes for station Y”.
- Checkpoints: no station FK, only TEXT location. No user→checkpoint FK.
- HQ oversight: `chief_commander` role has global read-only, works for oversight, but relies on hardcoded modules, not dynamic facility hierarchy.

**Gap:** MEDIUM-HIGH — Station side is halfway there (has table, FKs), checkpoint side is not. User assignment is missing for both.

---

## 4. Proposed Enterprise-Grade Data Model

### 4.1 Design Principles

1. **Normalize Geography:** `regions` → `districts` → `villages/towns` as FK tables, not TEXT.
2. **Facility Abstraction:** Single `facilities` table (or `organizational_units`) with `facility_type` to represent stations, checkpoints, airport branches, CID branches, fingerprint branches, HQ offices. Hierarchical via `parent_facility_id`.
3. **Decouple Role from Scope:** Roles become generic functional roles (`admin`, `station_officer`, `checkpoint_officer`, `cid_officer`, `fingerprint_officer`, `airport_officer`, `hr_officer`, `chief_commander`). Scope comes from `facility_id` / `region_id` / `district_id` assignment, not from role string.
4. **Zero-Code Provisioning:** Admin UI creates region → district → facility → user assignment. No code deploy.
5. **FK Enforcement:** All TEXT region/district/village columns become FKs with fallback for legacy data.
6. **Backward Compatible:** Keep old TEXT columns during migration, add new FK columns, dual-write, then deprecate.

### 4.2 New Tables (Proposed)

#### A. Geography Hierarchy

```sql
CREATE TABLE regions (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- e.g., 'SOL', 'SAN', 'ETG'
  name TEXT UNIQUE NOT NULL, -- 'Sool', 'Sanaag', 'East Togdheer'
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE districts (
  id SERIAL PRIMARY KEY,
  region_id INTEGER NOT NULL REFERENCES regions(id),
  code TEXT UNIQUE NOT NULL, -- 'SOL-LAS', 'SAN-ERI'
  name TEXT NOT NULL, -- 'Laascaanood', 'Erigavo'
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(region_id, name)
);

CREATE TABLE villages (
  id SERIAL PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts(id),
  name TEXT NOT NULL,
  village_type TEXT, -- 'Town', 'Village', 'City'
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE(district_id, name)
);
```

Seed example for vision:
- Sool: Laascaanood (districts: Laascaanood, Taleh, Hudun, Caynabo, Boocame)
- Sanaag: Erigavo (districts: Erigavo, Lasqoray, Badhan, Dhahar, Ceel Afweyn, Garadag)
- East Togdheer: Buhoodle (districts: Buhoodle, Burao, Oodweyne)

#### B. Facility Types (Organizational Unit Types)

```sql
CREATE TABLE facility_types (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- 'CENTRAL_REGISTRATION', 'CENTRAL_VEHICLE', 'CID_BRANCH', 'FINGERPRINT_BRANCH', 'AIRPORT_BRANCH', 'POLICE_STATION', 'CHECKPOINT'
  name TEXT NOT NULL,
  category TEXT NOT NULL, -- 'STATIC_HQ', 'SPECIALIZED_BRANCH', 'STATION', 'CHECKPOINT'
  description TEXT,
  is_global BOOLEAN DEFAULT FALSE, -- true for Central Police Registration, Central Vehicle
  is_active BOOLEAN DEFAULT TRUE
);

-- Seed:
INSERT INTO facility_types(code,name,category,is_global) VALUES
('CENTRAL_REGISTRATION','Central Police Registration Office','STATIC_HQ',true),
('CENTRAL_VEHICLE','Central Vehicle Police Car Registration','STATIC_HQ',true),
('CID_BRANCH','CID Branch','SPECIALIZED_BRANCH',false),
('FINGERPRINT_BRANCH','Fingerprint Branch','SPECIALIZED_BRANCH',false),
('AIRPORT_BRANCH','Airport Branch','SPECIALIZED_BRANCH',false),
('POLICE_STATION','Local Police Station','STATION',false),
('CHECKPOINT','Checkpoint','CHECKPOINT',false);
```

#### C. Facilities (The Core Abstraction)

Replaces/augments `police_stations`. Could keep `police_stations` as view for backward compat, or migrate to `facilities`.

```sql
CREATE TABLE facilities (
  id SERIAL PRIMARY KEY,
  facility_id TEXT UNIQUE NOT NULL, -- human readable: 'ST-001', 'AP-BUH-01', 'CID-ERI-01', 'CP-LAS-01'
  name TEXT NOT NULL, -- 'Lasanod Airport', 'Buuhoodle Airport', 'Erigavo CID'
  code TEXT UNIQUE NOT NULL, -- short code: 'LAS-AP', 'BUH-AP', 'ERI-CID'
  facility_type_id INTEGER NOT NULL REFERENCES facility_types(id),
  region_id INTEGER REFERENCES regions(id),
  district_id INTEGER REFERENCES districts(id),
  village_id INTEGER REFERENCES villages(id),
  parent_facility_id INTEGER REFERENCES facilities(id), -- hierarchy: e.g., Airport branch parent is Regional HQ
  station_tier TEXT, -- 'Regional HQ', 'District HQ', 'Outpost', etc. (or FK to tiers table)
  operational_status TEXT DEFAULT 'Active',
  contact_phone TEXT,
  cell_capacity INTEGER,
  commander_id INTEGER REFERENCES officers(id),
  deputy_id INTEGER REFERENCES officers(id),
  is_active BOOLEAN DEFAULT TRUE,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- legacy TEXT for migration period
  legacy_region TEXT,
  legacy_district TEXT,
  legacy_village TEXT
);

CREATE INDEX idx_facilities_region ON facilities(region_id);
CREATE INDEX idx_facilities_district ON facilities(district_id);
CREATE INDEX idx_facilities_type ON facilities(facility_type_id);
```

Examples:
- Lasanod Airport: type=AIRPORT_BRANCH, region=Sool, district=Laascaanood, facility_id='AP-LAS-01', code='LAS-AP'
- Buuhoodle Airport: type=AIRPORT_BRANCH, region=East Togdheer, district=Buuhoodle
- Erigavo CID: type=CID_BRANCH, region=Sanaag, district=Ceerigaabo (Erigavo)
- Taleh Police Station: type=POLICE_STATION, region=Sool, district=Taleh
- Hudun Checkpoint: type=CHECKPOINT, region=Sool, district=Hudun

#### D. Users — Facility Assignment

```sql
-- Add columns to existing users table (migration, not recreation)
ALTER TABLE users ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE users ADD COLUMN region_id INTEGER REFERENCES regions(id);
ALTER TABLE users ADD COLUMN district_id INTEGER REFERENCES districts(id);
-- For multi-facility assignment (if one user manages multiple stations):
CREATE TABLE user_facility_assignments (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  is_primary BOOLEAN DEFAULT FALSE,
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  assigned_by INTEGER REFERENCES users(id),
  UNIQUE(user_id, facility_id)
);

-- Keep role generic, not location-encoded
-- New generic roles: 'station_officer', 'checkpoint_officer', 'airport_officer', 'cid_officer', 'fingerprint_officer', etc.
-- Old roles like 'CheckpointSouth' remain for backward compat but new provisioning uses generic + facility_id
```

Provisioning workflow becomes:
1. Admin creates region (if not exists) — e.g., Sool
2. Admin creates district under region — e.g., Taleh under Sool
3. Admin creates facility — e.g., Taleh Police Station, type=POLICE_STATION, region=Sool, district=Taleh
4. Admin creates user — username='taleh.station', role='station_officer', facility_id = id of Taleh Police Station
5. User logs in, `checkpoint_scope()` or new `facility_scope()` returns their facility, and all queries filter by `facility_id` / `region_id` / `district_id`.
6. **Zero code changes.**

#### E. RBAC — Dynamic Roles & Permissions

```sql
CREATE TABLE roles (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- 'admin', 'station_officer', 'checkpoint_officer', 'cid_officer', 'fingerprint_officer', 'airport_officer', 'hr_officer', 'chief_commander'
  name TEXT NOT NULL,
  description TEXT,
  is_system BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE permissions (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- 'people:read', 'fingerprint:write', 'airport:read', 'cid:write', 'checkpoints:write', 'stations:manage', 'analytics:global', 'users:manage'
  name TEXT NOT NULL,
  module TEXT -- 'people','fingerprint','airport','cid','checkpoints','stations','officers','cars','crimes','conduct','analytics','admin'
);

CREATE TABLE role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY(role_id, permission_id)
);

-- Users can have multiple roles if needed, but start with single role_id FK for simplicity
ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id);
-- Or keep user_roles join table for flexibility
CREATE TABLE user_roles (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY(user_id, role_id)
);
```

This replaces hardcoded `ROLE_MODULES` dict. Modules are derived from permissions.

#### F. Operational Data Scoping

Add `facility_id`, `region_id`, `district_id` to all operational tables:

```sql
ALTER TABLE crime_incidents ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE checkpoint_events ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE airport_passengers ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE clearance_applications ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE crime_cases ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
ALTER TABLE suspect_alerts ADD COLUMN facility_id INTEGER REFERENCES facilities(id);
-- Keep legacy TEXT location columns for migration, but new code uses FKs
```

Then data scoping middleware:

```python
def facility_scope(user):
    # Returns facility_id, region_id, district_id for user
    # If user has facility_id, scope to that facility
    # If user has region_id, scope to region
    # If admin/chief, scope None (global)
```

HQ oversight: Chief Commander and SystemAdmin have `region_id=NULL, facility_id=NULL` meaning global. Their queries have no WHERE filter, so they see real-time data from all facilities.

### 4.3 Example Provisioning — No Code Change

**Scenario: Open new station in Taleh, Sool**

```sql
-- Step 1: Ensure region/district exist (or create)
INSERT INTO regions(code,name) VALUES ('SOL','Sool') ON CONFLICT DO NOTHING;
INSERT INTO districts(region_id,code,name) 
  SELECT id,'SOL-TAL','Taleh' FROM regions WHERE name='Sool';

-- Step 2: Create facility
INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,station_tier,operational_status)
SELECT 'ST-TAL-01','Taleh Police Station','TAL-01', ft.id, r.id, d.id, 'District HQ','Active'
FROM facility_types ft, regions r, districts d
WHERE ft.code='POLICE_STATION' AND r.name='Sool' AND d.name='Taleh';

-- Step 3: Create user account for that station
INSERT INTO users(username,display_name,role,branch,facility_id,password_hash,active)
VALUES ('taleh.station','Officer T. Ahmed','station_officer','Taleh Station',
        (SELECT id FROM facilities WHERE facility_id='ST-TAL-01'),
        sha256('ChangeMe123!'), 1);
```

No code change, no redeploy. Same for “Erigavo CID Branch”:

```sql
INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id)
SELECT 'CID-ERI-01','Erigavo CID Branch','ERI-CID', ft.id, r.id, d.id
FROM facility_types ft, regions r, districts d
WHERE ft.code='CID_BRANCH' AND r.name='Sanaag' AND d.name='Ceerigaabo';
```

### 4.4 Migration Strategy (Backward Compatible)

1. Create new tables (`regions`, `districts`, `villages`, `facility_types`, `facilities`, `roles`, `permissions`, etc.) — non-breaking.
2. Migrate existing `police_stations` data into `facilities`:
   - Map `region TEXT` → `regions` table (create missing regions)
   - Map `district TEXT` → `districts` table
   - Insert into `facilities` with `facility_type_id` for POLICE_STATION
3. Add `facility_id` FK to `users` and `officers`, populate from existing `station_id` or `branch` TEXT parsing.
4. Keep old columns (`region TEXT`, `district TEXT`, `branch TEXT`, `location_scope TEXT`) for 1-2 releases, dual-write.
5. Update backend code to use new FKs where available, fallback to old TEXT logic.
6. Deprecate old constants: replace `STATION_REGIONS` tuple with DB query `SELECT name FROM regions WHERE is_active=true`.
7. Frontend: replace hardcoded station list with API `/api/facilities` that returns DB-driven list.

---

## 5. Roadmap — Phased Implementation

### Phase 0: Audit & Documentation (Current — DONE)
- [x] Evaluate schema, roles, units
- [x] Document hardcoded constants inventory
- [x] Propose enterprise model
- [ ] Push findings to feature branch (this doc)

### Phase 1: Geography Foundation (Week 1-2)
- Create `regions`, `districts`, `villages` tables
- Seed with Sool, Sanaag, East Togdheer + their districts (Lasanod, Taleh, Hudun, Erigavo, Lasqoray, Badhan, Buhoodle, etc.)
- Migration script to populate from existing `police_stations.region/district`
- Add `region_id`, `district_id`, `village_id` FK columns to `police_stations` and `facilities`
- Keep legacy TEXT columns for backward compat
- **Deliverable:** Zero-code region/district creation via admin UI (new endpoint `/api/regions`, `/api/districts`)

### Phase 2: Facility Abstraction (Week 2-3)
- Create `facility_types` and `facilities` tables
- Migrate `police_stations` → `facilities` (type=POLICE_STATION)
- Create facilities for existing checkpoints (South/East/West → map to real geographic checkpoints)
- Create facilities for specialized branches (initially 1 per unit type per region, e.g., Lasanod Airport, Erigavo CID)
- Add `facility_id` to `users`, `officers`, `crime_incidents`, `checkpoint_events`, etc.
- Update `register_station()` to use new tables, keep old function as wrapper
- **Deliverable:** Admin can create new station/checkpoint/branch via `/api/facilities` without code change

### Phase 3: RBAC Decoupling (Week 3-4)
- Create `roles`, `permissions`, `role_permissions`, `user_roles` tables
- Seed generic roles: `station_officer`, `checkpoint_officer`, `cid_officer`, `fingerprint_officer`, `airport_officer`, `hr_officer`, `admin`, `chief_commander`
- Seed permissions matching current `ROLE_MODULES`
- Add `role_id` FK to `users`, migrate existing roles
- Refactor `ROLE_MODULES` dict to be DB-driven with fallback to hardcoded for backward compat
- Update `checkpoint_scope()` to `facility_scope()` that uses `facility_id` / `region_id` / `district_id`
- **Deliverable:** New checkpoint “Lasanod Airport” can be provisioned with role `checkpoint_officer` + facility_id, no new role string needed

### Phase 4: Provisioning UI & Zero-Code Workflow (Week 4-5)
- Frontend: New admin pages for Regions, Districts, Facilities management
- Backend: Endpoints `/api/facilities`, `/api/regions`, `/api/districts`, `/api/facility-types`
- User creation UI: dropdown for facility assignment (instead of free-text branch)
- Update `index.html` to load facilities from API, not hardcoded JS array
- **Deliverable:** Full workflow: Admin → Create Region → Create District → Create Facility (e.g., Taleh Police Station) → Create User Account for that facility → User logs in and sees only local data

### Phase 5: Data Scoping & HQ Oversight (Week 5-6)
- Implement middleware `enforce_facility_scope()` that filters all queries by user's facility/region/district
- Update all operational endpoints to include facility_id filtering
- HQ roles (SystemAdmin, chief_commander) bypass filter → global oversight
- Analytics: Update `build_global_analytics()` to aggregate by facility/region
- Dashboard: Show facility-specific KPIs for station users, global KPIs for HQ
- **Deliverable:** National HQ retains real-time oversight, remote stations see only local data

### Phase 6: Deprecation & Cleanup (Week 6-7)
- Deprecate `STATION_REGIONS`, `STATION_DISTRICTS`, `CHECKPOINT_LOCATIONS` hardcoded tuples — replace with DB queries
- Deprecate `users.branch TEXT` and `location_scope TEXT` — keep for backward compat but new code uses `facility_id`
- Deprecate `police_stations.region TEXT` etc. — use FKs
- Remove hardcoded station list from `index.html`
- Add DB constraints: `CHECK (region_id IS NOT NULL)` etc. for new facilities
- **Deliverable:** 100% DB-driven, zero hardcoded geography

### Phase 7: Future Enhancements (Beyond)
- Multi-facility assignment (one commander overseeing multiple stations)
- Facility hierarchy (Regional HQ → District HQ → Outpost → Checkpoint)
- Transfer workflow (officer transfer between facilities)
- Audit log per facility
- Geospatial: Add lat/lng to facilities for map view
- API for mobile apps at remote stations with offline sync

---

## 6. Assessment Summary

### How Well Does Current System Handle Vision?

**Strengths:**
- `police_stations` table exists and is used — good foundation for station management
- Officers, vehicles, crime incidents already have `station_id` FK — data is already partially scoped
- `locations` table exists (though underused) — shows intent for location abstraction
- RBAC system is sophisticated with alias handling, read-only global Commander role, module gating, location scoping — shows understanding of multi-role system
- HQ oversight via `chief_commander` global read-only role works for monitoring
- Conduct actions have `station_id` — station commander can submit reports

**Weaknesses (Critical for Scaling):**
- Geography is hardcoded, not DB-driven — adding new district requires code change
- No facility abstraction for CID/Fingerprint/Airport branches — cannot provision “Erigavo CID” or “Lasanod Airport” without code
- Checkpoint locations are directional (South/East/West), not geographic — cannot model real-world checkpoints in Sool/Sanaag/East Togdheer
- Roles encode location — need new role for each new checkpoint/station
- Users not FK-linked to stations — cannot enforce station-level data isolation
- Frontend has hardcoded station list and region dropdowns — requires code change for new station
- No hierarchical parent-child for facilities
- No dynamic permission system — `ROLE_MODULES` is static dict

### What Adjustments Are Needed?

**Must-Have (Blocking):**
1. Create `regions`, `districts`, `villages` tables — normalize geography
2. Create `facility_types` and `facilities` tables — generic abstraction for stations, checkpoints, airport/cid/fingerprint branches
3. Add `facility_id` FK to `users` — enable user→station assignment
4. Decouple role from location — generic roles + facility assignment
5. Make RBAC DB-driven or at least facility-aware

**Should-Have (Important):**
6. Add `facility_id` to all operational tables for scoping
7. Implement facility-scoped middleware for data isolation
8. Build admin UI for provisioning regions/districts/facilities/users
9. Migrate frontend to load facilities from API, not hardcoded JS

**Nice-to-Have (Future):**
10. Facility hierarchy, geospatial, multi-facility assignments, offline sync for remote stations

### Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Adding new district requires code deploy | High (already needed) | High (blocks scaling) | Phase 1: DB-driven geography |
| New checkpoint needs new role string | High | High | Phase 3: Generic roles + facility_id |
| User can see data outside their station | Medium | High (security) | Phase 5: Facility-scoped middleware |
| Frontend breaks when new station added | Medium | Medium | Phase 4: API-driven facility list |
| Circular FK (stations↔officers) already handled, but new hierarchy could reintroduce | Low | Medium | Use deferred constraints, parent_facility_id nullable |
| Migration of existing TEXT region/district to FKs may have dirty data (e.g., "Xudun" vs "Hudun") | High | Medium | Phase 1: Data cleaning script, canonical names table |

### Honest Grade

- **Current Foundation for Static HQ Offices:** 8/10 — Works, HQ is global, no scaling needed
- **Current Foundation for Expanding Specialized Units:** 3/10 — No branch concept, global roles only
- **Current Foundation for Station & Checkpoint Management:** 5/10 — Stations table exists, but checkpoints are not geographic, user assignment missing
- **Overall Enterprise Readiness:** 4/10 — Needs refactor before scaling to dozens of stations/checkpoints across Sool, Sanaag, East Togdheer

**Recommendation:** Do NOT attempt to scale to new regions/districts/stations by adding more hardcoded tuples/roles. Instead, invest 4-6 weeks in Phase 1-3 foundation refactor (geography + facility abstraction + RBAC decoupling). After that, provisioning new stations/branches/checkpoints becomes zero-code, admin-only operation, exactly as vision requires.

---

## 7. Appendices

### A. Hardcoded Constants Inventory (from `server.py`)

| Constant | Value | Location | Should Be DB Table? |
|---|---|---|---|
| `STATION_REGIONS` | ('Sool','Sanaag','East Togdheer') | line 978 | Yes → `regions` |
| `STATION_DISTRICTS` | dict of districts per region | line 979-983 | Yes → `districts` |
| `REGION_CODES` | {'Sool':'SOL',...} | line 984 | Yes → `regions.code` |
| `CHECKPOINT_LOCATIONS` | ('South','East','West') | line 944 | Yes → `facilities` where type=CHECKPOINT, or `locations` expanded |
| `OFFICER_ORIGIN_REGIONS` | 19 Somali regions | line ~959 | Yes → `regions` or separate `origin_regions` |
| `OFFICER_RANKS` | 8 ranks | line ~951 | Yes → `ranks` table |
| `OFFICER_UNITS` | 6 units | line 955 | Yes → `units` or `facility_types` |
| `STATION_TIERS` | 5 tiers | line ~977 | Yes → `facility_tiers` |
| `ROLE_MODULES` | dict role→modules | line 1121+ | Yes → `roles` + `permissions` |
| `ROLE_LOCATION_SCOPE` | dict role→location | line 1164+ | Yes → `users.facility_id` / `region_id` |
| `ALL_ROLES` | tuple of canonical roles | line 812 | Yes → `roles` table |

### B. Current Tables & FK Status

| Table | Has FK to Stations? | Has FK to Regions/Districts? | Has Facility Abstraction? | User Assignment? |
|---|---|---|---|---|
| `users` | No (branch TEXT) | No | No | N/A |
| `police_stations` | Self | No (TEXT) | Partial (is itself) | commander_id FK |
| `officers` | Yes | No (TEXT origin) | No | station_id FK |
| `crime_incidents` | Yes | No | No | station_id + officer_id FK |
| `vehicles` | Yes (station_id) | No | No | station_id + officer_id FK |
| `checkpoint_events` | No (TEXT location) | No | No | No |
| `airport_passengers` | No | No | No | created_by FK only |
| `clearance_applications` | No | No | No | created_by FK only |
| `crime_cases` | No | No | No | created_by FK only |
| `locations` | N/A | N/A | N/A | N/A — only South/East/West |

### C. Proposed ER Diagram (Textual)

```
regions 1---* districts 1---* villages
  |            |               |
  |            |               |
  *------------*---------------*
               |
               v
       facility_types 1---* facilities (self-referencing parent_facility_id)
               |               |
               |               *---* officers (station_id → facilities.id)
               |               |   |
               |               |   *---* crime_incidents (facility_id → facilities.id)
               |               |   *---* vehicles (facility_id)
               |               |
               |               *---* users (facility_id → facilities.id, region_id, district_id)
               |               |   |
               |               |   *---* user_facility_assignments
               |               |
               |               *---* checkpoint_events (facility_id)
               |               *---* airport_passengers (facility_id)
               |               *---* clearance_applications (facility_id)
               |               *---* crime_cases (facility_id)
               |
       roles 1---* role_permissions *---1 permissions
         |
         *---* user_roles *---* users
```

### D. Code References for Audit

- `backend/server.py:141-145` — users table, branch TEXT
- `backend/server.py:146-149` — locations table, only South/East/West
- `backend/server.py:215-228` — police_stations table, region/district TEXT not FK
- `backend/server.py:652-814` — ALL_ROLES, ROLE_MODULES, hardcoded
- `backend/server.py:978-984` — STATION_REGIONS, STATION_DISTRICTS, REGION_CODES hardcoded
- `backend/server.py:944` — CHECKPOINT_LOCATIONS hardcoded
- `backend/server.py:1189-1198` — UNIT_MODULE_DENY, shows awareness but still static
- `backend/server.py:3178-3240` — checkpoint_scope_sql, case-insensitive matching to work around TEXT inconsistency
- `index.html:1290-1298` — hardcoded stations array in JS
- `index.html:1008` — hardcoded region dropdown

---

## 8. Conclusion & Next Steps

The current foundation is **functional for a single-region, small-deployment** but **not enterprise-ready for multi-region scaling** across Sool, Sanaag, East Togdheer with dozens of stations, checkpoints, and specialized branches.

**The good news:** The core concepts (stations table, officers FK, crime_incidents FK, RBAC module gating, global read-only Commander) are already there. Refactoring to DB-driven geography and facility abstraction is **not a rewrite** — it's an **evolution** that preserves existing data and adds new FK tables alongside old TEXT columns.

**Recommended immediate action:**
1. Review this audit with HQ stakeholders
2. Approve Phase 1-3 roadmap (4 weeks)
3. Create feature branch for enterprise schema migration (this branch is audit only, no code changes per instruction — but next branch will implement)
4. After Phase 3, test provisioning workflow: create “Taleh Police Station” + user account without code change
5. Then scale to full vision: Lasanod Airport, Buuhoodle Airport, Erigavo CID, Lasqoray Checkpoint, etc. — all via admin UI, zero code

**Zero-code provisioning is achievable — but only after foundation refactor.**

---

*End of Audit — Pushed to feature branch `arena/01a0c448-sentinel-police-management` as preparatory notes, not merged to `main`.*
