# Reference Data — CID Scope Analysis

**Date:** 5 November 2026 · **Commit:** `9853683` · **Status:** **ANALYSIS — NOT IMPLEMENTED**
**Raised by:** the owner's scope correction — station management is an HQ responsibility, not a CID
Release 1.0 decision
**Revises:** A-18 in `OWNER_DECISION_SHEET.md` · C-1 in `OWNER_DECISION_SHEET_ADDENDUM.md`
**Extended by:** `HQ_PROVISIONING_AND_READINESS.md` — which **corrects option (a) from 15 branch rows to 12**, after finding that the three `police_station` branch rows auto-mirror into fabricated station records. Read that correction before acting on §4 or §5 below.

**Current CID scope, as stated by the owner:**

| Unit | Release |
|---|---|
| Fingerprint Unit | CID Release 1.0 |
| Crime Unit | CID Release 1.0 |
| Checkpoint Unit | CID Release 1.0 |
| Airport Unit | Phase 2 / CID Release 1.1 |

> Nothing has been implemented. No station row has been created, modified or deleted.
> `backend/server.py` is byte-identical to `e7263d7`.

---

## 1. Why the eight stations reached your decision sheet

**You were right to challenge it. The honest answer is that I made a scope error, not a judgement
call.**

The chain:

1. A-16 and A-17 required deciding **what a production database contains on first run**.
2. I read `init_db()` (`server.py:3261–3363`) to establish what first run creates.
3. That one function seeds **branches, checkpoint locations, stations, user accounts and
   demonstration records** — all in sequence, in the same ~100 lines.
4. I grouped everything it writes into a single question: *"which of this is reference data worth
   keeping, and which is demonstration data?"* That became A-18.
5. **I never asked the prior question: "is this inside CID Release 1.0 scope at all?"**

**Root cause: I treated code locality as scope.** The station seed sits between the branch seed and
the user seed in one function, so I treated it as part of the same decision. Proximity in a file is
not shared ownership.

I then made it worse in two specific ways:

- I asked you to validate **tiers and cell capacities** — `cell_capacity` is detention capacity, a
  custody and HQ matter with no CID function whatsoever.
- I wrote *"I cannot verify the station list is operationally correct"* and passed that verification
  burden to you. That was me escalating an HQ data-custody question into a CID security decision
  sheet because I could not resolve it myself.

**What should have happened:** on finding station seeding inside `init_db()`, I should have
classified it against the four CID units, found it belongs to none of them, and recorded it as an
HQ dependency — not raised it for your approval.

### A second error, which I am correcting here

In the addendum (C-1, note 3) I told you:

> *"The three `locations` rows are load-bearing. `South`/`East`/`West` are wired into
> `ROLE_LOCATION_SCOPE` and checkpoint scoping. Excluding them would break checkpoint officer
> authorization until recreated."*

**That is wrong.** The `locations` **table is never read by anything.**

| Evidence | Finding |
|---|---|
| `CREATE TABLE … locations` | `server.py:227` |
| Only writes | `server.py:3274`, `3278` (the seed) |
| **Reads** | **none** — no `SELECT … FROM locations` anywhere |
| `/api/locations` endpoint | **does not exist** (backend or SPA) |
| What actually drives scoping | `CHECKPOINT_LOCATIONS = ('South','East','West')` — a hard-coded Python constant at `server.py:1649` |
| `server.py:533` comment | explicitly says *"without joining the locations table"* |

Checkpoint authorization reads the **constant**, not the table. I asserted a dependency from the
column names looking load-bearing, without grepping for a read. **The `locations` table is
write-only dead weight.**

---

## 2. Dependency map — verified by reading every DDL and call site

### 2.1 What the CID tables actually reference

| CID table | Unit | → `police_branches` | → `police_stations` | → `officers` |
|---|---|---|---|---|
| `clearance_applications` (265) | Fingerprint | `branch_id` nullable | — | — |
| `clearance_signed_documents` (281) | Fingerprint | — | — | — |
| `crime_cases` (292) | Crime | `branch_id` nullable | — | — |
| **`crime_incidents`** (374) | **Crime** | `branch_id` nullable | **`station_id` NOT NULL** | **`officer_id` NOT NULL** |
| `case_evidence` (309) | Crime | — | — | — |
| `checkpoint_events` (316) | Checkpoint | `branch_id` nullable | — | — |
| `suspect_alerts` (299) | CID | — *(finding S-04)* | — | — |
| `airport_passengers` (255) | Airport (1.1) | `branch_id` nullable | — | — |
| `persons` (247) | Shared | — | — | — |

### 2.2 Answering your question 3 directly

> **Do the CID modules actually depend on the station records?**

| Unit | Depends on stations? | Evidence |
|---|---|---|
| **Fingerprint** | **No** | No station column, no station query |
| **Crime** | **YES — one hard dependency** | `crime_incidents.station_id` is **NOT NULL REFERENCES police_stations(id)** (`server.py:376`). The write path resolves a station and raises `'Station "X" does not exist'` (`server.py:5292–5296`) before inserting at `5338` |
| **Checkpoint** | **No** | `checkpoint_events` stores `location` as free **TEXT**; scoping uses the `CHECKPOINT_LOCATIONS` constant |
| **Airport (1.1)** | **No** | No station column |

**So: one of four CID units has a genuine, enforced dependency on station records — the Crime Unit,
and only for incident recording.**

Two important qualifications:

1. **The dependency is on *a* station existing, not on *these eight*.** Nothing in CID requires
   Ceerigaabo, Badhan or any particular tier or cell capacity. The Crime Unit needs the FK to
   resolve; which stations exist is entirely HQ's to determine.
2. **The same row also hard-requires an officer** (`officer_id NOT NULL REFERENCES officers(id)`).
   So Crime Unit incident recording depends on **two** HQ/HR-owned record types, not one.

### 2.3 What the CID modules genuinely do require

| Reference data | Required by | Verdict |
|---|---|---|
| **`police_branches`** (15 rows) | **All four CID units.** Every CID table carries `branch_id REFERENCES police_branches(id)`, and the branch-scope authorization model (`branch_scope_view` `:2661`, `require_record_branch_scope` `:2790`) resolves officer postings against this table | **KEEP — genuine CID reference data** |
| `locations` (3 rows) | **Nothing.** Write-only; no reads, no endpoint | **DROP from seeding** — see §4 |
| `police_stations` (8 rows) | Crime Unit incident recording needs ≥1 row; the specific eight are HQ's | **OUT OF CID SCOPE** — see §3 |

**The 15 `police_branches` rows are 3 branch names × 5 unit types** — and four of those five unit
types (`fingerprint`, `crime`, `checkpoint`, `airport`) *are* the CID units. This is the table the
CID authorization model is built on.

> **One point to note, not a decision I am asking you to make:** the three branch *names* —
> Buuhoodle Branch (East Togdheer), Lasanod Branch (Sool), Erigavo Branch (Sanaag) — are a
> deployment-geography question in the same family as the station list. The *structure* is CID's;
> the *place names* probably are not. I am flagging it so the same mistake is not repeated one
> table over. **No approval requested** — whoever owns deployment geography should confirm them
> when convenient.

---

## 3. HQ dependencies — recorded as outside the current release scope

Per your instruction 5. These are real couplings between CID Release 1.0 and HQ-owned data. They are
**not** CID decisions, and **no change to them is proposed.**

| # | Dependency | Owner | Effect on CID Release 1.0 |
|---|---|---|---|
| **HQ-1** | `crime_incidents.station_id` **NOT NULL** → `police_stations` | **HQ** | **Crime Unit incident recording cannot function until at least one station record exists.** On a clean production database with no stations, the API returns `Station "…" does not exist` |
| **HQ-2** | `crime_incidents.officer_id` **NOT NULL** → `officers` | **HR Directorate** | Same write path also requires a registered desk officer |
| **HQ-3** | `officers.station_id` **NOT NULL** → `police_stations` | **HR + HQ** | Registering any officer requires a station. Chains into HQ-2 |
| **HQ-4** | `officer_conduct_actions.station_id` (nullable) | **HR** | No CID impact |
| **HQ-5** | Station custodial attributes — `station_tier`, `cell_capacity`, `commander_id`, `deputy_id`, `operational_status` | **HQ** | **No CID function.** Consumed only by the Station Master Registry analytics bundle |
| **HQ-6** | `/api/stations` is readable by the `crimes` module (`server.py` bundle wrapper; SPA `index.html:8973`) | HQ data, CID reader | The Crime Unit reads stations to populate its incident form. **This is also part of finding S-05** — `crimes` currently grants the whole stations analytics bundle, which is wider than the Crime Unit needs |

### Go-live prerequisite this creates

**HQ-1, HQ-2 and HQ-3 form a chain that must be satisfied before the Crime Unit can record a single
incident:**

```
HQ provisions real stations  ->  HR registers officers (needs a station)
                             ->  Crime Unit can record an incident (needs both)
```

This is a **sequencing dependency for deployment, not an engineering task**, and it is not on the
CID critical path in terms of effort. But if HQ has not provisioned stations by go-live, the Crime
Unit is non-functional on day one. **It belongs in the go-live checklist, owned by HQ.**

---

## 4. Recommended treatment — nothing deleted

Your instruction 2 was explicit: do not delete or modify existing station data without investigating
dependencies. **Investigated; I recommend deleting nothing.**

| Object | Recommendation | Why |
|---|---|---|
| `police_stations` **table** | **Keep. Do not touch.** | Three FKs point at it, two of them `NOT NULL`. Dropping or altering it would break the Crime Unit and the entire officer register |
| Existing station **rows** in any current database | **Keep. Do not touch.** | Per R-1 the only databases are development/test, where they are useful fixtures. Deleting rows in a database that already has `crime_incidents` or `officers` would violate the FKs |
| **Seeding** 8 stations on production first run | **Stop** — HQ provisions real stations | Seeding placeholder stations into an operational police database is the S-13 problem in a different table |
| `locations` **table** | **Keep the table. Stop seeding it.** | Nothing reads it; the rows are inert. Removing the table is a separate cleanup, out of scope here |
| `police_branches` seeding | **Keep** | Genuine CID reference data, required by all four units and by branch authorization |

**Net effect on production initialization:** branches are created; stations and locations are not;
HQ provisions real stations before the Crime Unit goes live.

---

## 5. Revised A-18 — what is actually being asked

The station list, tiers and cell capacities have been **removed** from your decision. What remains
is a CID-scoped question only.

> **A-18 (revised):** For production initialization, should the system create **only
> `police_branches`** — the reference data the CID authorization model and all four CID units
> require — and create **no stations and no checkpoint-location rows**, leaving station
> provisioning to HQ?

**Options**
- **(a)** `police_branches` only. No stations, no `locations` rows. HQ provisions stations.
- **(b)** `police_branches` plus one placeholder station, so the Crime Unit works out of the box.
- **(c)** Status quo — seed branches, locations and all eight stations.

**Recommended: (a).**

- It is the only option that keeps production initialization inside CID scope.
- **(b) recreates S-13 in another table** — a fictional station in an operational police database,
  appearing in every station report and capacity figure. The Crime Unit "working out of the box"
  would mean incidents filed against a station that does not exist.
- **(c)** is what produced this scope error.

**Consequences**
- *Security:* No fictional operational records. Consistent with A-16 and A-17.
- *Operational:* **The Crime Unit cannot record incidents until HQ provisions stations and HR
  registers officers** (HQ-1/2/3). This must be in the go-live checklist. It is a sequencing
  constraint, not a defect.
- *Legal:* Avoids fabricated station and capacity records in an operational police system.

**Reversible:** **Yes** for the code. Rows already created in a database are untouched either way —
nothing is deleted.

**Affects:** P0-WP-3 acceptance criterion AC-8 (rewritten) · no change to the 7–9.5 day P0 estimate.

### AC-8, rewritten

| | Old AC-8 | **New AC-8** |
|---|---|---|
| Assertion | Reference stations and branches **are** created in production mode | **`police_branches` is populated (15 rows); `police_stations` and `locations` have ZERO rows** in production mode |
| Demo mode | — | unchanged: branches, locations and all 8 stations still seeded under `SENTINEL_SEED_DEMO_DATA=1` |

New tests for `backend/test_production_init.py`:

```python
def test_production_creates_branch_reference_data(self):
    """CID authorization needs police_branches; all four units FK to it."""
    self.assertEqual(self.count('police_branches'), 15)

def test_production_creates_no_stations(self):
    """Station provisioning is HQ's, not CID's (HQ-1)."""
    self.assertEqual(self.count('police_stations'), 0)

def test_production_creates_no_location_rows(self):
    """The locations table is never read; nothing should seed it."""
    self.assertEqual(self.count('locations'), 0)

def test_checkpoint_scoping_works_without_location_rows(self):
    """NEGATIVE CONTROL for my earlier incorrect claim that the three
    locations rows were load-bearing. Scoping reads CHECKPOINT_LOCATIONS,
    a constant — a checkpoint officer must still be correctly scoped with
    the table empty."""

def test_demo_mode_still_seeds_stations(self):
    self.assertEqual(self.fresh(env={'SENTINEL_SEED_DEMO_DATA': '1'}).count('police_stations'), 8)
```

`test_checkpoint_scoping_works_without_location_rows` exists specifically because I got this wrong
once already. It must be run and seen to pass before the claim is repeated.

---

## 6. What changed in the decision set

| Decision | Before | After |
|---|---|---|
| **A-18** | "Approve the 8 stations, their tiers and cell capacities" | **"Create `police_branches` only; HQ provisions stations"** — station list, tiers and capacities **removed** |
| C-1 (addendum) | Station table presented for your validation | Replaced by this analysis; the **`locations` "load-bearing" claim is withdrawn as incorrect** |
| A-10, A-11, A-11a, A-16, A-16a, A-17, A-19, A-13 | — | **Unchanged** |

**Still nine decisions.** No estimate changes.

---

## 7. Limits of this analysis

- **Static analysis plus DDL reading.** I did not execute a production-mode initialization, because
  that mode does not exist yet.
- **The `crime_incidents` dependency is certain** — it is a `NOT NULL` foreign key and an explicit
  runtime check, both read directly.
- **The `locations` finding is certain** — there is no read path and no endpoint.
- **I cannot tell you whether the eight station records are operationally accurate, and I should
  not have asked.** That is HQ's to own.
