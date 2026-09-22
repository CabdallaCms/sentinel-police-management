# Foundation Assessment — Quick Summary for Reviewers

**Date:** 2026-09-22  
**Branch:** `arena/01a0c448-sentinel-police-management`  
**Task:** Architectural Audit & Foundation Assessment for Enterprise Scaling

---

## TL;DR

- **Are units and permissions hardcoded?** **YES, heavily.** Roles like `CheckpointSouth`, `CheckpointEast`, `CheckpointWest` are hardcoded strings in `ROLE_MODULES`, `ROLE_LOCATION_SCOPE`, `CHECKPOINT_LOCATIONS`. Geography like `STATION_REGIONS = ('Sool','Sanaag','East Togdheer')` and `STATION_DISTRICTS` dict are hardcoded Python tuples. Adding a new station, district, or checkpoint branch currently requires code change.
- **Is foundation flexible enough for Region → District → Station/Branch via FKs?** **PARTIALLY.** `police_stations` table exists with region/district/village TEXT columns and is FK-linked from officers/vehicles/crime_incidents. But those region/district columns are TEXT, not FK to regions/districts tables. `locations` table exists but only for South/East/West directional checkpoints, not geographic. `users.branch` is TEXT, not FK.
- **Can we provision new station with zero code changes today?** **NO.** You would need to edit `STATION_REGIONS`, `STATION_DISTRICTS`, `ROLE_MODULES`, `ALL_ROLES`, frontend hardcoded station list, and redeploy.

---

## Current State — What Works

| Area | Status | Details |
|------|--------|---------|
| Police Stations table | ✅ Exists | `police_stations` with region/district/village, tier, commander_id FK, operational_status |
| Officer → Station link | ✅ FK | `officers.station_id` REFERENCES `police_stations(id)` |
| Vehicle → Station link | ✅ FK | `vehicles.station_id` |
| Crime → Station link | ✅ FK | `crime_incidents.station_id` |
| RBAC infrastructure | ✅ Sophisticated | Alias normalization, read-only global Commander, module gating, location_scope column |
| HQ oversight | ✅ Works | `chief_commander` has global read-only, sees all data |
| Conduct actions | ✅ Station-aware | `officer_conduct_actions.station_id` FK |

## Current State — What’s Missing / Hardcoded

| Area | Status | Details |
|------|--------|---------|
| Regions table | ❌ Missing | No `regions` table; `STATION_REGIONS` tuple hardcoded in server.py |
| Districts table | ❌ Missing | No `districts` table; `STATION_DISTRICTS` dict hardcoded |
| Villages table | ❌ Missing | No villages table; village is free TEXT |
| Facility abstraction | ❌ Missing | No generic `facilities` table for CID branches, Fingerprint branches, Airport branches, Checkpoints |
| Airport branches | ❌ Missing | Airport is single global role, no branch concept |
| CID branches | ❌ Missing | CID is single global role, no Erigavo CID, Lasanod CID |
| Fingerprint branches | ❌ Missing | Same — single global |
| Checkpoint geographic | ❌ Directional only | `CHECKPOINT_LOCATIONS = ('South','East','West')` not geographic like “Lasanod Checkpoint” |
| User → Station FK | ❌ Missing | `users.branch` is TEXT, not FK; no `users.facility_id` |
| Roles table | ❌ Missing | Roles are hardcoded constants, not DB table |
| Permissions table | ❌ Missing | `ROLE_MODULES` is static dict |
| Frontend station list | ❌ Hardcoded | `index.html` has hardcoded JS array of 8 stations |
| Zero-code provisioning | ❌ Not possible | Requires code edit + redeploy for new district/station/role |

---

## Operational Model Gaps

### 1. STATIC / GLOBAL HQ OFFICES
- **Requirement:** Central Police Registration Office and Central Vehicle Police Car Registration are single, national-level, never scale.
- **Current:** Implicitly via `SystemAdmin` role, not explicit DB entities. Works but should be explicit facilities with `is_global=true` for auditability.
- **Gap:** LOW

### 2. EXPANDING SPECIALIZED UNITS & BRANCHES
- **Requirement:** CID, Fingerprint, Airport expand into regional branches (Lasanod Airport, Buhoodle Airport, Erigavo CID, etc.)
- **Current:** No branch table. Single global roles. `airport_passengers` has no `facility_id`.
- **Gap:** HIGH — Biggest blocker. Need `facilities` with type `AIRPORT_BRANCH`, `CID_BRANCH`, `FINGERPRINT_BRANCH`.

### 3. STATION & CHECKPOINT MANAGEMENT
- **Requirement:** Local Police Stations (multiple per district) and Checkpoints (multiple per region/district) with dedicated user accounts, HQ oversight.
- **Current:** Stations table exists, crime incidents scoped to station — good. Checkpoints are directional not geographic, no FK. Users not linked to stations.
- **Gap:** MEDIUM-HIGH — Station side halfway, checkpoint side not, user assignment missing.

---

## Proposed Clean Model

### Core Tables
1. **regions** (id, code, name) — Sool, Sanaag, East Togdheer + future
2. **districts** (id, region_id FK, code, name) — Laascaanood, Taleh, Hudun, Erigavo, Lasqoray, Badhan, Buuhoodle, etc.
3. **villages** (id, district_id FK, name)
4. **facility_types** (id, code, name, category: STATIC_HQ, SPECIALIZED_BRANCH, STATION, CHECKPOINT)
5. **facilities** (id, facility_id human readable, name, code, facility_type_id FK, region_id FK, district_id FK, village_id FK, parent_facility_id self-FK, tier, status, commander_id FK, etc.)
6. **users** + facility_id FK, region_id FK, district_id FK, role_id FK
7. **user_facility_assignments** (user_id, facility_id) for multi-facility
8. **roles**, **permissions**, **role_permissions**, **user_roles** — DB-driven RBAC

### Provisioning Workflow (Zero Code)
```
Admin creates Region (Sool) → 
Admin creates District (Taleh under Sool) → 
Admin creates Facility (Taleh Police Station, type=POLICE_STATION, region=Sool, district=Taleh) → 
Admin creates User (taleh.station, role=station_officer, facility_id=Taleh Station) → 
User logs in, sees only Taleh data, HQ sees all.
```

No code change, no redeploy.

---

## Roadmap (Phased)

- **Phase 0 (Done):** Audit & docs — this branch
- **Phase 1 (Week 1-2):** Geography Foundation — regions, districts, villages tables, seed Sool/Sanaag/East Togdheer districts
- **Phase 2 (Week 2-3):** Facility Abstraction — facility_types, facilities, migrate police_stations → facilities, add facility_id to operational tables
- **Phase 3 (Week 3-4):** RBAC Decoupling — roles, permissions tables, generic roles + facility assignment, facility_scope() replaces checkpoint_scope()
- **Phase 4 (Week 4-5):** Provisioning UI — admin pages for regions/districts/facilities/users, frontend loads facilities from API not hardcoded JS
- **Phase 5 (Week 5-6):** Data Scoping & HQ Oversight — middleware enforces facility/region/district filter, HQ bypasses
- **Phase 6 (Week 6-7):** Deprecation — remove hardcoded tuples, branch TEXT, location_scope TEXT
- **Phase 7 (Future):** Hierarchy, geospatial, multi-facility, offline sync

---

## Honest Grade

- Static HQ Offices: 8/10
- Expanding Specialized Units: 3/10
- Station & Checkpoint Management: 5/10
- Overall Enterprise Readiness: 4/10 — Needs refactor before scaling

**Recommendation:** Do NOT scale by adding more hardcoded tuples/roles. Invest 4-6 weeks in Phase 1-3 foundation refactor. After that, new stations/branches/checkpoints become zero-code admin operation.

---

## Files in This Branch

- `docs/ARCHITECTURAL_AUDIT_AND_ROADMAP.md` — Full 300+ line audit with code references, ER diagram, risk matrix
- `docs/ENTERPRISE_DATA_MODEL_PROPOSAL.sql` — Proposed SQL schema with seed examples for Sool/Sanaag/East Togdheer
- `docs/FOUNDATION_ASSESSMENT_SUMMARY.md` — This quick summary

All pushed strictly to feature branch, not merged to main.

---

*End of Summary*
