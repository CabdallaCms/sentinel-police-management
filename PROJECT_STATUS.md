# PROJECT_STATUS.md — Sentinel Police Management System

**Live status document.** Updated in the same change set as the work it describes.
Rules governing this file: `PROJECT_CONTEXT.md` §14.3.

> **Honesty rule (binding).** No progress percentage is invented here. No work is marked complete
> without recorded evidence. Anything not assessed is labelled **"Not yet verified."**

---

## 1. Identification

| Field | Value |
|---|---|
| **Project name** | Sentinel Police Management System |
| **Repository** | `CabdallaCms/sentinel-police-management` |
| **Current release** | **CID Release 1.0** |
| **Current project phase** | **Phase 3 complete — CID Release 1.0 requirements and architecture package delivered. Awaiting owner review, the remaining blocking decisions, and explicit approval before any application change.** No implementation work is authorised. |
| **Current Git branch** | `arena/6303ef2f-sentinel-police-management` |
| **Current commit hash** | `a1c2478262776e9f20b4c3ad806eaa86adc27792` (`a1c2478`) |
| **Commit date / subject** | 2026-10-27 17:13:20 +0000 — *"Branch Management: full CRUD (edit/deactivate) + legacy placement cleanup"* |
| **Last verified commit** | `a1c2478262776e9f20b4c3ad806eaa86adc27792` — verified 2026-11-06 by repository inspection; identical to `origin/main` at that time. Phases 2 and 3 assessed this same commit; **no application file was modified in any phase** |
| **Build identity (verified)** | `sentinel-branch-crud-1-e7c41b90` (`python3 backend/server.py --ui-check` → exit 0) |
| **Last update date** | **2026-11-06** (Phase 3 — requirements and architecture package; supersedes the Phase 2 assessment update and the Phase 1 baseline of the same date) |
| **Assessment deliverables** | `assessment/` — seven Phase 2 documents, indexed in §12 |
| **Requirements and architecture deliverables** | `requirements/` (5), `architecture/` (2), `planning/` (1) and root `DECISION_REGISTER.md` — ten Phase 3 documents, indexed in §14 |
| **Release 1.0 scope (owner-confirmed 2026-11-06)** | Fingerprint Unit **including genuine biometric capture and matching** (**D-18 = BOTH**) · Crime Unit full operations including advanced reports (**D-14** catalogue approved as a starting point) · Checkpoint Unit existing functionality plus gaps · shared CID capabilities. **Airport Unit excluded → Release 1.1** (**D-16**) |

---

## 2. Unit status

> Scope definitions are in `PROJECT_CONTEXT.md` §3–§5 and `RELEASE_PLAN.md`. This section reports
> **state**, not scope.
>
> **Updated 2026-11-06 by the Phase 2 assessment.** Every feature in the three units was classified as
> *Implemented and verified* · *Implemented but not verified* · *Partially implemented* · *Not
> implemented* · *Blocked*. Full evidence, with file and line citations, is in
> `assessment/CID_TECHNICAL_ASSESSMENT.md`.
>
> **Binding caveat on the word "verified".** Only **one** feature area in the entire system is
> *Implemented and verified*: the A4 print contract (`backend/test_print_fit.py`, executed
> 2026-11-06 → PASS). **23 of 25 test suites still cannot be executed** (missing `psycopg2-binary`,
> `pgserver`, `jsdom@26`; installing them was out of scope), so almost everything that works is
> recorded as *Implemented but **not** verified*. That is a statement about the project's evidence,
> not a criticism of the code.
>
> **Phase 3 addendum (2026-11-06).** Owner decision **D-18 = BOTH** means the Fingerprint rows below
> are measured against a **smaller** scope than Release 1.0 now requires. Genuine biometric capture,
> template storage, 1:1 verification and 1:N identification are **Not implemented** — the system
> stores no biometric data server-side and its "matching" is string comparison
> (`index.html:4526`), with a fallback that returns an arbitrary person by rotating a cursor
> (`index.html:4573`). The owner-reported "~80% complete" figure for this unit is therefore **not
> applicable** to the approved scope. See `requirements/FINGERPRINT_UNIT_REQUIREMENTS.md` §0.

### 2.0 Classification roll-up (Phase 2, commit `a1c2478`)

| Unit | Implemented and verified | Implemented but not verified | Partially implemented | Not implemented | Blocked |
|---|---|---|---|---|---|
| **Fingerprint** | 1 | 9 | 5 | 6 | 2 |
| **Crime** | 0 | 7 | 4 | 10 | 3 |
| **Checkpoint** | 0 | 8 | 3 | 5 | 1 |

> No percentage is derived from this table. Counts are of assessed feature areas, which are not of
> equal size, so they must not be converted into a completion figure.

### 2.1 Fingerprint Unit — Release 1.0 · Unit A

| Field | Value |
|---|---|
| **Overall status** | **Assessed 2026-11-06.** The police-clearance workflow is substantially built. **Biometric capture and matching are not implemented server-side at all.** Classification: 1 verified · 9 unverified · 5 partial · 6 not implemented · 2 blocked. |
| **Owner-reported progress** | "approximately 80%" — **assessed and found neither supportable nor refutable from the repository, and not adopted.** **D-18 is now closed as BOTH** (clearance *and* genuine biometric capture and matching), so the figure is **definitively not applicable** to Release 1.0 scope: biometric storage, template generation, 1:1 verification and 1:N identification do not exist. Retained here as an owner report only; it must not be cited as measured progress. |
| **Evidence that implementation exists (verified at `a1c2478`)** | `clearance_applications` + `clearance_signed_documents` tables (`backend/server.py:265`, `:281`); endpoints `/api/clearance-applications` (incl. `/approve`, `/signed-document`, `/documents`) and `/api/fingerprint/applications`; role `FingerprintUnit` with modules `{dashboard, people, fingerprint}`; 12-hour review gate armed by a boot-time self-test (`review_lock_armed()`, `backend/server.py:1057`, enforced `:10022`); printable `application.html` and `certificate.html` pinned by `backend/test_print_fit.py` (**executed 2026-11-06 → PASS**) |
| **Phase 2 findings (verified by code reading at `a1c2478`)** | **Biometrics are not stored server-side.** Captures live in browser `localStorage` under `sentinelBiometrics` (`index.html:2698-2725`); matching is client-side **string** comparison (`matchPersonByFingerprint`, `index.html:4526`); the USB scanner bridge it calls (`http://127.0.0.1:<port>/scan`, `ws://localhost:<port>/biometrics`, `index.html:4773-5183`) **has no code in this repository**; the server's `total_biometrics_logged` metric counts clearance applications, not biometrics. **No rejection path exists** — the API can only move an application to `Approved`. **No separation of duties** — the submitter may approve their own application. 21 gaps catalogued as FG-01…FG-21. |
| **Not assessed** | Runtime behaviour of any of the above — 23 suites remain unrunnable |
| **Security findings confirmed present** | C-1 (unauthenticated document retrieval) · H-2a (cross-branch approve **and** signed-scan — neither route performs a branch check) · M-3 (self-approval; `Citizenship` and admin bypass of the 12-hour gate) · M-7 (unvalidated applicant/guardian uploads) · identifier collision risk on `FP-`/`CL-` millisecond ids |
| **New decisions raised** | **D-18** (is Release 1.0 clearance-only or real biometrics? — scanner, SDK, bridge ownership, template storage) · **D-19** (rejection path: who, reason codes, applicant notification) |
| **Next step** | Owner answers **D-18** and **D-19**; see `assessment/FINGERPRINT_UNIT_GAP_ANALYSIS.md` for the close-out order. **No work authorised.** |

### 2.2 Crime Unit — Release 1.0 · Unit B

| Field | Value |
|---|---|
| **Overall status** | **Assessed 2026-11-06.** Case registration, the case workspace, participant listing and evidence upload exist. **Case assignment, investigation workflow, suspect lifecycle, chain of custody, closure control and advanced reporting do not exist.** Classification: 0 verified · 7 unverified · 4 partial · 10 not implemented · 3 blocked. **This is the largest body of outstanding work in Release 1.0.** |
| **Evidence that implementation exists (verified at `a1c2478`)** | `crime_cases` (`backend/server.py:292`), `crime_incidents` (`:374`), `suspect_alerts` (`:299`), `case_evidence` (`:309`); endpoints `/api/crime-cases`, `/api/crimes`, `/api/suspect-alerts`, `/api/cid/analytics`; role `CIDUnit` with modules `{dashboard, people, cid, crimes}`; three-tab CID case workspace (Case Details · Participants & Suspect Linkage · Evidence & Media) documented in `README.md`; branch-scoped crime writes via `require_branch_write_scope(..., 'crime')` (`:9081`) and branch-scoped single-case reads via `require_record_branch_scope(..., 'crime', ...)` (`:8283`) |
| **Advanced reports** | **Assessed: a basic dashboard exists; advanced reporting does not.** `cid_crime_analytics(c)` (`:6132-6172`) produces 7 fixed metrics and 5 fixed charts with **no date filter, no filter of any kind, no export, no drill-down, no trend over time, and no branch scoping** (the builder takes no `user`, so branch-scoped officers receive **national** figures). 18 candidate report types derivable from existing columns are catalogued for owner selection in `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` §12. Still blocked on **decision D-14**. |
| **Phase 2 findings (verified by code reading at `a1c2478`)** | **No case-assignment model of any kind** (`grep assigned_to\|investigator\|assignee\|officer_in_charge` → **0** hits). **Four competing status vocabularies**: `CASE_STATUSES` (7, `:1716`), `CRIME_STATUSES` (5, `:1708`), the case-workspace `<select>` (4, `index.html:1730`), and free text accepted by `PATCH /api/crime-cases/<id>` — no state machine, no transition rules. **`suspect_alerts` has no `branch_id` column**, and `GET /api/suspect-alerts` (`:8425`) applies **no filter at all** — every officer nationwide reads every suspect, victim and witness listing. **Three write paths bypass branch isolation**: case PATCH (`:9581`), evidence POST (`:9092`), suspect-alert POST (`:9172`). `case_id` is `'CID-2026-' + COUNT(*)+8` (`:9083`) — hard-coded year, global counter, race-prone. **No dedicated Crime Unit test suite exists.** |
| **Open modelling question — now analysed** | **D-15.** `crime_cases` and `crime_incidents` have **no foreign key and no shared identifier**, and no code path reads one while writing the other. They are **not duplicates**: `crime_incidents` is a station intake record (victim block, severity, `incident_at`), `crime_cases` is a CID investigation file (participants, unbounded evidence). Three options with risks are set out in `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` §2.3. **Still the owner's decision.** |
| **Requirements proposal** | `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` — covers all ten required areas (registration · assignment · investigation workflow · suspect management · evidence · status & progression · responsibilities & permissions · search & filtering · advanced reports & statistics · audit history). **PROPOSED, NOT APPROVED.** Every requirement is either traced to existing code or marked `[NEEDS OWNER APPROVAL]`; none was invented. |
| **New decisions raised** | **D-21** (CID role structure; who assigns cases) · **D-22** (investigation workflow) · **D-23** (legal rules for suspect listing) · **D-24** (evidence chain of custody) · **D-25** (authoritative status vocabulary and transitions) · **D-26** (search filters, sort, pagination) |
| **Scope guard** | **Must not** be reduced to basic case registration to meet a date (`PROJECT_CONTEXT.md` §3.2, §15.5) |
| **Next step** | Owner reviews the requirements proposal and answers **D-14** and **D-15** first — the unit **cannot be sized** until both are answered. **No work authorised.** |

### 2.3 Checkpoint Unit — Release 1.0 · Unit C

| Field | Value |
|---|---|
| **Overall status** | **Assessed 2026-11-06.** Screening **capture** is built and is the most thorough intake form in the system. **Location isolation fails open for the canonical role, and there is no post-flag workflow.** Classification: 0 verified · 8 unverified · 3 partial · 5 not implemented · 1 blocked. |
| **Owner-reported status** | "already implemented" — **assessed and partially contradicted.** The unit can *record* a stop very well; it cannot yet be trusted to *contain* that record, and it cannot record the operational response to a flag. |
| **Evidence that implementation exists (verified at `a1c2478`)** | `checkpoint_events` table (`backend/server.py:316`); `/api/checkpoint-events`; unified `checkpoint_officer` role plus legacy `CheckpointSouth`/`East`/`West`, all with modules `{dashboard, checkpoints}` and one shared label (`ROLE_LABELS`, `:1816`); branch-scoped writes via `require_branch_write_scope(..., 'checkpoint')` (`:9219`); location scoping documented in `README.md` (`scope` + `visible_locations` on read, rejection of out-of-location writes); `backend/test_checkpoint_roles_audit.py` exists |
| **Phase 2 findings (verified by code reading at `a1c2478`)** | **Historical finding M-2 is confirmed, and it is worse than reported.** `ROLE_LOCATION_SCOPE[ROLE_CHECKPOINT_OFFICER] = ''` (`:1922`) and `checkpoint_scope()` returns `… or ''` (`:2990`); both call sites guard with `if scope:`, so a blank scope applies **no filter** — the canonical `checkpoint_officer` role **reads every location** (`:8460`) **and may write to any location** (`:9301`). The in-code comment states the opposite intent. Perversely, the **legacy** `CheckpointSouth/East/West` roles are **safer**. `location_scope` is also not mandatory at user creation. **Reads are never filtered by `branch_id`** — only by location string, via a six-way `OR`/`ILIKE` match across three columns that encode one fact. **`screening_result` and `action_taken` are server-computed** with two possible values each (`:9305-9306`): an officer cannot record a detention, refusal, referral, false match or handover, and "Supervisor contacted" is a string that notifies nobody. No `PATCH`, no single-event read route, no vehicle linkage on the event. |
| **Security findings confirmed present** | **M-2** (scope fail-open, read **and** write — reclassified **HIGH** in the remediation list) · **H-2b** (posting fail-open) · **C-1** (traveller photographs and ID scans retrievable without authentication) · **M-7** (unvalidated traveller/guardian uploads) |
| **Hard dependency** | The unit's entire value rests on `suspect_alerts`, which has **no branch column** and **no lifecycle** — an alert is written as `'Active alert'` and never changes, so a person cleared by CID keeps flagging at every checkpoint indefinitely. The post-flag workflow cannot be built before the Crime Unit's suspect lifecycle. |
| **Critical coverage gap** | **No test suite asserts that a `checkpoint_officer` with a blank `location_scope` is denied.** The suites are silent precisely where the control fails. The navigation suites assert what the **UI hides**, which cannot prove what the **server refuses**. |
| **New decisions raised** | **D-20** (fixed South/East/West catalogue vs named district checkpoints) · **D-27** (what outcomes an officer must be able to record, and the authorised post-flag procedure) · **D-28** (must a stop record the vehicle?) |
| **Next step** | Owner answers **D-20** and **D-27**; see `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md` §11 for the close-out order. **No work authorised.** |

### 2.4 Airport Unit — POSTPONED to CID Release 1.1

| Field | Value |
|---|---|
| **Release 1.0 status** | **Out of scope. Postponed to CID Release 1.1.** |
| **Code present?** | **Yes — verified.** `airport_passengers` table, `/api/airport-records`, role `AirportControl` `{dashboard, people, airport}`, branch `unit_type='airport'`, airport passenger register page |
| **Action during Release 1.0** | **Frozen.** Do not implement, expand, redesign or add Airport features. Do not delete it either. |
| **Open decision** | **D-16** — is the Airport module enabled or hidden in the Release 1.0 build? |

---

## 3. Completed and verified work

**Completed in the Phase 2 assessment session (2026-11-06, commit `a1c2478`):**

| Item | Evidence |
|---|---|
| CID Release 1.0 technical and functional assessment of all three units, with all ten required reporting items per unit | `assessment/CID_TECHNICAL_ASSESSMENT.md` |
| Every assessed feature classified against the five-value scale; roll-up published | §2.0 above; deliverable 1 §1 |
| Fingerprint Unit gap analysis — 15 existing capabilities, 21 gaps (FG-01…FG-21), test-gap table, close-out order | `assessment/FINGERPRINT_UNIT_GAP_ANALYSIS.md` |
| Crime Unit requirements **proposal** covering all ten required areas, with the `crime_cases` ↔ `crime_incidents` analysis and an 18-item advanced-report menu | `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` |
| Checkpoint Unit gap analysis — 17 existing capabilities, 17 gaps (G-01…G-17) | `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md` |
| Security re-verification: **23 findings** (3 CRITICAL, 10 HIGH, 7 MEDIUM, 3 LOW), each with severity, file+endpoint, evidence, impact, remediation and a required verification test; static findings separated from runtime-historical ones | `assessment/SECURITY_REMEDIATION_PRIORITY.md` |
| All **eight** headline concerns of the PR #23 audit re-checked against current code — **all eight still present**; concern #3 (fail-open scope) found **wider** than reported | Deliverable 1 §6 |
| Decision register reviewed and extended: D-01…D-17 carried forward, **D-18…D-29 raised**; grouped into blocking / can-wait / legal-operational / recommended-option-with-risks | `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` |
| Effort estimated in **engineering days** (never percentages) across 40+ work packages, with a dependency graph, three chokepoints, two critical chains, and a proposed development order | `assessment/DEPENDENCIES_AND_ESTIMATES.md` |
| Verdict delivered on the proposed 10-day sprint | Deliverable 7/8 §7 |
| Runnable checks re-executed at `a1c2478` | `--ui-check` → exit 0 (build `sentinel-branch-crud-1-e7c41b90`); `test_print_fit.py` → PASS |
| **No application code, schema, configuration, dependency or deployment artefact changed** | `git status` — changes confined to `assessment/`, `PROJECT_STATUS.md`, `CHANGELOG.md` |

**Completed and verified in the Phase 1 documentation session (2026-11-06):**

| Item | Evidence |
|---|---|
| Project documentation baseline created — `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md`, `RELEASE_PLAN.md`, `CHANGELOG.md` | Files present at repository root on branch `arena/6303ef2f-sentinel-police-management` |
| Baseline branch and commit recorded | `git rev-parse HEAD` → `a1c2478262776e9f20b4c3ad806eaa86adc27792`; identical to `origin/main` |
| Working tree confirmed clean before documentation | `git status --porcelain` → 0 lines |
| Technology stack and database schema documented from code, not assumption | `backend/server.py` DDL; `backend/vehicles.py`; `.env.example`; `git ls-files` (44 tracked files) |
| Role model and module grants documented from code | `ROLE_*`, `ROLE_LABELS` (`:1816`), `ROLE_MODULES` (`:1865`) |
| Served-UI identity verified | `python3 backend/server.py --ui-check` → exit 0, build `sentinel-branch-crud-1-e7c41b90` |
| One dependency-free test suite executed and passing | `python3 backend/test_print_fit.py` → `ALL PRINT TEMPLATE TESTS PASSED` |
| Existence and location of the earlier security audit established | PR **#23** (DRAFT, OPEN), branch `arena/8834f56d-sentinel-police-management` head `7da888b`, file `DEPLOYMENT_AUDIT.proposed.md` (1,522 lines); **not present on `main`** |
| Audit findings re-checked **statically** against current code | See §6 — eight findings confirmed still present at code level; three could not be checked without a running system |

**Completed in prior sessions (recorded, not re-verified by this session):**

11 merged pull requests (#1, #2, #3, #7, #10, #11, #12, #14, #15, #18, #19, #20, #21, #22 as reported by
`gh pr list --state all`), culminating in the current `main` commit `a1c2478`. The *functional
correctness* of that prior work has **not** been re-verified at this baseline.

---

## 4. Work in progress

**None.** No implementation work is authorised or under way.

Phase 2 (assessment) is complete as of 2026-11-06. The project is **stopped, awaiting owner
approval** and the fifteen decisions that block Release 1.0.

---

## 5. Work not started

> Updated by Phase 2. Items completed by the assessment have been removed; everything below is still
> not started, and **none of it is authorised**.

| Item | Work package | Blocked on |
|---|---|---|
| **Dependency manifests + a runnable test environment** (23 of 25 suites still cannot execute) | WP-01 | Owner approval — **this is the single highest-leverage item in the project** |
| Remediation of the 3 CRITICAL findings (C-1, C-2, C-3) | WP-03, WP-04, WP-05 | Owner approval; D-03 for the password policy |
| Fail-closed branch scope (shared control behind 10 call sites) | WP-06 | Owner approval |
| Fail-closed checkpoint location scope | WP-07 | Owner approval; **D-20** |
| Record-scope checks on the five unscoped write paths | WP-08 | Owner approval |
| Security regression suite (~30 named tests, none of which exist) | WP-15 | WP-01 |
| Session lifecycle, admin guards, authentication auditing | WP-10…WP-12 | Owner approval; **D-08**, D-09 |
| Versioned database migrations; removal of boot-time migration side effects | WP-16 | Owner approval — **gates all schema work** |
| `suspect_alerts.branch_id` (the only Release 1.0 access-control gap needing DDL) | WP-17 | WP-16; D-05 |
| Fingerprint rejection path and status model | WP-22 | **D-19** |
| Crime Unit: incident↔case link, assignment, status machine, investigation log, suspect lifecycle, chain of custody, search, advanced reports, test suite | WP-27…WP-35 | **D-14, D-15, D-21…D-26** |
| Checkpoint: configurable catalogue, branch read filtering, outcome recording, post-flag workflow | WP-36…WP-41 | **D-20, D-27**; WP-31 |
| Biometric capture programme (scanner, SDK, bridge service, template storage, matching) | WP-45 | **D-18** — **unestimable until answered** |
| Detailed implementation schedule and task order | — | Owner approval **after** the blocking decisions are answered |
| Retirement/rewrite of the two obsolete SQLite-era test harnesses | — | Owner approval |
| Environment separation (Development / Staging / Production); TLS topology | WP-20 | Owner approval + decisions D-01, D-02, D-07, D-08, D-09 |
| Backup, restore, rollback and monitoring procedures | WP-44 | Owner approval + decisions D-08, D-09 |

---

## 6. Known defects and security blockers

> **Source:** the earlier deployment audit (`DEPLOYMENT_AUDIT.proposed.md`, PR #23, audited revision
> `381545c` — the immediate **parent** of the current baseline commit `a1c2478`).
> **These are historical audit findings, not automatically current defects.** The "Status at `a1c2478`"
> column records only what could be established **without running the application**, since running the
> full suite required installing dependencies, which was out of scope in both phases.
>
> **Updated 2026-11-06 by the Phase 2 security review.** Several items the audit could only report at
> runtime are now **statically confirmed** (notably **H-4** and **H-5**), and **six findings new to
> this assessment** were added (**N-1…N-6**). The full register — 24 findings, each with severity,
> affected file and endpoint, evidence, impact, remediation and a **required verification test** — is
> `assessment/SECURITY_REMEDIATION_PRIORITY.md`. **The audit's identifiers are preserved exactly**; a
> numbering conflict found while drafting is reported in that document §0.2 rather than silently
> resolved, and PR #23 itself remains untouched.
>
> **Current totals: 3 CRITICAL · 10 HIGH · 8 MEDIUM · 3 LOW = 24 findings. Zero verified as fixed.**
> Two carried findings were re-rated by this assessment without changing their identifiers:
> **M-2 up to HIGH** (it affects the canonical role and permits writes) and **H-6 down to MEDIUM**
> (data-integrity impact rather than unauthorised access).

### 6.1 Security blockers — Critical

| ID | Finding | Status at `a1c2478` | Method |
|---|---|---|---|
| **C-1** | Uploaded police documents downloadable without authentication (`GET /uploads/<file>`) | **Still present at code level.** `/uploads/` is handled inside `serve_static()`, which `do_GET` invokes before any authentication | Static: `backend/server.py:7914`; `do_GET` entry calls `serve_static()` first |
| **C-2** | Default seeded accounts sharing a publicly documented password (`ChangeMe123!`) | **Still present at code level.** Nine seeded accounts | Static: `backend/server.py:3304+`; `README.md:566-589` |
| **C-3** | Unsalted SHA-256 password hashing | **Still present.** `def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()` | Static: `backend/server.py:3362` |

### 6.2 Security blockers — High

| ID | Finding | Status at `a1c2478` | Method |
|---|---|---|---|
| **H-2a** | Branch-level access-control failure: cross-branch write/approve on `/approve`, `/signed-document`, `/persons/<id>/documents` | **Still present at code level.** None of these three routes calls `require_record_branch_scope()` | Static: routes at `:8152`, `:8997`, `:9032`; call sites only at `:4281`, `:8244`, `:8283` |
| **H-2b** | Branch scope **fails open** when an officer's posting does not resolve to a registered branch | **Still present.** `branch_scope_view()` returns `None` (= unrestricted) when `resolve_posting_branch()` finds nothing | Static: `backend/server.py:2661-2694` |
| **H-3** | Sessions never expire; password reset does not revoke existing sessions | **Fully confirmed statically (Phase 2).** `sessions(token, user_id, created_at)` has **no expiry column** (`:446-449`) and `require_auth()` performs no age check (`:4004-4030`). Reset-revocation: the **only** two `DELETE FROM sessions` statements are logout (`:3998`) and the **self-service** password change (`:8759`); the administrative reset path (`:9638-9730`) has **none** | Static: `:446`, `:3976`, `:4004`, `:8759`, `:9638` |
| **H-5** | Administrator self-demotion causing permanent lockout | **Now confirmed statically (Phase 2).** No last-admin guard and no self-demotion guard exist anywhere; `PATCH /api/admin/users/<id>` also changes `password_hash`, `role` and `active` **without revoking sessions**, and deactivation leaves the session row intact so it **revives on reactivation** (`require_auth` filters on `active=1` at auth time only) | Static: `:9638-9730`, `:4004-4030` |
| **H-4** | No login throttling/lockout; authentication events not audited | **Now confirmed statically (Phase 2).** `POST /api/login` (`:8664-8678`) calls `audit()` on **neither** the success nor the failure path, and no rate-limit, backoff or lockout implementation exists anywhere in the codebase; logout (`:8680`) is also unaudited | Static: `:8664`, `:8680`, `:4032` |
| **H-6** | Registration/identifier generation races producing spurious `409`s | **Mechanism confirmed statically (Phase 2); the race itself not reproduced.** `case_id = 'CID-2026-' + COUNT(*)+8` (`:9083`) is a read-then-write global counter **with a hard-coded year**; `FP-`/`CL-`/`CP-` ids are the last 8 digits of epoch ms (`:9066`, `:9319`). **Re-rated MEDIUM** by this assessment | Static: `:9066`, `:9083`, `:9319` |
| **H-7** | Incomplete and mutable audit trail | **Fully confirmed statically (Phase 2).** `audit_events` has no immutability mechanism, no IP/user-agent/session id and no before/after values — e.g. `audit(c, user, 'UPDATE', 'crime_case', cid)` (`:9591`) records *that* a case changed, not *what* changed. Authentication events are absent entirely (H-4) | Static: `:450-454`, `:4032-4035`, `:9591` |
| **H-8** | No HTTPS; no `Secure` cookie; token duplicated into `localStorage` | **Confirmed statically (Phase 2).** Zero matches for `ssl.`/`wrap_socket`/HTTPS listener in `backend/server.py`; the session cookie is set `HttpOnly; SameSite=Lax` **without `Secure`** (`:8677`); no reverse-proxy, Dockerfile or systemd artefact exists in the repository. Whether production terminates TLS elsewhere is **[NOT VERIFIED]** | Static: `:8677`, `git ls-files` |

### 6.3 Security blockers — Medium (selected, carried forward)

| ID | Finding | Status at `a1c2478` |
|---|---|---|
| **M-2** | Clearing a checkpoint officer's `location_scope` widens them to every checkpoint | **Confirmed statically (Phase 2) and found wider than reported — re-rated HIGH.** `ROLE_LOCATION_SCOPE[ROLE_CHECKPOINT_OFFICER] = ''` (`:1922`) and `checkpoint_scope()` returns `… or ''` (`:2990`); both call sites guard with `if scope:`, so a blank scope applies **no filter on reads (`:8460`) and none on writes (`:9301`)**. The in-code comment states the opposite intent. The **legacy** South/East/West roles are safer |
| **M-3** | The 12-hour review gate is bypassable by the submitter; no separation of duties | **Confirmed statically (Phase 2).** `bypassed = is_admin_user(user) or citizenship_wait_exempt(app_row)` (`:9052`) skips **both** gates; the `purpose` that triggers the `Citizenship` exemption is supplied by the submitter. The approve route never compares approver to `created_by`. **There is also no reject path at all.** Remains blocked on decisions **D-06**, **D-12** and the new **D-19** |
| **M-11** | Migrations are unversioned boot-time side effects | **Still present (re-confirmed Phase 2).** Base DDL + `ADDED_COLUMNS` run at startup; no `schema_migrations` table anywhere. **This gates every schema change in the plan** (WP-16) | 
| **M-12** | No backup, restore, retention, monitoring or DB-aware health check | **Still present.** No such artefacts in the repository |
| **M-10** | Stale SQLite-era artefacts and missing dependency manifests | **Still present (re-confirmed Phase 2).** `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`, `backend/test_server.py`, `backend/test_conduct_frontend.mjs`; no `requirements.txt` / `package.json`. **This is the direct cause of 23 of 25 suites being unrunnable**, and therefore of the project's inability to verify any fix |
| **M-8** | Database access is superuser, unencrypted, unpooled | **Partially confirmed.** `.env.example` defaults to `SENTINEL_DB_USER=postgres`; no `sslmode`, no pooling configuration |

### 6.3b Security findings **new in this assessment** (not in the PR #23 audit)

| ID | Finding | Severity | Status at `a1c2478` |
|---|---|---|---|
| **N-1** | `GET /api/suspect-alerts` (`:8425`) applies **no scoping of any kind** — every CID and checkpoint officer nationwide reads every suspect, victim, witness and complainant listing. `suspect_alerts` **has no `branch_id` column**, so this cannot be fixed without DDL | **HIGH** | **Confirmed [STATIC]** |
| **N-2** | Three Crime Unit write paths bypass branch isolation: `PATCH /api/crime-cases/<id>` (`:9581`, which also accepts **free-text** status), `POST .../evidence` (`:9092`), `POST /api/suspect-alerts` (`:9172`) | **HIGH** | **Confirmed [STATIC]** |
| **N-3** | `cid_crime_analytics(c)` (`:6132`) and `cid_fingerprint_analytics(c)` (`:6071`) take **no `user`**, so branch-scoped officers receive **national** aggregates; only `cid_checkpoint_analytics(c, user)` (`:6176`) is scoped | MEDIUM | **Confirmed [STATIC]** |
| **N-4** | `Access-Control-Allow-Origin: *` on every JSON response (`:7773`) | LOW | **Confirmed [STATIC]** |
| **N-5** | No CSP, `X-Frame-Options`, `X-Content-Type-Options` or HSTS anywhere | LOW | **Confirmed [STATIC]** |
| **N-6** | Documents stored as JSON blobs in TEXT columns (`applicant_docs`, `guardian_docs`, `traveler_docs`) — no per-document authorization, retention or integrity hash. This is the structural reason C-1 is hard to fix well | LOW *(structural)* | **Confirmed [STATIC]** |

### 6.4 Known non-security defects

| Item | Status |
|---|---|
| `backend/test_server.py` — SQLite-era harness targeting retired storage | **Obsolete; expected to fail.** Must not be run on a machine with database credentials in the environment |
| `backend/test_conduct_frontend.mjs` — spawns the server with the retired `SENTINEL_DB` setting | **Obsolete; expected to fail** |
| Full defect inventory for the three CID units | **Produced 2026-11-06.** Fingerprint FG-01…FG-21 · Checkpoint G-01…G-17 · Crime X-1…X-6 plus the gap tables in the requirements proposal. See the `assessment/` deliverables |
| `case_id` hard-codes the year `2026` (`:9083`) — cases created in 2027 will be mislabelled | **Confirmed [STATIC]** (finding H-6) |
| Four competing case-status vocabularies with no state machine | **Confirmed [STATIC]** — blocked on decision **D-25** |
| Three columns encode one checkpoint location fact, requiring a six-way `OR`/`ILIKE` match beneath a security control | **Confirmed [STATIC]** (gap G-14) |

### 6.5 Deliberate counter-record (accuracy)

Branch isolation is **not** uniformly fail-open. `require_record_branch_scope()` treats a record with a
`NULL` branch as **out of scope** for a scoped officer — *"unknown must never mean everything"*
(`backend/server.py:2790-2805`). The fail-open behaviour (H-2b) is in **officer scope resolution**.
Remediation must target that path specifically and must not regress the correct per-record behaviour.

---

## 7. Test results

### 7.1 Executed (2026-11-06, commit `a1c2478`) — re-run in the Phase 2 session

| Check | Result |
|---|---|
| `python3 backend/server.py --ui-check` | **PASS** — exit 0; build `sentinel-branch-crud-1-e7c41b90`; serving `/home/user/sentinel-police-management/index.html`; checkout `arena/6303ef2f-sentinel-police-management @ a1c2478`; `Actions column: yes` |
| `python3 backend/test_print_fit.py` | **PASS** — `ALL PRINT TEMPLATE TESTS PASSED` (A4 print contract, blueprint fidelity, emblem placement, DOM bindings, single-page height budgets) |

### 7.2 Not executed

**23 of the 25 test files were not run** (24 counting `test_print_fit.py` as the sole executed suite;
`--ui-check` is not a suite). Reason: they require `psycopg2-binary`, `pgserver` and/or `jsdom@26`,
none of which are installed, and **installing dependencies was explicitly out of scope for both the
documentation task and the assessment**. Per `PROJECT_CONTEXT.md` §14.2.4, these are reported as
**not run**, never as passing.

**Consequence, stated plainly:** the project currently **cannot demonstrate that any feature works**,
beyond the A4 print contract and the served-UI identity check. This is the direct effect of finding
**M-10** (no dependency manifests), and it is why `assessment/DEPENDENCIES_AND_ESTIMATES.md` makes
**WP-01 — a runnable test environment — the first item of any sprint**.

### 7.2b Test-coverage map produced by Phase 2 *(by keyword analysis across all 25 files)*

| Unit | Coverage | Notes |
|---|---|---|
| **Fingerprint** | Well covered **on paper** | `test_review_gate.py` (37 refs), `test_branch_scope.py` (28), `test_clearance_rbac_ui.mjs` (26), `test_approval_flow.mjs` (20), `test_field_level_rbac.py` (8), `test_print_fit.py` |
| **Checkpoint** | Well covered **on paper** | `test_sidebar_navigation.mjs` (86), `test_checkpoint_roles_audit.py` (76), `test_frontend_session.mjs` (57), `test_officer_profile_locations.py` (34), branch-management suites (29/26) |
| **Crime** | **No dedicated suite exists** | Incidental references only (9/7/5/3/3); the 40 hits in `test_server.py` are in an **obsolete** SQLite-era harness |

**Proven coverage gaps (verified by inspection, not inferred):**

| Gap | Evidence |
|---|---|
| Nothing tests branch scoping on `/approve` or `/signed-document` | `grep -c "approve\|signed-document" backend/test_branch_scope.py` → **0** |
| No suite fetches `/uploads/<file>` anonymously | searched all 25 files → **0** |
| No suite asserts a `checkpoint_officer` with a **blank** `location_scope` is denied | searched all 25 files → **0** — the suites are silent exactly where the control fails |
| No suspect-alert isolation test, no self-approval test, no upload-validation test, no concurrency test | searched all 25 files → **0** |
| The navigation suites assert what the **UI hides**, which cannot prove what the **server refuses** | suite design |

### 7.3 Test inventory at `a1c2478` (verified by file listing)

| Category | Count | Files |
|---|---|---|
| Python suites | **12** | `test_branch_management_crud.py`, `test_branch_scope.py`, `test_checkpoint_roles_audit.py`, `test_dynamic_branches.py`, `test_field_level_rbac.py`, `test_linked_records.py`, `test_officer_profile_locations.py`, `test_print_fit.py`, `test_read_only_rbac.py`, `test_review_gate.py`, `test_server.py` *(obsolete)*, `test_station_actions.py` |
| Node/jsdom suites | **13** | `test_approval_flow.mjs`, `test_branch_management_ui.mjs`, `test_clearance_rbac_ui.mjs`, `test_conduct_frontend.mjs` *(obsolete)*, `test_form_improvements.mjs`, `test_frontend_session.mjs`, `test_officer_profile_ui.mjs`, `test_record_audit_ui.mjs`, `test_reverse_sequence_ui.mjs`, `test_shell_workflow_integration.mjs`, `test_sidebar_navigation.mjs`, `test_station_frontend.mjs`, `test_station_integration.mjs` |
| **Total test files** | **25** | — |
| Current (non-obsolete) suites | **23** | Total minus `test_server.py` and `test_conduct_frontend.mjs` |

### 7.4 Verification of the earlier audit's test claim

The assignment asked whether the audit's report of **"23 test suites, 21 passing, 2 failing legacy
SQLite-era harnesses"** remains accurate.

| Aspect | Finding |
|---|---|
| **Suite count** | **No longer accurate.** The audit measured `381545c` (11 Python + 12 Node = 23 files). Commit `a1c2478` added two suites — `backend/test_branch_management_crud.py` and `backend/test_branch_management_ui.mjs` — bringing the tree to **25 test files (12 Python + 13 Node)**. **[VERIFIED]** by file listing and `git diff --stat 381545c a1c2478`. |
| **The two failing harnesses** | **Still present and still obsolete** — `backend/test_server.py` (SQLite-era) and `backend/test_conduct_frontend.mjs` (spawns the server with the retired `SENTINEL_DB` setting). **[VERIFIED]** by file presence and import inspection (`sqlite3` in `test_server.py`). |
| **The 21-passing figure** | **Not re-verified.** Cannot be confirmed or refuted without installing dependencies. Treat the audit's pass/fail table as applying to `381545c` only. |
| **Net statement** | The audit's test section is **stale in count** and **unverified in outcome** at the current baseline. A fresh full test run against `a1c2478` is required and is listed as pending work. |

---

## 8. Deployment readiness

| Stage | Readiness at the documentation baseline |
|---|---|
| **Continued development** | **Proceed** — with synthetic data only, and no implementation work until the owner approves the assessment and schedule |
| **Dedicated staging (synthetic data)** | **Not ready.** No environment separation, no dependency manifests, no deployment configuration, no TLS configuration exist in the repository |
| **Controlled pilot with real police data** | **NOT READY.** Blocked by 3 CRITICAL (C-1, C-2, C-3) and 10 HIGH findings — including **M-2** (checkpoint scope fail-open on the canonical role, read **and** write) and **N-1** (nationwide unscoped suspect-alert read), both confirmed at code level |
| **Production** | **NOT READY.** Additionally blocked by unversioned migrations (**M-11**), absent backup/restore/rollback procedures and monitoring (**M-12**), absent transport security in the repository (**H-8**), and the inability to run 23 of 25 test suites (**M-10**) |
| **Zero-downtime upgrades** | **Must not be promised.** Re-confirmed by Phase 2: single-process `ThreadingHTTPServer`, DDL executed at application startup, no migration versioning, no rollback path, no deployment artefact in the repository. **No downtime claim can be made until WP-16 and WP-20 are complete and rehearsed (WP-44).** The first production deployment may require a planned maintenance window |

**No deployment of any kind has been performed, and no environment was modified, in this session.**

---

## 9. Current task

**Task (Phase 3):** Produce a complete, realistic and technically consistent **requirements and
architecture package** for CID Release 1.0 — Fingerprint, Crime and Checkpoint units plus the shared
CID capabilities — covering deliverables A–H of the Phase 3 brief and a revised implementation plan
with estimates.

**Status:** **Complete** as of 2026-11-06. Ten documents delivered (§14), plus updates to this file
and `CHANGELOG.md`.

**Owner decisions closed in the Phase 3 brief:** **D-18 = BOTH** (clearance *and* genuine biometric
capture and matching — this **overrode** the Phase 2 recommendation of clearance-only and moved
WP-45 into Release 1.0 scope); **D-14 = use the proposed report catalogue as the starting point**;
**D-16 = Airport Unit excluded from Release 1.0 → Release 1.1**.

**Constraints honoured:** no application source code, database schema, migration, configuration or
dependency was changed; nothing was deployed and no production system was contacted; no branch was
merged and no release was opened; **PR #23 and branch `arena/8834f56d-…` were not touched**; no
existing documentation was deleted — Phase 2 documents are **superseded in place**, not removed; no
progress percentage was invented; no test was claimed to pass that was not executed; and no legal or
operational policy was decided on the owner's behalf.

**Phases 1 and 2 remain complete** as of the same date.

---

## 10. Next approved task

**Next task:** **None is approved.** The project is **stopped, awaiting owner review of the Phase 3
requirements and architecture package**, owner answers to the remaining blocking decisions, and
explicit approval before **any** application change.

**Decision load:** **41 decisions are open; 24 block Release 1.0.** Three are now **closed**
(D-18, D-14, D-16) and **14 are new** (D-30…D-43), raised by the Phase 3 requirements and
architecture work. The canonical register is **`DECISION_REGISTER.md`** (root), which supersedes
`assessment/DECISION_REGISTER_RECOMMENDATIONS.md`.

**Immediate sign-off requested — analysis complete, only a decision is needed:**

| ID | Question | Recommendation |
|---|---|---|
| **D-15** | `crime_cases` ↔ `crime_incidents` | **Option A** — keep both, link explicitly via a `case_incidents` join table, one case to many incidents. **Do not merge** |
| **D-14a** | Which of the 24 catalogued reports are in Release 1.0? | Tier 1 now; Tier 2 with prerequisites; Tier 3 after the subsystem lands |
| **D-25** | Case status vocabulary | `CASE_STATUSES` (7) for cases + transition table; keep `CRIME_STATUSES` for incidents |
| **D-03** | Password hashing | stdlib PBKDF2-HMAC-SHA256, ≥600,000 iterations — no new dependency |
| **D-08** | Session policy | Split from RPO/RTO; decide the session half now |
| **D-20** | Checkpoint catalogue | Data-driven from `police_branches`, **in the same change as** the fail-closed fix |
| **D-13** | Out-of-scope module visibility | Hide via `ROLE_MODULES` **and** verify the API gate by test |

**Then, with the longest lead times, start immediately and in parallel:** the **biometric
procurement track** (**D-31** scanner, **D-32** bridge-service ownership, **D-33** matching engine
and template format, **D-35** fingers captured) and the **legal track** (**D-04**, **D-05**,
**D-23**, **D-24**, **D-27**). Neither is engineering work, and **neither can be shortened by adding
developers.**

### 10.1 Verdict on the proposed 10-day sprint *(revised after D-18)*

> **Unchanged in conclusion, worse in magnitude.** The assessed remaining work is now
> **≈ 257–506 engineering days** (was ≈144–292), because D-18 brought the biometric programme into
> scope — **+58–114 days**, excluding hardware procurement, the bridge service if built in-house
> (+15–30) and accuracy measurement (+5–15). The gap is roughly **26–50×** ten days.
>
> **What 10 days can honestly buy** (3 developers ≈ 30 engineering days): WP-01 test environment ·
> **WP-45g — remove the code that fabricates biometric matches** · WP-03 default credentials ·
> WP-04 password hashing · WP-09 upload validation · and a start on WP-05 authenticated document
> access and WP-06 fail-closed branch scope. **≈ 17–34 engineering days.** This closes two of three
> Critical findings, removes an active safety defect, and makes the rest of the programme
> verifiable. **It is Security Wave 1 plus test enablement — it is not Release 1.0 and must not be
> described as such.**
>
> **No production date is committed.** Full reasoning: `planning/IMPLEMENTATION_ROADMAP.md` §11.

---

## 11. Schedule note (recorded, not committed)

The owner has **proposed** an initial **10-calendar-day delivery sprint beginning 2026-11-06**, with
approximately two hours of owner review and coordination per day, and **2026-11-15 as an initial
review checkpoint — not an unconditional production launch deadline**.

**[Recorded as a proposal only.]** The agent has not adopted, finalised or scheduled against these
dates. The implementation order and schedule are established **after** the repository assessment and
**only** with owner approval. All planned CID Release 1.0 features must be completed and verified even
if the date moves. Security, testing and data integrity are never sacrificed for a date.

**Phase 2 addendum (2026-11-06).** The assessment has now answered the question the proposal implies.
**Ten days is not a Release 1.0 window** — see §10.1 and `assessment/DEPENDENCIES_AND_ESTIMATES.md`
§7. It *is* a realistic window for **Security Wave 1 plus test enablement**, which is a worthwhile
and high-leverage sprint. The 2026-11-15 checkpoint therefore remains useful as a **review point**,
and is still **not** a production launch deadline. **No date has been adopted or committed.**

**Phase 3 addendum (2026-11-06).** Owner decision **D-18 = BOTH** increased Release 1.0 scope. The
revised estimate is **≈ 257–506 engineering days**, and the project's true critical path now runs
through **procurement** (scanner, SDK, bridge service, matching engine) and **legal** (retention,
DPIA, detention framework) — **not** through code. Engineering time and owner review/approval time
are estimated **separately** in `planning/IMPLEMENTATION_ROADMAP.md` §6 and §7. **No 10-day
production release is promised, and no date has been adopted or committed.**

---

## 12. Phase 2 assessment deliverables

| # | Deliverable | File |
|---|---|---|
| 1 | CID Release 1.0 technical and functional assessment — all three units, ten required items each, with the five-value classification and the re-verification of the audit's eight headline concerns | `assessment/CID_TECHNICAL_ASSESSMENT.md` |
| 2 | Fingerprint Unit gap analysis — 15 existing capabilities (F-01…F-15), 21 gaps (FG-01…FG-21), test-gap table, close-out order | `assessment/FINGERPRINT_UNIT_GAP_ANALYSIS.md` |
| 3 | Crime Unit requirements **proposal** — all ten required areas, the `crime_cases` ↔ `crime_incidents` analysis with three costed options, and an 18-item advanced-report menu. **PROPOSED, NOT APPROVED** | `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` |
| 4 | Checkpoint Unit gap analysis — 17 existing capabilities (CP-01…CP-17), 17 gaps (G-01…G-17) | `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md` |
| 5 | Security remediation priority list — 24 findings with severity, file+endpoint, evidence, impact, remediation and a required verification test; static separated from runtime-historical | `assessment/SECURITY_REMEDIATION_PRIORITY.md` |
| 6 | Decision register recommendations — 30 open decisions grouped into blocking / can wait / legal-operational / recommended option with risks | `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` |
| 7 | Dependencies and realistic implementation estimates — effort bands in **engineering days**, dependency graph, three chokepoints, two critical chains | `assessment/DEPENDENCIES_AND_ESTIMATES.md` §1–§4, §6 |
| 8 | Proposed development order, and the 10-day sprint verdict | `assessment/DEPENDENCIES_AND_ESTIMATES.md` §5 and §7 |

---

## 13. Status-document conventions

- **"Not yet verified"** — the item has not been assessed at this baseline. It is not a progress claim.
- **"Still present at code level"** — confirmed by reading the code at `a1c2478`; a runtime
  reproduction has not been performed in this session.
- **"Not re-verified"** — a historical finding that this session could not check without running the
  application.
- **Percentages** are recorded only when measured, with the measurement method stated. Owner-reported
  or prior-session figures are quoted and labelled as such. **The Phase 2 assessment produced no
  percentage of any kind**; effort is expressed only in engineering-day ranges.
- **Evidence classes used by the Phase 2 deliverables:** **[STATIC]** (confirmed by reading the code
  at `a1c2478` on 2026-11-06) · **[RUNTIME-2026-11-06]** (actually executed this session — only
  `--ui-check` and `test_print_fit.py`) · **[RUNTIME-HISTORICAL]** (reported by the PR #23 audit at
  `381545c`; prior evidence, **not** re-reproduced) · **[NOT VERIFIED]**.
- **Five-value feature classification:** *Implemented and verified* · *Implemented but not verified* ·
  *Partially implemented* · *Not implemented* · *Blocked*. "Verified" requires an executed check, and
  only **one** feature area currently qualifies.
- **Security identifiers:** `C-n`/`H-n`/`M-n` are inherited from the PR #23 audit and are **never
  reassigned**; `N-n` marks findings new to this assessment. Where this assessment re-rates a carried
  finding's severity, the identifier is kept and the change is stated.
- **Requirement identifiers (Phase 3):** `FPR-` Fingerprint · `CRR-` Crime · `CKR-` Checkpoint ·
  `ARCH-` architecture · `SR-` security · `RPT-` reporting · `AC-` acceptance criteria. They are
  distinct from capability IDs (`CP-`), gap IDs (`FG-`, `G-`) and security finding IDs.
- **Decision identifiers are never reused or renumbered.** D-01…D-29 keep the meanings recorded in
  `PROJECT_CONTEXT.md` Appendix A and the Phase 2 register; Phase 3 extends the sequence from D-30.
  Closed decisions are retained with their answer and consequences, and an **overridden agent
  recommendation is recorded as overridden** (see D-18), never quietly dropped.
- **A recommendation is a proposal, not a decision.** Where no recommendation is offered, the
  question is legal, operational or a command matter: engineering can implement any answer but must
  not choose it.

---

## 14. Phase 3 requirements and architecture deliverables

All created 2026-11-06 on `arena/6303ef2f-sentinel-police-management`. **Documentation only — no
application file was touched.**

| Brief item | Document | Contents |
|---|---|---|
| **A** | `requirements/FINGERPRINT_UNIT_REQUIREMENTS.md` | Scope per **D-18 = BOTH**. Separates image acquisition · template generation · 1:1 verification · 1:N identification · thresholds and human review · false match and failed capture · device integration and fallback. States what is **retained** (bridge protocol, server identity engine, clearance workflow, review gate), **redesigned** (storage, matching, status model, identifiers) and **external** (scanner, SDK, bridge service, matching engine). Adds FPR-901/902 — removal of browser-stored biometrics and of the rotating-cursor fallback that fabricates identifications |
| **B** | `requirements/CRIME_UNIT_REQUIREMENTS.md` | Per workflow: actors and permissions, preconditions, steps, required data, status transitions, exceptions and rejection paths, audit events, acceptance criteria. **Supersedes** `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` (retained) |
| **B** | `requirements/CRIME_REPORT_CATALOGUE.md` | **D-14** catalogue reviewed and completed: 18 reviewed + 6 added = **24 reports**. Per report: purpose, sources, filters, grouping, output fields, permissions and **whether it is generatable from the planned model** (8 buildable from existing columns, 16 gated on other work). Plus reporting safeguards and the final selection for sign-off |
| **C** | `architecture/CRIME_DATA_MODEL_DECISION.md` | Four options analysed. **Recommends Option A** — separate, explicitly linked, one case to many incidents. Covers operational meaning, relationships, identifiers, history and migration implications, and the defects to fix irrespective of the choice |
| **D** | `requirements/CHECKPOINT_UNIT_REQUIREMENTS.md` | Five corrections with testable acceptance criteria: blank-scope canonical role · cross-location read/write · operations and incident recording · detention / referral / false-match workflows · legacy↔canonical consistency |
| **E** | `architecture/SYSTEM_ARCHITECTURE.md` | Current and target architecture, role-permission matrix, branch/location authorization model, document and attachment access model, audit requirements, API boundaries, biometric hardware/software boundary, and how the three units share data without over-granting |
| **F** | `requirements/SECURITY_REQUIREMENTS.md` | All 24 findings converted to **36 requirements** (SR-01…SR-31, SR-90…SR-94) with severity, correction, executing verification method and release-blocking flag. **27 are release-blocking** |
| **G** | `DECISION_REGISTER.md` *(root, canonical)* | **Supersedes** `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` (retained). 3 closed · 41 open · 24 blocking · 14 new (D-30…D-43), with recommendations, evidence, cost of delay and 5 named blockers |
| **H** | `requirements/RELEASE_ACCEPTANCE_CRITERIA.md` | Measurable gates across functional completeness, role/branch isolation, biometric correctness and safety, data protection, testing, backup/recovery, deployment readiness and operational documentation. **Exactly 2 of 115 criteria are met today** (AC-T4 and AC-T10), both by executed checks |
| **§4** | `planning/IMPLEMENTATION_ROADMAP.md` | Revised work packages with dependencies, deliverables, estimates and risks. **≈ 257–506 engineering days.** Engineering time is separated from owner review/approval time and from procurement/legal lead time. No production date committed |

**Superseded but retained** (nothing was deleted): `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md`
→ deliverable B · `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` → deliverable G ·
`assessment/DEPENDENCIES_AND_ESTIMATES.md` → the roadmap.

---
