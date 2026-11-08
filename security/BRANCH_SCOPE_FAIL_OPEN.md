# S-14 — Branch-scope authorization fails open

**Date:** 5 November 2026 (see §8 on dates) · **Commit:** `bc5483e` · **Severity:** **CRITICAL**
**Status:** **PROVEN BY EXECUTION — RELEASE BLOCKER — NOT FIXED**
**Raised by:** the owner's instruction to investigate unresolved-branch behaviour and treat it as a
release blocker until verified.

> **PARTIALLY SUPERSEDED by `AUTHORIZATION_REMEDIATION_PLAN.md` (revision 2).** The *evidence* in
> §3–§5 stands unchanged and is the record of the probe. Three things below are out of date:
> **(1)** §6.3's rollout proposed a **report-only production phase** — withdrawn; per R-1 there is
> no production database, so enforcement is verified in **staging before production exists**.
> **(2)** §6.6's 3–5 day estimate bundled the shared three-state helper, which is now costed once
> as **SEC-0**; S-14's own call-site work is **2–3 d**.
> **(3)** §5.3 said the person registry was 'not affected' — **wrong**, see **S-16a/S-16b**.

> Nothing implemented. The probe described here was a throwaway read-only harness, run against
> unmodified code and **deleted**. `backend/server.py` is byte-identical to `e7263d7`
> (sha256 `a8211f4f…b3b9fc`).

---

## 1. Answer

> *"Verify whether an officer with an invalid, missing or unmatched branch can access records
> outside their authorized scope."*

**Yes. Confirmed by execution against live code. They can read every branch's records, open any
individual record by id, and file new records into another branch.**

This is not a theoretical weakness inferred from reading code. I built a probe, ran it against a
real PostgreSQL-backed server, and compared a correctly-posted officer against an unresolvable one
in the same database, in the same run.

---

## 2. The defect

Every branch-scoped path follows the same shape:

```python
scope = user_branch_scope(c, user, 'fingerprint')
...
if scope:
    sql += ' WHERE a.branch_id=%s'
```

and the single-record guard (`require_record_branch_scope`, `server.py:2790`):

```python
scope = user_branch_scope(c, user, unit_type)
if not scope:
    return                      # <-- allows the request
```

`user_branch_scope()` returns `None` in two very different situations:

| Situation | Intended meaning | Actual effect |
|---|---|---|
| Admin, records-admin, Chief Commander, read-only | "deliberately unrestricted" | unrestricted ✔ |
| **Posting empty, unknown, misspelled or ambiguous** | **"cannot determine scope"** | **unrestricted ✘** |

**The two are indistinguishable at every call site.** `resolve_posting_branch()` returns `None` when
the posting matches nothing, when it scores below `POSTING_MATCH_MIN = 45`, or when it matches two
branches equally — and each of those becomes "see everything".

The irony is that the code already knows the rule. `require_record_branch_scope`'s own docstring
says:

> *"Rows stored without a branch are treated as out of scope for a scoped officer — 'unknown' must
> never mean 'everything'."*

That principle is applied to the **record's** branch and not to the **officer's**.

---

## 3. Proof by execution

**Method.** Throwaway harness `backend/zz_branch_scope_probe.py`, run against unmodified
`server.py` on an isolated `pgserver` cluster with demo seeding. Two Fingerprint Unit accounts were
created in the same database:

| Account | `users.branch` | Posting resolves? |
|---|---|---|
| `probe.resolved` | `Buuhoodle Branch` (a real branch) | yes → branch id 1 |
| `probe.unresolved` | `Zzz Nowhere Posting` | **no** |

Two clearance applications were seeded, one in branch 1 and one in branch 11. **The resolved account
is the negative control** — it runs in the same database, in the same run, and must be refused where
the unresolved account is allowed.

### Results — all five probes passed

| # | Probe | Result |
|---|---|---|
| **P1** | Resolved officer is scoped | `branch_scope` set; `branch_ids_seen=[1]`; **count = 1** |
| **P2** | **Unresolved officer sees every branch** | `branch_scope=None`; `branch_ids_seen=[1, 11]`; **count = 3** vs 1 |
| **P3** | **Unresolved officer opens an out-of-branch record** | resolved → **403**; unresolved → **200** |
| **P4** | **Unresolved officer files INTO another branch** | resolved → **403**; unresolved → **201**, record `FP-30345718` **landed in branch 11** |
| **P5** | `/api/crimes` scopes on the wrong unit type | same session: `/api/crime-cases` → `branch_id=2`; `/api/crimes` → `branch_id=5` |

**P3 and P4 are the decisive pair.** The same request, in the same database, against the same
record: **403 for a correctly-posted officer, 200/201 for one whose posting does not resolve.** The
control proves the guard works and is being bypassed — not that the endpoint is simply ungated.

P4 is the most serious: the unresolved officer did not merely read another branch's data, they
**created a record inside another branch**, confirmed by reading it back as administrator.

---

## 4. A second, separate defect found by P5

**`/api/crimes` filters on a branch id that `register_crime()` never stores.**

| | Unit type used | Branch ids in play |
|---|---|---|
| **Write** — `register_crime()` `server.py:5288` | `resolve_branch(c, …, 'crime')` | crime branches `2, 7, 12` |
| **Read** — `/api/crimes` list `server.py:8837` | `user_branch_scope(c, user, 'police_station')` | police-station branches `5, 10, 15` |

Measured on one CID session: `/api/crime-cases` reported scope `branch_id=2`, `/api/crimes` reported
`branch_id=5`. **The sets are disjoint by construction**, so `WHERE ci.branch_id = 5` can never match
a record stored with branch 2.

**Today this fails *closed* by accident** — a correctly-posted CID officer sees **zero** crime
incidents. It is a functional bug, not yet a leak.

### ⚠ This interacts with A-18 and changes the recommendation

If the `police_station` branch rows are removed from production initialization — as A-18 proposes —
then `user_branch_scope(c, user, 'police_station')` can **never** resolve, so `scope` is always
`None`, so `/api/crimes` returns **every crime incident to every CID officer**.

> **Implementing A-18 before fixing S-14 would convert an accidental fail-closed into a guaranteed
> total disclosure of the Crime Unit register.**

**A-18 must not be implemented until S-14 is fixed.** This is a hard ordering constraint, recorded
in the decision sheet.

---

## 5. Affected endpoints and modules

### 5.1 Confirmed — branch scoping present and failing open

| Endpoint | Line | Unit type | Module | Exposure when unresolved |
|---|---|---|---|---|
| `GET /api/clearance-applications` | 8481 | `fingerprint` | Fingerprint | **Proven (P2)** — all branches |
| `GET /api/clearance-applications/<id>` | 8524 | `fingerprint` | Fingerprint | **Proven (P3)** — any record |
| `POST /api/clearance-applications` | 4533 / 2742 | `fingerprint` | Fingerprint | **Proven (P4)** — write into any branch |
| `GET /api/airport-records` | 8465 | `airport` | Airport (1.1) | All branches |
| `POST /api/airport-records` | 9214–9215 | `airport` | Airport (1.1) | Write into any branch |
| `GET /api/crime-cases` | 8544 | `crime` | Crime | All branches |
| `GET /api/crime-cases/<id>` | 8563 | `crime` | Crime | Any record |
| `GET /api/crimes` | 8837 | `police_station` ⚠ | Crime | All incidents — **and unconditionally so under A-18** |
| Per-record audit history | 2790 + `AUDIT_ENTITY_*` | all | all | Audit trail of any record |
| Dashboard aggregates | 7580 | derived | all | Figures spanning every branch |

### 5.2 Checkpoint module — a different and worse shape

`checkpoint_events` **has** a `branch_id` column, but **no checkpoint endpoint calls
`user_branch_scope`**. Checkpoint scoping runs off `location_scope` and the hard-coded
`CHECKPOINT_LOCATIONS` constant instead. This is finding **H-2b** already on the register: the live
`cp.south` account carries `branch_scope: None`, `resolved: False`.

So the Checkpoint Unit — a Release 1.0 unit — is **not branch-scoped at all**. Fixing S-14 alone
does not fix Checkpoint; it needs scoping added, not repaired.

### 5.3 Not affected

`officers`, `police_stations`, `vehicles` and `suspect_alerts` carry no `branch_id`
(`suspect_alerts` is finding **S-04**). They are governed by module and role gates only — branch
isolation does not exist for them at all.

> **CORRECTION.** This section originally listed `persons` here as "not affected". **That was
> wrong.** The `persons` *table* has no `branch_id`, but `GET /api/persons/<id>` **attaches four
> unit registers that do** — and filters none of them. That is **S-16a (Critical)**, found one turn
> later while investigating Checkpoint. Listing the table as unaffected without checking what the
> endpoint returned is the same mistake as the `locations` claim: reasoning from schema instead of
> from the response.

---

## 6. Recommended fail-closed design

### 6.1 The core change — distinguish "unrestricted" from "unknown"

Return a three-state result instead of `None`-or-scope:

```python
SCOPE_UNRESTRICTED = 'unrestricted'   # admin / records-admin / Chief / read-only
SCOPE_BRANCH       = 'branch'         # resolved to exactly one branch
SCOPE_INDETERMINATE = 'indeterminate' # empty, unknown, below threshold, or ambiguous

def branch_scope_state(c, user, unit_type=None):
    """(state, scope_dict_or_None). Never conflates privilege with ignorance."""
```

Then at every call site:

```python
state, scope = branch_scope_state(c, user, 'fingerprint')
if state == SCOPE_INDETERMINATE:
    raise BranchScopeError(
        'Your posting does not resolve to a registered branch. '
        'Ask an administrator to correct your posting before using this register.')
if state == SCOPE_BRANCH:
    sql += ' WHERE a.branch_id=%s'; args.append(scope['branch_id'])
```

**Deny, do not silently return nothing.** A scoped officer seeing an empty list cannot tell a
genuinely empty branch from a broken posting; an explicit 403 with that message is both safer and
more usable, and it makes PRE-4 self-enforcing.

### 6.2 Fix the `/api/crimes` unit type

`server.py:8837` must scope on **`'crime'`**, matching what `register_crime()` stores:

```python
crime_scope = user_branch_scope(c, user, 'crime')     # was 'police_station'
```

**This must land in the same change as §6.1.** Fixing the unit type alone leaves the fail-open; fixing
the fail-open alone leaves CID officers seeing zero incidents.

### 6.3 Backfill and rollout

> **SUPERSEDED — see `AUTHORIZATION_REMEDIATION_PLAN.md` §4.** This section originally proposed a
> report-only phase **in production**. That was wrong: it would have deliberately shipped a known
> exploitable path. Per **R-1** there is no production database, so there is nothing to be
> backward-compatible with.

**Replacement:** enforcement is on from the first commit, and compatibility is established in
**staging** (phases R-C/R-D): load representative accounts plus deliberately broken ones, run a
read-only diagnostic that reports which accounts *would* be refused, correct the invalid
assignments (**PRE-4**), then re-run until only the deliberately broken accounts are refused.
**No guard is ever disabled, and nothing reaches production with a known open path.**

### 6.4 Longer term — the root cause

`users.branch` is **free text** (`branch TEXT NOT NULL`) fuzzy-matched by string similarity. A
posting is scored 0–100 against branch names and accepted above 45. **Authorization should not
depend on string similarity.** The durable fix is a real foreign key, `users.branch_id REFERENCES
police_branches(id)`, with the text retained only for display.

That is a schema change with a backfill, so it is **not** proposed for P0. Recorded as the intended
direction so the P0 fix is understood as a stopgap.

### 6.5 Required tests

| Test | Asserts |
|---|---|
| `test_unresolved_posting_is_refused` | Unresolved officer → **403**, not 200 |
| `test_unresolved_posting_cannot_read_foreign_record` | Direct id fetch → 403 (P3 inverted) |
| `test_unresolved_posting_cannot_write_foreign_branch` | Cross-branch POST → 403 (P4 inverted) |
| `test_resolved_officer_still_sees_own_branch` | **Negative control** — the fix must not lock out valid postings |
| `test_admin_remains_unrestricted` | **Negative control** — privilege is not confused with ignorance |
| `test_crimes_list_scopes_on_crime_branch` | A posted CID officer sees their own incidents (non-zero) |
| `test_ambiguous_posting_is_refused` | Two equal matches → 403, not open |
| `test_empty_posting_is_refused` | `branch=''` → 403 |

Each must be run against **unmodified** code first and seen to fail — P1–P5 are exactly those
pre-fix observations, already recorded.

### 6.6 Effort

> **SUPERSEDED — see `AUTHORIZATION_REMEDIATION_PLAN.md` §7.2.** This figure bundled the shared
> three-state helper, which is now **SEC-0** and costed once across all packages.

| Package | Content | New work |
|---|---|---|
| **SEC-0** | Three-state model, shared by every package | 2–3 d |
| **SEC-2** | S-14 — the 12 enforcing call sites only | **2–3 d** |
| SEC-3 | S-15 — `/api/crimes` unit type (was bundled here) | 1–2 d |

Authorization total (SEC-0…SEC-5): **10–16 d**. Total before Release 1.0: **17–25.5 d**.

---

## 7. Register entries

| ID | Title | Severity | Status |
|---|---|---|---|
| **S-14** | Branch-scope authorization fails open when a posting does not resolve | **Critical** | **Open — release blocker.** Proven by execution |
| **S-15** | `/api/crimes` scopes on `police_station` while records store a `crime` branch id | **High** | **Open.** Fails closed today; becomes a total leak if A-18 ships first |

Related: **H-2b** (checkpoint fail-open, §5.2), **S-04** (`suspect_alerts` has no `branch_id`),
**S-05** (analytics RBAC leak).

---

## 8. Limits and disclosures

- **The probe was deleted.** It was investigative tooling, not a deliverable. The permanent tests
  are specified in §6.5 but **not written** — writing them would be implementation.
- **P1–P5 ran against demonstration seeding** (15 branch rows, 8 stations). The fail-open is in the
  scope resolver, which does not depend on the seed.
- **I did not probe every endpoint in §5.1.** Fingerprint read, single-record read and write were
  proven directly; the others are listed from identical call-site structure and are marked as such.
  **Each should be covered by the §6.5 tests rather than assumed.**
- **§5.2 (Checkpoint) was established by code reading and by the earlier H-2b evidence, not by a new
  probe in this run.**
- **I previously described this fail-open only as an aside** — "an unresolvable posting yields *no
  scope* rather than *denied*" in `HQ_PROVISIONING_AND_READINESS.md` §3.2. I noted the shape and did
  not pursue it. It warranted a severity rating and a probe at that point, and it took your
  instruction to get one. Recorded so the omission is visible, not smoothed over.
