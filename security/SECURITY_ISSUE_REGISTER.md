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
| **S-04** | **Suspect alerts carry no `branch_id`** (N-1), so alerts are unscoped across branches. | **Medium** | **YES** (coupled to S-03) | **OPEN** | `suspect_alerts` DDL line 299 — no branch column |
| **S-05** | **Analytics RBAC leak** (N-3). `crimes` acts as a skeleton key: `cid.officer` receives vehicle and station analytics it has no module for; the CID bundle is ungated entirely. | **Medium** | No — fix before release, not a gate | **OPEN** | Root cause isolated, §3 |
| **S-06** | **Existing databases still hold `ChangeMe123!` credentials.** Stage 0 stopped *new* installations being seeded that way; it did not rotate anything already deployed. | **High** *(if any environment exists)* | **YES** if any environment exists | **OPEN — operational** | WP-02 changed seeding only; no row was rewritten |
| **S-07** | **N-7 — closing a disciplinary action is impossible**, so a suspended officer can never be returned to Active duty. Functional defect with a direct human consequence. | **High** (operational, not security) | **YES** for the HR module | **OPEN** | `server.py:6828`, `','.join('%s' * n)` → `'%,s,%,s,%,s'` |
| S-08 | No session expiry (H-3) | High | YES | OPEN — not investigated this round | Carried from the Phase 2 register |
| S-09 | No authentication throttling or auth audit (H-4) | High | YES | OPEN — not investigated this round | Carried |
| S-10 | Mutable audit log (H-7) | High | YES — needs decision D-04 | OPEN | Carried |
| S-11 | No TLS (H-8) | High | YES | OPEN — deployment concern | Carried |

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

## 5. S-06 — Existing-database credentials

Stage 0 removed the shared default from the **seeding path**. It did not, and could not, change rows
in a database that already exists. If any environment was ever started before `e7263d7`, its nine
seeded accounts still authenticate with `ChangeMe123!`.

**There is a second-order effect worth stating:** those rows are still stored as unsalted SHA-256.
The Stage 0 upgrade-on-login path rewrites a hash only when the user **successfully signs in**. An
account nobody uses keeps its weak hash indefinitely — and the weak hash is for a **publicly known
password**.

Full procedure in `security/CREDENTIAL_ROTATION_PROCEDURE.md`.

---

## 6. Summary of what blocks Release 1.0

Release-blocking and still open: **S-01, S-02, S-03, S-04, S-06** (if any environment exists),
**S-07** (HR module), plus the carried items **S-08, S-09, S-10, S-11**.

**Nothing in this register has been fixed.** This document is investigation and design only.
