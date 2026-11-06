# Decision Register — Sentinel CID (canonical)

**Phase 3 deliverable G.** This is the **authoritative** decision register for the project.
Branch `arena/6303ef2f-sentinel-police-management` · 2026-11-06

**Supersedes** `assessment/DECISION_REGISTER_RECOMMENDATIONS.md` (Phase 2), which remains in the
repository as the record of the Phase 2 analysis. `PROJECT_CONTEXT.md` Appendix A remains the
historical record of how D-01…D-17 were first raised. Where any of these differ, **this document
governs**.

---

## 0. Status summary

| | Count |
|---|---|
| Decisions carried into Phase 3 | 30 (D-01…D-29 incl. D-03b) |
| **Closed by the owner in the Phase 3 brief** | **3** (D-18, D-14, D-16) |
| New decisions raised by the Phase 3 requirements and architecture work | **14** (D-30…D-43) |
| **Open** | **41** (D-01…D-13, D-15, D-17, D-19…D-43, incl. D-03b) |
| **Release-blocking and open** | **24** |

**The 24 release-blocking open decisions**, so the number is checkable:
D-03 · D-04 · D-05 · D-06 · D-08 · D-12 · D-15 · D-19 · D-20 · D-21 · D-22 · D-23 · D-24 · D-25 ·
D-26 · D-27 · D-31 · D-32 · D-33 · D-34 · D-35 · D-07 · D-43 · D-02.

**D-14a** (§2) is a **sign-off item under the now-closed D-14**, not a new register entry, and is
therefore not counted above.

> **Zero decisions were closed at the end of Phase 2.** Three are now closed. That is real progress,
> and the two substantive closures (D-18, D-14) were the two largest estimating unknowns in the
> project — but they **increased** Release 1.0 scope rather than reducing it.

---

## 1. CLOSED — decided by the owner

| ID | Decision | Owner's answer | Consequences now built into the requirements |
|---|---|---|---|
| **D-18** | Fingerprint Release 1.0 definition — clearance-only, or genuine biometric capture and matching? | **BOTH.** The unit must deliver the clearance / identity-review workflow **and** genuine biometric capture and matching | **My Phase 2 recommendation of "clearance-only for 1.0" was overridden.** Work package **WP-45**, previously excluded from the estimate as `U` (unestimable), is **now in Release 1.0 scope and must be estimated** — see `planning/IMPLEMENTATION_ROADMAP.md`. Four prerequisites (**D-31 scanner, D-32 bridge service, D-33 matching engine, D-35 fingers captured**) are now on the critical path and are **procurement, not coding**. Eight new biometric security requirements (SR-20…SR-27) become release-blocking. The owner's "~80% complete" figure for this unit is **definitively not applicable** to the approved scope |
| **D-14** | Definition of Crime Unit "advanced reports" | **Use the proposed catalogue as the starting point**; review, complete and document it for approval | Catalogue reviewed, feasibility-assessed and completed: **18 reviewed + 6 added = 24 reports**, in `requirements/CRIME_REPORT_CATALOGUE.md`. 8 are buildable from existing columns; 16 depend on work already specified. **The final Release 1.0 selection still requires sign-off** — see §2 below |
| **D-16** | Airport module visibility in the Release 1.0 build | **Airport Unit is excluded from Release 1.0 → Release 1.1** | Airport is out of scope for all Phase 3 requirements. It appears in the architecture only where it already shares a table or route. **The visibility question remains partly open**: exclusion from scope is not the same as hiding the module in the build — see **D-13** |

---

## 2. OPEN — immediate sign-off requested *(no new analysis needed)*

These need only a decision; the work behind them is complete.

| ID | Question | Recommendation | Evidence | Cost of delay |
|---|---|---|---|---|
| **D-14a** | Which of the 24 catalogued reports are in Release 1.0? | **Tier 1 now** (R-1, R-2, R-3, R-6, R-9, R-10, R-12, R-24); **Tier 2 with their prerequisites**; **Tier 3 after the subsystem lands**. Export: CSV + print-to-PDF | `requirements/CRIME_REPORT_CATALOGUE.md` §3, §6 | Low — Tier 1 can start, since all reports need the scoping fix first |
| **D-15** | `crime_cases` ↔ `crime_incidents` relationship | **Option A — keep both, link them explicitly via a `case_incidents` join table, one case to many incidents.** Do **not** merge | `architecture/CRIME_DATA_MODEL_DECISION.md` — full option analysis | **HIGH.** Blocks the Crime data model, reports R-7 and R-20, and the intake-to-investigation workflow. It also blocks *correcting* the model later at lower cost |
| **D-03** | Password hashing algorithm | **stdlib PBKDF2-HMAC-SHA256**, per-user salt, ≥600,000 iterations, transparent rehash on login — **no new dependency**, so D-29 stays non-blocking | C-3 / SR-03 | High — a Critical finding cannot be closed |
| **D-08** | Session lifetime and idle timeout, **separately from** RPO/RTO | Split the decision. Session policy blocks SR-09 now; RPO/RTO blocks SR-19 at go-live | H-3 / SR-09 | High — blocks a release-blocking requirement |
| **D-25** | Authoritative case status vocabulary and transitions | Adopt `CASE_STATUSES` (7, `:1716`) for **cases**, with an explicit server-validated transition table. **Keep `CRIME_STATUSES` for incidents** — do not force one vocabulary onto two different object types | 4 competing vocabularies; free text accepted at `:9586` | **HIGH.** Blocks the status engine and reports R-4, R-5, R-15 |
| **D-20** | Checkpoint catalogue and officer→location assignment | Make it **data-driven from `police_branches`**, and do it **in the same change as the M-2/SR-05 fail-closed fix**, never separately | `:1649`, `:1922`, `:2990` | **HIGH.** Blocks the checkpoint scope fix, which is a release blocker |
| **D-13** | Are out-of-scope but implemented modules enabled or hidden in the Release 1.0 build? | **Hide via `ROLE_MODULES` *and* verify the API gate by test.** Hiding alone is a usability measure, not a control | Module gating is prefix-based and applied once per request (`:8097`, `:8869`) — sound, but untested for the hidden case | Medium |

---

## 3. OPEN — release-blocking, require owner or legal input

### 3.1 Legal and policy track *(longest lead time — start immediately, run in parallel)*

> **These are the schedule's real long poles.** None can be shortened by engineering effort, and
> several cannot be implemented until answered. Engineering can implement any answer; it cannot
> choose the answer.

| ID | Question | Who decides | Blocks | Cost of delay |
|---|---|---|---|---|
| **D-04** | Legal retention periods for clearance applications, identity documents, checkpoint events, crime cases, **biometric templates and images**, and audit logs; tamper-evident audit obligation | Legal | SR-27, FPR-706, ARCH-608 | **Very high.** Retention must be designed in, not retrofitted. Biometric retention is now in scope because of D-18 |
| **D-05** | Privacy / DPIA sign-off, lawful basis, consent, subject rights; may every role search the entire central person registry? **Now must also cover biometric processing and minors' data** | Legal / DPO | FPR-707, RPT-101/102, CKR-610 | **Very high.** A DPIA covering biometrics cannot be produced in days, and go-live without it is a legal exposure |
| **D-06** | Is the 12-hour `Citizenship` review exemption a legal requirement or a convenience? | Legal / command | FPR-324, FPR-403, SR-14 | High — currently a **submitter-selectable bypass** of a control |
| **D-12** | Separation of duties — may the filing officer approve their own clearance application? | Command | FPR-001, FPR-405, SR-14 | High |
| **D-19** | Rejection path — who may reject, mandatory reason codes, applicant notification, appeal route | Legal + command | FPR-303 | High — **there is no rejection capability anywhere in the system**; an officer can only approve or leave pending indefinitely |
| **D-23** | Legal rules for suspect listing — authorisation, evidence threshold, maximum alert lifetime, must a supervisor confirm an identity match before action? | Legal + command | CRR-605/606/609 | **Very high.** Alerts are written `'Active alert'` (`:9205`) and **never change** — a person cleared by CID keeps flagging at every checkpoint indefinitely |
| **D-24** | Evidence chain of custody, admissibility and disposal | Legal / prosecution | CRR-705…709 | High — no custody record, no integrity hash, and evidence is currently retrievable **without authentication** |
| **D-27** | **The authorised post-flag procedure** — detain / refuse / refer / release / record a false match, including the **legal basis and maximum duration of detention**, notification and custody-record obligations, referral routing and acknowledgement SLA, and who may clear a false match | Legal + command / operations | All of `CHECKPOINT_UNIT_REQUIREMENTS.md` §5 | **Very high.** The system can record **none** of these today, and with D-18 approving genuine matching, a wrongful match at a checkpoint can lead to a wrongful detention |

### 3.2 Operational and structural track

| ID | Question | Recommendation | Blocks |
|---|---|---|---|
| **D-21** | CID role structure — investigator / supervisor / unit chief; who assigns cases; case-level permissions | Add a **CID supervisor** role plus a minimal assignment model (assignee, assigned-by, assigned-at, history). Adopt the capability matrix in `architecture/SYSTEM_ARCHITECTURE.md` §3.2 | Assignment (CRR-3xx), report R-17, the whole permission matrix |
| **D-22** | Investigation workflow — mandatory steps, deadlines, supervisory review, inter-branch referral | **Minimum viable:** append-only action log + case timeline. No statutory deadlines until policy says otherwise — but design the log so they can be added without replacing it | CRR-4xx |
| **D-26** | Required search filters, default sort, pagination | Status, category, branch, date range, severity, assignee, location + keyset pagination. Page size depends on **D-07** | CRR-8xx |
| **D-43** | Checkpoint **operation / shift** model — types, shift boundaries, mandatory per-shift fields *(new — D-27 governs the post-flag procedure, not shift recording)* | Defer to command; the unit cannot report on operations until answered | `CHECKPOINT_UNIT_REQUIREMENTS.md` §4 |
| **D-07** | Expected scale — accounts, records/month, peak concurrency, document volume, **expected biometric gallery size** | Needed for indexing, pagination and — now critically — **1:N search performance**. The code currently loads **all** persons into memory for name resolution (`:5490`); that pattern must not be extended to biometric search | Indexing, pagination, 1:N design |

---

## 4. OPEN — new decisions raised by Phase 3

### 4.1 Biometric programme *(all consequent on D-18; all on the critical path)*

| ID | Question | Status | Why it blocks |
|---|---|---|---|
| **D-31** | **Scanner hardware** — model, quantity, per-site allocation, procurement timeline, budget | **New — blocking** | Nothing can be captured. Procurement lead time is outside engineering control |
| **D-32** | **Who builds, signs, distributes and updates the local bridge service** on every capture workstation? | **New — blocking** | The browser calls `127.0.0.1` for capture and **no bridge code exists in this repository**. This is also an endpoint-management obligation, not only a coding task |
| **D-33** | **Matching engine and template format** — vendor SDK or open implementation (e.g. NIST NBIS); ISO/IEC 19794-2, ANSI-378 or proprietary; does extraction run on the bridge or the server? | **New — blocking** | Determines accuracy, licensing cost, vendor lock-in, and whether raw images cross the network |
| **D-34** | **Required accuracy operating point** (FAR/FRR) and who accepts the measured evidence | **New — blocks go-live** | A police identification system must not run on an unjustified threshold |
| **D-35** | **Which fingers are captured** — thumb / two thumbs / four-finger slaps / ten-print | **New — blocking** | Drives hardware choice, capture time, storage, accuracy and the capture UI |
| **D-36** | Are source **images** retained in addition to templates? | **New** | Evidentiary value and re-processing ability vs. risk and storage |
| **D-37** | Is 1:N search branch-scoped by default, with cross-branch as a permissioned audited action? | **New** | A national biometric search is an investigative act, not a default |
| **D-30** | Are **latent prints** (lifted from scenes) in scope? | **New** | Requirements assume **no** for Release 1.0. Answer early — "yes" is a separate programme |

### 4.2 Crime data model and reporting

| ID | Question | Status |
|---|---|---|
| **D-38** | May an incident at a station in one branch be linked to a case in another branch, and who authorises it? | **New** |
| **D-39** | Does an unlinked incident need an explicit "no further action / filed" closure state, so *never actioned* is distinguishable from *awaiting action*? | **New** |
| **D-40** | Is an exported report a controlled document? Formats, watermarking, retention of exports | **New** |
| **D-41** | Does the **cross-unit person view** (report R-14 — one person across crime, checkpoint and clearance) proceed, under which permission and audit rules? | **New** — the single most privacy-sensitive output in the catalogue |
| **D-42** | Small-cell suppression threshold for demographic reporting (recommend 5, subject to the DPIA) | **New** |

---

## 5. OPEN — deployment and environment *(not blocking requirements, blocking go-live)*

| ID | Question | Status |
|---|---|---|
| **D-01** | Hosting target, region(s), data residency / sovereignty | Open — **now more consequential**, because biometric data has residency implications |
| **D-02** | Network design — VPN topology, IP plan, certificate issuance and rotation | Open — gates SR-08 (TLS) |
| **D-03b** | Organisational identity provider (AD/LDAP/OIDC) and MFA requirement | Open |
| **D-09** | Deployment authority, production database custody, two-person rule for user/role administration | Open |
| **D-10** | Third-party certificate verification (online, QR, both, none) | Open — assumed **out** of Release 1.0 |
| **D-11** | Genuine offline/field operation requirement, and therefore a designed sync model | Open — assumed **no** for Release 1.0 |
| **D-17** | Is `DEPLOYMENT_AUDIT.proposed.md` (PR #23) the authoritative audit of record — merge, revise or supersede? | Open. **PR #23 remains open and untouched**, as instructed |
| **D-28** | Must a checkpoint stop record the vehicle involved? | Open — can wait (Release 1.1 candidate) |
| **D-29** | Dependency management and supply chain — may third-party packages be added, how pinned and vetted | Open — **stays non-blocking only if D-03 chooses stdlib PBKDF2**. The *absence* of manifests (M-10) is already blocking verification and should not wait on this decision |

---

## 6. Blockers the owner should know about

| # | Blocker | Why it matters now |
|---|---|---|
| **B-1** | **23 of 25 test suites have never been executed.** They require `psycopg2-binary`, `pgserver` and `jsdom@26`, none of which are installed, and installation is outside the current authorization | **Every acceptance criterion in this package depends on executing tests.** Until this is resolved, nothing in Release 1.0 can be *verified*, only *written*. This is the single highest-priority item and it is not a decision — it is an authorization |
| **B-2** | **D-18's four procurement prerequisites (D-31, D-32, D-33, D-35) are outside engineering's control** | The biometric half of Release 1.0 cannot be scheduled until these are answered. No date should be committed before then |
| **B-3** | **`suspect_alerts` has no `branch_id`** | The only Release 1.0 access-control gap that **cannot be closed without a schema change**, which places it behind the migration framework (SR-18) |
| **B-4** | **The legal track (D-04, D-05, D-23, D-24, D-27) has the longest lead time in the project** | These are not engineering tasks and will not be accelerated by adding developers. If they start late, they become the critical path |
| **B-5** | **A rotating-cursor fallback in the SPA returns an arbitrary person as a biometric match** (`index.html:4573`) | At a checkpoint this can produce a **wrongful detention**. Removal (FPR-902 / SR-22) is unconditional and should not wait for any other decision |

---

## 7. Register conventions

1. **Identifiers are never reused or renumbered.** D-01…D-29 keep their original meaning from
   `PROJECT_CONTEXT.md` Appendix A and the Phase 2 register. New decisions extend the sequence
   from D-30.
2. **Closed decisions are retained**, with the answer and its consequences, not deleted.
3. **A recommendation is a recommendation.** Where the register offers one, it is engineering advice;
   the decision remains the owner's. Where no recommendation is offered, it is because the question
   is legal, operational or a command matter — engineering can implement any answer but must not
   choose it.
4. **Overridden recommendations are recorded as overridden** (see D-18), not quietly dropped.
5. **Cost of delay is stated** so that deferral is a visible choice rather than a default.
