# CID Release 1.0 — Technical and Functional Assessment

**Deliverable 1 of 8 · Phase 2 · Assessment only — no code, schema, configuration or deployment was changed.**

| Field | Value |
|---|---|
| Repository | `CabdallaCms/sentinel-police-management` |
| Branch | `arena/6303ef2f-sentinel-police-management` |
| Assessed commit | `a1c2478262776e9f20b4c3ad806eaa86adc27792` (`a1c2478`, 2026-10-27 17:13:20 +0000) |
| Identical to | `origin/main` |
| Build identity | `sentinel-branch-crud-1-e7c41b90` (`python3 backend/server.py --ui-check` → exit 0) |
| Assessment date | 2026-11-06 |
| Scope | Fingerprint Unit · Crime Unit · Checkpoint Unit (CID Release 1.0) |
| Companion documents | `FINGERPRINT_UNIT_GAP_ANALYSIS.md` · `CRIME_UNIT_REQUIREMENTS.proposed.md` · `CHECKPOINT_UNIT_GAP_ANALYSIS.md` · `SECURITY_REMEDIATION_PRIORITY.md` · `DECISION_REGISTER_RECOMMENDATIONS.md` · `DEPENDENCIES_AND_ESTIMATES.md` |

---

## 0. Method, evidence classes and limits

### 0.1 What was done

1. Read `PROJECT_CONTEXT.md`, `PROJECT_STATUS.md`, `RELEASE_PLAN.md`, `CHANGELOG.md`.
2. Read the historical audit `DEPLOYMENT_AUDIT.proposed.md` (branch `arena/8834f56d-sentinel-police-management`, head `7da888b`, draft PR **#23**, still open and unmerged).
3. Static code review of `backend/server.py` (10,067 lines), `backend/vehicles.py`, `index.html` (13,158 lines), `application.html`, `certificate.html`.
4. Inventory and content analysis of all 25 test files.
5. Executed the only two checks that run without installing dependencies.

### 0.2 Evidence classes used throughout

| Class | Meaning |
|---|---|
| **[STATIC]** | Established by reading the code at `a1c2478`. File and line cited. High confidence about *what the code does*; does not prove runtime behaviour under real data. |
| **[RUNTIME-2026-11-06]** | Executed in this session and observed. |
| **[RUNTIME-HISTORICAL]** | Executed by the PR #23 audit against `381545c` (the **parent** of `a1c2478`). Not re-executed here. |
| **[NOT VERIFIED]** | Could not be established in this session. |

### 0.3 Hard limits of this assessment

- **No test suite requiring dependencies could be run.** `psycopg2`, `pgserver`, `jsdom` and PostgreSQL are absent, and installing dependencies is outside the approved scope. 23 of 25 test files are therefore **not run**, not "passing". **[RUNTIME-2026-11-06]**
- **No database existed** to inspect, so no data-volume, index or query-plan observation was possible.
- **Static review cannot prove absence of a defect**, only presence. Where the code plainly lacks a check, that is stated; where behaviour depends on data, it is marked **[NOT VERIFIED]**.

### 0.4 Verifications executed this session **[RUNTIME-2026-11-06]**

| Check | Result |
|---|---|
| `python3 backend/server.py --ui-check` | **exit 0** — build `sentinel-branch-crud-1-e7c41b90`, checkout `arena/6303ef2f… @ a1c2478` |
| `python3 backend/test_print_fit.py` | **PASS** — `ALL PRINT TEMPLATE TESTS PASSED` |
| `python3 -c "import psycopg2"` | `ModuleNotFoundError` — confirms suites cannot run |

---

## 1. Classification summary across the three units

Using the five required classes. Counts are of **assessed feature areas**, not of code.

| Unit | Implemented and verified | Implemented but not verified | Partially implemented | Not implemented | Blocked |
|---|---|---|---|---|---|
| **Fingerprint** | 1 | 9 | 5 | 6 | 2 |
| **Crime** | 0 | 7 | 4 | 10 | 3 |
| **Checkpoint** | 0 | 8 | 3 | 5 | 1 |

> **"Implemented and verified" is almost empty by design, not by pessimism.** Only one feature area in Release 1.0 scope has a passing test executed at `a1c2478` in this session (the A4 print contract). Everything else has either no test, or a test that exists but could not be run here. This is the single most important finding of Phase 2.

---

## 2. Fingerprint Unit

### 2.1 Existing functionality **[STATIC]**

| Capability | Where |
|---|---|
| Clearance application intake (multipart or JSON), 4-part name, NID/passport requirement | `backend/server.py:8943-8996` |
| Five mandatory clearance purposes — Education, Travel, Employment, Citizenship, Licence | `CLEARANCE_REASONS`, `backend/server.py:649` |
| Guardian/guarantor block (name, relationship, ID, occupation, address, phone) | `clearance_applications` DDL `:265`; intake `:8972-8974` |
| Applicant documents (≥2 enforced) and guardian documents (≥2 enforced), applicant photo | `:8969-8973` |
| Central Person auto-create / fill-only enrichment on submit | `ensure_person()` at `:8964`; audit `CREATE`/`ENRICH` |
| Branch-scoped register read | `user_branch_scope(c,user,'fingerprint')`, `:8201` |
| Branch-scoped single-record read (403 on cross-branch) | `require_record_branch_scope(...,'fingerprint',...)`, `:8244` |
| Branch-scoped create | `require_branch_write_scope(...,'fingerprint')`, `:8952` |
| 12-hour mandatory review gate, `Citizenship` exempt, SystemAdmin bypass | `review_gate_decision()` + a second inline guard, `:9039-9066` |
| Boot-time refusal if the review gate is disarmed | `review_lock_armed()` `:1057`, enforced `:10022` |
| Signed-scan upload, versioned additively, extension allow-list + 20 MB cap | `:8997-9031`; `clearance_signed_documents` `:281` |
| Approval → certificate number generation, `reviewed_at` stamp, audit row | `:9067-9080` |
| Certificate print lock (signed scan required unless admin) | `certificate_print_state()`, used `:8227`, `:8258` |
| Printable A4 application and certificate | `application.html`, `certificate.html` |
| Per-record audit history, branch-scoped | `AUDIT_ENTITY_*` maps `:2757-2772`; `:4281` |
| Fingerprint register UI, review drawer, approve action, status badges | `renderFingerprintTable`, `openClearanceReview`, `approveFP` in `index.html` |
| USB scanner capture via a **local** bridge (WebSocket / HTTP on `127.0.0.1`) | `index.html:4773-5301` |

### 2.2 Actual implementation status

| Feature | Class | Evidence / reason |
|---|---|---|
| A4 print contract for application + certificate | **Implemented and verified** | `test_print_fit.py` **PASS** this session **[RUNTIME-2026-11-06]** |
| Application intake + validation | Implemented but not verified | `:8943-8996` **[STATIC]**; no suite run |
| 12-hour review gate + Citizenship exemption + admin bypass | Implemented but not verified | Double-guarded `:9039-9066`; `test_review_gate.py` exists (6 scenarios) but **not run** |
| Boot-time review-lock self-test | Implemented but not verified | `:10022` **[STATIC]** |
| Signed-scan upload with extension + size validation | Implemented but not verified | `:9009-9018` **[STATIC]** |
| Certificate print lock | Implemented but not verified | `certificate_print_state()`; `test_clearance_rbac_ui.mjs` exists, **not run** |
| Branch-scoped **read** of register and single record | Implemented but not verified | `:8201`, `:8244`; `test_branch_scope.py` exists, **not run** |
| Branch-scoped **create** | Implemented but not verified | `:8952` **[STATIC]** |
| Module gating (`fingerprint`) on GET and POST | Implemented but not verified | `:8099`, `:8872` **[STATIC]** |
| Per-record audit history | Implemented but not verified | `:4281` **[STATIC]** |
| Branch isolation on **approve / signed-document / documents** | **Partially implemented** | Those three routes carry **no** `require_record_branch_scope()` call — `:8152`, `:8997`, `:9032` vs call sites `:4281`, `:8244`, `:8283` **[STATIC]**; reproduced live at `381545c` **[RUNTIME-HISTORICAL]** |
| Document protection at retrieval | **Partially implemented** | `/uploads/` is served by `serve_static()` which `do_GET` calls before authentication, `:7914` **[STATIC]** |
| Upload validation for applicant/guardian documents | **Partially implemented** | `save_upload()` regenerates the name and strips the path but applies **no extension, MIME or size check**, `:3939-3946`. Only `/signed-document` validates. **[STATIC]** |
| Biometric capture | **Partially implemented** | Hardware capture UI exists, but the capture is stored in **browser `localStorage`** (`BIOMETRIC_STORE_KEY = 'sentinelBiometrics'`, `index.html:2698-2725`) **[STATIC]** |
| Fingerprint matching | **Partially implemented** | `matchPersonByFingerprint()` runs **client-side** against the local `db.people` array, `index.html:4526` **[STATIC]** |
| Server-side biometric storage (template column/table) | **Not implemented** | No `fingerprint_template` / biometric column or table anywhere in the DDL **[STATIC]** |
| Server-side biometric matching / AFIS | **Not implemented** | No matching code in `backend/server.py` **[STATIC]** |
| **Reject** a clearance application | **Not implemented** | No reject endpoint exists; `'Rejected'` appears only in HR/conduct constants and as an unreachable axis label in fingerprint analytics (`:6112`, `:6124`) **[STATIC]** |
| Separation of duties (filer ≠ approver) | **Not implemented** | The approve route checks role, time and purpose, never the submitter, `:9032-9080` **[STATIC]** |
| Certificate verification by a third party (QR/online) | **Not implemented** | No verification endpoint **[STATIC]** |
| Clearance renewal / expiry handling (the certificate states 6 months) | **Not implemented** | No expiry field or job **[STATIC]** |
| The local USB bridge service itself | **Blocked** | The browser calls `http://127.0.0.1:<port>` and `ws://localhost:<port>`; **no bridge service exists in this repository** `index.html:4773-4774, 5183` **[STATIC]**. Depends on **D-18**. |
| Biometric data policy (retention, DPIA, storage location) | **Blocked** | Depends on **D-04 / D-05** |

### 2.3 Roles and permissions **[STATIC]**

| Role | Fingerprint access |
|---|---|
| `SystemAdmin` | Full; bypasses the 12-hour gate (`is_admin_user` in `review_gate_decision`); unscoped across branches (`branch_scope_view` returns `None`) |
| `FingerprintUnit` | Modules `{dashboard, people, fingerprint}` (`ROLE_MODULES:1871`); branch-scoped on register and single-record reads; **not** branch-scoped on approve / signed-document / documents |
| `chief_commander` | Read-only: can read the register; every write answers `403` via `enforce_read_only()` before routing |
| All other roles | `403` from the module gate (`require_module(user,'fingerprint')`) |

**Gap:** the Fingerprint Unit has **one** operational role. There is no separate reviewer, supervisor or unit-chief role, which is why separation of duties cannot currently be expressed. Blocked on **D-12**.

### 2.4 Main workflows **[STATIC]**

1. **Intake** — officer files the application → identity resolved/created → documents stored → status `Pending Review` → `created_at` stamped UTC → `review_eligible_at` returned.
2. **Review wait** — 12 hours, enforced in three places; `Citizenship` exempt; admin bypass.
3. **Signed-scan upload** — paper sheet scanned back in, versioned additively.
4. **Approval** — gate re-evaluated twice server-side → status `Approved`, `certificate_number` `CL-xxxxxxxx`, `reviewed_at` set, audit row written.
5. **Certificate print** — unlocked once a signed scan exists (admins bypass).

**Missing from the workflow:** rejection, return-for-correction, re-submission, supervisor escalation, and any state other than `Pending Review` → `Approved`.

### 2.5 Database tables and relationships **[STATIC]**

```
persons (id, person_id 'P-0001', 4-part name, dob, national_id, passport_id,
         mother_name, photo_path, …)
   │ 1
   │                     ┌──────────────────────────────────────────┐
   └──< clearance_applications (application_id 'FP-########')        │
            │  person_id      → persons.id                          │
            │  branch_id      → police_branches.id  ON DELETE SET NULL
            │  purpose ∈ CLEARANCE_REASONS                          │
            │  status  'Pending Review' | 'Approved'                │
            │  certificate_number 'CL-########'                     │
            │  applicant_docs / guardian_docs  (JSON text columns)  │
            │  created_at (UTC) · reviewed_at · created_by → users.id
            │                                                       │
            └──< clearance_signed_documents (application_id FK,      │
                   ON DELETE CASCADE, file_path, uploaded_by)       │
                                                                     │
audit_events (user_id, action, entity='clearance_application'|       │
              'clearance_signed_document', entity_id, details)  ─────┘
```

**Notable:** `applicant_docs` and `guardian_docs` are **JSON blobs in TEXT columns**, not rows — so a document cannot be queried, counted, access-controlled or retention-managed individually. **[STATIC]**

### 2.6 API endpoints and frontend components **[STATIC]**

| Method | Path | Module gate | Branch scope | Note |
|---|---|---|---|---|
| GET | `/api/clearance-applications` | `fingerprint` | **Yes** | `:8197` |
| GET | `/api/clearance-applications/<id>` | `fingerprint` | **Yes** | `:8234` |
| GET | `/api/fingerprint/applications…` | `fingerprint` | via canonical alias | `canonical_api_path()` |
| POST | `/api/clearance-applications` | `fingerprint` | **Yes** | `:8943` |
| POST | `/api/clearance-applications/<id>/signed-document` | `fingerprint` | **No** | `:8997` |
| POST | `/api/clearance-applications/<id>/approve` | `fingerprint` | **No** | `:9032` |
| GET | `/api/persons/<id>/documents` | *(none — `/api/persons` is open to any session)* | **No** | `:8152` |
| GET | `/api/audit/entity/clearance_application/<id>` | `fingerprint` | **Yes** | `:4281` |
| GET | `/api/cid/analytics` → `fingerprint` section | any CID module | **No** | `cid_fingerprint_analytics(c)` takes no user, `:6071` |

**Frontend:** `index.html` page `#fingerprint`; `renderFingerprintTable`, `openClearanceReview`, `refreshClearanceReview`, `renderClearanceReview`, `approveFP`, `fingerprintStatusBadge`, `certificateControlHtml`, `certificatePrintState`, `clearanceFiles`, `clearancePurpose`, `handleFingerprintUpload`, `scanFingerprint`, `matchPersonByFingerprint`, `captureFromBridge` / `captureFromUsb` / `captureFromHid`; standalone pages `application.html`, `certificate.html`. One free-text search box ("Search application, person, purpose or status…"), no structured filters.

### 2.7 Existing tests and their results

| Suite | Fingerprint relevance | Result at `a1c2478` |
|---|---|---|
| `backend/test_print_fit.py` | A4 print contract, blueprint fidelity, bindings | **PASS** **[RUNTIME-2026-11-06]** |
| `backend/test_review_gate.py` | 12-hour gate, 6 scenarios incl. restart | **NOT RUN** (needs `pgserver`) |
| `backend/test_field_level_rbac.py` | field-level 403, print lock, photo attachment | **NOT RUN** |
| `backend/test_branch_scope.py` | 28 fingerprint references; register + record scoping | **NOT RUN** |
| `backend/test_approval_flow.mjs` | approval front end | **NOT RUN** (needs `jsdom`) |
| `backend/test_clearance_rbac_ui.mjs` | purpose chip, document viewer, print lock | **NOT RUN** |
| `backend/test_record_audit_ui.mjs` | record audit drawer | **NOT RUN** |

**Coverage gaps proven by inspection [STATIC]:**
- `test_branch_scope.py` contains **zero** references to `approve` or `signed-document` → the two leaking write routes are **untested**.
- **No suite requests an upload URL anonymously** → unauthenticated document access is **untested**.
- No test asserts that the submitter cannot approve their own application.

### 2.8 Missing functionality (summary)

Rejection path · return-for-correction · separation of duties · server-side biometric storage · server-side biometric matching · the local bridge service · certificate verification · certificate expiry/renewal · structured search filters · per-document rows with individual access control · branch isolation on approve/signed-document/documents · authenticated document retrieval.

### 2.9 Security weaknesses (unit view)

C-1 public documents · H-2a cross-branch approve and signed-scan · M-3 self-approval and the `Citizenship` bypass · M-7 unvalidated applicant/guardian uploads · identifier collision risk on `FP-`/`CL-` millisecond ids. Detail, severity and remediation in `SECURITY_REMEDIATION_PRIORITY.md`.

### 2.10 Integration dependencies

Central Person Registry (`ensure_person`, enrichment) · `police_branches` (scoping) · `users` (attribution, badge) · `audit_events` · the uploads directory · `suspect_alerts` (read, for the analytics hit-rate) · the external USB bridge on the officer's workstation · the two printable HTML pages.

---

## 3. Crime Unit

### 3.1 Existing functionality **[STATIC]**

| Capability | Where |
|---|---|
| CID case creation (`CID-2026-###`) with category, location, status, summary, notes | `:9080-9091` |
| CID case register, branch-scoped, with participant counts | `:8259-8281` |
| CID case detail with participants and evidence, branch-scoped | `:8282-8291` |
| CID case update (category, location, status, summary, notes) | PATCH `:9581-9593` |
| Evidence upload against a case | POST `:9092-9105` |
| Suspect / participant listing with **optional** case link | `suspect_alerts`, POST `:9172-9211` |
| Duplicate-alert guard (409 on an existing active alert for the same person+case) | `:9194-9202` |
| Station-level crime incident intake with victim block and 2 evidence slots | `crime_incidents` `:374`; `register_crime()` `:5032` |
| Crime incident register, branch-scoped by `police_station` | GET `/api/crimes` `:8555-8571` |
| CID analytics bundle (crime section) | `cid_crime_analytics()` `:6132` |
| Case workspace UI with three tabs | `index.html` `#caseworkspace` |
| Suspect alerts consumed by the Checkpoint Unit for flagging | `:9304-9306` |

### 3.2 Actual implementation status

| Feature | Class | Evidence / reason |
|---|---|---|
| Case registration | Implemented but not verified | `:9080` **[STATIC]**; no dedicated suite |
| Case register read, branch-scoped | Implemented but not verified | `:8259` **[STATIC]** |
| Case detail read, branch-scoped | Implemented but not verified | `:8283` **[STATIC]** |
| Suspect listing with optional case link | Implemented but not verified | `:9172` **[STATIC]** |
| Duplicate active-alert guard | Implemented but not verified | `:9194` **[STATIC]** |
| Evidence upload | Implemented but not verified | `:9092` **[STATIC]** |
| Crime incident intake (`/api/crimes`) | Implemented but not verified | `register_crime()` `:5032` **[STATIC]** |
| Case workspace UI (3 tabs) | Implemented but not verified | `index.html` `#caseworkspace` **[STATIC]** |
| Case status update | **Partially implemented** | PATCH accepts any string for `status`; no state machine, no allowed-transition check, no reason, no timestamp, **and no branch check** `:9581-9593` **[STATIC]** |
| Branch isolation across the unit | **Partially implemented** | Present on case list/detail/create; **absent** on PATCH case, POST evidence, and **entirely absent** on suspect alerts **[STATIC]** |
| Crime incident branch scoping | **Partially implemented** | `/api/crimes` scopes by `user_branch_scope(c, user, 'police_station')` `:8557` — the Crime Unit's own branches are `unit_type='crime'`. Whether a CID officer resolves against a `police_station` branch is data-dependent; if it does not resolve, `branch_scope_view()` returns `None` and the officer sees **every** incident **[STATIC]**, outcome **[NOT VERIFIED]** |
| Reports / statistics | **Partially implemented** | One fixed bundle, no filters, no date range, no export, **no branch scoping** — `cid_crime_analytics(c)` takes no user `:6132` **[STATIC]** |
| **Case assignment to an investigator** | **Not implemented** | No `assigned_to` / `investigator` / `officer_in_charge` column anywhere **[STATIC]** |
| Investigation workflow (tasks, actions, timeline, deadlines) | **Not implemented** | No table, no endpoint **[STATIC]** |
| Suspect status lifecycle (arrested, released, charged, cleared) | **Not implemented** | `alert_status` is only set to `'Active alert'`; no endpoint changes it **[STATIC]** |
| Evidence chain of custody | **Not implemented** | `case_evidence` records uploader and caption only — no custody transfers, no hash, no seal **[STATIC]** |
| Evidence delete / correct | **Not implemented** | No DELETE route for evidence **[STATIC]** |
| Case closure rules / approval | **Not implemented** | `status='Closed'` is a free-text PATCH **[STATIC]** |
| Structured search and filtering | **Not implemented** | One client-side free-text box per register; no server-side query parameters on `/api/crime-cases` or `/api/suspect-alerts` **[STATIC]** |
| Advanced reports (as a defined deliverable) | **Blocked** | No specification exists — **D-14** |
| `crime_cases` ↔ `crime_incidents` relationship | **Blocked** | No FK, no documented intent — **D-15** (full analysis in `CRIME_UNIT_REQUIREMENTS.proposed.md` §2) |
| Court/prosecution handover | **Blocked** | Depends on owner's operational definition — **D-19** |

### 3.3 Roles and permissions **[STATIC]**

| Role | Crime access |
|---|---|
| `CIDUnit` | Modules `{dashboard, people, cid, crimes}`. `cid` gates `/api/crime-cases` and `/api/suspect-alerts`; `crimes` gates `/api/crimes`. Also reads `stations`/`officers` through the `crimes` break-out at `:8116` |
| `SystemAdmin` | Everything, unscoped |
| `chief_commander` | Read-only across all crime routes; writes `403` |
| All other roles | `403` from the module gate |

**Gaps:** there is **one** CID role. No investigator vs. supervisor vs. unit-chief distinction, no case-level permission (anyone in the branch can edit any case), and `/api/suspect-alerts` is readable by **any** `cid`-module holder with **no branch filter at all** `:8425-8432` **[STATIC]**.

### 3.4 Main workflows **[STATIC]**

- **Case intake:** POST `/api/crime-cases` → `CID-2026-###` → status `Reported`.
- **Participant/suspect listing:** POST `/api/suspect-alerts`, case optional; origin `Case Link` / `Direct Intelligence Listing` / `Manual Entry`; a suspect alert makes the person flag at checkpoints.
- **Evidence:** POST `/api/crime-cases/<id>/evidence`, caption + file.
- **Case update:** PATCH, free-text fields.
- **Station incident intake:** POST `/api/crimes` → `crime_incidents`, a *separate* record with its own `file_number`, station, officer, victim block.

**There is no investigation workflow**: no assignment, no tasks, no actions log, no deadlines, no supervisory review, no closure authorisation.

### 3.5 Database tables and relationships **[STATIC]**

```
persons ──1──< suspect_alerts (alert_id 'AL-xxxxxxxx')
                  │ person_id → persons.id          (NOT NULL)
                  │ case_id   → crime_cases.id      (NULLABLE — link optional)
                  │ role      'Suspect'|'Victim'|'Witness'|'Complainant'
                  │ alert_status 'Active alert'
                  │ origin    'Case Link'|'Direct Intelligence Listing'|'Manual Entry'
                  │ ** NO branch_id **
crime_cases (case_id 'CID-2026-###')
     │ branch_id → police_branches.id (unit_type='crime')
     │ category · location · status · incident_summary · notes · created_by
     └──< case_evidence (evidence_id 'EV-xxxxxxxx', case_id → crime_cases.id,
                         caption, file_path, uploaded_by)

crime_incidents (file_number)         ← SEPARATE, NOT LINKED TO crime_cases
     │ station_id → police_stations.id (NOT NULL)
     │ officer_id → officers.id        (NOT NULL)
     │ branch_id  → police_branches.id
     │ category · incident_at · severity · case_status · victim_* · statement
     │ evidence1_type/path · evidence2_type/path
```

**Three structural findings [STATIC]:**
1. **`suspect_alerts` has no `branch_id`.** Suspect data is structurally global; branch isolation cannot be enforced on it without a schema change.
2. **`crime_cases` and `crime_incidents` have no relationship** — no foreign key, no shared identifier, no conversion endpoint. They are two parallel crime records with different lifecycles, different status vocabularies (`CASE_STATUSES` vs `CRIME_STATUSES`) and different evidence models (rows vs two fixed columns).
3. **No `case_participants` table.** Participants are `suspect_alerts` rows, so a victim or witness is stored in a table named "suspect alerts" and inherits its alert semantics.

### 3.6 API endpoints and frontend components **[STATIC]**

| Method | Path | Module gate | Branch scope |
|---|---|---|---|
| GET | `/api/crime-cases` | `cid` | **Yes** `:8260` |
| GET | `/api/crime-cases/<id>` | `cid` | **Yes** `:8283` |
| POST | `/api/crime-cases` | `cid` | **Yes** `:9081` |
| PATCH | `/api/crime-cases/<id>` | `cid` `:9509` | **No** `:9581` |
| POST | `/api/crime-cases/<id>/evidence` | `cid` | **No** `:9092` |
| GET | `/api/suspect-alerts` | `cid` | **No — none at all** `:8425` |
| POST | `/api/suspect-alerts` | `cid` | **No** `:9172` |
| GET | `/api/crimes` | `crimes` | by `police_station` `:8557` |
| POST | `/api/crimes` | `crimes` | inside `register_crime()` `:5033` |
| GET | `/api/cid/analytics` | any CID module | **No** `:6132` |

**Frontend:** pages `#cid`, `#caseworkspace`, `#crimes`; `renderCases`, `openCase`, `openCaseDrawer`, `submitCaseDrawer`, `saveCaseDetails`, `renderSuspectTable`, `openAddSuspect`, `submitAddSuspect`, `renderCwEvidence`, `uploadEvidence`, `renderCrimesTable`, `saveCrime`, `fillCrimeSelects`, `caseOptions`. Case-workspace status select offers **Reported / Under Investigation / Submitted for Prosecution / Closed** (`index.html:1730`) — a **fourth** vocabulary, differing from both `CASE_STATUSES` and `CRIME_STATUSES`.

### 3.7 Existing tests and their results

| Suite | Crime references | Result |
|---|---|---|
| `test_read_only_rbac.py` | 9 — Commander write-refusal on crime routes | **NOT RUN** |
| `test_branch_scope.py` | 5 — CID case read/write scoping | **NOT RUN** |
| `test_linked_records.py` | 3 | **NOT RUN** |
| `test_dynamic_branches.py` | 3 | **NOT RUN** |
| `test_reverse_sequence_ui.mjs` | 7 — row numbering only | **NOT RUN** |
| `test_server.py` | 40 — **obsolete SQLite-era harness** | Expected to fail |

**The Crime Unit has no dedicated test suite.** **[STATIC]** Counted across all 23 current suites, crime coverage is incidental (RBAC firewall, branch scoping, row numbering). There is no test for case creation validation, status transitions, evidence, suspect lifecycle, duplicate handling, reports, or cross-branch access on PATCH/evidence/suspect-alerts. For a unit whose Release 1.0 scope is "full operations including advanced reports", this is the largest single risk in the release.

### 3.8 Missing functionality

Case assignment · investigation workflow · suspect lifecycle · evidence chain of custody and deletion · closure authorisation · status state machine · structured search and server-side filtering · defined advanced reports · branch isolation on PATCH, evidence and suspect alerts · a decided `crime_cases`/`crime_incidents` relationship · participant modelling separate from alerts.

### 3.9 Security weaknesses (unit view)

Cross-branch case edit (PATCH) · cross-branch evidence upload · unscoped suspect-alert read and write · unscoped crime analytics · `COUNT(*)+8` case-id generation (race) · unvalidated evidence uploads · public document retrieval. See `SECURITY_REMEDIATION_PRIORITY.md`.

### 3.10 Integration dependencies

Central Person Registry · `police_branches` · `police_stations` and `officers` (required NOT NULL for `crime_incidents`) · `users` · `audit_events` · uploads directory · **Checkpoint Unit** (consumes `suspect_alerts` to flag travellers) · **Fingerprint Unit** (its analytics hit-rate reads `suspect_alerts`).

---

## 4. Checkpoint Unit

### 4.1 Existing functionality **[STATIC]**

| Capability | Where |
|---|---|
| Traveller screening event capture with mandatory real-time photo | POST `:9212-9345` |
| Full traveller validation: 4-part name, DOB, purpose of visit, current address, ≥1 traveller document | `:9220-9231` |
| Full guardian block: 4-part name, relationship, phone, permanent address, occupation, ≥1 document | `:9232-9246` |
| Guardian identity resolution against the central registry | `:9256-9266` |
| Automatic suspect flagging — `Flagged match` + `Supervisor contacted` when an active alert exists | `:9304-9307` |
| Location normalisation to canonical `South`/`East`/`West` codes across three columns | `:9267-9290` |
| Location-scoped read with a tolerant 6-way SQL match | GET `:8433-8492` |
| Location-scoped write refusal | `:9300-9303` |
| Branch-scoped write | `require_branch_write_scope(...,'checkpoint')` `:9219` |
| Unified `checkpoint_officer` role with legacy-alias migration | `unify_checkpoint_roles()`; `ROLE_LABELS:1816` |
| Per-record audit history, scoped | `AUDIT_ENTITY_*`; `test_checkpoint_roles_audit.py` |
| Vehicle plate/VIN lookup from the checkpoint page | `lookupCheckpointPlate`, `/api/vehicles` break-out `:8118-8123` |
| Checkpoint analytics, location-scoped | `cid_checkpoint_analytics(c, user)` `:6176` |

### 4.2 Actual implementation status

| Feature | Class | Evidence / reason |
|---|---|---|
| Screening event capture + validation | Implemented but not verified | `:9212-9266` **[STATIC]** |
| Mandatory traveller photo + documents | Implemented but not verified | `:9229-9231` **[STATIC]** |
| Guardian block + identity resolution | Implemented but not verified | `:9232-9266` **[STATIC]** |
| Automatic suspect flagging | Implemented but not verified | `:9304-9307` **[STATIC]** |
| Location normalisation | Implemented but not verified | `:9267-9290` **[STATIC]** |
| Unified role + legacy migration | Implemented but not verified | `test_checkpoint_roles_audit.py` (76 references) exists, **NOT RUN** |
| Branch-scoped write | Implemented but not verified | `:9219` **[STATIC]** |
| Location-scoped analytics | Implemented but not verified | `:6182` **[STATIC]** |
| **Location scoping (read + write)** | **Partially implemented** | `checkpoint_scope()` returns the **empty string** for a `checkpoint_officer` whose `location_scope` is blank (`ROLE_LOCATION_SCOPE[ROLE_CHECKPOINT_OFFICER] = ''`, `:1922`; `return ROLE_LOCATION_SCOPE[r] or ''`, `:2990`). Both call sites test `if scope:` — so an empty scope means **every location is readable** `:8460` **and writable** `:9301`. The in-code comment states the opposite intent. **[STATIC]** · reproduced as M-2 **[RUNTIME-HISTORICAL]** |
| Branch-scoped **read** | **Partially implemented** | GET filters by **location**, never by `branch_id`, even though `checkpoint_events.branch_id` exists `:8433-8480` **[STATIC]** |
| Single-record read scoping | **Partially implemented** | No `GET /api/checkpoint-events/<id>` route exists; the register returns whole rows, so there is no per-record gate to enforce **[STATIC]** |
| Screening outcome override by the officer | **Not implemented** | `screening_result` and `action_taken` are computed server-side only; the officer cannot record what actually happened `:9305-9306` **[STATIC]** |
| Event amendment / correction | **Not implemented** | No PATCH route for `checkpoint_events` **[STATIC]** |
| Detention / escalation / handover workflow | **Not implemented** | `action_taken` is a fixed two-value computation **[STATIC]** |
| Vehicle linkage on the event record | **Not implemented** | Plate lookup is a read-only UI convenience; no vehicle column on `checkpoint_events` **[STATIC]** |
| Offline operation at a checkpoint | **Not implemented** (as a designed capability) | The generic `localStorage` fallback exists but is not a sync model `index.html:2641-2648` **[STATIC]**; depends on **D-11** |
| Checkpoint catalogue beyond South/East/West | **Blocked** | `CHECKPOINT_LOCATIONS = ('South','East','West')` `:1649` is hard-coded, while branch management and postings already allow named district checkpoints — needs **D-20** |

### 4.3 Roles and permissions **[STATIC]**

| Role | Checkpoint access |
|---|---|
| `checkpoint_officer` (canonical) | Modules `{dashboard, checkpoints}`; scope = `users.location_scope`, **empty by default** → unscoped |
| `CheckpointSouth` / `East` / `West` (legacy) | Same modules; scope derived from the role name, so these are **safer by default** than the canonical role |
| `SystemAdmin` | All locations (`checkpoint_scope` → `None`) |
| `chief_commander` | Read-only all locations |
| All other roles | `403` from the module gate |

**This is the single most consequential finding for the Checkpoint Unit:** the *modern* role is the *less safe* one, because its default scope is an empty string that the read and write paths interpret as "no restriction".

### 4.4 Main workflows **[STATIC]**

1. Officer opens the checkpoint page, scoped to their posting.
2. Traveller screening form: identity (4-part name, DOB), purpose of visit, addresses, live photo, ≥1 document; guardian block with ≥1 document.
3. Identity resolved or created centrally; missing central fields enriched (fill-only).
4. Server checks `suspect_alerts` for an active `Suspect` alert → `Flagged match` + `Supervisor contacted`, else `No active alert` + `Cleared`.
5. Event stored with normalised location in three columns, audit row written.
6. Optional vehicle plate/VIN lookup as a side query.

**Missing:** what happens *after* a flag. There is no detention record, no escalation, no handover to CID, no outcome field, and no way to correct a mistaken screening.

### 4.5 Database tables and relationships **[STATIC]**

```
persons ──1──< checkpoint_events (event_id 'CP-########')
   │              │ person_id          → persons.id        (NOT NULL)
   │              │ guardian_person_id → persons.id        (nullable)
   │              │ branch_id          → police_branches.id (unit_type='checkpoint')
   │              │ location / location_code / checkpoint_location  (3 columns, same fact)
   │              │ screening_result 'Flagged match' | 'No active alert'
   │              │ action_taken     'Supervisor contacted' | 'Cleared'
   │              │ purpose_of_visit · current_address · permanent_address
   │              │ traveler_photo · traveler_docs (JSON text) · guardian_docs (JSON text)
   │              │ created_by → users.id
suspect_alerts ───┘  (read at screening time to decide the flag)
```

**Notable:** three columns encode one location fact, which is why the read path needs a six-way `OR` with `ILIKE` fallbacks — a normalisation debt that makes the scope filter hard to reason about and hard to test. **[STATIC]**

### 4.6 API endpoints and frontend components **[STATIC]**

| Method | Path | Module gate | Scope |
|---|---|---|---|
| GET | `/api/checkpoint-events` | `checkpoints` | **location** (fails open on empty scope) |
| POST | `/api/checkpoint-events` | `checkpoints` | **branch** (`require_branch_write_scope`) **+ location** (fails open on empty scope) |
| GET | `/api/vehicles` | break-out allows `checkpoints` `:8118` | none |
| GET | `/api/cid/analytics` → `checkpoint` section | `checkpoints` | **location** (same fail-open) |
| GET | `/api/audit/entity/checkpoint_event/<id>` | `checkpoints` | branch-scoped `:4281` |

**Frontend:** page `#checkpoints`; `renderCheckpointPage`, `renderCheckpointTable`, `renderCheckpointNav`, `fetchCheckpoints`, `openCheckpointDrawer`, `openCheckpointUnit`, `submitCheckpoint`, `travelerFormHTML`, `validateTraveler`, `checkpointScopeFor`, `paintCheckpointScopeHint`, `paintCheckpointChips`, `lookupCheckpointPlate`, `userCheckpointOptions`. One free-text search box, plus a plate/VIN lookup box.

### 4.7 Existing tests and their results

| Suite | Checkpoint references | Result |
|---|---|---|
| `test_checkpoint_roles_audit.py` | 76 — unified role, legacy migration, audit history | **NOT RUN** |
| `test_sidebar_navigation.mjs` | 86 — navigation scoping (client-side) | **NOT RUN** |
| `test_frontend_session.mjs` | 57 | **NOT RUN** |
| `test_officer_profile_locations.py` | 34 — role-driven location pickers | **NOT RUN** |
| `test_branch_management_ui.mjs` / `test_branch_management_crud.py` | 29 / 26 | **NOT RUN** |

**Coverage gap [STATIC]:** nothing asserts that a `checkpoint_officer` with a **blank** `location_scope` is denied. The historical audit recorded the opposite behaviour as reproduced (M-2).

### 4.8 Missing functionality

Fail-closed location scoping · branch-based (not only location-based) read scoping · officer-recorded screening outcome · detention/escalation/handover record · event amendment with audit · vehicle linkage on the event · a configurable checkpoint catalogue · designed offline operation.

### 4.9 Security weaknesses (unit view)

M-2 scope fail-open on the canonical role (read **and** write) · H-2b posting fail-open · public document retrieval of traveller photos and ID scans · unvalidated traveller/guardian uploads. See `SECURITY_REMEDIATION_PRIORITY.md`.

### 4.10 Integration dependencies

Central Person Registry · **`suspect_alerts` from the Crime Unit** (hard dependency — the flag is the Checkpoint Unit's core value) · `police_branches` · `users` · `audit_events` · uploads directory · `vehicles` (optional lookup).

---

## 5. Cross-cutting findings

### 5.1 Branch isolation is route-by-route, not systemic **[STATIC]**

Enforcement is applied by hand at each handler. Present at 9 sites (`:4281`, `:8201`, `:8244`, `:8260`, `:8283`, `:8557`, `:8922`, `:8952`, `:9081`, `:9219`); **absent** at `:8152` (person documents), `:8425` (suspect alerts read), `:8997` (signed document), `:9032` (approve), `:9092` (evidence), `:9172` (suspect alert write), `:9581` (case PATCH). A new route is unscoped unless the author remembers. **Recommendation:** a central, deny-by-default scoping layer in front of the router, with an explicit allow-list of unscoped routes.

### 5.2 Analytics bypass branch scoping **[STATIC]**

`cid_crime_analytics(c)` and `cid_fingerprint_analytics(c)` take no `user`. A branch-scoped officer who can see only their own branch's records nonetheless receives **national** totals, category distributions and suspect counts. `cid_checkpoint_analytics(c, user)` is correctly scoped — which shows the omission is an oversight, not a design.

### 5.3 Identifier generation is unsafe and partly hard-coded **[STATIC]**

| Identifier | Scheme | Problem |
|---|---|---|
| `crime_cases.case_id` | `'CID-2026-' + (COUNT(*)+8)` `:9083` | Race under concurrency; **year hard-coded to 2026**; numbering is global, not per-branch |
| `clearance_applications.application_id` | `'FP-' + last 8 digits of epoch ms` `:8975` | Collides on sub-millisecond parallel submits |
| `certificate_number` | same scheme `:9067` | Same |
| `checkpoint_events.event_id` | same scheme `:9319` | Same |
| `suspect_alerts.alert_id` / `case_evidence.evidence_id` | `secrets.token_hex(4)` | 32-bit space; collision possible at scale |

### 5.4 Four competing status vocabularies for one domain **[STATIC]**

`CASE_STATUSES` (7 values, `:1716`) · `CRIME_STATUSES` (5 values, `:1708`) · the case-workspace `<select>` (4 values, `index.html:1730`) · `clearance_applications.status` (2 reachable values, with a third, `Rejected`, charted at `:6124` but unreachable). Reports built on these axes will mis-bucket real data.

### 5.5 Documents are JSON blobs, not records **[STATIC]**

`applicant_docs`, `guardian_docs`, `traveler_docs`, `guardian_docs` (checkpoint) are JSON in TEXT columns. Consequence: no per-document authorization, no retention, no integrity hash, no audit of an individual document, and no way to revoke access to one file.

### 5.6 Test coverage is concentrated where the risk is not **[STATIC]**

Strong: RBAC module gating, read-only Commander firewall, navigation scoping, print geometry, branch *register* scoping.
Absent: unauthenticated upload access, cross-branch approve/signed-document, suspect-alert scoping, checkpoint fail-open, crime unit operations generally, concurrency, migrations.

---

## 6. Verification status of the historical audit's eight headline concerns

| # | Concern | Status at `a1c2478` | Class |
|---|---|---|---|
| 1 | Uploaded police documents accessible without authentication | **Still present** — `serve_static()` handles `/uploads/` before auth, `:7914` | **[STATIC]** confirmed |
| 2 | Branch-level access-control failures | **Still present** — 7 unscoped routes listed in §5.1 | **[STATIC]** confirmed |
| 3 | Branch scope failing open | **Still present** — `branch_scope_view()` returns `None` on unresolved posting `:2683-2684`; `checkpoint_scope()` returns `''` `:2990` | **[STATIC]** confirmed, and **wider than reported** (the canonical checkpoint role is affected by default) |
| 4 | Administrator self-demotion and lockout | **Still present** — no last-admin or self-demotion guard anywhere | **[STATIC]** confirmed |
| 5 | Password reset not revoking sessions | **Still present** — admin PATCH sets `password_hash` with no session delete; the only `DELETE FROM sessions` statements are logout `:3998` and self-change `:8759` | **[STATIC]** confirmed |
| 6 | Weak password hashing and default credentials | **Still present** — unsalted SHA-256 `:3362`; nine seeded accounts share `ChangeMe123!` `:3304+`, published in `README.md:566` | **[STATIC]** confirmed |
| 7 | Migrations inside application startup, no version tracking | **Still present** — base DDL + `ADDED_COLUMNS` at boot; no `schema_migrations` table | **[STATIC]** confirmed |
| 8 | Inadequate deployment, session and transport security | **Still present** — `sessions` has no expiry column `:446`; no TLS/reverse-proxy artefacts in the repository | **[STATIC]** confirmed |

**Also corrected:** the audit's "23 test suites, 21 passing" is stale. `a1c2478` added two suites, so the tree now holds **25 test files** (12 Python + 13 Node; 23 current + 2 obsolete). The pass/fail outcome was **not re-verified**.

---

## 7. Deliverables index

| # | Deliverable | File |
|---|---|---|
| 1 | CID technical assessment report | **this document** |
| 2 | Fingerprint Unit gap analysis | `assessment/FINGERPRINT_UNIT_GAP_ANALYSIS.md` |
| 3 | Crime Unit requirements proposal | `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` |
| 4 | Checkpoint Unit gap analysis | `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md` |
| 5 | Security remediation priority list | `assessment/SECURITY_REMEDIATION_PRIORITY.md` |
| 6 | Decision register recommendations | `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` |
| 7 | Dependencies and realistic implementation estimates | `assessment/DEPENDENCIES_AND_ESTIMATES.md` §1–§4, §6 |
| 8 | Proposed development order | `assessment/DEPENDENCIES_AND_ESTIMATES.md` §5 — with the 10-day sprint verdict in §7 |

---

## 8. Assessment-level conclusion

The three CID units are **real, coherent and substantially built**. The engineering quality in places is above average for a system at this stage — the double-guarded review lock, the boot-time self-tests, the read-only Commander firewall and the branch-scoped audit history are genuinely good work.

But the release is **not** mostly finished:

1. **Almost nothing in Release 1.0 scope is verified.** One passing suite at this commit. The rest are unrun, and the two riskiest routes have no test at all.
2. **Branch isolation — a mandatory Release 1.0 security control — is incomplete on seven routes** and fails open in two distinct ways.
3. **The Crime Unit's Release 1.0 scope ("full operations including advanced reports") is largely unbuilt**: no assignment, no investigation workflow, no suspect lifecycle, no chain of custody, no defined reports, and no dedicated tests.
4. **The Checkpoint Unit is not "already implemented"** in the Release 1.0 sense: the screening capture is good, but the scoping control that makes it safe fails open on the canonical role, and there is no post-flag workflow.
5. **The Fingerprint Unit's "~80%" is not supportable from the repository** — and the shortfall is concentrated in the biometric half of a biometrics unit, which currently lives in browser `localStorage`.

Detailed per-unit gaps, the Crime Unit requirement proposal, the prioritised security list, decision recommendations, estimates and the sprint verdict are in the companion documents.
