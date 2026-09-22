# Enterprise Scaling Refactor — Zero-Code Provisioning Prototype

**Branch:** `arena/enterprise-scaling-refactor`  
**Build Tag:** `sentinel-enterprise-scaling-refactor-v1`  
**Date:** 2026-09-22  
**Status:** Prototype — ready for review, NOT merged to main

## Problem Statement

The original Sentinel model had a hardcoded geography:

- `STATION_REGIONS = ('Sool','Sanaag','East Togdheer')`
- `STATION_DISTRICTS = { Sool: (Laascaanood, Caynabo, ...) }`
- Officers, stations, crimes stored `region` as TEXT, not FK
- Adding a new region/district/station required code change and redeploy

Requirement: Admins must be able to dynamically add regions, districts, station/checkpoint/airport/CID branches via DB/UI without writing code.

## Solution — Dynamic Relational Model

### New Tables (backend/enterprise.py ENTERPRISE_SCHEMA)

```
regions(id, code UNIQUE, name UNIQUE, description, is_active, created_by, created_at)
districts(id, region_id FK -> regions, code UNIQUE, name, UNIQUE(region_id,name), is_active, created_by, created_at)
villages(id, district_id FK -> districts, name, village_type, UNIQUE(district_id,name), is_active, created_by, created_at)
facility_types(id, code UNIQUE, name, category ENUM(STATIC_HQ, SPECIALIZED_BRANCH, STATION, CHECKPOINT), description, is_global BOOL, is_active)
facilities(id, facility_id UNIQUE, name, code UNIQUE, facility_type_id FK, region_id FK, district_id FK, village_id FK, parent_facility_id FK self, station_tier, operational_status, contact_phone, cell_capacity, commander_id FK officers, deputy_id FK officers, is_active, notes, created_by, legacy_region/district/village)
user_facility_assignments(id, user_id FK users, facility_id FK facilities, is_primary BOOL, assigned_at, assigned_by, UNIQUE(user_id,facility_id))
```

Plus ALTER columns on existing tables:
- `users.facility_id, region_id, district_id, village_id, role_id`
- `police_stations.facility_id`
- `officers.facility_id`
- `crime_incidents.facility_id`
- `checkpoint_events.facility_id`
- `vehicles.facility_id`
- `airport_passengers.facility_id`
- `clearance_applications.facility_id`
- `crime_cases.facility_id`

### Facility Types Seed

| Code | Name | Category | is_global | Description |
|------|------|----------|-----------|-------------|
| CENTRAL_REGISTRATION | Central Police Registration Office | STATIC_HQ | true | Single national-level, never scales |
| CENTRAL_VEHICLE | Central Vehicle Police Car Registration | STATIC_HQ | true | Single national-level |
| CID_BRANCH | CID Branch | SPECIALIZED_BRANCH | false | Regional CID branches (Erigavo CID, Lasanod CID) |
| FINGERPRINT_BRANCH | Fingerprint Branch | SPECIALIZED_BRANCH | false | Regional fingerprint branches |
| AIRPORT_BRANCH | Airport Branch | SPECIALIZED_BRANCH | false | Lasanod Airport, Buuhoodle Airport, etc. |
| POLICE_STATION | Local Police Station | STATION | false | Multiple per district |
| CHECKPOINT | Checkpoint | CHECKPOINT | false | Multiple per region/district |

Categories enforce scaling rules: STATIC_HQ never requires region/district; others do.

### Code Generation — Zero-Code Provisioning

**Region code:** First 3 letters upper, e.g., `SOL` for Sool, auto-increments if collision `SOL2`.

**District code:** `{region_code}-{3-letter}`, e.g., `SOL-TAL` for Taleh in Sool.

**Facility code:** `{region_code}-{district_suffix}-{type_suffix}-{NNN}`, e.g.:
- `SOL-TAL-ST-001` = Sool, Taleh, Station #1
- `SAN-ERI-CID-001` = Sanaag, Erigavo, CID Branch #1
- `ETG-BUH-AP-001` = East Togdheer, Buuhoodle, Airport Branch #1

Type suffix mapping:
- POLICE_STATION → ST
- CHECKPOINT → CP
- AIRPORT_BRANCH → AP
- CID_BRANCH → CID
- FINGERPRINT_BRANCH → FP
- CENTRAL_REGISTRATION → CR
- CENTRAL_VEHICLE → CV

Facility ID: `FAC-YYYY-NNNN` or type-specific prefix (`ST-YYYY-NNNN`, `AP-YYYY-NNNN`, etc.), auto-incremented.

All generation is server-side, no client input required — true zero-code provisioning.

### API Endpoints (Admin-only RBAC: requires admin module / stations:manage)

**Regions**
- `GET /api/regions?q=...` → list, filter by search
- `GET /api/regions/<id|code>` → detail + district_count + facility_count + districts list
- `POST /api/regions` {name, code?, description?} → create
- `PATCH /api/regions/<id|code>` {name?, code?, description?, is_active?}

**Districts**
- `GET /api/districts?region_id=...&q=...` → list filtered by region
- `GET /api/districts/<id|code>` → detail + facility_count
- `POST /api/districts` {name, region_id|region (code/name/id), code?, description?}
- `PATCH /api/districts/<id|code>` {name?, code?, description?, is_active?, region_id?}

**Villages**
- `GET /api/villages?district_id=...&q=...`
- `GET /api/villages/<id|name>`
- `POST /api/villages` {name, district_id|district, village_type?}
- `PATCH /api/villages/<id>`

**Facility Types**
- `GET /api/facility-types` → items + categories
- `GET /api/facility-types/<code|id>`
- `POST /api/facility-types` {code, name, category, description?, is_global?}

**Facilities (core zero-code provisioning)**
- `GET /api/facilities?region=...&district=...&facility_type=...&category=...&q=...` → filtered list
- `GET /api/facilities/<facility_id|code|id>` → detail + assigned_users
- `GET /api/facilities/<ref>/assignments` → user assignments for facility
- `GET /api/facilities/<ref>/stats` → officers, crime_incidents, checkpoint_events, vehicles counts
- `POST /api/facilities` {
    name,
    facility_type: POLICE_STATION|CHECKPOINT|AIRPORT_BRANCH|CID_BRANCH|FINGERPRINT_BRANCH,
    region: id|code|name,
    district: id|code|name,
    village?: id|name (auto-creates if district exists),
    parent_facility?: id|code,
    station_tier?: Regional HQ|District HQ|Outpost|Checkpoint|Border Post|Branch Office|Sub-Station,
    operational_status?: Active|Inactive|Maintenance|Planned|Closed,
    contact_phone,
    cell_capacity?,
    notes?
  } → auto-generates facility_id and code (e.g., SOL-TAL-ST-001)
- `PATCH /api/facilities/<ref>` {name?, tier?, status?, phone?, cell_capacity?, notes?, is_active?, parent_facility_id?}
- `POST /api/facilities/<ref>/assign-user` {user_id|username, is_primary?} → assign user to facility, updates users.facility_id/region_id/district_id/village_id if primary, creates user_facility_assignments row

**User Facility Assignments**
- `GET /api/user-facility-assignments?user_id=...&facility_id=...`
- `POST /api/user-facility-assignments` {user_id, facility_id, is_primary?}
- `POST /api/facilities/<ref>/assign-user` (alias)

**Enterprise Overview**
- `GET /api/enterprise/overview` → {regions, districts, villages, facilities counts, by_category, by_region, by_type}

**User Management Extended**
- `POST /api/admin/users` now accepts `facility_id|facility` (code/facility_id/name) + `region_id|region` + `district_id|district` for zero-code provisioning on user creation. If facility provided, branch defaults to facility name, facility_id/region_id/district_id/village_id auto-populated, and user_facility_assignments row created as primary.
- `PATCH /api/admin/users/<id>` accepts `facility_id|facility` to reassign user to new facility (clears previous primary, updates FKs, creates assignment).

**Auth Enrichment**
- `require_auth()` now SELECTs facility_id/region_id/district_id/village_id/role_id with fallback for legacy DB, looks up primary user_facility_assignments, enriches with facility_code/name/type/category/region/district.
- `user_view()` merges `enterprise.facility_scope()`, surfaces facility_id/code/name/type/category, region_id/district_id/village_id/role_id, enterprise_scope/facility_scope, effective branch = facility_name if assigned.

### Zero-Code Provisioning Workflow (Admin)

1. **Create Region (if new):**
   ```
   POST /api/regions { "name": "Sool", "code": "SOL" } → { region: {id, code: SOL, name: Sool} }
   ```
   Already seeded: Sool (SOL), Sanaag (SAN), East Togdheer (ETG)

2. **Create District (if new):**
   ```
   POST /api/districts { "name": "Taleh", "region": "SOL" } → { district: {code: SOL-TAL, name: Taleh, region_id} }
   ```
   Seeded: Laascaanood, Taleh, Hudun, Caynabo, Boocame, Las Anod, Ceerigaabo, Lasqoray, Badhan, Dhahar, Ceel Afweyn, Garadag, Buuhoodle, Burao, Oodweyne

3. **Create Facility (station/checkpoint/airport/CID branch):**
   ```
   POST /api/facilities {
     "name": "Taleh Police Station",
     "facility_type": "POLICE_STATION",
     "region": "SOL",
     "district": "Taleh",
     "contact_phone": "+252 63 555 0001",
     "station_tier": "District HQ",
     "cell_capacity": 10
   }
   → { facility: {facility_id: "ST-2026-0001", code: "SOL-TAL-ST-001", name: "Taleh Police Station", region_id, district_id} }
   ```
   No code change needed. Code auto-generated.

4. **Assign User to Facility:**
   ```
   POST /api/facilities/SOL-TAL-ST-001/assign-user { "username": "taleh.officer", "is_primary": true }
   → { assigned: true, user_id, username, facility_id: SOL-TAL-ST-001, is_primary: true }
   ```
   Or on user creation:
   ```
   POST /api/admin/users {
     "username": "taleh.officer",
     "display_name": "Officer T. Taleh",
     "password": "ChangeMe123!",
     "role": "SystemAdmin",
     "facility_id": "SOL-TAL-ST-001"
   }
   ```

5. **User now logs in and sees facility-scoped data:**
   - `user_view` returns `facility_code`, `facility_name`, `facility_type`, `enterprise_scope: {facility_id, region_id, district_id, scope_type: facility}`
   - Future filtering (crimes, officers, checkpoints) can use `facility_id` FK instead of TEXT matching

### Migration & Backward Compatibility

- `migrate()` executes `ENTERPRISE_SCHEMA` first (CREATE TABLE IF NOT EXISTS), refreshes table list, then retries FK column adds after ensuring enterprise tables exist. `seed_enterprise()` idempotent (INSERT only if not exists).
- `init_db()` executes `ENTERPRISE_SCHEMA` before `migrate()` and seeds.
- Existing `police_stations` rows are migrated into `facilities` if facilities empty (preserves legacy region/district as legacy_* columns plus FK resolution).
- All enterprise FK columns added as nullable, so legacy rows remain valid.
- `require_auth()` has try/except fallback for DBs without enterprise columns.
- Facility code generation does not break existing station codes (`ST-001` style still valid, new codes use `SOL-TAL-ST-001` pattern).

### STATIC_HQ vs Expanding Units

- **STATIC_HQ** (Central Police Registration Office, Central Vehicle Police Car Registration): `is_global=true`, region/district nullable, single national-level, never scales geographically. Enforced in `create_facility()` — region/district not required for global types.
- **SPECIALIZED_BRANCH** (CID, Fingerprint, Airport): `is_global=false`, requires region/district, expands into regional branches (Lasanod Airport, Buhodle Airport, Erigavo CID). Can have `parent_facility_id` for hierarchy (e.g., Erigavo CID branch parent = Central CID HQ).
- **STATION & CHECKPOINT**: Multiple per district/region, each gets dedicated user account for local crime reports/operational data, National HQ retains real-time oversight via `facility_id` FK filtering.

### Testing — Zero-Code Provisioning Scenario

Manual test (requires PostgreSQL running with SENTINEL_DB_* env):

```bash
# 1. Login as admin
curl -X POST http://localhost:8001/api/login -H "Content-Type: application/json" -d '{"username":"admin","password":"ChangeMe123!"}'
# → token

# 2. Create new region (example: Bari)
curl -X POST http://localhost:8001/api/regions -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name":"Bari","code":"BAR","description":"Bari Region"}'

# 3. Create district in Bari
curl -X POST http://localhost:8001/api/districts -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name":"Bosaso","region":"BAR","code":"BAR-BOS"}'

# 4. Create Airport Branch in Bosaso
curl -X POST http://localhost:8001/api/facilities -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{
  "name": "Bosaso Airport Control",
  "facility_type": "AIRPORT_BRANCH",
  "region": "BAR",
  "district": "Bosaso",
  "contact_phone": "+252 90 1234567",
  "station_tier": "Branch Office"
}'
# → code BAR-BOS-AP-001, facility_id AP-2026-0001

# 5. Create user assigned to new facility
curl -X POST http://localhost:8001/api/admin/users -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{
  "username": "bosaso.airport",
  "display_name": "Officer Bosaso Airport",
  "password": "ChangeMe123!",
  "role": "AirportControl",
  "facility_id": "BAR-BOS-AP-001"
}'

# 6. Verify enterprise overview
curl http://localhost:8001/api/enterprise/overview -H "Authorization: Bearer <token>"

# 7. Verify facility assignments
curl http://localhost:8001/api/facilities/BAR-BOS-AP-001/assignments -H "Authorization: Bearer <token>"
```

Expected: No code change, no redeploy, new region/district/facility/user all via API.

### Files Changed

- `backend/enterprise.py` (new) — ENTERPRISE_SCHEMA, seed, CRUD, scope, views
- `backend/server.py` — import enterprise, BUILD_TAG v1, ADDED_COLUMNS with facility FKs, migrate/init_db enterprise wiring, require_auth enrichment, user_view enterprise fields, GET/POST/PATCH routes for regions/districts/villages/facility-types/facilities/assignments/overview, admin user creation/patch with facility support

### Future Work (Not in Prototype)

- Frontend UI for enterprise provisioning (Region → District → Facility wizard)
- Facility-scoped filtering for crimes/officers/checkpoints/vehicles (use facility_id FK in queries)
- Migration of legacy `police_stations.region` TEXT to `facilities.region_id` FK for all queries
- Role hierarchy: facility commander vs deputy permissions
- Analytics by facility/region (reuse existing analytics builders but group by facility_id)
- Soft-delete vs hard-delete for facilities (currently is_active flag)
- Audit trail for enterprise provisioning (already via audit_events CREATE region/district/facility)

### Security & RBAC

- All enterprise write endpoints require `admin` module (SystemAdmin) or `stations:manage` permission (currently admin-only)
- Read endpoints require authentication but no extra module gate (any authenticated user can list regions/districts/facilities — needed for dropdowns)
- Commander / High Command (read-only) blocked by global firewall on POST/PATCH (403)
- Facility assignment updates users.facility_id which is used in facility_scope() for future row-level filtering

### How to Run

```bash
# Set PostgreSQL env in .env at project root:
# SENTINEL_DB_NAME=sentinel_police
# SENTINEL_DB_USER=postgres
# SENTINEL_DB_PASSWORD=...
# SENTINEL_DB_HOST=localhost
# SENTINEL_DB_PORT=5432

python3 backend/server.py
# → build sentinel-enterprise-scaling-refactor-v1
# → enterprise tables created, seeded with Sool/Sanaag/East Togdheer + 15 districts + 7 facility types
# → 8 legacy police_stations migrated to facilities
```

Then open http://localhost:8001 and use API or future UI.

## Conclusion

Prototype satisfies zero-code provisioning:

- Admin creates Region → District → Facility (station/checkpoint/airport/CID branch) via API without code
- Facility code auto-generated as `{region}-{district}-{type}-{NNN}` (e.g., SOL-TAL-ST-001)
- User assigned to facility via API, no code
- National HQ retains oversight via facility_id FK
- STATIC_HQ stays single national-level, SPECIALIZED_BRANCH expands regionally, STATION/CHECKPOINT multiple per district
- Fully backward compatible with existing TEXT-based region model
- Ready for review on `arena/enterprise-scaling-refactor`, NOT merged to main
