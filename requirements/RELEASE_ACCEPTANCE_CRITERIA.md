# Release 1.0 — Acceptance Criteria

**Phase 3 deliverable H · Criteria only. Nothing in this document has been met yet.**
Branch `arena/6303ef2f-sentinel-police-management` · 2026-11-06

> **The governing rule of this document:** *a feature is not complete merely because its user
> interface exists, and static code inspection is not proof of runtime behaviour.* Every criterion
> below names a **verification method that executes**. A criterion verified by reading code is
> recorded as **not met**.

**Current position, stated honestly:** of the criteria below, **one** is met today — AC-T4, the A4
print contract, proven by an executed passing test. Every other criterion is **not met** or
**not verified**.

**Gate status key:** ☐ not met · ◐ partially met · ☑ met and proven by execution

---

## 1. Functional completeness

### 1.1 Fingerprint Unit *(scope per D-18 = clearance **and** genuine biometrics)*

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-F1 | An applicant can be registered, resolved against the central registry, and the resolution tier recorded | Automated test | ☐ |
| AC-F2 | A Tier 3 / Tier 4 identity match cannot be accepted without a recorded officer confirmation | Negative test | ☐ |
| AC-F3 | A person can be biometrically **enrolled**, and the enrolment survives clearing browser storage and moving workstation | Automated test | ☐ |
| AC-F4 | **1:1 verification** returns match for self and no-match for another | Automated test | ☐ |
| AC-F5 | **1:N identification** returns the enrolled person at rank 1 for their own probe | Automated test against a gallery | ☐ |
| AC-F6 | **1:N returns "no match" for a non-enrolled probe — never a nearest neighbour** | Automated **negative** test | ☐ |
| AC-F7 | **No code path returns a candidate chosen by rotation, position or default** (FPR-902) | Code assertion + negative test | ☐ |
| AC-F8 | Scores between the review and auto-accept thresholds always require human adjudication | Automated test | ☐ |
| AC-F9 | Threshold changes are audited with who, when, from, to and why | Automated test | ☐ |
| AC-F10 | Failed capture (FTA) and failure to enrol (FTE) are recorded outcomes with a usable manual path | Automated test | ☐ |
| AC-F11 | A confirmed **false match** is recorded, reportable, and does not silently disappear | Automated test | ☐ |
| AC-F12 | A clearance application can be **rejected** with a reason code | Automated test | ☐ |
| AC-F13 | The submitter cannot approve their own application | Negative test | ☐ |
| AC-F14 | Review-gate bypasses are explicit, reasoned and recorded in a **queryable** field | Automated test | ☐ |
| AC-F15 | Certificate numbers are unique under 100 concurrent approvals | Concurrency test | ☐ |
| AC-F16 | Absence of a scanner degrades to the documented manual path and never to a fabricated result | Negative test | ☐ |

### 1.2 Crime Unit

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-C1 | A case can be registered with a validated category and a unique, year-correct identifier | Automated + concurrency test | ☐ |
| AC-C2 | An incident can be recorded and **linked to a case**, with reason and audit *(subject to D-15)* | Automated test | ☐ |
| AC-C3 | A case can be **assigned**, reassigned and unassigned, with full history | Automated test | ☐ |
| AC-C4 | Investigative actions are **append-only**; corrections are audited amendments that preserve the original | Negative test | ☐ |
| AC-C5 | A case timeline reconstructs the full history in order | Automated test | ☐ |
| AC-C6 | **Free-text status is refused**; illegal transitions are refused and audited | Negative test | ☐ |
| AC-C7 | Closure requires authorisation and a reason, and sets `closed_at` | Automated test | ☐ |
| AC-C8 | Participants (suspect / victim / witness / complainant) are recorded as participants, **not as "suspect alerts"** | Automated test | ☐ |
| AC-C9 | An alert can be **cleared**, and clearing stops checkpoint flagging within one request cycle | Automated test | ☐ |
| AC-C10 | Evidence carries a SHA-256 hash that re-verifies against the stored bytes | Automated test | ☐ |
| AC-C11 | Every evidence access is recorded in a custody log | Automated test | ☐ |
| AC-C12 | Evidence can be **withdrawn** with an audited reason; it is never silently deleted | Automated test | ☐ |
| AC-C13 | Server-side filtering and pagination exist and never widen scope | Automated + negative test | ☐ |
| AC-C14 | **A Crime Unit test suite exists and passes** — there is none today | CI run | ☐ |

### 1.3 Checkpoint Unit

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-K1 | A screening event can be recorded, and the officer can record the **actual** outcome, including disagreement with the automatic result | Automated test | ☐ |
| AC-K2 | An event can be opened individually (`GET` by id) and corrected by audited amendment | Automated test | ☐ |
| AC-K3 | A checkpoint **operation / shift** can be opened, populated and closed with a summary | Automated test | ☐ |
| AC-K4 | A checkpoint **incident** unrelated to any person screening can be recorded | Automated test | ☐ |
| AC-K5 | A **detention** records legal basis, start, a duration clock, escalation and outcome | Automated test | ☐ |
| AC-K6 | A **referral** is tracked through to acknowledgement and outcome | Automated test | ☐ |
| AC-K7 | A **false match** is recorded, reportable, and suppresses re-flagging pending supervisory review | Automated + negative test | ☐ |
| AC-K8 | An incident can be escalated to a crime case, audited at both ends | Automated test | ☐ |
| AC-K9 | Shift totals reconcile with the underlying screening records | Automated test | ☐ |

### 1.4 Reporting

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-R1 | Every Release 1.0 report in the approved catalogue is implemented, **branch-scoped**, filterable and drillable | Automated test per report | ☐ |
| AC-R2 | A scoped officer's report totals **equal** the count of records they can actually access | Automated test | ☐ |
| AC-R3 | Report arithmetic is pinned by tests | Automated test | ☐ |
| AC-R4 | Export is audited with the filters applied | Automated test | ☐ |
| AC-R5 | Drill-down uses the same scoped list endpoint and cannot leak | Negative test | ☐ |
| AC-R6 | Small-cell suppression is applied to demographic reports | Automated test | ☐ |

---

## 2. Role and branch isolation

> **These criteria are non-negotiable and all are release-blocking.**
> Every isolation test must assert on **record identifiers, not counts** — a count-based test passes
> when both officers see zero rows.

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-I1 | **Every** read and write endpoint enforces branch or location scope | Negative test per endpoint | ☐ |
| AC-I2 | An unresolvable posting returns **403** and never a national dataset | Negative test | ☐ |
| AC-I3 | A **blank** location scope **denies**; the system refuses to start with a blank-scope role | Startup assertion + negative test | ☐ |
| AC-I4 | Legacy and canonical checkpoint roles grant **identical** access for the same posting | Parity test | ☐ |
| AC-I5 | Cross-branch approve, signed-document upload, case PATCH, evidence upload and alert creation all return 403 and are audited | Negative test ×5 | ☐ |
| AC-I6 | `GET /api/suspect-alerts` is branch-isolated | Negative test | ☐ |
| AC-I7 | Analytics are branch-scoped in **every** builder | Automated test | ☐ |
| AC-I8 | Modules outside a role's set are unreachable **at the API**, not only hidden in the UI | Negative test | ☐ |
| AC-I9 | `chief_commander` can read across branches and write nothing | Negative test | ☐ |
| AC-I10 | A filter can narrow scope but never widen it | Negative test | ☐ |
| AC-I11 | No endpoint returns a record the caller could not retrieve individually | Negative test | ☐ |

---

## 3. Biometric correctness and safety

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-B1 | Measured **FAR/FRR** at the configured operating point is documented and formally accepted (D-34) | Accuracy report | ☐ |
| AC-B2 | Templates and images are **encrypted at rest**, with documented key management and a rehearsed rotation | Config review + rehearsal | ☐ |
| AC-B3 | **No biometric data exists in browser storage** after capture | Negative test | ☐ |
| AC-B4 | **No role — including `SystemAdmin` and `chief_commander` — can bulk-export templates or images** | Negative test per role | ☐ |
| AC-B5 | Every template or image read is individually audited | Automated test | ☐ |
| AC-B6 | Biometric endpoints never return template bytes to a general-purpose client | Negative test | ☐ |
| AC-B7 | The capture bridge is reachable on **loopback only** and its protocol version is validated | Negative test | ☐ |
| AC-B8 | Biometric retention is enforced with automated expiry and audited deletion (D-04) | Automated test | ☐ |
| AC-B9 | Re-enrolment creates a new version and never overwrites a prior template | Automated test | ☐ |
| AC-B10 | A biometric identification can be traced end-to-end afterwards: probe, candidates, scores, threshold, decision, officer | Automated test | ☐ |

---

## 4. Data protection

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-D1 | **No document is retrievable without an authenticated, authorized, audited request** | Negative test + penetration test | ☐ |
| AC-D2 | All uploads are validated for extension, MIME and size, with sanitised filenames | Negative test | ☐ |
| AC-D3 | No account has a default, shared or seeded password in any reachable environment | Negative test | ☐ |
| AC-D4 | Passwords are salted and iterated; two users with the same password have different hashes | Automated test | ☐ |
| AC-D5 | All traffic uses TLS; cookies carry `Secure`, `HttpOnly`, `SameSite` | Config review + test | ☐ |
| AC-D6 | Sessions expire (idle and absolute) and can be revoked | Automated test | ☐ |
| AC-D7 | Privilege changes revoke existing sessions immediately | Negative test | ☐ |
| AC-D8 | The last administrator cannot be deleted, demoted or deactivated | Negative test | ☐ |
| AC-D9 | Authentication is rate-limited and all auth events are audited | Automated test | ☐ |
| AC-D10 | The audit trail is **append-only** — the application role cannot UPDATE or DELETE an audit row | Negative test | ☐ |
| AC-D11 | Updates record **before and after** values | Automated test | ☐ |
| AC-D12 | Authorization **denials** are audited | Automated test | ☐ |
| AC-D13 | The database uses a least-privilege role and encryption at rest | Config review | ☐ |
| AC-D14 | A DPIA covering biometric and criminal data is signed off (D-05) | Signed document | ☐ |
| AC-D15 | Retention periods are implemented and enforced (D-04) | Automated test | ☐ |

---

## 5. Testing

> **This section gates every other section in this document.**

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-T1 | **A runnable test environment exists** — all 25 existing suites can be executed | Full-suite run | ☐ |
| AC-T2 | **All existing suites pass.** 23 have never been executed, so their true state is unknown — *"not run"*, never *"passing"* | Full-suite run | ☐ |
| AC-T3 | CI executes the full suite on every change | CI config + run evidence | ☐ |
| AC-T4 | The A4 print contract passes (`backend/test_print_fit.py`) | Executed 2026-11-06 | **☑ met** |
| AC-T5 | Every release-blocking security requirement has an executed **negative** test | Coverage review | ☐ |
| AC-T6 | Isolation tests assert on record identifiers, not counts | Test review | ☐ |
| AC-T7 | A Crime Unit test suite exists | CI run | ☐ |
| AC-T8 | Concurrency tests cover identifier generation | CI run | ☐ |
| AC-T9 | The eight proven test gaps are closed *(see `requirements/SECURITY_REQUIREMENTS.md` §6.1)* | Coverage review | ☐ |
| AC-T10 | `python3 backend/server.py --ui-check` exits 0 | Executed 2026-11-06 | **☑ met** |

---

## 6. Backup and recovery

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-V1 | Automated backups run on a defined schedule | Config review | ☐ |
| AC-V2 | **A restore has been rehearsed into a clean environment, with recorded evidence** | Rehearsal record | ☐ |
| AC-V3 | Measured RPO and RTO meet the agreed targets (D-08) | Rehearsal record | ☐ |
| AC-V4 | Backups containing biometric or document data inherit the same encryption and access rules | Config review | ☐ |
| AC-V5 | Uploaded documents are included in backup and restore — not only the database | Rehearsal record | ☐ |
| AC-V6 | Point-in-time recovery is available or its absence is formally accepted | Config review | ☐ |

---

## 7. Deployment readiness

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-P1 | **Versioned, reversible migrations exist; no DDL runs as an application startup side effect** | Automated test | ☐ |
| AC-P2 | Dependency manifests are pinned (`requirements.txt`, `package.json`) | Build from clean checkout | ☐ |
| AC-P3 | A clean environment can be built from the repository in a documented, repeatable way | Clean-build rehearsal | ☐ |
| AC-P4 | Dead code is removed (`backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`) | Code review | ☐ |
| AC-P5 | Configuration is externalised; no secret is committed | Secret scan | ☐ |
| AC-P6 | Health monitoring and structured logging detect an outage | Operational test | ☐ |
| AC-P7 | A rollback procedure exists and has been rehearsed | Rehearsal record | ☐ |
| AC-P8 | **The bridge service is packaged and deployable to every capture workstation** (D-32) | Deployment rehearsal | ☐ |
| AC-P9 | Scanner hardware is procured, allocated and accepted (D-31) | Acceptance record | ☐ |
| AC-P10 | An independent security review or penetration test is complete and its findings are closed or formally accepted | Review report | ☐ |

---

## 8. Operational documentation

| ID | Criterion | Proof | Status |
|---|---|---|---|
| AC-O1 | Role and permission documentation matches the implemented matrix | Review against tests | ☐ |
| AC-O2 | Officer procedures exist for each unit, including the **manual paths** (failed capture, scanner outage, detention, referral, false match) | Review | ☐ |
| AC-O3 | An administrator guide covers user, role, branch and location administration | Review | ☐ |
| AC-O4 | Runbooks exist for backup, restore, rollback and incident response | Review | ☐ |
| AC-O5 | **Demo credentials are removed from all documentation** (`README.md:566`) | Document scan | ☐ |
| AC-O6 | A data-protection notice and retention schedule are published | Review | ☐ |
| AC-O7 | Known limitations are documented — including any report whose quality is constrained by free-text data | Review | ☐ |
| AC-O8 | Training material covers what the biometric system **does not** guarantee: a match is evidence, not proof | Review | ☐ |

---

## 9. Release gate

**Release 1.0 may be declared ready only when all of the following hold:**

1. Every criterion in **§2 (isolation)**, **§3 (biometric safety)**, **§4 (data protection)** and
   **§5 (testing)** is **☑ met and proven by execution**.
2. All **27 release-blocking security requirements** in `requirements/SECURITY_REQUIREMENTS.md` §8
   are satisfied and verified.
3. §1 functional criteria are met for the **approved** scope of each unit.
4. §6 backup/recovery and §7 deployment readiness are satisfied.
5. §8 operational documentation is complete.
6. Every **release-blocking decision** in `DECISION_REGISTER.md` is **closed**, not merely noted.
7. No criterion is marked met on the basis of code inspection alone.

**Not grounds for declaring readiness:** a working user interface · a passing demo · the original
10-day window · a feature being "mostly done" · a test suite that exists but has not been executed.

> **No date is committed in this document.** A date can only follow from the decisions in
> `DECISION_REGISTER.md` §3 and §4 and the procurement items in `planning/IMPLEMENTATION_ROADMAP.md`.
