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
