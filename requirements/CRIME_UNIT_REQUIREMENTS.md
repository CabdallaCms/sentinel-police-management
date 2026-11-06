# Crime Unit — Operational Requirements (Release 1.0)

**Phase 3 deliverable B · Requirements only. No application code was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Supersedes** `assessment/CRIME_UNIT_REQUIREMENTS.proposed.md` (Phase 2), which remains in the
> repository as the record of the earlier proposal. Where the two differ, **this document governs**.
> The Phase 2 document is not deleted or rewritten.
>
> **Scope basis:** `RELEASE_PLAN.md` §1 — full Crime Unit operations **including advanced reports**.
> Scope must not be reduced to basic case registration to meet a date.
>
> **Data-model basis:** this document is written against **Option A** of
> `architecture/CRIME_DATA_MODEL_DECISION.md` (incidents and cases separate, explicitly linked,
> one case to many incidents). **Option A is a recommendation pending owner decision D-15.** If the
> owner chooses otherwise, §3 and the report catalogue change; the rest stands.

---

## 0. How each workflow is specified

Per the brief, every major workflow below defines: **actors and permissions · starting conditions ·
steps and decisions · required data · status transitions · exceptions and rejection paths · audit
events · acceptance criteria.**

Requirements are marked:
- **[EXISTS]** — implemented today, cited to file and line; retained
- **[FIX]** — exists but is defective; must change
- **[NEW]** — does not exist
- **[DECISION]** — cannot be specified until the owner answers

---

## 1. Actors, roles and permissions

| Actor | Role today | Release 1.0 requirement |
|---|---|---|
| **CID investigator** | `CIDUnit` — `{dashboard, people, cid, crimes}` `:1876` | Register cases, work assigned cases, log actions, manage participants and evidence, run reports for own branch |
| **CID supervisor** | **Does not exist** | **[NEW]** Assign and reassign cases, approve closure, adjudicate participant listings, override status transitions, run per-officer reports |
| **Station intake officer** | writes `crime_incidents` via `POST /api/crimes` | Record incident reports; **no** access to CID investigation files |
| **System administrator** | `SystemAdmin` | User/branch administration. **Not** an investigative role |
| **Commander** | `chief_commander` | Read-only across all branches (`enforce_read_only()`) |
| Every other role | — | No access; enforced by the `cid` / `crimes` module gates `:8101`, `:8874` |

| ID | Requirement |
|---|---|
| CRR-001 | **[EXISTS]** Only the `cid` and `crimes` modules reach Crime Unit endpoints. |
| CRR-002 | **[NEW]** A **CID supervisor** role is created (**D-21**). Investigation and approval authority must be separable. |
| CRR-003 | **[FIX]** **Every** Crime Unit read and write is branch-scoped. Today the list/detail/create routes scope; `PATCH /api/crime-cases/<id>` (`:9581`), `POST .../evidence` (`:9092`) and `POST /api/suspect-alerts` (`:9172`) do not. |
| CRR-004 | **[DECISION]** Case-level permissions — may any branch investigator edit any branch case, or only the assignee and their supervisor? (**D-21**) |
| CRR-005 | **[EXISTS]** The read-only Commander can read everything and write nothing. |

---

## 2. Workflow — Incident intake (station first report)

**Actors:** station intake officer · **Precondition:** authenticated; posting resolves to a station

| Element | Specification |
|---|---|
| **Steps** | Record reporting party type → victim block (or anonymous) → category, severity, `incident_at`, location → description and statement → up to two evidence attachments → file number issued |
| **Required data** | `station_id`, `officer_id`, `category`, `incident_at`, `description` (all **NOT NULL** today) |
| **Status** | `CRIME_STATUSES`: Reported / Open → Under Investigation → Referred to Court → Closed · Unresolved |
| **Exceptions** | Anonymous reporting supported (`victim_anonymous`); a report may be filed with **no further action** (**D-39**) |
| **Audit** | `CREATE crime_incident` with file number and station |

| ID | Requirement |
|---|---|
| CRR-101 | **[EXISTS]** Incident capture with victim block, severity, event time and reporting-party type. |
| CRR-102 | **[FIX]** `GET /api/crimes` scopes CID officers against `police_station` branches (`:8557`) while CID postings resolve as `crime`; an unresolvable posting **fails open** to a national view. Must fail closed. |
| CRR-103 | **[FIX]** Evidence is limited to **two fixed columns** (`evidence1_*`, `evidence2_*`). Replace with rows in a shared evidence table. |
| CRR-104 | **[NEW]** An incident can be explicitly closed as *no further action* with a reason, so "not actioned" is distinguishable from "awaiting action" (**D-39**). |
| CRR-105 | **[EXISTS]** `file_number` is station-coded (`new_crime_file_number()` `:5082`) — retained unchanged. |
| **Acceptance** | A station officer sees only their station's incidents; an unresolvable posting is **denied, not widened**; an anonymous report stores no victim identity |

---

## 3. Workflow — Case registration and incident linking

**Actors:** CID investigator · **Precondition:** authenticated; posting resolves to a `crime` branch

| Element | Specification |
|---|---|
| **Steps** | Open case (category, location, summary) **or** open a case *from* an incident → case id issued → optionally link further incidents |
| **Required data** | `category` (validated), `branch_id`, summary |
| **Status** | Opens at `Reported`; see §6 |
| **Exceptions** | A case may exist with **no** linked incident (intelligence-led). A link may be removed with a reason |
| **Audit** | `CREATE crime_case` · `LINK incident→case` · `UNLINK incident→case` (actor, timestamp, reason) |

| ID | Requirement |
|---|---|
| CRR-201 | **[EXISTS]** Case registration with category, location, status, summary and notes (`:9080`). |
| CRR-202 | **[FIX]** `category` is **not validated** against `CRIME_CATEGORIES` (`:1705`) on `/api/crime-cases`. It must be. |
| CRR-203 | **[FIX]** `case_id` = `'CID-2026-' + COUNT(*)+8` (`:9083`) — hard-coded year, global counter, race-prone. Replace with a year-scoped sequence generated in-transaction with a unique constraint. **Existing identifiers are never rewritten.** |
| CRR-204 | **[NEW]** A case can be opened **from** an incident, carrying over category, location, severity and `incident_at`, and creating the link. |
| CRR-205 | **[NEW]** A case may link **many** incidents; an incident may, where operationally necessary, link to more than one case. Exactly one link may be marked `is_primary`. |
| CRR-206 | **[NEW]** Linking records actor, timestamp and `link_reason`. Unlinking requires a reason and is audited. |
| CRR-207 | **[DECISION]** Cross-branch linking authority (**D-38**). |
| CRR-208 | **[NEW]** `crime_cases` gains `severity` and `closed_at` (the latter is a precondition for time-to-closure reporting). |
| **Acceptance** | An invalid category is refused with 400 · 100 concurrent registrations yield 100 distinct ids · a case created in 2027 is labelled `2027` · a cross-branch link without authority is refused and audited |

---

## 4. Workflow — Case assignment

**Nothing in this section exists.** `grep assigned_to|investigator|assignee|officer_in_charge` → **0**.

| Element | Specification |
|---|---|
| **Actors** | CID supervisor assigns; investigator receives |
| **Precondition** | Case exists in the supervisor's branch |
| **Steps** | Select case → select investigator (same branch unless authorised) → optionally set supervisor → record reason → notify |
| **Required data** | `case_id`, `assignee_user_id`, `assigned_by`, `assigned_at`, `reason`, optional `supervisor_user_id` |
| **Transitions** | Assignment is a precondition for leaving `Reported` (**D-21**) |
| **Exceptions** | Reassignment preserves history; unassignment requires a reason; an assignee who is deactivated leaves the case flagged *unassigned — action required* |
| **Audit** | `ASSIGN` · `REASSIGN` · `UNASSIGN`, each with from/to and reason |

| ID | Requirement |
|---|---|
| CRR-301 | **[NEW]** A case can be assigned to a named investigating officer. |
| CRR-302 | **[NEW]** Assignment history is retained in full; the current assignee is derived from the latest row. |
| CRR-303 | **[NEW]** A case may have a supervisor distinct from the investigator. |
| CRR-304 | **[DECISION]** Who may assign; may assignment cross branches; is assignment mandatory before investigation begins (**D-21**). |
| CRR-305 | **[NEW]** Deactivating a user must surface their open assignments rather than orphaning them silently. |
| **Acceptance** | Assignment, reassignment and unassignment are each audited with reason · a non-supervisor cannot assign · an unassigned case cannot reach `Under Investigation` (if D-21 so decides) · deactivating a user lists their open cases |

---

## 5. Workflow — Investigation

| Element | Specification |
|---|---|
| **Actors** | Assigned investigator; supervisor |
| **Precondition** | Case assigned (subject to D-21) |
| **Steps** | Log investigative actions (date, type, description, outcome) → attach evidence → add participants → request supervisory review → progress status |
| **Required data** | `case_id`, `action_at`, `action_type`, `description`, `officer_id` |
| **Transitions** | Actions do not themselves change status; status changes are explicit (§6) |
| **Exceptions** | An action may be **corrected** only by an audited amendment that preserves the original; never silently edited or deleted |
| **Audit** | `ACTION_LOGGED` · `ACTION_AMENDED` |

| ID | Requirement |
|---|---|
| CRR-401 | **[NEW]** An append-only investigative action log per case. |
| CRR-402 | **[NEW]** A case timeline assembled from registration, linking, assignment, actions, participants, evidence and status changes. *(Most components already land in `audit_events`; no timeline view exists.)* |
| CRR-403 | **[DECISION]** Mandatory investigative steps or statutory deadlines per category (**D-22**). |
| CRR-404 | **[DECISION]** Is supervisory review mandatory before closure (**D-22**)? |
| CRR-405 | **[DECISION]** Inter-branch case referral (**D-22**). |
| **Acceptance** | An action cannot be deleted · an amendment retains the original and records who amended it and why · the timeline reconstructs the full case history in order |

---

## 6. Workflow — Case status and progression

**Current state is incoherent and is a release blocker for reporting:** four competing vocabularies —
`CASE_STATUSES` (7, `:1716`), `CRIME_STATUSES` (5, `:1708`), the case-workspace `<select>` (4,
`index.html:1730`), and **free text accepted by `PATCH /api/crime-cases/<id>`** (`:9586`).

### 6.1 Proposed case lifecycle *(pending D-25)*

```
Reported ─► Assigned ─► Under Investigation ─┬─► Submitted for Prosecution ─► Referred to Court ─► Closed
                              │              │
                              ├─► On Hold ───┘
                              └─► Unresolved / Suspended ─► (reopen) ─► Under Investigation
                                                     Closed ─► (reopen, authorised) ─► Under Investigation
```

> Per `architecture/CRIME_DATA_MODEL_DECISION.md` §4.2, the **incident** keeps its own separate
> lifecycle (`CRIME_STATUSES`). The recommendation is **not** to force one vocabulary onto both
> object types.

| ID | Requirement |
|---|---|
| CRR-501 | **[FIX]** One authoritative case vocabulary, enforced server-side. **Free-text status is refused.** |
| CRR-502 | **[NEW]** A transition table defines permitted moves; an illegal transition returns 400 and is audited. |
| CRR-503 | **[NEW]** `case_status_history` records every transition: actor, timestamp, from, to, reason. |
| CRR-504 | **[FIX]** `PATCH /api/crime-cases/<id>` must enforce branch scope (it does not today, `:9581`). |
| CRR-505 | **[NEW]** Closure requires authorisation (supervisor) and a closure reason; sets `closed_at`. |
| CRR-506 | **[NEW]** Reopening a closed case is possible, authorised, reasoned and audited. |
| CRR-507 | **[DECISION]** The authoritative vocabulary, permitted transitions and closure authority (**D-25**). |
| **Acceptance** | Free-text status is refused · an illegal transition is refused and audited · cross-branch status change is refused · closure without reason is refused · `closed_at` is set on closure and cleared with history on reopen |

---

## 7. Workflow — Persons, suspects, victims and witnesses

**Current state:** participants exist **only** as `suspect_alerts` rows, so victims and witnesses are
stored in a table named and semantically treated as "suspect alerts". `case_participants` does not
exist (verified: `grep -c` → **0**).

| ID | Requirement |
|---|---|
| CRR-601 | **[NEW]** `case_participants` separates the *role of a person in a case* (Suspect / Victim / Witness / Complainant / Person of Interest) from the *operational alert* on a person. |
| CRR-602 | **[FIX]** `suspect_alerts` becomes a genuine alert: it gains **`branch_id`** (it has none — DDL `:299`) and a **lifecycle**. |
| CRR-603 | **[FIX]** `GET /api/suspect-alerts` (`:8425`) applies **no filter of any kind** — every officer nationwide reads every suspect, victim and witness listing. It must be branch-scoped. **This is the only Release 1.0 access-control gap that cannot be closed without DDL.** |
| CRR-604 | **[FIX]** `POST /api/suspect-alerts` (`:9172`) must enforce branch scope, including on the case it links to (`:9176` looks the case up unscoped). |
| CRR-605 | **[NEW]** Alert lifecycle: `Active` → `Suspended` → `Cleared` / `Closed` / `Expired`, each with reason, actor and timestamp. Today `alert_status` is only ever written as `'Active alert'` (`:9205`) and **never changes** — a person cleared by CID keeps flagging at every checkpoint indefinitely. |
| CRR-606 | **[NEW]** Alerts carry an expiry or a mandatory review date (**D-23**). |
| CRR-607 | **[EXISTS]** Duplicate active alerts for the same person+case are refused with 409 (`:9194`). Retained. |
| CRR-608 | **[EXISTS]** An unlinked listing requires a written reason (`:9183`). Retained and extended to require an explicit branch. |
| CRR-609 | **[DECISION]** Authorisation, evidence threshold, maximum alert lifetime, and whether a supervisor must confirm an identity match before an alert is acted on (**D-23**). |
| CRR-610 | **[NEW]** Victim data in `crime_incidents` links to `persons` where identified, while preserving anonymous reporting. |
| **Acceptance** | A branch-A officer sees only branch-A alerts (asserted on record ids, not counts) · clearing an alert stops checkpoint flagging within one request cycle · a victim is not stored as a "suspect alert" · an expired alert no longer flags |

---

## 8. Workflow — Evidence and document management

| ID | Requirement |
|---|---|
| CRR-701 | **[EXISTS]** Evidence attaches to a case with caption and type (`EVIDENCE_TYPES` `:1743`), recording uploader and timestamp. |
| CRR-702 | **[FIX]** `POST /api/crime-cases/<id>/evidence` (`:9092`) has **no branch check**. |
| CRR-703 | **[FIX]** Evidence files are retrievable **without authentication** via `/uploads/` (`:7914`). See security requirement **SR-01**. |
| CRR-704 | **[FIX]** `save_upload()` (`:3939`) applies **no extension, MIME or size validation**, unlike `/signed-document` (`:9009`) which does both. |
| CRR-705 | **[NEW]** Each evidence item stores a **SHA-256 hash** computed at upload; integrity is verifiable later. |
| CRR-706 | **[NEW]** **Chain of custody**: every access, transfer, handover and export is recorded with actor, timestamp and reason. |
| CRR-707 | **[NEW]** Evidence may be **withdrawn** with an audited reason; it is never silently deleted. There is no DELETE route today. |
| CRR-708 | **[NEW]** Evidence is addressable as a first-class object with its own authorization, not a JSON blob in a TEXT column. |
| CRR-709 | **[DECISION]** Legal requirements for custody, admissibility, retention and disposal (**D-24**, **D-04**). |
| **Acceptance** | Cross-branch evidence upload refused · anonymous retrieval refused · disallowed type and oversized file refused · stored hash matches bytes on re-verification · every access appears in the custody log · withdrawal preserves the record |

---

## 9. Workflow — Search and filtering

| ID | Requirement |
|---|---|
| CRR-801 | **[FIX]** Server-side filtering: status, category, branch, date range, severity, assignee, location. Today `:8259` reads **no query parameters**. |
| CRR-802 | **[FIX]** Server-side pagination — `ORDER BY cc.id DESC` with **no LIMIT** (`:8271`). |
| CRR-803 | **[NEW]** Participant search by person, national ID, passport — branch-scoped. |
| CRR-804 | **[NEW]** All filters respect branch isolation; a filter must never widen scope. |
| CRR-805 | **[DECISION]** Required filter set, default sort, page size (**D-26**, informed by **D-07**). |
| **Acceptance** | Filtering never returns a record the officer could not open directly · pagination is stable under concurrent inserts · an unresolvable posting returns 403, not an unfiltered page |

---

## 10. Workflow — Audit and case history

| ID | Requirement |
|---|---|
| CRR-901 | **[EXISTS]** Create/update/upload actions write audit rows (`audit()` `:4032`; calls at `:9088`, `:9103`, `:9207`, `:9591`). |
| CRR-902 | **[EXISTS]** Per-record audit history is retrievable and branch-scoped (`:4281`; `AUDIT_ENTITY_MODULES` `:4123`). |
| CRR-903 | **[FIX]** Updates record **no before/after values** — `audit(c, user, 'UPDATE', 'crime_case', cid)` (`:9591`) records *that* a case changed, not *what* changed. |
| CRR-904 | **[NEW]** Authentication events (login success/failure, logout) are audited. See **SR-10**. |
| CRR-905 | **[NEW]** Audit rows are append-only and tamper-evident. See **SR-11**. |
| CRR-906 | **[DECISION]** Audit retention (**D-04**). |
| **Acceptance** | An update records prior and new values · the application role cannot UPDATE or DELETE an audit row · the case timeline reconstructs history from the audit trail alone |

---

## 11. Release 1.0 acceptance criteria for the Crime Unit

A workflow is complete only when **all** of the following hold. A UI is not completion.

| # | Criterion |
|---|---|
| CA-1 | Every endpoint enforces branch scope on read **and** write; cross-branch attempts return 403 and are audited |
| CA-2 | `suspect_alerts` is branch-isolated and has a working lifecycle |
| CA-3 | One case status vocabulary; illegal transitions refused server-side |
| CA-4 | Cases are assignable, reassignable and the history is complete |
| CA-5 | Investigative actions are append-only and the timeline is reconstructable |
| CA-6 | Evidence has an integrity hash, a custody log and an audited withdrawal path |
| CA-7 | No police document is retrievable without an authenticated, scoped, audited request |
| CA-8 | Server-side search, filtering and pagination exist and never widen scope |
| CA-9 | Reports are branch-scoped, filtered, and their arithmetic is pinned by tests |
| CA-10 | A dedicated Crime Unit test suite exists and passes in CI — **there is none today** |
| CA-11 | Identifiers are unique under concurrency and year-correct |
| CA-12 | Audit records before/after values and is append-only |

---

## 12. Decisions this document depends on

| ID | Decision | Status |
|---|---|---|
| **D-14** | Advanced report catalogue | **Approved as a starting point**; see `requirements/CRIME_REPORT_CATALOGUE.md` for the completed catalogue requiring sign-off |
| **D-15** | Incident/case model | Recommendation made (Option A) — owner decides |
| **D-21** | CID role structure; who assigns; case-level permissions | Open — **blocks §4** |
| **D-22** | Investigation workflow: mandatory steps, deadlines, supervisory review, referral | Open — **blocks §5** |
| **D-23** | Legal rules for suspect listing; alert lifetime; match confirmation | Open — **blocks §7** |
| **D-24** | Evidence chain of custody and admissibility | Open — **blocks §8** |
| **D-25** | Case status vocabulary, transitions, closure authority | Open — **blocks §6** |
| **D-26** | Search filters, sort, pagination | Open — **blocks §9** |
| **D-38** | Cross-branch incident↔case linking authority | **New** |
| **D-39** | "No further action" closure state for unlinked incidents | **New** |
| **D-04 / D-05 / D-07** | Retention · DPIA · scale | Open |
