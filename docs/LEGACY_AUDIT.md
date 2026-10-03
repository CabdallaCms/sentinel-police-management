# Sentinel Police Management — Legacy Code & Structure Audit

Repository: `CabdallaCms/sentinel-police-management` @ `19cda80` (`main`, merge dated 2026-09-22)
Audit date: 2026-10-01 · Method: static read of every tracked file (23 files, ~21.8k lines). The app was **not** executed (no PostgreSQL / `psycopg2` in the audit sandbox), so runtime claims are drawn from code and the repo's own docs.

---

## 0. Executive summary (read this first)

1. **It is not a Django project.** There is no `manage.py`, no `models.py`, no `urls.py`, no template directory and no separate CSS/static tree. The stack is:
   - `backend/server.py` (6,172 lines): one Python-stdlib `BaseHTTPRequestHandler` with hand-rolled routing, auth, RBAC, validation, SQL and analytics, on PostgreSQL via `psycopg2`. Plus `backend/vehicles.py` (168 lines).
   - `index.html` (6,346 lines): a single-file SPA holding all CSS (lines 11–390), all markup (392–1273) and all JS (1273–6345), with no build step and no framework.
   - `application.html` and `certificate.html`: two standalone printable A4 documents. They only *mimic* Django syntax in comments (`{% static %}`, `{{ application.* }}`). They are bound client-side by `fetch()`.
   - So "Django templates" don't exist. The portable UI assets are the **CSS block, the page-section markup, the JS component functions and the two print documents**, all extracted from monoliths (§2).
2. **The "fantastic UX" is real and portable:** a design-token CSS system, grouped collapsible sidebar, KPI strip + full-width register + centered-modal pattern, a unified identity-matching form, read-only "view-only" mode, and the A4 Somali/Arabic/English print documents.
3. **Dynamic expansion is blocked in four places.** Checkpoints are literally three hardcoded locations (South/East/West) baked into **role names**. The Region→District gazetteer is hardcoded in both Python and JS. Users have no FK to any org unit. And, apart from checkpoints, **no list endpoint filters data by the caller's unit/region at all.**
4. **Module-level RBAC is excellent; data-level RBAC is almost absent.** Roles map to modules via static dicts. The only row-level scoping is `checkpoint_events`.
5. **Repo health caveats that affect porting:**
   - The SQLite→PostgreSQL migration is half-finished. `migrate_rbac.py`, `audit_instant_approvals.py` and `test_server.py` / `test_read_only_rbac.py` / `test_review_gate.py` still use `sqlite3`/`SENTINEL_DB`.
   - `backend/database.py` defines a **different, conflicting** schema (e.g. `officers.assigned_station TEXT`). Don't treat it as truth.
   - Uploads under `/uploads/` are served **without authentication**.
   - Passwords are unsalted SHA-256.
   - Sessions are bearer tokens with no expiry.
   - CORS is `*`.

---

## 1. Core module inventory

### 1.1 What the user listed vs. what actually exists

| Requested item | Reality in this repo |
|---|---|
| National Register Office | **No module by that name.** The nearest equivalent is the **Central Person Registry** (`persons`, ID `P-0001`). The "Registration Office" in the nav is the **police-officer HR register** (`officers`), not a national civil register. |
| Vehicle fleet | ✅ `vehicles` (police fleet + civilian), `backend/vehicles.py`; pages `cars`, `vehiclestatus` |
| CID units | ✅ as *functions*, not org units: Crime Unit (`crime_cases`, `suspect_alerts`, `case_evidence`), Crime intake (`crime_incidents`) |
| Fingerprint processing | ⚠️ **A clearance-certificate workflow only** (`clearance_applications`: apply → 12h review lock → approve → certificate no. → print). There is **no biometric capture, template storage or matching**. "Biometrics logged" in analytics is just a count of applications. |
| Airports | ⚠️ **One** passenger register (`airport_passengers`), labelled with a single hardcoded airport name. There is no airport entity. |
| Checkpoints | ✅ `checkpoint_events`, three fixed locations |
| Local police stations | ✅ `police_stations` (real DB rows, with tier/commander/cells/status) |

### 1.2 Full module list

| # | Module (nav label → page id) | Tables | Key code | Notes |
|---|---|---|---|---|
| 1 | Central Person Search → `people` | `persons` | `ensure_person`, `resolve_identity`, `upsert_person`, `find_by_id`; JS `identityFormHTML`/`wireIdentity` | 4-tier identity matching, fill-only enrichment |
| 2 | Central Police Search → `policesearch` | reads `officers`, `police_stations`, `vehicles` | JS `renderPoliceSearch`, `psLocMatch` | Region→District→Village filter |
| 3 | Fingerprint Unit → `fingerprint` | `clearance_applications` | `fingerprint_review_state`, approve route, `application.html`, `certificate.html` | 12h lock enforced in 3 places |
| 4 | Crime Unit (CID) → `cid`, `caseworkspace` | `crime_cases`, `suspect_alerts`, `case_evidence` | case workspace (3 tabs) | Suspects feed checkpoint/airport alerts |
| 5 | Checkpoint Unit → `checkpoints` | `checkpoint_events`, `locations` | `checkpoint_scope*`, JS `renderCheckpointTable` | Screens against active suspect alerts |
| 6 | Airport Unit → `airport` | `airport_passengers` | `/api/airport-records` | |
| 7 | Registration Office → `officers` | `officers` | `register_officer`, `officer_view` | 5-section form, photo/doc uploads |
| 8 | Conduct / Promotions / Discipline → `conduct` | `officer_conduct_actions`, `officer_service_history` (+ legacy `officer_promotions`, `officer_discipline`) | `submit_conduct_action`, `review_conduct_action` | Station commanders submit, HR reviews |
| 9 | Vehicle Registry / Status → `cars`, `vehiclestatus` | `vehicles` | `register_vehicle`, `update_vehicle_alert` | Plate/VIN lookup also used by checkpoints |
| 10 | Police Stations → `stations` | `police_stations` | `register_station`, `new_station_code` | |
| 11 | Register Crime → `crimes` | `crime_incidents` | `register_crime` | Station-anchored (FK) |
| 12 | Global Executive Dashboard → `executive` | read-only aggregates | `/api/analytics/global` | Chief Commander HQ view |
| 13 | Stations Oversight → `oversight` | read-only aggregates | same | HQ regional roll-up |
| 14 | User Management → `admin` | `users`, `sessions`, `audit_events` | `/api/admin/users*` | |
| 15 | Operations Dashboard → `dashboard` | cross-unit feed | `/api/dashboard` | Role-aware |

Cross-cutting: `audit_events` (written by every mutation); the 9 seeded demo users.

### 1.3 Static/global singletons vs. branch/region-hardcoded

**Global singletons: no branch/region column. One register for the whole country.**

| Module | Evidence |
|---|---|
| Persons | `persons` has no unit/region ownership. Genuinely central, which is correct. |
| Fingerprint / clearance | `clearance_applications` has no station/branch column. The UI sub-title is hardcoded to a single branch name ("Fingerprint Unit · …Branch") (`index.html:562`). The certificate hardcodes "Las Anod, HQ" and "Chief of Fingerprint Unit" (`certificate.html:284, 362`). |
| Airport | `airport_passengers` has no airport/location column. Hardcoded single-airport label (`index.html:600, 607`). |
| CID cases / suspects / evidence | `crime_cases.location` is free text. No unit/station FK. |
| HR conduct / officers roster | Global tables. `officers.station_id` is a FK (good), but nothing scopes *who may see/modify* which officers. |
| Users / audit | Global. |

**Hardcoded to specific branches/regions**

| Module | What is hardcoded |
|---|---|
| **Checkpoints** (the worst offender) | Exactly 3 locations: `South`/`East`/`West`. They are baked into role names (`CheckpointSouth/East/West`), the location scope, the DB seed, the UI chips, the dropdown and the analytics. See §3. |
| **Regions/districts (stations, officers, vehicles search, analytics)** | Sool / Sanaag / East Togdheer plus their districts, defined in Python *and* JS. See §3. |
| **Print documents** | Masthead and body text hardcode "Northeastern Police Force", "North East Police Force", "Waqooyi Bari State Police Force", code `PCC-2026-DIGITAL-01` and Somali/Arabic strings (`application.html:~160`, `certificate.html:~260–300`). |
| **Seed/demo data** | demo persons and a demo flight record, 8 stations, 9 users (`server.py:1823–1905`; JS offline DB `index.html:1274–1290`). |

**Already dynamic (keep): these are DB rows with FKs.**
`police_stations`, `officers.station_id`, `vehicles.station_id`, `crime_incidents.station_id`, `officer_conduct_actions.station_id`. This is the seed of the future tree: **a station is already a DB-driven unit.** The only problem is that its parents (region/district) are strings validated against a constant.

---

## 2. UI/UX & frontend assets catalogue

### 2.1 Where things live

| Asset | Location | Size | Portability |
|---|---|---|---|
| **Design tokens + all CSS** | `index.html:11–390` | ~380 lines | **High.** Lift verbatim into a stylesheet or design-system package. |
| **Login screen** | `index.html:393–415`, CSS `246–258` | | High |
| **Sidebar / shell / top bar** | `index.html:416–499`, CSS 360–376, 383 | | High (re-drive from tree, see §4) |
| **16 page sections** | `<section id="…" class="page">` at lines 500–1272 | | Medium: markup is portable, wiring is inline `onclick` + global state |
| **JS** | `index.html:1273–6345` (263 top-level functions) | ~5,000 lines | Mixed (see §2.3) |
| **Print: application** | `application.html` (A4, Somali, QAYBTA 01–04, watermark) | 526 lines | High after de-hardcoding text |
| **Print: certificate** | `certificate.html` (EN/AR letterhead, watermark, footer bar) | 496 lines | High after de-hardcoding text |
| **Emblem** | `images/police_logo.png` | 1.9 MB RGBA | Reuse; compress |
| **Print-fit tests** | `backend/test_print_fit.py` | 476 lines | High value. Pins A4 height budgets, watermark opacity band 0.08–0.12, and verbatim blueprint wording. |

There are no external CSS/JS/font/CDN dependencies. Only the font stack `Inter, system-ui…`; charts are hand-drawn on `<canvas>` (`drawBarChart`, `drawGroupedBarChart`, `drawRatioBar`).

### 2.2 Notable UX patterns worth porting

- **Design tokens:** `--navy #11233f`, `--blue #246bfe`, `--cyan #13b8a6`, plus red/amber/green. The shared components are `.card/.panel`, `.btn` variants, `.field`, `.table-wrap` (sticky header), `.badge`, `.tabs` and `.cmodal`.
- **Operational page recipe:** KPI strip (`renderUnitStats`) → searchable full-width table → single primary button → **centered modal** (`openEntryModal`/`closeEntryModal`) with a fixed header, scrolling body and sticky footer. The Escape key and backdrop click close it.
- **Error policy:** inline red alert inside modals, toast only for success.
- **Unified identity form + 4-tier matching:** exact ID, exact 4-part name + DOB, fuzzy warning, partial-name dropdown. Only non-empty matched fields are locked. Blank ones are enriched on save. (`identityFormHTML`, `wireIdentity`, `resolveIdentity`; server `resolve_identity`.)
- **Grouped collapsible sidebar** with section auto-hide when all items are hidden (`applyNavForRole`, `navItemAllowed`), persisted in `localStorage.sentinelNavGroups`.
- **Read-only "view-only" mode:** `body.readonly-mode`, `.write-action` / `data-write`, and the `hardenReadOnlyDom` MutationObserver sweep.
- **Reusable `locationDropdowns(prefix)`** cascading Region→District→Village control (`index.html:1638`). This is the best seed for a tree picker.
- **File-slot widgets** (`buildFileSlots`/`collectFiles`), the **12h review-lock badge** (`reviewLockState`), **officer 5-step form** (`offStep`), and **conduct review modal**.
- **Print contract:** `@page` A4, `print-color-adjust: exact`, chrome hidden on print.

### 2.3 UI ↔ audience mapping (HQ vs regional/unit)

| Audience | Pages | Gate |
|---|---|---|
| **HQ / Command** (read-only) | `executive` (Global Executive Dashboard), `oversight` (Stations Oversight & Regional Data), plus read access to every register | `chief_commander`, perms `analytics:global` + `readonly:global`. All writes return 403 (`enforce_read_only`). |
| **HQ / Central admin** | `admin` (User Management), `stations`/`cars` writes, all pages | `SystemAdmin` |
| **HQ directorates (national scope, not regional)** | `officers`, `conduct`, `policesearch` (HR); `fingerprint`; `cid` + `crimes`; `airport` | `hr_officer`, `FingerprintUnit`, `CIDUnit`, `AirportControl` |
| **Regional / site operations** | `checkpoints` only (South/East/West) | `CheckpointSouth/East/West` |

Important finding: **there is no regional-unit UI tier except Checkpoints.** There is no "Region admin", "District commander" or "Station commander" view. The README describes station commanders as submitters of conduct files, but `POST /api/conduct/submit` is open to *any authenticated user* (`server.py:~5340`) because no such role exists.

### 2.4 Front-end porting hazards

- **Global mutable state + inline handlers:** `db`, `currentUser`, `serverOn`, `onclick="…"` strings throughout.
- **Dual-mode "offline" fallback:** localStorage demo data and local re-implementations of server logic (`localResolveIdentity`, `execLocalFallback`, `renderDashboardLocal`, `buildLocalActivity`). Drop it. It duplicates the business rules and will diverge.
- **Role logic duplicated in JS:** `normalizeRole`, `isChiefRole`, `unitFamily`, `sanitizeModules`, `deniedModulesForRole`, `scopeFromRole`. The server already returns `modules`, `permissions`, `read_only`, `location_scope`. Use those only.
- **Stale-build/self-heal scaffolding** (`checkBackendBuild`, `backendIsStale`, `sentinel-ui-build` meta, `restart-8001.*`): operational scar tissue from a stale-process incident. Do not port.

---

## 3. Architectural limitations (exact locations)

### 3.1 Hardcoded branches/districts

| # | Limitation | Exact location(s) |
|---|---|---|
| L1 | **Checkpoint sites = constant tuple** `('South','East','West')` | `server.py:944` `CHECKPOINT_LOCATIONS`; used at `:1474, 1478, 1512, 1655, 1668, 1810, 3022, 3024, 3041, 3212, 3349, 3359, 4952, 5027, 5038, 5179, 5537, 5653, 5956`. Frontend: `CP_LOCATIONS` `index.html:2513`, `['South','West','East']` at `:3714`, fallbacks at `:4924, 4986`. |
| L2 | **Location encoded in the role name** (`CheckpointSouth/East/West`) | `server.py:663–665`, `ROLE_LABELS :1094`, `ROLE_MODULES :1121`, `ROLE_LOCATION_SCOPE :1164`, `CHECKPOINT_ROLE_ALIASES :717`, `normalize_role ~:806`, `user_view :1541`. Adding "North" means a code change in ≥8 places. |
| L3 | **Scope resolver only accepts the 3 constants** | `canonical_location_scope :1467` (matches first token against the constants); `checkpoint_scope :1642` (a stored scope is honoured *only if in the constant*); user create/patch reject anything else (`:5537`, `:5956`). |
| L4 | **`locations` table exists but is ignored** | `SCHEMA :146` (`code,label,kind`), seeded with 3 rows `:1824`. Nothing reads it for validation, scope or UI, and it is flat (no parent). |
| L5 | **Checkpoint rows store location as 3 free-text columns** (`location`, `location_code`, `checkpoint_location`) matched by `LIKE '%south%'` | `SCHEMA :200`, `checkpoint_scope_sql :3185`, POST handler `:5640–5680`. No FK. A site named "East Gate" would collide with "East". |
| L6 | **Region/District gazetteer duplicated as constants** | Python: `STATION_REGIONS :978`, `STATION_DISTRICTS :979`, `REGION_CODES :984`, `OFFICER_ORIGIN_REGIONS :970`. JS: `LOCATIONS index.html:1573`, `ORIGIN_REGIONS :1588`. `register_station` hard-validates `district in STATION_DISTRICTS[region]` (`:2318–2334`), so **a new district cannot be added without a deploy**. |
| L7 | **Station code generator breaks on any unknown region** | `new_station_code :2126` → `REGION_CODES[region]` raises `KeyError`. Seed codes are also inconsistent: `SAN-C-01`, `SOO-C-01`, `TOG-C-01` and `ETG-C-03` vs generated `STN-ETG-001`. |
| L8 | **Region is a text column, not an entity** | `police_stations.region/district/village TEXT` (`:215`). No `regions`/`districts` tables, no parent FK, no uniqueness. `officers.region_of_origin`/`district_of_origin` are text too. |
| L9 | **Analytics hardwired to the 3 regions/checkpoints** | `STATION_REGIONS` at `:3808, 3923, 3951, 4149` (partially tolerant: unknown regions are appended). Checkpoint per-location series at `:3022, 3349` (unknown → "Other"). |
| L10 | **Single airport / single branch strings in UI & print** | `index.html:562, 600, 607`, `certificate.html` ("Las Anod, HQ"), `application.html`/`certificate.html` mastheads. |
| L11 | **Users have no org-unit link** | `users.branch TEXT NOT NULL` (free text, display only) and `users.location_scope TEXT` (checkpoint-only). No `unit_id`/`station_id` FK. |
| L12 | **Static role→module / permission dicts, plus alias soup** | `ROLE_MODULES :1121`, `ROLE_PERMISSIONS :1321`, `UNIT_MODULE_DENY :1195`, `UNIT_ROLE_ALIASES :844`, `SPEC_ROLE_ALIASES :820`, `COMMANDER_ROLE_ALIASES :677`. A new role = code edit; the alias layers exist only to paper over inconsistent role strings. |
| L13 | **No row-level data scoping outside checkpoints** | Verified list routes with no caller-based filter: `/api/stations` (`:5180`), `/api/officers` (`:5183`), `/api/crimes` (`:5185`), `/api/vehicles` (`:5193`), `/api/conduct` (`:5196`; the `region`/`station` params are *user-supplied filters*, not enforced scope), `/api/airport-records` (`:4974`), `/api/clearance-applications` (`:4980`), `/api/crime-cases` (`:5004`). Mutations (`PATCH /api/officers/…`, `POST /api/vehicles/…/status`) also don't check the target's unit. |
| L14 | **Routing layer is a monolithic if/elif chain** | `do_GET :4880+`, `do_POST :5271+`, `do_PATCH :~5855+`, with a hand-written `post_module_for_path` dict (`:~5310`). There are no route params/middleware, so scoping can't be injected centrally except via the pattern `enforce_read_only` already demonstrates. |
| L15 | **Entity IDs are time-derived** | `'CP-'+str(int(time.time()*1000))[-8:]` (`:5694`), `'AR-'+…` (`:5380`) → collision risk and no per-unit sequence. |

### 3.2 Specific model-level gaps for Region → District → Unit

| Needed | Today |
|---|---|
| Org hierarchy table | ❌ none (`locations` is flat and unused) |
| Unit *type* (station / checkpoint / airport / CID office / fingerprint office / HR office / HQ) | ❌ only `police_stations.station_tier` (`Regional HQ, District HQ, Outpost, Checkpoint, Border Post`) hints at it |
| Every operational record carries its owning unit | Only `officers`, `vehicles`, `crime_incidents`, `conduct` (via `station_id`). **Missing** on `checkpoint_events` (text), `airport_passengers`, `clearance_applications`, `crime_cases`, `suspect_alerts`, `case_evidence`. |
| User ↔ unit assignment + role-in-unit | ❌ |
| Dynamic role/permission store | ❌ (code constants) |

Note: the existing `STATION_TIERS` already contains `Checkpoint` and `Border Post`. A checkpoint can therefore be modelled as a *unit with a type* rather than a bespoke module, and an airport likewise.

### 3.3 Refactoring needed to bridge to a dynamic tree

**A. Data model**
1. Add `org_units(id, parent_id, type, code, name, status, path/ltree, geo…)` with `type ∈ {hq, region, district, station, checkpoint, airport, directorate_office}`.
2. Migrate `police_stations` rows into `org_units`. Region/district strings become parent nodes. Keep station attributes (tier, cells, commander, phone) in an extension table.
3. Replace `locations` and the `CHECKPOINT_LOCATIONS` text columns with `unit_id` FKs on the unit-scoped event tables only: `checkpoint_events`, `airport_passengers`, `crime_incidents`, `officers`, `vehicles`. Add `intake_unit_id` to `clearance_applications`. CID cases stay national (see §4.4).
4. Replace `users.branch`/`location_scope` with `user_assignments(user_id, unit_id, role_id, include_descendants)`.
5. Per-type/year sequences for IDs, replacing time-based IDs.

**B. Authorization**
1. Roles → DB (`roles`, `role_permissions`), permission strings `module:action`, using the existing `analytics:global` / `stations:manage` style.
2. A single scope resolver `visible_unit_ids(user)` (assignment + descendants via ltree or a recursive CTE). Inject into every list query, and into every mutation as a "target in scope" check. Centralise it the way `enforce_read_only` is centralised.
3. Generalise the read-only firewall to a per-role/per-permission `can_write`, and scope-aware write.

**C. API / UI**
1. CRUD for `org_units` (admin), tree endpoint `GET /api/org/tree`, and unit-type–driven nav.
2. Replace `locationDropdowns` with a tree picker fed by the API. Delete `LOCATIONS` / `ORIGIN_REGIONS` / `CP_LOCATIONS`.
3. Replace the `cpLocChips` with chips generated from the user's visible checkpoint units.
4. Print documents: letterhead/issuing-unit/signatory come from the unit record.
5. Replace the hard-coded `STATION_*` validation with lookup against the tree.

---

## 4. Gap & migration roadmap

### 4.1 Port vs. rewrite

| Area | Verdict | Why / notes |
|---|---|---|
| CSS (`index.html:11–390`) | ✅ **Port as-is** | Pure presentation. Split into tokens + components. |
| Page markup for registers (persons, fingerprint, airport, CID, crimes, cars, officers 5-step form, conduct, executive, oversight) | ✅ **Port, then parametrise** | Remove the hardcoded branch/airport label and "Sool, Sanaag and East Togdheer" strings; replace the location block with the tree picker. |
| Login, shell, sidebar grouping | ✅ **Port**, but drive nav from `/api/me` modules + tree | Keep group UX; remove JS role regexes. |
| Centered-modal / KPI-strip / search-box / toast / inline-error patterns | ✅ **Port** (componentise) | |
| Identity matching form + 4-tier algorithm (JS UI + `resolve_identity`/`ensure_person`/enrichment) | ✅ **Port** | Pure domain logic, scope-independent. Persons stay a global singleton. |
| Fingerprint 12h review lock logic (`fingerprint_review_state`) | ✅ **Port** | Convert to a configurable policy value; keep server enforcement. |
| Validation rules + option lists (ranks, blood groups, doc types, crime categories, conduct classifications, vehicle enums) | ✅ **Port**, move enumerations to DB/config tables where they vary by agency | |
| Officer conduct workflow (`submit_conduct_action`, `review_conduct_action`, rank transitions, service history) | ✅ **Port logic**, ⚠️ rewrite authorisation | Add "submitter must belong to unit/descendant of target officer's unit". |
| Vehicles module (`vehicles.py`) | ✅ **Port**, small change | Already FK to station → retarget to `unit_id`. |
| Singleton logic: persons registry, suspect-alert → checkpoint/airport screening (`alerted` check), audit trail | ✅ **Port** | Alert matching stays global; *visibility* of alert details should become scope-aware. |
| Print documents `application.html` / `certificate.html` + `test_print_fit.py` | ✅ **Port**, ⚠️ templatise header/signatory/issuing city | Convert to real server-side templates; keep CSS and the print-fit test. |
| Analytics builders (`:2950–4300`) | ⚠️ **Rewrite queries, keep payload shape & charts** | Aggregate by tree level (`GROUP BY` ancestor at depth N) instead of `STATION_REGIONS`/`CHECKPOINT_LOCATIONS`. Roll-up to any node. |
| **Checkpoint module** | 🔴 **Rewrite** the backend and chips | Becomes "a unit of type checkpoint". Delete the 3 roles, the aliases, `canonical_location_scope`, `checkpoint_scope_sql`'s LIKE logic. |
| **Airport module** | 🔴 Rewrite data layer | Add `unit_id` (airport unit). Keep the form. |
| **RBAC core** (`ROLE_*`, `ROLE_MODULES`, aliases, denylist, `user_view`, `require_module`) | 🔴 **Rewrite** | Replace with DB roles/permissions + assignments + scope resolver. Keep the *invariants* (fail-closed unknown role, no write for read-only roles, denylist semantics) as tests. |
| Station create/validation (`register_station`, `new_station_code`) | 🔴 Rewrite | Generic org-unit create under a parent; codes from the parent path. |
| User management | 🔴 Rewrite | Assign user to unit(s) + role; remove `location_scope` and `branch`. |
| Routing/HTTP layer | 🔴 Replace | Do not port the 6k-line stdlib handler. Re-implement the endpoints in the unified stack's framework, with scoped queryset/middleware. |
| Auth (SHA-256, never-expiring tokens, CORS `*`, open `/uploads/`) | 🔴 **Do not port** | Use the unified codebase's auth; authenticate and scope file access. |
| JS offline/localStorage fallback & stale-build tooling | ❌ **Drop** | |
| `backend/database.py`, `migrate_rbac.py`, `audit_instant_approvals.py`, `restart-8001.*`, `TROUBLESHOOTING.md` | ❌ **Drop** | Conflicting schema / SQLite remnants / port-8001 operational scars. |
| Tests | ⚠️ **Reuse as specs, not code** | `test_server.py` (3,035 lines), `test_read_only_rbac.py`, `test_review_gate.py` and the `.mjs` suites describe valuable behaviour but run against SQLite (`SENTINEL_DB`) and no longer match the Postgres server. Translate the assertions to the new stack. |

### 4.2 Suggested sequence

1. **Foundation:** implement `org_units` tree + `user_assignments` + roles/permissions + `visible_unit_ids()` + a seed that reproduces today's world (HQ → Sool/Sanaag/East Togdheer → districts → 8 stations → 3 checkpoint units → 1 airport unit, plus Fingerprint/CID/HR/Transport directorate units under the root, see §4.4 T3). Acceptance: adding a region/district/station/checkpoint/airport is data-only, zero code.
2. **Scoping (per D1/D3):** add `unit_id` to `checkpoint_events` and `airport_passengers`, retarget `officers`/`vehicles`/`crime_incidents`/conduct `station_id` to `unit_id`, and add `intake_unit_id` to `clearance_applications`. Leave `crime_cases`/`suspect_alerts`/`case_evidence` national under the CID directorate unit. Backfill (checkpoint South/East/West → checkpoint units; legacy single airport → airport unit). Apply the scope resolver to every list, detail and mutation. Add field-level visibility for the person profile and timeline.
3. **Port UI shell + CSS** as-is, nav driven by permissions; add tree picker + org admin pages (HQ-only).
4. **Port domain modules** one by one (persons → fingerprint/print → CID → checkpoint → airport → officers/conduct → vehicles/stations), each re-pointed at `unit_id`.
5. **Port analytics** with tree roll-ups, then the HQ executive/oversight pages.
6. **Re-create the invariant tests** (unit isolation, read-only role, 12h lock, no cross-scope reads/writes, unknown-role fail-closed) plus a new "add a new branch with no code change" test.
7. **Decommission** the legacy repo only after parity sign-off.

### 4.3 Decisions (resolved 2026-10-01)

| # | Question | Decision |
|---|---|---|
| D1 | Which modules are units vs. national services? | **Hybrid.** Airports and Checkpoints are dynamic tree nodes (`unit_type = 'airport'` / `'checkpoint'`), so a new airport (e.g. Buuhoodle) is a data-only addition. Fingerprint/clearance, CID cases and HR conduct stay **national services** under HQ directorates. |
| D2 | Where does the read-only Chief Commander sit? | **Root node.** One assignment at the root, with inheritance to all descendants, gives read access to the whole tree. This replaces the hardcoded `executive`/`oversight` filters. |
| D3 | Is the persons registry global? | **Yes.** `persons` stays global. Operational events linked to a person are scoped to the `unit_id` where they occurred. |

### 4.4 What the decisions imply (design consequences to settle before the build)

**D1: checking the split against the legacy schema**

| Legacy table | Treatment under D1 |
|---|---|
| `checkpoint_events` | **Unit-scoped.** Add `unit_id` (FK to a `checkpoint` unit) and drop the three text location columns. Replaces limits L1–L5. |
| `airport_passengers` | **Unit-scoped.** Add `unit_id` (FK to an `airport` unit). Replaces L10. |
| `crime_incidents` (station crime intake) | **Unit-scoped.** It is already station-anchored (`station_id`), so just retarget it to `unit_id`. |
| `crime_cases`, `suspect_alerts`, `case_evidence` (CID investigations) | **National**, owned by the CID directorate. |
| `clearance_applications` | **National service**, but see tension T1. |
| `officer_conduct_actions`, `officer_service_history` | **National (HR)**, but see tension T2. |
| `officers`, `vehicles`, `police_stations` | **Unit-scoped.** They already link to stations by FK. |

Note that legacy `crime_incidents` (station intake, scoped) and `crime_cases` (CID, national) are two different things that the old UI labelled "Register Crime" and "Crime Unit". Keep them distinct in the new model. Escalating an incident to a CID case should be an explicit link, `crime_cases.source_incident_id`.

**Tensions between D1 and D3 that need a rule:**

- **T1 (clearance):** D1 says clearance is national, but D3 lists "a clearance request" as an event scoped to a `unit_id`. *Proposed resolution:* the **workflow and approval authority stay national** (the Fingerprint directorate approves and prints). Each application also records an `intake_unit_id`, the unit where it was filed, for attribution, reporting and the applicant's timeline. Intake scope never gives approval rights.
- **T2 (HR conduct):** conduct review is national, but the legacy design has station commanders *submit* the files, and `/api/conduct/submit` is currently open to any authenticated user. *Proposed resolution:* a submitter may only file against officers in their own unit or its descendants. The submitting unit is stored on the file (`station_id` already exists on the table). HR review remains national.
- **T3 (national services vs. the tree):** national directorates need a place in the permission model. *Proposed resolution:* model them as units too, `unit_type = 'directorate'` (Fingerprint, CID, HR, Transport) as **children of the root**, alongside the geographic Region → District → Unit branch. A directorate user's assignment gives them that directorate's national permissions. A regional user's assignment gives them access only to the subtree they are assigned to. This keeps one scope resolver for everything.

**D2: root-level read-only**

- Role assignment is `(user, root_unit, role=chief_commander, include_descendants=true)`, with a role whose permissions are all `*:view` or `*:read`. The old blanket `403` firewall (`enforce_read_only`) becomes "role has no write permission". It is no longer a special case, but keep its test suite as invariants.
- A Chief Commander on the root also sees the directorate children of the root, so national CID, fingerprint and HR data is covered by the same assignment. This is intended.
- Open point: should the *executive dashboard* aggregates ignore any per-unit field redactions? Recommended: yes (counts only, no personal data).
- A `global scope` flag is not needed. A root assignment gives the same result without a second authorization path. Avoid adding one.

**D3: global persons, risks to control**

- A global person master record means every unit can search every citizen. That is the intended design, but it needs **field-level visibility rules**. For example, a checkpoint officer should see identity fields and an "active alert: yes/no" flag. They should not see the CID case narrative, other units' logs or clearance details.
- Define the **person timeline view** as a union of that person's unit-scoped events, **filtered by the viewer's scope**. HQ and regional commanders see their whole subtree, and unit officers see only their own unit's events. This is the mechanism behind the "HQ can view the timeline across units" statement.
- Suspect-alert matching stays global (a checkpoint in any unit must be able to flag a wanted person). Only the *detail* is scoped.
- Fill-only enrichment from the old design now writes to a shared record from many units. Record who enriched which field (`audit_events` already carries the user, so add the unit and field name).
- Person merge (fuzzy Tier 3) is a destructive global operation. Restrict it to a national role.

**Still open**

- Is a "National Register Office" intended? Nothing in this repo implements one. If it is planned, it should be a national directorate unit (T3) that owns the `persons` master record, meaning merge and correction rights.
- Should any directorate (e.g. CID) get **regional sub-offices** later? If likely, give directorates the same tree capability from day one (a directorate unit can have children), instead of having to retrofit it.

---

### 4.5 Concrete schema (delivered)

The schema, scope engine, seed and tests that implement §4.3–4.4 are in **[`UNIFIED_SCHEMA_BLUEPRINT.md`](UNIFIED_SCHEMA_BLUEPRINT.md)** and **`migrations/001_initial_schema.sql`** (base migration; demo accounts in `migrations/dev/`). `docs/blueprint/test_blueprint.py` runs 24 acceptance tests against it (passing on PostgreSQL 16). The open items there (§8, O1–O9) supersede the "Still open" list in §4.4.

---

## 5. Appendix

### 5.1 File map

| File | Lines | Role |
|---|---|---|
| `backend/server.py` | 6,172 | API, RBAC, schema, seed, analytics, static serving |
| `backend/vehicles.py` | 168 | Vehicle schema + validation |
| `backend/database.py` | 84 | **Stale** alternative schema (conflicts with `server.py`) |
| `backend/migrate_rbac.py` | 221 | **Stale** SQLite RBAC migration |
| `backend/audit_instant_approvals.py` | 213 | SQLite audit/revert tool for the 12h-lock incident |
| `backend/test_*.py/.mjs` | ~9.5k | Python (SQLite-era) + Node frontend/session suites |
| `index.html` | 6,346 | SPA: CSS + markup + JS |
| `application.html`, `certificate.html` | 526, 496 | Printable A4 documents |
| `README.md`, `backend/README.md`, `TROUBLESHOOTING.md` | 553, 359, 147 | Docs (README is the most complete behavioural spec) |
| `scripts/restart-8001.{sh,ps1}` | | Stale-process takeover scripts |
| `images/police_logo.png` | 1.9 MB | Emblem |

### 5.2 Tables (PostgreSQL, `server.py:140–335` + `vehicles.py`)
`users`, `locations`, `persons`, `airport_passengers`, `clearance_applications`, `crime_cases`, `suspect_alerts`, `case_evidence`, `checkpoint_events`, `police_stations`, `officers`, `crime_incidents`, `officer_promotions`, `officer_discipline`, `officer_conduct_actions`, `officer_service_history`, `sessions`, `audit_events`, `vehicles`.
Conventions: `TEXT` timestamps, `SERIAL` PKs plus a human ID column (`P-0001`, `ST-001`, `CRM-YYYY-…`), and incremental `ALTER TABLE` migrations in `ADDED_COLUMNS` (`:337`).

### 5.3 Roles (9 seeded)
`SystemAdmin`, `FingerprintUnit`, `AirportControl`, `CIDUnit`, `hr_officer`, `CheckpointSouth`, `CheckpointEast`, `CheckpointWest`, `chief_commander`. All demo passwords are `ChangeMe123!`.

### 5.4 Limits of this audit
- Static analysis only; the app was not run, and no Postgres was available.
- Line numbers refer to commit `19cda80`; the `~` ones are approximate.
- Test suites were read but not executed. They reference SQLite, so they are expected to fail against the current Postgres-only server.
