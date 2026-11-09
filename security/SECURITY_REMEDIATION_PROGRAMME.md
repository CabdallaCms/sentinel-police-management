# Security Remediation Programme — REVISION 1

**Document date:** 9 November 2026 · **Status:** for owner approval. **Nothing implemented.**
**Companion:** `security/OWNER_DECISION_PACKAGE_R1.md` (the decisions that gate this programme).
**Evidence base:** `S08_S09_EXECUTION_VERIFICATION.md`, `S15_EXECUTION_VERIFICATION.md`,
`S16_REGISTER_VERIFICATION.md`, `BRANCH_SCOPE_FAIL_OPEN.md`, `OWNER_REVIEW_PACKAGE.md` (revision 3).

> **This document plans work. It does not perform it.** No application code, schema, migration or
> production configuration has been changed. The approval gate is §7.

## 0. Repository state — read directly from Git, not typed from memory

| Item | Value |
|---|---|
| Branch | `arena/6303ef2f-sentinel-police-management` |
| HEAD at the time this programme was written | `28e68eea93d7d0268c635326dbf88b4356793c2e` |
| `origin/main` | `a1c2478262776e9f20b4c3ad806eaa86adc27792` — **unchanged** |
| Working tree before this document | clean |
| `backend/server.py` | sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` |
| Test suite | 29 files — **28 PASS · 0 FAIL · 1 BLOCKED** (N-7 / S-07) |

The commit that carries this document is recorded in §8.1 after it exists. **No hash in this
document was typed by hand or predicted.**

---

## 1. How to read this

* **Finding IDs** (`S-xx`, `H-2b`) are never reused or renumbered.
* **Endpoint IDs** `E-1…E-26` are defined in `ENDPOINT_AUTHORIZATION_INVENTORY.md`. This programme
  adds **E-27…E-36** for the surfaces that had no inventory entry.
* **Test IDs** `T-01…T-46` are defined in `AUTHORIZATION_REMEDIATION_PLAN.md` §5.3. This programme
  adds **T-47…T-77** and the infrastructure set **TLS-1…TLS-10**.
* **Work items** `W-01…W-69` are new in this document and exist so the estimate can be audited.
* **Evidence classes:** `[E1]` executed this engagement · `[E2]` executed earlier · `[C]`
  code-reviewed · `[N]` not verified · `[O]` owner ruling.
* **"Mandatory before production"** means Release 1.0 must not go live without it. It is not a
  statement about convenience.

### 1.1 New endpoint inventory entries

| # | Endpoint | Method | Finding | Gate today |
|---|---|---|---|---|
| **E-27** | `/api/officers` | GET list | **S-20** | Outer map only, and the `crimes` bypass skips it. No internal gate |
| **E-28** | `/api/stations` | GET list | **S-05** | Same bypass |
| **E-29** | `/api/stations/analytics` | GET | **S-05** | `require_any_module('stations','crimes')` — `crimes` admits CID |
| **E-30** | `/api/vehicles/analytics` | GET | **S-05** | `require_any_module('cars','policesearch','checkpoints','crimes')` |
| **E-31** | `/api/analytics?module=…` | GET | **S-05** | Not in the module map at all; gating is per-bundle inside the dispatcher |
| **E-32** | `/api/cid/analytics` and `?module=cid` | GET | **S-05** | `?module=cid` has **no route-level gate**; sections filtered inside the builder |
| **E-33** | `/api/login` | POST | **S-09**, **S-11** | None by design; no throttle, no audit, cookie lacks `Secure` |
| **E-34** | `/api/logout` | POST | **S-08** | Revokes only the presented token |
| **E-35** | `/api/me/password` | POST | **S-02** *(control)* | Correctly revokes other sessions |
| **E-36** | `/api/admin/users/<id>` | PATCH | **S-02** | Writes `password_hash`; **never revokes sessions** |

---

## 2. Finding-by-finding remediation specification

Each finding states: **(1)** root cause and affected endpoints · **(2)** required code, database or
infrastructure change · **(3)** dependencies · **(4)** mandatory before production? · **(5)**
negative tests and acceptance criteria · **(6)** effort with assumptions.

---

### 2.1 S-14 — branch authorization fails open `[E2]` · CRITICAL

**(1) Root cause.** `branch_scope_view()` (`server.py:2661`) returns `None` for **two different
conditions** — "this account is privileged and may see everything" and "this account's posting
could not be resolved". Callers treat `None` as "no WHERE clause", so an unresolved posting reads
every branch. **Affected:** E-10…E-14, E-18, E-21, and every caller of `user_branch_scope()`
(`:2728`) — 23 call sites enumerated, 12 of which enforce.

**(2) Required change.** Code only, no schema. Replace the boolean-ish `None` with the SEC-0
three-state result (`UNRESTRICTED` / `GRANTED` / `INDETERMINATE`); migrate all enforcing call sites;
delete every `else: return '', ()` fallback that yields an empty predicate.

**(3) Dependencies.** **SEC-0** must land first — SEC-2 is the application of SEC-0's model.

**(4) Mandatory before production.** **Yes**, and before staging.

**(5) Negative tests / acceptance.** T-11…T-22, and **T-10** — a property test asserting that no
combination of role, branch, posting and location yields `UNRESTRICTED` without an explicit
unrestricted grant. **Acceptance:** an account with a missing, invalid or unresolvable posting
receives `403` on every scoped read and write; a correctly posted officer is unaffected (T-12,
T-14, T-16, T-18 are the positive controls and must stay green).

**(6) Effort: 2–3 d** (SEC-2), on top of SEC-0's 2–3 d. **Assumption:** the 12 enforcing call sites
are the complete set — enumerated in `BRANCH_SCOPE_FAIL_OPEN.md`; if a thirteenth appears, add
0.25 d.

---

### 2.2 S-15, S-17, S-18 — crime register scope and write validation `[E1]` · HIGH

**(1) Root cause.** Three defects in one register:
* **S-15** — `/api/crimes` (E-19, `:8835`) filters on `user_branch_scope(…, 'police_station')` while
  `register_crime()` (`:5287`) stores a **`crime`** branch id. The id sets are disjoint, so the list
  fails *closed* today — and converts to **total disclosure** if A-18 removes the `police_station`
  branch rows first (measured: 0 rows → 8 of 8).
* **S-17** — `register_crime()` calls `resolve_branch(…)` (`:4046`) without `required=True`, so
  `POST /api/crimes` with no `branch_id` returns **201** and stores **NULL**. A NULL-branch incident
  is invisible to every scoped officer and visible to every unscoped one, permanently.
* **S-18** — `register_crime()` has **no `require_branch_write_scope()` call at all** (`:2733`),
  unlike airport (`:9215`) and checkpoint (`:9511`). A Buuhoodle-scoped officer filed under Erigavo
  branch 12 → **201**.

**Affected:** E-19 (`GET /api/crimes`, `:8835`), E-20 (`POST /api/crimes`, `:9684`).

**(2) Required change.** Code only. Correct the unit type on the list; add the write-scope pin; make
the branch mandatory on write. **No migration** — but see §2.2a.

**(2a) Pre-existing NULL rows.** Making the column mandatory going forward does **not** repair rows
already stored with `branch_id IS NULL`. Per R-1 there is no production database, so the expected
count is zero; the package must still *report* the count and fail closed on any row it finds, never
default one to a branch.

**(3) Dependencies.** **SEC-0**, then **SEC-2**. SEC-3 must precede **A-18** — this is the ordering
constraint that prevents A-18 from converting a fail-closed into a disclosure.

**(4) Mandatory before production.** **Yes**, and before staging.

**(5) Negative tests / acceptance.** T-23…T-27. **T-26 is the critical one:** with zero
`police_station` branch rows the scope must resolve to *refuse*, **never** to "all". Plus: `POST`
without `branch_id` → `400`, not `201`; `POST` naming another branch → `403`; a correctly scoped
officer still files successfully (positive control). **Acceptance:** `/api/crime-cases` and
`/api/crimes` return the *same* branch for the same officer.

**(6) Effort: 1–2 d.** S-17 and S-18 are **inside** this range — they are three lines in the same
function. **Assumption:** no `/api/crimes/<id>` route needs building (there is none today; adding
one is out of scope).

---

### 2.3 S-16a and S-16b — person-detail and linked-record exposure `[E2]` · CRITICAL / HIGH

**(1) Root cause.** `GET /api/persons/<id>` composes a person object from four unit registers with
**no branch filter on any of them** (S-16a), and the three attached collection endpoints filter by
module and location but **not branch** (S-16b). Measured: **27 leak combinations across all four
registers.** **Affected:** E-3…E-9 — `/api/persons/<id>` arrays `clearance[]`, `airport[]`,
`alerts[]`, `checkpoints[]`; `/linked-records` (`linked_person_records`, `:5883`); `/documents`
(`person_document_records`, `:5962`); `/audit-history` (`person_audit_history`, `:4451`).

**(2) Required change.** Code only. Apply the SEC-0 scope clause to each attached collection.
**Identity stays shared** — `persons` has no branch column and checkpoint intake calls
`ensure_person()` without the `people` module, so module-gating identity would break intake.

**(3) Dependencies.** **SEC-0**, **SEC-4** (checkpoint scope must be correct before it is applied
here) and **M-02 Phase A** (alerts need an owner before alerts can be scoped). SEC-1 is therefore
**last** in the SEC band.

**(4) Mandatory before production.** **Yes**, and before staging. S-16a is the most directly
exploitable finding in the register: it needs no special posting, only a person id.

**(5) Negative tests / acceptance.** T-36…T-46. **T-39 is the guard against over-correction:** the
person object must keep the **same shape**, with filtered arrays — not a smaller object. T-37, T-38,
T-41, T-42, T-43 are the denials; T-36, T-40 the positives. **Acceptance:** for every one of the 27
measured leak combinations the out-of-branch read returns `403` **and** the in-branch read still
returns the record.

**(6) Effort: 2–3 d** (SEC-1). **Assumption:** the four registers are the complete set of attached
collections — verified by execution against all four.

---

### 2.4 H-2b — checkpoint branch and location scope `[E2]` · HIGH

**(1) Root cause.** Three separate defects, all measured:
* `checkpoint_scope_sql()` (`:6275`) begins `if not scope: return ('', ())` — an empty scope matches
  everything;
* it ends in two `ILIKE '%<scope>%'` comparisons, so **`South` matches `Southwest`**;
* `checkpoint_events` has **no branch filter at all** — a same-location officer of another branch
  read the record (`pr.cp.sth2`, 200);
* writes accept an **unknown location**: `"Atlantis Border Post"` → **201**, stored
  `location_code='atlantis'`.

**Affected:** E-21, E-22, and E-6 via the person detail.

**(2) Required change.** Code only. Exact-match location comparison; add the branch predicate;
validate the location against `CHECKPOINT_LOCATIONS` (`:1649`) on write and reject unknown values
with `400`.

**(3) Dependencies.** **SEC-0**. Must precede **SEC-1**.

**(4) Mandatory before production.** **Yes**, and before staging.

**(5) Negative tests / acceptance.** T-28…T-35. Specifically **T-29** (`location_scope=''` must
refuse, not match everything), **T-31** (unknown location → `400`), **T-33** (`Southwest` must not
match `South`), with **T-34/T-35** as the positive controls. **Acceptance:** no fabricated location
code can be stored, and a same-location officer from another branch is refused.

**(6) Effort: 2–3 d** (SEC-4). **Assumption:** `CHECKPOINT_LOCATIONS` is the authoritative list; if
HQ adds locations the validation is data-driven, not code.

---

### 2.5 S-04 — suspect alerts carry no owner `[E2]` · HIGH

**(1) Root cause.** `suspect_alerts` has no `branch_id` column (DDL `:299`), so alert content is
unscoped: an Erigavo CID officer read a Buuhoodle alert, **200**. **Affected:** E-15 (`GET
/api/suspect-alerts`), E-16 (`POST`), E-5 (`alerts[]` in person detail).

**(2) Required change.** **Database migration M-02 Phase A — additive only:**
`ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES
police_branches(id) ON DELETE SET NULL;` plus an index. Backfill from `crime_cases.branch_id`
where resolvable, otherwise a **worklist — never defaulted**. Record the branch on write; refuse
creation when the creator's branch is unresolved.

**(3) Dependencies.** **SEC-0**; gated by owner decisions **D-1a**, **D-4** and **D-7**. Must
precede **SEC-1**.

**(4) Mandatory before production.** **Yes**, and before staging.

**(5) Negative tests / acceptance.** T-44 (cross-branch content refused), **T-45** (the control — a
checkpoint officer with **no** `cid` module must still receive `Flagged match` for an out-of-branch
suspect; if this fails the fix over-restricted and is a safety regression), **T-46a** (creation
refused when the creator's branch is unresolved) and **T-46b** (`branch_id IS NULL` ⇒ refuse, never
"all"). **T-46 may not be reported green until both halves land.**

**(6) Effort: 1–1.5 d** (M-02 Phase A). **Assumption:** per R-1 the backfill worklist is empty or
near-empty. If a populated database appears, add 0.5–2 d for classification.

---

### 2.6 S-03 — suspect alerts can never be corrected `[C]` · HIGH

**(1) Root cause.** `alert_status` is written once at `INSERT` (`:9499`), always `'Active alert'`.
The only `UPDATE suspect_alerts` in the codebase is a one-time `origin` backfill (`:3232`). **No
PATCH, PUT, DELETE or withdraw route exists** (E-17 is an endpoint that does not exist). A wrongly
listed person is flagged at every checkpoint in the country, indefinitely, and **nobody — including
an administrator — can clear it.**

**(2) Required change.** Build **A-13**: one endpoint that sets a terminal status, requires a
mandatory reason, writes an audit event with the actor, and stops the national flag firing.
**Authorization must be a named permission (e.g. `alerts:withdraw`), not `role == 'SystemAdmin'`** —
see `OWNER_DECISION_PACKAGE_R1.md` §4 for why, and for the controls against unauthorized withdrawal.
No schema change beyond M-02 Phase A.

**(3) Dependencies.** **M-02 Phase A** (an alert must have an owner before a scoped withdrawal is
meaningful); owner decision **D-4b**; **legal decisions D-23.5 and D-23.6** before it is *built*.

**(4) Mandatory before production.** **Yes — at the A-13 minimum.** The full six-state lifecycle is
**not** mandatory and is deferred to 1.1 under D-23.

**(5) Negative tests / acceptance.** A caller without `alerts:withdraw` → `403`. A withdrawal with
no reason → `400`. After withdrawal, `POST /api/checkpoint-events` for that person returns
`No active alert` — **tested through the real endpoint**, because the checkpoint handler reads
`suspect_alerts` directly (`:9597`) and a UI-only suppression would not be detected by anything
else. An audit row exists naming actor, reason and timestamp. A second withdrawal of the same alert
is idempotent or refused, not silently duplicated. **Acceptance:** the flag stops, the record
survives, and who stopped it and why is recoverable.

**(6) Effort: 2–3 d.** **Assumption:** the interim uses the existing permission layer and creates no
supervisor role. Creating a real supervisor rank is **+4–8 d** and touches every module (D-23.1).

---

### 2.7 S-01 — cross-branch document access `[E2]` · HIGH

**(1) Root cause.** Uploaded files are served from a flat `/uploads/` path with no per-file
ownership record. Stage 0 closed **anonymous** access only; any *authenticated* officer can still
read any file, including another branch's. `test_upload_access_control.py::test_07` **returns 200
today**. **Affected:** `/uploads/<path>`, every upload producer (`save_upload_validated`, `:4606`),
and E-8 (`/api/persons/<id>/documents`).

**(2) Required change.** **Migration M-01** — a `documents` table recording owner branch, source
register and uploader for every stored file; backfill from existing rows; then enforcement at the
serving path. This is the **largest single item** in the programme.

**(3) Dependencies.** **SEC-0** (uses the same decision model), **D-7** (migration safety). Can run
in parallel with the SEC band after SEC-0, by a second engineer — it does not block A-18.

**(4) Mandatory before production.** **Yes.** Scoping the registers while leaving the documents open
means the data the registers protect is still reachable one layer down.

**(5) Negative tests / acceptance.** The matrix is **already written**:
`backend/test_document_branch_authorization.py` holds **15 prepared cases** in dual mode — it
measures and reports today's exposure and skips, and switches itself to strict enforcement the
moment the `documents` table exists. Cases include cross-branch denial, cross-branch CID denial,
enumeration revealing nothing, path traversal refused, unindexed file not served, anonymous and
forged-token refusal, and administrator/read-only-commander positives. **Acceptance:** that file
runs in enforcement mode with **zero skips** and all 15 green.

**(6) Effort: 11–18 d.** **Assumptions:** (a) the test matrix exists and only needs activating, so
no authoring cost is included; (b) per R-1 the backfill set is demo data only — a populated
production store would add reconciliation time; (c) a dual-read period is included so rollback does
not strand files.

---

### 2.8 S-05 and S-20 — analytics RBAC and officer-register exposure `[E1]` · HIGH

**(1) Root cause — one line.** The GET module gate contains a bypass at **`server.py:8396–8397`**:

```python
if prefix in ('/api/stations', '/api/officers') and 'crimes' in (user.get('modules') or []):
    break          # skips require_module() entirely
```

It was added so the crime-intake form could populate its station dropdown. It also opens
`/api/officers` (E-27, `:8833`), whose handler is a bare `SELECT` with **no internal gate**.
Measured: `ROLE_CID` — which holds `{dashboard, people, cid, crimes}` and **no `officers` module** —
receives the full officer register including `date_of_birth`, `mother_name`, `place_of_birth`,
`contact_number`, and the **`guarantor_name`, `guarantor_address` and `guarantor_contact` of a
third-party civilian**. Separately, `crimes` appears in the OR-lists of E-29 and E-30, and
**`/api/analytics?module=cid` (E-32) has no route-level gate at all** — reachable by `hr.officer`
(sections came back empty, so this is a gate gap, not a data leak).

**(2) Required change.** Code only. Remove the bypass; give crime intake a **narrow** station read
(the fields the dropdown needs, not the register); add an internal gate to `/api/officers`; gate
`?module=cid` at the route; re-derive the role × bundle matrix for every analytics surface.

**(3) Dependencies.** **None on SEC-0** — this is module gating, not branch scope. It can start as
soon as implementation is authorized, in parallel with SEC-0. **It must not be merged without its
negative controls**, because the crime desk legitimately needs *some* station data.

**(4) Mandatory before production.** **Yes — reclassified 9 Nov 2026 and flagged.** Revision 2
had S-05 as Medium and deferrable; execution showed personal data of officers and of their civilian
guarantors reachable by a role with no HR module. Under the owner's standing instruction this may
not be deferred without an explicit recorded risk acceptance.

**(5) Negative tests / acceptance.**

| Test | Asserts |
|---|---|
| **T-47** | `cid.officer` → `GET /api/officers` is **refused** |
| **T-48** | `cid.officer` → `/api/stations/analytics` refused |
| **T-49** | `cid.officer` → `/api/vehicles/analytics` refused |
| **T-50** | `cid.officer` → `?module=stations` and `?module=vehicles` refused |
| **T-51** | `?module=cid` refused to a role holding no CID-section module |
| **T-52** | `?module=all` returns **only** bundles the caller is entitled to, for all seven roles |
| **T-53** | *(positive control)* crime intake can still populate its station dropdown |
| **T-54** | *(positive control)* `hr.officer` still reads officers, analytics, discipline, promotions, conduct |
| **T-55** | *(positive control)* `/api/admin/*` still refused to every role but `admin`, including `chief` |
| **T-56** | *(positive control)* `cp.south` still reaches `/api/vehicles*` — by design, documented OR-list |

**Acceptance:** the measured 20 × 7 matrix in `S08_S09_EXECUTION_VERIFICATION.md` §2.1 is re-run and
every cell marked as a leak flips to refused, with **no cell that was correctly `200` turning into a
refusal.**

**(6) Effort: 2–4 d for both findings together.** **S-20 adds no days** — same root cause, same
one-line removal. The range is driven by W-54, the role × bundle review, not by the fix.
**Assumption:** the crime desk's legitimate station need can be met with a narrow projection; if it
turns out to need the full register, that is an owner conversation, not a wider gate.

---

### 2.9 S-08 — no session expiry `[E1]` · HIGH

**(1) Root cause.** The `sessions` table (DDL `:446`) holds only `(token, user_id, created_at)` —
**no expiry column**, and `users` carries no lockout or idle-timeout column. `require_auth()`
(`:4256`) resolves a token through the in-memory `TOKENS` map, then
`SELECT user_id FROM sessions WHERE token=%s` — **no time predicate on either path.** Measured: a
session forced to **678 days old** returned `200`, and still returned `200` **after a server
restart** cleared the cache — so it is re-validated from storage and accepted. Five concurrent
sessions for one account all worked; logging one out left four alive; nothing can enumerate them.
**Affected:** E-33, E-34, and every authenticated endpoint.

**(2) Required change.** Code **plus a small additive migration**: an absolute lifetime can be
computed from the existing `created_at` with no DDL, but an **idle** timeout needs a new
`last_seen_at` column. Also: a session-enumeration and revoke-all capability, and the `TOKENS` cache
must honour expiry rather than outliving the database state.

**(3) Dependencies.** **D-7** (because of the column). Independent of SEC-0. Pairs with **S-02** —
do not implement revocation twice.

**(4) Mandatory before production.** **Yes.** A token captured once works forever, which also
defeats the purpose of revoking sessions on password change.

**(5) Negative tests / acceptance.** T-57…T-64: a session older than the absolute lifetime is
refused on the cache path **and** after a restart on the database path; an idle session past the
idle window is refused; a *fresh* session is **not** refused (positive control); concurrent sessions
are enumerable and revoke-all kills every one; logout still kills exactly one. **Acceptance:** the
678-day scenario, re-run, returns `401`.

**(6) Effort: 2–3 d.** **Assumption:** absolute **and** idle expiry are both wanted. Absolute only
would be ~1.5 d and need no migration — that is an engineering option, not an owner decision, and is
flagged so the schedule is not surprised.

---

### 2.10 S-02 — administrator password reset does not revoke sessions `[E1]` · HIGH

**(1) Root cause.** `PATCH /api/admin/users/<id>` (E-36, `:9931`) writes `password_hash` and
**never calls `revoke_user_sessions()`** (`:4224`), which only the self-service branch (`:9053`)
invokes. Measured: after an admin reset the victim's **pre-existing token still returned 200**, the
old password failed, the new one worked, and **three session rows survived**. The operational case
that matters is exactly the one that fails: resetting a *known-compromised* account leaves the
attacker signed in.

**(2) Required change.** Code only. Call `revoke_user_sessions()` on the administrator path; decide
and implement the keep-token semantics (the admin's own session is unaffected; **all** of the
target's sessions die); write an audit event recording how many sessions were revoked.

**(3) Dependencies.** None. **Overlaps S-08** — the revocation helper is shared; cost it once, here.

**(4) Mandatory before production.** **Yes**, and before staging (it sits in P0-WP-2).

**(5) Negative tests / acceptance.** T-65…T-68: after an admin reset the victim's old token →
`401`; the victim's session rows are gone; the **admin's own** session still works (positive
control); the self-service path keeps its existing behaviour (changer stays in, others out — this
already passes and must not regress). **Acceptance:** zero surviving session rows for the target.

**(6) Effort: 1.5–2 d** (P0-WP-2). **Assumption:** the existing `revoke_user_sessions()` is correct —
it is, and the self-service path demonstrates it by execution.

---

### 2.11 S-09 — no login throttling, no authentication audit `[E1]` · HIGH

**(1) Root cause.** `/api/login` (E-33, `:8944`) has no rate limit, no lockout and **no audit call
on either branch**. Measured: 30 consecutive wrong passwords → all `401`, no `429`, a flat 212 ms
each; the **correct password immediately afterwards returned 200**, proving no threshold exists at
any value; a one-guess spray across all nine accounts met no limit; `audit_events` went **4 → 4**
across fifty failed logins and several successful ones. The 212 ms is PBKDF2 — that is *work*, not a
*defence*, and it does nothing against a spray, which never repeats against one account.

**(2) Required change.** Code, plus storage for attempt counters (a table or a column — a design
choice inside the package). Per-account **and** per-source throttling with a lockout threshold; an
authentication audit event for **both** success and failure carrying actor, source and timestamp; an
administrator unlock path so a locked-out officer is not stranded mid-shift.

**(3) Dependencies.** **D-7** if a column or table is added. Independent of SEC-0.

**(4) Mandatory before production.** **Yes.** For a police system the missing audit is an
accountability failure as much as a security one: the system can attribute a *record change* to a
user but cannot establish that the session was legitimately created.

**(5) Negative tests / acceptance.** T-69…T-76: repeated failures hit the threshold and are refused
with a distinct status; the **correct** password **after** the threshold is **still refused** (this
is the test that failed in the measurement); a spray across accounts is throttled per source; a
successful login writes an audit row; a failed login writes an audit row naming the attempted
username and source; **a legitimate officer who has not tripped the threshold logs in normally**
(positive control); the unlock path works and is itself audited.

**(6) Effort: 2–3 d.** **Assumption:** throttling is in-process. A multi-instance deployment needs
shared state (Redis or a database table) — if the deployment is ever load-balanced, add 0.5–1 d.
**This assumption must be checked against the intended production topology before the estimate is
relied on.**

---

### 2.12 S-11 — no TLS; session cookie lacks `Secure` `[E1-partial]` · HIGH

**(1) Root cause.** The application serves plain HTTP and issues
`Set-Cookie: sentinel_session=…; Path=/; HttpOnly; SameSite=Lax` (`:8971`) — **no `Secure`
attribute**. Every credential, token, person record and uploaded document crosses the network in
clear. **Affected:** E-33 and the entire transport.

**(2) Required change.** **Infrastructure plus one application line.** Infrastructure: a terminating
reverse proxy, a certificate with a renewal procedure and an expiry alarm, the application bound to
loopback or a private interface so it cannot be reached without passing the terminator, HTTP→HTTPS
redirection, HSTS once TLS is stable, and a named owner for renewal. Application: add `Secure` to
the cookie — **without it the cookie still travels in clear after termination**, so the
infrastructure work alone does not close the finding.

**(3) Dependencies.** None in code. Blocked only by the existence of a staging environment.

**(4) Mandatory before production.** **Yes, and not negotiable.** Fixing authorization while leaving
transport open means an attacker reads the data without needing authorization at all.

**(5) Negative tests / acceptance.** **TLS-1…TLS-10**, specified in
`S08_S09_EXECUTION_VERIFICATION.md` §5.2: plaintext refused or redirected; HTTPS serves; certificate
validates without `-k`; TLS 1.0/1.1 refused; cookie carries `Secure`; the cookie is **not** sent over
HTTP; HSTS present; `/uploads/` refused over HTTP; a packet capture during login shows no cleartext
credential; no mixed content. Plus **T-77** — a unit assertion that the login response carries
`Secure`, `HttpOnly` and `SameSite`.

**(6) Effort: 2–4 d**, of which **~0.25 d is application work** and the remainder is infrastructure
that does not compete with engineering capacity. **Assumption:** a terminator and certificate can be
provisioned; if a certificate authority or DNS name must be procured, that is owner lead time, not
engineering days.

---

### 2.13 S-07 / N-7 — disciplinary actions cannot be closed `[E2]` · HIGH (operational)

**(1) Root cause.** `update_discipline()` (`:6778`) builds a malformed SQL placeholder list —
`','.join('%s' * n)` produces `'%,s,%,s'` instead of `'%s,%s'`. A suspended officer **can never be
returned to Active duty.** It also blocks `backend/test_server.py`, the one suite that is not
passing.

**(2) Required change.** Code only, a one-line correction plus the regression test.

**(3) Dependencies.** None.

**(4) Mandatory before production.** **Yes** for the HR module. It is a direct human consequence: an
officer stays suspended because of a string bug.

**(5) Negative tests / acceptance.** Close a disciplinary action and verify the officer returns to
Active; verify the audit row; **`backend/test_server.py` must move from BLOCKED to PASS**, taking the
suite to 29 PASS / 0 FAIL / 0 BLOCKED.

**(6) Effort: 1.5 d** (P0-WP-1). **Assumption:** N-7 is the only cause of that suite's blockage —
confirmed unique to `:6828` during Stage 0.

---

### 2.14 S-12, S-13 and the S-06 residual — first production install `[E2]` / `[O]`

**(1) Root cause.** **S-12** — `bootstrap_password_for()` (`:3489`) returns
`SENTINEL_BOOTSTRAP_PASSWORD` **unchanged for every username**, so one variable gives all nine
seeded accounts the same password, with no warning. **S-13** — demo data seeds into a fresh database
by default. **S-06** is discharged on existing data by owner ruling **R-1** (no operational database
has ever existed); its residual is that **no documented production initialization exists**, so the
*next* install is the exposure.

**(2) Required change.** Per-account randomness with a refusal to accept a shared default;
demo seeding off by default (A-16/A-16a); admin-only initialization (A-17); a bootstrap variable
with an explicit warning (A-19); and **A-18** — the nine branch rows, gated on **PRE-3**.

**(3) Dependencies.** **SEC-2, SEC-3, PRE-3**, and the full A-18 prerequisite chain: **SEC-0 · SEC-2
· SEC-3 · SEC-4 · M-02 Phase A · SEC-1 · SEC-5 · PRE-3**.

**(4) Mandatory before production.** **Yes** — by definition, this *is* the production install.

**(5) Negative tests / acceptance.** A fresh initialization produces **no** shared password and
**no** demo records; the bootstrap variable emits a warning; initialization refuses to run as a
non-admin; the first production run yields branches 9 / stations 0 / locations 0 / officers 0 /
users 1. **Acceptance:** `PRODUCTION_INITIALIZATION.md` is executed end to end on a clean database
and the result matches the documented expectation exactly.

**(6) Effort: 2–3 d** (P0-WP-3). **Assumption:** PRE-3 has confirmed the authoritative CID branch
list. `DEFAULT_POLICE_BRANCHES` (`:1660`) has **no provenance and is not approved production data**.

---

### 2.15 S-10 — mutable audit log `[N]` · HIGH, conditional

**(1) Root cause.** Audit rows are ordinary table rows; nothing makes them tamper-evident.

**(2) Required change.** Append-only storage, hash chaining or an external write-once sink — the
design depends entirely on the legal requirement.

**(3) Dependencies.** **Decision D-04 / A-6 — legal.**

**(4) Mandatory before production.** **Conditional.** If alerts, clearances or conduct files are
ever used in a proceeding, **yes**. If not, it may follow 1.0. **This is not an engineering call and
has deliberately not been made.**

**(5) Negative tests / acceptance.** Cannot be specified until the requirement is known. Writing
them now would be inventing a requirement.

**(6) Effort: 5–10 d**, excluded from the mandatory total because the condition is unresolved.
**S-10 was deliberately not probed** — demonstrating it proves a property of PostgreSQL table
permissions, not of the application, and the open question is legal.

---

### 2.16 S-19 — crime file numbers encode the station region `[E1]` · MEDIUM

**(1) Root cause.** `new_crime_file_number()` (`:4734`) builds `CRM-<year>-<station code>-NNNN`. A
Buuhoodle-posted officer produced `CRM-2026-SAN-C-01-0006` — a permanent identifier asserting
Sanaag.

**(2) Required change.** A policy decision first, then possibly code. **Overlaps SS-1** — the same
fabricated-station problem produces invented codes in official file numbers.

**(3) Dependencies.** **D-5**, and **PRE-5** (station codes confirmed by HQ before first use,
because they are permanent once minted).

**(4) Mandatory before production.** **No** — but **PRE-5 is**, because a wrong code cannot be
corrected after it is stamped into a file number.

**(5) Negative tests / acceptance.** Covered by SS-1's tests if D-5 is approved.

**(6) Effort:** not separately costed — it is inside SS-1's 1–2 d.

---

## 3. Estimate reconciled from individual work items

**Method.** Every package is decomposed into work items with independent minimum and maximum days.
The package range is the sum of its items. **No package range was adjusted to match a previous
figure.** Where a decomposition confirms a prior number, that is stated; where it would change one,
that is stated too.

### 3.1 Work items

| ID | Work item | Min | Max | Package | Depends on | Mandatory 1.0 |
|---|---|--:|--:|---|---|:--:|
| W-01 | `AccessDecision` type, three states, `authorize()` | 0.5 | 0.75 | SEC-0 | — | ✔ |
| W-02 | `enforce()` → 403 on `INDETERMINATE` | 0.25 | 0.5 | SEC-0 | W-01 | ✔ |
| W-03 | `scope_clause()` with two branches, no empty-predicate fallback | 0.25 | 0.5 | SEC-0 | W-01 | ✔ |
| W-04 | Explicit unrestricted-grant registry | 0.25 | 0.5 | SEC-0 | W-01 | ✔ |
| W-05 | T-01…T-10 incl. the T-10 property test | 0.75 | 0.75 | SEC-0 | W-01…04 | ✔ |
| W-06 | Migrate 12 enforcing call sites to SEC-0 | 1.0 | 1.5 | SEC-2 | SEC-0 | ✔ |
| W-07 | Remove the `None`-means-two-things ambiguity at `:2661` | 0.25 | 0.5 | SEC-2 | SEC-0 | ✔ |
| W-08 | Write-pin paths through the new model | 0.25 | 0.25 | SEC-2 | W-06 | ✔ |
| W-09 | T-11…T-22 | 0.5 | 0.75 | SEC-2 | W-06…08 | ✔ |
| W-10 | `/api/crimes` unit type `police_station` → `crime` (S-15) | 0.25 | 0.5 | SEC-3 | SEC-2 | ✔ |
| W-11 | `require_branch_write_scope()` in `register_crime()` (S-18) | 0.25 | 0.5 | SEC-3 | SEC-2 | ✔ |
| W-12 | `resolve_branch(..., required=True)` for crime (S-17) | 0.25 | 0.25 | SEC-3 | SEC-2 | ✔ |
| W-13 | T-23…T-27 incl. the zero-station T-26 | 0.25 | 0.75 | SEC-3 | W-10…12 | ✔ |
| W-14 | Exact-match location comparison, replacing `ILIKE '%s%'` | 0.5 | 0.75 | SEC-4 | SEC-0 | ✔ |
| W-15 | Branch predicate on checkpoint reads | 0.5 | 0.75 | SEC-4 | SEC-0 | ✔ |
| W-16 | Reject unknown checkpoint locations on write | 0.5 | 0.75 | SEC-4 | SEC-0 | ✔ |
| W-17 | T-28…T-35 | 0.5 | 0.75 | SEC-4 | W-14…16 | ✔ |
| W-18 | Migration: `suspect_alerts.branch_id` + index | 0.25 | 0.25 | M-02-A | D-1a, D-4, D-7 | ✔ |
| W-19 | Backfill + unresolved worklist (never defaulted) | 0.25 | 0.5 | M-02-A | W-18 | ✔ |
| W-20 | Record branch on write; refuse unresolved creator (R4) | 0.25 | 0.5 | M-02-A | W-18 | ✔ |
| W-21 | T-46a | 0.25 | 0.25 | M-02-A | W-20 | ✔ |
| W-22 | Filter `clearance[]`, `airport[]`, `alerts[]`, `checkpoints[]` (E-3…E-6) | 0.75 | 1.0 | SEC-1 | SEC-4, M-02-A | ✔ |
| W-23 | Branch filter on `/linked-records`, `/documents`, `/audit-history` (E-7…E-9) | 0.5 | 0.75 | SEC-1 | SEC-0 | ✔ |
| W-24 | Alert read scoping on `/api/suspect-alerts` (E-15) | 0.25 | 0.5 | SEC-1 | M-02-A | ✔ |
| W-25 | T-36…T-46 incl. the T-39 shape control | 0.5 | 0.75 | SEC-1 | W-22…24 | ✔ |
| W-26 | Staging diagnostic of invalid assignments | 0.5 | 1.0 | SEC-5 | SEC-1…4 | ✔ |
| W-27 | PRE-4 correction of invalid `users.branch` in staging | 0.5 | 1.0 | SEC-5 | W-26 | ✔ |
| W-28 | Fix the malformed placeholder list (N-7) | 0.25 | 0.25 | P0-WP-1 | — | ✔ |
| W-29 | Unblock `test_server.py`; verify discipline closure | 0.75 | 0.75 | P0-WP-1 | W-28 | ✔ |
| W-30 | Regression tests | 0.5 | 0.5 | P0-WP-1 | W-28 | ✔ |
| W-31 | Call `revoke_user_sessions()` on the admin reset path | 0.25 | 0.25 | P0-WP-2 | — | ✔ |
| W-32 | Keep-token semantics for admin reset | 0.25 | 0.5 | P0-WP-2 | W-31 | ✔ |
| W-33 | Audit event recording sessions revoked | 0.25 | 0.25 | P0-WP-2 | W-31 | ✔ |
| W-34 | T-65…T-68 | 0.75 | 1.0 | P0-WP-2 | W-31…33 | ✔ |
| W-35 | Per-account bootstrap randomness; refuse shared default (S-12) | 0.5 | 0.75 | P0-WP-3 | — | ✔ |
| W-36 | Demo seeding off by default (S-13, A-16/16a) | 0.5 | 0.75 | P0-WP-3 | — | ✔ |
| W-37 | Admin-only init; bootstrap warning (A-17, A-19) | 0.5 | 0.75 | P0-WP-3 | W-35 | ✔ |
| W-38 | A-18 — nine branch rows | 0.25 | 0.5 | P0-WP-3 | **full SEC band + PRE-3** | ✔ |
| W-39 | Verification run on a clean database | 0.25 | 0.25 | P0-WP-3 | W-35…38 | ✔ |
| W-40 | M-01 schema: `documents` + ownership columns | 2.0 | 3.0 | S-01 | SEC-0, D-7 | ✔ |
| W-41 | Backfill existing files + reconciliation report | 2.0 | 3.0 | S-01 | W-40 | ✔ |
| W-42 | Dual-read period and rollback path | 1.0 | 2.0 | S-01 | W-40 | ✔ |
| W-43 | Enforcement at the serving path, per-file authorization | 3.0 | 5.0 | S-01 | W-40 | ✔ |
| W-44 | Wire every upload producer to record ownership | 2.0 | 3.0 | S-01 | W-40 | ✔ |
| W-45 | Activate the 15 prepared document tests (enforcement mode) | 1.0 | 2.0 | S-01 | W-43 | ✔ |
| W-46 | Terminal status + mandatory reason | 0.5 | 0.75 | A-13 | M-02-A, D-4b, D-23.5/.6 | ✔ |
| W-47 | Withdraw endpoint behind a named `alerts:withdraw` permission | 0.75 | 1.0 | A-13 | W-46 | ✔ |
| W-48 | Audit event: actor, reason, timestamp | 0.25 | 0.5 | A-13 | W-46 | ✔ |
| W-49 | Verify the flag stops at `POST /api/checkpoint-events` | 0.25 | 0.25 | A-13 | W-47 | ✔ |
| W-50 | Negative tests (no permission, no reason, double withdrawal) | 0.25 | 0.5 | A-13 | W-47 | ✔ |
| W-51 | Remove the `crimes` bypass; narrow station read for intake | 0.5 | 1.0 | SEC-6 | — | ✔ |
| W-52 | Internal gate on `/api/officers`; confirm `/api/stations` | 0.25 | 0.5 | SEC-6 | W-51 | ✔ |
| W-53 | Gate `?module=cid` at the route | 0.25 | 0.5 | SEC-6 | — | ✔ |
| W-54 | Role × bundle matrix review for every analytics surface | 0.5 | 1.0 | SEC-6 | W-51…53 | ✔ |
| W-55 | T-47…T-56 incl. four positive controls | 0.5 | 1.0 | SEC-6 | W-51…54 | ✔ |
| W-56 | Absolute session lifetime from `created_at` | 0.5 | 0.75 | SEC-7 | — | ✔ |
| W-57 | Idle timeout — additive `last_seen_at` column | 0.5 | 0.75 | SEC-7 | D-7 | ✔ |
| W-58 | Session enumeration + revoke-all | 0.5 | 0.75 | SEC-7 | — | ✔ |
| W-59 | `TOKENS` cache honours expiry | 0.25 | 0.25 | SEC-7 | W-56 | ✔ |
| W-60 | T-57…T-64 | 0.25 | 0.5 | SEC-7 | W-56…59 | ✔ |
| W-61 | Per-account and per-source throttling with a lockout threshold | 0.75 | 1.0 | SEC-8 | — | ✔ |
| W-62 | Authentication audit events, success and failure | 0.5 | 0.75 | SEC-8 | — | ✔ |
| W-63 | Administrator unlock path, itself audited | 0.25 | 0.5 | SEC-8 | W-61 | ✔ |
| W-64 | T-69…T-76 | 0.5 | 0.75 | SEC-8 | W-61…63 | ✔ |
| W-65 | `Secure` attribute on the session cookie + T-77 | 0.25 | 0.25 | SEC-9 | — | ✔ |
| W-66 | TLS termination, certificate, renewal procedure | 1.0 | 2.0 | SEC-9 | staging exists | ✔ |
| W-67 | HTTP→HTTPS redirect; bind app to a private interface | 0.25 | 0.75 | SEC-9 | W-66 | ✔ |
| W-68 | HSTS | 0.25 | 0.5 | SEC-9 | W-66 | ✔ |
| W-69 | TLS-1…TLS-10 acceptance run in staging | 0.25 | 0.5 | SEC-9 | W-65…68 | ✔ |

### 3.2 Package totals, summed from the items above

| Package | Items | Min | Max | Mandatory | Band |
|---|---|--:|--:|:--:|---|
| **SEC-0** | W-01…W-05 | **2.0** | **3.0** | ✔ | staging |
| **SEC-2** | W-06…W-09 | **2.0** | **3.0** | ✔ | staging |
| **SEC-3** | W-10…W-13 | **1.0** | **2.0** | ✔ | staging |
| **SEC-4** | W-14…W-17 | **2.0** | **3.0** | ✔ | staging |
| **M-02-A** | W-18…W-21 | **1.0** | **1.5** | ✔ | staging |
| **SEC-1** | W-22…W-25 | **2.0** | **3.0** | ✔ | staging |
| **SEC-5** | W-26…W-27 | **1.0** | **2.0** | ✔ | staging |
| **P0-WP-1** | W-28…W-30 | **1.5** | **1.5** | ✔ | staging |
| **P0-WP-2** | W-31…W-34 | **1.5** | **2.0** | ✔ | staging |
| **P0-WP-3** | W-35…W-39 | **2.0** | **3.0** | ✔ | production |
| **S-01 / M-01** | W-40…W-45 | **11.0** | **18.0** | ✔ | production |
| **A-13** | W-46…W-50 | **2.0** | **3.0** | ✔ | production |
| **SEC-6** (S-05 + S-20) | W-51…W-55 | **2.0** | **4.0** | ✔ | production |
| **SEC-7** (S-08) | W-56…W-60 | **2.0** | **3.0** | ✔ | production |
| **SEC-8** (S-09) | W-61…W-64 | **2.0** | **3.0** | ✔ | production |
| **SEC-9** (S-11) | W-65…W-69 | **2.0** | **4.0** | ✔ | production |

**Every package total equals the figure previously quoted for it.** The decomposition therefore
**confirms** the per-package numbers rather than revising them. That is the useful result: the
earlier error was never in the package estimates, only in how they were added up.

### 3.3 The arithmetic

```
BEFORE STAGING
  SEC-0      2.0 – 3.0
  SEC-2      2.0 – 3.0
  SEC-3      1.0 – 2.0
  SEC-4      2.0 – 3.0
  M-02-A     1.0 – 1.5
  SEC-1      2.0 – 3.0
  SEC-5      1.0 – 2.0
  P0-WP-1    1.5 – 1.5
  P0-WP-2    1.5 – 2.0
  ─────────────────────
  min 2+2+1+2+1+2+1+1.5+1.5         = 14.0
  max 3+3+2+3+1.5+3+2+1.5+2         = 21.0        →  14 – 21 days

ADDITIONALLY BEFORE PRODUCTION
  P0-WP-3    2.0 – 3.0
  S-01       11.0 – 18.0
  A-13       2.0 – 3.0
  SEC-6      2.0 – 4.0
  SEC-7      2.0 – 3.0
  SEC-8      2.0 – 3.0
  SEC-9      2.0 – 4.0
  ─────────────────────
  min 2+11+2+2+2+2+2                = 23.0
  max 3+18+3+4+3+3+4                = 38.0        →  23 – 38 days

TOTAL MANDATORY BEFORE PRODUCTION RELEASE 1.0
  min 14 + 23 = 37
  max 21 + 38 = 59                                →  37 – 59 days
```

| Scenario | Total |
|---|---|
| **All mandatory work** | **37 – 59 days** |
| If S-05/S-20 (SEC-6) is deferred under a **signed** risk acceptance | 35 – 55 days |
| Plus SS-1 if D-5 is approved | +1 – 2 days |
| Plus S-10 if D-04 requires it | +5 – 10 days |
| Full M-02 lifecycle, deferred to 1.1 under D-23 | 22 – 35 days *(not in the total)* |

### 3.4 Overlapping work that must **not** be counted twice

| # | Overlap | How it is handled |
|---|---|---|
| 1 | **S-04 appears twice** — as P1.4 (4–6 d) in the original remediation plan **and** as M-02-A (1–1.5 d) in the SEC band | **Count M-02-A only.** P1.4 is superseded: Phase A sits in the staging band and the remaining lifecycle is deferred to 1.1 under D-23 |
| 2 | **S-05 and S-20 share one root cause** (`:8396–8397`) | **One fix, costed once** in SEC-6. S-20 adds **zero** days |
| 3 | **S-17 and S-18 are inside SEC-3** | Three lines in the same function already being edited. **No separate estimate** |
| 4 | **S-16a and S-16b are both SEC-1** | One package, 2–3 d total |
| 5 | **SEC-0 is shared by SEC-1, SEC-2, SEC-3, SEC-4** | Costed **once** in SEC-0, never per consumer |
| 6 | **Session revocation is needed by both S-02 and S-08** | Costed **once** in P0-WP-2 (W-31…W-33). SEC-7 consumes the helper and does not re-cost it |
| 7 | **S-19 overlaps SS-1** | Not separately costed; inside SS-1's 1–2 d, which is optional |
| 8 | **S-08's `last_seen_at` migration uses the D-7 procedure** | The procedure is costed once as a decision, not per migration |
| 9 | **The 46 tests and the new T-47…T-77** | Each test is costed inside the package that owns it (W-05, W-09, W-13, W-17, W-21, W-25, W-34, W-50, W-55, W-60, W-64, W-69). **No separate testing line** |
| 10 | **S-01's 15 document tests already exist** | W-45 is *activation*, 1–2 d, not authoring. Authoring was paid during the investigation |
| 11 | **A-18 is inside P0-WP-3** | W-38, 0.25–0.5 d. It is not a separate package |

### 3.5 Every difference from previous estimates, explained

| # | Change | Explanation |
|---|---|---|
| 1 | **Revision 2: `+23–37`** | This was **never a sum of the items printed beside it.** It was the P1 band total of `REMEDIATION_PLAN.md` (S-03 2–3, S-01 5–8, S-01 6–10, **S-04 4–6**, **S-05 2–4**, S-08 2–3, S-09 2–3 = 23–37), pasted next to a different list. It **double-counted S-04 and S-05** and **omitted S-11 and P0-WP-3** |
| 2 | **Revision 3: `+23–38`** | The honest sum of seven production items **including** SEC-6 (S-05 + S-20) at 2–4, after execution moved S-05 into the mandatory band |
| 3 | **Why the minimum is 23 in both** | **Coincidence, not agreement.** Revision 2's minimum was `2+5+6+4+2+2+2`; revision 3's is `2+11+2+2+2+2+2`. Different items, same sum. Flagged so it is not read as confirmation |
| 4 | **Why the maximum moved 37 → 38** | Removing S-04 (−6) and S-05-as-P1 (−4), adding S-11 (+4), P0-WP-3 (+3) and SEC-6 (+4): `37 − 6 − 4 + 4 + 3 + 4 = 38` |
| 5 | **Total 37–58 (rev 2) → 37–59 (rev 3)** | Revision 2's total was built on the mis-cited band; revision 3's is `14–21` plus `23–38`. The near-match is arithmetic accident |
| 6 | **This revision: no package range changed** | The work-item decomposition reproduces every package total exactly (§3.2). **Nothing was adjusted to fit** |
| 7 | **Two new conditional additions disclosed** | S-09 **+0.5–1 d** if the production deployment is load-balanced (shared throttle state); M-02-A **+0.5–2 d** if a populated alert database appears. Neither is in the headline total, because neither condition is known to hold |

---

## 4. Implementation and verification packages, in dependency order

> **No package may start until the decisions in `OWNER_DECISION_PACKAGE_R1.md` that gate it are
> recorded, and until implementation is authorized.**

### Wave 0 — parallel, no SEC-0 dependency

#### P0-WP-1 — S-07 / N-7 discipline closure · 1.5 d

| | |
|---|---|
| **Scope** | Correct the malformed placeholder list so a disciplinary action can be closed and a suspended officer returned to Active duty |
| **Files / endpoints** | `backend/server.py` — `update_discipline()` (`:6778`, defect at `:6828`); `/api/conduct`, `/api/officers/discipline` |
| **Migration** | None |
| **Automated tests** | `backend/test_server.py` moves BLOCKED → PASS; new regression test for close-and-reactivate |
| **Manual tests** | Suspend an officer in the UI, close the action, confirm the roster shows Active |
| **Security acceptance** | No authorization change. The close action must remain restricted to the HR/conduct module and must write an audit row |
| **Rollback** | Revert one commit. No data written that a revert would strand |
| **Done when** | Suite is **29 PASS / 0 FAIL / 0 BLOCKED** and an officer can be returned to duty |

#### P0-WP-2 — S-02 administrator reset revocation · 1.5–2 d

| | |
|---|---|
| **Scope** | The administrator password-reset path revokes every session of the target account |
| **Files / endpoints** | `backend/server.py` — `PATCH /api/admin/users/<id>` (`:9931`), `revoke_user_sessions()` (`:4224`); E-36 |
| **Migration** | None |
| **Automated tests** | T-65…T-68 |
| **Manual tests** | Sign in as a user in two browsers, reset from the admin console, confirm **both** are signed out while the admin's own session persists |
| **Security acceptance** | Zero surviving `sessions` rows for the target; the admin's session unaffected; the self-service behaviour unchanged; an audit row records how many sessions were revoked |
| **Rollback** | Revert one commit. Revocation is not destructive to user data |
| **Done when** | The measured B.6 scenario returns `401` for the victim's old token |

#### SEC-6 — S-05 + S-20 module-gate repair · 2–4 d

| | |
|---|---|
| **Scope** | Remove the `crimes` bypass; gate `/api/officers`; gate `?module=cid`; re-derive the analytics role × bundle matrix |
| **Files / endpoints** | `backend/server.py:8396–8397` (the bypass), `/api/officers` (`:8833`), `/api/stations` (`:8784`), `/api/stations/analytics`, `/api/vehicles/analytics`, `/api/cid/analytics`, `/api/analytics` (`:8626–8660`); E-27…E-32. Possibly `index.html` where the intake dropdown is populated |
| **Migration** | None |
| **Automated tests** | T-47…T-56 |
| **Manual tests** | File a crime incident end to end as a CID officer and confirm the station dropdown still works |
| **Security acceptance** | The full 20 × 7 matrix re-run: every leak cell refused, **no correctly-permitted cell newly refused** |
| **Rollback** | Revert one commit. **Risk on rollback is re-opening the leak, not breaking data** — so rollback must be accompanied by re-asserting the risk acceptance |
| **Done when** | `cid.officer` cannot read the officer register and the crime desk still works |

### Wave 1 — the authorization foundation

#### SEC-0 — consolidated authorization model · 2–3 d

| | |
|---|---|
| **Scope** | One model: `UNRESTRICTED` / `GRANTED` / `INDETERMINATE`; `AccessDecision(state, value, reason)`; `authorize(c, user, *, module, unit_type, location)`; `enforce()` → 403 on `INDETERMINATE`; `scope_clause()` with **two** branches and no empty-predicate fallback |
| **Files / endpoints** | `backend/server.py` — new module-level helpers replacing `branch_scope_view` (`:2661`), `user_branch_scope` (`:2728`), `checkpoint_scope` (`:2965`), `checkpoint_scope_sql` (`:6275`). No endpoint changes yet |
| **Migration** | None |
| **Automated tests** | T-01…T-10. **T-10 is a property test** and is the single most important test in the programme |
| **Manual tests** | None — this package has no user-visible surface |
| **Security acceptance** | No input combination yields `UNRESTRICTED` without an explicit grant; `INDETERMINATE` can never produce an empty SQL predicate |
| **Rollback** | Revert. Nothing consumes it yet, so rollback is free — **which is why it ships first and alone** |
| **Done when** | T-01…T-10 green and the old helpers are unreferenced |

### Wave 2 — apply the model (SEC-2 → SEC-3; SEC-4 and M-02-A in parallel)

#### SEC-2 — S-14 fail-open removal · 2–3 d

| | |
|---|---|
| **Scope** | Move all 12 enforcing call sites onto SEC-0 |
| **Files / endpoints** | `backend/server.py`; E-10…E-14, E-18, E-21 |
| **Migration** | None |
| **Automated tests** | T-11…T-22 |
| **Manual tests** | Sign in as an officer with a deliberately invalid posting in staging; confirm refusal, not disclosure |
| **Security acceptance** | Unresolved, missing and invalid postings fail **closed** on every scoped read and write; correctly posted officers unaffected |
| **Rollback** | Revert. Fail-open returns — **must not be left rolled back in a reachable environment** |
| **Done when** | T-11…T-22 green and no caller treats `None` as "no filter" |

#### SEC-3 — S-15 + S-17 + S-18 crime register · 1–2 d

| | |
|---|---|
| **Scope** | Correct unit type on the list; pin the write scope; make the branch mandatory on write; report any pre-existing NULL rows without defaulting them |
| **Files / endpoints** | `backend/server.py` — `register_crime()` (`:5287`), `GET /api/crimes` (`:8835`), `POST /api/crimes` (`:9684`), `resolve_branch()` (`:4046`); E-19, E-20 |
| **Migration** | **None.** Pre-existing NULL rows are reported, not rewritten |
| **Automated tests** | T-23…T-27, **T-26 especially** |
| **Manual tests** | File an incident as a posted officer; attempt to file against another branch and confirm refusal |
| **Security acceptance** | `/api/crime-cases` and `/api/crimes` agree on the branch; no 201 without a branch; no cross-branch filing |
| **Rollback** | Revert. **Must be rolled back before A-18, never after** |
| **Done when** | T-23…T-27 green and the zero-station case refuses rather than returning all |

#### SEC-4 — H-2b checkpoint scope · 2–3 d

| | |
|---|---|
| **Scope** | Exact-match locations; branch predicate on reads; reject unknown locations on write |
| **Files / endpoints** | `checkpoint_scope()` (`:2965`), `checkpoint_scope_sql()` (`:6275`), `CHECKPOINT_LOCATIONS` (`:1649`), `GET /api/checkpoint-events`, `POST /api/checkpoint-events` (`:9505`); E-21, E-22 |
| **Migration** | None |
| **Automated tests** | T-28…T-35 |
| **Manual tests** | Record a stop at the officer's own checkpoint; attempt one at another and confirm refusal |
| **Security acceptance** | `South` does not match `Southwest`; an empty scope refuses; fabricated location codes cannot be stored |
| **Rollback** | Revert |
| **Done when** | T-28…T-35 green, including both positive controls |

#### M-02-A — suspect-alert ownership · 1–1.5 d · **gated by D-1a, D-4, D-7**

| | |
|---|---|
| **Scope** | Additive `branch_id` column + index; backfill with a worklist; record owner on write; refuse creation when the creator is unresolved |
| **Files / endpoints** | `suspect_alerts` DDL (`:299`), `POST /api/suspect-alerts` (`:9465`); E-16 |
| **Migration** | **Yes — additive only.** No column dropped, renamed or retyped; no row deleted |
| **Automated tests** | T-46a |
| **Manual tests** | Create an alert as a posted CID officer; confirm the owner is recorded. Attempt creation from an unresolved posting and confirm refusal |
| **Security acceptance** | No alert exists without an owner; unresolved rows appear on a worklist and are **never defaulted** to a branch |
| **Rollback** | **Two levers, strict order.** 1) revert the code — no data loss, the column stays and keeps populating. 2) `DROP COLUMN branch_id` — **only** if the column is being abandoned, and **never while enforcement is live** |
| **Done when** | Every new alert carries an owner and the worklist count is reported |

### Wave 3 — the dependent package

#### SEC-1 — S-16a + S-16b + alert reads · 2–3 d · **requires SEC-4 and M-02-A**

| | |
|---|---|
| **Scope** | Branch-filter the four attached registers in the person detail and the three attached collection endpoints; scope alert reads |
| **Files / endpoints** | `GET /api/persons/<id>` (`:8449`), `linked_person_records()` (`:5883`), `person_document_records()` (`:5962`), `person_audit_history()` (`:4451`), `GET /api/suspect-alerts` (`:8705`); E-3…E-9, E-15 |
| **Migration** | None |
| **Automated tests** | T-36…T-46 |
| **Manual tests** | Open the same person as officers of two different branches and compare what each sees |
| **Security acceptance** | All **27 measured leak combinations** refused; identity still shared (**T-39: the same object shape, never a smaller object**); in-branch reads unaffected |
| **Rollback** | Revert |
| **Done when** | T-36…T-46 green, T-45 still green, and the 27 combinations re-measured as refused |

### Wave 4 — staging verification

#### SEC-5 — staging diagnostic and PRE-4 correction · 1–2 d

| | |
|---|---|
| **Scope** | Report every invalid or unresolved posting in staging; correct them; re-verify |
| **Files / endpoints** | A staging-only diagnostic. **No production report-only phase** — the owner ruled that out |
| **Migration** | None; data correction in staging only |
| **Automated tests** | Re-run the full suite plus T-01…T-46 |
| **Manual tests** | Walk each role through its primary workflow in staging |
| **Security acceptance** | Zero unresolved postings remain; every role's primary workflow still completes |
| **Rollback** | Not applicable — diagnostic and data correction |
| **Done when** | The diagnostic reports zero invalid assignments |

### Wave 5 — production readiness, in parallel

#### SEC-7 — S-08 session lifetime · 2–3 d · **migration (D-7)**
#### SEC-8 — S-09 throttling and authentication audit · 2–3 d
#### SEC-9 — S-11 TLS and `Secure` cookie · 2–4 d
#### A-13 — interim alert withdrawal · 2–3 d · **gated by D-4b, D-23.5, D-23.6**
#### S-01 / M-01 — document ownership · 11–18 d · **can start after SEC-0, in parallel**

| Package | Files / endpoints | Migration | Tests | Rollback | Done when |
|---|---|---|---|---|---|
| **SEC-7** | `sessions` DDL (`:446`), `require_auth()` (`:4256`), `create_session()` (`:4209`), `lookup_session()` (`:4191`); E-33, E-34 | **Yes** — additive `last_seen_at` | T-57…T-64 | Revert code; the column may stay unused | The 678-day scenario returns 401 |
| **SEC-8** | `/api/login` (`:8944`); E-33 | **Yes if** counters are stored in a table/column | T-69…T-76 | Revert code; **lockout state must be cleared on rollback** so nobody stays locked out | 30 failures then the correct password is still refused, and every attempt is audited |
| **SEC-9** | `Set-Cookie` (`:8971`) plus deployment configuration | None | T-77 + **TLS-1…TLS-10** | Revert the cookie flag; infrastructure rollback is a proxy config change | TLS-1…TLS-10 all pass in staging |
| **A-13** | `suspect_alerts`, new withdraw route, `POST /api/checkpoint-events` (`:9597`) | None beyond M-02-A | Per §2.6 | Revert the route; withdrawn rows keep their status — **a second migration would be needed to undo them, so do not roll back after live use** | A wrongly listed person can be cleared, audited, by an authorized actor |
| **S-01** | `save_upload_validated()` (`:4606`), `/uploads/`, every upload producer, E-8 | **Yes — M-01, the largest** | The 15 prepared cases in enforcement mode | Dual-read period (W-42) exists precisely so code can be reverted without stranding files | That suite runs with **zero skips**, all 15 green |

### Wave 6 — production initialization

#### P0-WP-3 — S-12, S-13, A-16/16a/17/19, A-18 · 2–3 d

**Prerequisites, complete and authoritative:** **SEC-0 · SEC-2 · SEC-3 · SEC-4 · M-02 Phase A ·
SEC-1 · SEC-5 · PRE-3.** A-18 is production initialization; it may not precede any of them.

| | |
|---|---|
| **Files / endpoints** | `bootstrap_password_for()` (`:3489`), `init_db()` (`:3261`), demo seeding (`:3324–3375`), `DEFAULT_POLICE_BRANCHES` (`:1660`) |
| **Migration** | Data initialization, not schema. **Nine branch rows only** |
| **Tests** | Clean-database initialization run; expected result branches 9 / stations 0 / locations 0 / officers 0 / users 1 |
| **Security acceptance** | No shared default password; no demo records; a warning emitted for the bootstrap variable |
| **Rollback** | **The hardest to roll back** — initialization creates records in a real database. The rollback is a documented deletion script for the nine rows, valid **only** before any dependent record exists |
| **Done when** | `PRODUCTION_INITIALIZATION.md` executes end to end and the result matches exactly |

---

## 5. Final release acceptance checklist

**Nothing below may be marked complete on the basis of code inspection.** Each line is a measured
result or it is not done.

### 5.1 Environment

- [ ] A **disposable PostgreSQL cluster** is provisioned per run and destroyed at exit; no existing database is opened.
- [ ] A **real `server.py` process** serves every test; no in-process stubbing of authorization.
- [ ] All nine seeded role accounts exist and authenticate over **real HTTP**.
- [ ] `backend/server.py` sha256 recorded before and after the run.

### 5.2 Role-based authorization, over real HTTP

- [ ] **T-01…T-10** — the SEC-0 model, including the **T-10 property test**.
- [ ] **T-11…T-22** — S-14: unresolved, missing and invalid postings fail closed.
- [ ] **T-23…T-27** — S-15/S-17/S-18, including **T-26** (zero stations ⇒ refuse, never all).
- [ ] **T-28…T-35** — H-2b, including `Southwest` ≠ `South` and unknown location ⇒ 400.
- [ ] **T-36…T-46** — S-16a/S-16b, including **T-39** (same object shape) and **T-45** (the flag stays national).
- [ ] **T-47…T-56** — S-05/S-20, including all four positive controls.
- [ ] **T-57…T-64** — S-08 session expiry, including the post-restart database path.
- [ ] **T-65…T-68** — S-02 administrator reset revocation.
- [ ] **T-69…T-76** — S-09 throttling and authentication audit.
- [ ] **T-77** — the session cookie carries `Secure`, `HttpOnly`, `SameSite`.
- [ ] The **15 prepared document tests** run in enforcement mode with **zero skips**.
- [ ] **Every one of the 27 measured S-16 leak combinations** re-measured as refused.
- [ ] **The 20 × 7 analytics matrix** re-measured with no new false refusals.
- [ ] **Negative controls:** every denial test has a matching allow test that still passes.
- [ ] **No test was weakened to pass**, no assertion loosened, no suite skipped.

### 5.3 Frontend workflows, manually walked

- [ ] Fingerprint clearance intake, end to end, including document upload.
- [ ] Crime incident registration, including the station dropdown and the generated file number.
- [ ] Checkpoint stop recording, including a flagged match.
- [ ] Airport record creation.
- [ ] Officer registration and posting.
- [ ] Disciplinary action opened **and closed**, officer returned to Active duty.
- [ ] Suspect alert created; if A-13 is approved, withdrawn and the flag confirmed stopped at a real checkpoint stop.
- [ ] Admin: create a user, reset a password, confirm the target is signed out everywhere.
- [ ] Each role sees only its own modules in the navigation.

### 5.4 Migrations

- [ ] Every migration is **additive**; nothing dropped, renamed or retyped on the way in.
- [ ] Each migration runs on a **clean** database and on a **populated** one.
- [ ] Backfill worklists are **reported**, and unresolved rows are **never defaulted**.
- [ ] Re-running a migration is idempotent (`IF NOT EXISTS`).
- [ ] The row counts before and after each migration are recorded.

### 5.5 Rollback

- [ ] Every package's rollback is **executed in staging**, not merely described.
- [ ] The **two-lever** rule is respected: code first, schema only after, and never while enforcement is live.
- [ ] A-13 and P0-WP-3 are confirmed as the two packages that **cannot** be cleanly rolled back after live use, and this is accepted in writing before they ship.

### 5.6 Staging gate before production

- [ ] SEC-5 reports **zero** invalid or unresolved postings.
- [ ] **TLS-1…TLS-10** all pass against the staging host.
- [ ] The full suite is **29 PASS / 0 FAIL / 0 BLOCKED** (N-7 fixed).
- [ ] PRE-1, PRE-2, PRE-3, PRE-4, PRE-5 are all confirmed by their owners.
- [ ] **No report-only production phase** is scheduled — enforcement is live from the first production request.
- [ ] A rollback decision-maker is named and reachable during the production initialization window.

---

## 6. What this programme deliberately does **not** cover

| Item | Why |
|---|---|
| **S-10** tamper-evident audit | Conditional on legal decision **D-04 / A-6**. Specifying tests now would invent a requirement |
| **Full M-02 six-state lifecycle** | Deferred to 1.1 under **D-23**. 22–35 d, excluded from the total |
| **A CID supervisor role** | +4–8 d, touches every module, and needs **D-23.1** |
| **SS-1** station safeguards | Optional, awaiting **D-5**. 1–2 d |
| **S-19** file-number provenance | Policy first; overlaps SS-1 |
| **`/api/crimes/<id>`** | No such route exists today; building one is new functionality, not remediation |
| **Load-balanced throttle state** | Only if the production topology is multi-instance — flagged in §2.11 as an unverified assumption |

---

## 7. Approval gate

**Nothing in this programme may begin until:**

1. The owner records the decisions in `OWNER_DECISION_PACKAGE_R1.md` — at minimum **D-3**, which
   blocks all implementation.
2. The owner explicitly authorizes implementation. **This document is a plan, not a mandate.**
3. **D-23.5 and D-23.6** are answered before **A-13** is built, and **PRE-3** before **A-18**.

**Standing constraint restated:** these are sensitive police records. Where this programme offers a
choice between a faster path and a correctly isolated, fully accountable one, it recommends the
latter, and every place where speed was traded away is stated rather than hidden.

---

## 8. Verification

### 8.1 Commit ledger

| Item | Value |
|---|---|
| Branch | `arena/6303ef2f-sentinel-police-management` |
| HEAD before this work | `28e68eea93d7d0268c635326dbf88b4356793c2e` |
| `origin/main` | `a1c2478262776e9f20b4c3ad806eaa86adc27792` — **unchanged** |
| This programme's content commit | _recorded by the follow-up metadata commit; a commit cannot contain its own hash_ |
| `backend/server.py` | sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` |

### 8.2 Compliance

| Restriction | Status |
|---|---|
| No application code modified | ✔ `server.py` sha256 unchanged |
| No merge into `main` | ✔ `origin/main` = `a1c2478…` |
| All investigation evidence preserved | ✔ nothing deleted, re-dated or rewritten |
| Branch, HEAD, tree and `origin/main` confirmed **from Git** | ✔ §0, read with `git rev-parse` |
| No hash invented, estimated or typed by hand | ✔ every hash in this document was read from `git` |
| Decisions neither rewritten nor selected on the owner's behalf | ✔ `OWNER_DECISION_PACKAGE_R1.md` quotes the original wording verbatim |
