# Decision Register — Review and Recommendations

**Deliverable 6 of 8 · Phase 2 · Assessment only.**
Branch `arena/6303ef2f-sentinel-police-management` · commit `a1c2478` · 2026-11-06

---

## 0. Rules this document follows

1. **No decision is made here.** Every entry ends with the owner. Where a technical option is recommended, it is labelled as a recommendation and its risks are stated alongside it.
2. **No legal or operational policy is settled by the agent.** Retention periods, exemptions, authorisation thresholds and custody rules are recorded as questions, never resolved.
3. **Nothing is marked complete without evidence.** Decisions are either *open*, or *open with new analysis attached from Phase 2*.
4. **Blocking means blocking.** A decision is called blocking only when work cannot be correctly specified, estimated or safely built without the answer — not merely when it would be convenient to have.

**Register size:** 18 carried forward (D-01…D-17, including D-03b) + **11 new from Phase 2** (D-18…D-28) + **1 new from the security review** (D-29) = **30 open decisions**. **Zero are closed.**

---

## 1. Full register at a glance

| ID | Decision | Origin | Phase 2 added? | Group |
|---|---|---|---|---|
| D-01 | Hosting target, region(s), data residency / sovereignty | Audit PR #23 | — | Go-live blocker · legal |
| D-02 | Network design — VPN topology, IP plan, certificate issuance & rotation | Audit PR #23 | — | Go-live blocker |
| D-03 | Password policy (length, complexity, rotation, reuse) | Audit PR #23 | ✚ scope note | **Release blocker** |
| D-03b | Organisational identity provider (AD/LDAP/OIDC) and MFA | Phase 1 | — | Can wait |
| D-04 | Legal retention periods + tamper-evident audit obligation | Audit PR #23 | ✚ H-7 evidence | Legal |
| D-05 | Privacy/DPIA sign-off; may every role search the whole person registry? | Audit PR #23 | ✚ N-1 evidence | Legal |
| D-06 | Is the 12-hour `Citizenship` exemption a legal requirement or a convenience? | Audit PR #23 | ✚ M-3 evidence | **Release blocker** · legal |
| D-07 | Expected scale — accounts, records/month, peak concurrency, document volume | Audit PR #23 | ✚ SF-03 evidence | Can wait (gates performance work) |
| D-08 | RPO/RTO **and** session lifetime / idle timeout | Audit PR #23 | ✚ split proposed | **Partly a release blocker** |
| D-09 | Deployment authority, production DB custody, two-person rule for user/role admin | Audit PR #23 | ✚ H-5 evidence | Operational |
| D-10 | Third-party certificate verification (online, QR, both, none) | Audit PR #23 | — | Can wait |
| D-11 | Genuine offline/field operation requirement and sync model | Audit PR #23 | ✚ G-16 evidence | Can wait (large) |
| D-12 | Separation of duties — may the filing officer approve their own application? | Audit PR #23 | ✚ M-3 evidence | **Release blocker** · operational |
| D-13 | Are out-of-scope but implemented modules enabled or hidden in the 1.0 build? | Phase 1 | — | **Release blocker** |
| D-14 | Definition of Crime Unit "advanced reports" | Phase 1 | ✚ R-1…R-18 menu | **Release blocker** |
| D-15 | `crime_cases` ↔ `crime_incidents` relationship | Phase 1 | ✚ full analysis + 3 options | **Release blocker** |
| D-16 | Airport module visibility in the 1.0 build | Phase 1 | — | **Release blocker** (trivial) |
| D-17 | Is `DEPLOYMENT_AUDIT.proposed.md` (PR #23) the authoritative audit of record? | Phase 1 | ✚ re-verified | Near-term housekeeping |
| **D-18** | **Fingerprint Release 1.0 definition — clearance-only, or real biometric capture?** | **Phase 2** | new | **Release blocker — largest single unknown** |
| **D-19** | **Rejection path for clearance applications** — who, reason codes, notification | **Phase 2** | new | **Release blocker** · legal |
| **D-20** | **Checkpoint catalogue** — fixed South/East/West, or named district checkpoints? | **Phase 2** | new | **Release blocker (Checkpoint)** |
| **D-21** | **CID role structure** — investigator / supervisor / unit chief; who assigns cases | **Phase 2** | new | **Release blocker (Crime)** |
| **D-22** | **Investigation workflow** — mandatory steps, deadlines, supervisory review, referral | **Phase 2** | new | **Release blocker (Crime)** |
| **D-23** | **Legal rules for suspect listing** — authorisation, threshold, alert lifetime, match confirmation | **Phase 2** | new | **Release blocker** · legal |
| **D-24** | **Evidence chain of custody and admissibility** | **Phase 2** | new | Legal |
| **D-25** | **Authoritative case status vocabulary and permitted transitions; who may close/reopen** | **Phase 2** | new | **Release blocker (Crime)** |
| **D-26** | **Required search filters, default sort, pagination** | **Phase 2** | new | **Release blocker (Crime)** |
| **D-27** | **Checkpoint outcomes and the authorised post-flag procedure** | **Phase 2** | new | **Release blocker (Checkpoint)** · operational |
| **D-28** | **Must a checkpoint stop record the vehicle involved?** | **Phase 2** | new | Can wait |
| **D-29** | **Dependency management and supply chain** — may third-party packages be added; how pinned and vetted | **Phase 2** | new | Can wait (conditionally blocking) |

---

## 2. Group 1 — Decisions that **block Release 1.0**

> "Blocking" here means: the work cannot be specified, estimated or safely built until the owner answers. **Fifteen decisions are in this group.** This is the single most important finding in the Phase 2 assessment — *scheduling cannot precede these answers.*

### 2.1 Blocking because the **scope is unknown**

| ID | Why it blocks | What is blocked |
|---|---|---|
| **D-18** | The repository contains **no server-side biometric storage at all** — fingerprint templates live only in browser `localStorage` (`index.html:2698-2725`), matching is client-side substring comparison (`matchPersonByFingerprint:4526`), and the USB scanner bridge it calls (`ws://localhost`, `index.html:4773-5183`) **has no code in this repository**. If Release 1.0 means "police clearance workflow", the unit is largely built. If it means "biometric identification", a major component does not exist and is not even specified. **The owner's "~80% complete" figure cannot be evaluated until this is answered** — it is true under one reading and badly wrong under the other. | The entire Fingerprint Unit estimate; the meaning of the 80% claim; hardware procurement; whether a scanner SDK, a bridge service and a template store must be built |
| **D-14** | "Advanced reports" is an acceptance criterion with no definition. Eighteen candidate report types were derived from existing columns (Crime requirements §12.1); four of them need new columns or new models first. | Crime Unit size; whether R-16 (time-to-closure) and R-17 (per-investigator) are in scope, each of which forces additional schema |
| **D-15** | `crime_cases` and `crime_incidents` have **no foreign key and no shared identifier**. Whether they are one workflow or two independent registers changes the data model, both UIs, the status vocabulary and every report. | Crime Unit data model; reporting scope; the branch-scoping fix for `/api/crimes` |
| **D-13 / D-16** | The build currently ships modules outside the approved Release 1.0 scope (HR, Airport, Transport, Stations). Whether they are hidden, disabled or shipped changes the test matrix, the RBAC surface and the security review boundary. | Release build definition; regression scope; what "done" means at the release gate |

### 2.2 Blocking because the **behaviour is a policy choice**

| ID | Why it blocks | What is blocked |
|---|---|---|
| **D-06** | `is_admin_user(user) or citizenship_wait_exempt(app_row)` (`server.py:9052`) skips **both** review gates. The `Citizenship` purpose is supplied by the submitter, so the exemption is caller-selectable. We cannot "fix" this without knowing whether it is lawful. | Security finding **M-3**; the Fingerprint approval gate; the review-gate test suite |
| **D-12** | Self-approval is currently permitted — there is no check that the approver differs from the submitter. | **M-3** remediation; approval workflow; whether a second role is needed in the Fingerprint Unit |
| **D-19** | **There is no rejection path anywhere in the system.** `'Rejected'` exists only in HR/conduct constants and as an unreachable analytics axis (`:6112`, `:6124`). An officer's only options are approve or leave pending indefinitely. | Fingerprint workflow completeness; the clearance status model; applicant notification; any SLA reporting |
| **D-23** | Listing a named person as a suspect is the most consequential data entry in the system, and it directly drives checkpoint flagging. The repository has no authorisation rule, no evidence threshold, no alert lifetime and no match-confirmation step. | Suspect lifecycle (SM-07/SM-08); the Checkpoint post-flag workflow (which depends on it); legal defensibility |
| **D-25** | **Four competing status vocabularies exist**: `CASE_STATUSES` (7, `:1716`), `CRIME_STATUSES` (5, `:1708`), the case-workspace `<select>` (4, `index.html:1730`), and free text accepted by `PATCH /api/crime-cases/<id>`. No state machine, no transition rules, no closure authority. | Case progression; closure-rate reporting (which is already published to commanders); the PATCH scope fix; every status-based report |
| **D-27** | A checkpoint officer cannot record what actually happened. `screening_result` and `action_taken` are **server-computed** from the alert check and have two possible values each (`:9305-9306`). "Supervisor contacted" is written as a string; nothing notifies anyone. | The Checkpoint Unit's operational value; whether the unit can be called complete |
| **D-20** | `CHECKPOINT_LOCATIONS` is hard-coded to South / East / West (`:1649`), while Branch Management and officer postings already support **named district checkpoints**. Named checkpoints fall into the analytics "Other" bucket and interact badly with the scope matcher. | The M-2 scope fix; checkpoint analytics; branch model consistency |
| **D-21** | There is **one** CID role. No investigator, supervisor or unit chief. Case assignment does not exist in any form (`grep assigned_to|investigator|assignee|officer_in_charge` → **0** hits). | Case assignment; investigation workflow; per-officer reporting (R-17); case-level permissions |
| **D-22** | Whether the investigation workflow needs mandatory steps, deadlines, supervisory review or inter-branch referral determines whether this is a small feature or a large one. | Crime Unit estimate; the audit model; notification requirements |
| **D-26** | Server-side filtering and pagination do not exist (`:8259` reads no query parameters; no `LIMIT`). The required filter set defines the work. | Search & filtering scope; list performance; interacts with **D-07** |

### 2.3 Blocking because a **security fix cannot be completed without them**

| ID | Why it blocks |
|---|---|
| **D-03** | Default credentials (C-2) cannot be replaced without a password policy to replace them *with*. Length, complexity, rotation and reuse rules also set the lockout thresholds in **H-4**. *Note: the hashing algorithm itself (C-3) can proceed independently using standard-library PBKDF2.* |
| **D-08 (session half)** | **H-3** cannot be closed without absolute-expiry and idle-timeout values. **Recommend splitting this decision**: the session half is a release blocker; the RPO/RTO half is a go-live/operations decision that can follow (it pairs with **M-12**). |

### 2.4 Blocking **go-live**, though not day-to-day development

| ID | Why |
|---|---|
| **D-01** | Hosting target and data residency determine whether this system may lawfully hold Somali citizens' biometric and criminal data where it is being deployed. |
| **D-02** | Without a decided network design and certificate issuance process, **H-8** (no transport security anywhere in the repository) cannot be closed. |

---

## 3. Group 2 — Decisions that **can wait**

| ID | Decision | Why it can wait | When it is needed by |
|---|---|---|---|
| **D-03b** | Identity provider (AD/LDAP/OIDC) + MFA | Local accounts with a proper KDF and a password policy are a defensible Release 1.0 position. Federating later does not invalidate that work, provided `users` keeps a stable identity key. | Release 1.1, or sooner if the force already runs a directory |
| **D-07** | Expected scale | Current volumes are unknown but the register sizes in the repository are small. Pagination and indexing can be added once real numbers exist. **Caveat:** if peak concurrency is high, the `COUNT(*)`-based `case_id` (**H-6**) fails sooner, so answer before go-live. | Before performance tuning; before go-live sizing |
| **D-10** | Third-party certificate verification | Certificates are already issued and printable (`certificate.html`, the A4 print contract is the one *verified* feature in the system). External verification is an addition, not a prerequisite. | Release 1.1 — unless an external body already demands it |
| **D-11** | Offline/field operation | Genuinely large (a designed sync model, conflict resolution, local storage security). The current `localStorage` fallback is a demo artefact, not an offline mode, and should not be mistaken for one. | Must be decided **before** anyone promises checkpoint operation without connectivity |
| **D-28** | Vehicle linkage on checkpoint events | The plate lookup already works as a read-only convenience; recording the vehicle on the event is additive. | Release 1.1 |
| **D-29** | Dependency management and supply chain | Avoidable for Release 1.0 if PBKDF2 (standard library) is chosen for C-3. **Becomes blocking** the moment Argon2/bcrypt, a migration framework or a PDF library is chosen. **Caveat:** the *absence* of manifests (finding **M-10**) is already blocking verification, so the manifest itself should not wait. | Before the first third-party package is added; the manifest itself, immediately |
| **D-17** | Status of the historical audit artefact | Housekeeping, not engineering. But PR #23 is still **open and in draft**, and this assessment has now re-verified all eight of its headline concerns as still present. Leaving it unresolved risks two competing audit records. | **Near term — recommend resolving this week** |

---

## 4. Group 3 — Decisions requiring **legal or operational confirmation**

> These are **not** engineering decisions. The agent has deliberately not formed a position on any of them, and no code behaviour should be chosen until an authorised person answers.

| ID | Decision | Who must answer | What Phase 2 adds |
|---|---|---|---|
| **D-01** | Data residency / sovereignty for biometric and criminal records | Legal + command | — |
| **D-04** | Retention periods for clearance applications, identity documents, checkpoint events, crime cases and audit logs; is a tamper-evident audit legally required? | Legal | **H-7**: the audit table is plain, with no append-only constraint and no integrity control; updates record no before/after values; authentication events are absent entirely (**H-4**). If tamper-evidence is a legal obligation, the current design does not meet it. |
| **D-05** | DPIA sign-off; may every role search the entire central person registry? | Legal / data protection | **N-1**: `GET /api/suspect-alerts` is **entirely unscoped** — every CID and checkpoint officer nationwide reads every suspect, victim and witness listing, including the free-text reason for unlinked listings. This is a live privacy exposure, not a theoretical one. |
| **D-06** | Is the 12-hour `Citizenship` exemption lawful? | Legal + command | **M-3**: the exemption is selectable by the submitter via the application's `purpose`. |
| **D-09** | Deployment authority, production database custody, two-person rule for user/role administration | Command / operations | **H-5**: a single administrator can today reset any password, change any role and deactivate any account with **no session revocation** and **no last-admin guard**. A two-person rule would be a control, not a formality. |
| **D-12** | May the filing officer approve their own clearance application? | Command / professional standards | **M-3**: currently permitted. |
| **D-19** | Who may reject an application; mandatory reason codes; applicant notification; appeal route | Legal + command | No rejection capability exists at all. |
| **D-23** | Authorisation and evidence threshold for listing a suspect; maximum alert lifetime; must a supervisor confirm an identity match before action? | Legal + command | Alerts are written as `'Active alert'` and **never change** — a person cleared by CID keeps flagging at every checkpoint indefinitely. |
| **D-24** | Evidence chain of custody, admissibility and disposal | Legal / prosecution service | No custody record, no integrity hash, no access log, and evidence files are currently retrievable **without authentication** (C-1). |
| **D-27** | The authorised procedure after a checkpoint flag — detain, refuse, refer, release, record a false match | Command / operations | The system can record none of these. |
| **D-03b** | Is MFA mandated for police systems in this jurisdiction? | Legal / command | — |

---

## 5. Group 4 — Recommended technical option, with its risks

> **Each of these remains the owner's decision.** What follows is the engineering recommendation and, in every case, what could go wrong if it is adopted. Where no responsible recommendation is possible without policy input, that is stated plainly.

| ID | Recommended technical option | Risks of adopting it |
|---|---|---|
| **D-15** | **Option A — link them.** Add a nullable `crime_cases.source_incident_id` FK plus a "convert incident to case" action. `crime_incidents` stays the station intake register (it already carries the victim block, severity and `incident_at`); `crime_cases` stays the CID investigation file. | Additive and reversible, but it introduces a conversion workflow needing its own permissions, audit and tests; it commits the project to one status mapping between two vocabularies; and it does not by itself fix the `/api/crimes` branch-scoping mismatch (that must be done regardless). **Option B (merge) is explicitly not recommended inside Release 1.0** — destructive migration, two UIs, two scoping models. |
| **D-18** | **Define Release 1.0 as the police-clearance workflow**, and carve biometric capture out as a separately scoped programme. | Risks contradicting the owner's "~80% complete" expectation if that figure was meant to include biometrics. It also leaves the browser `localStorage` biometric demo code in the build, which must then be **removed or visibly disabled** so no officer mistakes it for a real identification capability. That removal is itself a scope item. |
| **D-03** | **PBKDF2-HMAC-SHA256 with a per-user salt and a high iteration count**, using the Python standard library, with transparent re-hash on next login. | Weaker than Argon2id against GPU attack. Mitigation: pick a high cost parameter now and leave a documented upgrade path. Choosing Argon2 instead is better cryptography but makes **D-29** blocking. |
| **D-08** | **Split the decision.** Session half: absolute expiry plus idle timeout, with token rotation on login and on any privilege change. RPO/RTO half: defer to the operations decision. | Shorter sessions mean more logins at checkpoints and stations, which is exactly where re-authentication is most disruptive. Set the values with operational input, not by engineering preference. |
| **D-25** | **Adopt `CASE_STATUSES` (7 values, `:1716`) as the single authoritative vocabulary**, map the other three onto it, and add an explicit transition table validated server-side. | Existing rows carry values from the other vocabularies and would need mapping; closure-rate figures already shown to commanders may shift once statuses are normalised. That shift must be announced, not silent. |
| **D-20** | **Make the checkpoint catalogue configurable** from `police_branches` rather than the hard-coded `CHECKPOINT_LOCATIONS` tuple, so named district checkpoints become first-class. | Touches the scope matcher, which is a **security control** (M-2). Must be done *with* the M-2 fail-closed fix and its negative tests, never before or separately. |
| **D-21** | **Add a supervisor role and a minimal assignment model** (assignee, assigned-by, assigned-at, history). | Expands the RBAC matrix, which is already the most intricate part of the system (`rbac_self_test()` exists for a reason). Every new role multiplies the authorization test surface. |
| **D-22** | **Minimum viable workflow:** an append-only investigative action log plus a case timeline assembled from existing `audit_events`. No deadlines, no mandatory steps, until policy says otherwise. | Under-serves a unit that may need statutory deadlines. If policy later adds them, the action log must be extended rather than replaced — design it with that in mind. |
| **D-26** | **Server-side filters for status, category, branch, date range and assignee, plus keyset pagination**, replacing client-side filtering. | Current client-side search is instant on small registers and will feel slower when moved server-side. Also depends on **D-07** for sensible page sizes and index choices. |
| **D-14** | **Phase the report set.** Ship R-1…R-8 (all derivable from existing columns, all currently unscoped and unfiltered — so they must be scoped and filtered anyway) in Release 1.0. Defer R-16/R-17 (which need `closed_at` and case assignment) to the phase that delivers those models. | Risks the owner regarding a phased set as a scope reduction. It is not — it is sequencing by data dependency. **The owner must confirm the split rather than have it assumed.** |
| **D-13 / D-16** | **Hide out-of-scope modules in the Release 1.0 build** via the existing `ROLE_MODULES` gating rather than deleting code. | Hidden ≠ unreachable: the API module gate must be verified to deny them too, otherwise this is UI-only concealment — exactly the mistake the navigation test suites already make by asserting what the UI hides rather than what the server refuses. |
| **D-29** | **Adopt a pinned `requirements.txt` with hashes** before any third-party package is introduced. | Minimal risk; the real risk is the status quo — finding **M-10** — the project depends on `psycopg2`, `pgserver` and `jsdom@26` with **no manifest anywhere**, which is why 23 of 25 suites could not be executed in this assessment. |
| **D-11** | **Defer**, and explicitly document that offline operation is *not* supported in Release 1.0. | Operationally real: checkpoints are exactly where connectivity fails. Deferring is only acceptable if the owner confirms connectivity, or accepts manual fallback procedures. |
| **D-04, D-05, D-06, D-09, D-12, D-19, D-23, D-24, D-27, D-01, D-03b** | **No technical recommendation offered.** These are legal, operational or command decisions. Engineering can implement any answer; it cannot choose the answer. | The only risk here is *failing to ask* — and then encoding an accidental policy in code, which is precisely how the `Citizenship` exemption and the fail-open scopes came to exist. |

---

## 6. What changed in the register as a result of Phase 2

1. **Eleven new decisions** (D-18…D-28) were raised, plus **D-29** from the security review. All arise from code evidence, none from speculation.
2. **Two existing decisions moved from "question" to "blocking with analysis attached":** D-14 now has an 18-item candidate report menu with the data dependency of each; D-15 now has a full field-level comparison and three costed options.
3. **D-08 is recommended for splitting** into a session-security half (release blocker) and an RPO/RTO half (operations).
4. **D-05 and D-04 acquired concrete evidence** — **N-1** (unscoped nationwide suspect read, new in this assessment) and **H-7** (mutable, incomplete audit trail) respectively. They are no longer abstract compliance questions.
5. **D-17 is now urgent-ish rather than cosmetic:** this assessment re-verified all eight of PR #23's headline concerns as **still present** at `a1c2478`, so the two documents agree — but PR #23 remains an **open draft** and two audit records of record is a governance risk.
6. **Nothing was closed.** No decision in the register was resolved by this assessment, and none should be assumed resolved.

---

## 7. Suggested order in which the owner is asked

> This is a **suggestion about sequencing the questions**, so the answers arrive in the order engineering needs them. It is not a schedule and it is not a commitment.

| Wave | Decisions | Why these first |
|---|---|---|
| **A — unblocks estimating at all** | **D-18**, **D-14**, **D-15** | Until these three are answered, the size of two of the three units is unknown, and **no credible schedule can exist**. |
| **B — unblocks the security fixes** | **D-03**, **D-08 (session half)**, **D-12**, **D-06** | Wave 1 security remediation needs these to be *finishable*, not merely started. |
| **C — unblocks the functional build** | **D-25**, **D-21**, **D-26**, **D-19**, **D-20**, **D-27**, **D-22**, **D-13/D-16** | Each one defines a work package that is otherwise unspecifiable. |
| **D — legal review, in parallel** | **D-04**, **D-05**, **D-23**, **D-24**, **D-01**, **D-09** | Long lead times; start them now, in parallel with A–C, because they gate go-live rather than development. |
| **E — can follow** | **D-02**, **D-07**, **D-10**, **D-11**, **D-28**, **D-29**, **D-03b**, **D-17** | Needed, but not in the critical path for building Release 1.0 — with the caveats noted in §3. |

---

## 8. The single sentence the owner most needs

**Fifteen of the thirty open decisions block Release 1.0, and three of them (D-18, D-14, D-15) must be answered before anyone — including this assessment — can state how large the remaining work actually is.**
