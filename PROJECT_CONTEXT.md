# PROJECT_CONTEXT.md — Sentinel Police Management System

**Permanent source of project rules, architecture facts and approved decisions.**
Every AI developer session and every contributor must read this file before touching the repository.

| Field | Value |
|---|---|
| Project | Sentinel Police Management System |
| Repository | `CabdallaCms/sentinel-police-management` |
| Current release target | **CID Release 1.0** |
| Document created | 2026-11-06 (documentation baseline) |
| Baseline branch | `arena/6303ef2f-sentinel-police-management` |
| Baseline commit | `a1c2478262776e9f20b4c3ad806eaa86adc27792` (`a1c2478`, 2026-10-27 17:13:20 +0000) |
| Document owner | Project owner (approval authority) |
| Maintained by | AI developer agent, under owner approval |

---

## 0. How to read this document — evidence classification

This document deliberately separates what is **proven** from what is **claimed** or **undecided**.
Every substantive statement carries one of these tags:

| Tag | Meaning |
|---|---|
| **[VERIFIED]** | Confirmed by direct inspection of this repository at commit `a1c2478` during the 2026-11-06 documentation session. The verification method is stated. |
| **[HISTORICAL]** | Reported by an earlier audit or an earlier session. **Not** re-verified at `a1c2478`. Treat as a lead, not as fact. |
| **[REQUIREMENT]** | A mandatory rule for this project. Binding on all future work. |
| **[DECISION-NEEDED]** | An open question the **project owner** must answer. The agent must not decide it unilaterally. |
| **[UNVERIFIED]** | Asserted somewhere (owner, README, prior session) but not yet supported by evidence in this repository. |

**Rule:** no future session may promote an item from `[HISTORICAL]`, `[UNVERIFIED]` or `[DECISION-NEEDED]`
to `[VERIFIED]` without recording the verification command, its output and the commit it was run against.

---

## 1. Project purpose and background

### 1.1 Purpose

Sentinel is a central police management platform for the **North East Police Force / Criminal
Investigation Directorate (CID)**. Its organising principle is a **single Central Person Registry**:
every individual receives one central `Person ID` (`P-0001`, …), and each operational unit keeps its
own records that reference that central identity instead of duplicating it. **[VERIFIED]** — `README.md`
"Central-person linking model"; `persons` table and `person_id` foreign keys throughout
`backend/server.py`.

### 1.2 Background and maturity

- **This is an existing, substantially developed system. It is not a new project and must not be
  rebuilt from scratch.** **[REQUIREMENT]**
- The repository contains a working full-stack application: a ~529 KB / 10,067-line backend
  (`backend/server.py`) and a ~810 KB / 13,158-line single-file front end (`index.html`).
  **[VERIFIED]** — `wc -l`, `stat -c%s`.
- Development history to date is visible as **24 pull requests** against `main` (PRs #1–#24),
  of which 11 are merged. **[VERIFIED]** — `gh pr list --state all`.
- Operational units already present in the codebase include Fingerprint/clearance, CID crime cases,
  Checkpoints, Airport passenger register, Police Stations, Officers/HR conduct, Vehicles, Central
  Police Search, Branch Management and an executive analytics surface. **[VERIFIED]** — `ROLE_MODULES`
  in `backend/server.py:1865`; DDL block in `backend/server.py`.

### 1.3 Responsibility model

| Party | Responsibility |
|---|---|
| **Project owner** | Approves requirements, priorities, scope, schedules, security/legal policy and all production releases. Reviews and coordinates approximately **two hours per day**. **[VERIFIED]** — stated by the owner in the Release 1.0 documentation assignment. |
| **AI developer agent** | Performs implementation, testing, verification and documentation **within approved scope only**. Never self-approves scope, schedule or release. |

---

## 2. Current architecture and technology stack

All entries in this section are **[VERIFIED]** at commit `a1c2478` unless marked otherwise.

### 2.1 Runtime inventory

| Layer | Technology | Evidence |
|---|---|---|
| Language | Python 3 (sandbox: 3.11.2) | `python3 -V`; `backend/server.py` shebang |
| HTTP server | `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler` (Python standard library) | `backend/server.py:45` |
| Web framework | **None** — hand-rolled routing inside `do_GET` / `do_POST` / `do_PUT` / `do_PATCH` / `do_DELETE` | `backend/server.py` |
| Database | **PostgreSQL** via `psycopg2` | `backend/server.py:23-26`; `.env.example` |
| Front end | **Single-file HTML SPA** (`index.html`), inline CSS + inline JavaScript, no framework, no bundler, no build step | `index.html` (13,158 lines) |
| Printable documents | `application.html` (Somali clearance application), `certificate.html` (bilingual Certificate of Good Conduct) | files at repo root |
| Static assets | `images/police_logo.png` (1.9 MB) served by the backend | `backend/server.py` `serve_static()` |
| Config | Root `.env`, read by a standard-library loader (`load_env_file()`); template in `.env.example` | `backend/server.py:52+` |
| Default port | 8001 (`PORT` env var) | `.env.example`; `scripts/restart-8001.sh` |
| Ops scripts | `scripts/restart-8001.sh` / `.ps1`, `scripts/uat-stack.sh`, `scripts/verify-live-ui.sh` | `scripts/` |

### 2.2 Notably absent from the repository

**[VERIFIED]** — `git ls-files` returns 44 tracked files; none of the following exist:

`requirements.txt` · `package.json` / lockfile · `Dockerfile` / compose file · CI configuration
(`.github/workflows`) · reverse-proxy or TLS configuration · systemd unit · licence file ·
`schema_migrations` table or any migration-version tracking · `DEPLOYMENT_AUDIT.md` ·
`CHANGELOG.md` (created by this baseline).

Dependencies are installed ad hoc (`psycopg2-binary`, `pgserver`, `jsdom`). **[REQUIREMENT]**
Dependency manifests must be added before any staging or production deployment is approved —
tracked as an open item, **not** performed in this documentation task.

### 2.3 Database schema (tables created by the application)

**[VERIFIED]** — `CREATE TABLE IF NOT EXISTS` statements in `backend/server.py` and `backend/vehicles.py`:

| Domain | Tables |
|---|---|
| Identity | `persons` |
| Access control | `users`, `sessions`, `audit_events` |
| Organisation | `police_branches`, `police_stations`, `locations` |
| Fingerprint / clearance | `clearance_applications`, `clearance_signed_documents` |
| Crime / CID | `crime_cases`, `crime_incidents`, `case_evidence`, `suspect_alerts` |
| Checkpoint | `checkpoint_events` |
| Airport | `airport_passengers` |
| Personnel | `officers`, `officer_promotions`, `officer_discipline`, `officer_conduct_actions`, `officer_service_history` |
| Transport | `vehicles` |

There is **no `case_participants` table**; case participants are modelled through `suspect_alerts`
(`role` = Suspect / Victim / Witness / Complainant). **[VERIFIED]** — `grep -c case_participants
backend/server.py` → 0; `suspect_alerts` DDL at `backend/server.py:299`.

### 2.4 Branch (unit) model

`police_branches.unit_type` is constrained to exactly five values:
`'fingerprint'`, `'crime'`, `'checkpoint'`, `'airport'`, `'police_station'`.
**[VERIFIED]** — DDL `CHECK` constraint at `backend/server.py:236`; `BRANCH_UNIT_TYPES` at
`backend/server.py:1652`.

Default seeded branches: **Buuhoodle Branch** (East Togdheer), **Lasanod Branch** (Sool),
**Erigavo Branch** (Sanaag). **[VERIFIED]** — `DEFAULT_POLICE_BRANCHES`, `backend/server.py:1660`.

A branch is **never deleted** — Branch Management edits it in place and toggles Active/Inactive so
foreign keys, postings and audit rows keep pointing at the same row. **[VERIFIED]** — comment and
lifecycle code at `backend/server.py:3367+`.

### 2.5 API surface

**[VERIFIED]** — 52 distinct `/api/...` path prefixes, including:
`/api/login`, `/api/logout`, `/api/me`, `/api/health`, `/api/persons` (+ `/resolve`, `/upsert`),
`/api/clearance-applications` (+ `/approve`, `/signed-document`, `/documents`),
`/api/fingerprint/applications`, `/api/crime-cases`, `/api/crimes`, `/api/suspect-alerts`,
`/api/checkpoint-events`, `/api/airport-records`, `/api/stations`, `/api/officers`,
`/api/vehicles`, `/api/conduct`, `/api/branches`, `/api/admin/*`, `/api/audit/entity/*`,
`/api/analytics` (+ `/global`), `/api/cid/analytics`, `/api/officers/analytics`,
`/api/vehicles/analytics`, `/api/stations/analytics`, `/api/dashboard`.

### 2.6 Architectural characteristics that constrain Release 1.0

**[VERIFIED]** by code inspection:

1. **Schema migrations run inside application startup.** Base DDL plus an `ADDED_COLUMNS` table of
   `ALTER TABLE … ADD COLUMN` statements execute as a side effect of booting the web process
   (`backend/server.py:457+`). There is **no version table, no ordering, no checksums and no
   down-migrations**.
2. **Sessions have no expiry column.** `CREATE TABLE sessions(token, user_id, created_at)` —
   `backend/server.py:446`. The only `Max-Age` in the codebase is `Max-Age=0` on logout
   (`backend/server.py:8688`).
3. **Uploads are served by `serve_static()`**, which `do_GET` calls *before* authentication
   (`backend/server.py:7914`, called at `do_GET` entry).
4. **Password hashing is a bare unsalted SHA-256 hex digest** —
   `def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()`
   (`backend/server.py:3362`).
5. **Startup self-tests exist and are good defensive engineering**: the process refuses to start if
   the 12-hour review lock is disarmed (`review_lock_armed()`, `backend/server.py:1057`, enforced at
   `:10022`) or if the RBAC self-test reports problems (`rbac_self_test()`, `:2010`, enforced at `:10026`).
6. **The front end falls back to a `localStorage` "demo database"** when the backend is unreachable,
   showing an "Offline" badge. **[REQUIREMENT]** This fallback must be treated as a data-integrity
   hazard and must be reviewed before any operational use.

---

## 3. Current CID Release 1.0 scope

**Release 1.0 contains exactly three operational units plus the shared functionality they require.**
This scope statement is authoritative and is repeated identically in `RELEASE_PLAN.md` and
`PROJECT_STATUS.md`.

### 3.1 In scope

| # | Unit | Scope summary |
|---|---|---|
| **A** | **Fingerprint Unit** | Complete clearance/fingerprint operations, review workflow, approval gate, certificate issue and printing. |
| **B** | **Crime Unit** | **Full Crime Unit operations, including advanced reports.** |
| **C** | **Checkpoint Unit** | Complete checkpoint screening operations, verified end to end. |
| **S** | **Shared functionality required by A, B and C** | Central Person Registry and identity resolution; authentication and sessions; roles, permissions and server-side authorization; branch-level data isolation; audit logging; document/attachment handling; branch management as it serves the three units; the dashboard/navigation shell as it serves the three units; database, migration and deployment foundations for the three units. |

### 3.2 Out of scope for Release 1.0

- **Airport Unit** — postponed to **CID Release 1.1** (see §5).
- Unrelated police department modules not required by the three CID units.
- Unnecessary HQ administration expansion.
- Any feature not explicitly approved by the project owner.

**[REQUIREMENT]** The Crime Unit must **not** be reduced to basic case registration in order to meet
a date. Advanced reports are part of Release 1.0.

**[REQUIREMENT]** Existing functionality must be **inspected first**. Missing work is identified by
assessment, not by assumption.

### 3.3 Scope-boundary note on already-implemented non-Release-1.0 modules

**[VERIFIED]** The repository already contains working code for modules outside Release 1.0 —
Airport, Police Stations, Officers/HR conduct, Vehicles, Central Police Search, executive analytics.
Their presence in the codebase does **not** place them in Release 1.0 scope.

**[REQUIREMENT]** Treat these modules as **frozen**: do not expand, redesign or add features to them
during Release 1.0. Touch them only when (a) a Release 1.0 unit depends on shared code they also use,
and (b) the change is approved, minimal and recorded. **[DECISION-NEEDED D-13]** The owner must
confirm whether these out-of-scope modules remain *enabled* in the Release 1.0 build or are hidden
until their own release.

---

## 4. Fingerprint, Crime and Checkpoint unit responsibilities

> Status of each unit's **completeness** lives in `PROJECT_STATUS.md`, not here. This section defines
> **responsibility**, not progress.

### 4.1 Fingerprint Unit

**Responsibility:** receive, review, approve and issue police clearance (Certificate of Good Conduct)
records, and maintain the fingerprint/biometric register.

**Implemented behaviour observed in the repository [VERIFIED]:**

- `clearance_applications` holds applicant data, purpose, guardian/guarantor data, applicant and
  guardian document references, applicant photo, status (`Pending Review` default), certificate
  number, `created_at` / `reviewed_at`, and a `branch_id` foreign key. (`backend/server.py:265`)
- `clearance_signed_documents` versions re-scanned signed application sheets additively, retaining
  upload provenance. (`backend/server.py:281`)
- Clearance purposes are constrained to five values — **Education, Travel, Employment, Citizenship,
  Licence** — with HTTP 400 on anything else. (`README.md`)
- A **mandatory 12-hour review period** gates approval, with **Citizenship exempt** and
  **SystemAdmin able to bypass**. Enforced in three places (backend approve route, the register table
  in `index.html`, and `application.html`), and armed by a startup self-test that refuses to boot if
  the gate is disabled. (`README.md`; `review_lock_armed()` at `backend/server.py:1057`, `:10022`)
- `application.html` and `certificate.html` are A4 print contracts pinned by `backend/test_print_fit.py`.
- Role `FingerprintUnit` is limited to modules `{dashboard, people, fingerprint}`.
  (`ROLE_MODULES`, `backend/server.py:1865`)

**Owner-reported progress of ~80% is [UNVERIFIED]** and must be assessed. See `PROJECT_STATUS.md`.

**Known open concerns carried into Release 1.0 [HISTORICAL — re-verified at code level, see §7.4]:**
cross-branch approval and signed-scan writes; unauthenticated document retrieval; the submitter being
able to approve their own application; the `Citizenship` bypass.

### 4.2 Crime Unit

**Responsibility:** full CID crime operations — incident/case intake, case management, participants
and suspect handling, evidence custody, case status lifecycle, and **advanced reports**.

**Implemented behaviour observed in the repository [VERIFIED]:**

- `crime_cases` — `case_id`, `branch_id`, `category`, `location`, `status` (default `Reported`),
  `incident_summary`, `notes`, `created_by`, `created_at`. (`backend/server.py:292`)
- `crime_incidents` — a richer station-level intake record: `file_number`, `station_id`, `officer_id`,
  `branch_id`, `category`, `incident_at`, `location_of_occurrence`, `severity`, `description`,
  `case_status` (default `Reported / Open`), reporting-party and victim fields (including
  `victim_anonymous`), `statement`, and two evidence slots. (`backend/server.py:374`)
- `suspect_alerts` — `alert_id`, `person_id`, optional `case_id`, `role` (default `Suspect`),
  `alert_status` (default `Active alert`), `origin` (default `Direct Intelligence Listing`).
  Case linkage is **deliberately optional**. (`backend/server.py:299`; `README.md`)
- `case_evidence` — `evidence_id`, `case_id`, `caption`, file path/name/type, `uploaded_by`.
  (`backend/server.py:309`)
- A full-page **CID case workspace** with three tabs: Case Details & Incident Summary; Participants &
  Suspect List Linkage; Evidence & Media Storage. (`README.md`)
- Endpoints `/api/crime-cases`, `/api/crimes`, `/api/suspect-alerts`, `/api/cid/analytics`.
- Role `CIDUnit` is limited to modules `{dashboard, people, cid, crimes}`.
  (`ROLE_MODULES`, `backend/server.py:1865`)

**[REQUIREMENT]** Before any Crime Unit implementation begins, the following must be **documented and
owner-approved**: requirements, workflows, user roles, permissions, and the **definition of "advanced
reports"**. **[DECISION-NEEDED D-14]** "Advanced reports" is currently undefined — the owner must
specify the report list, their fields, filters, aggregation rules, export formats and who may run them.

**[DECISION-NEEDED D-15]** The relationship between `crime_cases` (CID case) and `crime_incidents`
(station incident file) is not documented anywhere in the repository. The owner must confirm the
intended operational relationship before Crime Unit work is scheduled.

### 4.3 Checkpoint Unit

**Responsibility:** traveller/vehicle screening at checkpoints, with strict location isolation, and
the resulting screening record, action taken and alert interaction.

**Implemented behaviour observed in the repository [VERIFIED]:**

- `checkpoint_events` — `event_id`, `person_id`, `branch_id`, `location`, `location_code`,
  `checkpoint_location`, `screening_result`, `action_taken` (default `Cleared`), `notes`.
  (`backend/server.py:316`)
- A **single scalable checkpoint role** (`checkpoint_officer`) alongside legacy compound roles
  (`CheckpointSouth` / `CheckpointEast` / `CheckpointWest`), all rendering one label
  "Checkpoint Officer"; the checkpoint itself is printed from the posting, not the role.
  (`ROLE_LABELS`, `backend/server.py:1816`; `README.md`)
- All checkpoint roles are limited to modules `{dashboard, checkpoints}`.
  (`ROLE_MODULES`, `backend/server.py:1865`)
- `GET /api/checkpoint-events` returns `scope` and `visible_locations`;
  `POST /api/checkpoint-events` rejects events outside the officer's location. (`README.md`)
- Writes pass through `require_branch_write_scope(..., 'checkpoint')`. (`backend/server.py:9219`)
- Canonical South/East/West checkpoints are grouped under "Checkpoint areas" in the unit tree.
  (commit `17c37bc`)

**Owner-reported status "already implemented" is [UNVERIFIED].** **[REQUIREMENT]** It must be verified
across: workflows, permissions, security, branch/location isolation, and integration with the Central
Person Registry and suspect alerts, before it is accepted into Release 1.0.

**Known open concern [HISTORICAL]:** clearing a checkpoint officer's `location_scope` reportedly widens
them to every checkpoint (prior finding M-2). Not re-verified at runtime in this session.

---

## 5. Airport Unit — postponed to Release 1.1

- The **Airport Unit is NOT part of CID Release 1.0.** It is reserved for **CID Release 1.1**.
  **[REQUIREMENT]**
- Airport functionality **already exists** in the codebase — `airport_passengers` table,
  `/api/airport-records`, role `AirportControl` with modules `{dashboard, people, airport}`, branch
  `unit_type='airport'`, and the "Hargeisa Local Airport passenger register" page. **[VERIFIED]**
- **[REQUIREMENT]** During Release 1.0 the agent must **not** implement, expand, redesign or add
  features to the Airport Unit. Existing Airport code is **frozen**, not deleted and not disabled.
- **[REQUIREMENT]** If a Release 1.0 change to shared code (identity resolution, auth, branch scoping,
  audit, uploads) necessarily affects the Airport Unit, the agent must (a) keep the change minimal,
  (b) state the Airport impact explicitly in the task report, and (c) not treat it as licence to
  extend Airport features.
- **[DECISION-NEEDED D-16]** Whether the Airport module is visible/enabled in the Release 1.0 build,
  or hidden until Release 1.1. (Related to D-13.)

---

## 6. Development principles

**[REQUIREMENT]** All of the following are binding.

1. **Controlled, incremental delivery.** Small, reviewable changes with a stated scope. No large
   unreviewable rewrites.
2. **Assess before you build.** Inspect existing implementation before declaring work missing.
3. **Evidence over assertion.** Never claim a behaviour works without running something that proves it.
4. **No unapproved scope.** If it was not approved, it is not in the sprint. Propose, do not proceed.
5. **Do not rebuild what exists.** The system is mature; extend and fix it.
6. **Security is not negotiable for a date.** Never trade security, testing or data integrity for a
   deadline. If the work does not fit the date, the date moves.
7. **Shared services over duplication.** New modules integrate with existing users, permissions, audit
   logs and branch management rather than duplicating them.
8. **Keep documentation live.** `PROJECT_STATUS.md` and `CHANGELOG.md` are updated as part of the task,
   not afterwards.
9. **Report conflicts, do not silently resolve them.** If an instruction contradicts the repository or
   an existing document, surface the conflict to the owner.
10. **Never rewrite technical history.** Audit findings, changelog entries and prior reports are
    amended by appending a correction, never by editing the record away.
11. **Synthetic data only** in development and staging. **[REQUIREMENT]**
12. **One branch per session.** Work on the session branch; never push to `main`; never merge without
    owner approval.

---

## 7. Security and privacy requirements

The system contains sensitive police information. Security, privacy, data integrity and accountability
are **mandatory**, not optional.

### 7.1 Mandatory security principles — binding project requirements

**[REQUIREMENT]** Each of the following is a standing project requirement. Release 1.0 acceptance is
measured against them.

| # | Requirement |
|---|---|
| S-01 | Enforce authorization **on the server**, not only in the frontend. |
| S-02 | **Deny access by default.** |
| S-03 | Enforce **branch-level data isolation** on all relevant operations — reads *and* writes. |
| S-04 | **Never allow an unresolved branch identity to grant broader access** (no fail-open). |
| S-05 | **Protect uploaded documents and attachments** — authentication and authorization on retrieval. |
| S-06 | Use **secure password hashing** (salted, slow — e.g. Argon2/bcrypt/scrypt). |
| S-07 | Apply appropriate **session expiration and revocation** (including on password reset, role change and deactivation). |
| S-08 | **Prevent unauthorized privilege escalation.** |
| S-09 | Maintain **audit logs for important actions**, including authentication events. |
| S-10 | **Protect sensitive police records** from unauthorized access. |
| S-11 | Use **synthetic data** in development and staging. |
| S-12 | **Never expose credentials, tokens or sensitive records** in reports, logs, test output or documentation. |
| S-13 | Use **versioned database migrations**. |
| S-14 | Maintain **reliable backups and tested restoration**. |
| S-15 | **Document deployment and rollback procedures.** |
| S-16 | **Do not perform production changes without explicit owner approval.** |

### 7.2 Privacy requirements

- The Central Person Registry contains identity documents, photographs, guardian/guarantor details and
  criminal-justice records. Access must be justified by role **and** branch.
- **[DECISION-NEEDED D-05]** Whether every role may search the entire central person registry (the
  current behaviour) requires a privacy decision from the owner.
- **[DECISION-NEEDED D-04]** Retention periods for clearance applications, identity documents,
  checkpoint events, crime cases and audit logs are undefined and legally significant.

### 7.3 Reporting hygiene

**[REQUIREMENT]** No report, commit message, changelog entry, test fixture or documentation file may
contain a real credential, a session token, or a real person's police record. Documentation of *default*
credentials that exist in code is permitted only as a **defect reference**, never as usable instructions.

### 7.4 Security posture at the documentation baseline

These are **standing concerns inherited into Release 1.0**. Full detail, including verification status
per item, is in `PROJECT_STATUS.md` §Security blockers. Summary of what was re-checked **statically**
at `a1c2478` during this documentation session:

| Concern | Code-level status at `a1c2478` | Method |
|---|---|---|
| Uploaded documents reachable without authentication | **Code path still unauthenticated** — `/uploads/` is handled in `serve_static()`, which `do_GET` calls before any auth check | `backend/server.py:7914`, `do_GET` entry |
| Unsalted SHA-256 password hashing | **Still present** | `backend/server.py:3362` |
| Default seeded accounts sharing a published password | **Still present** (nine seeded accounts) | `backend/server.py:3304+`; `README.md:566` |
| Branch isolation missing on `/approve`, `/signed-document`, `/persons/<id>/documents` | **No `require_record_branch_scope()` call on those routes** | `backend/server.py:8152`, `:8997`, `:9032` vs call sites at `:4281`, `:8244`, `:8283` |
| Branch scope **fails open** on an unresolvable posting | **Still present** — `branch_scope_view()` returns `None` (unrestricted) when the posting does not resolve | `backend/server.py:2661-2694` |
| Sessions never expire | **No expiry column**; only `Max-Age=0` on logout | `backend/server.py:446`, `:8688` |
| Migrations run at startup without version tracking | **Still the case** — base DDL + `ADDED_COLUMNS` at boot, no `schema_migrations` table | `backend/server.py:457+` |
| Administrator self-demotion / lockout | **Not re-verified** (requires a running system) | — |
| Password reset not revoking sessions | **Not re-verified** (requires a running system) | — |
| Transport/session/deployment hardening (TLS, `Secure`, HSTS, headers) | **Not re-verified**; no reverse-proxy or TLS configuration exists in the repository | `git ls-files` |

**A partial counter-fact, recorded for accuracy [VERIFIED]:** branch isolation is *not* uniformly
fail-open. `require_record_branch_scope()` explicitly treats a record with a `NULL` branch as **out of
scope** for a scoped officer — *"unknown must never mean everything"* (`backend/server.py:2790-2805`).
The fail-open behaviour is in **officer scope resolution**, not in per-record read checks. Future
remediation must address the resolution path specifically.

---

## 8. User roles and access-control principles

### 8.1 Implemented roles

**[VERIFIED]** — `ROLE_*` constants (`backend/server.py:1335-1412`), `ROLE_LABELS` (`:1816`),
`ROLE_MODULES` (`:1865`), `ROLE_PERMISSIONS` (`:2065`):

| Role constant | Label | Modules granted |
|---|---|---|
| `SystemAdmin` | System Administrator | dashboard, analytics, admin, people, fingerprint, airport, cid, checkpoints, policesearch, stations, officers, cars, crimes, conduct |
| `FingerprintUnit` | Fingerprint Unit Officer | dashboard, people, fingerprint |
| `AirportControl` | Airport Control Officer | dashboard, people, airport |
| `CIDUnit` | CID Criminal Unit Officer | dashboard, people, cid, crimes |
| `hr_officer` | HR Directorate Officer | dashboard, people, policesearch, stations, officers, conduct |
| `checkpoint_officer` | Checkpoint Officer | dashboard, checkpoints |
| `CheckpointSouth` / `CheckpointEast` / `CheckpointWest` | Checkpoint Officer (legacy compound roles) | dashboard, checkpoints |
| `chief_commander` | Chief Commander (HQ / Command) | dashboard, executive, oversight, people, policesearch, fingerprint, airport, cid, checkpoints, crimes, stations, officers, conduct, cars — **global read-only** |

**[VERIFIED]** The operational units (`FingerprintUnit`, `AirportControl`, `CIDUnit`) deliberately do
**not** hold `policesearch`; the cross-registry officers/stations/vehicles lookup is restricted to
`SystemAdmin`, `hr_officer` and `chief_commander`.

**[VERIFIED]** `chief_commander` is a **global read-only** role enforced by a server-side firewall
(`enforce_read_only()`) that runs inside `do_POST` / `do_PUT` / `do_PATCH` / `do_DELETE` after
authentication and before routing, answering `403 Forbidden` with `code: read_only_role`. It covers
non-existent paths and unserved verbs. `GET`/`HEAD`/`OPTIONS`, `POST /api/login` and `POST /api/logout`
are exempt. (`README.md` "Global read-only command role")

**[VERIFIED]** Role names are **alias-tolerant**: a stored `fingerprint_officer`, `admin`,
`CheckpointSouth` or `cp_south` resolves to the canonical role for modules, RBAC gates, visibility
flags and the review window (`role_label_for()`, `canonical_unit_role()`, `normalize_role()`).

### 8.2 Access-control principles

**[REQUIREMENT]**

1. **Server-side enforcement is the only enforcement that counts.** The front end's role mirror
   (`effectiveModules()`, `hardenReadOnlyDom()`, `canWrite()`) is **presentation only**.
2. **Deny by default.** A role that has not been granted a module does not have it.
3. **Least privilege.** A unit role sees its own unit plus the shared person registry — nothing more.
4. **Read-only means read-only everywhere**, enforced in front of the router.
5. **No self-escalation, and no self-lockout.** A user must not be able to grant themselves privileges,
   nor to remove the last administrator.
6. **Tests that assert UI behaviour do not prove server enforcement.** Each access-control requirement
   needs an API-level negative test.

### 8.3 Open role decisions

- **[DECISION-NEEDED D-03]** Password policy (length, complexity, rotation, reuse).
- **[DECISION-NEEDED D-08]** Session lifetime and idle timeout.
- **[DECISION-NEEDED D-12]** Separation of duties: may the officer who files a clearance application
  also approve it? Is an independent approver required?
- **[DECISION-NEEDED D-06]** Is the 12-hour `Citizenship` exemption a legal requirement or a convenience?
- **[DECISION-NEEDED D-09]** Deployment/approval authority and whether a two-person rule applies to
  user and role administration.
- **[DECISION-NEEDED D-03b]** Is an organisational identity provider (AD/LDAP/OIDC) and/or MFA required?

---

## 9. Branch-level data isolation requirements

**[REQUIREMENT]** Branch isolation is a **core security control** of this system, not a UI convenience.

1. **Every relevant read and every relevant write must be branch-scoped on the server.**
2. **Fail closed.** If an officer's branch identity cannot be resolved, the officer gets **no broader
   access** — they must be denied, not unrestricted. This directly contradicts the current
   `branch_scope_view()` behaviour (§7.4) and is a Release 1.0 correction requirement.
3. **Unknown is not everything.** A stored record with no branch must be out of scope for a scoped
   officer. (Already correct in `require_record_branch_scope()`.)
4. **Isolation must cover the whole record lifecycle** — list, read, create, update, approve, attach,
   download, print, and audit-history read. Approval and attachment routes are explicitly in scope.
5. **Unscoped sessions must be explicit and few.** Only `SystemAdmin`, the records administrators and
   the read-only Commander are intended to be unscoped (`branch_scope_view()`); any other unscoped
   session is a defect.
6. **Branches are never deleted**, so isolation rules must handle Inactive branches and legacy postings.
7. **Every isolation rule needs a negative test** proving cross-branch access is refused — including
   the write and approval paths, not only reads.

**[VERIFIED]** Existing helpers to build on: `branch_scope_view()` / `user_branch_scope()` (`:2661`,
`:2728`), `posting_scope_status()` (`:2696`), `require_branch_write_scope()` (`:2733`),
`require_record_branch_scope()` (`:2790`), `record_branch_id()` (`:2777`), plus
`AUDIT_ENTITY_BRANCH_SOURCES` / `AUDIT_ENTITY_UNIT_TYPES` maps.

---

## 10. Data integrity and audit requirements

### 10.1 Data integrity

**[REQUIREMENT]**

1. Identifier generation must be **safe under concurrency**. Current generators
   (`SELECT COUNT(*)+8`, millisecond-epoch ids, scan-max ids) are **[HISTORICAL]** reported to produce
   user-visible `409` failures under parallel writes.
2. Writes that span multiple tables must be **transactional** — no partially written case, application
   or screening event.
3. **Referential integrity must be preserved** across branch deactivation, person merges and
   identity enrichment.
4. **Identity enrichment must never overwrite existing non-null central data** — fill-only. **[VERIFIED]**
   as the current documented behaviour (`README.md`, "Central Person enrichment on submission").
5. The front-end `localStorage` offline fallback must never be mistaken for live data.
6. **No fabricated records.** Demo/seed data must never reach a shared or operational database.

### 10.2 Audit requirements

**[REQUIREMENT]**

1. **Audit important actions**: create, update, approve, reject, delete, permission change, role change,
   user activation/deactivation, password reset, **login success, login failure, logout**.
2. Each audit entry should carry **who** (user id + badge), **what** (action, entity, entity id),
   **when**, and enough **detail** to reconstruct the change.
3. Audit records must be **append-only and tamper-evident**; retention must be defined
   (**[DECISION-NEEDED D-04]**).
4. Branch scoping applies to **reading** audit history, so a scoped officer cannot read another
   branch's record history by guessing an identifier. **[VERIFIED]** as already implemented via
   `require_record_branch_scope()` at `backend/server.py:4281`.

**[VERIFIED]** Current implementation: `audit_events(user_id, action, entity, entity_id, details,
created_at)` (`backend/server.py:450`), a per-record history endpoint `/api/audit/entity/<...>`, an
admin audit view `/api/admin/audit`, and badge-number attribution.
**[HISTORICAL]** Known gaps: no authentication/session events, no IP/user-agent/session id, no
before/after values, no immutability guarantee, no retention policy.

---

## 11. Database migration and deployment principles

### 11.1 Migration principles

**[REQUIREMENT]**

1. **Versioned migrations.** Ordered, named, recorded in a migration-version table, with checksums.
2. **Migrations must not be a side effect of booting the web process.**
3. **Idempotent and concurrency-safe** — two processes starting together must not race on DDL
   (advisory lock or a separate migration step).
4. **Additive-first.** Prefer `ADD COLUMN` / new table over destructive DDL. Destructive changes need
   explicit owner approval and a rehearsed rollback.
5. **Rollback is not the inverse of migration.** Reverting application code does **not** revert schema.
   Every migration must state its rollback strategy, including "restore from backup" when that is the
   honest answer.
6. **Test migration idempotency on a populated database**, not only an empty one.
7. **No seed/demo data** in any shared, staging-with-real-data, or production database.

### 11.2 Deployment principles

**[REQUIREMENT]**

1. The project must eventually support **separate Development, Staging and Production environments**.
2. Deployment must prioritise: controlled releases · versioned migrations · verified backups ·
   tested restoration · rollback procedures · application/database compatibility · monitoring and
   post-deployment checks.
3. **The first production deployment may require a planned maintenance window.**
4. **Do not promise zero downtime** until the architecture and deployment process have been verified to
   support it. **[VERIFIED]** the current architecture cannot: schema migrations are unversioned
   boot-time side effects (§2.6).
5. **Backups must be proven by restoration**, not by existence.
6. **No production change without explicit owner approval.**
7. Database access must be **least-privilege**, not superuser, and encrypted in transit.

**[DECISION-NEEDED]** D-01 hosting target and data residency · D-02 network design/VPN · D-07 expected
scale · D-08 RPO/RTO · D-09 deployment authority and production database custody · D-10 certificate
verification by third parties · D-11 genuine offline/field requirements.

---

## 12. AI developer agent responsibilities

**[REQUIREMENT]**

### 12.1 At the start of every session

Read, in this order:

1. `PROJECT_CONTEXT.md` (this file)
2. `PROJECT_STATUS.md`
3. `RELEASE_PLAN.md`
4. `DEPLOYMENT_AUDIT.proposed.md`, **if present** (see §12.4)
5. `README.md`

Then inspect: the current Git branch · recent commits · the relevant application files · the existing
tests · the current project status.

### 12.2 Before implementing anything

Identify and state, explicitly:

1. The exact task.
2. The problem being solved.
3. The affected files and components.
4. The affected database tables and APIs.
5. Relevant roles and permissions.
6. Acceptance criteria.
7. Risks and dependencies.
8. Required tests.

**The agent must not begin unapproved work.**

### 12.3 On completing every task

Report:

- Summary of changes · exact files modified · database changes · tests performed · **passing and
  failing results** · security implications · remaining defects · commit reference · updated project
  status.

**Never claim completion without verification evidence.** "Should work", "appears to work" and
"logically correct" are not evidence.

### 12.4 Note on `DEPLOYMENT_AUDIT.proposed.md`

**[VERIFIED]** At the documentation baseline the audit file is **not present on `main` and not in this
working tree**. It exists only on branch `arena/8834f56d-sentinel-police-management` (head `7da888b`),
proposed by **draft pull request #23**, which is **open and unmerged**. A session that does not find
the file locally must consult PR #23 rather than conclude that no audit exists. The file and its
history must be preserved; findings must not be edited.

### 12.5 Prohibited without explicit approval

Merging branches · pushing to `main` · production or staging changes · schema or data changes outside
an approved task · changing authentication or authorization logic outside an approved task ·
installing or upgrading dependencies outside an approved task · deleting or overwriting existing
project documentation · unrelated changes bundled into an approved task.

---

## 13. Project owner approval responsibilities

**[REQUIREMENT]** The project owner — not the agent — approves:

1. **Requirements** for each unit, including the definition of "advanced reports".
2. **Priorities and implementation order.**
3. **Scope**, including every addition or reduction.
4. **The delivery schedule**, after reviewing the repository assessment.
5. **Security and legal policy**: retention, DPIA/privacy sign-off, password policy, session lifetime,
   separation of duties, MFA/SSO, certificate verification.
6. **Environment and infrastructure decisions**: hosting, network, scale, RPO/RTO.
7. **Promotion to staging and to production**, and any production maintenance window.
8. **Acceptance of each release**, against the criteria in `RELEASE_PLAN.md`.
9. **Resolution of every `[DECISION-NEEDED]` item** recorded in this document.

The owner has approximately **two hours per day** for review and coordination; work should be packaged
into reviewable units that respect that budget.

---

## 14. Rules for implementation, testing, documentation and release approval

### 14.1 Implementation rules

**[REQUIREMENT]**

1. One approved task per change set. No drive-by edits.
2. Server-side enforcement first; UI second.
3. Touch the minimum surface needed. Out-of-scope modules stay frozen (§3.3).
4. No new dependency without approval and a recorded justification.
5. Schema changes follow §11.1 and are called out explicitly in the task report.
6. Preserve the startup self-tests (`review_lock_armed()`, `rbac_self_test()`); never weaken a guard to
   make a test pass.

### 14.2 Testing rules

**[REQUIREMENT]**

1. Every security requirement needs an **API-level negative test** proving the refusal. A passing UI
   test does not satisfy a server-enforcement requirement.
2. Every fixed defect gets a **regression test that fails before the fix and passes after**.
3. Record **exact results** — suite name, pass/fail, counts, and the commit tested.
4. **A suite that cannot be run is reported as "not run", never as "passing".**
5. Tests use **synthetic data** and throwaway databases only.
6. Obsolete suites must be **retired or rewritten**, so that "all tests pass" is a meaningful statement.
   **[VERIFIED]** two SQLite-era harnesses are currently obsolete (`backend/test_server.py`,
   `backend/test_conduct_frontend.mjs`); they must not be run on a machine with real database
   credentials in the environment.

### 14.3 Documentation rules

**[REQUIREMENT]**

1. `PROJECT_STATUS.md` is updated **in the same change set** as the work it describes.
2. `CHANGELOG.md` gets an entry for every significant change, in the defined format.
3. `PROJECT_CONTEXT.md` changes only for rules, architecture facts and approved decisions — and every
   change states its evidence.
4. `RELEASE_PLAN.md` changes only with owner approval.
5. **Never invent progress percentages.** Unassessed work is labelled **"Not yet verified."**
6. Historical records are corrected by **appending**, never by deleting.

### 14.4 Release approval rules

**[REQUIREMENT]** A release is approved only when, in order:

1. All planned scope for that release is **complete and verified**.
2. Functional, security and integration testing have passed, with recorded evidence.
3. Known defects are listed, with severity, and the owner has accepted any that remain.
4. No open security blocker remains unaccepted.
5. Migration, backup, restore and rollback procedures are documented and rehearsed.
6. A staging verification has been completed on synthetic data.
7. The **owner explicitly approves** promotion.

---

## 15. Strict rules against unapproved scope expansion

**[REQUIREMENT]**

1. **Do not add features without explicit owner approval.** Not "small" ones, not "obvious" ones, not
   "while I was in there" ones.
2. **Do not expand a unit's scope** beyond the approved definition in §3.
3. **Do not implement or expand the Airport Unit** during Release 1.0 (§5).
4. **Do not expand HQ administration** or unrelated police department modules.
5. **Do not reduce approved scope to meet a date.** In particular, the Crime Unit keeps advanced reports.
6. **Do not invent or finalise a delivery schedule.** The owner approves it after the repository
   assessment.
7. **Do not decide unresolved legal or operational policy.** Record it as `[DECISION-NEEDED]`.
8. **Proposals are welcome; unilateral action is not.** Out-of-scope improvements are written down as
   candidates for a future release and left unimplemented.
9. **Refactoring is scope.** A refactor needs approval exactly like a feature.
10. If the agent believes the approved scope is wrong, it **says so and stops**, rather than quietly
    building something else.

---

## Appendix A — Decisions requiring owner confirmation (consolidated register)

| ID | Decision | Raised in |
|---|---|---|
| D-01 | Hosting target, region(s), data residency/sovereignty constraints | §11.2 |
| D-02 | Network design — VPN topology, IP plan, certificate issuance and rotation | §11.2 |
| D-03 | Password policy (length, complexity, rotation, reuse) | §8.3 |
| D-03b | Organisational identity provider (AD/LDAP/OIDC) and MFA requirement | §8.3 |
| D-04 | Legal retention periods for clearance applications, identity documents, checkpoint events, crime cases and audit logs; tamper-evident audit obligation | §7.2, §10.2 |
| D-05 | Privacy/DPIA sign-off; may every role search the entire central person registry? | §7.2 |
| D-06 | Is the 12-hour `Citizenship` exemption a legal requirement or a convenience? | §8.3 |
| D-07 | Expected scale — accounts, records/month, peak concurrency, document volume | §11.2 |
| D-08 | RPO/RTO, and session lifetime / idle timeout | §8.3, §11.2 |
| D-09 | Deployment authority, production database custody, two-person rule for user/role administration | §8.3, §11.2 |
| D-10 | Third-party certificate verification (online, QR, both, or none) | §11.2 |
| D-11 | Genuine offline/field operation requirement (and therefore a designed sync model) | §11.2 |
| D-12 | Separation of duties — may the filing officer approve their own clearance application? | §8.3 |
| D-13 | Are out-of-scope but implemented modules enabled or hidden in the Release 1.0 build? | §3.3 |
| D-14 | **Definition of Crime Unit "advanced reports"** — list, fields, filters, aggregations, exports, permitted roles | §4.2 |
| D-15 | Intended operational relationship between `crime_cases` and `crime_incidents` | §4.2 |
| D-16 | Airport module visibility in the Release 1.0 build | §5 |
| D-17 | Reconciliation of the earlier audit artefact: is `DEPLOYMENT_AUDIT.proposed.md` (PR #23) the authoritative audit of record, and should it be merged, revised or superseded? | §12.4 |

> D-01…D-12 restate the twelve open questions raised by the earlier deployment audit (PR #23 §12), which
> remain unanswered in the repository. D-13…D-17 were raised by this documentation baseline.

---

## Appendix B — Baseline verification record

| Item | Value |
|---|---|
| Verification date | 2026-11-06 (session executed 2026-11-05 UTC) |
| Branch | `arena/6303ef2f-sentinel-police-management` |
| Commit | `a1c2478262776e9f20b4c3ad806eaa86adc27792` |
| Identical to | `origin/main` at the time of verification |
| Working tree | Clean (`git status --porcelain` → 0 lines) before documentation files were added |
| UI identity check | `python3 backend/server.py --ui-check` → **exit 0**, build `sentinel-branch-crud-1-e7c41b90`, serving `index.html`, checkout `arena/6303ef2f-sentinel-police-management @ a1c2478` |
| Dependency-free suite executed | `python3 backend/test_print_fit.py` → **PASS** (`ALL PRINT TEMPLATE TESTS PASSED`) |
| Suites **not** executed | The remaining 24 test files — they require `psycopg2`, `pgserver` and/or `jsdom`, none of which are installed, and installing dependencies was out of scope for this documentation task |
| Application code changed | **None** |
