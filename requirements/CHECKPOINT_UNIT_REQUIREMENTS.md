# Checkpoint Unit — Requirements and Corrections (Release 1.0)

**Phase 3 deliverable D · Requirements only. No application code was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Scope basis:** `RELEASE_PLAN.md` §1 — existing functionality **plus** the identified gaps:
> officer/location restrictions, operations and incident recording, detention/referral/false-match
> workflows.
>
> **Owner claim on record:** *"Checkpoint Unit is already implemented."* The Phase 2 assessment found
> this **partly supportable and partly contradicted**. A real, usable screening workflow exists. But
> the unit's **primary access control is inverted** — the canonical checkpoint role reads every
> record in the country and may write to any location — and the post-screening workflow (what
> happens *after* a person is flagged) does not exist. Both are in Release 1.0 scope.

Markers: **[EXISTS]** retained · **[FIX]** defective · **[NEW]** absent · **[DECISION]** needs owner input.

---

## 1. What genuinely exists *(capabilities CP-01…CP-17, full detail in `assessment/CHECKPOINT_UNIT_GAP_ANALYSIS.md`)*

Screening event capture with person auto-create/enrich · automatic suspect-alert screening at
`:9304-9307` · guardian/minor handling (8 fields) · traveller photo and document upload ·
location and location-code capture · branch resolution · event identifiers · audit on create ·
a six-way location filter on list (`:8460`) · a scoped analytics section (`cid_checkpoint_analytics(c, user)`
`:6176` — **the only analytics builder in the system that takes `user`**) · a checkpoint role audit
test with 76 references (`test_checkpoint_roles_audit.py` — **written but not executed**).

**This is a real unit, not a stub.** The corrections below do not contradict that.

---

## 2. CORRECTION 1 — The blank-scope canonical role *(release blocker)*

### 2.1 The defect

```
ROLE_LOCATION_SCOPE  (backend/server.py:1908-1925)
  ROLE_CHECKPOINT_SOUTH    → 'South'
  ROLE_CHECKPOINT_EAST     → 'East'
  ROLE_CHECKPOINT_WEST     → 'West'
  ROLE_CHECKPOINT_OFFICER  → ''        ← canonical role, blank scope
```

Blank is consumed as *"no restriction"* in three places:

| Site | Consequence |
|---|---|
| `checkpoint_scope()` `:2990` | returns no restriction |
| `GET /api/checkpoint-events` `:8460` | **no location filter applied — reads every checkpoint event nationwide** |
| `POST /api/checkpoint-events` `:9301` | **no location check — may write an event at any location** |

**The generic, canonical role is the least restricted.** The three legacy regional roles are safer
than the role intended to replace them. Security finding **M-2**, re-rated **UP to HIGH** in Phase 2.

### 2.2 Requirements

| ID | Requirement |
|---|---|
| CKR-101 | **[FIX]** `ROLE_CHECKPOINT_OFFICER` must resolve to a **real, assigned location scope**. A checkpoint officer is posted to a checkpoint; the data model must say so. |
| CKR-102 | **[FIX]** **Blank, null or unresolvable scope must mean DENY, never ALL** — at every one of the three sites above. This is the same fail-open class as H-2b (`branch_scope_view` `:2661`). |
| CKR-103 | **[FIX]** An officer whose posting cannot be resolved receives **403**, not a national dataset. |
| CKR-104 | **[NEW]** Officer→location assignment is **data**, not a role constant. Hard-coding South/East/West cannot express a fourth checkpoint (**D-20**). |
| CKR-105 | **[DECISION]** Is an officer assigned to one location, several, or a region (**D-20**)? |
| CKR-106 | **[FIX]** The legacy roles must be **reconciled, not merely coexist**. Today the system has four checkpoint roles with two different security postures. |
| CKR-107 | **[EXISTS]** `enforce_read_only()` keeps `chief_commander` read-only across all checkpoint routes. Retained. |
| **Acceptance** | A blank-scope role is **refused** · an officer sees only their own location's events, asserted **on record ids, not counts** · writing an event at another location returns 403 and is audited · `test_checkpoint_roles_audit.py` **executes** and passes · a negative test specifically asserts that blank scope denies |

> **Note on evidence.** `test_checkpoint_roles_audit.py` contains 76 role/audit references but **has
> never been executed in this environment** (it requires `pgserver`/`psycopg2`, which cannot be
> installed under the current authorization). Until it runs, the fix is **not verified**. Static
> inspection is not proof of runtime behaviour.

---

## 3. CORRECTION 2 — Cross-location read and write

| ID | Requirement |
|---|---|
| CKR-201 | **[FIX]** Reads are location-scoped by default. |
| CKR-202 | **[FIX]** Writes are restricted to the officer's assigned location(s). |
| CKR-203 | **[NEW]** Cross-location read, where operationally required (a traveller moving between checkpoints), is an **explicit, permissioned, audited** action — not a side effect of a blank string. |
| CKR-204 | **[FIX]** The six-way `OR` location filter (`:8460`) matches `location`, `location_code`, `checkpoint_location` and more. Every branch of that filter must sit **inside** the scope predicate so a filter can narrow but never widen. |
| CKR-205 | **[NEW]** A person's **own** checkpoint history across locations is visible to an authorised officer as an explicit, audited lookup — it is operationally necessary and must not be achieved by removing scoping. |
| **Acceptance** | A filter never returns a record the officer could not open directly · cross-location access is permissioned and audited · a two-officer test proves isolation on record ids |

---

## 4. CORRECTION 3 — Operations and incident recording

**Nothing in this section exists.** A checkpoint event today records a *screening*, not an
*operation*, an *incident* or a *shift*.

| Element | Specification |
|---|---|
| **Actors** | Checkpoint officer records; supervisor reviews |
| **Precondition** | Officer authenticated and assigned to the location |
| **Steps** | Open shift/operation → record screenings → record incidents → close shift with summary |
| **Required data** | location, start/end, officers present, operation type, outcome counts |
| **Transitions** | Operation: `Open` → `Closed`. Incident: `Recorded` → `Referred` / `Resolved` |
| **Exceptions** | An operation left open past a configured period is flagged; an incident may be amended only by audited amendment |
| **Audit** | `OPEN_OPERATION` · `CLOSE_OPERATION` · `RECORD_INCIDENT` · `AMEND_INCIDENT` |

| ID | Requirement |
|---|---|
| CKR-301 | **[NEW]** A checkpoint **operation / shift** record: location, period, officers, type, summary. |
| CKR-302 | **[NEW]** A checkpoint **incident** record independent of a person screening — obstruction, contraband, vehicle incident, assault on officer, equipment failure, closure. **None of these can be recorded today.** |
| CKR-303 | **[NEW]** Incidents carry type, severity, narrative, persons involved (where known) and outcome. |
| CKR-304 | **[NEW]** A checkpoint incident can be **escalated to a crime case**, creating an audited link. |
| CKR-305 | **[NEW]** Screenings performed during an operation roll up to it for shift reporting. |
| CKR-306 | **[DECISION]** Operation types, shift model, mandatory per-shift fields (**D-43**). |
| **Acceptance** | An operation can be opened, populated and closed with a summary · an incident unrelated to any person screening can be recorded · escalation to a crime case is audited at both ends · shift totals reconcile with the underlying screening records |

---

## 5. CORRECTION 4 — Detention, referral and false-match workflows

**This is the unit's largest functional gap.** The system flags a person — and then stops.
`screening_result` is set automatically (`:9304-9307`) and `action_taken` defaults to `'Cleared'`.
**There is no record of what the officer actually did.**

### 5.1 Detention

| ID | Requirement |
|---|---|
| CKR-401 | **[NEW]** A detention record: person, location, officer, start time, legal basis, grounds. |
| CKR-402 | **[NEW]** Detention **end** time and outcome: released · referred to CID · transferred to a station · handed to another authority. |
| CKR-403 | **[NEW]** **Detention duration is tracked against a configured legal maximum, with escalation as it approaches.** A police system that records a detention without a clock is a liability. |
| CKR-404 | **[NEW]** Every detention status change is audited with actor, timestamp and reason. |
| CKR-405 | **[DECISION]** **Legal basis, maximum duration, mandatory notifications and custody-record obligations — part of D-27 (the authorised post-flag procedure). This is a legal question, not a product question, and it is on the critical path for this workflow.** |

### 5.2 Referral

| ID | Requirement |
|---|---|
| CKR-411 | **[NEW]** A referral from a checkpoint to CID, a station or another authority, carrying the screening and any detention. |
| CKR-412 | **[NEW]** Referral status is tracked to acknowledgement and outcome — a referral nobody accepted must be visible. |
| CKR-413 | **[NEW]** A referral may create or link to a crime case (shared mechanism with CKR-304). |
| CKR-414 | **[NEW]** The originating checkpoint officer can see the outcome of their own referral. |
| CKR-415 | **[DECISION]** Referral routing and acknowledgement SLA (**D-27**). |

### 5.3 False match

> With D-18 approving **genuine biometric matching**, false-match handling becomes a joint
> checkpoint/biometric requirement. Today's matching is a string comparison plus — in the SPA's live-
> scan path — a **rotating-cursor fallback that returns an arbitrary person** (Fingerprint FPR-902).
> **At a checkpoint, a fabricated identification can result in a wrongful detention.** That is the
> concrete operational consequence, and it is why FPR-902 is unconditional.

| ID | Requirement |
|---|---|
| CKR-421 | **[NEW]** An officer can mark a flag or match as a **false match**, with a reason. |
| CKR-422 | **[NEW]** A false match is **recorded against the event and the alert**, and is reportable (report R-19). It must not merely vanish from the screen. |
| CKR-423 | **[NEW]** A confirmed false match **must not re-flag the same person on the same basis** without supervisory review. Today an alert is written `'Active alert'` (`:9205`) and **never changes** — a cleared person is re-flagged at every checkpoint, indefinitely. |
| CKR-424 | **[NEW]** Repeated false matches against one alert raise it for supervisory review. |
| CKR-425 | **[NEW]** Where a match originated from biometric identification, the score, threshold and candidate list are retained with the false-match record. |
| CKR-426 | **[DECISION]** Who may clear a false match — the officer alone, or a supervisor (**D-27**)? |
| **Acceptance** | Detention with basis and clock · duration escalation fires · referral tracked to acknowledgement · false match recorded, reportable, and suppresses re-flagging pending review · every transition audited |

---

## 6. CORRECTION 5 — Legacy ↔ canonical consistency

| ID | Requirement |
|---|---|
| CKR-501 | **[FIX]** One checkpoint role model. Four roles with two security postures is a correctness problem before it is a tidiness problem. |
| CKR-502 | **[FIX]** `CHECKPOINT_LOCATIONS = ('South','East','West')` (`:1649`) is hard-coded; locations must come from `police_branches`, **with the fail-closed fix applied at the same time** (**D-20**). Fixing the catalogue without fixing the fail-open would widen the defect. |
| CKR-503 | **[NEW]** Migrating a legacy-role user to the canonical role must **not silently widen** their access. Any widening is explicit and audited. |
| CKR-504 | **[FIX]** `UNIT_ROLE_ALIASES` inheritance must be verified by test so an alias cannot acquire a different scope from its canonical role. |
| CKR-505 | **[NEW]** A startup assertion refuses to run with any checkpoint role whose location scope is blank or unresolvable. |
| **Acceptance** | Legacy and canonical roles produce **identical** access for the same posting · a blank-scope role prevents startup · no migration widens access without an audit record |

---

## 7. Supporting requirements

| ID | Requirement |
|---|---|
| CKR-601 | **[FIX]** `GET /api/checkpoint-events/<id>` does not exist; an officer cannot open a single event. |
| CKR-602 | **[FIX]** `PATCH` does not exist; a mistyped event **cannot be corrected at all**. Correction must be by audited amendment that preserves the original, never by overwrite. |
| CKR-603 | **[FIX]** `save_upload()` (`:3939`) validates nothing — traveller photos and documents accept any type and any size (**M-7**). |
| CKR-604 | **[FIX]** Traveller documents are retrievable **unauthenticated** via `/uploads/` (`:7914`) — security requirement **SR-01**. |
| CKR-605 | **[FIX]** `screening_result` is fully automatic. An officer must be able to record the **actual** outcome, including disagreement with the automatic result, with a reason. |
| CKR-606 | **[NEW]** No vehicle linkage exists on `checkpoint_events` although `vehicles` tables exist. A checkpoint that cannot record the vehicle a person arrived in is incomplete (**D-28**). |
| CKR-607 | **[FIX]** Analytics are scoped (`:6176`) but unfiltered and offer no drill-down — same cross-cutting gaps as the Crime catalogue. |
| CKR-608 | **[NEW]** Server-side pagination; the list route has none. |
| CKR-609 | **[EXISTS]** Guardian/minor handling is retained. |
| CKR-610 | **[NEW]** Minors' data requires explicit handling rules in the DPIA (**D-05**). |

---

## 8. Release 1.0 acceptance criteria for the Checkpoint Unit

| # | Criterion | Proof |
|---|---|---|
| KA-1 | No checkpoint role has a blank or unresolvable scope; blank **denies** | Startup assertion + negative test |
| KA-2 | Officers read only their assigned location(s) — asserted on **record ids** | Two-officer isolation test |
| KA-3 | Officers write only at their assigned location(s) | Negative test |
| KA-4 | An unresolvable posting returns 403, never a national dataset | Negative test |
| KA-5 | Legacy and canonical roles grant identical access for the same posting | Parity test |
| KA-6 | Operations/shifts can be opened, populated, closed | Functional test |
| KA-7 | Checkpoint incidents independent of a screening can be recorded and escalated | Functional test |
| KA-8 | Detention records basis, clock, escalation and outcome | Functional test |
| KA-9 | Referrals are tracked to acknowledgement and outcome | Functional test |
| KA-10 | False matches are recorded, reportable, and suppress re-flagging pending review | Functional + negative test |
| KA-11 | No traveller document is retrievable unauthenticated | Negative test |
| KA-12 | Uploads are type- and size-validated | Negative test |
| KA-13 | Events can be opened individually and corrected by audited amendment | Functional test |
| KA-14 | `test_checkpoint_roles_audit.py` **executes** and passes in CI | CI run |
| KA-15 | Location catalogue is data-driven, with fail-closed resolution | Functional + negative test |

---

## 9. Decisions this document depends on

| ID | Decision | Status |
|---|---|---|
| **D-20** | Location catalogue from `police_branches`; officer→location assignment model | Open — **blocks §2, §6**. Must be done **with** the fail-closed fix |
| **D-27** | **Checkpoint outcomes and the authorised post-flag procedure** — detain / refuse / refer / release / record a false match, including the **legal basis and maximum duration of detention**, notification and custody-record obligations, referral routing and acknowledgement SLA, and who may clear a false match | Open — **blocks §5 entirely; longest lead time in this unit** |
| **D-43** | Checkpoint **operation / shift** model — operation types, shift boundaries, mandatory per-shift fields *(new; D-27 governs the post-flag procedure, not shift recording)* | **New** — blocks §4 |
| **D-28** | Vehicle linkage at checkpoints | Open — blocks CKR-606 |
| **D-05** | DPIA, including minors' data | Open |
| **D-18** | *Closed — BOTH.* Genuine biometric matching makes §5.3 a real workflow rather than a theoretical one | **Closed** |
