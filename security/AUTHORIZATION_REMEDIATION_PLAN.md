# Authorization Remediation Plan — S-14, S-15, S-16, Checkpoint, Station Safeguards

**Date:** 5 November 2026 (date conflict unresolved — `RELEASE_1_0_REFERENCE_DATA.md` §5)
**Commit:** `8e0de56` · **Status:** **PLAN — NOTHING IMPLEMENTED**
**Answers:** the owner's points 1–5 and 7 of 5 November 2026

> No application code, schema or initialization changed. `backend/server.py` is byte-identical to
> `e7263d7` (sha256 `a8211f4f…b3b9fc`). Both probes referenced here were throwaway harnesses, run
> against unmodified code and **deleted**. Suite re-verified: **28 PASS / 0 FAIL / 1 BLOCKED**.

---

## 0. A new Critical finding — S-16

While investigating Checkpoint (your point 3) I found a defect more severe than S-14, and it is not
a checkpoint defect. **It is reported first because it changes the shape of the plan.**

### `GET /api/persons/<id>` returns unit records with no module, branch or location filtering

The endpoint is **deliberately not module-gated**. The code says so (`server.py:8374`):

> *"Every authenticated user can see /api/me and the central /api/persons registry, but each unit
> endpoint is restricted to the roles that operate that module."*

That reasoning holds for identity fields. But the handler also attaches **four unit registers**
(`server.py:8449–8461`), each an unfiltered `WHERE person_id=%s`:

```python
person['airport']     = ... FROM airport_passengers      WHERE person_id=%s
person['clearance']   = ... FROM clearance_applications  WHERE person_id=%s
person['alerts']      = ... FROM suspect_alerts          WHERE person_id=%s
person['checkpoints'] = ... FROM checkpoint_events       WHERE person_id=%s
```

**No module check. No branch filter. No checkpoint-location filter.**

### Proven by execution

| # | Probe | Result |
|---|---|---|
| **Q1** | Checkpoint officer (`cp.south`, modules `['checkpoints','dashboard']`) is refused the unit registers | `/api/clearance-applications` **401**, `/api/airport-records` **401**, `/api/crime-cases` **401** ✔ refused |
| **Q2** | **Same officer** reads a Fingerprint record via `/api/persons/<id>` | **200**, `clearance: 1` — returned application `FP-40964580` |
| **Q3** | **Control** — the sibling `/linked-records` filters by module | **200**, `units_returned = []` — Fingerprint correctly absent |
| **Q4** | **A correctly-posted Fingerprint officer** scoped to branch 1 reads branch 11's application | scoped list `[]` ✔ · direct `GET …/FP-40964580` → **403** ✔ · **`/api/persons/<id>` → returns it** ✘ |

**Q3 is the decisive control.** The same session, the same person, the same underlying table: the
sibling endpoint filters correctly and the primary one does not. This is an omission, not a design
choice — `linked_person_records()` applies `if module not in modules: continue` **and**
`checkpoint_scope_sql(...)`, while the primary handler applies neither.

**Q4 is what makes it Critical.** S-14 requires a broken posting. **S-16 requires nothing** — a
correctly configured officer, refused by the front door (403), walks through this one.

| | |
|---|---|
| **ID** | **S-16** |
| **Severity** | **CRITICAL** |
| **Reachable by** | **Any authenticated account**, including roles with no `people` module |
| **Discloses** | Clearance applications, airport movements, suspect alerts, checkpoint events — all branches, all locations, all units |
| **Precondition** | **None** |

> **Scope of the proof.** The **clearance** section was demonstrated empirically (Q2, Q4). The
> `airport`, `alerts` and `checkpoints` sections are the **same three lines in the same handler with
> the same unfiltered `WHERE person_id=%s`**; I did not seed records into them in this run (the
> airport POST returned 400 on fixture fields). Stated as structurally identical, **not** as
> separately measured.

---

## 1. S-14 — remediation design

### 1.1 Separate "unrestricted" from "unresolved"

The root cause is one overloaded return value. `user_branch_scope()` returns `None` for both
*"deliberately unrestricted"* and *"cannot determine"*, and every call site reads `if scope:`.

Replace with an explicit three-state result:

```python
SCOPE_UNRESTRICTED  = 'unrestricted'   # admin / records-admin / Chief / read-only
SCOPE_BRANCH        = 'branch'         # resolved to exactly one branch
SCOPE_INDETERMINATE = 'indeterminate'  # empty, unknown, below threshold, or ambiguous


def branch_scope_state(c, user, unit_type=None):
    """(state, scope|None). Privilege and ignorance are never the same value."""
    if _is_privileged(user):
        return SCOPE_UNRESTRICTED, None
    unit = normalize_branch_unit_type(unit_type) if unit_type else primary_unit_type(user)
    if not unit:
        return SCOPE_INDETERMINATE, None          # was: return None  (open)
    branch = resolve_posting_branch(c, user, unit)
    if not branch:
        return SCOPE_INDETERMINATE, None          # was: return None  (open)
    return SCOPE_BRANCH, {...}
```

Note the two `SCOPE_INDETERMINATE` returns: today **both** of those paths return `None` and are read
as "unrestricted". The missing-unit-type path matters — it is how a session with no recognised unit
reaches an open query.

### 1.2 Fail closed at every call site

One helper, applied uniformly:

```python
def branch_filter(c, user, unit_type, column='branch_id'):
    """('', ()) when unrestricted; (' WHERE col=%s', (id,)) when scoped;
    raises BranchScopeError otherwise. There is no fourth outcome."""
    state, scope = branch_scope_state(c, user, unit_type)
    if state == SCOPE_INDETERMINATE:
        raise BranchScopeError(
            'Your posting does not resolve to a registered branch. Ask an '
            'administrator to correct your posting before using this register.')
    if state == SCOPE_UNRESTRICTED:
        return '', ()
    return f' WHERE {column}=%s', (scope['branch_id'],)
```

**No fallback to unrestricted access.** The function has three branches and the indeterminate one
raises. There is no `else: return ''`.

Deny rather than return an empty list: a scoped officer shown zero records cannot distinguish an
empty branch from a broken posting. An explicit 403 naming the cause makes PRE-4 self-enforcing.

### 1.3 Every affected call site

All call sites of the resolver family (`branch_scope_view`, `user_branch_scope`,
`require_record_branch_scope`, `require_branch_write_scope`, `posting_scope_status`):

| # | Site | Line | Unit type | Kind | Today | Action |
|---|---|---|---|---|---|---|
| 1 | `require_record_branch_scope` | 2790 | param | guard | `if not scope: return` | **fail closed** |
| 2 | `require_branch_write_scope` | 2742 | param | write guard | `if not scope: return branch_row` | **fail closed** |
| 3 | `GET /api/airport-records` | 8465 | `airport` | list | `if scope:` | **fail closed** |
| 4 | `GET /api/clearance-applications` | 8481 | `fingerprint` | list | `if scope:` | **fail closed** |
| 5 | `GET /api/clearance-applications/<id>` | 8524 | `fingerprint` | record | via #1 | inherits |
| 6 | `GET /api/crime-cases` | 8544 | `crime` | list | `if case_scope:` | **fail closed** |
| 7 | `GET /api/crime-cases/<id>` | 8563 | `crime` | record | via #1 | inherits |
| 8 | `GET /api/crimes` | 8837 | **`police_station`** ⚠ | list | `if crime_scope:` | **fail closed + S-15 unit fix** |
| 9 | `POST /api/clearance-applications` | 4533 | `fingerprint` | write | via #2 | inherits |
| 10 | `POST /api/airport-records` | 9214–9215 | `airport` | write | via #2 | inherits |
| 11 | `POST /api/checkpoint-events` | 9510–9511 | `checkpoint` | write | via #2 | inherits |
| 12 | Dashboard aggregates | 7580 | derived | aggregate | `branch_scope_view(...)` | **fail closed** |
| 13 | `posting_scope_status` | 2697 | derived | display | reports `resolved` | keep; surface the state |
| 14 | `/api/me`, admin user payloads | 4280, 8410, 8964, 9028, 9837 | derived | display | informational | **do not** raise — display only |

Sites 13–14 are deliberately excluded from the fail-closed rule: they *report* scope rather than
enforce it. Making `/api/me` throw would lock a misconfigured user out of the page that explains
why. They must surface `state` so the UI can say "your posting does not resolve".

**Write paths #9–#11 are the ones probe P4 exercised** — the unresolved officer filed into another
branch through #9.

### 1.4 Rollout

A fail-closed switch locks out every account whose posting does not currently resolve — and the
probe shows those accounts **work today**, so flipping it blind converts a silent leak into a silent
outage.

| Phase | Action | Exit criterion |
|---|---|---|
| **A** | Ship `branch_scope_state()`; **no behaviour change**. Log every `SCOPE_INDETERMINATE` with user, role, posting, endpoint | Deployed, logging |
| **B** | Report-only. Review the log; administrators correct `users.branch` (PRE-4) | Log empty across a full operating cycle |
| **C** | Enforce — flip the raise on | Tests in §5 pass |

Phase B cannot be skipped and cannot be time-boxed below one full operating cycle.

### 1.5 Root cause — recorded, not proposed for P0

`users.branch` is **free text** (`branch TEXT NOT NULL`), fuzzy-matched by string similarity
(`_branch_match_score`, accept ≥ 45). **Authorization must not depend on string similarity.** The
durable fix is `users.branch_id INTEGER REFERENCES police_branches(id)`, text kept for display only.
That is a schema change plus backfill — **not P0**, recorded as the intended direction so the P0 fix
is understood as a stopgap.

---

## 2. S-15 — remediation

### 2.1 The mismatch

| | Unit type | Branch ids |
|---|---|---|
| **Write** — `register_crime()` `server.py:5288` | `resolve_branch(c, …, 'crime')` | `2, 7, 12` |
| **Read** — `GET /api/crimes` `server.py:8837` | `user_branch_scope(c, user, 'police_station')` | `5, 10, 15` |

Measured on one CID session (probe P5): `/api/crime-cases` → `branch_id=2`; `/api/crimes` →
`branch_id=5`. **Disjoint by construction**, so `WHERE ci.branch_id = 5` can never match.

### 2.2 Consistent branch ownership

`crime_incidents.branch_id` is a **`crime`** branch. Every path must agree:

| Operation | Endpoint | Today | After |
|---|---|---|---|
| Create | `POST /api/crimes` → `register_crime()` | `'crime'` ✔ | unchanged; add `require_branch_write_scope(…, 'crime')` |
| List | `GET /api/crimes` | `'police_station'` ✘ | **`'crime'`** |
| Retrieve by id | *(no single-record route today)* | — | if added, `require_record_branch_scope(…, 'crime', …)` |
| Update | *(no update route today)* | — | if added, `'crime'` |
| Analytics | `GROUP BY station_id` `server.py:7281` | station-based | unchanged — station grouping is the report's purpose, not an authorization boundary |

Verified: `/api/crimes` is the only crimes route; there is no `GET /api/crimes/<id>`, no PATCH and
no DELETE. The "retrieval and update" rows are forward constraints, not existing defects.

**The create path currently has no branch write guard at all** — `register_crime()` calls
`resolve_branch(...)` but never `require_branch_write_scope(...)`, unlike checkpoint
(`server.py:9511`) and airport (`9215`). So a CID officer can file an incident into any branch today.
That is part of S-15's fix, not a separate finding.

### 2.3 Demonstrating that removing station branch rows cannot grant unrestricted access

This is the ordering constraint, and it is exactly what makes A-18 dangerous today:

```
Today  (15 branch rows):  scope resolves to a police_station id -> WHERE branch_id=5  -> 0 rows (closed by accident)
A-18   (9 branch rows):   no police_station rows -> scope = None -> NO WHERE CLAUSE   -> ALL rows (open)
Fixed  (S-14 + S-15):     scope resolves to a crime id          -> WHERE branch_id=2  -> own branch only
```

The demonstration is a **test, not an argument** — `test_removing_station_branches_does_not_widen_access`
(§5, T-16): seed with **zero** `police_station` branch rows, log in as a CID officer, assert the
crimes list is **either** correctly scoped **or** 403 — and **never** a full table scan. It must be
run against today's code and **fail** before the fix.

---

## 3. Checkpoint security

### 3.1 Every Checkpoint endpoint

| # | Endpoint | Line | Module gate | Branch scope | Location scope | Verdict |
|---|---|---|---|---|---|---|
| C1 | `GET /api/checkpoint-events` | 8713 | `checkpoints` ✔ | **NONE** ✘ | `checkpoint_scope()` — **fails open** ✘ | defective |
| C2 | `POST /api/checkpoint-events` | 9505 | `checkpoints` ✔ | `require_branch_write_scope(…,'checkpoint')` — inherits S-14 ✘ | `if scope and location != scope` — **fails open** ✘ | defective |
| C3 | `GET /api/persons/<id>` → `checkpoints` | 8458 | **NONE** ✘ | **NONE** ✘ | **NONE** ✘ | **S-16** |
| C4 | `GET /api/persons/<id>/linked-records` | `linked_person_records()` | module ✔ | **NONE** ✘ | `checkpoint_scope_sql()` ✔ | branch missing |
| C5 | `/documents`, `/audit-history` | siblings | module ✔ | **NONE** ✘ | checkpoint filter ✔ | branch missing |

### 3.2 Where authorization is missing

**(a) `checkpoint_scope()` repeats the S-14 conflation — and inverts its own documentation.**

```python
def checkpoint_scope(user):
    """Admins see all locations (None). Checkpoint users see only their own.
       Other unit users see no checkpoint data (empty string)."""
```

Admin → `None`. Unknown → `''`. **Both are falsy**, and both call sites test `if scope:`. So *"other
unit users see no checkpoint data"* is **false** — they see **all** of it. `ROLE_LOCATION_SCOPE`
maps `ROLE_CHECKPOINT_OFFICER: ''` with the comment *"its default scope is empty so the SQL filter
never leaks other locations"* — **the opposite of what the empty string does.**

A checkpoint officer with no `location_scope` therefore sees **every checkpoint event nationally**.
This is finding **H-2b**, now precisely located.

**(b) No branch filtering anywhere in Checkpoint.** `checkpoint_events.branch_id` exists and is
populated on write (C2), but **no read path filters on it** — C1 selects `ce.branch_id` and never
constrains it. Checkpoint is location-scoped only, so two branches sharing a location name are not
isolated from each other.

**(c) Unknown locations are accepted and stored.** C2 normalises an unrecognised location to
`first_token` and stores the row anyway. A row at location `atlantis` is then invisible to every
*scoped* officer and visible to every *unscoped* one — it silently escapes location scoping.

**(d) Substring matching.** The filter includes `ILIKE '%south%'` on two columns. A location named
`Southwest` matches scope `South`. Loose by construction.

### 3.3 Remediation

| # | Change | Addresses |
|---|---|---|
| CP-1 | `checkpoint_scope_state()` returning the same three states as §1.1; `''` → **indeterminate → 403** | (a) |
| CP-2 | Add branch filtering to C1 using `branch_filter(c, user, 'checkpoint')`, alongside location | (b) |
| CP-3 | Reject a location not in `CHECKPOINT_LOCATIONS` at write with 400 | (c) |
| CP-4 | Replace `ILIKE '%scope%'` with exact matching on the normalised `location_code`; keep the legacy OR-clause only for rows predating normalisation | (d) |
| CP-5 | Apply module + branch + location filtering to C3 — covered by S-16 (§4 of this plan) | S-16 |
| CP-6 | Add branch filtering to C4/C5 | (b) |

CP-3 and CP-4 change stored-data matching; both need the Phase-B report-only pass from §1.4 to find
rows that would change visibility.

---

## 4. Station creation safeguards — package SS-1

### 4.1 All four paths that can create a station record

| # | Path | Line | Trigger | Record produced |
|---|---|---|---|---|
| **1** | `register_station()` | 4915 | `POST /api/stations`, SystemAdmin only | **Legitimate** — validated, phone required, `created_by` set, audited |
| **2** | `resolve_station_with_branch()` | 4700 | Any reference to `BR-<id>` | tier hard-coded `'District HQ'`, `'Active'`, **no phone**, `created_by NULL`, notes `'Mirrored from branch N (auto)'` |
| **3** | `resolve_station_with_branch()` | 4724 | Same, legacy numeric id | as #2, notes `'… (auto numeric)'` |
| **4** | `POST /api/branches` with `unit_type='police_station'` | 9145 | Creating a Police Stations branch | as #2 but `created_by` set; wrapped in `except Exception: pass` — **fails silently** |

Paths 2 and 3 are reachable from `register_officer()` (`server.py:4181`), `register_crime()`
(`5293`) and the vehicle register. **So recording a crime can create the station it is filed
against** — and that station's code is then embedded permanently in the case file number
`CRM-<year>-<code>-NNNN`.

### 4.2 Preventing Crime Unit operations from creating HQ-owned stations

**Principle: reading a station is a CID operation; creating one is not.** Resolution and creation
must be different functions.

```python
def resolve_station_readonly(c, station_code):
    """Resolve to an existing station. NEVER creates. Returns None if absent."""
```

`register_crime()` calls `resolve_station_readonly()`. Station creation stays on path 1 only.

### 4.3 Package SS-1 — G-a … G-d

Presented as a **separate implementation package**, as requested. It touches `register_crime()`, so
it is **not** part of A-18.

| ID | Guard | Change | Effect |
|---|---|---|---|
| **G-a** | Reject provisional stations at crime intake | In `register_crime()`: refuse a station with `contact_phone IS NULL` or `created_by IS NULL` | Blocks all of paths 2–4. `contact_phone` is mandatory on path 1 and absent on 2–4, so it is a reliable discriminator |
| **G-b** | No station creation as a side effect | `register_crime()` uses `resolve_station_readonly()` | Removes the crime→station creation path entirely |
| **G-c** | Require an active station | Refuse `operational_status != 'Active'` | No filing against closed stations |
| **G-d** | Confirm codes before first use (PRE-5) | Procedural | A guard cannot repair a code already embedded in issued file numbers |

**G-a also rejects the eight legacy seeded stations** — correctly: they have no `contact_phone`
either, and they are not authoritative records.

**Effort: 1–2 days.** No schema change. Independently revertible.

> **Decision needed.** G-b changes behaviour an operator may rely on: posting an officer or filing a
> crime against a `BR-<id>` branch currently "just works". After G-b it returns an error until HQ
> registers the station properly. **That is the intent**, but it is an operational change, not only
> a security fix. It needs your approval, not just mine.

---

## 5. Test strategy

### 5.1 Standards

- **Every test asserts a concrete value** — a status code, a record id, a row count. No
  `assertTrue(response)`, no "did not raise".
- **Every test runs against unmodified code first and must fail there.** A test never seen to fail
  proves nothing.
- **No skips in the final suite.** The existing `test_document_branch_authorization.py` pattern
  (4 skips gated on M-01) is **not** acceptable here: these fixes are being implemented, so their
  tests must execute. If a test cannot run, the package is not done.
- **Authorized and unauthorized behaviour are both asserted**, in pairs, in the same database and
  the same run — the pairing is what makes the result evidence rather than an observation.

### 5.2 Coverage against your ten requirements

| # | Your requirement | Test | Asserts |
|---|---|---|---|
| 1 | **Valid branch access** | **T-01** `test_resolved_officer_sees_own_branch` | 200; exactly the own-branch ids; count > 0 |
| 1 | | **T-02** `test_resolved_officer_can_write_own_branch` | 201; record lands in own branch |
| 2 | **Unresolved branch access** | **T-03** `test_unresolved_posting_list_is_refused` | **403** (today: 200 + 3 records) |
| 2 | | **T-04** `test_unresolved_posting_write_is_refused` | **403** (today: 201 into branch 11) |
| 3 | **Missing branch assignment** | **T-05** `test_empty_posting_is_refused` | `branch=''` → **403** |
| 3 | | **T-06** `test_null_unit_type_is_refused` | session with no resolvable unit → **403** (the §1.1 second path) |
| 4 | **Invalid branch mapping** | **T-07** `test_unknown_branch_name_is_refused` | `branch='Zzz Nowhere'` → **403** |
| 4 | | **T-08** `test_ambiguous_posting_is_refused` | two equal-scoring branches → **403**, not open |
| 4 | | **T-09** `test_below_threshold_match_is_refused` | score < 45 → **403** |
| 5 | **Cross-branch reads** | **T-10** `test_list_excludes_other_branches` | foreign ids absent; own present |
| 6 | **Cross-branch access by id** | **T-11** `test_foreign_record_by_id_is_403` | **403** for a scoped officer |
| 6 | | **T-12** `test_foreign_record_by_id_is_403_when_unresolved` | **403** (today: 200 — probe P3) |
| 7 | **Cross-branch writes** | **T-13** `test_cross_branch_write_is_403` | **403**; row count unchanged |
| 8 | **Administrator unrestricted** | **T-14** `test_admin_sees_all_branches` | 200; ids from **both** branches |
| 8 | | **T-15** `test_admin_is_not_locked_out_by_the_fix` | **negative control** — privilege must not be confused with ignorance |
| 9 | **Crime branch consistency** | **T-16** `test_removing_station_branches_does_not_widen_access` | zero `police_station` rows → scoped or 403, **never** all rows |
| 9 | | **T-17** `test_crimes_list_uses_crime_branch` | posted CID officer sees own incidents — **count > 0** (today: 0) |
| 9 | | **T-18** `test_crime_create_is_branch_scoped` | cross-branch filing → 403 |
| 10 | **Checkpoint branch + location** | **T-19** `test_checkpoint_officer_sees_own_location_only` | own location only |
| 10 | | **T-20** `test_checkpoint_empty_scope_is_refused` | `location_scope=''` → **403** (today: all events) |
| 10 | | **T-21** `test_checkpoint_cross_location_write_is_403` | 403 |
| 10 | | **T-22** `test_checkpoint_unknown_location_is_rejected` | location `atlantis` → **400** |
| 10 | | **T-23** `test_checkpoint_is_branch_scoped` | two branches, one location → isolated |
| — | **S-16** | **T-24** `test_person_detail_respects_module_gating` | `cp.south` → `clearance` section **absent/empty** (today: 1 record) |
| — | | **T-25** `test_person_detail_respects_branch_scope` | scoped FP officer → foreign application absent (today: present — probe Q4) |
| — | | **T-26** `test_person_detail_respects_checkpoint_location` | own-location events only |
| — | | **T-27** `test_person_detail_still_returns_identity_fields` | **negative control** — the fix must not break the registry |
| — | **Station safeguards** | **T-28** `test_crime_rejects_auto_mirrored_station` | 400 |
| — | | **T-29** `test_crime_does_not_create_a_station` | `police_stations` count unchanged |
| — | | **T-30** `test_crime_rejects_inactive_station` | 400 |
| — | | **T-31** `test_crime_accepts_registered_station` | **negative control** — 201 |
| — | | **T-32** `test_file_number_uses_registered_code` | prefix `CRM-<year>-<code>-` |

**32 tests.** T-15, T-27 and T-31 are negative controls whose only job is to prove the fix did not
over-correct. T-03/T-04/T-12/T-17/T-20/T-25 are the inversions of probes P2, P4, P3, P5, H-2b and
Q4 — each already observed failing on unmodified code.

### 5.3 Suites

| File | Tests | Status |
|---|---|---|
| `backend/test_branch_scope_enforcement.py` | T-01…T-15 | new |
| `backend/test_crime_branch_consistency.py` | T-16…T-18 | new |
| `backend/test_checkpoint_scope_enforcement.py` | T-19…T-23 | new |
| `backend/test_person_detail_authorization.py` | T-24…T-27 | new |
| `backend/test_station_safeguards.py` | T-28…T-32 | new |

All match the runner's `test_*.py` glob. **Suites 29 → 34.**

---

## 6. Packages, dependencies and blockers

| Pkg | Content | Severity | Effort | Depends on |
|---|---|---|---|---|
| **SEC-1** | **S-16** — module + branch + location filtering on `/api/persons/<id>` and siblings | **Critical** | **2–3 d** | — |
| **SEC-2** | **S-14** — three-state scope, fail closed, 12 call sites, Phase A/B/C | **Critical** | **3–5 d** | SEC-1 (shares the helper) |
| **SEC-3** | **S-15** — `/api/crimes` unit type + crime write guard | **High** | **1–2 d** | SEC-2 |
| **SEC-4** | **Checkpoint** CP-1…CP-6 | **High** | **3–4 d** | SEC-2 |
| **SS-1** | **G-a…G-d** station safeguards | **High** | **1–2 d** | independent |
| **P0-WP-1/2/3** | Existing P0 (N-7, session revocation, initialization) | — | 7–9.5 d | — |
| **A-18** | Production reference data | — | in WP-3 | **SEC-2 + SEC-3** + PRE-3 |

**SEC-1 is sequenced first** because it needs no precondition to exploit, whereas S-14 needs a
broken posting.

### Revised totals

| | Before | **Now** |
|---|---|---|
| Authorization packages | — | **10–16 days** |
| P0 | 7–9.5 d | 7–9.5 d |
| **P0 + authorization** | 7–9.5 d | **17–25.5 days** |

### Release blockers

| ID | Blocks | Cleared by |
|---|---|---|
| **S-16** | Release 1.0 | SEC-1 + T-24…T-27 |
| **S-14** | Release 1.0 | SEC-2 + T-01…T-15 |
| **S-15** | Release 1.0 **and A-18** | SEC-3 + T-16…T-18 |
| H-2b / Checkpoint | Release 1.0 | SEC-4 + T-19…T-23 |
| **PRE-3** authoritative branch list | A-18 | CID deployment authority |

**A-18 remains on hold** (your point 6). No branch rows seeded, no initialization change, until
S-14 and S-15 are resolved **and** the authoritative branch list is confirmed.

---

## 7. Limits and disclosures

- **Nothing implemented.** Both probes were deleted; `server.py` unchanged; suite still
  28 PASS / 0 FAIL / 1 BLOCKED.
- **The 32 tests are specified, not written.** Writing them is implementation.
- **S-16's `airport` / `alerts` / `checkpoints` sections were not separately measured** (§0). Only
  `clearance` was demonstrated. Structurally identical, explicitly not claimed as proven.
- **§1.3 lists 14 sites from a systematic grep of the resolver family.** Sites 3, 4, 5, 9 were
  exercised by probes; the rest are from call-site structure. T-01…T-15 must cover each.
- **Checkpoint findings (a)–(d) are from code reading plus the earlier H-2b evidence**, not from a
  new probe in this run. **T-19…T-23 must run against unmodified code first.**
- **Effort estimates exclude the Phase-B report-only period**, which is bounded by operations, not
  engineering.
- **I rated the checkpoint fail-open as a footnote twice before probing it.** It appeared as "H-2b,
  already on the register" in two prior documents. It is the same defect class as S-14 and should
  have been escalated when S-14 was. Recorded so the pattern is visible.
