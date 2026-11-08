# Suspect alert ownership and authorization — architecture

**Date:** 5 November 2026
**Status:** PROPOSAL — for owner decision. Nothing built.
**Answers:** owner review point 2 (who may view, create, update and withdraw suspect alerts)
**Pairs with:** `SUSPECT_ALERT_LIFECYCLE.md` (M-02 — *states* and *transitions*).
This document is the **authorization and ownership** half. It does not restate the lifecycle.
**Finding:** S-04 (`suspect_alerts` carries no branch)

---

## 1. Three facts that decide the architecture

**1.1 — The register has no branch column, and its own endpoint has no branch filter.**
Measured (`S16_REGISTER_VERIFICATION.md` §4): an **Erigavo** CID officer reads a **Buuhoodle**
alert from `GET /api/suspect-alerts` and receives `200`. There is no branch clause in the route.

**1.2 — `case_id` is nullable, deliberately.** The DDL (`server.py:299`) declares
`case_id INTEGER REFERENCES crime_cases(id)` with no `NOT NULL`, and `init_db` actively
*relaxes* the constraint on older databases (`:3092`). `POST /api/suspect-alerts` supports
"Direct Intelligence Listing" / "Manual Entry" — an alert with **no case at all**.

**1.3 — Alert existence is already consumed nationally, with no CID module.**
`POST /api/checkpoint-events` (`:9597`) runs:

```sql
SELECT 1 FROM suspect_alerts WHERE person_id=%s AND role='Suspect'
  AND alert_status='Active alert' LIMIT 1
```

and sets `screening_result` to `Flagged match`. **The checkpoint officer does not hold the
`cid` module and never sees the alert itself** — the system already distinguishes *that a
person is flagged* from *why*. That is not a workaround to be removed; it is the correct
behaviour, and it is the model to formalise.

---

## 2. The ownership model

### 2.1 An alert is two separable facts

| Fact | Content | Who needs it | Scope |
|---|---|---|---|
| **The flag** | A boolean: this person has an active Suspect alert | Every officer performing a screening — checkpoint, airport, fingerprint intake | **National** |
| **The listing** | Case link, `origin`, `notes`, `role`, listing officer, history | CID investigators working the matter | **Branch-owned** |

**This is the same distinction you endorsed in review point 5** — shared identity versus
protected unit records — applied one level down. A person's *identity* is shared; a person's
*alert status* is shared **as a signal**; the *intelligence behind the alert* is unit data.

A checkpoint in Erigavo must stop a suspect listed in Buuhoodle. If alert existence were
branch-scoped, the alert system would stop working the moment the suspect crossed a regional
boundary — which is precisely when it matters. **Branch-scoping the flag would be a safety
regression, not a security improvement.**

### 2.2 Owning branch

> **An alert is owned by the CID branch that created it — stored explicitly on the row,
> never derived.**

| Candidate | Verdict |
|---|---|
| Derive from `crime_cases.branch_id` via `case_id` | **Rejected.** Fails for standalone alerts (1.2). Also unstable: `crime_cases.branch_id` is `ON DELETE SET NULL`, so deleting a branch silently makes the alert unowned — and under SEC-0 an unowned row is `INDETERMINATE`, so alerts would start disappearing from their own unit's screen |
| Derive from the creating user's branch at read time | **Rejected.** `users.branch` is mutable free text. Transferring an officer would silently re-own every alert they ever filed |
| **Store `branch_id` on `suspect_alerts` at creation** | **Adopted.** Stable, explicit, auditable, independent of case and of staff movement |

The case link stays as *provenance* and remains valuable, but it is **not** the authorization key.

### 2.3 Is a schema change required?

**Yes. This cannot be solved in application code.** There is no column to filter on, and no
stable derivation. The change is exactly the one already specified in `SUSPECT_ALERT_LIFECYCLE.md`
§3 (migration **M-02**):

```sql
ALTER TABLE suspect_alerts
  ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES police_branches(id) ON DELETE SET NULL;
```

It is additive and nullable, so it is safe to apply, but **authorization must treat NULL as
`INDETERMINATE` (refuse), not as "all branches"** — that is the S-14 mistake and SEC-0 exists
to prevent it.

> **R-1 makes the backfill nearly free.** M-02 §3 treats unresolvable rows as a real migration
> problem. Per your R-1 ruling there is **no production database**, so the only rows that exist
> are demo seed data. There is no legacy backfill risk. **This is the cheapest moment this
> change will ever be made** — the cost rises permanently once real alerts exist.

---

## 3. Authorization matrix

`U` = unrestricted administrator · `B` = alert's owning branch · `IND` = unresolved → **refuse**

| Action | Endpoint | Module | Branch rule | Today | After |
|---|---|---|---|---|---|
| **See the flag** (boolean, during screening) | checkpoint / airport / fingerprint intake | none — any authenticated officer performing an intake | **national, unscoped** | works (`:9597`) | **unchanged, deliberately** |
| **View listing content** (list) | `GET /api/suspect-alerts` | `cid` | `U` or `B`; `IND` refuses | **no branch filter** | scoped |
| **View listing content** (on a person) | `GET /api/persons/<id>`, `/linked-records` | `cid` | `U` or `B`; `IND` refuses | **leaks to everyone** (S-16a) | scoped |
| **Create** | `POST /api/suspect-alerts` | `cid` | `branch_id` := creator's resolved CID branch; `IND` refuses creation | no branch recorded | scoped + recorded |
| **Update** (status, notes) | **does not exist** | `cid` | `U` or `B` | — | new, per M-02 |
| **Withdraw** | **does not exist** | `cid` (+ seniority, D-23) | `U` or `B` | — | new, per M-02 |

### 3.1 Update and withdraw are not authorization gaps — they are missing endpoints

I searched every write path. `alert_status` is written **once**, at `INSERT` (`:9497`), always
as `'Active alert'`. The only `UPDATE suspect_alerts` in the codebase is a one-time migration
backfill of `origin` (`:3232`). There is **no PATCH, no PUT, no DELETE and no withdraw route.**

**An alert, once created, is permanent and cannot be cleared, corrected or withdrawn by anyone,
including an administrator.** That is finding **S-03**, it is the subject of the **D-23** legal
brief, and it means your point 2 cannot be fully closed by the authorization work alone:
authorization for update/withdraw is authorization for endpoints that must first be built under
M-02.

**SEC-1 can and will close the *read* side.** The *write* side needs M-02 approved.

### 3.2 Cross-branch access — one decision needed

A CID officer in Erigavo investigating a person listed in Buuhoodle will be refused the listing
content. Three ways to handle it:

| Option | Behaviour | Cost | Risk |
|---|---|---|---|
| **A. Strict branch** | Refuse; officer contacts the owning branch out-of-band | 0 (falls out of SEC-0) | Operationally rigid; may drive workarounds |
| **B. National CID read role** | A named role reads every branch's listings, fully audited | +0.5 d | Needs a role-model addition and an owner ruling on who holds it |
| **C. Flag + request** | Cross-branch officer sees the flag and the owning branch name, but not the content, plus an audited "request access" action | +1–1.5 d | More to build; best operational fit |

**Recommendation: A for Release 1.0, C as a follow-up.** A is the fail-closed default and costs
nothing; C is the right long-term design but should not delay the security fix. **B should not be
chosen by default** — a national read role recreates the current exposure under a nicer name
unless the holder list is tightly controlled.

---

## 4. Effect on the plan

| Item | Change |
|---|---|
| **SEC-1** | Gains the alert read-scoping, but **only after** `branch_id` exists. Dependency added: SEC-1 → M-02 Phase A |
| **M-02** | Promoted from "future proposal" to a **dependency of the authorization work**. Phase A (the additive column + backfill) is now on the Release 1.0 path; the lifecycle/state machine is not |
| **T-44** | Rewritten. It currently *pins the gap*. It becomes: alert content is branch-scoped, the flag remains national (both asserted) |
| **New T-45 / T-46** | T-45: a checkpoint officer with no `cid` module still gets `Flagged match` for an out-of-branch suspect. T-46: `branch_id IS NULL` ⇒ refused, never "all" |
| **Estimate** | M-02 Phase A (column + backfill + write-path recording): **1–1.5 d**. Alert read-scoping is inside SEC-1's existing 2–3 d — **not double-counted** |

**Revised authorization total: 11–17.5 d** (was 10–16 d).

---

## 5. What I need from you

1. **Approve the ownership model** — alert owned by the creating CID branch, stored explicitly.
2. **Confirm the flag stays national.** This is the one place I am deliberately *not*
   restricting access, and it is a safety judgement, not a technical one.
3. **Choose A, B or C** for cross-branch CID access (recommend **A** now, **C** later).
4. **Approve M-02 Phase A** (the `branch_id` column only) as a Release 1.0 dependency. The
   lifecycle state machine stays behind D-23 and is **not** requested here.
5. Note that **update/withdraw remain impossible** until M-02 is built — S-03 stays open.
