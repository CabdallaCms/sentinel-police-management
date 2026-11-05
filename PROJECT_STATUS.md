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
| **Current project phase** | **Documentation baseline established — awaiting owner-approved repository assessment and delivery plan.** No implementation work is authorised. |
| **Current Git branch** | `arena/6303ef2f-sentinel-police-management` |
| **Current commit hash** | `a1c2478262776e9f20b4c3ad806eaa86adc27792` (`a1c2478`) |
| **Commit date / subject** | 2026-10-27 17:13:20 +0000 — *"Branch Management: full CRUD (edit/deactivate) + legacy placement cleanup"* |
| **Last verified commit** | `a1c2478262776e9f20b4c3ad806eaa86adc27792` — verified 2026-11-06 by repository inspection; identical to `origin/main` at that time; working tree clean before documentation files were added |
| **Build identity (verified)** | `sentinel-branch-crud-1-e7c41b90` (`python3 backend/server.py --ui-check` → exit 0) |
| **Last update date** | **2026-11-06** (documentation baseline; session executed 2026-11-05 UTC) |

---

## 2. Unit status

> Scope definitions are in `PROJECT_CONTEXT.md` §3–§5 and `RELEASE_PLAN.md`. This section reports
> **state**, not scope.

### 2.1 Fingerprint Unit — Release 1.0 · Unit A

| Field | Value |
|---|---|
| **Overall status** | **Not yet verified.** Substantial implementation exists and is evidenced below; completeness against Release 1.0 requirements has **not** been assessed. |
| **Owner-reported progress** | "approximately 80%" — **Not yet verified.** This figure is recorded as an owner report only. It is **not** adopted as a project fact and must not be cited as measured progress. |
| **Evidence that implementation exists (verified at `a1c2478`)** | `clearance_applications` + `clearance_signed_documents` tables (`backend/server.py:265`, `:281`); endpoints `/api/clearance-applications` (incl. `/approve`, `/signed-document`, `/documents`) and `/api/fingerprint/applications`; role `FingerprintUnit` with modules `{dashboard, people, fingerprint}`; 12-hour review gate armed by a boot-time self-test (`review_lock_armed()`, `backend/server.py:1057`, enforced `:10022`); printable `application.html` and `certificate.html` pinned by `backend/test_print_fit.py` (**executed 2026-11-06 → PASS**) |
| **Not assessed** | Requirements coverage · completeness of the clearance workflow against owner requirements · biometric/fingerprint capture and matching maturity · report requirements · outstanding defect list |
| **Known open concerns carried in** | Cross-branch approve / signed-scan writes; unauthenticated upload retrieval; submitter self-approval; `Citizenship` review-gate exemption (see §6) |
| **Next step** | Repository assessment of actual implementation status and outstanding work — **requires owner approval to start** |

### 2.2 Crime Unit — Release 1.0 · Unit B

| Field | Value |
|---|---|
| **Overall status** | **Not yet verified.** Core data model and case workspace exist; the Release 1.0 requirement set (full operations **including advanced reports**) is **undefined and unassessed**. |
| **Evidence that implementation exists (verified at `a1c2478`)** | `crime_cases` (`backend/server.py:292`), `crime_incidents` (`:374`), `suspect_alerts` (`:299`), `case_evidence` (`:309`); endpoints `/api/crime-cases`, `/api/crimes`, `/api/suspect-alerts`, `/api/cid/analytics`; role `CIDUnit` with modules `{dashboard, people, cid, crimes}`; three-tab CID case workspace (Case Details · Participants & Suspect Linkage · Evidence & Media) documented in `README.md`; branch-scoped crime writes via `require_branch_write_scope(..., 'crime')` (`:9081`) and branch-scoped single-case reads via `require_record_branch_scope(..., 'crime', ...)` (`:8283`) |
| **Advanced reports** | **Not defined.** `/api/cid/analytics` exists, but no requirement specification for "advanced reports" exists in the repository. Blocked on **decision D-14**. |
| **Not assessed** | Requirements · workflows · user roles and permissions for Crime Unit operations · report definitions · case lifecycle/status model · evidence chain-of-custody requirements · integration points · outstanding defect list |
| **Open modelling question** | Relationship between `crime_cases` (CID case) and `crime_incidents` (station incident file) is undocumented — **decision D-15** |
| **Scope guard** | **Must not** be reduced to basic case registration to meet a date (`PROJECT_CONTEXT.md` §3.2, §15.5) |
| **Next step** | Document requirements, workflows, roles, permissions and reports **before** implementation — **requires owner approval** |

### 2.3 Checkpoint Unit — Release 1.0 · Unit C

| Field | Value |
|---|---|
| **Overall status** | **Not yet verified.** The owner reports it as already implemented; that report is **unverified**. |
| **Owner-reported status** | "already implemented" — **Not yet verified.** |
| **Evidence that implementation exists (verified at `a1c2478`)** | `checkpoint_events` table (`backend/server.py:316`); `/api/checkpoint-events`; unified `checkpoint_officer` role plus legacy `CheckpointSouth`/`East`/`West`, all with modules `{dashboard, checkpoints}` and one shared label (`ROLE_LABELS`, `:1816`); branch-scoped writes via `require_branch_write_scope(..., 'checkpoint')` (`:9219`); location scoping documented in `README.md` (`scope` + `visible_locations` on read, rejection of out-of-location writes); `backend/test_checkpoint_roles_audit.py` exists |
| **Required verification (none performed)** | Workflows · permissions · security · branch and location isolation · integration with the Central Person Registry and suspect alerts · report/print requirements · defect list |
| **Known open concern carried in** | Clearing a checkpoint officer's `location_scope` reportedly widens them to all checkpoints (historical finding M-2) — **not re-verified** |
| **Next step** | Formal verification pass — **requires owner approval to start** |

### 2.4 Airport Unit — POSTPONED to CID Release 1.1

| Field | Value |
|---|---|
| **Release 1.0 status** | **Out of scope. Postponed to CID Release 1.1.** |
| **Code present?** | **Yes — verified.** `airport_passengers` table, `/api/airport-records`, role `AirportControl` `{dashboard, people, airport}`, branch `unit_type='airport'`, airport passenger register page |
| **Action during Release 1.0** | **Frozen.** Do not implement, expand, redesign or add Airport features. Do not delete it either. |
| **Open decision** | **D-16** — is the Airport module enabled or hidden in the Release 1.0 build? |

---

## 3. Completed and verified work

**Completed and verified in this documentation session (2026-11-06):**

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

The current activity is documentation only, and it is complete as of 2026-11-06.

---

## 5. Work not started

| Item | Blocked on |
|---|---|
| Repository assessment of the three CID units (actual implementation status and outstanding work) | Owner approval — this is the agreed next session |
| Crime Unit requirements, workflows, roles, permissions and **advanced report definitions** | Owner approval + **decision D-14** |
| Checkpoint Unit verification pass (workflows, permissions, security, integration) | Owner approval |
| Fingerprint Unit completeness assessment against requirements | Owner approval |
| Detailed implementation schedule and task order | Owner approval **after** the repository assessment |
| Remediation of any security finding | Owner approval; explicitly excluded from this documentation task |
| Versioned database migrations; removal of boot-time migration side effects | Owner approval |
| Dependency manifests (`requirements.txt`, `package.json`), CI configuration | Owner approval |
| Retirement/rewrite of the two obsolete SQLite-era test harnesses | Owner approval |
| Environment separation (Development / Staging / Production) | Owner approval + decisions D-01, D-02, D-07, D-08, D-09 |
| Backup, restore, rollback and monitoring procedures | Owner approval + decisions D-08, D-09 |

---

## 6. Known defects and security blockers

> **Source:** the earlier deployment audit (`DEPLOYMENT_AUDIT.proposed.md`, PR #23, audited revision
> `381545c` — the immediate **parent** of the current baseline commit `a1c2478`).
> **These are historical audit findings, not automatically current defects.** The "Status at `a1c2478`"
> column records only what this documentation session could establish **without running the
> application**, since running the full suite required installing dependencies, which was out of scope.

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
| **H-3** | Sessions never expire; password reset does not revoke existing sessions | **Partially confirmed statically.** `sessions(token, user_id, created_at)` has **no expiry column**; the only `Max-Age` in the codebase is `Max-Age=0` on logout. Reset-revocation behaviour **not re-verified** (needs a running system) | Static: `backend/server.py:446`, `:8688` |
| **H-5** | Administrator self-demotion causing permanent lockout | **Not re-verified** — requires a running system | — |
| **H-4** | No login throttling/lockout; authentication events not audited | **Not re-verified**; `audit_events` schema contains no authentication-specific structure | Static: `backend/server.py:450` |
| **H-6** | Registration/identifier generation races producing spurious `409`s | **Not re-verified** — requires concurrent runtime testing | — |
| **H-7** | Incomplete and mutable audit trail | **Partially confirmed statically.** `audit_events` has no immutability mechanism, no IP/user-agent/session id, no before/after values | Static: `backend/server.py:450` |
| **H-8** | No HTTPS; no `Secure` cookie; token duplicated into `localStorage` | **Not re-verified at runtime.** No TLS or reverse-proxy configuration exists in the repository | Static: `git ls-files` |

### 6.3 Security blockers — Medium (selected, carried forward)

| ID | Finding | Status at `a1c2478` |
|---|---|---|
| **M-2** | Clearing a checkpoint officer's `location_scope` widens them to every checkpoint | **Not re-verified** |
| **M-3** | The 12-hour review gate is bypassable by the submitter; no separation of duties | **Not re-verified**; blocked on decisions D-06 and D-12 |
| **M-11** | Migrations are unversioned boot-time side effects | **Still present.** Base DDL + `ADDED_COLUMNS` run at startup; no `schema_migrations` table anywhere | 
| **M-12** | No backup, restore, retention, monitoring or DB-aware health check | **Still present.** No such artefacts in the repository |
| **M-10** | Stale SQLite-era artefacts and missing dependency manifests | **Still present.** `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`, `backend/test_server.py`, `backend/test_conduct_frontend.mjs`; no `requirements.txt` / `package.json` |
| **M-8** | Database access is superuser, unencrypted, unpooled | **Partially confirmed.** `.env.example` defaults to `SENTINEL_DB_USER=postgres`; no `sslmode`, no pooling configuration |

### 6.4 Known non-security defects

| Item | Status |
|---|---|
| `backend/test_server.py` — SQLite-era harness targeting retired storage | **Obsolete; expected to fail.** Must not be run on a machine with database credentials in the environment |
| `backend/test_conduct_frontend.mjs` — spawns the server with the retired `SENTINEL_DB` setting | **Obsolete; expected to fail** |
| Full defect inventory for the three CID units | **Not yet verified** — produced by the pending repository assessment |

### 6.5 Deliberate counter-record (accuracy)

Branch isolation is **not** uniformly fail-open. `require_record_branch_scope()` treats a record with a
`NULL` branch as **out of scope** for a scoped officer — *"unknown must never mean everything"*
(`backend/server.py:2790-2805`). The fail-open behaviour (H-2b) is in **officer scope resolution**.
Remediation must target that path specifically and must not regress the correct per-record behaviour.

---

## 7. Test results

### 7.1 Executed in this session (2026-11-06, commit `a1c2478`)

| Check | Result |
|---|---|
| `python3 backend/server.py --ui-check` | **PASS** — exit 0; build `sentinel-branch-crud-1-e7c41b90`; serving `/home/user/sentinel-police-management/index.html`; checkout `arena/6303ef2f-sentinel-police-management @ a1c2478`; `Actions column: yes` |
| `python3 backend/test_print_fit.py` | **PASS** — `ALL PRINT TEMPLATE TESTS PASSED` (A4 print contract, blueprint fidelity, emblem placement, DOM bindings, single-page height budgets) |

### 7.2 Not executed in this session

**24 of the 25 test files were not run.** Reason: they require `psycopg2`, `pgserver` and/or `jsdom`,
none of which are installed in this environment, and **installing dependencies was explicitly out of
scope for this documentation task**. Per `PROJECT_CONTEXT.md` §14.2.4, these are reported as
**not run**, not as passing.

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
| **Controlled pilot with real police data** | **NOT READY.** Blocked by the unresolved Critical findings C-1, C-2, C-3 and High findings H-2a/H-2b (all confirmed present at code level) |
| **Production** | **NOT READY.** Additionally blocked by unversioned migrations, absent backup/restore/rollback procedures, and absent monitoring |
| **Zero-downtime upgrades** | **Must not be promised.** Schema migrations are unversioned boot-time side effects (`PROJECT_CONTEXT.md` §2.6, §11.1). The first production deployment may require a planned maintenance window |

**No deployment of any kind has been performed, and no environment was modified, in this session.**

---

## 9. Current task

**Task:** Establish the permanent project documentation baseline for CID Release 1.0 — create
`PROJECT_CONTEXT.md`, `PROJECT_STATUS.md`, `RELEASE_PLAN.md` and `CHANGELOG.md`; record the verified
repository state; and record the status of the earlier security audit.

**Status:** **Complete** as of 2026-11-06.

**Constraints honoured:** no application code, database schema, configuration, dependency or
deployment artefact was changed; no feature was implemented; no defect was fixed; no branch was merged;
no existing documentation was deleted or overwritten.

---

## 10. Next approved task

**Next task:** A **repository assessment** of CID Release 1.0 — establishing the actual implementation
status and the outstanding work for the Fingerprint, Crime and Checkpoint units — followed by a
delivery-planning session.

**Approval state:** **Awaiting project owner approval.** The agent must not begin it, or any
implementation work, until the owner approves.

**Owner inputs needed before or during that session:** the decisions registered in
`PROJECT_CONTEXT.md` Appendix A, most urgently **D-14** (definition of Crime Unit advanced reports),
**D-15** (`crime_cases` vs `crime_incidents`), **D-12/D-06** (separation of duties and the
`Citizenship` exemption), **D-13/D-16** (visibility of out-of-scope modules, including Airport), and
**D-17** (status of the PR #23 audit).

---

## 11. Schedule note (recorded, not committed)

The owner has **proposed** an initial **10-calendar-day delivery sprint beginning 2026-11-06**, with
approximately two hours of owner review and coordination per day, and **2026-11-15 as an initial
review checkpoint — not an unconditional production launch deadline**.

**[Recorded as a proposal only.]** The agent has not adopted, finalised or scheduled against these
dates. The implementation order and schedule are established **after** the repository assessment and
**only** with owner approval. All planned CID Release 1.0 features must be completed and verified even
if the date moves. Security, testing and data integrity are never sacrificed for a date.

---

## 12. Status-document conventions

- **"Not yet verified"** — the item has not been assessed at this baseline. It is not a progress claim.
- **"Still present at code level"** — confirmed by reading the code at `a1c2478`; a runtime
  reproduction has not been performed in this session.
- **"Not re-verified"** — a historical finding that this session could not check without running the
  application.
- **Percentages** are recorded only when measured, with the measurement method stated. Owner-reported
  or prior-session figures are quoted and labelled as such.
