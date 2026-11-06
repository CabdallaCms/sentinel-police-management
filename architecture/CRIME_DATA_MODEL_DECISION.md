# Crime Data Model — Investigation and Recommendation

**Phase 3 deliverable C · Architecture recommendation. No schema was changed and no migration was run.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Required by the brief:** investigate `crime_cases` and `crime_incidents`; recommend whether one
> investigation case can contain multiple incidents, whether incidents and cases should be separate
> linked records, or whether another model is more appropriate. Explain operational meaning,
> relationships, identifiers, history and migration implications. **Do not merge tables merely
> because they look related.**

---

## 1. What the two structures actually are

Both tables exist and both are in active use by different parts of the product. They are **not**
duplicates, and the difference is not accidental — each carries fields the other lacks, and each is
written by a different role through a different endpoint.

| Property | `crime_incidents` | `crime_cases` |
|---|---|---|
| DDL | `backend/server.py:374` | `:292` |
| Identifier | `file_number`, from `new_crime_file_number(c, station.code)` `:5082` — **station-coded** | `case_id` = `'CID-2026-' + zfill(COUNT(*)+8,3)` `:9083` — hard-coded year, global counter |
| Written by | `POST /api/crimes` `:9391` | `POST /api/crime-cases` `:9080` |
| Module gate | `crimes` | `cid` |
| Mandatory links | `station_id` **NOT NULL**, `officer_id` **NOT NULL** | none beyond `branch_id` |
| Branch scoping | `user_branch_scope(c, user, 'police_station')` `:8557` | `user_branch_scope(c, user, 'crime')` `:8260` |
| Status column | `case_status`, default `'Reported / Open'`, vocabulary `CRIME_STATUSES` (5) `:1708` | `status`, default `'Reported'`, vocabulary `CASE_STATUSES` (7) `:1716` |
| When it happened | `incident_at` **NOT NULL** — the real event time | **absent** — only `created_at`, the data-entry time |
| Where it happened | `location_of_occurrence` | `location` |
| Severity | `severity` ∈ `CRIME_SEVERITIES` | **absent** |
| Who reported | `reporting_party_type` ∈ Victim / Witness / Third-Party / Police | **absent** |
| Victim block | anonymity flag, name, contact, national ID, gender, age, address, `statement` | **absent** |
| Participants | **absent** | via `suspect_alerts` (Suspect / Victim / Witness / Complainant) |
| Evidence | **two fixed columns** `evidence1_*`, `evidence2_*` | `case_evidence` rows, **unbounded** |
| Narrative | `description` **NOT NULL** | `incident_summary`, `notes` |
| UI | page `#crimes` | page `#cid` + `#caseworkspace` (3 tabs) |

### 1.1 The operational meaning

Read as operational artefacts rather than as tables, the asymmetry is coherent:

- **`crime_incidents` is a station intake / first-report record.** A member of the public — or an
  officer — reports that something happened. It is bound to a **station** and a **receiving officer**,
  it captures **when and where the event occurred**, who reported it, the victim's details and
  statement, severity, and up to two immediate evidence attachments. It is a *report of an event*.

- **`crime_cases` is a CID investigation file.** It is bound to a **branch**, it carries the
  investigative narrative, an open-ended evidence collection and a participant list. It has no event
  time and no victim block because those belong to the report that triggered it. It is a
  *unit of investigative work*.

### 1.2 The relationship today

**There is none.** No foreign key, no shared identifier, no cross-reference column, no conversion
endpoint, and **no code path reads one while writing the other**. Verified by inspection of both
handlers and the full DDL.

This is the gap, and it is an operational gap before it is a technical one: **the system cannot
answer "which report caused this investigation?" or "was this report ever investigated?"**

---

## 2. The question the brief asks: can one case contain multiple incidents?

Operationally, yes — and this is the decisive argument.

Real investigations routinely absorb more than one report:

- A serial burglar generates one report per burgled house; CID runs **one** investigation.
- A road traffic collision generates separate reports from two stations; one case.
- A domestic matter reported three times over six months; one case file.
- Conversely, one report can **split**: a reported "assault" that turns out to involve two unrelated
  offenders may become two investigations.

So the real-world cardinality is **many-to-many in the limit**, overwhelmingly **one-case-to-many-
incidents** in practice, and occasionally one-incident-to-many-cases on a split.

**The current model cannot express any of this**, because it expresses no relationship at all.

---

## 3. Options considered

### Option A — Separate linked records, one case to many incidents *(RECOMMENDED)*

Keep both tables. Add an explicit link. An investigation may draw on several reports; a report may
exist without ever becoming an investigation.

```
police_stations ──< crime_incidents >── (link) ──< crime_cases >── police_branches
                         │                             │
                      persons (victim)            case_participants
                                                  case_evidence
                                                  case_status_history
                                                  case_assignments
```

**Mechanism.** A join table rather than a single FK column, because it is the only option that
survives the split case without a later migration:

| `case_incidents` | |
|---|---|
| `case_id` → `crime_cases.id` | |
| `incident_id` → `crime_incidents.id` | |
| `linked_by`, `linked_at`, `link_reason` | who connected them and why |
| `is_primary` | the report that originated the case |
| **unique** `(case_id, incident_id)` | no duplicate links |

**Why this is the recommendation**

1. It matches the operational reality in §2 without forcing it.
2. It is **purely additive** — no existing column changes type, no existing row is rewritten, both
   existing UIs keep working on day one.
3. Both identifier schemes keep their meaning: a station file number stays a station file number, a
   CID case number stays a CID case number. Citizens and courts already hold documents quoting them.
4. It is **reversible**. Dropping the join table returns the system to its current state.
5. It keeps the two **branch-scoping domains** (`police_station` vs `crime`) separate instead of
   forcing a single scope model onto two different organisational structures.
6. It gives the missing report its data source: "reports received vs investigations opened" and
   "reports never actioned" become answerable (report R-20, catalogue §4).

**Risks and what they cost**

| Risk | Mitigation |
|---|---|
| A conversion/linking workflow needs its own permissions, audit and tests | Specified as CRR-2xx in the Crime requirements; roughly 4–8 engineering days including tests |
| Two status vocabularies now sit side by side on linked records | **D-25** decides the authoritative vocabulary; the recommendation is that each object keeps its **own** lifecycle (a report is Received/Referred/Filed; a case is Open/Under Investigation/…), and the UI shows both. Do **not** force one status onto both objects |
| Cross-branch linking (a Sool station report feeding a Sanaag investigation) is a new authorization surface | Must be an explicit, permissioned, audited action — **D-38** |
| Users may link indiscriminately, inflating case files | Require `link_reason`; make links auditable and unlinkable with a reason |

---

### Option B — Merge into one table *(NOT recommended)*

One `crime_cases` table absorbing the victim block, severity, `incident_at` and the reporting-party
type; `crime_incidents` becomes a view or is migrated away.

**Why it is rejected**

- **Destructive and irreversible.** Rows must be rewritten and `file_number` values either discarded
  or crammed into `case_id`. Documents already issued quote those numbers.
- It **loses the station↔branch distinction**: `crime_incidents.station_id` and `officer_id` are NOT
  NULL and have no equivalent in `crime_cases`; the two tables are scoped against two different
  organisational hierarchies.
- It **cannot express one case from many reports** — the exact capability §2 identifies as the
  operational requirement. Merging would force a single victim block onto a multi-report case.
- It forces an immediate reconciliation of two status vocabularies on live data.
- It requires rewriting both UIs simultaneously, with no incremental path.
- It must happen **before** the versioned-migration mechanism exists (M-11), i.e. a destructive
  migration with no recorded version and no rollback.

**This is the option the brief warns against: merging because two tables look related.** They are
related; they are not the same thing.

---

### Option C — Keep separate, formalise, do not link *(insufficient)*

Document them as two deliberately distinct registers; fix only the branch-scoping mismatch.

Cheapest, and it does fix a real bug — but it leaves the central operational question unanswered and
makes several requested reports impossible. Acceptable only as a **fallback if the owner declines
Option A**, and it should then be recorded as a deliberate limitation of Release 1.0.

---

### Option D — Incident as a child of case only *(rejected)*

Make `crime_incidents` strictly a child row of `crime_cases` (simple FK, no join table).

Rejected because it inverts the real sequence: **the report exists first, and most reports never
become investigations.** A mandatory parent case would force the creation of empty investigation
files at intake, corrupting every case-count metric in the system.

---

## 4. Recommendation

> **Adopt Option A: two separate record types, explicitly linked through a `case_incidents` join
> table, supporting one case to many incidents (and, where operationally necessary, one incident to
> many cases).**
>
> **This remains owner decision D-15.** The recommendation is made with its risks stated; it is not
> a decision taken on the owner's behalf.

### 4.1 Identifiers

| Object | Scheme | Change required |
|---|---|---|
| Incident | `file_number`, station-coded | Keep. Already meaningful and station-scoped |
| Case | `case_id` | **Must be fixed regardless of D-15.** `'CID-2026-' + COUNT(*)+8` hard-codes the year, uses a global counter and races under concurrency. Replace with a year-scoped sequence, e.g. `CID-<year>-<branch>-<seq>`, generated inside the inserting transaction with a unique constraint |
| Link | surrogate | New |

**Existing identifiers are never rewritten.** Any new scheme applies to new records only; historical
`CID-2026-…` values remain valid and are not retro-numbered. Rewriting issued reference numbers
would invalidate documents already in circulation.

### 4.2 History and audit

- The link itself is an audited event: `LINK incident→case` and `UNLINK`, each with actor, timestamp
  and reason.
- Linking must **not** rewrite either record's own history. Both keep their own `created_at`,
  `created_by` and status history.
- `case_status_history` (new, Crime requirements CRR-5xx) records case transitions; the incident keeps
  its own `case_status` lifecycle.
- A case's effective "offence date" derives from its linked incidents' `incident_at`. Until a case has
  a link, it has no offence date — which is **already true today**, and should be surfaced as a data-
  quality gap rather than silently defaulted to `created_at`.

### 4.3 Migration implications

| Step | Nature | Risk |
|---|---|---|
| 1. Create `case_incidents` | Additive DDL, new empty table | Low |
| 2. Backfill | **None is possible** — there is no shared key, no timestamp overlap rule, and no reliable heuristic. Existing cases and incidents stay unlinked | Low, but must be stated: **historical records will not be retrospectively linked.** Attempting a fuzzy backfill on police records would manufacture false associations |
| 3. Add `case_id` sequence + unique constraint | Additive, new records only | Low |
| 4. Link UI + endpoints | Application work | Medium — new permission surface |
| 5. Reports consuming the link | Application work | Low |

**Sequencing constraint:** steps 1 and 3 are DDL and therefore sit **behind M-11 (versioned
migrations)**. They must not be added as further application-startup side effects — that is precisely
the pattern the security review flagged.

### 4.4 What must be fixed irrespective of which option is chosen

These are defects, not design choices, and they are independent of D-15:

| # | Defect | Reference |
|---|---|---|
| 1 | `GET /api/crimes` scopes CID officers against `police_station` branches (`:8557`) while CID postings resolve as `crime`; an unresolvable posting **fails open** to a national view | H-2b |
| 2 | `PATCH /api/crime-cases/<id>` has **no branch check** and accepts **free-text** status | N-2, D-25 |
| 3 | `POST /api/crime-cases/<id>/evidence` has **no branch check** | N-2 |
| 4 | `suspect_alerts` has **no `branch_id`**, and `GET /api/suspect-alerts` applies **no filter at all** | N-1 |
| 5 | `case_id` hard-codes `2026` | H-6 |
| 6 | `crime_incidents` supports exactly **two** evidence items in fixed columns | CRR-4xx |

---

## 5. Target entity model (Release 1.0, assuming Option A)

```
                     ┌──────────────┐
                     │   persons    │  Central Person Registry (shared)
                     └──────┬───────┘
          ┌─────────────────┼──────────────────────┬────────────────────┐
          │                 │                      │                    │
   victim block      case_participants      suspect_alerts       checkpoint_events
   (crime_incidents)        │                 (+branch_id NEW)          │
          │                 │                      │                    │
┌─────────▼────────┐   ┌────▼─────────┐            │                    │
│ crime_incidents  │   │ crime_cases  │◄───────────┘                    │
│  file_number     │   │  case_id     │   alerts reference a case       │
│  station_id  ────┼──►│  branch_id   │                                 │
│  officer_id      │   │              │                                 │
│  incident_at     │   └──┬────┬───┬──┘                                 │
│  severity        │      │    │   │                                    │
│  victim_*        │      │    │   └──► case_evidence (+hash, custody)  │
└────────┬─────────┘      │    │                                        │
         │                │    └──────► case_status_history   NEW       │
         │  case_incidents│                                             │
         └────────────────┘    └───────► case_assignments      NEW      │
             (NEW join)                                                 │
                                                                        │
   police_stations ── police_branches ── users ── audit_events ─────────┘
```

**New tables proposed:** `case_incidents` · `case_participants` · `case_assignments` ·
`case_status_history` · `evidence_custody` · `document_objects` (shared, see the architecture
document) · biometric enrolment tables (see the Fingerprint requirements).

**Modified tables proposed:** `suspect_alerts` (+`branch_id`, +lifecycle columns) ·
`crime_cases` (+`closed_at`, +`severity`, +`source` metadata) · `case_evidence` (+`sha256`,
+`withdrawn_at`, +`withdrawn_reason`).

> `case_participants` is listed as **new**: the Phase 2 assessment confirmed `grep -c
> case_participants` → **0**. Participants currently exist only as `suspect_alerts` rows, which is why
> victims and witnesses are stored in a table named and treated as "suspect alerts".

---

## 6. Decisions arising

| ID | Decision | Status |
|---|---|---|
| **D-15** | Adopt Option A (separate, linked, one-case-to-many-incidents)? | **Recommendation made — owner decides** |
| **D-25** | Status vocabularies: the recommendation is that incidents and cases keep **separate** lifecycles rather than being forced into one list | Open |
| **D-38** | May an incident at a station in one branch be linked to a case in another branch, and who authorises it? | **New** |
| **D-39** | Does an unlinked incident need an explicit "no further action / filed" closure state, so "never actioned" is distinguishable from "awaiting action"? | **New** |
| **D-07** | Expected volumes — governs indexing and whether the all-rows-in-memory pattern at `:5490` must be replaced before go-live | Open |
