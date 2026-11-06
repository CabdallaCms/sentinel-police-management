# Crime Unit — Advanced Report Catalogue (for owner sign-off)

**Phase 3 deliverable B (reports) · Requirements only. No code was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Owner decision D-14 — APPROVED as a starting point:** "use the proposed report catalogue as the
> starting point; review, complete and document it for owner approval."
>
> This document does that. The Phase 2 proposal listed 18 candidates (R-1…R-18). Each has now been
> **reviewed for feasibility against the planned data model**, specified in full, and the catalogue
> **completed with six reports that were missing** (R-19…R-24).
>
> **The catalogue itself still requires owner sign-off** on which reports are in Release 1.0 — that
> final selection is §6.

---

## 1. What exists today, stated accurately

**One** report surface serves the Crime Unit: the `crime` section of `GET /api/cid/analytics`, built
by `cid_crime_analytics(c)` at `backend/server.py:6132-6172`.

**Metrics:** `total_cases` · `open_cases` · `closed_cases` · `closure_rate` · `active_suspects` ·
`categories_tracked` · `top_category`.
**Charts:** `by_location` · `by_time_of_day` (4 fixed bands) · `by_category` · `by_status` ·
`open_vs_closed`.

**Three defects affect every one of them:**

| # | Defect | Evidence |
|---|---|---|
| 1 | **Not branch-scoped.** `cid_crime_analytics(c)` takes **no `user`** — a branch-scoped officer receives **national** figures. Only `cid_checkpoint_analytics(c, user)` (`:6176`) is scoped | `:6132`, `:6319` |
| 2 | **No filters of any kind.** The builder takes no parameters and the route reads no query string | `:6132`, `:8353` |
| 3 | **No drill-down** — `'lists': {}` is returned empty | `:6171` |

Plus: no export, no trend over calendar time (`by_time_of_day` buckets *hour of day*, not dates), no
per-officer breakdown, and `closure_rate` is computed from a `status` column that currently accepts
**free text**.

**Verdict: a basic dashboard exists; advanced reporting does not.**

---

## 2. Cross-cutting requirements — apply to EVERY report

| ID | Requirement |
|---|---|
| RPT-001 | **Branch-scoped by default.** A report must never include a record the caller could not open directly. A scoped officer's totals must equal the count of records they can actually access. |
| RPT-002 | **Filters are server-side** and are applied inside the same scope predicate — a filter can narrow, never widen. |
| RPT-003 | **Every metric has a published definition** in the API response, as `cid_fingerprint_analytics` already does in its docstring (`:6074-6083`). |
| RPT-004 | **Arithmetic is pinned by tests.** A report whose numbers are not test-asserted is not complete. |
| RPT-005 | **Export is audited** — who exported what, with which filters, when. An exported police report is itself a controlled document (**D-40**). |
| RPT-006 | **Drill-down** from any aggregate to the underlying records, through the normal scoped list endpoint — so drill-down cannot leak. |
| RPT-007 | **Empty is empty.** A report with no qualifying data returns zero, never a national fallback. |
| RPT-008 | **Reports are read-only** and must never create, modify or lock records. |
| RPT-009 | Reports state the **data-as-of timestamp** and the filters in force, on screen and in any export. |
| RPT-010 | Reports depending on data the model does not yet carry are **not shipped half-built**; they ship with their prerequisite or not at all. |

### 2.1 Standard filter set

Date range (`from`/`to`, applied to a **named** date field) · category · status · branch / region /
district · severity · location · assigned officer · participant role · alert status · station
(incidents) · victim anonymity.

### 2.2 Access permissions — proposed *(requires sign-off)*

| Audience | Report scope |
|---|---|
| CID investigator | **Own branch only.** Today they receive national figures — this must change |
| CID supervisor *(role does not yet exist — D-21)* | Own branch, **plus** per-officer breakdowns |
| Station intake officer | Own station's incident reports only |
| `SystemAdmin` | All branches |
| `chief_commander` | All branches, read-only (already holds `analytics:global`) |
| Any other role | No access |

---

## 3. The reviewed catalogue — R-1 … R-18

**Feasibility key:** ✅ buildable from existing columns · ⚠️ needs a model change first · ⛔ blocked

| # | Report | Purpose | Data sources | Filters | Grouping | Output fields | Access | Feasible? |
|---|---|---|---|---|---|---|---|---|
| **R-1** | Case volume by period | Workload and trend over calendar time | `crime_cases.created_at` | date range, branch, category, status | day / week / month | period, count, Δ vs previous | Investigator (own branch), supervisor, admin, commander | ✅ |
| **R-2** | Case volume by category | Which offence types dominate | `crime_cases.category` | date range, branch, severity | category | category, count, % of total | as R-1 | ✅ *(exists, unscoped/unfiltered)* |
| **R-3** | Case volume by branch / region / district | Comparative load across the force | `crime_cases.branch_id` → `police_branches` | date range, category, status | branch → district → region | branch, count, rate per branch | **Supervisor+** (an investigator seeing all branches defeats isolation) | ✅ |
| **R-4** | Case status distribution | Pipeline health | `crime_cases.status` | date range, branch, category | status | status, count, % | as R-1 | ⚠️ **requires D-25** — a free-text status column makes the distribution meaningless |
| **R-5** | Open vs closed, closure rate | Headline effectiveness | `crime_cases.status` | date range, branch, category | period | open, closed, closure rate | as R-1 | ⚠️ **requires D-25** |
| **R-6** | Case volume by location | Geographic concentration | `crime_cases.location` | date range, branch, category | location | location, count | as R-1 | ✅ *(free-text location limits quality — see §5)* |
| **R-7** | Time-of-day distribution | Deployment planning | `created_at` today; **should be** `incident_at` | date range, branch, category | 4 bands | band, count | as R-1 | ⚠️ **misleading as built** — it buckets *data-entry* time, not offence time. Correct only once incidents are linked (D-15) |
| **R-8** | Active suspect alerts by origin and role | Alert-list hygiene | `suspect_alerts.origin`, `role`, `alert_status` | date range, branch, role, status | origin × role | origin, role, count, oldest alert age | Investigator (own branch), supervisor | ⚠️ **requires `suspect_alerts.branch_id`** (N-1) — cannot be scoped at all today |
| **R-9** | Evidence volume per case / category | Evidential completeness; cases with no evidence | `case_evidence` | date range, branch, category, evidence type | case, category | case id, item count, types, cases with zero evidence | as R-1 | ✅ |
| **R-10** | Station incident volume | Station-level intake load | `crime_incidents.*` | date range, station, category, severity | station × category | station, category, severity, count | Station officer (own station), supervisor+ | ✅ *(no builder exists at all today)* |
| **R-11** | Victim demographics | Vulnerability and service planning | `crime_incidents.victim_*` | date range, station, category | gender, age band | gender, age band, count, anonymity rate | **Supervisor+ only** — sensitive; aggregate-only, suppress small cells (§5) | ✅ with safeguards |
| **R-12** | Reporting-party type distribution | How reports reach the police | `crime_incidents.reporting_party_type` | date range, station, category | party type | type, count, % | as R-10 | ✅ |
| **R-13** | Repeat-person analysis | Persons recurring across cases | `suspect_alerts.person_id`, `case_participants` | date range, branch, role, min occurrences | person | person ref, occurrences, roles, first/last seen | **Supervisor+** — a repeat-offender list is an intelligence product | ⚠️ needs `case_participants` + `branch_id` |
| **R-14** | Cross-unit person view | One person across crime, checkpoint, clearance | `persons.id` across tables | person, date range | person | unit, record ref, date, outcome | **Explicit permission + per-access audit.** This is the highest-risk report in the catalogue | ⚠️ needs the cross-unit access rule (§5, **D-41**) |
| **R-15** | Case ageing | Cases growing stale | `created_at` + `status` | date range, branch, category, assignee | age band (0-7 / 8-30 / 31-90 / 90+ days) | band, count, oldest case | as R-1 | ⚠️ **requires D-25** (needs a reliable "open" definition) |
| **R-16** | Time-to-closure | Investigation efficiency | **requires `crime_cases.closed_at`** | date range, branch, category | period, category | mean, median, p90 days to close | as R-1 | ⚠️ **requires CRR-208** (`closed_at` does not exist) |
| **R-17** | Per-investigator workload and outcomes | Supervision and fairness | **requires `case_assignments`** | date range, branch, officer, status | officer | officer, open, closed, mean age, closure rate | **Supervisor+ only.** Individual performance data — never visible peer-to-peer | ⚠️ **requires CRR-301** (no assignment model exists) |
| **R-18** | Branch comparison dashboard | Command oversight | `crime_cases.branch_id` + the above | date range, category | branch | branch, volume, closure rate, mean age, backlog | **Commander / admin only** | ⚠️ depends on R-5, R-15, R-16 |

### 3.1 Feasibility summary

| Status | Count | Reports |
|---|---|---|
| ✅ Buildable from existing columns | **7** | R-1, R-2, R-3, R-6, R-9, R-10, R-12 |
| ⚠️ Requires a model change or decision first | **11** | R-4, R-5, R-7, R-8, R-11, R-13, R-14, R-15, R-16, R-17, R-18 |
| ⛔ Blocked outright | 0 | — |

**No report in the catalogue is impossible.** Of the 18 reviewed, seven are buildable now and eleven are gated on work already specified in the
Crime Unit requirements — chiefly **D-25** (status vocabulary), **`suspect_alerts.branch_id`**,
**`closed_at`**, **`case_assignments`** and **`case_participants`**.

---

## 4. Missing reports — added to complete the catalogue

These were absent from the Phase 2 proposal. Each is justified by an operational or oversight need,
not added for completeness.

| # | Report | Why it is needed | Data sources | Feasible? |
|---|---|---|---|---|
| **R-19** | **Identification and false-match report** *(Fingerprint, but Crime-relevant)* | D-18 approved genuine biometric matching. Every 1:N search, its threshold, its outcome and every **confirmed false match** must be reportable — otherwise match accuracy cannot be monitored and a wrongful identification cannot be traced. Required to satisfy Fingerprint FPR-252 | biometric match-event log (new) | ⚠️ needs the biometric subsystem |
| **R-20** | **Intake-to-investigation conversion** | Answers *"how many reports became investigations, and how many were never actioned?"* — the single most important oversight question the current model cannot answer, and the direct justification for linking incidents to cases | `crime_incidents` + `case_incidents` link | ⚠️ needs **D-15 Option A** |
| **R-21** | **Audit and access report** | Who viewed, exported or altered which case, evidence or person record, over a period. Required for professional-standards enquiries, DPIA evidence and any misuse investigation. Cannot be produced from the current audit table because updates record no before/after values | `audit_events` (+ before/after, SR-11) | ⚠️ needs **CRR-903** |
| **R-22** | **Evidence integrity and custody report** | Items lacking a hash, failing re-verification, or with gaps in the custody chain. Without it, chain-of-custody is a claim rather than a control | `case_evidence` + `evidence_custody` | ⚠️ needs **CRR-705/706** |
| **R-23** | **Alert hygiene / expiry report** | Alerts never cleared, past review date, or active beyond the maximum lifetime. Directly addresses the finding that an alert is written `'Active alert'` and **never changes**, so a cleared person keeps flagging at checkpoints indefinitely | `suspect_alerts` lifecycle columns | ⚠️ needs **CRR-605/606** |
| **R-24** | **Data-quality exceptions report** | Cases with no category, no linked incident, no assignee, no evidence, or an unresolvable branch. Makes silent data decay visible instead of letting it corrupt every other report | all crime tables | ✅ buildable incrementally |

---

## 5. Reporting safeguards *(not optional)*

| ID | Safeguard |
|---|---|
| RPT-101 | **Small-cell suppression** on demographic reports (R-11, R-13): a cell below a configured threshold is suppressed, because a count of one in a district is an identification. Threshold is **D-42** |
| RPT-102 | **R-14 (cross-unit person view) requires an explicit permission and writes a per-access audit row.** It joins biometric, criminal and travel data about one named individual — it is the most privacy-sensitive output in the system and must not be reachable by default (**D-41**) |
| RPT-103 | **Individual performance reports (R-17) are supervisor-only** and never visible peer-to-peer |
| RPT-104 | Every export records the filters applied, so an exported figure can be reproduced and challenged |
| RPT-105 | Free-text `location` limits R-6 and R-18 quality. Either adopt a controlled location list or state the limitation on the report. Decision deferred, limitation must be disclosed |
| RPT-106 | Reports must not become a scope bypass: the drill-down link uses the **same** scoped list endpoint, never a privileged query |

---

## 6. What the owner is asked to sign off

| Question | Agent recommendation |
|---|---|
| **1. Which reports are in Release 1.0?** | **Tier 1 (ship):** R-1, R-2, R-3, R-6, R-9, R-10, R-12, R-24 — buildable now, and all require the scoping fix anyway. **Tier 2 (ship with their prerequisite):** R-4, R-5, R-7, R-8, R-13, R-15, R-16, R-17, R-18, R-20, R-23. **Tier 3 (sequence after the subsystem lands):** R-11, R-14, R-19, R-21, R-22 |
| **2. Is export required, and in which formats?** | Recommend **CSV + print-to-PDF** for Release 1.0. Export must be audited (**D-40**) |
| **3. Who may run each report?** | Adopt the matrix in §2.2, subject to **D-21** creating the supervisor role |
| **4. Is a statutory or command reporting format mandated?** | **Unknown — owner must answer.** If a prescribed format exists, it changes output fields across the catalogue |
| **5. Small-cell suppression threshold?** | **D-42** — recommend 5 as a starting point, subject to the DPIA |
| **6. Does R-14 proceed at all?** | Recommend **yes, but permissioned and fully audited** — it is operationally valuable and privacy-critical in equal measure (**D-41**) |

> **Tier 1 is not a reduced scope.** It is the set that can be delivered correctly without waiting on
> another decision. Tier 2 is sequenced by data dependency, not deprioritised.

---

## 7. Decisions arising

| ID | Decision | Status |
|---|---|---|
| **D-14** | Report catalogue | **Approved as starting point — final selection (§6) requires sign-off** |
| **D-40** | Is an exported report a controlled document? Formats, watermarking, retention of exports | **New** |
| **D-41** | Does the cross-unit person view (R-14) proceed, under which permission and audit rules? | **New** |
| **D-42** | Small-cell suppression threshold for demographic reporting | **New** |
| **D-25 / D-21 / D-15 / D-07** | Status vocabulary · supervisor role · incident-case link · scale | Open — each gates part of this catalogue |
