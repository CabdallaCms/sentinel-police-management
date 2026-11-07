# CHANGELOG — Sentinel Police Management System

Structured history of significant changes to this repository.

**Rules for this file** (binding — see `PROJECT_CONTEXT.md` §14.3):

- Every significant change gets an entry, newest first.
- **No invented history.** This changelog begins at the documentation baseline of 2026-11-06. Work
  that predates it is visible in Git history and in the pull-request record; it is **not**
  retroactively reconstructed here.
- Entries are **appended**, never rewritten. A mistake is corrected by a new entry that states the
  correction.
- Never claim a test passed without having run it. A suite that was not run is recorded as
  **not run**.
- Never record a credential, token or real police record in this file.

**Entry format** — every entry uses these fields:

```
## YYYY-MM-DD — <Version or release> — <Short title>

- Change description:
- Affected modules:
- Database migrations:
- Tests performed:
- Commit reference:
```

---

## 2026-11-07 — Stage 0 security implementation (authorised scope only)

**First code change to the application since the documentation and assessment phases.** Five
work packages, exactly matching the five items the owner authorised. Nothing else was touched.

### WP-01 — reproducible test environment
- Added `requirements.txt`, `requirements-dev.txt`, `package.json` (pinned: psycopg2-binary 2.9.10,
  pgserver 0.1.4, jsdom 26.1.0) and `scripts/run-tests.sh`. Closes the manifest half of finding M-10.
- Repaired the bootstraps of `test_server.py` and `test_conduct_frontend.mjs`, which still used the
  retired `SENTINEL_DB=<sqlite file>` convention. Added `backend/pg_test_env.py` so Node harnesses
  can provision an isolated PostgreSQL database. **No assertion was weakened**; three stale
  checkpoint-role expectations and two station-analytics fixtures were corrected to match the real
  (stricter) server, and one expectation was *tightened* from 200 to 401.
- **Measured result: 23 PASS / 2 FAIL before → 27 PASS / 0 FAIL / 1 BLOCKED after** (28 suites).

### WP-45g — removal of fabricated biometric matching (SR-22, finding FPR-902)
- Deleted the `allowFallbackScan` branch of `matchPersonByFingerprint()`, which returned an
  **arbitrary person** by rotating `window._bioScanCursor` through the registry when no comparison
  matched — and whose result was announced as "Biometric Fingerprint Match Found".
- Measured before/after: the same unknown print previously identified **three different citizens in
  rotation**; it now returns no match, every time.
- The two silent "simulate scan" paths now report the negative result instead of doing nothing.
- The `localStorage` biometric store (WP-45a) was **deliberately left unchanged** — out of scope.

### WP-02 — seeded default credentials eliminated (SR-02, finding C-2)
- Removed the hard-coded `ChangeMe123!` from `backend/server.py`, `index.html`, `backend/migrate_rbac.py`,
  `README.md`, `backend/README.md` and `TESTING.md`. Nine accounts — including `admin` and `chief` —
  previously shared it, and the login screen both displayed it and auto-filled it.
- Seeded accounts now take `SENTINEL_BOOTSTRAP_PASSWORD`, or each receives its own random password
  reported once to stderr and to a `0600` file.

### WP-03 — secure password hashing (SR-03, finding C-3; decision D-03)
- Replaced unsalted single-round SHA-256 with **PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte
  per-password salt**, standard library only. Stored in the existing TEXT column — **no schema change**.
- Login no longer matches the password inside a SQL predicate; it verifies in constant time.
- Legacy hashes are accepted once and **transparently upgraded** on next sign-in, so an existing
  database migrates with no DDL and no forced reset.
- **N-8 (new, fixed):** a self-service password change deleted the `sessions` rows but not the
  in-process `TOKENS` cache, so other browsers stayed authenticated. Now properly revoked.

### WP-08 / WP-09 — upload validation and document access control (SR-01/SR-15, findings C-1/M-7)
- `/uploads/` required **no authentication at all**: passport scans, applicant photographs, guardian
  identity documents and case evidence were readable by any anonymous caller. Now 401 without a
  valid session, and served with `nosniff`, a sandbox CSP and `Content-Disposition`.
- `save_upload()` accepted **any extension at any size**. Now an allow-list (images + PDF), a 20 MB
  cap, a magic-number check so content must match its extension, and mode `0640` on disk.
- **Known remaining exposure, disclosed not hidden:** an *authenticated* officer can still read any
  upload, including cross-branch. Per-file authorisation needs the document-ownership schema change
  described in finding N-6 and was **not** made. `test_upload_access_control.py` asserts this
  explicitly so it cannot be forgotten.

### Reported, deliberately NOT fixed (outside the authorised five items)
- **N-7** — `update_discipline()` builds `','.join('%s' * n)`, producing `'%,s,%,s,%,s'`. psycopg2
  raises, the request 400s, and **a suspended officer can never be returned to Active duty**.
  Blocks `test_server.py`. Needs owner authorisation.
- **H-5** — an admin password reset does not end the target's existing sessions. Measured and
  recorded by `test_password_security.py`.
- **Analytics RBAC inconsistency** — `/api/analytics` is not gated purely by `ROLE_MODULES`;
  `cid.officer` receives station and vehicle analytics it has no module for.

### Planning documents (prepared in parallel, as instructed)
- `planning/BIOMETRIC_PROCUREMENT_PLAN.md` — D-31, D-32, D-33, D-35 and the D-34 acceptance evidence.
- `planning/LEGAL_ACTION_PLAN.md` — D-04, D-05, D-23, D-24, D-27.

### Constraints honoured
No schema change, no migration, no deployment, no merge to `main`, no real police records, no
unrelated UI or feature change, and **Stage 1 was not started**.


## 2026-11-06 — CID Release 1.0 (pre-development) — Requirements and architecture package (Phase 3)

**Documentation only. No application source code, database schema, migration, configuration or
dependency was changed. Nothing was deployed, no production system was contacted, no branch was
merged, and no release was opened.**

### Change description

Completed the owner-authorised Phase 3 requirements and architecture package for CID Release 1.0,
against commit `a1c2478`. Added three new directories — `requirements/`, `architecture/`,
`planning/` — containing nine documents, plus the canonical `DECISION_REGISTER.md` at the repository
root.

**Owner decisions recorded as closed in the Phase 3 brief:**

- **D-18 = BOTH.** The Fingerprint Unit must deliver the clearance / identity-review workflow **and**
  genuine biometric capture and matching. This **overrode** the Phase 2 recommendation of a
  clearance-only Release 1.0, and moved work package **WP-45** — previously excluded from the
  estimate as unestimable — into Release 1.0 scope.
- **D-14 = use the proposed report catalogue as the starting point**, reviewed, completed and
  documented for approval.
- **D-16 = Airport Unit excluded from Release 1.0** → Release 1.1.

Deliverables added:

- `requirements/FINGERPRINT_UNIT_REQUIREMENTS.md` — biometric requirements separated into image
  acquisition, template generation, 1:1 verification, 1:N identification, thresholds and human
  review, false match and failed capture, and device integration with fallback. States what is
  retained, what is redesigned, and what requires external hardware or software.
- `requirements/CRIME_UNIT_REQUIREMENTS.md` — supersedes
  `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` (retained, not deleted).
- `requirements/CRIME_REPORT_CATALOGUE.md` — 18 proposed reports reviewed and 6 added (24 total),
  each assessed for whether it is generatable from the planned model.
- `architecture/CRIME_DATA_MODEL_DECISION.md` — four options analysed; recommends keeping
  `crime_cases` and `crime_incidents` separate and explicitly linked (one case to many incidents).
  **The tables were not merged.**
- `requirements/CHECKPOINT_UNIT_REQUIREMENTS.md` — five corrections with testable acceptance criteria.
- `architecture/SYSTEM_ARCHITECTURE.md` — context and components, role-permission matrix,
  branch/location authorization model, document access model, audit requirements, API boundaries,
  biometric hardware/software boundary, and the cross-unit data-sharing rules.
- `requirements/SECURITY_REQUIREMENTS.md` — the 24 findings converted to 34 requirements, each with
  severity, correction, an executing verification method and a release-blocking flag; 27 are
  release-blocking.
- `DECISION_REGISTER.md` (root, canonical) — supersedes
  `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` (retained). 3 closed, 41 open, 24 blocking,
  14 new (D-30…D-43).
- `requirements/RELEASE_ACCEPTANCE_CRITERIA.md` — measurable gates across eight areas.
- `planning/IMPLEMENTATION_ROADMAP.md` — revised estimate of **≈ 257–506 engineering days** (was
  ≈144–292), with engineering time separated from owner review/approval time and from
  procurement/legal lead time.

Updated: `PROJECT_STATUS.md` (§1 identification, §2 caveat, §9 current task, §10 next approved task,
§11 schedule note, new §14 deliverable index, extended §13 conventions) and this file.

### Affected modules

**None.** Documentation only. `git diff --stat a1c2478` against `backend/`, `index.html`,
`application.html`, `certificate.html`, `scripts/` and `images/` is empty.

### Database migrations

**None.** No schema change was made, proposed-as-applied, or executed. Schema changes recommended by
the architecture documents are **proposals requiring owner approval** and are explicitly sequenced
behind a versioned-migration mechanism that does not yet exist (finding M-11).

### Tests performed

- `python3 backend/server.py --ui-check` → **exit 0**, build `sentinel-branch-crud-1-e7c41b90`.
- `python3 backend/test_print_fit.py` → **PASS**.
- **The remaining 23 test suites were NOT RUN.** They require `psycopg2-binary`, `pgserver` and/or
  `jsdom@26`, none of which are installed, and installing dependencies was outside the authorisation
  for this phase. They are recorded as **not run**, never as passing.
- No runtime security testing or penetration testing was performed. All findings referenced in this
  package were established by **static inspection**, which is explicitly **not** proof of runtime
  security.

### Notable correction recorded in this entry

A draft of the Checkpoint requirements cited **D-27**, **D-28** and **D-29** with meanings taken from
working memory rather than from the register. The authoritative register was re-read and the
citations were corrected before commit: **D-27** is the authorised post-flag procedure (detain /
refuse / refer / release / false match), **D-28** is checkpoint vehicle linkage, and **D-29** is
dependency management and supply chain. The genuinely new checkpoint operation/shift question was
assigned the new identifier **D-43**. No existing decision identifier was renumbered.

### Commit reference

Recorded at commit time on branch `arena/6303ef2f-sentinel-police-management`. **PR #23 and branch
`arena/8834f56d-sentinel-police-management` were not modified.**

---

## 2026-11-06 — CID Release 1.0 (pre-development) — Technical and functional assessment (Phase 2)

**Assessment only. No application change. No feature implemented, no defect fixed, no dependency
installed, no branch merged, no deployment performed.**

### Change description

Completed the owner-approved technical and functional assessment of CID Release 1.0 across the three
approved units (Fingerprint, Crime, Checkpoint), at commit `a1c2478`. Added a new `assessment/`
directory containing seven deliverables, and updated `PROJECT_STATUS.md` with the verified results.

Deliverables added:

- `assessment/CID_TECHNICAL_ASSESSMENT.md` — all three units reported against the ten required items
  (existing functionality · actual implementation status · roles and permissions · workflows ·
  database tables and relationships · API endpoints and frontend components · existing tests and
  their results · missing functionality · security weaknesses · integration dependencies), with every
  feature classified as *Implemented and verified* / *Implemented but not verified* / *Partially
  implemented* / *Not implemented* / *Blocked*, and a re-verification of the earlier audit's eight
  headline concerns.
- `assessment/FINGERPRINT_UNIT_GAP_ANALYSIS.md` — 15 existing capabilities, 21 gaps (FG-01…FG-21).
- `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` — **proposed, not approved** requirements across
  the ten required areas, the `crime_cases` ↔ `crime_incidents` investigation with three costed
  options, and an 18-item advanced-report menu with filters, metrics and proposed access permissions.
- `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md` — 17 existing capabilities (CP-01…CP-17), 17 gaps
  (G-01…G-17).
- `assessment/SECURITY_REMEDIATION_PRIORITY.md` — 24 findings (3 CRITICAL, 10 HIGH, 8 MEDIUM, 3 LOW),
  each with severity, affected file and endpoint, evidence, potential impact, recommended remediation
  and a required verification test; static findings separated from runtime-historical ones.
- `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` — 30 open decisions (D-01…D-17 carried forward
  plus **D-18…D-29** newly raised), grouped into decisions blocking Release 1.0, decisions that can
  wait, decisions needing legal or operational confirmation, and recommended technical options with
  their risks.
- `assessment/DEPENDENCIES_AND_ESTIMATES.md` — 47 work packages with effort bands in **engineering
  days**, a dependency graph, three chokepoints, two critical chains, a proposed development order,
  and the verdict on the proposed 10-day sprint.

### Key findings recorded

- **All eight** headline concerns of the PR #23 audit remain present at `a1c2478`; concern #3
  (fail-open scope) is **wider** than reported — the canonical `checkpoint_officer` role has a blank
  location scope that disables filtering on **reads and writes**.
- **Six security findings new to this assessment** (N-1…N-6), the most serious being that
  `GET /api/suspect-alerts` applies no scoping of any kind and `suspect_alerts` has no `branch_id`
  column — the only Release 1.0 access-control gap that cannot be closed without a schema change.
- **Fingerprint biometrics are not stored server-side at all**; captures live in browser
  `localStorage`, matching is client-side string comparison, and the USB bridge service the UI calls
  has no code in this repository. Raised as decision **D-18**.
- **Crime Unit** has no case-assignment model, four competing status vocabularies, no state machine
  and no dedicated test suite; `crime_cases` and `crime_incidents` have no foreign key and no shared
  identifier.
- The owner-reported Fingerprint figure of "approximately 80%" is **neither supportable nor refutable
  from the repository** and is **not adopted**; the Checkpoint report of "already implemented" is
  partially contradicted by the scope fail-open and the absent post-flag workflow.
- **No progress percentage was produced by this assessment.**

### Correction recorded (no history rewritten)

While drafting the security list, an intermediate draft reassigned several of the PR #23 audit's
finding identifiers. The audit's numbering — as carried in `PROJECT_STATUS.md` §6 — is authoritative
and was restored before delivery. The conflict is documented in
`assessment/SECURITY_REMEDIATION_PRIORITY.md` §0.2 rather than silently resolved. **PR #23 and its
audit report were not modified.**

### Affected modules

Documentation only — new `assessment/` directory; updates to `PROJECT_STATUS.md` and this changelog.
**No change to `backend/`, `index.html`, `application.html`, `certificate.html`, `scripts/`, any test
file, or any configuration.**

### Database migrations

**None.** No schema change was made, proposed as executed, or applied.

### Tests performed

| Check | Result |
|---|---|
| `python3 backend/server.py --ui-check` | **PASS** — exit 0; build `sentinel-branch-crud-1-e7c41b90`; checkout `arena/6303ef2f-sentinel-police-management @ a1c2478` |
| `python3 backend/test_print_fit.py` | **PASS** — `ALL PRINT TEMPLATE TESTS PASSED` |
| The other **23** suites | **NOT RUN.** They require `psycopg2-binary`, `pgserver` and `jsdom@26`; none are installed and installing dependencies was out of scope. Recorded as *not run*, never as passing. |

### Commit reference

Recorded in the commit that adds this entry, on branch
`arena/6303ef2f-sentinel-police-management`.

### Next step

**STOP — awaiting owner approval.** No implementation, remediation or scheduling work is authorised.
Fifteen of the thirty open decisions block Release 1.0; **D-18**, **D-14** and **D-15** must be
answered before the remaining work can be sized.

---

## 2026-11-06 — CID Release 1.0 (pre-development) — Documentation baseline

**This entry is the documentation setup for CID Release 1.0. It is not a feature release and contains
no application change.**

### Change description

Established the permanent project documentation baseline so that future development sessions do not
depend on prior chat history. Created four documents at the repository root:

| File | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | Permanent source of project purpose, verified architecture, Release 1.0 scope, unit responsibilities, development principles, mandatory security and privacy requirements, roles and access-control principles, branch-isolation requirements, data-integrity and audit requirements, migration/deployment principles, agent and owner responsibilities, and the rules against unapproved scope expansion. Includes a consolidated register of 17 decisions requiring owner confirmation (D-01 … D-17). |
| `PROJECT_STATUS.md` | Live status: release, phase, branch, commit, per-unit status, completed/in-progress/not-started work, known defects, security blockers, test results, deployment readiness, current and next task. |
| `RELEASE_PLAN.md` | Approved release structure: Release 1.0 scope (Fingerprint, Crime incl. advanced reports, Checkpoint), Airport postponed to Release 1.1, acceptance principles, functional-testing requirements, 12 security gates, integration requirements, staging/production approval requirements, and future release planning rules. |
| `CHANGELOG.md` | This file. |

Recorded as verified repository facts at the baseline commit:

- **Branch** `arena/6303ef2f-sentinel-police-management`, **commit**
  `a1c2478262776e9f20b4c3ad806eaa86adc27792` (2026-10-27 17:13:20 +0000), identical to `origin/main`;
  working tree clean before the documentation files were added.
- **Stack:** Python 3 standard-library `ThreadingHTTPServer` + `psycopg2` + PostgreSQL backend
  (`backend/server.py`, 10,067 lines); single-file HTML SPA front end (`index.html`, 13,158 lines);
  printable `application.html` and `certificate.html`; 44 tracked files; **no** dependency manifests,
  container definition, CI configuration or TLS/reverse-proxy configuration.
- **Database schema:** 21 application tables; `police_branches.unit_type` constrained to
  `fingerprint`, `crime`, `checkpoint`, `airport`, `police_station`; no `case_participants` table
  (participants are modelled via `suspect_alerts`); **no migration-version table**.
- **Role model:** nine role identities with module grants read directly from `ROLE_MODULES`,
  including the global read-only `chief_commander` firewall.
- **Build identity:** `sentinel-branch-crud-1-e7c41b90`.

Recorded as the status of the earlier security audit:

- `DEPLOYMENT_AUDIT.proposed.md` is **not present on `main` and not in the working tree**. It exists
  only on branch `arena/8834f56d-sentinel-police-management` (head `7da888b`), proposed by **draft
  pull request #23**, which is **open and unmerged**. The file is 1,522 lines and the branch adds
  **exactly one file** relative to its merge base. **The audit and its history were preserved; no
  audit finding was modified.**
- The audit's audited revision was `381545c` — the **immediate parent** of the current baseline
  commit `a1c2478`. The eight historical concerns named in the Release 1.0 assignment were re-checked
  **statically** at `a1c2478`; results are recorded per finding in `PROJECT_STATUS.md` §6, including
  three that could not be checked without a running system.
- **Correction to a prior figure:** the audit's "23 test suites" count is **no longer accurate**. The
  tree now contains **25 test files** (12 Python + 13 Node), because `a1c2478` added
  `backend/test_branch_management_crud.py` and `backend/test_branch_management_ui.mjs`. The two
  obsolete SQLite-era harnesses remain present. The audit's "21 passing" outcome was **not
  re-verified** at this baseline.

### Affected modules

**None.** No application module was modified. Documentation only.

- Files added: `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md`, `RELEASE_PLAN.md`, `CHANGELOG.md`
- Files modified: none
- Files deleted: none
- Application code, frontend, backend, configuration, scripts and tests: **unchanged**

### Database migrations

**None.** No schema change, no data change, no migration created, applied or designed. No database was
connected to during this task.

### Tests performed

| Check | Result |
|---|---|
| `python3 backend/server.py --ui-check` | **PASS** — exit 0; build `sentinel-branch-crud-1-e7c41b90`; checkout `arena/6303ef2f-sentinel-police-management @ a1c2478` |
| `python3 backend/test_print_fit.py` | **PASS** — `ALL PRINT TEMPLATE TESTS PASSED` |
| Remaining 24 test files | **NOT RUN** — they require `psycopg2`, `pgserver` and/or `jsdom`, which are not installed; installing dependencies was out of scope for this documentation task. Recorded as *not run*, **not** as passing. |
| `git status` / `git diff` review | Confirmed the change set contains only the four new documentation files |

### Commit reference

- **Branch:** `arena/6303ef2f-sentinel-police-management`
- **Baseline commit (state documented):** `a1c2478262776e9f20b4c3ad806eaa86adc27792`
- **Documentation commit:** recorded in the session report accompanying this change set.

### Notes and limitations

1. **Release 1.0 scope is fixed as:** Fingerprint Unit, Crime Unit (full operations **including
   advanced reports**), Checkpoint Unit, plus the shared functionality they require. **Airport Unit is
   postponed to CID Release 1.1.**
2. **No progress percentage was adopted.** The owner-reported "Fingerprint ~80%" and "Checkpoint
   already implemented" are recorded as **owner reports, not yet verified**.
3. **The 10-day sprint proposal beginning 2026-11-06, with 2026-11-15 as a review checkpoint, is
   recorded as a proposal only.** No schedule was invented or finalised.
4. **17 decisions require owner confirmation** before the affected work can proceed
   (`PROJECT_CONTEXT.md` Appendix A). D-01 … D-12 restate the earlier audit's open questions, which
   remain unanswered in the repository; D-13 … D-17 were raised by this baseline.
5. **Next step:** an owner-approved repository assessment of the three CID units, followed by a
   delivery-planning session. No implementation work is authorised.
6. This entry was prepared in the session of 2026-11-05 UTC and is dated 2026-11-06 as the Release 1.0
   documentation baseline, per the project owner's instruction.
