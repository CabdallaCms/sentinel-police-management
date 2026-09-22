-- Sentinel Police Management — Enterprise Data Model Proposal
-- For multi-region scaling: Sool [Lasanod, Taleh, Hudun, etc.], Sanaag [Erigavo, Lasqoray, Badhan, etc.], East Togdheer [Buhoodle, etc.]
-- Branch: arena/01a0c448-sentinel-police-management (audit preparatory notes, not merged to main)
-- Date: 2026-09-22
-- This file is a PROPOSAL, not yet applied — to be reviewed before implementation.
-- It is designed to be backward compatible with existing tables.

-- ============================================================================
-- 1. GEOGRAPHY HIERARCHY — Replaces hardcoded STATION_REGIONS / STATION_DISTRICTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS regions (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- e.g., 'SOL', 'SAN', 'ETG'
  name TEXT UNIQUE NOT NULL, -- 'Sool', 'Sanaag', 'East Togdheer'
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS districts (
  id SERIAL PRIMARY KEY,
  region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE RESTRICT,
  code TEXT UNIQUE NOT NULL, -- 'SOL-LAS', 'SAN-ERI', 'ETG-BUH'
  name TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  UNIQUE(region_id, name)
);

CREATE TABLE IF NOT EXISTS villages (
  id SERIAL PRIMARY KEY,
  district_id INTEGER NOT NULL REFERENCES districts(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  village_type TEXT, -- 'Town', 'Village', 'City', 'Settlement'
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  UNIQUE(district_id, name)
);

-- Seed for vision: Sool, Sanaag, East Togdheer with detailed districts
-- Sool: Lasanod, Taleh, Hudun, Caynabo, Boocame, etc.
-- Sanaag: Erigavo, Lasqoray, Badhan, Dhahar, Ceel Afweyn, Garadag, etc.
-- East Togdheer: Buhoodle, Burao, Oodweyne, etc.

INSERT INTO regions(code,name,description) VALUES
('SOL','Sool','Sool Region — Lasanod, Taleh, Hudun, Caynabo, Boocame'),
('SAN','Sanaag','Sanaag Region — Erigavo, Lasqoray, Badhan, Dhahar, Ceel Afweyn'),
('ETG','East Togdheer','East Togdheer — Buhoodle, Burao, Oodweyne')
ON CONFLICT(name) DO NOTHING;

-- Districts per region (expandable without code change)
INSERT INTO districts(region_id,code,name) 
SELECT r.id, 'SOL-LAS','Laascaanood' FROM regions r WHERE r.name='Sool' UNION ALL
SELECT r.id, 'SOL-TAL','Taleh' FROM regions r WHERE r.name='Sool' UNION ALL
SELECT r.id, 'SOL-HUD','Hudun' FROM regions r WHERE r.name='Sool' UNION ALL
SELECT r.id, 'SOL-CAY','Caynabo' FROM regions r WHERE r.name='Sool' UNION ALL
SELECT r.id, 'SOL-BOO','Boocame' FROM regions r WHERE r.name='Sool' UNION ALL
SELECT r.id, 'SAN-ERI','Ceerigaabo' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'SAN-LAS','Lasqoray' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'SAN-BAD','Badhan' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'SAN-DHA','Dhahar' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'SAN-CEEL','Ceel Afweyn' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'SAN-GAR','Garadag' FROM regions r WHERE r.name='Sanaag' UNION ALL
SELECT r.id, 'ETG-BUH','Buuhoodle' FROM regions r WHERE r.name='East Togdheer' UNION ALL
SELECT r.id, 'ETG-BUR','Burao' FROM regions r WHERE r.name='East Togdheer' UNION ALL
SELECT r.id, 'ETG-OOD','Oodweyne' FROM regions r WHERE r.name='East Togdheer'
ON CONFLICT(code) DO NOTHING;

-- ============================================================================
-- 2. FACILITY TYPES — Replaces hardcoded unit types, distinguishes STATIC_HQ vs BRANCHES
-- ============================================================================

CREATE TABLE IF NOT EXISTS facility_types (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL, -- 'STATIC_HQ', 'SPECIALIZED_BRANCH', 'STATION', 'CHECKPOINT'
  description TEXT,
  is_global BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

INSERT INTO facility_types(code,name,category,is_global,description) VALUES
('CENTRAL_REGISTRATION','Central Police Registration Office','STATIC_HQ',true,'Single national-level office, never scales geographically'),
('CENTRAL_VEHICLE','Central Vehicle Police Car Registration','STATIC_HQ',true,'Single national-level vehicle registration'),
('CID_BRANCH','CID Branch','SPECIALIZED_BRANCH',false,'Criminal Investigation Department regional branch, e.g., Erigavo CID, Lasanod CID'),
('FINGERPRINT_BRANCH','Fingerprint Branch','SPECIALIZED_BRANCH',false,'Fingerprint / Good Conduct regional branch'),
('AIRPORT_BRANCH','Airport Branch','SPECIALIZED_BRANCH',false,'Airport Control regional branch, e.g., Lasanod Airport, Buuhoodle Airport'),
('POLICE_STATION','Local Police Station','STATION',false,'Multiple per district across regions'),
('CHECKPOINT','Checkpoint','CHECKPOINT',false,'Multiple per region/district, e.g., Hudun Checkpoint, Lasqoray Checkpoint')
ON CONFLICT(code) DO NOTHING;

-- ============================================================================
-- 3. FACILITIES — Generic abstraction for stations, checkpoints, branches, HQ
--    Replaces/augments police_stations, enables zero-code provisioning
-- ============================================================================

CREATE TABLE IF NOT EXISTS facilities (
  id SERIAL PRIMARY KEY,
  facility_id TEXT UNIQUE NOT NULL, -- human readable: 'ST-001', 'AP-BUH-01', 'CID-ERI-01', 'CP-LAS-01', 'HQ-REG-01'
  name TEXT NOT NULL, -- 'Lasanod Airport', 'Buuhoodle Airport', 'Erigavo CID', 'Taleh Police Station'
  code TEXT UNIQUE NOT NULL, -- short code: 'LAS-AP', 'BUH-AP', 'ERI-CID', 'TAL-ST'
  facility_type_id INTEGER NOT NULL REFERENCES facility_types(id),
  region_id INTEGER REFERENCES regions(id),
  district_id INTEGER REFERENCES districts(id),
  village_id INTEGER REFERENCES villages(id),
  parent_facility_id INTEGER REFERENCES facilities(id), -- hierarchy: e.g., Buuhoodle Airport parent is Buuhoodle District HQ
  station_tier TEXT, -- 'Regional HQ', 'District HQ', 'Outpost', 'Checkpoint', 'Border Post' — could be FK to tiers table
  operational_status TEXT DEFAULT 'Active',
  contact_phone TEXT,
  cell_capacity INTEGER,
  commander_id INTEGER REFERENCES officers(id),
  deputy_id INTEGER REFERENCES officers(id),
  is_active BOOLEAN DEFAULT TRUE,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  -- legacy TEXT for migration period (backward compat)
  legacy_region TEXT,
  legacy_district TEXT,
  legacy_village TEXT
);

CREATE INDEX IF NOT EXISTS idx_facilities_region ON facilities(region_id);
CREATE INDEX IF NOT EXISTS idx_facilities_district ON facilities(district_id);
CREATE INDEX IF NOT EXISTS idx_facilities_type ON facilities(facility_type_id);
CREATE INDEX IF NOT EXISTS idx_facilities_parent ON facilities(parent_facility_id);

-- Migrate existing police_stations into facilities (example, to be run after tables created)
-- INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,station_tier,operational_status,contact_phone,cell_capacity,legacy_region,legacy_district,legacy_village)
-- SELECT ps.station_id, ps.name, ps.code, ft.id, r.id, d.id, ps.station_tier, ps.operational_status, ps.contact_phone, ps.cell_capacity, ps.region, ps.district, ps.village
-- FROM police_stations ps
-- JOIN facility_types ft ON ft.code='POLICE_STATION'
-- LEFT JOIN regions r ON r.name=ps.region
-- LEFT JOIN districts d ON d.name=ps.district AND d.region_id=r.id;

-- Example new facilities for vision (zero-code provisioning after model is live):
-- Lasanod Airport Branch
-- INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,operational_status)
-- SELECT 'AP-LAS-01','Lasanod Airport','LAS-AP', ft.id, r.id, d.id, 'Active'
-- FROM facility_types ft, regions r, districts d WHERE ft.code='AIRPORT_BRANCH' AND r.name='Sool' AND d.name='Laascaanood';

-- Buuhoodle Airport
-- INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,operational_status)
-- SELECT 'AP-BUH-01','Buuhoodle Airport','BUH-AP', ft.id, r.id, d.id, 'Active'
-- FROM facility_types ft, regions r, districts d WHERE ft.code='AIRPORT_BRANCH' AND r.name='East Togdheer' AND d.name='Buuhoodle';

-- Erigavo CID
-- INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,operational_status)
-- SELECT 'CID-ERI-01','Erigavo CID Branch','ERI-CID', ft.id, r.id, d.id, 'Active'
-- FROM facility_types ft, regions r, districts d WHERE ft.code='CID_BRANCH' AND r.name='Sanaag' AND d.name='Ceerigaabo';

-- ============================================================================
-- 4. USERS — Facility Assignment for Zero-Code Provisioning
-- ============================================================================

-- Add FK columns to existing users table (non-breaking migration)
-- These ALTERs are idempotent in proposal — actual migration script will check existence

-- ALTER TABLE users ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS region_id INTEGER REFERENCES regions(id);
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS district_id INTEGER REFERENCES districts(id);
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id);

-- For multi-facility assignment (one commander overseeing multiple stations)
CREATE TABLE IF NOT EXISTS user_facility_assignments (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  is_primary BOOLEAN DEFAULT FALSE,
  assigned_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),
  assigned_by INTEGER REFERENCES users(id),
  UNIQUE(user_id, facility_id)
);

-- ============================================================================
-- 5. RBAC — Dynamic Roles & Permissions (Replaces hardcoded ROLE_MODULES)
-- ============================================================================

CREATE TABLE IF NOT EXISTS roles (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- 'admin', 'station_officer', 'checkpoint_officer', 'cid_officer', 'fingerprint_officer', 'airport_officer', 'hr_officer', 'chief_commander'
  name TEXT NOT NULL,
  description TEXT,
  is_system BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS permissions (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL, -- 'people:read', 'fingerprint:write', 'airport:read', 'cid:write', 'checkpoints:write', 'stations:manage', 'analytics:global', 'users:manage', 'officers:manage', 'vehicles:read'
  name TEXT NOT NULL,
  module TEXT, -- 'people','fingerprint','airport','cid','checkpoints','stations','officers','cars','crimes','conduct','analytics','admin'
  description TEXT,
  created_at TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY(role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY(user_id, role_id)
);

-- Seed generic roles (decoupled from location)
INSERT INTO roles(code,name,description,is_system) VALUES
('admin','System Administrator','Full system access, HQ',true),
('station_officer','Station Officer','Local police station officer — scoped to assigned facility'),
('checkpoint_officer','Checkpoint Officer','Checkpoint officer — scoped to assigned checkpoint facility'),
('cid_officer','CID Officer','CID / Criminal Investigation — scoped to facility/region'),
('fingerprint_officer','Fingerprint Officer','Fingerprint / Good Conduct — scoped to facility/region'),
('airport_officer','Airport Officer','Airport Control — scoped to airport facility'),
('hr_officer','HR Directorate Officer','Police Officers Registration Office'),
('chief_commander','Chief Commander (HQ / Command)','Global read-only HQ oversight',true)
ON CONFLICT(code) DO NOTHING;

-- Seed permissions (mirroring current ROLE_MODULES)
INSERT INTO permissions(code,name,module) VALUES
('dashboard:read','View Dashboard','dashboard'),
('people:read','Central Person Search','people'),
('people:write','Manage Persons','people'),
('fingerprint:read','View Fingerprint Applications','fingerprint'),
('fingerprint:write','Manage Fingerprint Applications','fingerprint'),
('airport:read','View Airport Records','airport'),
('airport:write','Manage Airport Records','airport'),
('cid:read','View CID Cases','cid'),
('cid:write','Manage CID Cases','cid'),
('checkpoints:read','View Checkpoint Events','checkpoints'),
('checkpoints:write','Manage Checkpoint Events','checkpoints'),
('stations:read','View Police Stations','stations'),
('stations:manage','Manage Police Stations','stations'),
('officers:read','View Officers','officers'),
('officers:manage','Manage Officers','officers'),
('cars:read','View Vehicles','cars'),
('cars:manage','Manage Vehicles','cars'),
('crimes:read','View Crime Incidents','crimes'),
('crimes:write','Manage Crime Incidents','crimes'),
('conduct:read','View Conduct Actions','conduct'),
('conduct:manage','Manage Conduct Actions','conduct'),
('analytics:global','Global Executive Analytics','analytics'),
('users:manage','Manage Users','admin'),
('policesearch:read','Central Police Search (officers/stations/cars)','policesearch')
ON CONFLICT(code) DO NOTHING;

-- Example role_permissions mapping (to be refined)
-- Admin gets everything
-- INSERT INTO role_permissions(role_id,permission_id) SELECT r.id,p.id FROM roles r, permissions p WHERE r.code='admin';

-- ============================================================================
-- 6. OPERATIONAL DATA SCOPING — Add facility_id to all operational tables
-- ============================================================================

-- These ALTERs add facility scoping to existing operational tables
-- Keep legacy TEXT columns for migration period

-- ALTER TABLE crime_incidents ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE checkpoint_events ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE airport_passengers ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE clearance_applications ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE crime_cases ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);
-- ALTER TABLE officers ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id); -- alternative to station_id
-- ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS facility_id INTEGER REFERENCES facilities(id);

-- ============================================================================
-- 7. BACKWARD COMPATIBILITY VIEWS
-- ============================================================================

-- Keep police_stations as view for old code that queries police_stations
-- CREATE OR REPLACE VIEW police_stations AS
-- SELECT f.id, f.facility_id AS station_id, f.name, f.code, r.name AS region, d.name AS district, v.name AS village,
--        f.station_tier, f.commander_id, f.deputy_id, f.contact_phone, f.cell_capacity, f.operational_status, f.notes, f.created_by, f.created_at
-- FROM facilities f
-- JOIN facility_types ft ON ft.id=f.facility_type_id AND ft.code='POLICE_STATION'
-- LEFT JOIN regions r ON r.id=f.region_id
-- LEFT JOIN districts d ON d.id=f.district_id
-- LEFT JOIN villages v ON v.id=f.village_id;

-- ============================================================================
-- 8. EXAMPLE ZERO-CODE PROVISIONING WORKFLOW
-- ============================================================================

-- Scenario: Provision Taleh Police Station + user account

-- Step 1: Ensure geography exists
-- INSERT INTO regions(code,name) VALUES ('SOL','Sool') ON CONFLICT DO NOTHING;
-- INSERT INTO districts(region_id,code,name) SELECT id,'SOL-TAL','Taleh' FROM regions WHERE name='Sool' ON CONFLICT DO NOTHING;

-- Step 2: Create facility
-- INSERT INTO facilities(facility_id,name,code,facility_type_id,region_id,district_id,station_tier,operational_status)
-- SELECT 'ST-TAL-01','Taleh Police Station','TAL-01', ft.id, r.id, d.id, 'District HQ','Active'
-- FROM facility_types ft, regions r, districts d WHERE ft.code='POLICE_STATION' AND r.name='Sool' AND d.name='Taleh';

-- Step 3: Create user for that facility
-- INSERT INTO users(username,display_name,role,branch,facility_id,password_hash,active)
-- VALUES ('taleh.station','Officer T. Ahmed','station_officer','Taleh Station',
--         (SELECT id FROM facilities WHERE facility_id='ST-TAL-01'),
--         'hashed_password',1);

-- Step 4: User logs in, facility_scope() returns facility_id, all queries filtered
-- SELECT * FROM crime_incidents WHERE facility_id = (SELECT facility_id FROM users WHERE id = current_user_id);

-- HQ oversight: chief_commander has facility_id=NULL, sees all
-- SELECT * FROM crime_incidents; -- no filter for HQ

-- ============================================================================
-- END OF PROPOSAL
-- ============================================================================
