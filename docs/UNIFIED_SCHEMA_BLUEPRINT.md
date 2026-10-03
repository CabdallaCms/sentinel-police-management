# Sentinel Unified Platform — Schema & Scope Blueprint

Status: **locked for build** (decisions D1–D3 and T1–T3 confirmed 2026-10-01; see `LEGACY_AUDIT.md` §4.3–4.4).
Target database: PostgreSQL 14+ (verified on 16.2). No extensions required.

This blueprint is **executable**. `migrations/001_initial_schema.sql` creates the schema and seeds the official org tree as
data; `docs/blueprint/test_blueprint.py` proves the invariants (24 tests, all passing). The migration is the single source
of truth; this document explains it.

| File | Purpose |
|---|---|
| `migrations/001_initial_schema.sql` — Part 1 | Org tree, closure table, tree triggers, `move_unit()`, RBAC tables, **the scope engine**, audit, reference numbers, policy settings |
| `migrations/001_initial_schema.sql` — Part 2 | Domain tables with ownership columns, integrity guards, `person_timeline()`, `person_alert_flag()`, **row-level security** |
| `migrations/001_initial_schema.sql` — Part 3 | Unit types/rules, 37 permissions, 12 roles, policy settings, the official org tree as rows (+ a `schema_migrations` row) |
| `migrations/dev/001_demo_accounts.sql` | **Dev only.** The 9 legacy accounts as assignments; never applied to production |
| `docs/blueprint/test_blueprint.py` | Acceptance tests (run command in §10) |

---

## 1. The model in one page

```mermaid
erDiagram
    unit_types ||--o{ unit_type_rules : "allowed parent→child"
    unit_types ||--o{ org_units : typed
    org_units  ||--o{ org_units : parent_id
    org_units  ||--o{ org_unit_closure : "ancestor/descendant"
    users      ||--o{ user_assignments : has
    roles      ||--o{ user_assignments : "granted as"
    org_units  ||--o{ user_assignments : "at unit"
    roles      ||--o{ role_permissions : holds
    permissions||--o{ role_permissions : in
    persons    ||--o{ checkpoint_events : "global master record"
    org_units  ||--o{ checkpoint_events : unit_id
    org_units  ||--o{ airport_passengers : unit_id
    org_units  ||--o{ officers : unit_id
    org_units  ||--o{ clearance_applications : "intake_unit_id (filed) / owner_unit_id (national)"
    org_units  ||--o{ crime_cases : "owner_unit_id (CID)"
    org_units  ||--o{ conduct_actions : "officer_unit_id / owner_unit_id (HR)"
```

**Three ideas carry the whole design:**

1. **One tree, typed nodes.** HQ is the single root. Its children are the four national directorates *and* the regions. Regions contain districts; districts/regions contain stations, checkpoints and airports; directorates may contain bureaus. Node types and the legal parent→child shapes are **rows** (`unit_types`, `unit_type_rules`), not code.
2. **One place a user meets the tree: `user_assignments(user, role, unit, include_descendants)`.** Everything else (`users.branch`, `users.location_scope`, `CheckpointSouth/East/West`, the alias tables, the unit denylist) disappears.
3. **One question the whole platform asks:** *"does this user hold permission P on unit U?"* — answered by `authz_can()` for a point check and `authz_scope()` for a list filter, and backed by Postgres RLS so a forgotten `WHERE` cannot leak.

### 1.1 The seeded tree (reproduces the legacy world, as data)

```
HQ  Police HQ / Command
├── DIR-FP   Fingerprint & Clearance Directorate   service_key=fingerprint   (T3)
├── DIR-CID  Criminal Investigation Directorate    service_key=cid
├── DIR-HR   HR Directorate (Registration Office)  service_key=hr
├── DIR-TRN  Transport Directorate                 service_key=transport
├── SOOL     Sool ─ Laascaanood ▸ ST-004, ST-008, AP-LAA*, CP-SOUTH*, CP-EAST*, CP-WEST*   ─ Caynabo ▸ ST-003 ─ Xudun ─ Taleex
├── SANAAG   Sanaag ─ Ceerigaabo ▸ ST-001 ─ Badhan ▸ ST-002 ─ Ceel Afweyn ─ Garadag ─ Dhahar
└── ETOG     East Togdheer ─ Burao ▸ ST-005 ─ Oodweyne ▸ ST-006 ─ Buuhoodle ▸ ST-007
```
`*` placeholder district, see §8-O2/O3. The regions under HQ are **exactly** Sool, Sanaag and East Togdheer (asserted by a test). 32 units: 1 hq, 4 directorates, 3 regions, 12 districts, 8 stations, 3 checkpoints, 1 airport.

### 1.2 Legacy hardcoding → what replaces it

| Legacy limitation (audit §3.1) | Replacement |
|---|---|
| L1 `CHECKPOINT_LOCATIONS = ('South','East','West')` | `org_units` rows of `unit_type='checkpoint'`; `checkpoint_events.unit_id` FK, type enforced by `enforce_unit_type` |
| L2 roles `CheckpointSouth/East/West` | one role `checkpoint_officer` + an assignment at a checkpoint unit |
| L3 `canonical_location_scope`, `checkpoint_scope` | `authz_scope()` / `authz_can()` |
| L4 unused flat `locations` table | dropped; `org_units` |
| L5 three text location columns + `LIKE '%south%'` | `unit_id` FK (no string matching) |
| L6 `STATION_REGIONS/DISTRICTS` in Python **and** JS | region/district rows; API serves `GET /api/org/tree`; no constants in either language |
| L7 `new_station_code` `KeyError` | unit `code` is free data, unique; refs from `next_ref()` |
| L8 region/district as text | parent FK + closure |
| L9 analytics hardwired to 3 regions | `GROUP BY` ancestor at any depth via closure (§6) |
| L10 Hardcoded single-airport / "Las Anod, HQ" strings | read from the unit record |
| L11 `users.branch` free text | `user_assignments` |
| L12 static `ROLE_MODULES`, alias soup | `roles` / `permissions` / `role_permissions` rows; unknown role = no assignment = no powers |
| L13 no row-level scoping | `authz_*` + RLS on every domain table |
| L14 if/elif router | framework router + one `scope` dependency (§5) |
| L15 time-derived IDs | `next_ref()` (`ref_sequences`, atomic upsert) |
| `enforce_read_only()` special-case firewall | `roles.is_read_only` + DB guard trigger: a read-only role *cannot hold* a write permission |
| `UNIT_MODULE_DENY` denylist | absence of the permission (deny-by-default) |

---

## 2. Tree schema (`01_…sql` §A–B)

| Table | Key columns | Notes |
|---|---|---|
| `unit_types` | `code`, `label`, `is_geographic` | seed: hq, directorate, bureau, region, district, station, checkpoint, airport. Add `border_post` with one INSERT. |
| `unit_type_rules` | `(parent_type, child_type)` | legal shapes. Seeded: hq→{directorate,region}; directorate→bureau; bureau→bureau; region→{district,station,checkpoint,airport}; district→{station,checkpoint,airport}; station→{station,checkpoint}. |
| `org_units` | `parent_id`, `unit_type`, `code` (unique), `name`, `name_local`, `service_key`, `status` (`planned`/`active`/`inactive`), `depth`, `path`, `attrs jsonb` | single root enforced by partial unique index; `service_key` only on directorates (unique); sibling names unique. |
| `org_unit_closure` | `(ancestor_id, descendant_id, depth)` | includes self-rows. "Is X inside Y?" = one PK lookup. Chosen over `ltree` because it needs no extension and keeps FK integrity. |
| `org_unit_events` | `unit_id`, `action`, `old/new` | structure change log (create, move). |

**Guarantees enforced in the database** (tests `TestTree`): single root; illegal shapes rejected (`checkpoint` under HQ, `district` under a station…); `parent_id`/`unit_type` can't be edited except through `move_unit()`; `move_unit()` rewrites `path`, `depth` and closure for the whole subtree, refuses the root, own-subtree cycles and illegal shapes; closure always agrees with `path`.

**Attributes that don't need columns** live in `attrs` (station `tier`, `cells`, `village`; airport `iata`). Promote an attribute to a typed extension table (`station_profile`, `airport_profile`) only when you need to query or constrain it. The legacy `commander_id`, `deputy_id` and `contact_phone` fit a small `station_profile` table keyed by `unit_id`.

**Status semantics.** `planned` (not yet operating) and `inactive` (closed) units **take no new records** (`enforce_active_unit`) but all history stays readable and in scope. This is how a new airport can be staged before go-live.

---

## 3. RBAC schema (`01_…sql` §C)

| Table | Purpose |
|---|---|
| `permissions` | `module:action` codes with `is_write` and `scope_kind`: **`unit`** (checked against a tree node) or **`global`** (not tied to a unit: `person:search`, `person:create`, `person:update`, `person:merge`, `alert:check`, `vehicle:lookup`, `user:manage`). |
| `roles` | `is_read_only` (DB-guarded), `is_system`. |
| `role_permissions` | trigger forbids writes on a read-only role. |
| `user_assignments` | `(user, role, unit, include_descendants, valid_from, valid_until, revoked_at, granted_by)`; one live row per `(user, role, unit)`. Time-boxed and revocable. |
| `active_assignments` (view) | live = not revoked, within validity window, user `active`. All scope functions read only this view. |

### 3.1 Permission × role matrix (generated from the seeded migration)

● = role holds it, ✎ = write permission. *admin* = `system_admin`, *chief* = `chief_commander` (read-only), *region* = `regional_commander`, *st.cmd/st.off* = station commander/officer, *chkpt* = checkpoint officer, *finger* = fingerprint, *transp* = transport.

| permission | scope | W | admin | chief | region | st.cmd | st.off | chkpt | airport | finger | cid | hr | transp | u.admin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `airport:create` | unit | ✎ | ● |  |  |  |  |  | ● |  |  |  |  |  |
| `airport:view` | unit |  | ● | ● | ● |  |  |  | ● |  |  |  |  |  |
| `alert:check` | global |  | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |  |  |
| `alert:create` | unit | ✎ | ● |  |  |  |  |  |  |  | ● |  |  |  |
| `alert:view_detail` | unit |  | ● | ● |  |  |  |  |  |  | ● |  |  |  |
| `analytics:view` | unit |  | ● | ● | ● | ● |  |  |  |  | ● | ● |  |  |
| `assignment:manage` | unit | ✎ | ● |  | ● |  |  |  |  |  |  |  |  | ● |
| `audit:view` | unit |  | ● | ● | ● |  |  |  |  |  |  |  |  |  |
| `case:create` | unit | ✎ | ● |  |  |  |  |  |  |  | ● |  |  |  |
| `case:update` | unit | ✎ | ● |  |  |  |  |  |  |  | ● |  |  |  |
| `case:view` | unit |  | ● | ● |  |  |  |  |  |  | ● |  |  |  |
| `checkpoint:create` | unit | ✎ | ● |  |  |  |  | ● |  |  |  |  |  |  |
| `checkpoint:view` | unit |  | ● | ● | ● |  |  | ● |  |  |  |  |  |  |
| `clearance:approve` | unit | ✎ | ● |  |  |  |  |  |  | ● |  |  |  |  |
| `clearance:create` | unit | ✎ | ● |  |  | ● | ● |  |  | ● |  |  |  |  |
| `clearance:override_review_lock` | unit | ✎ | ● |  |  |  |  |  |  |  |  |  |  |  |
| `clearance:print` | unit | ✎ | ● |  |  |  |  |  |  | ● |  |  |  |  |
| `clearance:view` | unit |  | ● | ● | ● | ● | ● |  |  | ● |  |  |  |  |
| `conduct:review` | unit | ✎ | ● |  |  |  |  |  |  |  |  | ● |  |  |
| `conduct:submit` | unit | ✎ | ● |  | ● | ● |  |  |  |  |  |  |  |  |
| `conduct:view` | unit |  | ● | ● | ● | ● |  |  |  |  |  | ● |  |  |
| `incident:create` | unit | ✎ | ● |  |  | ● | ● |  |  |  | ● |  |  |  |
| `incident:view` | unit |  | ● | ● | ● | ● | ● |  |  |  | ● |  |  |  |
| `officer:create` | unit | ✎ | ● |  |  |  |  |  |  |  |  | ● |  |  |
| `officer:update` | unit | ✎ | ● |  |  |  |  |  |  |  |  | ● |  |  |
| `officer:view` | unit |  | ● | ● | ● | ● |  |  |  |  |  | ● |  |  |
| `person:create` | global | ✎ | ● |  |  | ● | ● | ● | ● | ● | ● |  |  |  |
| `person:merge` | global | ✎ | ● |  |  |  |  |  |  |  |  |  |  |  |
| `person:search` | global |  | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |  |
| `person:update` | global | ✎ | ● |  |  |  |  |  |  | ● |  |  |  |  |
| `unit:manage` | unit | ✎ | ● |  |  |  |  |  |  |  |  |  |  |  |
| `unit:view` | unit |  | ● | ● | ● | ● |  |  |  |  |  | ● | ● | ● |
| `user:manage` | global | ✎ | ● |  |  |  |  |  |  |  |  |  |  |  |
| `vehicle:create` | unit | ✎ | ● |  |  |  |  |  |  |  |  |  | ● |  |
| `vehicle:lookup` | global |  | ● | ● |  |  |  | ● |  |  |  |  | ● |  |
| `vehicle:update_alert` | unit | ✎ | ● |  |  |  |  |  |  |  |  |  | ● |  |
| `vehicle:view` | unit |  | ● | ● | ● | ● |  |  |  |  |  | ● | ● |  |
### 3.2 Legacy account → assignment

| Legacy user (role) | New assignment | `include_descendants` |
|---|---|---|
| `admin` (SystemAdmin) | `system_admin` @ `HQ` | yes |
| `chief` (chief_commander) | `chief_commander` @ `HQ` **(D2)** | yes |
| `fp.officer` | `fingerprint_officer` @ `DIR-FP` | yes |
| `cid.officer` | `cid_officer` @ `DIR-CID` | yes |
| `hr.officer` | `hr_officer` @ `DIR-HR` | yes |
| `ap.officer` | `airport_officer` @ `AP-LAA` | no (legacy was global because only one airport existed) |
| `cp.south` / `cp.east` / `cp.west` | `checkpoint_officer` @ `CP-SOUTH` / `CP-EAST` / `CP-WEST` | no |

Legacy "Central Police Search is denied to fingerprint/airport/CID" needs no denylist: those roles simply don't hold `officer:view`, `vehicle:view` or `unit:view` (asserted in `TestLegacyParity`).

---

## 4. The unified scope check (`01_…sql` §D)

```sql
authz_scope(user, perm)        -- SETOF unit_id : every unit where user holds perm   → list filters
authz_can(user, perm, unit)    -- boolean       : point check                          → detail views AND every write
authz_has(user, perm)          -- boolean       : global permissions                   → person:search, alert:check …
service_unit('fingerprint')    -- the national owner unit of a service
owning_service_unit(unit)      -- nearest ancestor-or-self directorate (NULL for geographic units)
can_grant(grantor, role, unit) -- delegated admin without privilege escalation
```

**Resolution rule.** `authz_can(u, P, X)` is true iff a *live* assignment exists for `u` whose role holds `P` and whose unit is `X` itself, or an ancestor of `X` when `include_descendants` is true. That is the whole rule. Deny by default: no assignment, expired, revoked, disabled user, unknown permission, `NULL` unit → false (all tested).

### 4.1 Who is scoped by what (ownership matrix)

| Record | Scope column | Read check | Create check | Update/approve check |
|---|---|---|---|---|
| `persons` | none (global) | `person:search` (global) | `person:create` (global) | `person:update` / `person:merge` (national role) |
| `checkpoint_events` | `unit_id` (type `checkpoint`) | `checkpoint:view` @ unit | `checkpoint:create` @ unit | — |
| `airport_passengers` | `unit_id` (type `airport`) | `airport:view` @ unit | `airport:create` @ unit | — |
| `crime_incidents` | `unit_id` (station/checkpoint/airport) | `incident:view` @ unit | `incident:create` @ unit | — |
| `officers` | `unit_id` | `officer:view` @ unit | `officer:create` @ unit | `officer:update` @ unit |
| `vehicles` | `unit_id` (fleet) / NULL (civilian) | `vehicle:view` @ unit **or** global `vehicle:lookup` | `vehicle:create` | `vehicle:update_alert` |
| `clearance_applications` **(T1)** | `intake_unit_id` + `owner_unit_id` (directorate or bureau) | `clearance:view` @ intake **or** owner | `clearance:create` @ **intake** | `clearance:approve` @ **owner** |
| `crime_cases`, `suspect_alerts` | `owner_unit_id` (CID or CID bureau) | `case:view` / `alert:view_detail` @ owner | `case:create` / `alert:create` @ owner | `case:update` @ owner |
| `conduct_actions` **(T2)** | `officer_unit_id` + `owner_unit_id` (HR) | `conduct:view` @ officer's unit **or** owner | `conduct:submit` @ **officer's unit** | `conduct:review` @ **owner** |

### 4.2 How the three confirmed rules fall out of the model (no special cases)

- **T1 — clearance files locally, approves nationally.** Filing is checked at `intake_unit_id`; approval at `owner_unit_id`. Assign `clearance:approve` only at `DIR-FP`. A bureau officer's assignment is *below* the directorate, so it does not cover the directorate: bureau staff can work cases at their bureau and **cannot approve nationally** (`test_directorate_bureau_inherits_national_service`). The row must also be structurally complete to be `Approved` (certificate number, signature, key id, reviewer) — enforced by a `CHECK`.
- **T2 — conduct filed only inside your own subtree.** Insert is checked against the *officer's* unit: a station commander can file for their station, a regional commander for any station beneath their region, nobody for another jurisdiction. Review requires `conduct:review` at the HR directorate (`test_conduct_filing_is_limited_to_own_subtree`).
- **T3 — directorates are root children.** `service_unit()`/`owning_service_unit()` give national services a stable owner without hardcoded IDs. `enforce_service_owner` guarantees a clearance is owned by the fingerprint directorate (or one of its bureaus), a case by CID, a conduct file by HR. Regional bureaus later are one INSERT under the directorate node, and the national officer covers them automatically.
- **D2 — Chief Commander.** One assignment `chief_commander @ HQ (descendants)`. The role holds every non-write permission and, by trigger, cannot hold a write one. The test walks **every unit × every read permission (must be true) and every write permission (must be false)**. Executive dashboards are simply `analytics:view` aggregates over `authz_scope()`.
- **D3 — global persons, scoped events, filtered timeline.** `person_timeline(viewer, person)` unions checkpoint, airport and clearance events and filters each by the viewer's scope; the Chief sees all four events, a South checkpoint officer only the South one (`test_person_timeline_is_scope_filtered`). Alert *existence* is exposed via `person_alert_flag()` (a `SECURITY DEFINER` boolean) while `suspect_alerts` rows stay invisible to anyone without `alert:view_detail` (`test_alert_flag_without_detail_leak`).

### 4.3 Defence in depth: row-level security

`02_…sql` enables RLS on all scoped tables with `SELECT` / `INSERT` / `UPDATE` policies built from the same `authz_can()`. The API sets `SELECT set_config('app.user_id', :id, true)` at the start of each request transaction (transaction-local, so it is safe with pooled connections) and connects as a **non-owner** role (`sentinel_app`; tests use `app_rw`). Consequences, all tested: a South officer's `SELECT *` returns only South rows; inserting an East row raises `InsufficientPrivilege`; a station officer's attempt to approve a clearance updates **0 rows**.

Owner/superuser connections bypass RLS, so use them only for migrations and background jobs — never for request handling. `person_alert_flag()` is `SECURITY DEFINER` and relies on the function owner (the table owner) bypassing RLS; do **not** `FORCE ROW LEVEL SECURITY` on `suspect_alerts` without reworking it.

---

## 5. Service-layer contract (framework-agnostic)

Every request handler follows the same four steps; this replaces the legacy per-route `if/elif` module gates.

```
1. authenticate           → user_id (reject if user inactive)
2. open txn; set_config('app.user_id', user_id, true)          # arms RLS
3. authorize explicitly   → LIST:  WHERE unit_id IN (SELECT authz_scope(:u,'<module>:view'))
                            ONE:   authz_can(:u,'<module>:<action>', <record's scope unit>) else 403
                            WRITE: authz_can(:u,'<module>:create', <target unit>) BEFORE insert
4. write audit_events (user_id, unit_id, action, entity, entity_id)
```

Notes:
- Do the explicit check in step 3 *and* keep RLS: the check gives a clean 403 and good messages; RLS is the safety net.
- A record's "scope unit" is the column in §4.1. Never accept `unit_id` from the client without `authz_can` on it.
- **Navigation** is derived, not declared: `GET /api/me` returns the user's assignments plus the set of permissions they hold anywhere; the UI shows a module iff the user holds one of its `*:view`/`*:create` permissions. Delete the JS role regexes and alias tables.
- **Review window**: read `policy_settings['clearance.review_window_hours']`; allow approval when `now() >= created_at + window` **or** the user holds `clearance:override_review_lock` @ owner. Keep the check in the service layer and in the UI badge, not in SQL.
- **Signing**: on approval, build the canonical certificate payload (ref, person ref, purpose, issued-at, issuing unit), sign it with the directorate key, store `certificate_signature` + `signing_key_id`, and expose a public verify endpoint. The schema guarantees you cannot persist `Approved` without them.
- **Person master writes**: wrap enrichment so each filled field inserts a `person_field_audit` row (user, unit). `person:merge` is global and should be held only by a national role.
- **Delegated admin**: `POST /assignments` must call `can_grant(actor, role, unit)`; this stops a regional commander granting a role that holds permissions they don't themselves hold, or granting outside their subtree.
- **Caching**: scope sets are small and change rarely. Cache `authz_scope` per `(user, perm)` for the request or a short TTL; invalidate on assignment or `move_unit()` changes.

---

## 6. Analytics on the tree

Replace per-region constants with the closure table, so any node (HQ → region → district → station) is a roll-up:

```sql
-- events per unit at depth N below a node the viewer may see
SELECT anc.id, anc.name, count(e.*) AS screenings
  FROM org_units anc
  JOIN org_unit_closure c ON c.ancestor_id = anc.id
  JOIN checkpoint_events e ON e.unit_id = c.descendant_id
 WHERE anc.unit_type = 'region'
   AND anc.id IN (SELECT authz_scope(:user, 'analytics:view'))
 GROUP BY anc.id, anc.name;
```
Swap `'region'` for `'district'` or `'station'` for a different level; add a new region and it appears in the dashboard with no code change. The Chief's Executive Dashboard and Stations Oversight pages become these queries under root scope.

---

## 7. Migration from the legacy PostgreSQL schema

Run as an ordered, idempotent job after `01–03` are applied (seed is for dev; production loads real units).

1. **Units.** For each distinct `police_stations.region` → `region` unit; each distinct `(region, district)` → `district` unit; each `police_stations` row → `station` unit (`code` = legacy `station_id`, e.g. `ST-004`; legacy `code` kept in `attrs.legacy_code`; `station_tier`, `cell_capacity`, `village`, `contact_phone`, commander/deputy into `attrs` or `station_profile`). Legacy `operational_status` maps `Active`→`active`, `Inactive`/`Maintenance`→`inactive`.
2. **Checkpoints.** One unit per legacy `locations` row (`South`/`East`/`West`). Their real parent district is unknown to the legacy data (§8-O2).
3. **Airport.** One airport unit (`Laascaanood Airport`, `AP-LAA`) under district *Laascaanood*, flagged `needs_relocation_review` (§8-O3).
4. **Backfill `unit_id`** — `checkpoint_events` via `location_code` → checkpoint unit (rows with an unrecognised location go to a review queue, not silently to "Other"); `airport_passengers` → the airport unit (`AP-LAA`); `officers`/`vehicles`/`crime_incidents`/`officer_conduct_actions` via `station_id` → the matching station unit; `clearance_applications.intake_unit_id` → the `DIR-FP` unit for historic rows (filing location was never recorded); `crime_cases`/`suspect_alerts` → `owner_unit_id` = CID default.
5. **People.** Copy `persons` 1:1 (keep `person_id` as `person_ref`). Where an `officers` row matches a person (national ID / name + DOB), set `officers.person_id`; otherwise leave NULL for HR to reconcile.
6. **Users.** Create users; **re-hash passwords** (legacy is unsalted SHA-256; force a reset instead of porting hashes). Convert each user's `(role, location_scope)` using §3.2; any role string not in the known set gets **no assignment** (fail closed — the opposite of the legacy fall-through bug).
7. **Reference numbers.** Seed `ref_sequences` from the highest legacy numbers per prefix/year; keep legacy IDs as the human refs where they exist.
8. **Verify.** Row counts per table before/after; every migrated row has a non-null scope unit; the tests in `test_blueprint.py` pass against the migrated database with the production seed swapped in.

Legacy columns not listed in `02_…sql` (guardian/traveller documents, victim fields, officer origin and guarantor data, vehicle owner data, evidence files) port 1:1 into typed columns or the `details jsonb` bucket; they carry no scoping logic. Uploaded files move behind **authenticated, scope-checked download endpoints**, not public `/uploads/` URLs.

---

## 8. Open items and recommended defaults

| # | Item | Recommended default |
|---|---|---|
| O1 | **`system_admin` currently holds every permission** (parity with legacy, including review-lock override). | Keep for cut-over, then split: `system_admin` = users/units/assignments only; operational permissions via explicit roles. Separation of duties. |
| O2 | **Real district of the South/East/West checkpoints.** Legacy data has no district; the seed places them under Laascaanood and flags `attrs.needs_relocation_review`. | Ops confirm, then `SELECT move_unit(<cp>, <real district>)`. All scope follows automatically. |
| O3 | **Operational district of the active airport.** Legacy data has no airport location. The seed places `AP-LAA` under Laascaanood (operational HQ) and flags `attrs.needs_relocation_review`. | Ops confirm, then `SELECT move_unit(<airport>, <real district>)`. The unit must stay within Sool, Sanaag or East Togdheer. |
| O4 | **Vehicle plate lookup is a *global* read.** RLS cannot hide columns, so `vehicle:lookup` holders can read all vehicle columns. | Expose lookups through a narrow view/endpoint returning plate, status and alert only. |
| O5 | **Alert visibility granularity.** Only a yes/no flag is exposed outside CID. | Confirm whether border units also need the alert *reason category*; if so, add a `person_alert_summary()` returning category only. |
| O6 | **Station extras** (`commander_id`, `deputy_id`, phone, cells). | Add `station_profile(unit_id PK, …)`; keep `attrs` for the rest. |
| O7 | **Closure vs `ltree`.** Closure chosen for portability. | Revisit only if the tree exceeds ~10⁵ nodes. Moves lock the subtree; do them rarely and in a transaction. |
| O8 | **Directorate regional bureaus.** Supported structurally. | Add per-directorate `unit_type_rules` only if a directorate needs a different shape from the generic `bureau`. |
| O9 | **Session/auth stack.** Out of scope here. | Use the unified codebase's auth (argon2/bcrypt, expiring tokens, revocation); this blueprint needs only `users.id` and `active`. |

---

## 9. Migration 002 — person identity (search + field immutability)

`migrations/002_person_identity.sql` extends the global `persons` registry: indexed fuzzy-search keys, `place_of_birth`,
a data-driven field policy (`person_field_policy`) enforced by the `persons_guard` trigger, guardian links, and the
`person:edit_core` / `person:update_dynamic` permissions. Design, legacy comparison, API and open items:
**[`IDENTITY_SERVICE.md`](IDENTITY_SERVICE.md)**.

---

## 9b. Migration 003 — operational units (checkpoints, airports, stations)

`migrations/003_operational_events.sql` hardens the three event tables created by 001: region scope from policy data
(Sool, Sanaag, East Togdheer), database-stamped provenance, append-only logs, a duplicate-airport unique index, incident
vocabularies, an optional victim registry link, and an `uploads` ownership table. Design, API, deliberate changes and
roadmap: **[`OPERATIONS.md`](OPERATIONS.md)**.

## 9c. Migration 004 — directorate services (clearance, CID, HR conduct, structure)

`migrations/004_directorate_services.sql`: review-window and immutability triggers on clearance, Ed25519 signing keys and
an append-only print log, case evidence, participant alerts, officer service history, conduct-driven rank/duty changes,
region helper functions (`unit_claimed_region`, `unit_region_name`, `unit_in_state`) and policy vocabularies. Design, API,
keys and roadmap: **[`DIRECTORATE.md`](DIRECTORATE.md)**.

---

## 10. Running the tests

```bash
# applying the migration to a real database (one transaction; the file has no BEGIN/COMMIT of its own):
psql "$DATABASE_URL" -1 -f migrations/001_initial_schema.sql
psql "$DATABASE_URL" -1 -f migrations/dev/001_demo_accounts.sql   # DEV ONLY

# acceptance tests — any PostgreSQL 14+ where you can CREATE DATABASE:
BLUEPRINT_PG_URI=postgresql://user:pass@host:5432/postgres python3 docs/blueprint/test_blueprint.py

# or with no server (embedded PostgreSQL):
pip install pgserver psycopg2-binary && python3 docs/blueprint/test_blueprint.py
```

Result at time of writing: `Ran 24 tests … OK` on PostgreSQL 16.2. The tests were also checked for sensitivity: deliberately breaking `include_descendants` handling, the read-only guard, and the clearance update policy each made the suite fail.

| Test class | What it pins |
|---|---|
| `TestTree` | single root, structure rules, closure = path, `move_unit` rewires scope, cycle/root/type rejection, `next_ref`, append-only audit |
| `TestCodeFreeExpansion` | new airport (Buuhoodle), new region/district/checkpoint, directorate bureau — all as plain INSERTs, no code |
| `TestScopeEngine` | RLS isolation, scope = subtree, **Chief read-only on every unit × permission**, fail-closed (unknown/disabled/expired/revoked), `include_descendants`, delegated-admin escalation |
| `TestNationalServices` | T1 clearance flow, scoped person timeline, alert flag without detail leak, CID ownership + incident escalation, T2 conduct filing/review, inactive units, fleet/lookup |
| `TestLegacyParity` | the nine legacy accounts keep equivalent powers; users with no assignment have none |

Port these assertions to the unified stack's own test runner as the permanent authorization regression suite, and add one HTTP-level test per route proving a request cannot cross a unit boundary.
