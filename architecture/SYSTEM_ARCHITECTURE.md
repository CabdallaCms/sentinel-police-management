# Sentinel CID — Shared System Architecture (Release 1.0)

**Phase 3 deliverable E · Architecture only. No application code, schema, configuration or
dependency was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

**Scope:** the three Release 1.0 units — **Fingerprint**, **Crime**, **Checkpoint** — and the shared
CID capabilities they depend on. **Airport Unit is excluded from Release 1.0 by owner decision
(→ Release 1.1)**; it appears below only where it already shares a table or a route, because
pretending it is absent would misdescribe the system.

No department is added and HQ administration is not expanded beyond what the three units require.

---

## 1. Current architecture — as built

```
┌──────────────────────────────────────────────────────────────────────┐
│ Officer workstation (browser)                                        │
│  index.html — 13,158-line single-file SPA, all units, all pages      │
│  localStorage: session hints · sentinelBiometrics (TO BE REMOVED)    │
└───────────────┬──────────────────────────────┬───────────────────────┘
                │ HTTP (no TLS — H-8)          │ localhost only
                │ cookie session               │ ports 8080/9001/11100
                ▼                              ▼
┌──────────────────────────────────┐   ┌────────────────────────────────┐
│ backend/server.py                │   │ Fingerprint bridge service     │
│ stdlib ThreadingHTTPServer       │   │ ** NO CODE IN THIS REPO **     │
│ 10,067 lines, one module         │   │ protocol specified at          │
│  do_GET 7946 · do_POST 8657      │   │ index.html:4773-4800           │
│  do_PATCH 9491 · do_DELETE 9783  │   └────────────────────────────────┘
│  module gate 8097 / 8869         │
│  enforce_read_only() per verb    │
│  /uploads/ 7914  ← UNAUTHENTICATED (C-1)
└───────────────┬──────────────────┘
                │ psycopg2
                ▼
┌──────────────────────────────────┐   ┌────────────────────────────────┐
│ PostgreSQL — 21 tables           │   │ Filesystem uploads/            │
│ DDL executed at startup (M-11)   │   │ unvalidated writes (M-7)       │
│ superuser, unencrypted (M-8)     │   │ served without auth (C-1)      │
│ no schema_migrations             │   └────────────────────────────────┘
└──────────────────────────────────┘
```

**Characteristics that constrain every decision below:**
no `requirements.txt` · no `package.json` · no Dockerfile · no CI · no TLS · no migration framework ·
no backup/restore procedure · one 10,067-line backend module · one 13,158-line frontend file ·
**23 of 25 test suites cannot be executed in this environment** (missing `psycopg2-binary`,
`pgserver`, `jsdom@26`; installation is outside the current authorization).

> **Honest note:** the stdlib HTTP stack is unusual but is **not** itself the problem, and replacing
> it is **not** recommended for Release 1.0. The defects found are in authorization, data modelling
> and operational practice — a framework swap would consume the schedule without fixing any of them.

---

## 2. Target architecture — Release 1.0

```
┌───────────────────────────────────────────────────────────────────────┐
│ Officer workstation                                                   │
│  SPA (no biometric data in browser storage — FPR-901)                 │
│  Bridge client ──► local bridge service (NEW, external — D-32)        │
└───────────────┬─────────────────────────────────┬─────────────────────┘
                │ HTTPS (SR-08)                   │ loopback only
                ▼                                 ▼
┌──────────────────────────────────────┐   ┌──────────────────────────┐
│ API layer                            │   │ Capture device + SDK     │
│  1 authenticate (session, expiry)    │   │ (procured — D-31)        │
│  2 module gate (prefix-based)        │   └──────────────────────────┘
│  3 permission check (per capability) │
│  4 SCOPE RESOLUTION — FAIL CLOSED ◄── the single highest-leverage fix
│  5 handler                           │
│  6 audit (before/after)              │
└───┬────────────┬────────────┬────────┘
    │            │            │
    ▼            ▼            ▼
┌────────┐  ┌─────────┐  ┌──────────────────┐   ┌────────────────────┐
│ Domain │  │ Document│  │ Biometric service│──►│ Matching engine    │
│ Crime  │  │ service │  │ enrol/1:1/1:N    │   │ (vendor or NBIS —  │
│ Chkpt  │  │ authz'd │  │ thresholds       │   │  D-33)             │
│ Finger │  │ hashed  │  │ encrypted store  │   └────────────────────┘
└───┬────┘  └────┬────┘  └────────┬─────────┘
    └────────────┴────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PostgreSQL — least-privilege app role, encryption at rest,           │
│ versioned migrations, append-only audit, tested backup/restore       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 Design principles

| # | Principle | Why it is stated |
|---|---|---|
| P-1 | **Unknown means deny.** Every scope resolution fails closed | Three separate fail-open defects (H-2b, M-2, CRR-102) share this one root cause |
| P-2 | **Authorize at the boundary, uniformly** | Scoping is applied at 9 sites and absent at 7 — because each handler decides for itself |
| P-3 | **Documents are objects, not paths** | `/uploads/` is public because files are served as static paths |
| P-4 | **Biometric data never leaves the server unencrypted and never reaches browser storage** | It is irrevocable |
| P-5 | **Audit records what changed, not that something changed** | Current UPDATE audits carry no before/after |
| P-6 | **Additive, reversible schema change** | No migration framework exists yet (M-11) |
| P-7 | **Verification by execution, not inspection** | 23 suites have never run |

---

## 3. Role and permission model

### 3.1 As built

Three independent mechanisms, inconsistently applied:

| Mechanism | Location | Behaviour |
|---|---|---|
| `ROLE_MODULES` | `:1865-1905` | Which UI modules / URL prefixes a role may reach. Applied **once per request** at `:8097-8112` (GET) and `:8869-8887` (POST) — this part is sound |
| `ROLE_PERMISSIONS` | `:2065-2080` | **Coarse.** Every CID and checkpoint role holds exactly `PERM_CID_VIEW`; HR holds `PERM_PERSONNEL_VIEW`; admin = `CHIEF_PERMISSIONS`; commander = `COMMANDER_PERMISSIONS`. It cannot express "may approve", "may assign", "may clear an alert" |
| `ROLE_LOCATION_SCOPE` / branch scope | `:1908-1925`, `:2624`, `:2661` | Which **records** a role may see. **Fails open in two of three implementations** |

`enforce_read_only()` at the top of `do_POST`/`do_PATCH`/`do_DELETE` → 403 for `chief_commander` is
**centrally applied and correct**; it is the model the scope checks should follow.

### 3.2 Target permission matrix *(proposed — requires sign-off, D-21)*

Capability-based, replacing the single `PERM_CID_VIEW` for every CID role.
**R** read · **W** create/update · **A** approve/authorise · **–** none · *(a)* audited exception

| Capability | Fingerprint officer | Fingerprint supervisor | CID investigator | CID supervisor | Station intake | Checkpoint officer | Checkpoint supervisor | SystemAdmin | Commander |
|---|---|---|---|---|---|---|---|---|---|
| Person registry — read | R | R | R | R | R | R | R | R | R |
| Person registry — create/enrich | W | W | W | W | W | W | W | – | – |
| Biometric capture / enrol | W | W | – | – | – | – | – | – | – |
| Biometric 1:1 verify | W | W | – | – | – | *(a)* | *(a)* | – | – |
| Biometric 1:N identify | W | W | *(a)* | *(a)* | – | *(a)* | *(a)* | – | – |
| Biometric template/image bytes | – | – | – | – | – | – | – | **–** | **–** |
| Biometric threshold config | – | – | – | – | – | – | – | A | – |
| Clearance application — create | W | W | – | – | – | – | – | – | R |
| Clearance — approve / reject | – | **A** | – | – | – | – | – | *(a)* | R |
| Crime case — read | – | – | R | R | – | – | – | R | R |
| Crime case — create / edit | – | – | W | W | – | – | – | – | – |
| Crime case — assign | – | – | – | **A** | – | – | – | – | – |
| Crime case — close / reopen | – | – | – | **A** | – | – | – | – | R |
| Incident report — create | – | – | – | – | W | – | – | – | – |
| Incident ↔ case linking | – | – | W | A | – | – | – | – | – |
| Evidence — upload | – | – | W | W | W | – | – | – | – |
| Evidence — withdraw | – | – | – | **A** | – | – | – | – | – |
| Suspect alert — create | – | – | W | W | – | – | – | – | R |
| Suspect alert — clear / expire | – | – | – | **A** | – | – | **A** | – | – |
| Checkpoint event — create | – | – | – | – | – | W | W | – | – |
| Checkpoint event — amend | – | – | – | – | – | *(a)* | A | – | – |
| Detention — record / release | – | – | – | – | – | W | **A** | – | R |
| Referral — raise / accept | – | – | – | A | – | W | A | – | R |
| False match — confirm | – | A | – | A | – | W | **A** | – | – |
| Reports — own scope | R | R | R | R | R | R | R | R | R |
| Reports — cross-branch | – | – | – | – | – | – | – | R | R |
| Cross-unit person view (R-14) | – | *(a)* | – | *(a)* | – | – | *(a)* | – | *(a)* |
| User / branch administration | – | – | – | – | – | – | – | **A** | – |
| Audit log — read | – | R | – | R | – | – | R | R | R |

**Three deliberate choices in this matrix:**

1. **`SystemAdmin` has no biometric data access and no investigative authority.** Administering the
   system is not authority over its contents.
2. **Nobody gets bulk biometric export**, including the commander (FPR-703).
3. **Approval authority is always separated from creation authority** (D-12).

---

## 4. Branch and location authorization model

### 4.1 The single highest-leverage fix in Release 1.0

Three resolvers exist; **two fail open**:

| Resolver | Site | Behaviour | Status |
|---|---|---|---|
| `branch_scope_view()` | `:2661-2694` | returns `None` ⇒ **unscoped** | **FAIL OPEN — H-2b** |
| `checkpoint_scope()` | `:2965-3000` (`:2990`) | blank scope ⇒ **no restriction** | **FAIL OPEN — M-2** |
| `require_record_branch_scope()` | `:2790-2805` | denies when unresolvable | **FAIL CLOSED — correct** |

Scoping is **present** at `:4281`, `:8201`, `:8244`, `:8260`, `:8283`, `:8557`, `:8922`, `:8952`,
`:9081`, `:9219` and **absent** at `:8152`, `:8425`, `:8997`, `:9032`, `:9092`, `:9172`, `:9581`.

| ID | Requirement |
|---|---|
| ARCH-401 | All three resolvers **fail closed**. An unresolvable posting yields 403. |
| ARCH-402 | Scope is resolved **once per request** in the pipeline (§2, step 4) — not re-derived in each handler. This is what makes "absent at 7 sites" structurally impossible to repeat. |
| ARCH-403 | A handler cannot opt out of scoping; it can only request a documented, permissioned, audited cross-scope action. |
| ARCH-404 | Location scope is **data** (officer→location assignments), not role constants (**D-20**). |
| ARCH-405 | A startup assertion refuses to boot with any role whose scope is blank or unresolvable. |
| ARCH-406 | Isolation tests assert on **record identifiers**, never on counts — a count test passes when both officers see zero rows. |
| ARCH-407 | `suspect_alerts` has **no `branch_id`** and therefore **cannot be scoped without DDL** (N-1). This is the only Release 1.0 access-control gap requiring a schema change, which places it behind the migration framework (M-11). |

### 4.2 Branch vs station vs location

Three distinct hierarchies are in play and the system currently conflates them:

- **Branch** (`police_branches`) — the CID organisational unit; scopes crime cases, clearances, checkpoint events
- **Station** (`police_stations`) — where incidents are reported; `crime_incidents.station_id` NOT NULL
- **Checkpoint location** — currently the hard-coded strings `South` / `East` / `West` (`:1649`)

`GET /api/crimes` scopes CID officers against **`police_station`** branches (`:8557`) while CID
postings resolve as **`crime`** — the mismatch that makes H-2b data-dependent. The target model
keeps the three hierarchies distinct and resolves each explicitly.

---

## 5. Document and attachment access model

### 5.1 As built — the most severe finding in the assessment

`/uploads/` is served at `:7914` **before any authentication check**. Every clearance scan, traveller
document, guardian document, case evidence file and officer photograph is retrievable by **anyone
who can reach the server**, with no credentials, from any branch. Paths are predictable.

Validation is also inconsistent: `/signed-document` enforces an extension allow-list and a 20 MB cap
(`:9009-9018`), while the general `save_upload()` (`:3939`) enforces **nothing**.

### 5.2 Target

| ID | Requirement |
|---|---|
| ARCH-501 | Documents are served **only** through an authenticated, authorized, audited endpoint. The static `/uploads/` route is removed. |
| ARCH-502 | A `document_objects` table holds owner entity, type, SHA-256, size, MIME, uploader, timestamp and retention class. Storage paths are **opaque** and never user-supplied. |
| ARCH-503 | Access is checked against the **owning record's** scope, not the file path. |
| ARCH-504 | **One** validation path: extension allow-list, MIME sniff, size cap, filename sanitisation — applied to every upload. |
| ARCH-505 | Every document read is audited (actor, document, owning record, timestamp). |
| ARCH-506 | Documents are stored outside the web root; direct filesystem exposure is not an access method. |
| ARCH-507 | **Biometric images and templates are not `document_objects`.** They use the restricted biometric store with its own access rules (FPR-701…710). |
| ARCH-508 | Attachment metadata moves out of TEXT JSON blobs (`applicant_docs`, `guardian_docs`, `traveler_docs`) into rows, so each document is independently authorizable (**N-6**). |

---

## 6. Audit logging

| ID | Requirement |
|---|---|
| ARCH-601 | **Append-only.** The application database role holds `INSERT` and `SELECT` on `audit_events` — **no UPDATE, no DELETE** (**H-7**). |
| ARCH-602 | Updates record **before and after** values. `audit(c,user,'UPDATE','crime_case',cid)` (`:9591`) records that something changed, not what. |
| ARCH-603 | **Authentication events are audited** — login success, login failure, logout, password change, privilege change. None are today (**H-4**). |
| ARCH-604 | Every audit row carries actor, role, source address, timestamp, entity type, entity id, action, before/after and outcome. |
| ARCH-605 | Authorization **denials** are audited, not only successes. A refused cross-branch attempt is a security signal. |
| ARCH-606 | **Overrides and exceptions are structured, queryable fields** — not free text inside a detail string (`:9071`). |
| ARCH-607 | Biometric template/image reads are individually audited (FPR-704). |
| ARCH-608 | Audit retention and archival follow **D-04**. |
| ARCH-609 | Audit reads are themselves authorized and audited. |
| ARCH-610 | Clock source is explicit and consistent — the schema already uses `CURRENT_TIMESTAMP AT TIME ZONE 'UTC'`; this is retained. |

---

## 7. API boundaries

**46 `/api/*` route prefixes exist.** Release 1.0 touches the following; the remainder (HR/conduct,
officers, stations, vehicles, airport) are **out of scope and must not be expanded**.

| Boundary | Routes | Release 1.0 change |
|---|---|---|
| **Auth / session** | `/api/login`, `/api/logout`, `/api/me`, `/api/me/password`, `/api/me/avatar` | Session expiry, revocation on privilege change, throttling, auth auditing, `Secure` cookie |
| **Person registry** *(shared)* | `/api/persons`, `/api/persons/`, `/api/persons/resolve`, `/api/persons/upsert` | Fail-closed scoping on write; record Tier 3/4 confirmations; **do not** load all persons into memory at scale (`:5490`) |
| **Fingerprint / clearance** | `/api/clearance-applications`, `/api/clearance-applications/<id>`, `.../signed-document`, `.../approve` | Branch scope on `/approve` and `/signed-document`; separation of duties; rejection path; restricted bypasses |
| **Biometric** *(NEW)* | `/api/biometrics/enrol`, `/verify`, `/identify`, `/thresholds`, `/match-events` | Entirely new boundary; never returns template bytes to a general client |
| **Crime — cases** | `/api/crime-cases`, `/api/crime-cases/<id>`, `.../evidence` | Branch scope on PATCH and evidence; status transition table; filters; pagination |
| **Crime — incidents** | `/api/crimes` | Fail-closed scope; evidence as rows |
| **Crime — linking** *(NEW)* | `/api/crime-cases/<id>/incidents` | Pending D-15 |
| **Crime — assignment** *(NEW)* | `/api/crime-cases/<id>/assignments` | Pending D-21 |
| **Suspect alerts** | `/api/suspect-alerts` | **Branch scope (needs `branch_id` DDL)**; lifecycle |
| **Checkpoint** | `/api/checkpoint-events` | Fail-closed location scope; GET-by-id; audited amendment; detention/referral/false-match sub-resources |
| **Documents** *(NEW)* | `/api/documents/<id>` | Replaces static `/uploads/` |
| **Analytics / reports** | `/api/analytics`, `/api/cid/analytics`, `/api/dashboard` | Scope **every** builder by `user`; filters; drill-down; audited export |
| **Audit** | `/api/audit/entity/<type>/<id>`, `/api/admin/audit` | Before/after values; denial events |
| **Admin** | `/api/admin/users`, `/api/admin/branches` | Last-admin protection; session revocation on privilege change. **No expansion beyond this** |

**Boundary rules**

| ID | Requirement |
|---|---|
| ARCH-701 | Authorization is enforced **server-side at the boundary**. Hiding a module in `ROLE_MODULES` is a usability measure; the API gate is the control (**D-13**, **D-16**). |
| ARCH-702 | Every list endpoint supports server-side filtering and pagination within the scope predicate. |
| ARCH-703 | No endpoint returns records the caller could not retrieve individually. |
| ARCH-704 | `Access-Control-Allow-Origin: *` (`:7773`) is replaced by an explicit allow-list (**N-4**). |
| ARCH-705 | Error responses do not disclose record existence across scope boundaries (404, not 403-with-detail). |
| ARCH-706 | The biometric boundary is **internal-only**; the browser receives decisions and metadata, never templates. |

---

## 8. Biometric hardware and software boundary

```
 Officer workstation                │  Server
 ───────────────────────────────────┼──────────────────────────────────────
 Scanner (D-31)                     │
   └─ vendor SDK/driver (E-2)       │
        └─ bridge service (D-32)    │
             loopback 8080/9001/11100
             /health /scan/info     │
             /scan  ws:/biometrics  │
                  │                 │
                  ▼                 │
            SPA bridge client ──────┼──► POST /api/biometrics/enrol|verify|identify
            (R-1, retained)   HTTPS │         │
                                    │         ├─► template extraction (D-33)
                                    │         ├─► matcher 1:1 / 1:N (E-4)
                                    │         ├─► threshold policy (FPR-241)
                                    │         └─► encrypted template store (FPR-701)
```

| ID | Requirement |
|---|---|
| ARCH-801 | The bridge is **loopback-only**. The browser never calls a non-local address for capture. |
| ARCH-802 | The bridge protocol is **versioned**; the server rejects unsupported versions. |
| ARCH-803 | The bridge is **out of this repository's scope to build** (**D-32**) and is an **endpoint deployment obligation** on every capture workstation. |
| ARCH-804 | **Where template extraction runs — bridge or server — is D-33** and determines whether raw images cross the network. |
| ARCH-805 | The matching engine is isolated behind an interface so the vendor can change without touching domain code. |
| ARCH-806 | Matching **never** runs in the browser. |
| ARCH-807 | The bridge's absence degrades to the manual path (FPR-805) and never to a fabricated result (FPR-902). |

---

## 9. How the three units share data without over-granting

**The shared object is `persons`** — the Central Person Registry. All three units create, enrich and
read it, and that is correct: one person, one record.

**The risk is that shared identity becomes shared access.** A checkpoint officer legitimately needs
to know a person is flagged; they do **not** need the investigation file. A fingerprint officer needs
identity; they do not need crime narratives.

### 9.1 Sharing rules

| ID | Rule |
|---|---|
| ARCH-901 | **The person record is shared; unit records are not.** Access to `persons` never implies access to a unit's records about that person. |
| ARCH-902 | **Cross-unit signals are minimal.** A checkpoint receives *"this person has an active alert"* plus the minimum needed to act — not the case file. The screening logic at `:9304-9307` already works this way; the model is right and must be preserved under the new permission matrix. |
| ARCH-903 | **The cross-unit person view (report R-14) is a privileged, audited capability** (**D-41**), never a default. |
| ARCH-904 | **Branch scope applies within each unit independently.** Sharing a person does not share a branch boundary. |
| ARCH-905 | **Biometric data is not shared as data.** Other units consume **match decisions**, never templates. |
| ARCH-906 | **Enrichment never overwrites.** `enrich_person()` (`:5565`) fills only empty fields — correct, and retained. Overwriting an identity field must be an explicit, audited correction. |
| ARCH-907 | **Alert state is authoritative in one place.** A cleared alert stops flagging everywhere within one request cycle (CKR-423). |
| ARCH-908 | **Analytics respect unit boundaries.** `CID_ANALYTICS_SECTIONS` already returns only the caller's own section (`:6310`) — retained, and extended with the branch scoping that two of the three builders lack. |

### 9.2 Shared-data flow

```
            ┌──────────────────── persons (shared identity) ───────────────────┐
            │                            │                                     │
   Fingerprint Unit               Crime Unit                          Checkpoint Unit
   ───────────────                ──────────                          ───────────────
   clearance_applications         crime_cases                         checkpoint_events
   biometric_enrolments (NEW)     crime_incidents                     detentions   (NEW)
   match_events        (NEW)      case_participants (NEW)             referrals    (NEW)
            │                     case_evidence                       false_matches(NEW)
            │                            │                                     │
            │   match decision only      │        alert signal only            │
            └───────────────────────────►├────────────────────────────────────►│
                   (never templates)     │   (never the case file)             │
                                         │                                     │
                                  suspect_alerts ◄── cleared alert stops flagging
                                  (+branch_id NEW)
```

---

## 10. Cross-cutting technical requirements

| ID | Requirement | Finding |
|---|---|---|
| ARCH-1001 | **Versioned migrations** with a `schema_migrations` table and rollback. DDL must stop executing as a startup side effect — this blocks every schema change in Release 1.0 | M-11 |
| ARCH-1002 | **Dependency manifests** (`requirements.txt`, `package.json`) with pinned versions | M-10 |
| ARCH-1003 | **A runnable test environment.** 23 of 25 suites have never executed. This is the **prerequisite for every acceptance criterion in this package** | WP-01 |
| ARCH-1004 | **CI** running the full suite on every change | — |
| ARCH-1005 | **TLS** everywhere; `Secure`, `HttpOnly`, `SameSite` cookies | H-8 |
| ARCH-1006 | **Least-privilege database role** (not superuser), encryption at rest | M-8 |
| ARCH-1007 | **Tested backup and restore**, with stated RPO/RTO | M-12, D-08 |
| ARCH-1008 | **Security headers** (CSP, HSTS, X-Content-Type-Options, X-Frame-Options) | N-5 |
| ARCH-1009 | **Remove dead code** before release: `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py` | M-10 |
| ARCH-1010 | **Structured logging and health monitoring** sufficient to detect an outage | M-12 |

> **Deliberately NOT recommended for Release 1.0:** replacing the stdlib HTTP stack with a framework ·
> splitting `server.py` into modules · componentising the SPA · introducing an ORM · containerising.
> Each is defensible long-term; none fixes a release blocker, and all four would consume the
> schedule while destabilising the one part of the system that currently works.

---

## 11. Architecture decisions required

| ID | Decision | Blocks |
|---|---|---|
| **D-15** | Incident/case model — recommendation: separate, linked (Option A) | Crime model, 2 reports |
| **D-21** | CID role structure and capability matrix | §3.2, assignment |
| **D-20** | Location catalogue and officer→location assignment | §4, checkpoint scope |
| **D-25** | Case status vocabulary and transitions | Status engine, 4 reports |
| **D-31/32/33/35** | Scanner · bridge ownership · matcher and template format · fingers captured | §8 entirely |
| **D-36/37** | Image retention · cross-branch 1:N | Biometric storage and authz |
| **D-41** | Cross-unit person view | §9.1 |
| **D-13/D-16** | Module visibility vs API enforcement | §7 |
| **D-03** | Password hashing algorithm — recommendation: stdlib PBKDF2-HMAC-SHA256, no new dependency | Auth |
| **D-08** | Session policy, separated from RPO/RTO | Auth, backup |
| **D-07** | Expected scale | Indexing, 1:N performance, pagination |
| **D-04/D-05** | Retention · DPIA and lawful basis | Biometric and document retention |
