# HQ Provisioning, Officer Provisioning and Crime Unit Readiness

**Date:** 5 November 2026 · **Commit:** `4cc3067` · **Status:** **CLARIFICATION — NOT IMPLEMENTED**
**Answers:** the owner's five questions of 5 November 2026
**Companion to:** `REFERENCE_DATA_SCOPE_ANALYSIS.md` · `OWNER_DECISION_SHEET.md` §6 (A-18) ·
`P0_TECHNICAL_CLARIFICATION.md` §7

> Nothing implemented. No database created or modified. `backend/server.py` is byte-identical to
> `e7263d7` (sha256 `a8211f4f…b3b9fc`).

---

## ⚠ One finding changes A-18. Read this first.

**A-18 option (a) as I wrote it — "seed `police_branches`, create no stations" — does not actually
hold. Seeding the branch table as it stands would still cause station records to be created.**

`init_db()` seeds **15** branch rows: 3 branch names × **5** `BRANCH_UNIT_TYPES`. The fifth unit
type is **`police_station`** — not a CID unit.

And a `police_station` branch **silently creates a `police_stations` row** through **three**
separate code paths:

| # | Site | Trigger |
|---|---|---|
| 1 | `resolve_station_with_branch()` `server.py:4700` | Any officer, vehicle or crime incident posted against the identifier `BR-<id>` |
| 2 | `resolve_station_with_branch()` `server.py:4724` | Same, via the legacy numeric branch id |
| 3 | `POST /api/branches` `server.py:9145` | **Creating** a `police_station` branch mirrors it as a station immediately |

Site 3 is wrapped in `except Exception: pass` — if the mirror fails, it fails **silently**.

The INSERT at site 1:

```python
c.execute('''INSERT INTO police_stations(station_id,name,code,region,district,village,
    station_tier,operational_status,notes,created_by)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
    (st_id, branch['name'], st_code, branch['region'], b_district, village,
     'District HQ', 'Active', f'Mirrored from branch {branch["id"]} (auto)', None))
```

The auto-created station gets:

| Field | Value | Problem |
|---|---|---|
| `station_tier` | **hard-coded `'District HQ'`** | The system invents an HQ-owned classification |
| `operational_status` | `'Active'` | Asserts an operational fact nobody confirmed |
| `contact_phone` | **absent** | `register_station()` *rejects* a station without one |
| `created_by` | `NULL` | No accountable author |
| `notes` | `'Mirrored from branch N (auto)'` | Marked machine-generated |

Sites 2 and 3 produce the same shape (`notes` reading `'Mirrored from branch N (auto numeric)'` and
`'Mirrored from branch N'` respectively; site 3 does record `created_by`).

**So the three `police_station` branch rows are a latent station-creation mechanism, reachable three
different ways.** Leaving them in the production seed would let the system manufacture station
records with a fabricated tier — precisely what you ruled out of CID scope.

**Correction to A-18 option (a): seed only the four CID unit types — 12 rows, not 15.**

| | Rows | Unit types |
|---|---|---|
| Current seed | 15 | fingerprint, crime, checkpoint, airport, **police_station** |
| **Revised (a)** | **12** | fingerprint, crime, checkpoint, airport |

This is not a cosmetic trim. It is what makes "no fictional stations" true rather than aspirational.
It also matches the seed loop's own comment, which already claims to seed branches *"for each CID
unit"* (`server.py:3267`) while actually iterating all five.

---

## 1. HQ station provisioning — the operational process

> *"Identify whether an existing HQ interface or another authorized process handles this. Do not
> assume direct database editing is the permanent solution."*

**You were right to push on this. Direct database editing is not required and should never be the
process — a complete, validated, audited station management interface already exists and works
today.**

### 1.1 The existing interface

| Layer | Location | Function |
|---|---|---|
| **UI — register** | `index.html:1851` — "Register police station" drawer (`stForm`) | Full form; submits `POST /api/stations` (`index.html:12350`) |
| **UI — edit** | `index.html:1892` — Edit drawer (`stEditForm`) | Submits `PATCH /api/stations/<id>` (`index.html:12193`) |
| **UI — view** | Registered Stations table + View drawer | Registry fields, deployment counters, branch lineage |
| **API — create** | `POST /api/stations` → `register_station()` (`server.py:4915`) | Validates and persists |
| **API — edit** | `PATCH` / `PUT /api/stations/<id>` → `update_station()` | Field-level PATCH semantics |
| **API — read** | `GET /api/stations`, `GET /api/stations/<id>` | Register + detail |
| **API — delete** | **none** | See §1.4 |

The UI block is marked `<!-- Register police station (SystemAdmin / stations:manage only) -->` and
wrapped in `.admin-write`, so the controls are hidden from non-administrators as well as refused by
the server.

### 1.2 Who is authorized

Station writes pass **two** independent gates:

```
POST /api/stations
  ├─ enforce_read_only(user, 'POST', path)   → 403 for read-only roles
  ├─ module gate: post_module_for_path['/api/stations'] = 'admin'
  └─ require_records_admin(user, 'Registering a police station')   → 403 for every non-Admin
```

| Role | `stations` module | Can read register | **Can create/edit stations** |
|---|---|---|---|
| **SystemAdmin (Admin)** | yes | yes | **YES — the only role that can** |
| HR Directorate | yes | yes | **No** — 403 (`require_records_admin`); holds no `admin` module |
| Chief Commander / Commander | yes | yes | **No** — globally read-only (`enforce_read_only`) |
| CID (Crime Unit) | **no** | yes, via the `crimes` exception | **No** |
| Fingerprint / Airport / Checkpoint | no | no | No |

**Station provisioning is a System Administrator function, performed in the application.**

> **Observation worth recording (not a decision):** `CHIEF_PERMISSIONS` grants the Chief Commander
> `PERM_STATIONS_MANAGE = 'stations:manage'` (`server.py:1389`, `1396`), and the POST module gate
> honours it (`server.py:9192`). But `enforce_read_only` and `require_records_admin` both reject the
> Chief first, so **the permission can never take effect.** It is dead capability. Harmless today —
> it grants nothing — but it means the code reads as though Command can provision stations when it
> cannot. If HQ's intended provisioning authority is actually the Chief Commander rather than the
> System Administrator, that is a real gap and needs its own decision. **I am not assuming either
> way.**

### 1.3 What the interface enforces (`register_station()`)

| Field | Required | Validation |
|---|---|---|
| `name` | **yes** | non-empty |
| `station_tier` | **yes** | `Regional HQ · District HQ · Outpost · Checkpoint · Border Post` |
| `region` | **yes** | `Sool · Sanaag · East Togdheer` |
| `district` | **yes** | must belong to the region (`STATION_DISTRICTS`) |
| `contact_phone` | **yes** | non-empty |
| `code` | auto | `new_station_code()` → **`STN-<REGION>-NNN`** |
| `station_id` | auto | `new_station_id()` → `ST-NNN` |
| `village` | no | free text |
| `operational_status` | defaults `Active` | `Active · Inactive · Maintenance` |
| `cell_capacity` | no | integer ≥ 0 |
| `commander_id` | no | must be an existing officer of rank **Inspector or above** |
| `deputy_id` | no | must be an existing officer |
| `notes` | no | free text |

`STATION_DISTRICTS` (`server.py:1699`):

| Region | Districts |
|---|---|
| Sool | Laascaanood, Caynabo, Xudun, Taleex |
| Sanaag | Ceerigaabo, Ceel Afweyn, Garadag, Badhan, Dhahar |
| East Togdheer | Burao, Oodweyne, Buuhoodle |

Every create and edit is audited: `audit(c, user, 'CREATE', 'police_station', …)`; edits record
`changed_fields`, `updated_at` and `updated_by`.

**The commander/officer circularity resolves cleanly:** `commander_id` is **optional** at
registration, so HQ registers the station first, HR posts officers to it, then HQ sets the
commander. No deadlock, no manual SQL.

### 1.4 Stations cannot be deleted — by design

**There are no `DELETE FROM police_stations`, `DELETE FROM officers` or `DELETE FROM
police_branches` statements anywhere in the codebase, and `do_DELETE` (`server.py:10076`) exposes no
routes at all** — it answers 405 for every path.

Decommissioning is `operational_status = 'Inactive'`, a reversible edit that preserves every foreign
key. This directly supports your instruction that existing station data must not be deleted: **the
application is structurally incapable of deleting it.**

### 1.5 The eight seeded stations could not have been created through this interface

Evidence that they are a legacy fixture, not records produced by the sanctioned process:

| Check | Seeded rows | What the API produces |
|---|---|---|
| Code format | `SAN-C-01`, `SOO-C-03`, `TOG-C-01`, `ETG-C-03` | **`STN-SAN-001`** — `new_station_code()` emits `STN-<code>-NNN`; the SPA field placeholder is literally `STN-REG-XXX` |
| Region prefixes | `SOO-`, `TOG-` | `REGION_CODES` = `Sool→SOL`, `Sanaag→SAN`, `East Togdheer→ETG` — **`SOO` and `TOG` are not valid codes** |
| `contact_phone` | **not set** | **required** — `register_station()` raises `'Contact phone is required'` |
| `created_by` | not set | the acting administrator's user id |
| `operational_status` | not set (falls to DDL default) | explicit |

> **This corrects an anomaly I reported earlier.** In the addendum I flagged ST-007's `ETG-C-03` as
> the odd one out against `TOG-`. That was backwards: `ETG` is the *valid* region code and `TOG` is
> not. More to the point, **all eight codes are in a format the application would never generate.**
> I had compared the seeds to each other instead of to the code generator.

These are HQ data-quality matters, outside CID scope, listed here only as evidence about the
provisioning process. **No change to them is proposed.**

### 1.6 The recommended process

1. **System Administrator** opens Police Stations → *Register police station*.
2. Enters name, tier, region, district, contact phone; optionally village, cell capacity, notes.
3. System assigns `station_id` and `code` (`STN-…`); writes an audit record.
4. Commander/deputy assigned afterwards, once officers exist.
5. Changes made via the Edit drawer; closures via `operational_status = 'Inactive'`. Never deleted.

**No direct database access at any point.**

---

## 2. Officer provisioning

### 2.1 Process and authority

| | |
|---|---|
| Endpoint | `POST /api/officers` → `register_officer()` (`server.py:4160` region) |
| Content type | **`multipart/form-data`** (file uploads are mandatory) |
| Module gate | `officers` |
| Authorized | **HR Directorate** and **SystemAdmin**. Chief Commander blocked by `enforce_read_only`. CID cannot create officers |
| Service ID | auto — `new_service_id()` → **`POL-<YYYY>-NNNN`** |
| Audit | `audit(c, user, 'CREATE', 'officer', service_id, "<name> @ <station>")` |

**Officer provisioning belongs to the HR Directorate, not HQ and not CID.**

### 2.2 Required fields

Mandatory — registration fails on the first missing one:

| Section | Fields |
|---|---|
| Official | `rank` (∈ `OFFICER_RANKS`), `unit` (∈ `OFFICER_UNITS`), **`station_id`**, `date_of_enlistment` |
| Personal | `full_name`, `mother_name`, `date_of_birth`, `place_of_birth`, `contact_number` |
| Files | **`photo`** (validated image), **`doc1_file`** + `doc1_type` |
| Guarantor | `guarantor_name`, `guarantor_address`, `guarantor_contact` |

Optional: `duty_status` (default `Active`), height, weight, blood group, origin region/district/town,
`guarantor_occupation`, `guarantor_relationship`, `guarantor_photo`, second document slot.

`station_id` is resolved against `police_stations.station_id`, then via
`resolve_station_with_branch()`; failing both → `'Assigned station "X" does not exist'`.

### 2.3 What Crime Unit incident recording requires of an officer

`register_crime()` (`server.py:5287`) requires `officer_id` and resolves it through
`resolve_officer_row()`:

```python
officer = resolve_officer_row(c, fields.get('officer_id'))
if not officer:
    raise ValueError('Desk officer_id is required and must refer to an existing officer')
```

`resolve_officer_row()` accepts **either** the numeric `officers.id` **or** the `service_id`
(`POL-YYYY-NNNN`). It performs **no** check on rank, unit, duty status or station.

**So the Crime Unit's requirement is minimal: one existing officer row, any officer.** The field is
the *desk officer* recording the report. Everything else `register_officer()` demands — guarantor,
photo, documents — is HR's completeness standard, not a Crime Unit prerequisite.

**Practical consequence:** the Crime Unit needs **at least one registered officer**, and HR cannot
register one without a station. One real station plus one real officer unblocks incident recording.

---

## 3. Branch reference data

### 3.1 Source of the three records

`DEFAULT_POLICE_BRANCHES` (`server.py:1660`) — a hard-coded constant:

```python
DEFAULT_POLICE_BRANCHES = (
    ('Buuhoodle Branch', 'East Togdheer', 'Buuhoodle'),
    ('Lasanod Branch',   'Sool',          'Laascaanood'),
    ('Erigavo Branch',   'Sanaag',        'Ceerigaabo'),
)
```

Seeded by `init_db()` (`server.py:3266–3272`) as 3 × 5 = **15 rows**, `ON CONFLICT DO NOTHING`, with
a case-insensitive unique index on `(name, region, unit_type)`.

**Provenance, stated plainly: these three names originate in application source code, not from a
documented HQ or CID authority.** They are developer-authored defaults. Each names one district
capital of the three regions the system covers, and each is internally consistent with
`STATION_DISTRICTS`. **I cannot confirm they are the correct production branch list — that
confirmation has to come from whoever owns CID deployment geography.**

One spelling note: the branch is `Lasanod Branch` while the canonical district is `Laascaanood`
(`STATION_DISTRICTS`), and the seeded station is `Las Anod Station`. Three spellings of one place.
Harmless to matching (§3.2 scores on the district too), but it is the kind of inconsistency that
makes registers hard to reconcile later.

### 3.2 How branch records affect authorization

**This is the part that matters, and it means the branch names are not cosmetic.**

```
user.branch (free TEXT, NOT NULL)  ──fuzzy match──▶  police_branches.name
                                                            │
                        restricted to the session's unit_type (MODULE_UNIT_TYPES)
                                                            │
                                                            ▼
                                            branch_scope_view() → branch_id
                                                            │
                                  require_record_branch_scope() → 403 on mismatch
```

- `users.branch` is **free text** (`users` DDL: `branch TEXT NOT NULL`). There is no foreign key to
  `police_branches`.
- `resolve_posting_branch()` (`server.py:~2600`) scores every branch of the session's unit type with
  `_branch_match_score()`: exact name **100**, posting contained in branch name **70–80**, branch
  name contained in posting **72**, district hint **62**, region hint lower. Threshold
  `POSTING_MATCH_MIN = 45`, and the best match must be **unique**.
- `MODULE_UNIT_TYPES` maps the session's module to a unit type:
  `fingerprint→fingerprint`, `airport→airport`, **`cid→crime`**, `checkpoints→checkpoint`,
  `stations→police_station`.

**So a CID session is scoped by the `crime` branch rows.** That is the direct, verified link between
this table and CID authorization, and it confirms the branch rows are genuine CID reference data.

**The failure mode you should know about:** if a user's `branch` text does not resolve to exactly
one branch, `resolve_posting_branch()` returns `None`, and `branch_scope_view()` returns `None` —
which downstream means **unscoped**, not **denied**. The docstring is explicit that callers *"must
treat that as 'no scope', never as 'scope to everything'"*, and `require_record_branch_scope()`
honours that. But this is the same fail-open shape as finding **H-2b**, already on the register.

**Consequence for production:** if HQ's real branch names differ from these three, officer postings
written against the real names will not resolve, and those sessions land in the unscoped path. **The
branch list must be correct before CID goes live — not for cosmetic reasons, but because branch
scoping is the CID authorization boundary.**

### 3.3 Are these the correct production records?

**I cannot confirm it, and I will not assume it.** What I can state:

| | |
|---|---|
| Structurally valid | **Yes** — all three regions/districts are in `STATION_DISTRICTS`; the unique index holds |
| Functionally required | **Yes** — all four CID units FK to this table; CID scoping resolves against the `crime` rows |
| Authoritatively confirmed | **No** — hard-coded developer defaults, no documented source |

**This needs confirmation from the CID deployment authority before go-live.** Unlike the station
list, it *is* inside CID scope — it is CID's own branch structure — so it is yours (or your
delegate's) to confirm. It is recorded as prerequisite **PRE-3** in §4.

---

## 4. Crime Unit readiness — HQ prerequisites

Ordered; each step depends on the one before.

| # | Prerequisite | Owner | Blocks | Verification |
|---|---|---|---|---|
| **PRE-1** | Register **≥ 1 real police station** via *Register police station*. Needs name, tier, region, district, contact phone | **HQ** (System Administrator) | All officer registration and all incident recording | `GET /api/stations` returns ≥ 1 non-mirrored row |
| **PRE-2** | Register **≥ 1 officer** per station used as a crime desk — multipart, with photo and primary document | **HR Directorate** | Incident recording | `GET /api/officers` returns ≥ 1 row |
| **PRE-3** | Confirm the **three CID branch names and placements**, or replace them with the real list | **CID deployment authority** | Branch scoping correctness (§3.2) | Each CID user's posting resolves — `posting_scope_status().resolved == true` |
| **PRE-4** | Ensure each CID user's `users.branch` posting text resolves to exactly one `crime` branch | **System Administrator** | Per-user scoping | As PRE-3, per account |
| **PRE-5** | Confirm station **codes** before first use — they are embedded permanently in crime file numbers (§4.1) | **HQ** | Nothing technically; permanent identifiers | Review `code` on each station |

### 4.1 Why PRE-5 matters more than it looks

Crime file numbers are derived from the station code (`new_crime_file_number()`, `server.py`):

```python
prefix = f'CRM-{year}-{token}-'      # token = station code, stripped of non-alphanumerics
return f'{prefix}{n:04d}'            # e.g. CRM-2026-STN-SOL-001-0001
```

`crime_incidents.file_number` is **`TEXT UNIQUE NOT NULL`** and is the citable case reference.
**A station code chosen today is embedded in every case file raised at that station, permanently.**
Renaming a station later does not rewrite the file numbers already issued.

This is the strongest argument against the rejected option (b): a placeholder station would stamp a
fabricated code into real case references — unfixable after the fact.

### 4.2 The dependency chain

```
PRE-1  HQ registers a real station
   │        (needs: name, tier, region, district, phone)
   ▼
PRE-2  HR registers an officer at that station
   │        (officers.station_id is NOT NULL)
   ▼
Crime Unit can record an incident
            (crime_incidents.station_id NOT NULL + officer_id NOT NULL)
```

**Until PRE-1 and PRE-2 are complete, the Crime Unit is non-functional.** Fingerprint, Checkpoint
and Airport are unaffected and can operate on an empty station table.

### 4.3 What this costs

**No engineering effort.** These are data-entry and confirmation steps in an interface that already
exists. They belong in the go-live checklist with named owners, not in the P0 work packages. The
7–9.5 day P0 estimate is unchanged.

---

## 5. Production initialization — confirmations

Confirming each item you listed, with the one qualification from the top of this document.

| # | Your requirement | Status |
|---|---|---|
| 5a | **Preserve the existing station table and its schema** | **CONFIRMED.** No `DROP`, no `ALTER`, no change to `police_stations`. Three FKs point at it (two `NOT NULL`); the Crime Unit and the entire officer register depend on it. The table is created by `CREATE TABLE IF NOT EXISTS` exactly as today |
| 5b | **Preserve existing station data** | **CONFIRMED.** No row is deleted or modified. The seed is already guarded by `IF COUNT(*) == 0`, so it never touches a populated table, and the API exposes no delete path at all (§1.4) |
| 5c | **Avoid creating fictional or placeholder stations** | **CONFIRMED — with the correction in §0.** Requires (i) removing the 8-station seed **and** (ii) excluding the 3 `police_station` branch rows, which would otherwise auto-mirror into fabricated station records. Option (b) — one placeholder station — remains rejected |
| 5d | **Seed only CID-required branch reference data** | **CONFIRMED, revised to 12 rows** — 3 branches × 4 CID unit types (`fingerprint`, `crime`, `checkpoint`, `airport`). The `police_station` unit type is HQ's and is excluded |
| 5e | **No `locations` seeding** | **CONFIRMED.** Table retained, never populated — nothing reads it (`REFERENCE_DATA_SCOPE_ANALYSIS.md` §1) |

### 5.1 Production first-run state

| Table | Rows | Why |
|---|---|---|
| `police_branches` | **12** | CID reference data — all four units FK to it; CID scoping resolves against the `crime` rows |
| `police_stations` | **0** | HQ provisions via the existing interface (PRE-1) |
| `locations` | **0** | Never read by anything |
| `officers` | **0** | HR provisions (PRE-2) |
| `users` | **1** (`admin`) | Per A-17; random password per A-19 |
| All demonstration records | **0** | Per A-16 / S-13 |

**Demonstration mode (`SENTINEL_SEED_DEMO_DATA=1`) is unchanged** — 15 branch rows, 3 locations,
8 stations, 9 personas. The ~22 suites that depend on this fixture keep working.

### 5.2 Residual risk I am not hiding

Excluding the `police_station` branch rows from production removes the auto-mirror path **for the
seed**, but **all three code paths in §0 remain in the application.** If an administrator later
creates a `police_station` branch through Branch Management, a station row with a hard-coded
`'District HQ'` tier and no contact phone is created immediately (site 3) — and would also be
created on first reference (sites 1–2).

**I am not proposing to change those paths** — they are outside the agreed scope and outside P0, and
touching them would risk the officer and vehicle flows that depend on them. **I am recording the
behaviour** so it is a decision you make later with the facts, rather than a surprise. The test in
`P0_TECHNICAL_CLARIFICATION.md` §7 asserts on the `police_stations` **table**, not on the seed
block, so it catches a station arriving by any of the three routes during initialization.

**Disclosure:** I found sites 2 and 3 only on a second pass, after writing §0 around site 1 alone.
That is the same under-investigation that produced the `locations` error. Stated here rather than
quietly folded in.

---

## 6. Updated out-of-scope register

Supersedes §3 of `REFERENCE_DATA_SCOPE_ANALYSIS.md`.

| # | Dependency | Owner | Effect on CID Release 1.0 |
|---|---|---|---|
| **HQ-1** | `crime_incidents.station_id` NOT NULL | HQ | Crime Unit blocked until PRE-1 |
| **HQ-2** | `crime_incidents.officer_id` NOT NULL | HR | Crime Unit blocked until PRE-2 |
| **HQ-3** | `officers.station_id` NOT NULL | HR + HQ | Officer registration blocked until PRE-1 |
| **HQ-4** | `officer_conduct_actions.station_id` nullable | HR | None |
| **HQ-5** | Station custodial attributes — tier, cell capacity, commander, deputy, operational status | HQ | None. No CID function |
| **HQ-6** | `/api/stations` readable via the `crimes` module | HQ data, CID reader | Crime Unit reads stations for its incident form. Also part of finding **S-05** |
| **HQ-7** | **NEW** — `police_station` branch unit type auto-mirrors into `police_stations` via **three** code paths (`server.py:4700`, `4724`, `9145`), with a hard-coded `'District HQ'` tier and no contact phone | HQ | Excluded from the production seed; the paths themselves are unchanged (§5.2) |
| **HQ-8** | **NEW** — station `code` permanently embedded in crime file numbers | HQ | Codes should be confirmed before first use (PRE-5) |
| **HQ-9** | **NEW** — `CHIEF_PERMISSIONS` grants `stations:manage`, unreachable behind read-only + admin-only gates | HQ / RBAC owner | None today. Flags a possible mismatch between intended and actual provisioning authority (§1.2) |

---

## 7. Limits

- **Static analysis.** Production-mode initialization does not exist yet, so none of this was
  executed. Every claim cites a file and line; the behavioural claims are specified as tests in
  `P0_TECHNICAL_CLARIFICATION.md` §7 and must be **run and seen to pass** before they are repeated
  as fact.
- **The auto-mirror behaviour (§0) is read from source, not demonstrated.** `test_production_init.py`
  includes a test that fails if the seed produces any station row, which would catch it.
- **I cannot confirm the three branch names are the correct production list** (§3.3), and I cannot
  confirm anything about the eight stations. Both need a human authority.
- **I corrected my own earlier station-code anomaly here** (§1.5). I had compared the seeded codes
  to each other rather than to the generator.
