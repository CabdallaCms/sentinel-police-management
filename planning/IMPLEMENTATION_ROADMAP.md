# Release 1.0 — Implementation Roadmap and Revised Estimates

**Phase 3 §4 deliverable · Planning only. No application code was changed and no date is committed.**
Branch `arena/6303ef2f-sentinel-police-management` · 2026-11-06

**Revises** `assessment/DEPENDENCIES_AND_ESTIMATES.md` (Phase 2, ≈144–292 engineering days across
47 work packages). That estimate is now **superseded** because owner decision **D-18 = BOTH** moved
**WP-45 (biometrics)** — previously excluded as `U`, unestimable — **into Release 1.0 scope**.

---

## 1. Estimating conventions

| Band | Engineering days |
|---|---|
| **XS** | ≤ 1 |
| **S** | 1–3 |
| **M** | 3–8 |
| **L** | 8–20 |
| **XL** | > 20 |
| **U** | Unestimable until a named decision closes |

**Rules applied throughout**

1. The unit is one **engineering day** — design, implementation, tests and review for one developer.
2. **Owner review and approval time is estimated separately** (§7) and is **not** included in any
   engineering figure. Mixing them is how "10 days" became plausible.
3. **Procurement and legal lead times are tracked separately** (§6) and are **not** engineering days.
4. Ranges are honest ranges. The upper bound is not padding; it is the figure that applies when a
   dependency arrives late or a decision changes shape.
5. **A package is not complete until its tests execute and pass.** Test effort is inside the estimate.

---

## 2. What changed since the Phase 2 estimate

| Change | Effect |
|---|---|
| **D-18 = BOTH** | WP-45 enters scope. It is **not one work package** — it decomposes into seven (WP-45a…WP-45g, §4) |
| **D-14 = catalogue approved as starting point** | Reporting is now specified: **24 reports** (18 reviewed + 6 added), of which **8 are buildable from existing columns** and 16 are gated on other work. WP-34 is re-scoped and split |
| **D-16 = Airport excluded** | No Airport work packages in Release 1.0. No estimate reduction, because none were included |
| **Phase 3 analysis** | WP-27 grows (join table, not a single FK column); WP-38 splits into detention / referral / false-match; four new packages appear (WP-48…WP-51) |

---

## 3. Work package summary — carried forward

Unchanged from `assessment/DEPENDENCIES_AND_ESTIMATES.md` unless a revision is noted.

| Group | Packages | Days | Revision |
|---|---|---|---|
| **Enablement** | WP-01 test environment, WP-02 CI | 4–8 | — |
| **Security Wave 1** | WP-03, WP-04, WP-05, WP-06, WP-07, WP-08, WP-09 | 17–35 | — |
| **Security Wave 2** | WP-10, WP-11, WP-12, WP-13, WP-14, WP-15 | 19–38 | — |
| **Platform / Wave 3** | WP-16, WP-17, WP-18, WP-19, WP-20, WP-21 | 17–39 | — |
| **Fingerprint (clearance)** | WP-22, WP-23, WP-24, WP-26 | 17–33 | WP-25 remains deferred (D-10) |
| **Crime** | WP-27, WP-28, WP-29, WP-30, WP-31, WP-32, WP-33, WP-34, WP-35 | 46–91 | **WP-27 and WP-34 revised — see §5** |
| **Checkpoint** | WP-36, WP-37, WP-38, WP-39, WP-40, WP-41 | 20–34 | **WP-38 split — see §5** |
| **Release** | WP-42, WP-43, WP-44 | 9–18 | — |
| | **Subtotal (carried)** | **≈ 149–296** | |

---

## 4. NEW — the biometric programme (WP-45, decomposed)

> **This section exists only because D-18 was answered BOTH.** Every package below is new scope.
>
> **Four of the seven cannot start until a procurement or technical decision closes**, and those
> decisions are **not** engineering tasks. The estimates are therefore conditional, and are stated
> as conditional.

| # | Package | Band | Days | Depends on | Blocked by |
|---|---|---|---|---|---|
| **WP-45a** | **Biometric data model and encrypted store** — enrolment tables, per-finger versioning, encryption at rest, key management, retention hooks | **L** | 10–18 | WP-16 (migrations) | D-04, D-35, D-36 |
| **WP-45b** | **Capture bridge integration (server side)** — versioned protocol contract, enrolment ingest, device attribution, quality gating, loopback enforcement | **M–L** | 6–12 | WP-45a | **D-32**, D-33 |
| **WP-45c** | **Matching engine integration** — template extraction, 1:1 verification, 1:N identification, candidate ranking, engine abstraction so the vendor can change | **XL** | **20–40** | WP-45a | **D-33**, D-35 |
| **WP-45d** | **Threshold policy and adjudication workflow** — two configurable thresholds, audited changes, mandatory human adjudication band, supervisor override | **M–L** | 6–12 | WP-45c | D-34 |
| **WP-45e** | **Exception handling** — FTA / FTE, false-match recording, re-flag suppression, manual review path | **M–L** | 6–12 | WP-45d, WP-24 | D-27 |
| **WP-45f** | **Biometric security controls** — SR-20…SR-27: access restriction, per-read audit, no bulk export, retention expiry, audited deletion | **L** | 8–16 | WP-45a, WP-19 | D-04, D-05 |
| **WP-45g** | **Removal of the false biometric layer** — delete `biometricStore`, string matching, and the **rotating-cursor fallback**; redefine the two biometric metrics | **S** | 2–4 | — | **none — can start immediately** |
| | **Biometric subtotal** | | **58–114** | | |

### 4.1 What is NOT in those numbers

| Item | Why excluded | Owner |
|---|---|---|
| Scanner hardware procurement (**D-31**) | Not engineering time. Lead time unknown | Owner / procurement |
| Vendor SDK licensing (**E-2**) | Commercial, not engineering | Owner / procurement |
| **Building the local bridge service itself** (**D-32**) | **No code for it exists in this repository.** If this team must build it, add an estimated **15–30 days** and a platform-support matrix. If a vendor supplies it, add integration and acceptance time instead | **Unassigned — D-32 must decide** |
| Bridge rollout to every capture workstation | Endpoint management, not application development | Owner / IT operations |
| Accuracy test-set construction and FAR/FRR measurement (**D-34**) | Specialist activity; needs representative data and a defined protocol. Estimated **5–15 days** once D-33 and D-35 close | Shared |
| DPIA covering biometric processing (**D-05**) | Legal | Legal / DPO |

> **WP-45g is the one item here that should start immediately and independently.** It removes the
> code that fabricates identifications. It depends on no decision, no hardware and no other package.

---

## 5. NEW and REVISED packages from Phase 3 analysis

| # | Package | Band | Days | Change |
|---|---|---|---|---|
| **WP-27** *(revised)* | Incident↔case link via a **`case_incidents` join table** (not a single FK), link/unlink with reason, cross-branch authority, plus the `/api/crimes` scoping fix | **L** | **8–14** *(was M, 4–8)* | Many-to-many support and a new authorization surface |
| **WP-34** *(revised + split)* | **WP-34a** Tier 1 reports (R-1, R-2, R-3, R-6, R-9, R-10, R-12, R-24) scoped, filtered, drillable, exportable | **L** | 10–18 | Was a single 8–15 package covering R-1…R-8 |
| | **WP-34b** Tier 2 reports (R-4, R-5, R-7, R-8, R-13, R-15, R-16, R-17, R-18, R-20, R-23) | **L** | 12–20 | Each gated on its prerequisite |
| | **WP-34c** Tier 3 reports (R-11, R-14, R-19, R-21, R-22) incl. small-cell suppression and the cross-unit view's permission + audit model | **L** | 10–18 | D-41, D-42 |
| **WP-38** *(split)* | **WP-38a** officer-recorded outcomes (replacing fully automatic `screening_result`) | **M** | 4–8 | — |
| | **WP-38b** detention record: basis, clock, escalation, outcome | **L** | 8–14 | **D-27** (legal) |
| | **WP-38c** referral: raise, route, acknowledge, outcome, escalate to case | **M–L** | 6–12 | **D-27** |
| | **WP-38d** false match: record, report, suppress re-flagging | **M** | 4–8 | D-27, WP-45e |
| **WP-48** *(new)* | Checkpoint **operation / shift** model | **M–L** | 5–10 | **D-43** |
| **WP-49** *(new)* | `case_participants` — separate participants from suspect alerts | **M–L** | 5–10 | Split out of WP-31 |
| **WP-50** *(new)* | `crime_cases.closed_at` + `severity`; case closure/reopen authority | **S–M** | 3–6 | D-25 |
| **WP-51** *(new)* | Data-quality exceptions report + reporting safeguards framework (RPT-101…106) | **M** | 4–8 | — |
| | **New / revised subtotal** | | **≈ 79–146** | |

---

## 6. Revised totals

| Component | Engineering days |
|---|---|
| Carried-forward packages (§3) | 149–296 |
| Revisions and new packages (§5), net of what they replace | +50–96 |
| **Biometric programme (§4)** | **+58–114** |
| **Release 1.0 total** | **≈ 257–506 engineering days** |

**Still excluded:** WP-25 certificate verification (D-10) · WP-46 offline/sync (D-11) ·
WP-47 IdP/MFA (D-03b) · the bridge service if built in-house (+15–30) · accuracy measurement (+5–15).

### 6.1 Calendar translation *(engineering only — excludes §7 and §8)*

| Team | Elapsed |
|---|---|
| 1 developer | ≈ 257–506 working days ≈ **12–24 months** |
| 3 developers | ≈ **6–12 months**, assuming the dependency chain allows parallelism — it only partly does |
| 5 developers | ≈ **4–9 months**; beyond roughly 4 developers the critical path, not headcount, governs |

> **These are engineering figures only.** Owner review (§7) and procurement/legal lead time (§8) are
> additional and, for the biometric half, probably dominant.

---

## 7. Owner review and approval time *(separate from engineering)*

| Activity | Owner effort | Elapsed |
|---|---|---|
| Review and approve this Phase 3 package | 1–2 days | 3–7 days |
| Close the 7 §2 sign-off decisions in `DECISION_REGISTER.md` | 1–2 days | 3–10 days |
| Close the operational/structural decisions (D-21, D-22, D-26, D-43, D-07) | 2–3 days | 1–3 weeks |
| Close the **legal** track (D-04, D-05, D-06, D-12, D-19, D-23, D-24, D-27) | varies | **4–12 weeks** — external counsel |
| Close the **biometric** track (D-31…D-37) | varies | **4–16 weeks** — procurement |
| Per-package acceptance reviews (approx. 25 gates) | 0.5 day each ≈ 12 days | spread |
| Release gate review (G-1…G-12) | 2–3 days | 1 week |
| **Total owner effort** | **≈ 20–25 owner-days** | **largely in parallel, but the legal and biometric tracks are not** |

---

## 8. Critical paths

### 8.1 Software critical path

```
WP-01 test environment (2–4)
   └─► WP-16 versioned migrations (4–8)
          ├─► WP-17 suspect_alerts.branch_id (3–6)
          │      └─► WP-49 participants (5–10)
          │             └─► WP-31 alert lifecycle (5–10)
          │                    └─► WP-38d false match (4–8)
          └─► WP-28 assignment (5–10)
                 └─► WP-29 status engine (4–8)
                        └─► WP-34a Tier 1 reports (10–18)
                                                      ──► 42–82 days
```

### 8.2 Biometric critical path *(the governing path)*

```
D-31 / D-32 / D-33 / D-35  ← procurement + technical decisions, NOT engineering
   └─► WP-45a store (10–18)
          └─► WP-45c matching engine (20–40)
                 └─► WP-45d thresholds (6–12)
                        └─► WP-45e exceptions (6–12)
                               └─► D-34 accuracy acceptance (5–15)
                                                      ──► 47–97 engineering days
                                                          AFTER the decisions close
```

### 8.3 Legal critical path

```
D-04 retention ─┐
D-05 DPIA      ─┼─► 4–12 weeks elapsed, outside engineering control
D-23 / D-24    ─┤    └─► gates WP-19, WP-26, WP-31, WP-32, WP-38b, WP-45f
D-27 detention ─┘
```

> **The project's true critical path is not code.** It runs through procurement (§8.2) and legal
> (§8.3). Adding developers will not shorten either.

---

## 9. Recommended sequencing

| Stage | Contents | Days | Why here |
|---|---|---|---|
| **Stage 0 — start now, no decision needed** | WP-01, WP-02, **WP-45g** *(remove the fabricated-match code)*, WP-09, WP-21 | 8–16 | Nothing is verifiable without WP-01, and WP-45g removes an active safety defect |
| **Stage 1 — Security Wave 1** | WP-03, WP-04, WP-05, **WP-06**, **WP-07**, WP-08 | 16–31 | WP-06 and WP-07 are the two highest-leverage changes in the programme: one fail-closed fix each, correcting many endpoints |
| **Stage 2 — platform** | WP-16, WP-17, WP-18, WP-19, WP-20, WP-15 | 22–48 | Unblocks every schema change |
| **Stage 3 — Security Wave 2** | WP-10, WP-11, WP-12, WP-13, WP-14 | 13–26 | Session, auth and analytics isolation |
| **Stage 4 — units (parallel)** | Fingerprint clearance · Crime · Checkpoint | 85–160 | Three streams; the dependency chains in §8.1 bound each |
| **Stage 5 — biometrics** | WP-45a…f | 56–110 | **Starts only when D-31/32/33/35 have closed** |
| **Stage 6 — reporting** | WP-34a, WP-34b, WP-34c, WP-51 | 36–64 | Needs the status engine, assignment and participants |
| **Stage 7 — release** | WP-42, WP-43, WP-44, accuracy acceptance, penetration test | 15–30 | Gates G-1…G-12 |

**Stages 0–3 are decision-free or near-decision-free** and represent **59–121 engineering days** of
work that can begin on approval of this package. Stage 4 onward is decision-gated.

---

## 10. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | **23 of 25 test suites still cannot be executed** | Certain today | **Critical** — no acceptance criterion can be verified | WP-01 first; this is an authorization, not an estimate |
| R-2 | **Biometric procurement (D-31/32/33/35) slips** | High | **Critical** — Stage 5 cannot start | Start procurement in parallel with Stage 0; do not sequence it after software |
| R-3 | **The bridge service has no owner** | High | High — capture is impossible without it | **D-32 must be answered before any biometric estimate is committed** |
| R-4 | **Legal track runs long** | Medium–High | High — gates 6 packages | Start D-04/05/23/24/27 immediately, in parallel |
| R-5 | **Matching accuracy fails to meet the required operating point** | Medium | High — rework or hardware change | Prototype WP-45c early against a small gallery; do not defer accuracy testing to the end |
| R-6 | **The fabricated-match code reaches production** | Medium if not acted on | **Critical** — wrongful identification, potentially wrongful detention | **WP-45g in Stage 0, unconditionally** |
| R-7 | Schedule pressure reduces security scope | Medium | Critical | All 27 blocking security requirements are enumerated and non-negotiable |
| R-8 | D-15 answered against the recommendation | Medium | Medium — report catalogue and WP-27 change shape | Both options are documented; the cost of each is stated |
| R-9 | Scale assumptions wrong (D-07) | Medium | Medium–High — 1:N performance and the all-rows-in-memory pattern at `:5490` | Answer D-07 before WP-45c design |
| R-10 | Single-file SPA (13,158 lines) and backend module (10,067 lines) slow every change | Certain | Medium | Accepted for Release 1.0. Refactoring is explicitly **not** recommended now |
| R-11 | Estimates drift as decisions close | Certain | Medium | Re-estimate at each stage gate; treat §6 as a planning range, not a commitment |

---

## 11. The 10-day question

**No.** Release 1.0 cannot be delivered in 10 days. The gap is now **roughly 26–50×** the available
time — **257–506 engineering days against 10** — and it widened, not narrowed, when D-18 was
answered BOTH.

**What 10 days can honestly buy** *(with 3 developers ≈ 30 engineering days)*:

| Deliverable | Days |
|---|---|
| WP-01 test environment — makes everything else verifiable | 2–4 |
| **WP-45g — remove the code that fabricates biometric matches** | 2–4 |
| WP-03 default credentials | 2–4 |
| WP-04 password hashing | 2–4 |
| WP-09 upload validation | 1–2 |
| WP-05 authenticated document access *(start)* | 4–8 |
| WP-06 fail-closed branch scope *(start)* | 4–8 |
| **Total** | **17–34** |

That is a **genuine, material security improvement** — it closes two of three Critical findings,
removes an active safety defect and makes the rest of the programme verifiable. **It is not
Release 1.0, and it must not be described as such.**

> **No production date is committed in this document.** A credible date requires: D-31/32/33/35
> closed with known procurement lead times, the legal track closed, and WP-01 complete so estimates
> can be validated against executed tests rather than inspection.
