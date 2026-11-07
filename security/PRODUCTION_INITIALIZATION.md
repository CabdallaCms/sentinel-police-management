# Production Initialization and Credential Controls

**Date:** 7 November 2026 · **Status:** **VERIFICATION + PROPOSED RUNBOOK — NOT IMPLEMENTED**
**Answers:** the owner's credential implications 2, 3 and 4 following the **R-1** decision
**Related:** `CREDENTIAL_ROTATION_PROCEDURE.md` (now contingency-only) · `P0_WORK_PACKAGES.md` §4

> §2 reports **executed test results**. §3 reports **verified code reads**. §4 is a **proposed
> runbook that cannot be followed yet** — it depends on approvals A-16/A-17 (P0-WP-3). I have
> marked which parts work today and which do not.

---

## 1. R-1 outcome

**Owner decision (7 November 2026):** Sentinel has never had an operational database before
`e7263d7`. Only temporary development and test databases have existed.

**Consequence — credential implication 1:** no emergency credential rotation is required. No live
account holds `ChangeMe123!`, because no live account exists.

`CREDENTIAL_ROTATION_PROCEDURE.md` is **retained as contingency**, not deleted. It applies if a
forgotten environment surfaces, and §4/§6 of it (rotation via the API, terminating all sessions)
stay useful operational references.

**R-1 removes an emergency. It does not remove the problem** — it relocates it. The first database
that matters is the **next** one created, and the defects in that path are live. That is §3.

---

## 2. Credential implication 2 — no shared defaults in new installations

### Verified by executed tests

`backend/test_password_security.py`, run 7 November 2026 on commit `595ec3b`: **15 tests, 15
passed.** Five bear directly on this question.

| Test | Asserts | Result |
|---|---|---|
| `test_01_no_default_password_constant_in_the_source` | `ChangeMe123!` appears in neither `server.py`, `index.html` nor `migrate_rbac.py` (comments stripped first) | **PASS** |
| `test_02_random_seeding_gives_every_account_a_different_password` | all nine seeded accounts get **distinct** hashes | **PASS** |
| `test_03_the_retired_default_password_no_longer_works` | `ChangeMe123!` is refused on every account | **PASS** |
| `test_04_generated_credentials_are_reported_once_and_owner_only` | disclosed once, to stderr and a `0600` file | **PASS** |
| `test_05_explicit_bootstrap_password_is_honoured` | an operator-supplied password is used | **PASS** |

Supporting code, re-read and confirmed:

```python
# backend/server.py:3489
def bootstrap_password_for(username):
    explicit = os.environ.get(BOOTSTRAP_PASSWORD_ENV)
    if explicit:
        return explicit
    return 'Sx-' + secrets.token_hex(16)      # 128 bits, unique per account
```

**Answer: confirmed — with one material exception, below.** In the default path a new installation
has no shared credential: each account gets 128 bits of CSPRNG entropy, hashed with PBKDF2-HMAC-
SHA256 at 600,000 iterations with a unique 16-byte salt.

### The exception — S-12, newly recorded

`bootstrap_password_for()` returns the environment value **unchanged for every username**. The
per-account randomness happens **only when `SENTINEL_BOOTSTRAP_PASSWORD` is unset.**

```
SENTINEL_BOOTSTRAP_PASSWORD unset  ->  9 accounts, 9 different random passwords   (safe)
SENTINEL_BOOTSTRAP_PASSWORD set    ->  9 accounts, ONE shared password            (S-12)
```

`scripts/run-tests.sh` sets it to `ChangeMe123!` — correct for tests, since ~22 suites depend on a
known password. **The risk is an operator copying a test command, or a `.env` file, into
production.** There is no warning and no guard.

This is not a theoretical concern: `.env.example` is the documented way to configure the backend,
and nothing in it tells an operator what this variable does. The protection Stage 0 added is real
but **opt-out via a single environment variable, silently.**

Proposed remedy: approval **A-19** — keep the variable for testing, emit a warning outside
demonstration mode, and in production mode create only one account so the shared case cannot arise.

---

## 3. Credential implication 3 — identifying and controlling test accounts

### What the first run actually creates

`backend/server.py:3302` — whenever the `users` table is empty, **nine accounts** are created
unconditionally. They are demonstration personas with fictional names and badge numbers:

| Username | Display name | Role | Posting |
|---|---|---|---|
| `admin` | Officer A. Hassan | SystemAdmin | Central HQ |
| `fp.officer` | Officer H. Xasan | Fingerprint | Fingerprint Unit |
| `ap.officer` | Officer S. Cabdi | Airport | Airport Control |
| `cid.officer` | Officer M. Nuur | CID | CID Unit |
| `hr.officer` | Officer S. Warsame | HR | HR Directorate |
| `cp.south` | Officer F. Cali | Checkpoint | South Checkpoint |
| `cp.east` | Officer A. Maxamed | Checkpoint | East Checkpoint |
| `cp.west` | Officer N. Yuusuf | Checkpoint | West Checkpoint |
| `chief` | Gen. C. Warsame | Commander | Police HQ / Command |

### And it does not stop at accounts — S-13, newly recorded

The same first-run block (lines 3324 onward) inserts **demonstration records**:

| Table | Rows | Note |
|---|---|---|
| `persons` | 3 | fictional citizens, **with national ID numbers** (P-0001…P-0003) |
| `crime_cases` | 2 | |
| **`suspect_alerts`** | **1** | **`'Active alert'` against P-0002, origin `'Case Link'`** |
| `clearance_applications` | 1 | |
| `checkpoint_events` | 1 | `screening_result = 'Flagged match'` |
| `airport_passengers` | 1 | |

**There is no production initialization mode.** A real deployment begins with a fictional person
listed as an active suspect — and because of **S-03**, no code path can ever change
`alert_status`, so **that alert cannot be cleared through the application.** A demonstration
fixture becomes permanent operational data in the suspect register.

**Answer to implication 3, honestly: the test accounts are currently neither clearly identified nor
controlled.** They are indistinguishable from real accounts in schema and behaviour, they are
created by default, and they arrive with demonstration case data attached.

### Proposed control

Approvals **A-16 / A-17** (P0-WP-3): gate all demonstration seeding behind
`SENTINEL_SEED_DEMO_DATA`, **default off**.

| Mode | Accounts | Demo data | Reference stations/branches |
|---|---|---|---|
| **Production** (default) | `admin` only | **none** | yes (A-18) |
| **Demonstration** (`=1`) | all nine | full set | yes |

Controls that make this checkable rather than assumed:

- `backend/test_production_init.py` asserts **zero** `suspect_alerts` rows and the **absence** of all
  eight non-admin personas after a default initialization.
- The runbook (§4) requires an operator to confirm the account list before go-live.
- `scripts/run-tests.sh` sets `SENTINEL_SEED_DEMO_DATA=1`, so existing suites are unaffected.

---

## 4. Credential implication 4 — secure production administrator initialization

> **This runbook cannot be followed today.** Steps 3–5 depend on the production mode from
> approvals A-16/A-17. Until then, a first run creates nine accounts and a suspect alert.
> Published now so you can approve the procedure and the code change together.

### Pre-flight

| # | Check |
|---|---|
| 1 | PostgreSQL reachable; the target database is **empty** (`SELECT COUNT(*) FROM users` → 0, or no schema) |
| 2 | `SENTINEL_BOOTSTRAP_PASSWORD` is **unset** — `env \| grep SENTINEL_BOOTSTRAP` returns nothing |
| 3 | `SENTINEL_SEED_DEMO_DATA` is **unset** |
| 4 | `.env` contains no value copied from `.env.example` verbatim (`SENTINEL_DB_PASSWORD=change-me`) |
| 5 | The host filesystem is not world-readable; the service account owns the application directory |
| 6 | A backup and a **tested restore** exist before first use |

Step 2 is the one that silently breaks everything else (S-12). Check it explicitly.

### Initialize

```sh
# 1. Confirm no credential override is in the environment
env | grep -E 'SENTINEL_(BOOTSTRAP_PASSWORD|SEED_DEMO_DATA)'     # must print nothing

# 2. Start the backend once against the empty database
python3 backend/server.py
```

The server creates the schema, reference stations and branches, and **exactly one** account:

```
========================================================================
SENTINEL FIRST-RUN CREDENTIALS - shown once, store them now
Generated 2026-11-07T...
Change every password after first sign-in, then delete this file.

  admin        Sx-<32 hex characters>

Saved to: backend/bootstrap-credentials.txt
========================================================================
```

### Secure the administrator account

| # | Step |
|---|---|
| 1 | Record the password in the organisation's password manager — **not** in a file, email or chat |
| 2 | Sign in as `admin` and **immediately** change the password via `POST /api/me/password` |
| 3 | Verify the generated password no longer works |
| 4 | **Delete `backend/bootstrap-credentials.txt`** — it is `0600` and gitignored, but it is still a plaintext credential on disk |
| 5 | Confirm `SELECT COUNT(*) FROM users` is **1** |
| 6 | Confirm `SELECT COUNT(*) FROM suspect_alerts` is **0** |

Steps 5 and 6 are the acceptance check for S-13. If either is wrong, demonstration seeding ran —
stop, drop the database, and restart from pre-flight.

### Create real officer accounts

Create every officer through `POST /api/admin/users` with a unique password per officer, delivered
over a secure channel. **Never** by direct SQL — that bypasses PBKDF2 hashing and the audit trail,
and an incorrectly formatted hash silently locks the account out.

### Residual weaknesses at go-live

State these in the deployment record rather than discovering them later:

| ID | Weakness | Effect |
|---|---|---|
| **S-02** | Password reset does not end sessions | Until P0-WP-2, a compromised session survives a reset |
| **S-08** | No session expiry | A token is valid indefinitely |
| **S-09** | No throttling or lockout | Passwords can be guessed without limit |
| **S-11** | No TLS | **Credentials cross the network in clear text** |
| — | The login page enumerates usernames | Valid usernames are discoverable |
| — | No forced password change on first sign-in | Step 2 above is procedural, not enforced (M-03 / A-9) |

**S-11 is decisive. Do not expose this system to a network until TLS terminates in front of it.**
Everything else in this runbook is undone by credentials sent in clear text.

---

## 5. Summary

| Implication | Status |
|---|---|
| 1. No emergency rotation needed | **Confirmed** by R-1. Procedure retained as contingency |
| 2. No shared defaults in new installations | **Verified by 15 executed tests** — with exception **S-12** (`SENTINEL_BOOTSTRAP_PASSWORD` shares one password across all nine) |
| 3. Test accounts identified and controlled | **Not met today.** Nine personas plus demo data — including an un-clearable suspect alert (**S-13**) — are created by default. Remedy proposed as A-16/A-17 |
| 4. Secure production admin initialization | **Documented** in §4. **Requires A-16/A-17 before it can be followed** |

Two new findings, **S-12** and **S-13**, are recorded in `SECURITY_ISSUE_REGISTER.md` and
remediated by **P0-WP-3**.
