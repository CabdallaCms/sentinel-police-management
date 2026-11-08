# S-15 — execution verification report

**Date:** 5 November 2026 · **Status:** COMPLETE — executed, not inferred
**Scope:** investigation only. No fix implemented.
**Method:** disposable pgserver database, real running server, every authorization
measurement a real HTTP request.

---

## 0. Verdict

| Question | Answer |
|---|---|
| Is the original S-15 finding confirmed? | **CONFIRMED, and the write half is worse than recorded** |
| Is current behaviour safe? | **No.** It fails *closed* for resolvable postings and **wide open** for unresolvable ones |
| Is the proposed correction safe? | **Only if SEC-2 and a write guard ship with or before it.** Alone it is **not** safe |
| New defects found? | **Yes — three** (§5) |
| Recommendation | **Ready for owner decision** (§8) |

---

## 1. Environment and fixtures

| Item | Value |
|---|---|
| Database | Disposable `pgserver` cluster in a temp dir, destroyed at exit |
| Server | Real `backend/server.py`, unmodified (sha256 `a8211f4f…b3b9fc`) |
| Branch register | Seeded by `init_db`: 3 locations × 5 unit types = ids 1–15 |
| Buuhoodle | `crime`=**2**, `police_station`=**5** |
| Erigavo | `crime`=**12**, `police_station`=**15** |
| Stations | Demo seed ST-001(Sanaag), ST-002(Sanaag), ST-003(Sool), ST-004(Sool) — **not modified** |
| Desk officer | `POL-S15-0001` — **seeded by SQL into the disposable DB** (the demo seed creates no officers and crime intake requires one) |

### 1.1 Test accounts

| Account | Role | `users.branch` | Posting state |
|---|---|---|---|
| `s15.buu` | `ROLE_CID` | `Buuhoodle Branch` | valid, resolvable |
| `s15.eri` | `ROLE_CID` | `Erigavo Branch` | valid, resolvable |
| `s15.unres` | `ROLE_CID` | `Zzz Nowhere Posting` | **unresolvable** |
| `s15.empty` | `ROLE_CID` | `''` | **missing** |
| `admin` | `ROLE_ADMIN` | `Central HQ` | **explicitly unrestricted** |

### 1.2 Code path under test

```python
# GET /api/crimes            server.py:8837
crime_scope = user_branch_scope(c, user, 'police_station')     # <-- unit type
...
if crime_scope:
    crime_sql += ' WHERE ci.branch_id=%s'                      # <-- compared to
    crime_args.append(crime_scope['branch_id'])

# register_crime()           server.py:5288
branch = resolve_branch(c, fields.get('branch_id'), 'crime')   # <-- stored unit type
# ... no require_branch_write_scope() call anywhere in this function
```

**The record stores a `crime` branch id. The reader's scope resolves a `police_station` branch
id. The two are compared directly.** They are disjoint sets, so the comparison can only ever
match by coincidence.

---

## 2. Scenario A — branch mismatch

**Record:** `CRM-2026-SAN-C-01-0001`, `ci.branch_id=2` (Buuhoodle **crime**), station ST-001
(Sanaag). Created `POST /api/crimes` as `admin` → **201**.

| Account | Posting | Method/endpoint | HTTP | `branch_scope` returned | Items | Sees record? | Expected | Actual |
|---|---|---|---|---|---|---|---|---|
| `s15.buu` | Buuhoodle | GET `/api/crimes` | 200 | `id=5 police_station` | **0** | **False** | should see own branch's record | **does not** |
| `s15.eri` | Erigavo | GET `/api/crimes` | 200 | `id=15 police_station` | **0** | False | should not see | correct, by accident |
| `s15.unres` | unresolvable | GET `/api/crimes` | 200 | **`None` — no WHERE clause** | **1** | **True** | should be refused | **sees everything** |
| `s15.empty` | missing | GET `/api/crimes` | 200 | **`None` — no WHERE clause** | **1** | **True** | should be refused | **sees everything** |
| `admin` | unrestricted | GET `/api/crimes` | 200 | `None` (by design) | 1 | True | sees all | correct |

**Result: CONFIRMED.** A correctly posted CID officer sees **zero** incidents — including the one
filed for their own branch. The scope (`police_station` id 5) can never equal the stored value
(`crime` id 2).

---

## 3. Scenario B — branch scope enforcement

Total incidents in database: **1**.

| Account | Posting state | Scope | Rows returned | Verdict |
|---|---|---|---|---|
| `s15.buu` | valid, resolvable | `5` | 0 of 1 | SCOPED |
| `s15.eri` | valid, resolvable | `15` | 0 of 1 | SCOPED |
| `s15.unres` | **unresolvable** | `None` | **1 of 1** | **UNRESTRICTED — sees ALL** |
| `s15.empty` | **missing** | `None` | **1 of 1** | **UNRESTRICTED — sees ALL** |
| `admin` | explicitly unrestricted | `None` | 1 of 1 | intended |

> ### Can unresolved scope become unrestricted access?
> **Yes. Measured, on this endpoint.** `s15.unres`, `s15.empty` and `admin` are **indistinguishable
> in both the scope value (`None`) and the result set**. `branch_scope_view()` (`:2661`) returns
> `None` for "privileged" and for "could not resolve", and `/api/crimes` reads `if crime_scope:`.
> An officer with a typo in their posting receives **administrator-equivalent visibility** of the
> national crime register.

**Note:** `/api/me` returned no `posting_scope` key for any account, so the UI is not told the
posting failed to resolve on this path. Recorded as an observation, not a finding — the
`posting_scope_status()` helper exists but is not surfaced in this payload.

---

## 4. Scenario C — write authorization

All requests `POST /api/crimes` (JSON) with a valid station and desk officer.

| Actor | Scope | `branch_id` sent | HTTP | Stored `ci.branch_id` | Expected | Actual |
|---|---|---|---|---|---|---|
| `s15.buu` | Buuhoodle (5) | **12 = Erigavo crime** | **201** | **12** | refuse (403) | **ACCEPTED — cross-branch write** |
| `s15.buu` | Buuhoodle (5) | 2 = Buuhoodle crime | 201 | 2 | allow | allow ✔ |
| `s15.buu` | Buuhoodle (5) | **omitted** | **201** | **NULL** | pin to own branch | **NO BRANCH RECORDED** |
| `s15.unres` | none | 12 = Erigavo crime | **201** | 12 | refuse | **ACCEPTED** |

Cross-region stations (officer posted to Buuhoodle / East Togdheer):

| Station | Region | HTTP | File number |
|---|---|---|---|
| ST-001 | Sanaag | **201** | `CRM-2026-SAN-C-01-0006` |
| ST-002 | Sanaag | **201** | `CRM-2026-SAN-C-02-0001` |
| ST-003 | Sool | **201** | `CRM-2026-SOO-C-03-0001` |

**Result: the server enforces nothing on write.** There is no `require_branch_write_scope()` call
in `register_crime()` — unlike airport (`:9215`) and checkpoint (`:9511`), which both pin the
branch. Any CID officer can file an incident under **any** branch, under **no** branch, and
against a station in **any** region. **This is server-side, not a frontend gap** — these requests
bypassed the SPA entirely.

---

## 5. New defects discovered

| # | Defect | Evidence | Severity |
|---|---|---|---|
| **S-17** | **`crime_incidents.branch_id` accepts NULL from the API.** Omitting `branch_id` stores NULL (`resolve_branch` returns `None` when `required=False`, and `register_crime` does not pass `required=True`). A NULL-branch incident is invisible to **every** scoped officer and visible to **every** unscoped one. It can never be brought back into scope. | §4 row 3 | **High** |
| **S-18** | **Cross-branch and cross-region crime filing is accepted from a scoped account.** Known in outline; now measured end-to-end including the stored value. | §4 rows 1, 4 | **High** |
| **S-19** | **File numbers encode the station, not the branch.** `CRM-2026-SAN-C-01-0006` was filed by a Buuhoodle-posted officer against a Sanaag station. The permanent file number asserts a region the filing officer has no posting in. | §4 cross-region table | **Medium** |

S-17 and S-18 are both inside the S-15 defect class and are remediated by the same SEC-3 + SEC-0
work; they are **not** separate estimates. S-19 is an integrity/record-keeping issue that
overlaps SS-1 and needs an owner view, not a code fix on its own.

---

## 6. Scenario D — station-removal (A-18 simulation)

Deleted the **3** `police_station` branch rows **in the disposable database only**.

| Account | Scope BEFORE | Rows BEFORE | Scope AFTER | Rows AFTER | Effect |
|---|---|---|---|---|---|
| `s15.buu` | `5` | **0** | **`None`** | **8** | **WIDENED — now sees ALL** |
| `s15.eri` | `15` | **0** | **`None`** | **8** | **WIDENED — now sees ALL** |
| `s15.unres` | `None` | 8 | `None` | 8 | unchanged (already unrestricted) |
| `s15.empty` | `None` | 8 | `None` | 8 | unchanged (already unrestricted) |

Cross-branch write after removal: `s15.buu` → Erigavo crime branch 12 → **201**.

> ### A-18 blocker — proven
> **Removing the `police_station` branch rows converts every posted CID officer from seeing
> *nothing* to seeing *every crime incident in the country*.** `user_branch_scope(user,
> 'police_station')` can no longer resolve, returns `None`, and the `WHERE` clause disappears.
>
> This is the exact failure predicted when A-18 was put on hold. **It is now measured, not
> inferred. A-18 must not proceed before SEC-2 and SEC-3.**

---

## 7. Scenario E — negative controls and direct access

### 7.1 Direct record endpoints

| Endpoint | Account | HTTP | Result |
|---|---|---|---|
| `GET /api/crimes/1` | `s15.eri`, `s15.unres`, `admin` | **404** | Not found — for all three |
| `GET /api/crimes/CRM-2026-SAN-C-01-0001` | `s15.eri`, `s15.unres`, `admin` | **404** | Not found — for all three |

**There is no direct-ID endpoint for crime incidents.** The route matches `p.path == '/api/crimes'`
exactly (`:8835`), so no single-record path exists. **Unlike S-16a, there is no direct-ID bypass
here** — the list is the only read surface. This narrows the exposure and is reported as a
*negative* result: I looked for a second leak and did not find one.

### 7.2 Does the filter work at all when the ids align?

Restored a `police_station` branch for Buuhoodle (id **16**) and set the probe incident's
`ci.branch_id=16` so scope and record agree. Database then held **9** incidents.

| Account | Scope | Rows | Sees probe incident |
|---|---|---|---|
| `s15.buu` | **16** | **1 of 9** | **True** |
| `admin` | `None` | 9 | True |

**The `WHERE ci.branch_id=%s` clause is correct.** With aligned ids, `s15.buu` received exactly
**1 of 9** records — the right one — and **8 were correctly excluded**. The defect is *solely*
which `unit_type` the scope is resolved from.

> **Control caveat, disclosed:** the `s15.eri` row of this control is **confounded** and I have
> excluded it. Only Buuhoodle's `police_station` branch was restored, so Erigavo's posting no
> longer resolved and that account was unscoped (scope `None`, 9 rows). It therefore proves
> nothing about exclusion. The `s15.buu` result above is unaffected and carries the conclusion.

---

## 8. Is the proposed correction safe?

The proposed SEC-3 correction is to resolve the read scope from `'crime'` instead of
`'police_station'`.

| Question | Finding |
|---|---|
| Does it fix the mismatch? | **Yes.** `s15.buu` would resolve crime branch 2 and match the stored value |
| Does it introduce cross-branch exposure? | **Not by itself.** The `WHERE` clause is proven correct (§7.2); changing which id feeds it does not widen anything |
| **Is it safe alone?** | **NO** — for three measured reasons |

1. **Unresolved postings still see everything.** The correction does not touch
   `branch_scope_view()`. `s15.unres` and `s15.empty` would remain administrator-equivalent.
   **SEC-3 must not ship before SEC-2.**
2. **Writes remain unrestricted.** Without a write guard, an officer can file under another
   branch and then — once reads are correctly scoped — **lose sight of the record they just
   created**. The read fix makes the write hole more confusing, not less.
3. **NULL-branch records (S-17) become permanently orphaned.** They match no scoped query and
   remain visible only to unscoped sessions. The correction must be paired with
   `required=True` on intake plus a backfill decision for any NULL rows.

**It is also a visibility *increase* for correctly posted officers** — from zero to their own
branch. That is the intent, but it is a behaviour change that must be verified in staging
(R-C/R-D), not assumed.

---

## 9. Evidence classification

| Claim | Execution-tested | Inferred from code |
|---|---|---|
| Scope resolves `police_station`, record stores `crime` | ✔ (ids 5 vs 2 observed) | — |
| Posted officers see zero incidents | ✔ | — |
| Unresolved posting ⇒ unrestricted read | ✔ | — |
| Missing posting ⇒ unrestricted read | ✔ | — |
| Cross-branch write accepted | ✔ (stored value read back) | — |
| NULL branch accepted and stored | ✔ | — |
| Cross-region station accepted | ✔ | — |
| No direct-ID endpoint | ✔ (404 ×6) | — |
| `WHERE` clause correct when ids align | ✔ (1 of 9) | — |
| Station removal widens visibility | ✔ (0 → 8) | — |
| `register_crime` has no write-scope call | — | code read (`:5287–5345`), consistent with ✔ above |

**Nothing in this report is described as passing because the code looks correct.**

---

## 10. Remaining risks and dependencies

| Item | Status |
|---|---|
| **SEC-2 (S-14)** | **Hard dependency.** SEC-3 alone leaves unresolved postings unrestricted |
| **SEC-0** | Supplies the three-state model that makes `INDETERMINATE` ≠ unrestricted |
| **Write guard** | Must land with SEC-3, not after |
| **S-17 NULL rows** | Needs `required=True` + a decision on existing NULL rows |
| **A-18** | **Blocked — proven.** Must follow SEC-2 and SEC-3 |
| **S-19 file numbers** | Owner view needed; overlaps SS-1 |
| Estimate impact | **None.** S-17/S-18 are inside SEC-3's existing 1–2 d; the write guard was already scoped |

---

## 11. Compliance statement

| Requirement | Status |
|---|---|
| Investigation only, fix not implemented | ✔ |
| `server.py` unmodified | ✔ sha256 `a8211f4f…b3b9fc`, verified before and after |
| Schema / migrations / initialization / production config unchanged | ✔ |
| Existing station records unmodified | ✔ all deletions were in the disposable database |
| Disposable test data only | ✔ temp pgserver cluster, destroyed at exit |
| Temporary probes deleted | ✔ `backend/zz_s15_probe.py` and its output removed |
| Working tree clean, commits preserved | ✔ |
| Nothing merged into `main` | ✔ `origin/main` = `a1c2478` |
| `PROJECT_STATUS.md` unchanged, no decisions approved | ✔ |
