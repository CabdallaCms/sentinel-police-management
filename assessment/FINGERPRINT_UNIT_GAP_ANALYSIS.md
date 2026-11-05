# Fingerprint Unit — Gap Analysis

**Deliverable 2 of 8 · Phase 2 · Assessment only.**
Branch `arena/6303ef2f-sentinel-police-management` · commit `a1c2478` · 2026-11-06
Evidence classes: **[STATIC]** code read at `a1c2478` · **[RUNTIME-2026-11-06]** executed here · **[RUNTIME-HISTORICAL]** PR #23 at `381545c` · **[NOT VERIFIED]**

---

## 1. The headline question: is the Fingerprint Unit ~80% complete?

**The owner-reported "~80%" cannot be supported or refuted from the repository, and the figure is not adopted.** What the repository does support:

| Observation | Evidence |
|---|---|
| The **clearance-certificate half** of the unit is built end to end — intake, review gate, signed scan, approval, certificate, print contract | §2 below **[STATIC]**, print contract **[RUNTIME-2026-11-06]** |
| The **biometric half** is a browser-local prototype — capture UI exists, storage is `localStorage`, matching is client-side, and **no server-side biometric storage or matching exists at all** | §4.1 **[STATIC]** |
| **Verified** functionality is one feature area (the A4 print contract) | §6 **[RUNTIME-2026-11-06]** |

A unit named "Fingerprint" whose fingerprints are not stored on the server is not 80% complete in any sense the owner would recognise — **unless** the owner's definition of this unit is "police clearance certificate processing", in which case the figure is plausible. **This is the single most important clarification needed: see decision D-18.**

---

## 2. What exists and works (by code reading)

| # | Capability | Location | Class |
|---|---|---|---|
| F-01 | Clearance application intake (multipart + JSON), 4-part name, NID-or-passport requirement | `server.py:8943-8961` | Implemented but not verified |
| F-02 | Five mandatory purposes, case-insensitive, legacy values mapped, 400 otherwise | `CLEARANCE_REASONS:649`; `normalise_reason():8958` | Implemented but not verified |
| F-03 | Guardian/guarantor block captured and required | `:8970`; DDL `:265` | Implemented but not verified |
| F-04 | ≥2 applicant documents, ≥2 guardian documents enforced server-side | `:8969-8972` | Implemented but not verified |
| F-05 | Central Person auto-create or fill-only enrichment, with `CREATE`/`ENRICH` audit rows | `ensure_person():8964` | Implemented but not verified |
| F-06 | 12-hour review gate, `Citizenship` exempt, SystemAdmin bypass, **double-guarded** | `review_gate_decision():9039` + inline guard `:9050-9066` | Implemented but not verified |
| F-07 | Server refuses to boot if the review gate is disarmed | `review_lock_armed():1057`, enforced `:10022` | Implemented but not verified |
| F-08 | Signed-scan upload, additively versioned, **extension allow-list + 20 MB cap** | `:9009-9031`; `clearance_signed_documents:281` | Implemented but not verified |
| F-09 | Approval sets status, certificate number, `reviewed_at`, audit row recording bypass | `:9067-9080` | Implemented but not verified |
| F-10 | Certificate print lock — signed scan required unless admin | `certificate_print_state()`, used `:8227`,`:8258` | Implemented but not verified |
| F-11 | A4 print contract for `application.html` and `certificate.html` | `test_print_fit.py` | **Implemented and verified** **[RUNTIME-2026-11-06]** |
| F-12 | Branch-scoped register read and single-record read (403 cross-branch) | `:8201`, `:8244` | Implemented but not verified |
| F-13 | Branch-scoped create | `:8952` | Implemented but not verified |
| F-14 | Module gate `fingerprint` on GET and POST | `:8099`, `:8872` | Implemented but not verified |
| F-15 | Branch-scoped per-record audit history | `:4281` | Implemented but not verified |

---

## 3. Gaps that are **inside** Release 1.0 scope

### 3.1 Security gaps (blocking)

| # | Gap | Evidence | Class | Priority |
|---|---|---|---|---|
| **FG-01** | **Clearance documents are retrievable without authentication.** `/uploads/<file>` is served by `serve_static()`, which `do_GET` calls before any auth. Applicant photographs, national ID scans, passport scans and signed clearance sheets are affected. | `server.py:7914`; `do_GET` entry `:7946` | **[STATIC]** confirmed; **[RUNTIME-HISTORICAL]** reproduced (C-1) | **P0** |
| **FG-02** | **Cross-branch approval.** `POST /api/clearance-applications/<id>/approve` performs no branch check. A Fingerprint officer posted to branch A can approve branch B's application and mint its certificate — while being correctly refused `403` on *reading* it. | `:9032-9080` has no `require_record_branch_scope`; contrast `:8244` | **[STATIC]** confirmed; **[RUNTIME-HISTORICAL]** reproduced (H-2) | **P0** |
| **FG-03** | **Cross-branch signed-scan attachment.** Same omission on `/signed-document`. | `:8997-9031` | **[STATIC]** confirmed | **P0** |
| **FG-04** | **Cross-branch document listing.** `GET /api/persons/<id>/documents` aggregates a person's unit documents with no branch check and no module gate (the `/api/persons` prefix is open to every authenticated session). | `:8152` | **[STATIC]** | **P1** |
| **FG-05** | **Applicant and guardian uploads are unvalidated.** `save_upload()` sanitises the filename and strips the path, but applies **no extension, MIME or size check** — unlike `/signed-document`, which does. | `:3939-3946` vs `:9009-9018` | **[STATIC]** | **P1** |
| **FG-06** | **No separation of duties.** The approve route never compares the approver to `created_by`. The submitting officer can approve their own application. | `:9032-9080` | **[STATIC]** | **P1**, gated on **D-12** |
| **FG-07** | **`Citizenship` bypasses the review window entirely**, by stored purpose, for any Fingerprint officer. | `citizenship_wait_exempt()` used `:9048`,`:9060` | **[STATIC]** | **P2**, gated on **D-06** |
| **FG-08** | **Identifier collision risk.** `FP-` and `CL-` ids are the last 8 digits of epoch milliseconds; two submissions in the same millisecond collide against the UNIQUE constraint and the second fails. | `:8975`, `:9067` | **[STATIC]** | **P2** |

### 3.2 Functional gaps (in scope, must be decided then built)

| # | Gap | Evidence | Class |
|---|---|---|---|
| **FG-09** | **No rejection path.** The API can only move an application to `Approved`. There is no reject, no decline-with-reason, no return-for-correction, no resubmission. The fingerprint analytics chart nonetheless plots a `Rejected` axis that no endpoint can produce. | no reject route; `:6112`, `:6124` | **Not implemented** |
| **FG-10** | **Only two reachable statuses** (`Pending Review`, `Approved`). No `Under Review`, no `On Hold`, no `Expired`. | `:274`, `:9068` | **Not implemented** |
| **FG-11** | **No structured search or filtering.** The register has one client-side free-text box; no server-side query parameters (purpose, status, date range, branch, officer). | `index.html` `#fingerprint`; `:8197` takes no query params | **Not implemented** |
| **FG-12** | **No certificate verification.** The certificate states six months' validity, but nothing records expiry, and no third party can verify a printed certificate. | `certificate.html`; no verification route | **Not implemented**, gated on **D-10** |
| **FG-13** | **Documents are JSON blobs, not rows.** `applicant_docs` / `guardian_docs` are JSON in TEXT columns, so no per-document authorization, retention, integrity hash or audit is possible. | DDL `:273` | **Partially implemented** |
| **FG-14** | **Fingerprint analytics are not branch-scoped.** `cid_fingerprint_analytics(c)` takes no user; a branch-scoped officer sees national totals, match rates and suspect-hit rates. | `:6071`, called `:6318` | **Partially implemented** |
| **FG-15** | **No unit-chief / supervisor role.** One role (`FingerprintUnit`) does intake, review and approval, so no supervisory control can be expressed. | `ROLE_MODULES:1871` | **Not implemented**, gated on **D-12** |

### 3.3 Biometric gaps — the largest cluster

| # | Gap | Evidence | Class |
|---|---|---|---|
| **FG-16** | **Biometric captures are stored in the browser.** `biometricStore` is read from and written to `localStorage` under `sentinelBiometrics`; it ships with hard-coded demo entries (`DEFAULT_BIOMETRICS`). Nothing is sent to the server. | `index.html:2698-2725` | **Partially implemented** |
| **FG-17** | **No server-side biometric storage.** No template column, no biometric table, nothing in the DDL. | `server.py` DDL; no match for `template`/`minutiae`/`biometric` column | **Not implemented** |
| **FG-18** | **Matching is client-side and non-biometric.** `matchPersonByFingerprint()` compares normalised **strings** (person id, "biometric hash", filename, NID, passport) against the browser's local `db.people`. It is identifier matching, not fingerprint matching. | `index.html:4526-4560`; `db` from `localStorage` `:2641` | **Partially implemented** |
| **FG-19** | **The local USB bridge service is not in this repository.** The page calls `http://127.0.0.1:<port>/scan` and `ws://localhost:<port>/biometrics`. Whatever answers those is an external component with no source, no version, no installer and no security review here. | `index.html:4773-4774, 5183, 5269` | **Blocked** on **D-18** |
| **FG-20** | **The server's "biometrics logged" metric is not biometric.** `total_biometrics_logged` counts clearance applications; `identity_match_rate` is `(applications − distinct persons) / applications`. These are application metrics labelled as biometric ones. | `:6071-6108` | **Partially implemented** |
| **FG-21** | **No biometric data policy.** Retention, encryption at rest, lawful basis, DPIA and cross-branch visibility for biometric data are undefined. | — | **Blocked** on **D-04 / D-05** |

---

## 4. Test gap analysis

### 4.1 What exists

| Suite | Covers | Result at `a1c2478` |
|---|---|---|
| `test_print_fit.py` | A4 geometry, blueprint fidelity, DOM bindings, emblem, height budgets | **PASS** **[RUNTIME-2026-11-06]** |
| `test_review_gate.py` | 12-hour gate, 6 scenarios including survival across restart | **NOT RUN** |
| `test_field_level_rbac.py` | field-level 403, print lock, photo attachment | **NOT RUN** |
| `test_branch_scope.py` | register + single-record branch scoping (28 fingerprint references) | **NOT RUN** |
| `test_approval_flow.mjs` | approval front end | **NOT RUN** |
| `test_clearance_rbac_ui.mjs` | purpose chip, document viewer, print lock | **NOT RUN** |
| `test_record_audit_ui.mjs` | record audit drawer | **NOT RUN** |

### 4.2 What is missing entirely **[STATIC]**

| Required test | Currently |
|---|---|
| Anonymous `GET /uploads/<clearance document>` must return 401/403 | **No suite requests an upload URL anonymously** |
| Cross-branch `POST …/approve` must return 403 | **`test_branch_scope.py` contains zero references to `approve`** |
| Cross-branch `POST …/signed-document` must return 403 | **Zero references to `signed-document`** |
| Cross-branch `GET /api/persons/<id>/documents` must be filtered | None |
| Submitter cannot approve own application | None |
| Upload of a disallowed type/oversized file to applicant docs must be rejected | None |
| Concurrent submissions must not collide on `FP-`/`CL-` ids | None |
| Fingerprint analytics must be branch-scoped | None |

---

## 5. Integration dependencies

| Dependency | Direction | Risk |
|---|---|---|
| Central Person Registry (`ensure_person`, fill-only enrichment) | Fingerprint → shared | Shared with Crime, Checkpoint, Airport — changes ripple |
| `police_branches` scoping helpers | Fingerprint → shared | Fixing FG-02/03 touches shared helpers used by all units |
| `users` (attribution, badge, role) | Fingerprint → shared | Separation of duties (FG-06) needs a role change |
| `audit_events` | Fingerprint → shared | — |
| Uploads directory | Fingerprint → shared | Fixing FG-01 affects **every** unit's documents at once |
| `suspect_alerts` (Crime Unit) | Fingerprint ← Crime | Read-only, for the analytics hit-rate |
| `application.html` / `certificate.html` | Fingerprint → own | Pinned by `test_print_fit.py`; changes must keep it passing |
| External USB bridge on the officer's PC | Fingerprint → external | Not in repo; unversioned; **D-18** |

---

## 6. Classification roll-up

| Class | Count | Items |
|---|---|---|
| **Implemented and verified** | 1 | F-11 |
| **Implemented but not verified** | 9 | F-01…F-10, F-12…F-15 (grouped areas) |
| **Partially implemented** | 5 | FG-05 (upload validation — present only on `/signed-document`) · FG-13 (document model) · FG-14 (analytics scoping) · FG-16 (biometric capture storage) · FG-18 + FG-20 (client-side matching and the "biometrics logged" metric that counts applications) |
| **Not implemented** | 6 | FG-09 (rejection path) · FG-10 (status model) · FG-11 (server-side search) · FG-12 (certificate verification) · FG-15 (supervisor role) · FG-17 (server-side biometric storage) |
| **Blocked** | 2 | FG-19 (**D-18**), FG-21 (**D-04/D-05**) |

---

## 7. Recommended close-out order for this unit

> Order only. **No work is authorised until the owner approves.**

1. **FG-01** authenticated document retrieval (shared fix — also closes the same hole for Crime and Checkpoint).
2. **FG-02 / FG-03** branch isolation on approve and signed-document, with the two negative tests that do not exist today.
3. **FG-04** scope `GET /api/persons/<id>/documents`.
4. **FG-05** apply the `/signed-document` validation pattern to applicant and guardian uploads.
5. **FG-14** pass `user` into `cid_fingerprint_analytics` and scope it.
6. **D-18 decision**, then plan the biometric gaps FG-16…FG-20 as a *distinct* work package. This is where the unmeasured remainder of the unit actually sits, and it may be larger than everything above it combined. **No percentage is asserted** — the work is unestimable until D-18 is answered.
7. **D-12 decision**, then FG-06 / FG-15 (separation of duties and roles).
8. **FG-09 / FG-10** rejection path and status model — needed before the unit can be called operationally complete.
9. **FG-11** structured search.
10. **D-06** then FG-07; **D-10** then FG-12.

---

## 8. New decisions raised by this unit

| ID | Decision needed |
|---|---|
| **D-18** | **What is the Fingerprint Unit's Release 1.0 definition?** (a) clearance-certificate processing only, with biometrics deferred to a later release, or (b) genuine biometric capture, server-side storage and matching. If (b): which scanner hardware and SDK, who owns the local bridge service, where do templates live, and what is the matching standard? This decision alone can double or halve the unit's remaining work. |
| **D-19** | Must a clearance decision be **rejectable**, and by whom, with what reason codes and what applicant notification? (Needed before FG-09.) |
