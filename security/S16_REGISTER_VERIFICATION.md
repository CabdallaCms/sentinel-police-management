# S-16 — execution verification across all four linked registers

**Date:** 5 November 2026
**Status:** COMPLETE — executed, not inferred
**Answers:** owner review point 1 ("you have measured only the clearance register")
**Supersedes:** the "structurally identical, not proven" disclosure in
`AUTHORIZATION_REMEDIATION_PLAN.md` revision 2

---

## 0. What changed as a result of running this

You were right to refuse structural similarity as evidence. Running it changed three
conclusions:

| Before (rev 2) | After (measured) |
|---|---|
| S-16b was "code-read only, High" | **S-16b is PROVEN by execution** on two registers |
| Three registers "asserted structurally identical" | **All four measured**; they are **not** identical — they fail in *three different ways* |
| Checkpoint branch exposure was a code-read inference | **H-2b proven**: an Erigavo checkpoint officer reads a Buuhoodle record from the **owning endpoint itself** |
| `suspect_alerts` framed as "cannot be branch-filtered" | True, but the **consequence is worse than recorded** — its own list endpoint has *no* branch filter, so there is nothing to leak *relative to* |

---

## 1. Method

| Aspect | Choice | Why |
|---|---|---|
| Fixture data | One person + one record in **each** of the four registers, seeded with **direct SQL** into a throwaway pgserver database, with **known** `branch_id` / `location_code` | Gives exact control of the authorization inputs. The multipart intake endpoints derive branch from the poster, which is the very thing under test |
| Authorization measurement | **Every measurement is a real HTTP request** to the running server | Nothing about the decision is inferred from source |
| Control | For each register, the **unit's own list endpoint** is called first | Establishes what authorization is *supposed* to allow for that user. Without it, a leak cannot be distinguished from legitimate access |
| Accounts | 9 accounts + `admin`, each with a **real branch name** so posting resolves | Avoids S-14 unresolved-scope noise contaminating the result |

**Fixture:** person `P-S16B-<tag>`; all four records owned by **Buuhoodle**
(fingerprint `branch_id=1`, crime `2`, checkpoint `3`, airport `4`); checkpoint event at
location `South`. Branch layout confirmed from the live table: 3 locations × 5 unit types,
ids 1–15.

**Reading the tables:** `own list endpoint` = the register's own API; `persons/<id>` =
the person-detail endpoint; `linked-records` = `/api/persons/<id>/linked-records`.
`<--` marks a user who **cannot** see the record on the owning endpoint but **does**
receive it from a person endpoint.

---

## 2. Register 1 — `clearance_applications` (Fingerprint)

```
user         own list endpoint            persons/<id>     linked-records
pr.fp.buu    200 RECORD VISIBLE           200 LEAKS        200 LEAKS
pr.fp.eri    200 filtered out             200 LEAKS        200 LEAKS   <--
pr.ap.buu    401 refused                  200 LEAKS        200 absent  <--
pr.ap.eri    401 refused                  200 LEAKS        200 absent  <--
pr.cid.buu   401 refused                  200 LEAKS        200 absent  <--
pr.cid.eri   401 refused                  200 LEAKS        200 absent  <--
pr.cp.sth    401 refused                  200 LEAKS        200 absent  <--
pr.cp.est    401 refused                  200 LEAKS        200 absent  <--
pr.cp.sth2   401 refused                  200 LEAKS        200 absent  <--
admin        200 RECORD VISIBLE           200 LEAKS        200 LEAKS
```

* **Control is sound.** `pr.fp.buu` (same branch) sees it; `pr.fp.eri` (different branch)
  is **correctly filtered out** of the owning endpoint. Branch authorization *works* here.
* **S-16a:** eight of nine accounts receive the record from `/api/persons/<id>` anyway.
* **S-16b PROVEN:** `pr.fp.eri` is refused the record by the Fingerprint register and
  **still receives it from `/linked-records`** — module matches, branch does not, and
  branch is never checked.

## 3. Register 2 — `airport_passengers` (Airport)

```
pr.fp.buu    401 refused                  200 LEAKS        200 absent  <--
pr.fp.eri    401 refused                  200 LEAKS        200 absent  <--
pr.ap.buu    200 RECORD VISIBLE           200 LEAKS        200 LEAKS
pr.ap.eri    200 filtered out             200 LEAKS        200 LEAKS   <--
pr.cid.buu   401 refused                  200 LEAKS        200 absent  <--
pr.cid.eri   401 refused                  200 LEAKS        200 absent  <--
pr.cp.sth    401 refused                  200 LEAKS        200 absent  <--
pr.cp.est    401 refused                  200 LEAKS        200 absent  <--
pr.cp.sth2   401 refused                  200 LEAKS        200 absent  <--
admin        200 RECORD VISIBLE           200 LEAKS        200 LEAKS
```

Identical shape to Fingerprint. **S-16b PROVEN** a second time: `pr.ap.eri` is filtered out
of `/api/airport-records` and still receives the record from `/linked-records`.

> **Naming note.** Your review called this register `airport_movements`. The table is
> **`airport_passengers`**; `movement` is a *column* on it (`Arrival`/`Departure`). Same
> register, flagging the name so the test plan and the schema agree.

## 4. Register 3 — `suspect_alerts` (CID)

```
pr.fp.buu    401 refused                  200 LEAKS        200 absent  <--
pr.fp.eri    401 refused                  200 LEAKS        200 absent  <--
pr.ap.buu    401 refused                  200 LEAKS        200 absent  <--
pr.ap.eri    401 refused                  200 LEAKS        200 absent  <--
pr.cid.buu   200 RECORD VISIBLE           200 LEAKS        200 LEAKS
pr.cid.eri   200 RECORD VISIBLE           200 LEAKS        200 LEAKS
pr.cp.sth    401 refused                  200 LEAKS        200 absent  <--
pr.cp.est    401 refused                  200 LEAKS        200 absent  <--
admin        200 RECORD VISIBLE           200 LEAKS        200 LEAKS
```

**This register fails differently, and the differential test cannot see it.**

`pr.cid.eri` is an **Erigavo** CID officer reading a **Buuhoodle** alert, and the owning
endpoint returns it — `200 RECORD VISIBLE`. So `/linked-records` is not "leaking relative to"
the owning endpoint; **both are unfiltered**. `GET /api/suspect-alerts` applies a module gate
and nothing else: no branch clause exists anywhere in the route.

**This is S-04, and it is the reason point 2 of your review has to be answered before CID
authorization can be called complete.** See `SUSPECT_ALERT_OWNERSHIP.md`.

## 5. Register 4 — `checkpoint_events` (Checkpoint)

```
pr.fp.buu    401 refused                  200 LEAKS        200 absent  <--
pr.fp.eri    401 refused                  200 LEAKS        200 absent  <--
pr.ap.buu    401 refused                  200 LEAKS        200 absent  <--
pr.ap.eri    401 refused                  200 LEAKS        200 absent  <--
pr.cid.buu   401 refused                  200 LEAKS        200 absent  <--
pr.cid.eri   401 refused                  200 LEAKS        200 absent  <--
pr.cp.sth    200 RECORD VISIBLE           200 LEAKS        200 LEAKS
pr.cp.est    200 filtered out             200 LEAKS        200 absent  <--
pr.cp.sth2   200 RECORD VISIBLE           200 LEAKS        200 LEAKS
admin        200 RECORD VISIBLE           200 LEAKS        200 LEAKS
```

**The decisive row is `pr.cp.sth2`** — added specifically to isolate the branch dimension.
It is a checkpoint officer at location **`South`** (matching the record) but posted to
**Erigavo Branch** (not matching the record's `branch_id=3`, Buuhoodle).

It receives the record from the **owning endpoint**: `200 RECORD VISIBLE`.

Location scope is enforced (`pr.cp.est`, East, is filtered out). **Branch is not enforced at
all.** This proves **H-2b by execution** — previously a code-read inference. Without this row
the checkpoint register would have looked safe, because `pr.cp.est` differs in *both*
location and branch and location alone was enough to filter it.

---

## 6. Consolidated verdict

| Register | Own endpoint: module | Own endpoint: branch | Own endpoint: location | S-16a (`/persons/<id>`) | S-16b (`/linked-records`) |
|---|---|---|---|---|---|
| `clearance_applications` | ✔ enforced | ✔ **enforced** | n/a | ✘ **LEAKS** | ✘ **LEAKS — proven** |
| `airport_passengers` | ✔ enforced | ✔ **enforced** | n/a | ✘ **LEAKS** | ✘ **LEAKS — proven** |
| `suspect_alerts` | ✔ enforced | ✘ **absent (S-04)** | n/a | ✘ **LEAKS** | ✘ unfiltered — same defect as its own endpoint |
| `checkpoint_events` | ✔ enforced | ✘ **absent (H-2b, proven)** | ✔ enforced | ✘ **LEAKS** | location only; **branch absent** |

* **S-16a: 4 of 4 registers leak.** 27 distinct (register, account) combinations where an
  account refused `401` by the owning endpoint receives the record from
  `GET /api/persons/<id>`. Severity **Critical** confirmed, no precondition.
* **S-16b: proven, not inferred.** Demonstrated on Fingerprint and Airport, which are the
  two registers whose own endpoints *do* enforce branch — so the leak is unambiguous.
* The other two registers do not show a *differential* leak only because their own
  endpoints are **also** missing branch enforcement. That is a worse finding, not a better one.

**Consequence for the fix:** adding a branch filter to `/linked-records` alone would make
Fingerprint and Airport correct and leave CID and Checkpoint exactly as exposed as they are
now. SEC-1 must therefore depend on SEC-4 (checkpoint branch) and on the `suspect_alerts`
ownership decision — recorded in the dependency graph.

---

## 7. Limits of this evidence

1. **Fixtures were seeded with SQL, not filed through the intake endpoints.** The
   authorization measurements are all real HTTP, but the records did not pass through
   `POST` validation. A record filed normally could carry a different `branch_id` than the
   one I set — that is S-14/S-15 territory and is covered separately.
2. **One record per register.** Multi-record ordering, pagination and `limit` behaviour were
   not exercised.
3. **`/documents` and `/audit-history` were not measured here.** They share
   `checkpoint_scope_sql` with `/linked-records` and are covered by T-41…T-43; on the
   evidence above I expect them to behave like `/linked-records`, but **I have not run them**
   and they remain code-read only.
4. **`admin` was included as an unrestricted control**, not as a finding. Its `200`s are
   correct behaviour.
5. The probe was a throwaway (`backend/zz_s16b_registers_probe.py`), **deleted after the
   run**. `backend/server.py` sha256 `a8211f4f…b3b9fc`, unmodified throughout.
