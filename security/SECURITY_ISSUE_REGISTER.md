# Security Issue Register — post-Stage-0 triage

**Date:** 7 November 2026 · **Baseline commit:** `e7263d7` (Stage 0) · **Report commit:** `41b4843`
**Status:** investigation and design only. **No application code was modified and no migration was
executed in producing this register.**

Severity scale: **Critical** (exploitable now, severe harm) · **High** · **Medium** · **Low**.
"Release-blocking" means Release 1.0 must not go live with the issue open.

---

## 1. Register

| ID | Issue | Severity | Release-blocking | State | Evidence |
|---|---|---|---|---|---|
| **S-01** | **Cross-branch document access.** Any authenticated officer can read any uploaded document, including another branch's. | **High** | **YES** | **OPEN** — Stage 0 closed anonymous access only | `test_upload_access_control.py::test_07` returns **200** |
| **S-02** | **Admin password reset does not revoke the target's sessions** (H-5). A stolen session survives the reset. | **High** | **YES** | **OPEN** | `test_password_security.py::test_15` passes, proving the session stays live |
| **S-03** | **Suspect alerts can never be cleared.** `alert_status` is written `'Active alert'` at INSERT and **no code path ever updates it**. A person cleared by CID keeps flagging at every checkpoint, forever. | **High** | **YES** | **OPEN** | Only `UPDATE suspect_alerts` in the codebase is `SET origin=…` (line 3232). No status transition exists. |
| **S-04** | **Suspect alerts carry no `branch_id`** (N-1), so alerts are unscoped across branches. **PROVEN BY EXECUTION (5 Nov 2026):** an Erigavo CID officer reads a Buuhoodle alert from `GET /api/suspect-alerts` — `200`, no branch clause exists in the route. Also leaks via `/api/persons/<id>`. **Severity raised Medium → High**: it is not a latent schema gap, it is a live cross-branch read. Architecture and fix: `SUSPECT_ALERT_OWNERSHIP.md` (requires schema change M-02 Phase A). | **High** *(raised)* | **YES** (coupled to S-03) | **OPEN** → M-02-A + SEC-1 | `S16_REGISTER_VERIFICATION.md` §4; `suspect_alerts` DDL line 299 |
| **S-05** | **Analytics RBAC leak** (N-3). `crimes` acts as a skeleton key: `cid.officer` receives vehicle and station analytics it has no module for; the CID bundle is ungated entirely. | **Medium** | No — fix before release, not a gate | **OPEN** | Root cause isolated, §3 |
| **S-06** | ~~Existing databases still hold `ChangeMe123!`~~ → **R-1 (7 Nov 2026): no operational database has ever existed.** No emergency rotation is required. **Residual:** no documented production initialization exists, so the *next* install is the exposure. | **High** | **No longer** blocking on existing data; **YES** for the first production install | **REDUCED** — rotation discharged, initialization open → **P0-WP-3** | Owner decision R-1; `PRODUCTION_INITIALIZATION.md` |
| **S-07** | **N-7 — closing a disciplinary action is impossible**, so a suspended officer can never be returned to Active duty. Functional defect with a direct human consequence. | **High** (operational, not security) | **YES** for the HR module | **OPEN** | `server.py:6828`, `','.join('%s' * n)` → `'%,s,%,s,%,s'` |
| S-08 | No session expiry (H-3) | High | YES | OPEN — not investigated this round | Carried from the Phase 2 register |
| S-09 | No authentication throttling or auth audit (H-4) | High | YES | OPEN — not investigated this round | Carried |
| S-10 | Mutable audit log (H-7) | High | YES — needs decision D-04 | OPEN | Carried |
| S-11 | No TLS (H-8) | High | YES | OPEN — deployment concern | Carried |
| **S-12** *(new, 7 Nov)* | **One environment variable gives all nine seeded accounts the same password.** `bootstrap_password_for()` returns `SENTINEL_BOOTSTRAP_PASSWORD` **unchanged for every username**; per-account randomness happens only when it is unset. No warning is emitted. The test runner sets it to `ChangeMe123!` by design — an operator copying that into production recreates the defect Stage 0 removed. | **High** | **YES** for the first production install | **OPEN** → **P0-WP-3** | `server.py:3489`; `test_password_security.py::test_05` |
| **S-13** *(new, 7 Nov)* | **First run seeds demonstration data into any empty database** — 3 fictional persons with national IDs, 2 crime cases, 1 clearance application, 1 checkpoint event, and **1 `'Active alert'` suspect alert**. There is no production mode. Combined with **S-03**, that seeded alert **can never be cleared**. | **High** | **YES** for the first production install | **OPEN** → **P0-WP-3** | `server.py:3302` (accounts), `:3324`+ (data); alert INSERT verified |
| **S-14** *(new)* | **Branch-scope authorization fails open.** `user_branch_scope()` returns `None` both for a deliberately unrestricted session (admin / Chief) **and** for an officer whose posting is empty, misspelled, unknown or ambiguous. Every call site then skips the `WHERE branch_id=…` filter, and `require_record_branch_scope()` returns early. **Proven by execution:** an officer posted to `Zzz Nowhere Posting` listed records from every branch (3 vs 1), opened another branch's record (**200** where a correctly-posted officer got **403**), and **filed a new record into another branch** (**201**, landed in branch 11). | **CRITICAL** | **YES** | **OPEN** — release blocker | `BRANCH_SCOPE_FAIL_OPEN.md` §3, probes P1–P4; `server.py:2790`, `2742`, `8465`, `8481`, `8524`, `8544`, `8563`, `8837` |
| **S-15** *(new)* | **`/api/crimes` scopes on the wrong unit type.** The list filters on `user_branch_scope(…, 'police_station')` (`server.py:8837`) while `register_crime()` stores a **`crime`** branch id (`server.py:5288`). Measured on one CID session: `/api/crime-cases` → `branch_id=2`, `/api/crimes` → `branch_id=5`; the id sets are disjoint. **Fails closed today** (a posted CID officer sees zero incidents) but **becomes a total disclosure of the crime register if A-18 removes the `police_station` branch rows first.** | **High** | **YES** — ordering constraint on A-18 | **OPEN** | `BRANCH_SCOPE_FAIL_OPEN.md` §4, probe P5 |
| **S-16a** *(new)* | **`GET /api/persons/<id>` applies NO module, branch or location filtering to the unit records it attaches.** The route is deliberately not module-gated (`server.py:8374`), yet the handler attaches four unit registers — `clearance_applications`, `airport_passengers`, `suspect_alerts`, `checkpoint_events` — each an unfiltered `WHERE person_id=%s` (`:8449–8461`). **Proven by execution:** `cp.south` (modules `['checkpoints','dashboard']`) was refused `/api/clearance-applications` with **401** yet received application `FP-40964580` from `/api/persons/<id>` (**200**); and a **correctly posted** Fingerprint officer, whose scoped list excluded the record and whose direct fetch returned **403**, received it here. The sibling `/linked-records` filtered correctly (`units_returned=[]`) — the omission is local to this handler. **No precondition: needs no misconfiguration.** | **CRITICAL** | **YES** | **OPEN** → SEC-1 | `AUTHORIZATION_REMEDIATION_PLAN.md` §2, probes Q1–Q4 |
| **S-16b** *(new)* | **The three sibling person endpoints apply module and checkpoint-location filtering but NO branch filtering.** `linked_person_records()`, `person_document_records()` and `person_audit_history()` each gate sources on `user_module_set(user)` and apply `checkpoint_scope_sql(...)`, but return `branch_id`/`branch_name` purely as display metadata and never constrain on them. A correctly posted officer therefore sees other branches' records through `/linked-records`, `/documents` and `/audit-history`. **PROVEN BY EXECUTION (5 Nov 2026):** an Erigavo Fingerprint officer filtered out of `/api/clearance-applications` still receives the Buuhoodle record from `/linked-records`; same result for Airport. `/documents` and `/audit-history` remain code-read only. | **High** | **YES** | **OPEN** → SEC-1 | `S16_REGISTER_VERIFICATION.md` §2–§3; tests T-41…T-43 |

### Owner's four tracked items — confirmed still visible and open

Recorded explicitly at the owner's request, so none is lost behind the newer findings:

| ID | Item | State | Next step |
|---|---|---|---|
| **S-01** | Cross-branch document authorization | **OPEN — release-blocking** | Migration **M-01**, approvals A-1…A-6; tests already written and skipping until the table exists |
| **S-02** | Administrator password-reset session revocation | **OPEN — release-blocking** | **P0-WP-2**, approval A-11 |
| **S-05** | Analytics RBAC leak | **OPEN** | Approval A-12 (P1.5) |
| **S-03 / S-04** | Suspect-alert lifecycle and branch scope | **OPEN — release-blocking** | Interim withdrawal A-13; migration **M-02** A-7/A-8; blocked on **D-23** (`planning/D23_LEGAL_ACTION_BRIEF.md`) |

### Closed by Stage 0 (for completeness)

| ID | Issue | State |
|---|---|---|
| C-1 | Anonymous access to `/uploads/` | **CLOSED** — 401, verified |
| C-2 | Nine shared seeded default credentials | **CLOSED** for new installs — see S-06 for existing ones |
| C-3 | Unsalted single-round SHA-256 passwords | **CLOSED** — PBKDF2-HMAC-SHA256, 600k, salted |
| M-7 | Unvalidated uploads | **CLOSED** — allow-list, cap, magic-number check |
| FPR-902 | Fabricated biometric matches | **CLOSED** — fallback removed, negative control run |
| N-8 | Password change did not revoke other sessions | **CLOSED** — `revoke_user_sessions()` |

---

## 2. S-02 — Administrator password reset (H-5), investigated

**Where:** `PATCH /api/admin/users/<id>`, `backend/server.py:9931`.

**What the handler does:** builds a `sets` dict of changed columns — `display_name`, `branch`,
`role`, `location_scope`, `badge_number`, `active`, `password_hash` — issues one `UPDATE users`,
writes an audit row, and returns. **There is no reference to the `sessions` table or to the `TOKENS`
cache anywhere in the handler.**

**Why some changes *do* take effect immediately, and the password does not.** `require_auth()`
re-reads the user row on every request with `SELECT … WHERE id=%s AND active=1`. So:

| Admin change | Takes effect on existing sessions? | Why |
|---|---|---|
| `active = 0` (deactivate) | **Yes, immediately** | the `active=1` predicate fails on the next request |
| `role`, `branch`, `location_scope` | **Yes, immediately** | the row is re-read each request |
| **`password`** | **No — session survives** | the session token is independent of the password; nothing links them |

**Consequence.** The single most common incident response — "this officer's password is
compromised, reset it" — **does not evict the attacker**. The attacker's existing session keeps
working indefinitely, because there is also no session expiry (S-08). The administrator has no way
to know this, and the UI gives no warning.

**Note on asymmetry:** Stage 0 fixed the *self-service* path (N-8) but the *administrator* path is
the one that matters more during an incident, because the victim may have lost access to the account.

**Recommended fix (design only — not implemented):** call the existing
`revoke_user_sessions(conn, uid, keep_token=None)` helper — already present from Stage 0 — whenever
`password_hash` is in `sets`. Roughly:

```python
if 'password_hash' in sets:
    revoke_user_sessions(c, uid)          # no keep_token: end EVERY session
    audit(c, user, 'REVOKE', 'user_sessions', str(uid),
          'all sessions revoked by administrator password reset')
```

**Also recommend:** revoke on `active = 0` too. It is already enforced per-request, but leaving dead
tokens in the `sessions` table and the `TOKENS` cache is untidy and becomes a real hole if the
`active=1` predicate is ever refactored away.

**Estimate:** 1–2 engineering days including tests. **Requires owner approval to change code.**

---

## 3. S-05 — Analytics RBAC leak (N-3), investigated

**Root cause is precise and has two parts.**

**Part 1 — `crimes` is a skeleton key.** The bundle gates are:

```python
def _officers_bundle(c, user):
    require_module(user, 'officers')

def _vehicles_bundle(c, user):
    require_any_module(user, ('cars', 'policesearch', 'checkpoints', 'crimes'))

def _stations_bundle(c, user):
    require_any_module(user, ('stations', 'crimes'))

def _global_bundle(c, user):
    require_permission(user, PERM_ANALYTICS_GLOBAL)
```

`ROLE_CID = {'dashboard', 'people', 'cid', 'crimes'}`. Because `crimes` appears in **both** the
vehicles OR-list and the stations OR-list, a CID officer passes both gates — despite having neither
the `cars` module nor the `stations` module.

**Part 2 — the CID bundle has no gate at all.** `build_cid_analytics()` is registered directly in
`ANALYTICS_BUILDERS` with no `require_module`. Any authenticated user reaches it. It filters
*sections* internally (`CID_SECTION_MODULES[name] in mods`), so the payload is narrowed, but the
endpoint itself is open and always returns 200.

**Measured against the running server** (recorded during Stage 0, consistent with the code above):

| Account | `ROLE_MODULES` | `?module=all` returns | Should return |
|---|---|---|---|
| `fp.officer` | `{dashboard, people, fingerprint}` | `['cid']` (fingerprint section only) | `['cid']` — acceptable |
| `cp.south` | `{dashboard, checkpoints}` | `['cid','vehicles']` | `['cid']` — **vehicles leaked** via `checkpoints` |
| `cid.officer` | `{dashboard, people, cid, crimes}` | `['cid','stations','vehicles']` | `['cid']` — **stations and vehicles leaked** via `crimes` |

**What leaks.** The station bundle includes the station deployment matrix, per-station cell capacity
and unassigned-officer counts. The vehicle bundle includes fleet status. Neither is catastrophic in
isolation, but both are operational police data exposed to roles the module map says must not have
them — and the module map is the document the project treats as the authorization contract.

**Why this is Medium and not High:** read-only, aggregate, available only to an authenticated
officer, and no personal data in the station/vehicle bundles. It is a **contract violation**, not a
breach. It is not release-blocking on its own, but it should be corrected before release because it
undermines confidence in every other `ROLE_MODULES` claim.

**Recommended fix (design only):**

1. Gate the CID bundle explicitly: `require_any_module(user, ('cid','fingerprint','checkpoints','airport'))`.
2. Remove `crimes` from the vehicles and stations OR-lists. `crimes` means *crime intake*, not
   *fleet* and not *station registry*.
3. If HR genuinely needs station analytics, it already has the `stations` module — the OR-list does
   not need `crimes` for that.
4. Add a test that asserts, for **every** seeded role, that `?module=all` returns exactly the
   expected bundle list. The current gap exists because no test ever asserted the full matrix.

**Decision needed from the owner:** is a CID officer *intended* to see vehicle and station
analytics? If yes, the fix is to add `cars`/`stations` to `ROLE_CID` explicitly and document it —
not to leave it happening by accident through `crimes`. **I recommend the explicit narrowing above.**

**Estimate:** 2–4 engineering days including the full role × bundle test matrix.

---

## 4. S-07 — N-7, investigated and triaged

**Location:** `backend/server.py:6828`, inside `update_discipline()`.

```python
elif action['status'] == 'Closed':
    placeholders = ','.join('%s' * len(DISCIPLINE_OPEN_STATUSES))   # BUG
    sql = ('SELECT COUNT(*) FROM officer_discipline WHERE officer_id=%s '
           'AND action_id<>%s AND status IN (' + placeholders + ')')
    still_open = c.execute(sql, (officer_id, action_id) + tuple(DISCIPLINE_OPEN_STATUSES)).fetchone()[0]
    if not still_open:
        c.execute("UPDATE officers SET duty_status='Active' WHERE id=%s AND duty_status='Suspended'", (officer_id,))
```

`DISCIPLINE_OPEN_STATUSES = ('Pending', 'In Review', 'Appealed')` (line 1732), so `len(...) == 3`.

- `'%s' * 3` → `'%s%s%s'` (string repetition)
- `','.join('%s%s%s')` joins the **characters** → `'%,s,%,s,%,s'`
- psycopg2 raises `unsupported format character ',' (0x2c) at index 94` → HTTP 400

**Correct form:** `','.join(['%s'] * len(DISCIPLINE_OPEN_STATUSES))`.

**Operational consequence.** The `Closed` branch is the *only* path that restores
`duty_status='Active'`. It always raises before reaching that `UPDATE`. Therefore **a suspended
officer can never be returned to Active duty through the application.** The suspension is
effectively permanent until someone edits the database by hand.

### Recommendation: handle as a separate HR maintenance task — **yes, with one qualification**

**Yes, it should be a separate task**, because:

- It is a **functional defect in the HR/conduct module**, not a security issue. It belongs on the HR
  work stream, not the security remediation stream, and mixing them muddies both review and rollback.
- It is **independent**: no shared code with any security item, no schema change, no migration.
- It has its own stakeholder (HR Directorate) who should confirm the intended reinstatement rule.

**The qualification — do not let "separate" mean "later".** This is a **one-line fix** with a
**direct effect on a person's employment status**, and it is currently the only thing preventing the
last test suite from running. Its cost is near zero and its impact is high. I recommend it be
authorised as a **standalone, same-week maintenance task**, not deferred into a future HR sprint.

**Estimate:** 0.5 day for the fix; ~1 day for a regression test that suspends an officer, closes the
action and asserts `duty_status` returns to `Active`, plus the multi-action case where another
action is still open and the officer must *stay* suspended.

**Owner approval required** — it is outside every scope authorised so far.

### Verified: this is the sole remaining blocker on `test_server.py`

The Stage 0 report named N-7 as the reason `test_server.py` was blocked. That was **incomplete**.
Running the suite to exhaustion found four *additional* faults ahead of N-7, all of them test-only
(stale fixtures and a stale token). Those have been corrected. With them corrected, N-7 is the
**only** remaining blocker.

The one-line fix was applied temporarily, the suite ran to completion — `ALL BACKEND TESTS PASSED` —
and `server.py` was then restored to its committed state (sha256 verified, `git diff` empty). So the
impact of approving this fix is measured, not estimated: **it turns the last blocked suite green.**

Full chain and the reproducible commands: `REMEDIATION_PLAN.md` §5.

---

## 5. S-06 — Credentials: resolved for existing data, open for the first install

> **UPDATE — R-1, 7 November 2026.** The owner has confirmed that **Sentinel has never had an
> operational database before `e7263d7`**; only temporary development and test databases existed.
> **No emergency rotation is required.** The subsection below is retained as the contingency
> analysis. The live part of S-06 is now §5a.

Stage 0 removed the shared default from the **seeding path**. It did not, and could not, change rows
in a database that already exists. If any environment was ever started before `e7263d7`, its nine
seeded accounts still authenticate with `ChangeMe123!`.

**There is a second-order effect worth stating:** those rows are still stored as unsalted SHA-256.
The Stage 0 upgrade-on-login path rewrites a hash only when the user **successfully signs in**. An
account nobody uses keeps its weak hash indefinitely — and the weak hash is for a **publicly known
password**.

Full procedure in `security/CREDENTIAL_ROTATION_PROCEDURE.md` — **retained as contingency**, in
case a forgotten environment surfaces.

### 5a. The live residual — the next installation

R-1 removes an emergency. **It relocates the problem rather than removing it:** the first database
that matters is the next one created, and that path is defective.

**Verified safe (executed, `test_password_security.py` 15/15):** no default password constant in
source; nine **distinct** random passwords; `ChangeMe123!` refused on every account; credentials
disclosed once to a `0600` file.

**Verified unsafe — two new findings:**

- **S-12** — `bootstrap_password_for()` (`server.py:3489`) returns `SENTINEL_BOOTSTRAP_PASSWORD`
  unchanged **for every username**. Set it, and all nine accounts share one password. Silently.
- **S-13** — the first-run block (`server.py:3302`) seeds nine demonstration personas **and**
  demonstration records into any empty database, including **one `'Active alert'` suspect alert
  against a fictional person**. Because of **S-03**, that alert can never be cleared. There is no
  production initialization mode.

Remediation: **P0-WP-3** (`P0_WORK_PACKAGES.md` §4), approvals **A-16…A-19**. Operator runbook:
`security/PRODUCTION_INITIALIZATION.md`.

---

## 6. Summary of what blocks Release 1.0

> **⚠ Reordered.** Four authorization defects — **S-16a, S-16b, S-14, S-15** — plus the checkpoint
> findings (**H-2b**) are **one defect class**: module, branch and checkpoint-location scope each
> return a falsy value for both "unrestricted" and "cannot determine", and every call site reads
> falsy as "allow". They are remediated by one consolidated model (**SEC-0**), not ten patches.
> S-16a and S-14 were proven by execution
> and now sit **ahead of the original P0**. Two are Critical and one of them, **S-16a, needs no
> misconfiguration at all**: a correctly configured officer refused at the front door with 403
> reaches the same data through `GET /api/persons/<id>`. Full plan:
> **`AUTHORIZATION_REMEDIATION_PLAN.md`**.

Release-blocking and still open: **S-16a, S-16b, S-14, S-15, S-04** (authorization — all five now proven by execution), **S-01, S-02, S-03,
S-04, S-07** (HR module), **S-12, S-13** (first production install), plus the carried items
**S-08, S-09, S-10, S-11**, and **H-2b** (checkpoint scope).
**S-05** should be fixed before release but is not itself a gate.
**S-06** is **reduced** by R-1 — no rotation needed; its live residual is S-12/S-13.

| Band | Items | Days |
|---|---|---|
| **SEC** — authorization, **first** | **SEC-0** unified model · **SEC-1** S-16a/b · **SEC-2** S-14 · **SEC-3** S-15 · **SEC-4** H-2b/checkpoint · **SEC-5** staging diagnostics | **10–16** |
| **SS-1** — station safeguards, **separate, awaiting approval** | G-a…G-d | 1–2 |
| **P0** — approve now | S-07, S-02, (S-06 residual + S-12 + S-13) | 5–6.5 *(7–9.5 with A-11a/A-13)* |
| **P1** — release-blocking | S-01, S-03, S-04, S-05, S-08, S-09 | 23–37 |
| **P2** — before deployment | S-10 *(D-04)*, S-11, full lifecycle *(D-23)* | 34–57 |

**Ordering constraint:** **SEC-1 → SEC-2 → SEC-3 → A-18.** Implementing A-18 first would remove the
`police_station` branch rows, leaving `/api/crimes` with no `WHERE` clause — converting an
accidental fail-closed into disclosure of the whole crime register.

**Nothing in this register has been fixed.** This document is investigation and design only. P0 is
specified to implementation detail in `P0_WORK_PACKAGES.md` and awaits approvals **A-10, A-11,
A-16…A-19**; the SEC packages await approval of `AUTHORIZATION_REMEDIATION_PLAN.md`.
