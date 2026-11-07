# P0 Work Packages — for owner approval

**Date:** 7 November 2026 · **Status:** **AWAITING APPROVAL — NOT IMPLEMENTED**
**Scope:** the three Priority 0 items from `REMEDIATION_PLAN.md` §2, specified to implementation
detail so you can approve or reject each one on its own.

> No application code has been changed and no migration has been run. `backend/server.py` is
> byte-identical to commit `e7263d7`.

---

## 0. Deviation — P0.1 changed, and you should know why

**The P0.1 I originally proposed was "credential rotation assessment". Your R-1 answer discharges
it.** There is no operational database, so there is nothing to rotate. Keeping it as a work package
would be billing you for work your own answer eliminated.

I have **replaced** it with the work your R-1 follow-ups actually require — production
initialization and credential controls (your credential implications 2, 3 and 4). That is a
different work package from the one you approved in principle, so I am flagging it rather than
quietly substituting it.

| | Original P0.1 | Replacement |
|---|---|---|
| Item | S-06 emergency rotation assessment | **P0-WP-3** production init + credential controls |
| Trigger | "does a live database exist?" | R-1 = no → the *next* install is the one that matters |
| Status | **DISCHARGED by R-1** | **NEW — needs your approval** |

**If you would rather I deliver exactly the original three, say so** and I will drop P0-WP-3; the
rotation procedure is already written and retained as contingency.

Two further notes:

- **P0-WP-3 grew.** Investigating your credential items uncovered two findings I had not previously
  recorded: **S-12** (one environment variable gives all nine seeded accounts the *same* password)
  and **S-13** (first run seeds demonstration data into a production database, including a suspect
  alert that cannot be cleared). Both are in §4.
- **These estimates assume one engineer** and exclude review and deployment time.

---

## 1. Summary

| WP | Finding | Severity | Files | DB change | Days |
|---|---|---|---|---|---|
| **P0-WP-1** | S-07 / N-7 — disciplinary action cannot be closed | High (operational) | `backend/server.py` (1 line) | **None** | 1.5 |
| **P0-WP-2** | S-02 / H-5 — admin password reset leaves sessions alive | High (security) | `backend/server.py` (~12 lines) | **None** | 1.5–2 |
| **P0-WP-3** | S-06 residual, S-12, S-13 — production initialization | High (security) | `backend/server.py`, docs | **None** | 2–3 |
| | | | | **Total** | **5–6.5** |

**No work package in P0 changes the database schema.** That is deliberate: P0 should be approvable
without a migration decision.

---

## 2. P0-WP-1 — N-7: closing a disciplinary action

### Finding and severity
**S-07 / N-7.** **High**, operational rather than security. Release-blocking for the HR module.

Closing a disciplinary action returns HTTP 400. The `Closed` branch is the **only** code path that
restores `duty_status` to `'Active'`, so **a suspended officer can never be reinstated through the
application.** This has a direct effect on a named person's employment.

### Exact files affected
- `backend/server.py` — **line 6828**, inside `update_discipline()` (defined at line 6778). One line.
- `backend/test_server.py` — the assertion at line 1015 already covers it and currently fails.
- `backend/test_officer_discipline.py` — **new file**, the dedicated regression suite.

Verified unique: `grep -n "join('%s' \*" server.py vehicles.py` returns **only** line 6828. This
bug pattern exists nowhere else in the codebase.

### Proposed change

```python
# backend/server.py:6828, in update_discipline()
- placeholders = ','.join('%s' * len(DISCIPLINE_OPEN_STATUSES))
+ placeholders = ','.join(['%s'] * len(DISCIPLINE_OPEN_STATUSES))
```

`'%s' * 3` is the string `'%s%s%s'`; `','.join()` then joins it **per character**, producing
`'%,s,%,s,%,s'`. psycopg2 reads `%,` as a format specifier and raises
`unsupported format character ',' (0x2c) at index 94` → HTTP 400. Wrapping in a list produces the
intended `'%s,%s,%s'`.

### Database impact
**None.** No schema change, no migration, no data change. The statement is a `SELECT COUNT(*)` that
never executed successfully, so no incorrect data was ever written by it.

### Acceptance criteria

| # | Criterion |
|---|---|
| AC-1 | `PATCH` a disciplinary action to `Closed` returns **200**, not 400 |
| AC-2 | With no other open action, the officer's `duty_status` returns to `'Active'` |
| AC-3 | With another action still open (`Pending`/`In Review`/`Appealed`), the officer **stays** `'Suspended'` |
| AC-4 | An officer who is `Terminated` or `Retired` is **not** reactivated |
| AC-5 | `test_server.py` runs to completion: **ALL BACKEND TESTS PASSED** |
| AC-6 | Full suite: **29 PASS / 0 FAIL / 0 BLOCKED** |

AC-3 is the one that matters most. It is the case a careless fix breaks, and it would wrongly
return a genuinely suspended officer to duty.

### Tests

**Positive**
1. Suspend an officer → confirm `duty_status == 'Suspended'` → close the action → assert **200** and
   `duty_status == 'Active'`.
2. Close an action of a type that never suspended anyone → assert 200 and `duty_status` unchanged.

**Negative (security / correctness controls)**
3. **Two open actions**, close one → assert the officer **remains** `'Suspended'`. *This is the
   negative control: it must fail against a naive fix that drops the "still open" check.*
4. `Terminated` officer, close an action → assert `duty_status` stays `'Terminated'`.
5. An officer without HR permission attempts the close → **403**, `duty_status` unchanged.
6. **Pre-fix negative control:** run the new suite against the unfixed line and confirm it **fails**
   with the 400. Per standing instruction, a regression test that was never seen to fail proves
   nothing.

### Rollback
`git revert` the commit, or restore the single line. **Zero data risk** — nothing persistent
changes. Rollback restores the current broken behaviour exactly.

### Estimate
**0.5 day** fix · **1 day** regression suite incl. the negative controls → **1.5 days**.

---

## 3. P0-WP-2 — H-5: revoke sessions on administrator password reset

### Finding and severity
**S-02 / H-5.** **High**, security. Release-blocking.

`PATCH /api/admin/users/<id>` updates `password_hash` and **nothing else**. There is no reference to
`sessions` or `TOKENS` anywhere in the handler. An administrator resetting a compromised officer's
password does **not** sign the attacker out — the session token is independent of the password.
Combined with **S-08** (no session expiry), the attacker's session never ends.

This is the precise scenario the control exists for: the reset is what an administrator does *first*
after a suspected compromise, and today it does not work.

### Exact files affected
- `backend/server.py` — the `PATCH /api/admin/users/<id>` handler at **lines 9931–10019**;
  change inside the `if sets:` block at **lines 10011–10017**. ~12 lines added.
- `backend/test_password_security.py` — **tighten `test_15`** (line ~370), which currently *records*
  the exposure and auto-skips when it is fixed.

Helper already exists — Stage 0 built it for N-8, so no new primitive is needed:

```python
revoke_user_sessions(conn, user_id, keep_token=None)   # server.py:4224
```

It clears the in-process `TOKENS` cache **and** deletes the `sessions` rows. Both are required:
`require_auth()` consults `TOKENS` before the table, which is exactly why a bare
`DELETE FROM sessions` is insufficient (finding N-8).

### Proposed change

```python
# backend/server.py, inside `if sets:` (currently lines 10011-10017)
  if sets:
      columns = list(sets.keys())
      values  = [sets[col] for col in columns]
      c.execute(f"UPDATE users SET {', '.join(c + '=%s' for c in columns)} WHERE id=%s",
                (*values, int(uid)))
      audit(c, user, 'UPDATE', 'user', uid,
            'changed fields: ' + ', '.join(columns))
+     # H-5: an administrator reset must END the target's sessions. The token
+     # is independent of the password, so without this a stolen session
+     # survives the reset that was meant to stop it. No keep_token: unlike
+     # the self-service change, the administrator is not the account owner.
+     if 'password_hash' in sets or sets.get('active') == 0:
+         revoke_user_sessions(c, int(uid))
+         audit(c, user, 'REVOKE_SESSIONS', 'user', uid,
+               'all sessions revoked: '
+               + ('password reset by administrator'
+                  if 'password_hash' in sets else 'account deactivated'))
```

Two deliberate choices:

- **No `keep_token`.** The self-service path keeps the caller's own session; here the caller is a
  *different* person, so every one of the target's sessions must go.
- **`active == 0` included.** Deactivation already takes effect because `require_auth()` filters on
  `active = 1`, so this is belt-and-braces — but it makes the audit trail explicit about when
  sessions ended. **Say so if you want this half dropped**; the password half is the security fix.

### Database impact
**None** — no schema change. Row-level effect only: `DELETE FROM sessions WHERE user_id=…`, plus one
new `audit_events` row per reset. Both tables already exist.

### Acceptance criteria

| # | Criterion |
|---|---|
| AC-1 | After an administrator reset, the target's pre-existing token returns **401** |
| AC-2 | The target can sign in with the new password |
| AC-3 | The old password returns 401 |
| AC-4 | **The administrator's own session is unaffected** |
| AC-5 | **Other users' sessions are unaffected** |
| AC-6 | An `audit_events` row records the revocation, the actor and the target |
| AC-7 | A PATCH that does *not* change the password leaves the target's sessions **alive** |
| AC-8 | `test_15` asserts 401 — the `skipTest` escape is removed |
| AC-9 | Full suite stays green |

AC-7 is the guard against over-correction: editing a display name must not sign an officer out.

### Tests

**Positive**
1. Victim signs in → administrator resets → victim's old token → **401**.
2. Victim signs in with the new password → 200.
3. An `audit_events` row exists with action `REVOKE_SESSIONS` and the correct actor and target.

**Negative (controls)**
4. **Administrator's own session survives** their own action → 200. *Catches a revoke that is too
   broad.*
5. **A third user's session survives** → 200. *Catches `DELETE FROM sessions` with no `WHERE`.*
6. **Display-name-only PATCH → victim's session stays alive** (200). *Catches revoking on every
   update.*
7. **Cache-level control:** victim holds **two** tokens; after the reset **both** are 401. *This is
   the N-8 control — it fails if only the database rows are deleted and `TOKENS` is left populated.*
8. **Pre-fix control:** run the tightened `test_15` against unfixed code and confirm it fails with
   `200 != 401`.

### Rollback
`git revert`. **One caveat, stated plainly:** rollback does not restore sessions that were already
revoked. Affected officers sign in again. No data loss; the rollback is operationally safe but not
invisible.

### Estimate
**1 day** implementation · **0.5–1 day** tests incl. the two-token and pre-fix controls →
**1.5–2 days**.

---

## 4. P0-WP-3 — Production initialization and credential controls

### Finding and severity

Three related items, all consequences of R-1 being *no*: the **next** database created is the one
that matters.

| ID | Finding | Severity |
|---|---|---|
| **S-06** (residual) | No emergency rotation needed, but no documented production initialization exists either | **High** |
| **S-12** *(new)* | `SENTINEL_BOOTSTRAP_PASSWORD` gives **all nine** seeded accounts the **same** password | **High** |
| **S-13** *(new)* | First run seeds demonstration **data** into any empty database, including an **un-clearable suspect alert** | **High** |

**S-12** — `bootstrap_password_for()` (line 3489) returns the environment value *unchanged for every
username*. The per-account random generation only happens when the variable is **unset**. The test
runner sets it to `ChangeMe123!` by design; an operator who copies that into production recreates
the shared-credential defect Stage 0 removed. The protection is real but **opt-out by a single
environment variable, with no warning.**

**S-13** — the seed block at line 3302 fires whenever `users` is empty. It creates nine fictional
officers (`'Officer A. Hassan'`, badge `ADM-101`, …) **and** demonstration records:

| Table | Rows |
|---|---|
| `persons` | 3 fictional citizens **with national ID numbers** |
| `crime_cases` | 2 |
| **`suspect_alerts`** | **1 — `'Active alert'` against P-0002** |
| `clearance_applications` | 1 |
| `checkpoint_events` | 1, `screening_result = 'Flagged match'` |
| `airport_passengers` | 1 |

**There is no production mode.** A real deployment starts with a fictional person flagged as a
suspect — and because of **S-03**, that alert **can never be cleared through the application.** A
demonstration fixture becomes permanent operational data.

### Exact files affected
- `backend/server.py` — seed block **lines 3302–3323** (accounts) and **3324–~3395** (demo data);
  `bootstrap_password_for()` **line 3489**.
- `.env.example` — document `SENTINEL_BOOTSTRAP_PASSWORD` and the new mode flag.
- `README.md`, `backend/README.md`, `TESTING.md` — initialization instructions.
- `backend/test_password_security.py` — extend for S-12.
- `backend/test_production_init.py` — **new**.

### Proposed change

**(a) Separate demonstration seeding from initialization.** Introduce `SENTINEL_SEED_DEMO_DATA`,
defaulting to **off**:

```
SENTINEL_SEED_DEMO_DATA unset / '0'  -> PRODUCTION: create ONLY the administrator account.
                                        No demo persons, cases, alerts or checkpoint events.
SENTINEL_SEED_DEMO_DATA = '1'        -> DEMONSTRATION: current behaviour, unchanged.
```

The test runner sets it to `1`, so every existing suite keeps its fixtures.

**Default-off is the whole point.** An operator who does nothing gets a clean database. Today an
operator who does nothing gets a fictional suspect alert.

**(b) Make the shared-password path loud and bounded (S-12).** Keep `SENTINEL_BOOTSTRAP_PASSWORD`
for test use, but in production mode refuse it for multiple accounts and warn:

```python
if os.environ.get(BOOTSTRAP_PASSWORD_ENV) and not demo_mode:
    sys.stderr.write('WARNING: SENTINEL_BOOTSTRAP_PASSWORD is set. The administrator '
                     'account will use it. Change it immediately after first sign-in.\n')
```

In production mode only one account is created, so the shared-credential case cannot arise.

**(c) Document secure production administrator initialization** — new
`security/PRODUCTION_INITIALIZATION.md`, written as an operator runbook: pre-flight checks, the
single administrator account, retrieving the generated password, the mandatory first-time change,
deleting `backend/bootstrap-credentials.txt`, and creating real officer accounts through
`POST /api/admin/users`.

**(d) Identify and control test accounts (your item 3).** The nine seeded personas are
**demonstration fixtures, not real officers**. In production mode they are not created at all. In
demonstration mode the runbook states they must never exist on a production host, and
`test_production_init.py` asserts their absence.

### Database impact
**None.** No schema change. The change is to *which rows are inserted on first run of an empty
database*. **No existing database is modified** — and per R-1 there are none.

### Acceptance criteria

| # | Criterion |
|---|---|
| AC-1 | Default initialization (no env vars) creates **exactly one** user: the administrator |
| AC-2 | Default initialization creates **zero** rows in `persons`, `crime_cases`, `suspect_alerts`, `clearance_applications`, `checkpoint_events`, `airport_passengers` |
| AC-3 | **No `suspect_alerts` row exists after a production initialization** |
| AC-4 | The administrator password is CSPRNG-generated, ≥128 bits, unique per install |
| AC-5 | It is written to stderr and to a `0600` file, once |
| AC-6 | `SENTINEL_SEED_DEMO_DATA=1` reproduces today's behaviour exactly; all existing suites pass unchanged |
| AC-7 | In demonstration mode none of the nine accounts shares a password **unless** `SENTINEL_BOOTSTRAP_PASSWORD` is set, which emits a warning |
| AC-8 | Reference stations and branches **are** still created in production mode (reference data, not demo data) |
| AC-9 | Re-running against a non-empty database changes nothing (idempotent) |
| AC-10 | `PRODUCTION_INITIALIZATION.md` exists and was followed end-to-end on a clean database |

AC-8 is a real decision: stations and branches are operational reference data, not fiction. **Tell
me if you want those excluded too** — I have assumed they should be kept.

### Tests

**Positive**
1. Initialize a clean database with no env vars → exactly one user, role `admin`.
2. Password meets the entropy rule and differs across two separate initializations.
3. The credentials file exists with mode `0600`.
4. `SENTINEL_SEED_DEMO_DATA=1` → all nine accounts and the full demo dataset appear.
5. Reference stations and branches exist in both modes.

**Negative (controls)**
6. **Production init → `SELECT COUNT(*) FROM suspect_alerts` is 0.** *Directly asserts S-13 closed.*
7. **Production init → none of `fp.officer`, `cp.south`, `chief`, … exists.** *Asserts the
   demonstration personas are absent.*
8. **`ChangeMe123!` is refused against every account**, both modes — the existing Stage 0 control,
   retained.
9. **S-12 control:** demonstration mode with `SENTINEL_BOOTSTRAP_PASSWORD` set → assert all nine
   hashes verify against that one password **and** that the warning was emitted. *This test asserts
   the exposure exists and is announced, so the behaviour cannot change silently.*
10. **Idempotence:** run initialization twice → no duplicate users, no second alert.
11. **Pre-change control:** run `test_production_init.py` against current code and confirm it
    **fails** — today a default init creates nine users and a suspect alert.

### Rollback
`git revert`. The change is additive and gated on a new flag; reverting restores demonstration
seeding as the default. **No data migration either way.** Any database already initialized under the
new default is unaffected by a rollback — it simply has fewer rows, which is the desired state.

### Estimate
**1 day** seeding split and the S-12 warning · **0.5 day** runbook · **1–1.5 days** the new suite
and controls → **2–3 days**.

---

## 5. What I need from you

### Approve or reject, per work package

| # | Approval | WP |
|---|---|---|
| **A-10** | Fix N-7 (`server.py:6828`) | P0-WP-1 |
| **A-11** | Revoke sessions on administrator password reset | P0-WP-2 |
| **A-11a** | …also revoke on `active = 0` (§3; drop if you prefer) | P0-WP-2 |
| **A-16** | **NEW** — split demonstration seeding behind `SENTINEL_SEED_DEMO_DATA`, default **off** | P0-WP-3 |
| **A-17** | **NEW** — production init creates **only** the administrator account | P0-WP-3 |
| **A-18** | **NEW** — keep reference stations/branches in production mode (AC-8) | P0-WP-3 |
| **A-19** | **NEW** — retain `SENTINEL_BOOTSTRAP_PASSWORD` with a warning, rather than removing it | P0-WP-3 |

### Also confirm

- **P0-WP-3 replacing the original P0.1** (§0), or tell me to drop it.
- Whether P0 may be implemented **in one branch** or as three reviewable commits. I recommend
  **three commits on one branch** — each is independently revertible.

### Still yours to create

```sh
git branch stage-1-security e7263d7
```

This session is bound to `arena/6303ef2f-sentinel-police-management` and cannot create or push
another branch. **No implementation should start on this branch.**

---

## 6. What P0 does not do

P0 is 5–6.5 days and closes three items. It leaves open, and these stay visible in
`SECURITY_ISSUE_REGISTER.md`:

- **S-01** cross-branch document access — any authenticated officer can read any branch's documents
- **S-03 / S-04** suspect-alert lifecycle — alerts still cannot be cleared
- **S-05** analytics RBAC leak
- **S-08 / S-09 / S-10 / S-11** session expiry, throttling, mutable audit, no TLS

**Completing P0 does not make the system deployable.** S-11 alone (no TLS) makes a networked
deployment unsafe. P0 removes two active harms and one initialization defect; it is a first step,
not a release gate.
