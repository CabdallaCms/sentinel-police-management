# Crime Unit — Requirements Proposal (PROPOSED, NOT APPROVED)

**Deliverable 3 of 8 · Phase 2 · Assessment only. Nothing here is approved or implemented.**
Branch `arena/6303ef2f-sentinel-police-management` · commit `a1c2478` · 2026-11-06

> **Status of this document.** Every requirement below is either (a) **derived from code that already exists** in this repository, with the file and line cited, or (b) marked **`[NEEDS OWNER APPROVAL]`** because the repository does not answer it.
> **No requirement was invented.** Where a capability is absent and the repository gives no indication of the intended behaviour, the requirement is stated as a **question to the owner**, not as a specification.

---

## 1. Scope reminder

`RELEASE_PLAN.md` §1 fixes the Crime Unit's Release 1.0 scope as **full Crime Unit operations, including advanced reports**, and forbids reducing it to basic case registration to meet a date.

---

## 2. Investigation: the `crime_cases` ↔ `crime_incidents` relationship (decision D-15)

### 2.1 What the code actually shows **[STATIC]**

| Property | `crime_cases` | `crime_incidents` |
|---|---|---|
| Created at | `server.py:292` | `server.py:374` |
| Primary identifier | `case_id` — `'CID-2026-' + (COUNT(*)+8)` `:9083` | `file_number` — `new_crime_file_number(c, station.code)` `:5082` |
| Module / role | `cid` → `CIDUnit` | `crimes` → `CIDUnit` (and `SystemAdmin`) |
| Endpoint | `/api/crime-cases` | `/api/crimes` |
| Branch scoping | `user_branch_scope(c, user, 'crime')` `:8260` | `user_branch_scope(c, user, 'police_station')` `:8557` |
| Mandatory links | none beyond branch | `station_id` **NOT NULL**, `officer_id` **NOT NULL** `:376-377` |
| Status vocabulary | `CASE_STATUSES` — 7 values `:1716` | `CRIME_STATUSES` — 5 values `:1708` |
| Default status | `'Reported'` | `'Reported / Open'` |
| Victim data | none | full block: anonymity flag, name, contact, NID, gender, age, address, statement `:384-387` |
| Participants | `suspect_alerts` rows | none |
| Evidence | `case_evidence` rows (unbounded) `:309` | two fixed columns `evidence1_*`, `evidence2_*` `:388-389` |
| Severity | none | `severity` ∈ `CRIME_SEVERITIES` `:380` |
| Incident time | none (only `created_at`) | `incident_at` **NOT NULL** `:379` |
| UI page | `#cid` + `#caseworkspace` | `#crimes` |

### 2.2 Findings

1. **There is no relationship.** No foreign key, no shared identifier, no conversion endpoint, no cross-reference column, and no code path that reads one while writing the other. **[STATIC]**
2. **They are not duplicates either.** `crime_incidents` is a *station intake / victim report* record; `crime_cases` is a *CID investigation file* record. Each has fields the other lacks.
3. **The natural operational reading** — a station takes a report (`crime_incidents`), and CID opens an investigation (`crime_cases`) from it — is **not implemented anywhere**, and must not be assumed.
4. **The branch-scoping mismatch is a live risk.** `/api/crimes` scopes a CID officer against `police_station` branches, not `crime` branches. If the officer's posting does not resolve to a `police_station` branch, `branch_scope_view()` returns `None` and the officer sees **every** incident nationally. Whether it resolves depends on branch data. **[STATIC]** / outcome **[NOT VERIFIED]**
5. **A third status vocabulary exists in the UI**: the case-workspace `<select>` offers Reported / Under Investigation / Submitted for Prosecution / Closed (`index.html:1730`) — matching neither constant list.

### 2.3 Options for the owner — `[NEEDS OWNER APPROVAL]` (D-15)

| Option | Description | Technical risk |
|---|---|---|
| **A — Link them** | `crime_incidents` is the station intake; CID converts an incident into a `crime_cases` investigation. Add a nullable `crime_cases.source_incident_id` FK and a convert action. | Low. Additive DDL. Preserves all existing data and both UIs. Requires one status-mapping decision. |
| **B — Merge them** | One `crime_cases` table absorbing the victim block, severity and `incident_at`; `crime_incidents` becomes a view or is migrated away. | **High.** Destructive migration, two UIs to rework, two status vocabularies to reconcile, both branch-scoping models to unify. Not advisable inside Release 1.0. |
| **C — Keep separate, formalise** | Document them as two deliberately distinct registers with no link; fix only the branch-scoping mismatch. | Lowest. But leaves the operational question ("where does an investigation come from?") unanswered. |

**Recommended technical option: A.** It is additive, reversible, preserves history, and matches the field asymmetry already in the schema. **Risk of A:** it introduces a conversion workflow that needs its own permissions, audit and tests, and it commits the project to one status mapping. **This is the owner's decision, not the agent's.**

---

## 3. Investigation: existing reports and advanced reporting capability

### 3.1 What exists today **[STATIC]**

**One** report surface serves the Crime Unit: the `crime` section of `GET /api/cid/analytics`, built by `cid_crime_analytics(c)` at `server.py:6132-6172`.

**Metrics produced:**

| Metric | Definition in code |
|---|---|
| `total_cases` | row count of `crime_cases` |
| `open_cases` | total − closed |
| `closed_cases` | rows whose `status` lowercases to `'closed'` |
| `closure_rate` | `pct(closed, total)` |
| `active_suspects` | `COUNT(*)` of `suspect_alerts` where `role='Suspect'` and `alert_status='Active alert'` |
| `categories_tracked` | distinct categories present |
| `top_category` | most frequent category |

**Charts produced:** `by_location` · `by_time_of_day` (4 fixed bands) · `by_category` (axis = `CRIME_CATEGORIES`) · `by_status` (axis = `CASE_STATUSES`) · `open_vs_closed`.

**Related surfaces:** `GET /api/analytics?module=cid` (same builder) · `GET /api/admin/analytics` (admin aggregate) · `GET /api/analytics/global` (Commander executive dashboard).

### 3.2 Honest capability verdict

| Advanced-reporting capability | Present? | Evidence |
|---|---|---|
| Fixed KPI tiles and category/status/location/time charts | **Yes** | `:6154-6170` |
| **Any filter at all** (date range, category, status, branch, officer, severity) | **No** — the builder takes no parameters and the route reads no query string | `:6132`, `:8353` |
| **Branch scoping of the numbers** | **No** — `cid_crime_analytics(c)` receives no `user`; contrast `cid_checkpoint_analytics(c, user)` `:6176` | `:6319-6320` |
| Export (CSV / PDF / print) | **No** | no export route or handler |
| Scheduled or saved reports | **No** | — |
| Time-series / trend over a period | **No** — `by_time_of_day` buckets hour-of-day, not dates | `:6163-6165` |
| Clearance/closure **time** (days to close) | **No** — `crime_cases` has no closed-at timestamp | DDL `:292` |
| Per-officer or per-investigator productivity | **No** — no assignment data exists | — |
| Per-station reporting | **No** for `crime_cases` (no station link) | — |
| Suspect outcome reporting | **No** — `alert_status` never changes from `'Active alert'` | `:9205` |
| Victim/demographic reporting | **Only** possible from `crime_incidents`, which has no report builder at all | `:384-387` |
| Drill-down from a chart to the underlying records | **No** | `'lists': {}` `:6171` |

**Conclusion: a basic dashboard exists; advanced reporting does not.** Classify current state as **Partially implemented**. Everything in §9 below is new work.

---

## 4. Proposed requirements — Case registration

| ID | Requirement | Basis |
|---|---|---|
| CR-01 | A CID officer may register a case with category, location, status, incident summary and notes. | **Exists** `:9080-9091` |
| CR-02 | `category` is mandatory; the API rejects a missing category with 400. | **Exists** `:9082` |
| CR-03 | A case is filed under exactly one branch; a scoped officer may only file under their own branch (403 otherwise). | **Exists** `:9081` |
| CR-04 | Case identifiers are unique, collision-safe under concurrency, and **not year-hard-coded**. | **Gap** — `'CID-2026-' + COUNT(*)+8` `:9083` |
| CR-05 | `category` must be validated against a controlled list. | **Gap** — `CRIME_CATEGORIES:1705` exists but is **not enforced** on `/api/crime-cases` |
| CR-06 | The incident date/time must be recorded separately from the record-creation time. | **Gap** — `crime_cases` has only `created_at` |
| CR-07 | Severity must be recorded. | **Gap** — exists on `crime_incidents` only |
| CR-08 | Case creation writes an audit row. | **Exists** `:9088` |
| CR-09 | `[NEEDS OWNER APPROVAL]` Is a case ever created from a station incident report, and if so by whom? | **D-15** |
| CR-10 | `[NEEDS OWNER APPROVAL]` Required minimum fields at registration, and whether a case may be registered without a known victim or suspect. | — |

## 5. Proposed requirements — Case assignment

> **Nothing in this section exists.** `crime_cases` has no assignment column; no endpoint assigns a case. **[STATIC]**

| ID | Requirement | Status |
|---|---|---|
| CA-01 | A case can be assigned to a named investigating officer. | **Not implemented** |
| CA-02 | Assignment is recorded with who assigned it, to whom, and when, and is audited. | **Not implemented** |
| CA-03 | A case can be reassigned, with reason, preserving the previous assignment in history. | **Not implemented** |
| CA-04 | A case can have a supervisor distinct from the investigator. | **Not implemented** |
| CA-05 | `[NEEDS OWNER APPROVAL]` Who may assign — any CID officer, a unit chief, or an administrator? | **D-21** |
| CA-06 | `[NEEDS OWNER APPROVAL]` May a case be assigned across branches? | **D-21** |
| CA-07 | `[NEEDS OWNER APPROVAL]` Is assignment mandatory before a case can leave `Reported`? | **D-21** |

## 6. Proposed requirements — Investigation workflow

> **Nothing in this section exists.** There is no task, action, timeline or deadline model. **[STATIC]**

| ID | Requirement | Status |
|---|---|---|
| IW-01 | An investigator can log investigative actions against a case (date, action, officer, outcome). | **Not implemented** |
| IW-02 | Actions are immutable once recorded, or amendable only with an audited correction. | **Not implemented** |
| IW-03 | A case carries a chronological timeline assembled from registration, assignment, actions, evidence, participants and status changes. | **Partially** — `audit_events` already records most of these; no timeline view exists |
| IW-04 | `[NEEDS OWNER APPROVAL]` Are there mandatory investigative steps or deadlines per category? | **D-22** |
| IW-05 | `[NEEDS OWNER APPROVAL]` Is supervisory review required at any point before closure? | **D-22** |
| IW-06 | `[NEEDS OWNER APPROVAL]` Does the unit need inter-branch case referral? | **D-22** |

## 7. Proposed requirements — Suspect management

| ID | Requirement | Basis |
|---|---|---|
| SM-01 | A person can be listed as Suspect, Victim, Witness or Complainant against a case. | **Exists** `:9205` (`role` column) |
| SM-02 | A suspect may be listed **without** a case; origin recorded as `Direct Intelligence Listing` or `Manual Entry`. | **Exists** `:9186-9187` |
| SM-03 | An unlinked suspect listing requires a written reason. | **Exists** `:9183-9185` |
| SM-04 | A duplicate active alert for the same person (+case) is refused with 409. | **Exists** `:9194-9202` |
| SM-05 | An active `Suspect` alert flags the person at checkpoints. | **Exists** `:9304-9307` |
| SM-06 | A suspect alert must be **branch-scoped**: a scoped officer sees and creates alerts only for their own branch. | **Gap — security.** `suspect_alerts` has **no `branch_id` column** (DDL `:299`); `GET /api/suspect-alerts` applies **no filter at all** `:8425`; `POST` applies none `:9172` |
| SM-07 | A suspect alert can be **cleared, closed or resolved** with a reason and an audit trail. | **Gap** — `alert_status` is only ever written as `'Active alert'` |
| SM-08 | Suspect status progression (e.g. wanted → arrested → charged → released → cleared) is recorded. | **Not implemented** |
| SM-09 | Linking a suspect to a case must verify the case is in the officer's branch. | **Gap** — `:9176-9178` looks the case up with no scope check |
| SM-10 | Victims and witnesses should not be stored in a table named and semantically treated as "suspect alerts". | **Gap — modelling** |
| SM-11 | `[NEEDS OWNER APPROVAL]` Legal rules for listing a suspect: who authorises, what evidence threshold, what notification, how long an alert may stay active. | **D-23** |
| SM-12 | `[NEEDS OWNER APPROVAL]` Must a supervisor confirm a possible identity match before an alert is acted on? (Raised by the prior audit's open questions.) | **D-23** |

## 8. Proposed requirements — Evidence management

| ID | Requirement | Basis |
|---|---|---|
| EM-01 | Evidence files can be attached to a case with a caption and a type. | **Exists** `:9092-9105`; `EVIDENCE_TYPES:1743` |
| EM-02 | Each evidence item records who uploaded it and when. | **Exists** `case_evidence.uploaded_by`, `created_at` |
| EM-03 | Evidence upload is **branch-scoped**. | **Gap — security.** `:9092-9095` resolves the case by `case_id` with no scope check |
| EM-04 | Evidence files are **not retrievable without authentication**. | **Gap — security.** `/uploads/` served before auth `:7914` |
| EM-05 | Evidence uploads are validated for type and size. | **Gap.** `save_upload()` performs no validation `:3939` |
| EM-06 | Evidence has an integrity hash recorded at upload. | **Not implemented** |
| EM-07 | **Chain of custody**: every access, transfer and handover is recorded. | **Not implemented** |
| EM-08 | Evidence can be corrected or withdrawn, with an audited reason; never silently deleted. | **Not implemented** — no DELETE route exists |
| EM-09 | `[NEEDS OWNER APPROVAL]` Legal requirements for evidence custody, admissibility, retention and disposal. | **D-04 / D-24** |

## 9. Proposed requirements — Case status and progression

| ID | Requirement | Basis |
|---|---|---|
| CS-01 | A case has a status drawn from one controlled vocabulary. | **Gap — four vocabularies exist**: `CASE_STATUSES` (7) `:1716`, `CRIME_STATUSES` (5) `:1708`, the workspace `<select>` (4) `index.html:1730`, and whatever free text a PATCH supplies |
| CS-02 | Status changes are validated against allowed transitions. | **Not implemented** — PATCH accepts any string `:9586` |
| CS-03 | Each status change records who, when and why. | **Not implemented** — only a generic `UPDATE` audit row `:9591` |
| CS-04 | Status changes are **branch-scoped**. | **Gap — security.** PATCH has no scope check `:9581` |
| CS-05 | Closure requires authorisation and a closure reason. | **Not implemented** |
| CS-06 | A closed case can be reopened, with reason and audit. | **Not implemented** |
| CS-07 | `[NEEDS OWNER APPROVAL]` The authoritative status list and the permitted transitions. | **D-25** |
| CS-08 | `[NEEDS OWNER APPROVAL]` Who may close a case? | **D-25** |

## 10. Proposed requirements — Officer responsibilities and permissions

| ID | Requirement | Basis |
|---|---|---|
| OP-01 | Only the `cid` module may reach crime-case and suspect endpoints. | **Exists** `:8101-8102`, `:8874-8875` |
| OP-02 | The read-only Commander can read everything and write nothing. | **Exists** `enforce_read_only()` |
| OP-03 | Branch isolation applies to every Crime Unit operation. | **Partial** — list/detail/create only |
| OP-04 | Distinct roles for investigator, supervisor and unit chief. | **Not implemented** — one `CIDUnit` role `:1875` |
| OP-05 | Case-level permissions (only the assigned investigator and their supervisor may edit). | **Not implemented** |
| OP-06 | `[NEEDS OWNER APPROVAL]` The CID role structure and whether case-level permissions are required. | **D-21** |

## 11. Proposed requirements — Search and filtering

| ID | Requirement | Basis |
|---|---|---|
| SF-01 | Free-text search across the case register. | **Exists, client-side only** (`index.html` `#cid` search box) |
| SF-02 | Server-side filtering by status, category, branch, date range, severity, assigned officer. | **Not implemented** — `:8259` reads no query parameters |
| SF-03 | Server-side pagination. | **Not implemented** — `ORDER BY cc.id DESC` with no `LIMIT` `:8271` |
| SF-04 | Search across participants (by person, NID, passport). | **Partial** — `/api/suspect-alerts` returns everything unfiltered |
| SF-05 | Filters must respect branch isolation. | **Prerequisite:** SM-06, CS-04 |
| SF-06 | `[NEEDS OWNER APPROVAL]` Required filter set and default sort order. | **D-26** |

## 12. Proposed requirements — Advanced reports and statistics

> **`[NEEDS OWNER APPROVAL]` — decision D-14.** The list below is a **menu derived from fields that already exist in the schema**, offered so the owner can select. It is **not** a specification, and nothing here is committed.

### 12.1 Candidate report types (all derivable from existing columns)

| # | Candidate report | Source columns that already exist | Currently |
|---|---|---|---|
| R-1 | Case volume by period (day/week/month) | `crime_cases.created_at` | Not implemented (only hour-of-day) |
| R-2 | Case volume by category | `category` | **Exists** (unfiltered, unscoped) |
| R-3 | Case volume by branch / region / district | `branch_id` → `police_branches` | Not implemented |
| R-4 | Case status distribution | `status` | **Exists** (unfiltered, unscoped) |
| R-5 | Open vs closed, and closure rate | `status` | **Exists** (unfiltered, unscoped) |
| R-6 | Case volume by location | `location` | **Exists** (unfiltered, unscoped) |
| R-7 | Time-of-day distribution | `created_at` | **Exists** (unfiltered, unscoped) |
| R-8 | Active suspect alerts, by origin and role | `suspect_alerts.origin`, `role`, `alert_status` | Count only |
| R-9 | Evidence volume per case / per category | `case_evidence` | Not implemented |
| R-10 | Station incident volume by station, category, severity | `crime_incidents.*` | **No report builder at all** |
| R-11 | Victim demographics (gender, age band, anonymity rate) | `crime_incidents.victim_*` | Not implemented |
| R-12 | Reporting-party type distribution | `crime_incidents.reporting_party_type` | Not implemented |
| R-13 | Repeat-offender / repeat-person analysis | `suspect_alerts.person_id` | Not implemented |
| R-14 | Cross-unit person view (crime ↔ checkpoint ↔ clearance) | `persons.id` across tables | Partially, via person profile |
| R-15 | Case ageing (open cases by age band) | `created_at` + `status` | Not implemented |
| R-16 | Time-to-closure | **requires a new `closed_at` column** | Not implemented |
| R-17 | Per-investigator workload and outcomes | **requires case assignment (CA-01)** | Not implemented |
| R-18 | Branch comparison dashboard | `branch_id` | Not implemented |

### 12.2 Candidate filters

Date range (from/to) · category · status · branch / region / district · severity (needs CR-07) · location · assigned officer (needs CA-01) · suspect role · alert status · origin · station (incidents) · victim anonymity.

### 12.3 Candidate metrics

Counts · distinct persons · rates (closure, flag, repeat) · averages (evidence per case, age of open cases) · period-over-period change · branch comparison.

### 12.4 Access permissions — proposed, `[NEEDS OWNER APPROVAL]`

| Audience | Proposed scope of reports |
|---|---|
| `CIDUnit` officer | **Own branch only.** Today they receive national figures — this must change (see §13, finding X-2). |
| CID unit chief *(role does not exist)* | Own branch, plus per-officer breakdowns |
| `SystemAdmin` | All branches |
| `chief_commander` | All branches, read-only (already has `analytics:global`) |
| Any other role | No access |

### 12.5 Non-functional requirements for reports — proposed

Reports must be **branch-scoped by default**; must never expose a record the caller could not open directly; must declare every metric's definition (as `cid_fingerprint_analytics` already does in its docstring `:6074-6083`); must be covered by tests pinning the arithmetic; and export, if approved, must be audited.

### 12.6 Blocking questions for D-14

1. Which of R-1 … R-18 are in Release 1.0?
2. Which filters are mandatory?
3. Is export required? In which formats? Is an exported police report itself a controlled document?
4. Who may run each report?
5. Are reports needed for `crime_incidents` as well as `crime_cases` — i.e. does D-15 change the answer?
6. Is any statutory or command reporting format mandated?

## 13. Proposed requirements — Audit history

| ID | Requirement | Basis |
|---|---|---|
| AH-01 | Create, update, approve and upload actions on crime records write audit rows with badge attribution. | **Exists** `audit()` `:4032`; calls at `:9088`, `:9103`, `:9207`, `:9591` |
| AH-02 | Per-record audit history is retrievable and branch-scoped. | **Exists** `:4281`; `AUDIT_ENTITY_MODULES` maps `crime_case`→`crimes`, `suspect_alert`→`cid` `:4123-4124` |
| AH-03 | Audit entries record **before/after values** for updates. | **Gap** — `audit(c,user,'UPDATE','crime_case',cid)` passes no detail `:9591` |
| AH-04 | Authentication events (login success/failure, logout) are audited. | **Not implemented** |
| AH-05 | Audit rows are append-only and tamper-evident. | **Not implemented** — plain table, no integrity control |
| AH-06 | Audit retention is defined. | **Blocked** — **D-04** |

---

## 14. Cross-cutting findings specific to the Crime Unit

| ID | Finding | Evidence |
|---|---|---|
| **X-1** | **`suspect_alerts` cannot be branch-isolated without a schema change** — there is no `branch_id` column. This is the only Release 1.0 gap that *requires* DDL to close. | DDL `:299-308` |
| **X-2** | **Crime reports leak across branches.** `cid_crime_analytics(c)` takes no user. | `:6132`, `:6319` |
| **X-3** | **Three write paths bypass branch isolation**: PATCH case `:9581`, POST evidence `:9092`, POST suspect alert `:9172`. | **[STATIC]** |
| **X-4** | **`GET /api/suspect-alerts` has no scoping of any kind.** | `:8425-8432` |
| **X-5** | **No dedicated test suite exists for the Crime Unit.** Coverage is incidental. | test inventory |
| **X-6** | **`case_id` hard-codes the year 2026.** Cases created in 2027 will be labelled `CID-2026-…`. | `:9083` |

---

## 15. New decisions raised by this proposal

| ID | Decision |
|---|---|
| **D-14** | Define "advanced reports": which of R-1…R-18, which filters, which metrics, export formats, and who may run each. *(Pre-existing, now itemised.)* |
| **D-15** | The `crime_cases` ↔ `crime_incidents` relationship — Option A, B or C (§2.3). *(Pre-existing, now analysed.)* |
| **D-21** | CID role structure: investigator / supervisor / unit chief; who assigns cases; whether case-level permissions are required. |
| **D-22** | Investigation workflow: mandatory steps, deadlines, supervisory review, inter-branch referral. |
| **D-23** | Legal rules for suspect listing: authorisation, evidence threshold, alert lifetime, supervisor confirmation of identity matches. |
| **D-24** | Evidence chain-of-custody and admissibility requirements. |
| **D-25** | The authoritative case status vocabulary and permitted transitions; who may close and reopen a case. |
| **D-26** | Required search filters, default sort, and whether pagination is needed at expected volumes (relates to **D-07**). |

---

## 16. Summary for the owner

- **What exists:** case registration, a case workspace, participant/suspect listing with optional case linkage, evidence upload, station incident intake with a victim block, and one fixed analytics bundle.
- **What does not exist:** case assignment, investigation workflow, suspect lifecycle, chain of custody, closure control, a single status model, server-side search and filtering, and advanced reports as a defined capability.
- **What is unsafe today:** three unscoped write paths, one entirely unscoped read path, unscoped reports, and a suspect table with no branch column at all.
- **What is undecided:** eight decisions (D-14, D-15, D-21 … D-26), of which **D-14 and D-15 block scheduling** — the Crime Unit's size cannot be estimated until both are answered.

**This document is a proposal. No requirement here is approved, and no implementation has begun.**
