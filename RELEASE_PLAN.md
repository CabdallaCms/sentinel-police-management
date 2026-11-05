# RELEASE_PLAN.md — Sentinel Police Management System

**Approved release structure.** This document defines *what* each release contains and *what must be
true* before it is accepted. It deliberately does **not** define a delivery schedule.

| Field | Value |
|---|---|
| Project | Sentinel Police Management System |
| Repository | `CabdallaCms/sentinel-police-management` |
| Current release | **CID Release 1.0** |
| Baseline branch | `arena/6303ef2f-sentinel-police-management` |
| Baseline commit | `a1c2478262776e9f20b4c3ad806eaa86adc27792` |
| Document created | 2026-11-06 |
| Change authority | **Project owner only** (`PROJECT_CONTEXT.md` §13) |

---

## 1. CID Release 1.0 — scope

**CID Release 1.0 contains exactly three operational units plus the shared functionality required for
their operation.** This statement is identical to `PROJECT_CONTEXT.md` §3 and `PROJECT_STATUS.md` §2.

### 1.1 In scope

| # | Item | Included |
|---|---|---|
| **A** | **Fingerprint Unit** | Yes |
| **B** | **Crime Unit — full operations, including advanced reports** | Yes |
| **C** | **Checkpoint Unit** | Yes |
| **S** | **Shared functionality required by A, B and C** | Yes |

### 1.2 Shared functionality in scope (only as required by A, B and C)

- Central Person Registry and the identity-resolution engine
- Authentication and session management
- Roles, permissions and **server-side** authorization
- **Branch-level data isolation**
- Audit logging for the three units' operations
- Document and attachment handling for the three units
- Branch Management, to the extent the three units depend on it
- Application shell, navigation and dashboard, to the extent the three units depend on them
- Database, migration, backup/restore and deployment foundations for the three units

### 1.3 Out of scope for Release 1.0

- **Airport Unit** — postponed to **CID Release 1.1** (§4)
- Unrelated police department modules
- Unnecessary HQ administration expansion
- Any feature not explicitly approved by the project owner

### 1.4 Binding scope rules

1. **The Crime Unit must not be reduced to basic case registration to meet a date.** Advanced reports
   are part of Release 1.0.
2. **Existing functionality must be inspected before missing work is identified.**
3. **Requirements, workflows, user roles, permissions and reports must be documented and approved
   before Crime Unit implementation begins.**
4. **No feature is added without explicit owner approval.**
5. Modules already implemented but outside Release 1.0 are **frozen** — not extended, not redesigned,
   not deleted (`PROJECT_CONTEXT.md` §3.3).

---

## 2. Unit scope detail

### 2.1 Fingerprint Unit (Unit A)

**Included in Release 1.0:** the clearance/fingerprint register and its full operational lifecycle —
application intake, applicant and guardian data, document attachments, the mandatory review gate,
approval, certificate number generation, and the printable application and certificate documents —
operated under role-based access control and branch-level data isolation.

**Current state:** substantial implementation exists; completeness is **Not yet verified**
(`PROJECT_STATUS.md` §2.1). The owner-reported "~80%" figure is recorded as an owner report and is
**not** adopted as a measured fact.

**Release 1.0 requires:** an assessment of actual implementation status and outstanding work, then
completion and verification of the gap — including closure of the branch-isolation and document-access
concerns affecting this unit.

### 2.2 Crime Unit (Unit B) — full operations, including advanced reports

**Included in Release 1.0:** full Crime Unit operations. At minimum, and subject to the owner's
requirement specification:

- Incident/case intake and registration
- Case management and case status lifecycle
- Participants and suspect handling, including suspect alerts with optional case linkage
- Evidence and media storage, with custody expectations
- Case search and retrieval
- **Advanced reports** — scope to be specified by the owner (**decision D-14**)
- Role-based permissions specific to Crime Unit operations
- Branch-level data isolation across every Crime Unit operation
- Audit coverage of Crime Unit actions

**Current state:** core data model and the case workspace exist; the Release 1.0 requirement set is
**undefined and unassessed** (`PROJECT_STATUS.md` §2.2).

**Release 1.0 requires, in order:**
1. Owner-approved requirements, workflows, roles, permissions and **report definitions**;
2. inspection of existing functionality;
3. identification of missing work;
4. implementation and verification.

**Blocking decisions:** **D-14** (what "advanced reports" means) and **D-15** (the intended
relationship between `crime_cases` and `crime_incidents`).

### 2.3 Checkpoint Unit (Unit C)

**Included in Release 1.0:** checkpoint screening operations end to end — traveller/vehicle screening
events, screening results and actions taken, location-isolated access, integration with the Central
Person Registry and suspect alerts, and audit coverage.

**Current state:** the owner reports it as already implemented; that report is **unverified**
(`PROJECT_STATUS.md` §2.3).

**Release 1.0 requires a formal verification pass covering:** workflows · permissions · security ·
branch and location isolation (including the reported `location_scope`-widening concern) ·
integration · audit · defect list. Any gap found becomes Release 1.0 work.

---

## 3. Shared functionality — Release 1.0 acceptance focus

Shared work is in scope **only where the three units depend on it**. The following are the shared
areas Release 1.0 must address:

| Area | Release 1.0 expectation |
|---|---|
| Server-side authorization | Enforced on the server for every Release 1.0 operation; the UI is presentation only |
| Branch-level data isolation | Enforced on reads **and** writes, including approval, attachment, download and audit-history routes; **fail closed** on unresolved branch identity |
| Document/attachment protection | Authentication and authorization enforced on retrieval |
| Authentication and sessions | Secure password hashing; session expiry and revocation; no default credentials in any shared environment |
| Audit logging | Important actions recorded, including authentication events |
| Data integrity | Safe identifier generation under concurrency; transactional multi-table writes |
| Migrations | Versioned, ordered, recorded, not a side effect of booting the web process |
| Backup and restore | Defined, automated and **proven by a tested restoration** |
| Deployment and rollback | Documented procedures, rehearsed before production |

---

## 4. Airport Unit — postponed to CID Release 1.1

- The **Airport Unit is not part of CID Release 1.0.** It is reserved for **CID Release 1.1**.
- Airport functionality **already exists in the codebase** and is **frozen** for Release 1.0: do not
  implement, expand, redesign or add Airport features; do not delete the existing code.
- If a Release 1.0 change to shared code necessarily affects the Airport Unit, the change must be
  minimal, its Airport impact must be stated explicitly in the task report, and it must not be used as
  a basis for extending Airport functionality.
- **Open decision D-16:** whether the Airport module is enabled or hidden in the Release 1.0 build.
- **CID Release 1.1 scope is not yet defined** beyond "Airport Unit", and will be specified and
  approved by the owner when Release 1.0 is accepted.

---

## 5. Release acceptance principles

**A release is accepted only when every principle below is satisfied and the owner explicitly approves.**

1. **Completeness.** All approved scope for the release is implemented. Nothing approved is silently
   dropped.
2. **Verification, not assertion.** Every "done" claim is backed by recorded evidence: what was run,
   against which commit, and what the output was.
3. **No unverified feature is presented as complete.** Unassessed work is labelled
   **"Not yet verified."**
4. **No invented progress.** Percentages appear only when measured, with the method stated.
5. **Security is a gate, not a preference.** No open Critical or High security finding may remain
   unaccepted at release. Acceptance of any residual risk is the owner's explicit, recorded decision.
6. **Data integrity is a gate.** No release with known data-loss, data-corruption or cross-branch
   data-leak defects.
7. **Defects are disclosed.** Every known defect is listed with severity; none is hidden to protect a
   date.
8. **Dates move before scope or quality does.** If the work does not fit the date, the date moves.
9. **Documentation is part of the release.** `PROJECT_STATUS.md` and `CHANGELOG.md` are current at the
   moment of acceptance.
10. **Rollback is understood.** The release states how to roll it back, including the database, before
    it is promoted.

---

## 6. Functional testing requirements

**For every Release 1.0 unit:**

1. **Workflow coverage.** Each approved workflow has at least one end-to-end test exercising the real
   API — not a UI mock alone.
2. **Role coverage.** Each role that touches the unit has a positive test (it can do what it should)
   **and** a negative test (it cannot do what it should not).
3. **Validation coverage.** Required fields, constrained value sets and business rules are tested for
   both acceptance and rejection.
4. **Report coverage** (Crime Unit). Each approved advanced report has a test asserting its data
   correctness, filtering and permission gating.
5. **Regression protection.** Every fixed defect gets a test that **fails before the fix and passes
   after it**.
6. **Obsolete suites are retired or rewritten**, so that "all tests pass" is a meaningful statement.
   At baseline, two SQLite-era harnesses are obsolete (`backend/test_server.py`,
   `backend/test_conduct_frontend.mjs`).
7. **Synthetic data only.** Tests never use real police records, and never run against a database
   holding them.
8. **Results are recorded exactly** — suite, outcome, counts, and the commit tested. A suite that
   cannot be run is reported as **not run**, never as passing.

---

## 7. Security requirements for release

Release 1.0 is measured against the mandatory security principles in `PROJECT_CONTEXT.md` §7.1
(**S-01 … S-16**). The following are the specific security gates for this release:

| Gate | Requirement |
|---|---|
| **G-1** | Authorization is enforced **server-side** for every Release 1.0 operation, and **denies by default**. |
| **G-2** | **Branch-level data isolation** is enforced on all relevant operations — including approval, attachment, document download and audit-history routes. |
| **G-3** | **Unresolved branch identity never grants broader access** (fail closed). |
| **G-4** | **Uploaded documents and attachments are protected** by authentication and authorization. |
| **G-5** | **Secure password hashing** (salted, slow) is in use; no default or shared credentials exist in any environment that holds non-synthetic data. |
| **G-6** | **Session expiration and revocation** are implemented, including revocation on password reset, role change and deactivation. |
| **G-7** | **Privilege escalation is prevented**, including self-escalation and last-administrator lockout. |
| **G-8** | **Audit logs** cover important actions, including authentication events. |
| **G-9** | **Sensitive police records are protected** from unauthorized access, including by guessed identifiers. |
| **G-10** | **Only synthetic data** is used in development and staging. |
| **G-11** | **No credentials, tokens or sensitive records** appear in reports, logs, tests or documentation. |
| **G-12** | **Negative tests exist** proving each of G-1 … G-9 is actually refused by the server. |

**Each gate must be demonstrated, not asserted.** A gate without a negative test is not closed.

**Security findings outstanding at baseline** (`PROJECT_STATUS.md` §6) are inherited by Release 1.0 and
must each be either remediated and verified, or explicitly accepted in writing by the owner.

---

## 8. Integration requirements

Release 1.0 must verify, with tests:

1. **Central Person Registry linkage** — Fingerprint, Crime and Checkpoint records resolve to and
   reference one central `Person ID`, with the documented matching tiers.
2. **Fill-only enrichment** — linking a unit record to an existing person fills empty central fields
   and **never overwrites existing non-null data**.
3. **Cross-unit interactions in scope** — in particular suspect alerts raised by the Crime Unit and
   consumed at checkpoints.
4. **Shared services are reused, not duplicated** — users, permissions, audit logs and branch
   management have one implementation (`PROJECT_CONTEXT.md` §6.7).
5. **Branch isolation holds across integrations** — a cross-unit path must not become a way around
   branch scoping.
6. **Audit continuity** — an action that spans units produces a coherent, attributable audit trail.
7. **Out-of-scope modules are unaffected** — changes to shared code do not alter Airport, Stations,
   Officers/HR, Vehicles or Police Search behaviour; where they must, the impact is stated and tested.
8. **Printable documents remain contract-compliant** — the A4 application and certificate contracts
   continue to pass (`backend/test_print_fit.py`).

---

## 9. Staging and production approval requirements

### 9.1 Environment separation

The project must support separate **Development**, **Staging** and **Production** environments.
**None of these are separated today** (`PROJECT_STATUS.md` §8).

### 9.2 Staging approval requirements

Staging may be approved when:

1. The environment is network-isolated, reachable only over a private network/VPN, with TLS in use.
2. It holds **synthetic or de-identified data only**, and has **no route to production data**.
3. Its database and document storage are isolated from every other environment.
4. Any seeded demo accounts exist **only** here and are clearly labelled as such.
5. Dependency manifests exist so the environment is reproducible.
6. Deployment to staging is a repeatable, documented procedure.
7. The owner approves the promotion.

### 9.3 Production approval requirements

Production may be approved only when **all** of the following hold:

1. All Release 1.0 scope is complete and verified (§5).
2. Every security gate G-1 … G-12 is closed, or the residual risk is explicitly accepted in writing by
   the owner.
3. **Versioned migrations** are in place, and migrations do **not** run as a side effect of booting
   the web process.
4. Migration idempotency has been tested **on a populated database**.
5. **Backups are automated and restoration has been successfully tested.**
6. **Rollback procedures are documented and rehearsed**, including the honest statement that schema
   rollback may require restoration from backup.
7. Database access is least-privilege and encrypted in transit.
8. Monitoring and post-deployment checks are in place.
9. Deployment and rollback procedures are documented (`PROJECT_CONTEXT.md` §11.2).
10. A staging verification has been completed on synthetic data.
11. The owner gives **explicit, recorded approval**, including approval of any maintenance window.

### 9.4 Deployment expectations

- **The first production deployment may require a planned maintenance window.**
- **Zero downtime must not be promised** until the architecture and deployment process have been
  verified to support it. At baseline they do not.
- **No production change is made without explicit owner approval.**

---

## 10. Schedule — recorded proposal, not a commitment

The owner has **proposed** an initial **10-calendar-day delivery sprint beginning 2026-11-06**, with
approximately two hours of owner review and coordination per day, and **2026-11-15 as an initial
review checkpoint**.

**Binding interpretation:**

1. **2026-11-15 is a review checkpoint, not an unconditional production launch deadline.**
2. **The 10-day proposal is not a guaranteed delivery date** and is not adopted as a commitment by
   this document.
3. **All planned CID Release 1.0 features must be completed and verified, even if the deadline moves.**
4. **Security, testing and data integrity are never sacrificed to meet a date.**
5. **The implementation order is established only after a complete repository assessment, and only
   with owner approval.** No schedule is invented by the agent.

---

## 11. Future release planning rules

1. **One release at a time.** A future release is planned only after the current release is accepted.
2. **Scope is approved before work starts**, never discovered during it.
3. **Postponed items stay postponed** until the owner moves them. Airport remains Release 1.1.
4. **A release is defined by its acceptance criteria**, written before implementation begins.
5. **Carry-over is explicit.** Anything not delivered is listed, with reason, and re-approved into the
   next release rather than silently rolled forward.
6. **Scope changes are recorded** in `CHANGELOG.md` and reflected identically in `PROJECT_CONTEXT.md`,
   `PROJECT_STATUS.md` and this document.
7. **Future modules integrate with existing shared services** — users, permissions, audit logs and
   branch management — instead of duplicating them.
8. **Technical debt is scheduled, not assumed.** Known debt (unversioned migrations, obsolete test
   harnesses, missing dependency manifests, boot-time schema side effects) is planned into a release
   rather than deferred indefinitely.
9. **Release numbering:** `CID Release <major>.<minor>`. Release 1.0 = Fingerprint + Crime +
   Checkpoint. Release 1.1 = Airport Unit. Later scope is assigned by the owner.

---

## 12. Cross-document consistency

The Release 1.0 scope statement is intentionally duplicated in three places and **must remain
identical** in all of them:

| Document | Section |
|---|---|
| `PROJECT_CONTEXT.md` | §3 — Current CID Release 1.0 scope |
| `PROJECT_STATUS.md` | §2 — Unit status |
| `RELEASE_PLAN.md` (this document) | §1 — CID Release 1.0 scope |

Any change to scope must be applied to all three in the same change set, recorded in `CHANGELOG.md`,
and approved by the owner.
