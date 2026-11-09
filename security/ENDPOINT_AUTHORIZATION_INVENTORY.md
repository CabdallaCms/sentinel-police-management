> ## 📌 EXTENDED — identifier ceilings moved, 9 November 2026
>
> This document remains authoritative for **E-1…E-26** and **T-01…T-46**. Later work extended both
> sequences; the entries live in `security/SECURITY_REMEDIATION_PROGRAMME.md` and are listed here
> so no identifier is minted twice.
>
> | Range | Where defined | Subject |
> |---|---|---|
> | **E-27…E-36** | Programme §1.1 | Officer/station registers, analytics surfaces, login, logout, password, admin PATCH |
> | **E-37, E-38** | Programme §1.1 | **Do not exist yet** — created by **D-4b**: the withdraw route and the permission grant/revoke path |
> | **T-47…T-56** | Programme §2.8 | S-05 / S-20, incl. four positive controls |
> | **T-57…T-64** | Programme §2.9 | S-08 session expiry |
> | **T-65…T-68** | Programme §2.10 | S-02 admin reset revocation |
> | **T-69…T-77** | Programme §2.11–§2.12 | S-09 throttling and audit; `Secure` cookie |
> | **T-78…T-81** | Programme §2.6 | **A-13 under D-4b** — SystemAdmin refused, cross-branch refused, NULL owner refused, non-status field rejected |
> | **T-82…T-85** | Programme §2.16 | **SS-1 under D-5** — fabricated station refused on both paths, registered station still works |
> | **TLS-1…TLS-10** | `S08_S09_EXECUTION_VERIFICATION.md` §5.2 | TLS acceptance |
>
> **Current ceilings: findings S-20 · endpoints E-38 · tests T-85 · work items W-78.**
> **Grep for the maximum before minting any new identifier.**

---

# Consolidated endpoint authorization inventory

**Date:** 5 November 2026
**Status:** Specification for approval — nothing implemented
**Answers:** owner review point 5
**Scope:** every endpoint that returns or writes unit-owned data, plus the person endpoints

This is the single reference that ties **S-14, S-15, S-16a/b, the checkpoint findings (H-2b) and
suspect-alert ownership (S-04)** to one authorization model and one test id each. It replaces the
12-row matrix in `AUTHORIZATION_REMEDIATION_PLAN.md` §5.2.

---

## 1. How to read this

| Column | Meaning |
|---|---|
| **Module** | Required module permission. `—` = none required **by design** |
| **Branch** | Must the result be constrained to the caller's branch? |
| **Location** | Must it be constrained to the caller's checkpoint location? |
| **Now** | Measured current behaviour. ✔ enforced · ✘ **missing** · `n/a` |
| **Finding** | The register entry this gap belongs to |
| **Tests** | The test that proves denial **and** the test that proves authorized access still works |

Every row's tests assert **both directions**. A row with only a denial test is not accepted as
covered — that is how a fix that blocks everything would pass.

---

## 2. Person endpoints — shared identity vs protected unit records

The boundary you set in review point 5. `persons` holds **no unit data and no branch column**, so
identity is shared and only the **attached arrays** are filtered.

| # | Endpoint | Method | Module | Branch | Location | Now | Finding | Tests |
|---|---|---|---|---|---|---|---|---|
| E-1 | `/api/persons?q=` | GET | — *(by design)* | no | no | ✔ correct | — | T-36 (identity stays readable) |
| E-2 | `/api/persons/<id>` — identity fields | GET | — *(by design)* | no | no | ✔ correct | — | T-39 (same object shape, never smaller) |
| E-3 | `/api/persons/<id>` — `clearance[]` | GET | `fingerprint` | **yes** | n/a | ✘ **none** | **S-16a** | T-37 deny · T-40 allow |
| E-4 | `/api/persons/<id>` — `airport[]` | GET | `airport` | **yes** | n/a | ✘ **none** | **S-16a** | T-37 deny · T-40 allow |
| E-5 | `/api/persons/<id>` — `alerts[]` | GET | `cid` | **yes** (after M-02) | n/a | ✘ **none** | **S-16a** + **S-04** | T-44 deny · T-46 null-branch |
| E-6 | `/api/persons/<id>` — `checkpoints[]` | GET | `checkpoints` | **yes** | **yes** | ✘ **none** | **S-16a** + **H-2b** | T-38 deny · T-40 allow |
| E-7 | `/api/persons/<id>/linked-records` | GET | per source | **yes** | **yes** | module ✔ · location ✔ · **branch ✘** | **S-16b** *(proven)* | T-41 deny · T-40 allow |
| E-8 | `/api/persons/<id>/documents` | GET | per source | **yes** | **yes** | module ✔ · location ✔ · **branch ✘** | **S-16b** *(code-read)* | T-42 |
| E-9 | `/api/persons/<id>/audit-history` | GET | per source | **yes** | **yes** | module ✔ · location ✔ · **branch ✘** | **S-16b** *(code-read)* | T-43 |

> **E-1 and E-2 are deliberately left open.** Checkpoint officers do not hold the `people` module,
> yet `POST /api/checkpoint-events` calls `ensure_person(...)`. Module-gating identity would break
> intake. **T-39 fails if the fix returns a smaller person object** rather than the same object with
> filtered arrays.

---

## 3. Unit registers — list and direct-ID

| # | Endpoint | Method | Module | Branch | Location | Now | Finding | Tests |
|---|---|---|---|---|---|---|---|---|
| E-10 | `/api/clearance-applications` | GET list | `fingerprint` | **yes** | n/a | ✔ *(when posting resolves)* | **S-14** when unresolved | T-11 deny · T-12 allow |
| E-11 | `/api/clearance-applications/<id>` | GET id | `fingerprint` | **yes** | n/a | ✔ *(when resolves)* | **S-14** | T-13 deny · T-14 allow |
| E-12 | `/api/clearance-applications` | POST | `fingerprint` | **write pin** | n/a | ✘ **unresolved writes allowed** | **S-14** | T-15 deny · T-16 allow |
| E-13 | `/api/airport-records` | GET list | `airport` | **yes** | n/a | ✔ *(when resolves)* | **S-14** | T-17 deny · T-18 allow |
| E-14 | `/api/airport-records` | POST | `airport` | **write pin** | n/a | ✔ pinned (`:9215`) | — | T-19 allow |
| E-15 | `/api/suspect-alerts` | GET list | `cid` | **yes** (after M-02) | n/a | ✘ **no branch filter at all** | **S-04** | T-44 deny · T-45 flag stays national |
| E-16 | `/api/suspect-alerts` | POST | `cid` | **record branch** | n/a | ✘ **no branch recorded** | **S-04** | T-46 null ⇒ refuse |
| E-17 | `/api/suspect-alerts/<id>` | PATCH / withdraw | `cid` | **yes** | n/a | **endpoint does not exist** | **S-03** | *blocked on M-02* |
| E-18 | `/api/crime-cases` | GET list | `cid` | **yes** | n/a | ✔ *(when resolves)* | **S-14** | T-23 deny · T-24 allow |
| E-19 | `/api/crimes` | GET list | `crimes` | **yes** | n/a | ✘ **wrong unit type** (`police_station` vs `crime`) | **S-15** | T-25 deny · T-27 allow |
| E-20 | `/api/crimes` | POST | `crimes` | **write pin** | n/a | ✘ **no write scope check at all** | **S-15** | T-26 zero-station ⇒ never "all" |
| E-21 | `/api/checkpoint-events` | GET list | `checkpoints` | **yes** | **yes** | location ✔ · **branch ✘** | **H-2b** *(proven)* | T-28 deny · T-30 allow |
| E-22 | `/api/checkpoint-events` | POST | `checkpoints` | **write pin** | **yes** | branch ✔ pinned · location fail-open | **H-2b** | T-31 unknown ⇒ 400 · T-32 allow |

**Cross-cutting checkpoint tests:** T-29 (`location_scope=''` must refuse, not match everything),
T-33 (`Southwest` must not match `South` — the `ILIKE '%scope%'` substring defect), T-34/T-35
(negative controls: a correctly-scoped officer still reads and still writes).

---

## 4. Administrative and unrestricted access

| # | Endpoint | Module | Branch | Now | Tests |
|---|---|---|---|---|---|
| E-23 | `/api/admin/users` | `admin` | none — **explicitly unrestricted** | ✔ | T-09 (`UNRESTRICTED` is reached only by an explicit grant) |
| E-24 | `/api/admin/audit` | `admin` | explicitly unrestricted | ✔ | T-09 |
| E-25 | `/api/stations` POST | `admin` (SystemAdmin) | n/a | ✔ | — *(SS-1, separate)* |
| E-26 | Any endpoint, unresolved posting | — | **must refuse** | ✘ **fails open** | **T-10** property test · T-20, T-21, T-22 |

**T-10 is the single most important test in the plan:** a property test asserting that **no**
combination of inputs yields `UNRESTRICTED` unless the account carries an explicit unrestricted
grant. It is what stops S-14 from ever recurring under a new name.

---

## 5. Coverage check — every finding, one owner, no duplication

| Finding | Where it is fixed | Endpoints | Tests | Counted in |
|---|---|---|---|---|
| **S-14** branch fail-open | **SEC-0** model + **SEC-2** call sites | E-10…E-14, E-18, E-26 | T-11…T-22 | SEC-0 2–3 d · SEC-2 2–3 d |
| **S-15** crime unit-type mismatch | **SEC-3** | E-19, E-20 | T-23…T-27 | SEC-3 1–2 d |
| **S-16a** person-detail leak | **SEC-1** | E-3…E-6 | T-36…T-40 | SEC-1 2–3 d |
| **S-16b** linked/doc/audit branch | **SEC-1** | E-7, E-8, E-9 | T-41…T-43 | *same* SEC-1 — **not re-counted** |
| **H-2b** checkpoint scope | **SEC-4** | E-21, E-22, and E-6's location half | T-28…T-35 | SEC-4 2–3 d |
| **S-04** alert ownership | **M-02 Phase A** + SEC-1 read scoping | E-15, E-16 | T-44…T-46 | M-02-A 1–1.5 d · read side inside SEC-1 |
| **S-03** no withdraw path | **M-02** (endpoint does not exist) | E-17 | — | *not in authorization scope* |
| Fabricated stations | **SS-1** | E-25 and the two resolver callers | separate | SS-1 1–2 d, **optional** |

### 5.1 Where the same underlying fix is shared

| Shared mechanism | Used by | Costed in |
|---|---|---|
| Three-state `authorize()` / `enforce()` / `scope_clause()` | S-14, S-15, S-16a/b, H-2b, S-04 | **SEC-0 only** |
| `checkpoint_scope_sql` correction | H-2b (E-21/E-22) **and** S-16b's location half (E-7…E-9) | **SEC-4 only** — SEC-1 consumes it |
| Branch clause on the person arrays | S-16a (E-3…E-6) **and** S-16b (E-7…E-9) | **SEC-1 only** — one filter, nine call sites |

**No endpoint appears in two packages' estimates.** Where a fix serves several findings it is
costed once, in the package that owns the mechanism, and the consuming package records a
dependency instead of a cost.

### 5.2 Ordering forced by this table

E-7 (`/linked-records`) cannot be fully correct until **SEC-4** lands, because its location half
uses the same defective `checkpoint_scope_sql`. E-5/E-15/E-16 cannot be correct until **M-02
Phase A** adds `branch_id`. Hence:

```
SEC-0 ──┬── SEC-2 (S-14) ── SEC-3 (S-15) ──┐
        ├── SEC-4 (H-2b) ──────────────────┤
        │        │                         ├── SEC-5 (staging) ── A-18 (also needs PRE-3)
        │        └──────────┐              │
        └── M-02 Phase A ───┴── SEC-1 ─────┘
                                (S-16a/b + alert reads)

SS-1 — independent, optional, no dependency in either direction
```

**SEC-1 is now the last package, not the first** — it depends on both SEC-4 and M-02 Phase A.
That is a change from revision 2, forced by the measured evidence in §4 of
`S16_REGISTER_VERIFICATION.md`.

---

## 6. Totals

| Package | New work |
|---|---|
| SEC-0 consolidated model | 2–3 d |
| SEC-2 S-14 call sites | 2–3 d |
| SEC-3 S-15 crime consistency | 1–2 d |
| SEC-4 H-2b checkpoint | 2–3 d |
| M-02 Phase A alert `branch_id` | 1–1.5 d |
| SEC-1 person endpoints + alert reads | 2–3 d |
| SEC-5 staging verification | 1–2 d |
| **Authorization total** | **11–17.5 d** |
| P0 (unchanged) | 7–9.5 d |
| **Before Release 1.0** | **18–27 d** |
| SS-1, if approved | +1–2 d |

46 tests across five suites; suite count 29 → 34.

---

## 7. Endpoints deliberately **not** in this inventory

Listed so their absence is a decision, not an oversight:

* `/api/officers`, `/api/conduct`, `/api/vehicles`, `/api/stations` (GET) — HR/HQ registers. No
  branch dimension in the current model; **out of CID Release 1.0 scope**.
* `/api/admin/analytics`, `/api/dashboard` — aggregate counts. **Known leak via aggregates is
  finding S-02 and stays open**; not addressed by SEC-0…SEC-5.
* `/uploads/<path>` — gated behind `require_auth` in Stage 0; per-file ownership is **M-01**, which
  is a separate unapproved proposal.
* `/api/health`, `/api/login`, `/api/me` — no unit data.
