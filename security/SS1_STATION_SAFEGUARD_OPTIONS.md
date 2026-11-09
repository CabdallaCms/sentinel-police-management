> ## ✅ D-5 DECIDED — 9 November 2026
>
> **Owner's answer, verbatim: "Crime Unit officers select existing registered police stations.
> They cannot create stations."**
>
> This **mandates guard G-b** — `register_crime()` (`:5294`) and `register_officer()` (`:4828`)
> must resolve an existing registered station or refuse; neither may create one. **SS-1 is
> therefore no longer optional: it is a mandatory package at 1–1.5 d**
> (`security/SECURITY_REMEDIATION_PROGRAMME.md` §4, Wave 5), with tests **T-82…T-85**.
>
> **The decision does not state whether guards G-a and G-c, or the operator remedy message that
> distinguishes option (iii) from option (ii), are also in scope.** That residual is raised as
> **new decision D-5a** (+0.25–0.5 d) and **has not been assumed either way**. The options below
> are preserved exactly as they were put to the owner.
>
> **PRE-5 remains mandatory regardless** — a wrong station code cannot be corrected once stamped
> into a `CRM-<year>-<code>-NNNN` file number.
>
> **Implementation remains unauthorized.**

---

# SS-1 — station creation safeguards: options in full

**Date:** 5 November 2026
**Status:** PROPOSAL — awaiting owner decision. **Nothing implemented.**
**Answers:** owner review point 4
**Separate from:** SEC-0…SEC-5. Not a dependency of any of them, and not a dependency for them.

---

## 1. The defect

A police station is HQ reference data. It is supposed to be created by a System Administrator
through *Register police station*, which validates tier, region, district and a contact phone,
sets `created_by`, and issues a code `STN-<REGION_CODES[region]>-NNN`.

**Three other code paths create station rows with none of that.** They fire automatically, with
no operator intent, when something references a Police Stations *branch* by code.

| # | Path | Line | `created_by` | `contact_phone` | Tier | Validated? |
|---|---|---|---|---|---|---|
| 1 | `register_station()` | 4915 | set | **required** | chosen | **yes — legitimate** |
| 2 | `resolve_station_with_branch()` — `BR-<id>` | 4700 | **NULL** | **NULL** | invented `'District HQ'` | no |
| 3 | `resolve_station_with_branch()` — legacy numeric | 4724 | **NULL** | **NULL** | invented `'District HQ'` | no |
| 4 | `POST /api/branches` with `unit_type='police_station'` | 9145 | set | **NULL** | invented `'District HQ'` | no — and inside `except Exception: pass`, so failure is silent |

### 1.1 Why it matters beyond tidiness

`register_crime()` stamps the station's code into the permanent crime file number:

```
CRM-<year>-<station code>-NNNN
```

So an auto-created station with an invented code produces **official crime file numbers built on a
station that nobody registered, that has no contact phone, and that no administrator approved.**
The file number cannot be changed afterwards — it is the record's identity. Path 4 is worse again:
wrapped in `except Exception: pass`, so if the insert fails the system carries on regardless.

---

## 2. The four guards

| ID | Guard | What it changes |
|---|---|---|
| **G-a** | Refuse to use a station with `contact_phone IS NULL` **or** `created_by IS NULL` at crime intake | Blocks *use* of fabricated rows. Does not stop them being created |
| **G-b** | `register_crime()` / `register_officer()` call a new `resolve_station_readonly()` that **never creates** | Stops the fabrication at source |
| **G-c** | Refuse a station whose `operational_status != 'Active'` | Closes a second, unrelated hole: decommissioned stations currently still accept filings |
| **G-d** | Confirm station codes with HQ before first use (**PRE-5**) | Procedural, not code |

`created_by IS NULL` + `contact_phone IS NULL` is a reliable discriminator: **only** paths 2 and 3
produce that combination. Path 4 sets `created_by`, so G-a catches it on the phone alone.

---

## 3. Affected workflows — measured, both call sites

`resolve_station_with_branch()` has exactly **two** callers. Both use the identical
"look up by `station_id`, else fall back" pattern:

| Workflow | Caller | Line | Today, given an unregistered `BR-<id>` | After G-b |
|---|---|---|---|---|
| **File a crime** | `register_crime()` | 5294 | Station silently created; crime filed; invented code burned into the file number | **Error:** station does not exist |
| **Register an officer** | `register_officer()` | 4828 | Station silently created; officer posted to it | **Error:** assigned station does not exist |

Nothing else in the system calls it. **The blast radius of G-b is these two forms.**

### 3.1 Who is affected in practice

Only an operator who types or selects a **Police Stations branch code** (`BR-<id>`) where a
**station id** (`STN-…`) is expected. A correctly registered station is found by the first lookup
and never reaches the fallback. So:

* units working from the proper station register — **no change whatsoever**;
* anyone relying on the branch-code shortcut — **blocked until an administrator registers the
  station**.

I cannot tell you how many operators are in the second group: there is no production database
(**R-1**) and therefore no usage data. **That is exactly why this is your decision and not mine.**

---

## 4. The three options

### Option (i) — G-a + G-c only. Defer G-b.

| | |
|---|---|
| **Behaviour** | Fabricated stations can still be created, but cannot be *used* for crime intake |
| **Crime filing against `BR-7`** | Fails — station has no phone / no `created_by` |
| **Officer registration against `BR-7`** | **Still succeeds** — G-a is a crime-intake guard; the officer path is untouched |
| **Database** | Junk station rows keep accumulating silently |
| **Effort** | 0.5–1 d |
| **Reversible** | Yes |
| **Residual risk** | **The hole stays open.** Rows are still fabricated; a later code path that forgets the check reopens the exposure. Officer postings still create them |

### Option (ii) — all four guards.

| | |
|---|---|
| **Behaviour** | Fabrication stopped at source; use of any pre-existing junk row also blocked |
| **Crime filing against `BR-7`** | Fails: *"Station \"BR-7\" does not exist"* |
| **Officer registration against `BR-7`** | Fails, same message |
| **Database** | No new fabricated rows |
| **Effort** | 1–2 d |
| **Reversible** | Yes — independent of every SEC package |
| **Residual risk** | **Operator-facing.** The error names a station code but not the remedy. An operator who does not know they need a System Administrator is simply stuck, and the obvious workaround is to invent a station through the proper form — which is worse, because it looks legitimate |

### Option (iii) — all four guards **plus an actionable operator message**. ← recommended

| | |
|---|---|
| **Behaviour** | As (ii), but the error states what is wrong, who fixes it, and how |
| **Message** | *"Station BR-7 is a branch record, not a registered police station. A System Administrator must register it under Stations → Register police station before crimes or officers can be filed against it."* |
| **Effort** | 1–2 d (the message is the cheap part) |
| **Reversible** | Yes |
| **Residual risk** | The administrative step still exists — it has simply been made visible and routable instead of a dead end |

---

## 5. Recommendation

**Option (iii).**

1. **(i) does not close the defect.** It blocks one consumer and leaves the generator running, and
   it leaves the officer-registration path fabricating stations exactly as it does now. Half the
   measured blast radius is untouched.
2. **(ii) and (iii) cost the same.** The difference is a sentence of error text. Given that the
   whole operational objection to G-b is "operators will be blocked and will not know why", refusing
   to spend that sentence makes no sense.
3. **The security argument is strong but it is not mine to weigh.** Fabricating an HQ-owned record
   and stamping its invented code permanently into an official crime file number is a serious
   integrity defect. Against that, G-b converts a currently-working action into a blocking error.
   **That trade is an operational judgement and it is yours.**
4. **There is no production data yet (R-1), so this is the cheapest moment to close it.** Once real
   crime file numbers carry fabricated station codes, they cannot be corrected — the file number is
   the record's identity.

### 5.1 If you prefer not to change the workflow at all

A fourth position is legitimate: **accept the risk for Release 1.0** and apply **G-c only** (refuse
decommissioned stations — no workflow change, nobody is blocked), deferring G-a/G-b to 1.1. I do
not recommend it, but it is coherent, and it is better than (i) dressed up as a fix. If you choose
it, the fabricated-station defect should be recorded as **accepted, with an owner signature**, not
left open in the register as though it were still scheduled.

---

## 6. What this does not touch

* **No schema change.** No migration, no new column, no data deletion.
* **No existing record is altered.** Stations already created stay exactly as they are; this is
  about what happens next.
* **Not coupled to the authorization work.** SS-1 can be approved, deferred or rejected without
  affecting SEC-0…SEC-5, and vice versa.
* **The eight HQ police stations and their cell capacities remain out of CID scope** — unchanged by
  any option here.

**Effort if approved: 1–2 days. Nothing proceeds without your explicit instruction.**
