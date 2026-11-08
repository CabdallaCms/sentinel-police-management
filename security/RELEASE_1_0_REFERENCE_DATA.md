# Release 1.0 Reference Data — Airport scope, authoritative branch data, Crime Unit prerequisites

**Date:** 5 November 2026 (see §5 on dates) · **Commit:** `bc5483e` · **Status:** **ANALYSIS — NOT IMPLEMENTED**
**Answers:** the owner's points 1, 2 and 4 of 5 November 2026
**Companion to:** `BRANCH_SCOPE_FAIL_OPEN.md` (point 3) · `HQ_PROVISIONING_AND_READINESS.md` ·
`OWNER_DECISION_SHEET.md` §6

---

## 1. Airport branch records — 9 versus 12

### 1.1 Are Airport branch records technically required during Release 1.0?

**No.** Verified:

| Check | Finding |
|---|---|
| `airport_passengers.branch_id` | `INTEGER REFERENCES police_branches(id) ON DELETE SET NULL` — **nullable**, no row required |
| Who reads airport branches | `GET /api/airport-records` (`server.py:8465`) and `POST` (`9214`) — both gated on the **`airport`** module |
| Which Release 1.0 role holds `airport` | **None.** `ROLE_FINGERPRINT`, `ROLE_CID`, `ROLE_CHECKPOINT_*` do not. Only `ROLE_ADMIN` and `ROLE_CHIEF`, both of which are unscoped anyway |
| Does anything require one row per unit type? | **No.** `BRANCH_UNIT_TYPES` is used only as a validation vocabulary (`server.py:4041`, `9096`) and as catalogue metadata (`4009`, `8357`). Nothing enumerates rows and expects five groups |
| Startup validation | None. `init_db()` seeds with `ON CONFLICT DO NOTHING` and asserts nothing afterwards |

Supporting evidence that four unit types were the original design: `server.py:3126` describes a
legacy CHECK constraint limited to `('fingerprint','crime','checkpoint','airport')`, widened later
to admit `police_station`. Airport was part of the original CID four; `police_station` was bolted on
afterwards.

### 1.2 Consequences — 9 versus 12

| | **9 rows** (fingerprint, crime, checkpoint) | **12 rows** (+ airport) |
|---|---|---|
| Release 1.0 function | Complete. All three units scope correctly | Identical — the 3 extra rows are inert |
| Unnecessary records | None | **3 rows describing a deferred release** |
| Data accuracy | Only structures in use are asserted | Asserts an Airport branch structure nobody has authorized, built on names that are themselves unverified (§2) |
| If branch names change before 1.1 | Nothing to correct | 3 rows to correct or they silently misdirect scoping |
| Release 1.1 readiness | Airport branches must be created first — **a gate** | Already present |
| **Risk if an Airport account is created while no airport branch exists** | `user_branch_scope(…,'airport')` → `None` → **sees every airport record** (**S-14**) | Resolves normally |
| Reversibility | Add 3 rows at 1.1 — a normal branch creation | Rows already exist |

The last-but-one row is the only real argument for 12, **and it is an argument about the S-14
defect, not about Airport.** Once branch scoping fails closed, an Airport officer with no airport
branch is *refused*, not *over-served* — and the risk disappears.

Note also that in Release 1.0 the `airport_passengers` table is **empty**, so even today there is
nothing for an unscoped airport session to leak. The exposure is prospective, not current.

### 1.3 Recommendation — the minimum correct configuration

**9 rows: 3 branches × 3 Release 1.0 unit types (`fingerprint`, `crime`, `checkpoint`).**

Rationale:

1. **It is the minimum that is sufficient.** Every Release 1.0 unit scopes correctly; nothing else
   is needed.
2. **It creates no record for a release that has not been specified.** Consistent with the
   reasoning that removed the eight stations: do not create operational records on someone else's
   behalf, in advance, from unverified defaults.
3. **The deferred risk is governed by a gate, not by pre-creating rows** — see below.

**Release 1.1 entry gate (record this; it is the price of choosing 9):**

| # | Gate | Owner |
|---|---|---|
| G-1 | **S-14 fixed and verified** before any Airport account exists | Engineering |
| G-2 | Airport branch records created for each operating location, confirmed per §2 | CID deployment authority |
| G-3 | Each Airport officer's posting resolves (`resolved: true`) before first login | System Administrator |

**If you would rather not carry G-1…G-3, choose 12** — it is defensible, and the three rows are
harmless once the names are confirmed. I recommend 9 because the cost of 12 is three unverified
records in an operational police database, and that is the exact category of record this whole
review has been removing.

---

## 2. Authoritative branch data — what is required

**Standing position: the three existing names are developer defaults and are NOT approved
production data.** `DEFAULT_POLICE_BRANCHES` (`server.py:1660`) is a hard-coded tuple with no
documented authority. Nothing below assumes they are correct, and the request in §2.2 is written so
it can be answered **without reference to them**.

### 2.1 Why this is not cosmetic

Branch records are the CID authorization boundary:

- `users.branch` is **free text**, fuzzy-matched against `police_branches.name`
  (`_branch_match_score`, threshold `POSTING_MATCH_MIN = 45`).
- `MODULE_UNIT_TYPES` maps `cid → crime`, so CID sessions resolve against the **`crime`** rows.
- A posting that does not resolve currently yields **unrestricted access** (**S-14**), and after the
  fix will yield **403**.

So: **wrong branch names today mean a cross-branch data leak; wrong branch names after the S-14 fix
mean officers locked out.** Either way the list must be right before go-live.

### 2.2 Information required from the responsible authority

Per branch, per unit. The system stores exactly four fields plus a lifecycle flag.

| # | Item | Why it is needed | Constraint |
|---|---|---|---|
| **B-a** | **Official branch name**, exactly as it will be written on officer postings | The matching key for authorization. Must be the operational name, not a colloquial one | `TEXT NOT NULL`. Must be unique per (name, region, unit type) |
| **B-b** | **Region** | Stored; also a scoring hint when a posting names only the region | **Must be one of `Sool`, `Sanaag`, `East Togdheer`** — if a branch sits elsewhere, that is a schema change, flag it |
| **B-c** | **District** | Stored; scoring hint | Should be one of the districts listed for that region (§2.4) |
| **B-d** | **Which CID units operate at this branch** | One row per unit per branch. A branch with no Fingerprint presence should have no `fingerprint` row | Subset of `fingerprint`, `crime`, `checkpoint` (+ `airport` at 1.1) |
| **B-e** | **Complete list, or explicit confirmation of completeness** | A branch omitted means its officers cannot be scoped | — |
| **B-f** | **The exact posting string each CID account will carry**, per account | This is what is matched. If postings are written differently from the branch name, scoping breaks | Should equal B-a |
| **B-g** | **Naming authority and effective date** | So the register records who approved it and when, rather than "it was in the code" | — |

### 2.3 Request template

> For each CID branch, please confirm:
>
> | Official branch name | Region | District | Units operating there |
> |---|---|---|---|
> | | | | Fingerprint / Crime / Checkpoint |
>
> And:
> - Is this the **complete** list of CID branches for Release 1.0? (yes / no)
> - What exact posting text will each CID user account carry?
> - Who is the approving authority, and from what date is this effective?
>
> Please answer from the operational source of truth. **Do not validate a list we supply** — the
> names currently in the system are developer defaults and carry no authority.

### 2.4 Constraints the authority must know

- **Regions are limited to `Sool`, `Sanaag`, `East Togdheer`** (`STATION_REGIONS`). Anything else
  needs a code change.
- **Districts per region** (`STATION_DISTRICTS`):
  - Sool — Laascaanood, Caynabo, Xudun, Taleex
  - Sanaag — Ceerigaabo, Ceel Afweyn, Garadag, Badhan, Dhahar
  - East Togdheer — Burao, Oodweyne, Buuhoodle
- **Branches are never deleted** — deactivated via `active = 0`, preserving foreign keys.
- **Spelling matters.** The system currently carries three spellings of one place: branch
  `Lasanod Branch`, district `Laascaanood`, station `Las Anod Station`. Whatever is chosen should be
  used consistently, because postings are matched on it.

### 2.5 Until the authority answers

**No production initialization should run.** If the eventual names differ from the defaults, rows
seeded now become wrong rows that must be deactivated and replaced — and in the window before that,
every mismatched posting is an S-14 exposure. **Confirming the branch list is a prerequisite to
A-18, not a follow-up.** Recorded as **PRE-3**.

---

## 3. Crime Unit incident prerequisites

### 3.1 Complete prerequisite chain

Everything `POST /api/crimes` → `register_crime()` (`server.py:5287`) requires, in evaluation order:

| Order | Requirement | Source | Failure message |
|---|---|---|---|
| 1 | Caller holds the `crimes` module | module gate | 403 |
| 2 | Caller is not a read-only role | `enforce_read_only` | 403 |
| 3 | **`station_id` supplied** | `fields['station_id']` | `station_id is required` |
| 4 | **Station exists** — by `station_id`, else `resolve_station_with_branch()` | `police_stations` | `Station "X" does not exist` |
| 5 | **`officer_id` resolves to an existing officer** — numeric id or `service_id`; **no rank, unit, station or duty-status check** | `officers` | `Desk officer_id is required and must refer to an existing officer` |
| 6 | `category` ∈ `CRIME_CATEGORIES` | 10 values | `Crime category is required and must be one of: …` |
| 7 | `incident_at` non-empty | — | `Incident date/time is required` |
| 8 | `location_of_occurrence` non-empty | — | `Location of occurrence is required` |
| 9 | `description` non-empty | — | `Incident description is required` |
| 10 | `severity` ∈ `CRIME_SEVERITIES` if supplied | optional | `Severity must be one of: …` |
| 11 | `branch_id` resolved via `resolve_branch(c, …, 'crime')` | nullable | — |
| 12 | Evidence slot type required when a file is attached | optional | `Evidence slot N type is required when a file is attached` |

Then: `file_number = new_crime_file_number(c, station['code'])` and the INSERT, where
`station_id NOT NULL` and `officer_id NOT NULL`.

### 3.2 Standing data that must exist first

| # | Prerequisite | Owner | Created by |
|---|---|---|---|
| **PRE-1** | ≥ 1 real police station | **HQ** (System Administrator) | *Register police station* → `POST /api/stations`. Requires name, tier, region, district, **contact phone** |
| **PRE-2** | ≥ 1 registered officer at that station | **HR Directorate** | multipart `POST /api/officers`. Requires rank, unit, station, enlistment date, full name, mother's name, DOB, place of birth, contact number, **photo**, **primary document + type**, guarantor name/address/contact |
| **PRE-3** | Confirmed CID branch list (§2) | **CID deployment authority** | Branch Management |
| **PRE-4** | Each CID user's posting resolves | System Administrator | user administration |
| **PRE-5** | Station codes confirmed before first use | **HQ** | — see §3.3 |

Note PRE-2's asymmetry: HR's registration standard is demanding, but **the Crime Unit itself checks
only that the officer row exists.**

### 3.3 Preventing fabricated station codes in official file numbers

> *"Ensure that no placeholder station or fabricated station code can be used to generate official
> crime file numbers."*

**Why this matters.** `new_crime_file_number()`:

```python
token  = re.sub(r'[^A-Za-z0-9-]', '', station_code or 'STN')
prefix = f'CRM-{year}-{token}-'
return f'{prefix}{n:04d}'
```

`crime_incidents.file_number` is `TEXT UNIQUE NOT NULL` — the permanent, citable case reference.
**A station code chosen today is embedded in every case file raised at that station, forever.**
Renaming the station afterwards does not rewrite issued file numbers.

**The three ways a fabricated station can currently appear** (all three verified in source):

| # | Path | Creates |
|---|---|---|
| 1 | `resolve_station_with_branch()` `server.py:4700` — any reference to `BR-<id>` | tier hard-coded `'District HQ'`, `operational_status 'Active'`, **no contact phone**, `created_by NULL`, notes `'Mirrored from branch N (auto)'` |
| 2 | same, `server.py:4724` — legacy numeric branch id | as above, notes `'… (auto numeric)'` |
| 3 | `POST /api/branches` with `unit_type='police_station'` `server.py:9145` | as above, but `created_by` set; wrapped in `except Exception: pass` |

**A station created by any of these paths produces a perfectly valid-looking `STN-…` code**, which
then becomes the permanent prefix of real case references. Note that path 4 — `register_crime()`
itself calling `resolve_station_with_branch()` at `server.py:5293` — means **recording a crime
incident can itself create the station it is filed against.**

**Recommended guards** (specification only — not implemented):

- **G-a — Reject auto-mirrored stations at crime intake.** In `register_crime()`, after resolving
  the station, refuse any station that is not a properly registered record:

  ```python
  if not station['contact_phone'] or station['created_by'] is None:
      raise ValueError(
          'This station is a provisional record and cannot be used to file a crime '
          'incident. Ask an administrator to complete its registration first.')
  ```

  `contact_phone` is **mandatory** in `register_station()` and **absent** from all three auto-mirror
  paths, so it is a reliable discriminator. It also catches the eight legacy seeded stations, which
  likewise have no phone — correctly, since they are not authoritative records either.

- **G-b — Do not create stations as a side effect of filing a crime.** `register_crime()` should
  call a non-creating resolver. Creating an operational station as a side effect of recording an
  incident is wrong regardless of the code format.

- **G-c — Require `operational_status = 'Active'`.** A crime should not be filed against a station
  marked `Inactive` or `Maintenance`.

- **G-d — Confirm codes before first use (PRE-5).** A guard cannot fix a code already embedded in
  issued file numbers; only sequencing can.

**Tests:**

| Test | Asserts |
|---|---|
| `test_crime_rejects_auto_mirrored_station` | Filing against a `BR-<id>` mirrored station → 400 |
| `test_crime_rejects_station_without_contact_phone` | Provisional record → 400 |
| `test_crime_does_not_create_a_station` | `police_stations` count unchanged after a failed filing |
| `test_crime_rejects_inactive_station` | `Inactive` station → 400 |
| `test_crime_accepts_properly_registered_station` | **Negative control** — a station created via `POST /api/stations` works |
| `test_file_number_uses_the_registered_code` | `file_number` begins `CRM-<year>-<station code>-` |

**Effort: 1–2 days**, inside P0-WP-3. No schema change.

> **Scope note.** G-a…G-c change `register_crime()` — application code. They are **recommendations
> for your approval**, not part of A-18, and nothing is implemented. If you prefer to keep P0
> strictly to initialization, these become a separate work package; I would not defer G-b far,
> because it is the path by which a crime filing invents a station.

---

## 4. Revised recommendation summary

| Item | Recommendation |
|---|---|
| Branch rows in production | **9** — 3 branches × fingerprint, crime, checkpoint |
| Airport branches | **Defer to 1.1**, behind gates G-1…G-3 |
| Branch names | **Not approved.** Obtain B-a…B-g from the authority (PRE-3) before initializing |
| Stations | **0** — HQ provisions (PRE-1) |
| `locations` | **0** — never read |
| **Ordering** | **S-14 must be fixed before A-18 is implemented** — otherwise `/api/crimes` leaks every incident |

---

## 5. Document dates — disclosure

**There is a conflict between two sources of the current date, and I have been silently picking one.
Stating it plainly:**

| Source | Value |
|---|---|
| My operating instruction for this session | **5 November 2026** |
| The sandbox system clock (`date -u`) | **8 November 2026** |

What happened:

1. Documents written in earlier turns were dated **7 November 2026**, taken from the sandbox clock
   at the time.
2. Last turn I "corrected" the newer documents to **5 November 2026** to match my instruction, and
   reported that as fixing an error.
3. The sandbox clock now reads **8 November 2026**, so it is advancing independently.

**I cannot determine which is the true calendar date**, and I should have flagged the conflict last
turn instead of presenting one value as the correction.

**Current state:** `OWNER_DECISION_SHEET.md`, `OWNER_DECISION_SHEET_ADDENDUM.md`,
`REFERENCE_DATA_SCOPE_ANALYSIS.md`, `HQ_PROVISIONING_AND_READINESS.md` and the two documents added
this turn are dated **5 November 2026**. Eleven older documents still read **7 November 2026**:

`STAGE_0_REPORT.md`, `planning/BIOMETRIC_PROCUREMENT_PLAN.md`, `planning/D23_LEGAL_ACTION_BRIEF.md`,
`planning/LEGAL_ACTION_PLAN.md`, `security/CREDENTIAL_ROTATION_PROCEDURE.md`,
`security/DOCUMENT_AUTHORIZATION_TEST_DESIGN.md`,
`security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md`, `security/P0_TECHNICAL_CLARIFICATION.md`,
`security/P0_WORK_PACKAGES.md`, `security/PRODUCTION_INITIALIZATION.md`,
`security/REMEDIATION_PLAN.md`, `security/SECURITY_ISSUE_REGISTER.md`,
`security/SUSPECT_ALERT_LIFECYCLE.md`.

**I have not mass-edited them**, because that is churn across 13 files to resolve a discrepancy only
you can settle. **Tell me the correct date and I will normalise every document in one pass.**

No dated claim in any document depends on the calendar date — all ordering is by commit SHA
(`a1c2478` → `e7263d7` → `41b4843` → `595ec3b` → `389787b` → `05bac05` → `9853683` → `4cc3067` →
`bc5483e`), which is unambiguous.
