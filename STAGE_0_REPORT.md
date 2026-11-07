# Stage 0 Implementation Report

**Date:** 7 November 2026
**Branch:** `arena/6303ef2f-sentinel-police-management`
**Commit:** `e7263d7` (parent `a9096c8`; application code baseline `a1c2478`)
**Scope:** the five items the owner authorised, and nothing else
**Status:** complete · **Stage 1 has NOT been started**

---

## 0. Read this first — two things you must know before the detail

### 0.1 The branch instruction could not be followed exactly

You asked for the work to be done on **a separate, clearly identified implementation branch**.

This session is permanently bound to `arena/6303ef2f-sentinel-police-management` and is technically
prevented from creating, switching to, or pushing any other branch. I could not create a branch
named, for example, `stage-0-security`.

**What I did instead:** all work is on `arena/6303ef2f-sentinel-police-management`. That branch is
separate from `main`, clearly identified, and **has not been merged into anything**.

**What this means for you:**

- `main` is untouched — still at `a1c2478`, verified after the push.
- The audit history is intact; nothing was rewritten.
- PR #23 and branch `arena/8834f56d-…` were not touched (re-verified: OPEN, draft).
- If you want a differently named branch, you can create it from `e7263d7` yourself:
  `git branch stage-0-security e7263d7`.

I am flagging this at the top rather than burying it, because it is a deviation from an explicit
instruction.

### 0.2 One authorised item is only partly closed, and I am not calling it done

Item 5 was "upload validation **and** prevent unauthorised access to uploaded documents."

- **Upload validation: fully closed.**
- **Unauthorised access: the anonymous hole is closed, the cross-branch hole is not.**

Any *authenticated* officer can still read any uploaded document, including one belonging to another
branch. Closing that requires linking each stored file to its owning record, which does not exist
today because documents are stored as JSON blobs inside the owning row (finding N-6). That is a
**schema change**, and you instructed that database structures must not change without approval. So
I stopped, wrote a test that asserts the exposure out loud, and am reporting it here.

Details in §6.

---

## 1. Summary

| # | Item authorised | Work package | Outcome |
|---|---|---|---|
| 1 | Reproducible test environment | WP-01 | **Done** |
| 2 | Remove fabricated biometric-match behaviour | WP-45g | **Done** |
| 3 | Eliminate seeded default credentials | WP-02 | **Done** |
| 4 | Secure password hashing | WP-03 | **Done** |
| 5 | Upload validation + prevent unauthorised document access | WP-09 / WP-08 | **Validation done. Authentication done. Cross-branch authorisation NOT done — see §0.2 and §6** |

### Test position — measured, not estimated

| Run | Suites | PASS | FAIL | BLOCKED | SKIP |
|---|---|---|---|---|---|
| Baseline, before any change (`a1c2478`) | 25 | 23 | 2 | 0 | 0 |
| After Stage 0 (`e7263d7`) | **28** | **27** | **0** | **1** | 0 |

The single BLOCKED suite is `test_server.py`, stopped by **N-7**, a genuine application defect that
is outside the authorised scope. **BLOCKED is not a pass**, and the runner exits non-zero for it.

### Two new application defects found

Making the suite runnable exposed two real defects that were invisible before:

- **N-7 — reported, deliberately not fixed.** Closing a disciplinary action fails, so **a suspended
  officer can never be returned to Active duty**. HR/conduct is not one of the five items.
- **N-8 — fixed.** A password change did not actually sign other sessions out. This is inside item 4:
  a password change that leaves the attacker logged in is not a working password change.

---

## 2. WP-01 — Reproducible test environment

**1 · Files changed**
`requirements.txt` (new), `requirements-dev.txt` (new), `package.json` (new),
`scripts/run-tests.sh` (new), `backend/pg_test_env.py` (new),
`backend/test_server.py` (harness repair, +323/−…), `backend/test_conduct_frontend.mjs` (harness
repair), `backend/test_checkpoint_roles_audit.py` (one call renamed), `.gitignore`, `TESTING.md`.

**2 · Exact problem corrected**
There was no dependency manifest anywhere in the repository — no `requirements.txt`, no
`package.json` (finding M-10). 23 of 25 suites could not be executed at all. Separately,
`test_server.py` and `test_conduct_frontend.mjs` still passed the **retired** `SENTINEL_DB=<sqlite
file>` convention, so the PostgreSQL server never started and both timed out on a health check.
They were never "broken tests" — they were obsolete harnesses.

**3 · Before and after**

| | Before | After |
|---|---|---|
| Install path | none documented or pinned | `pip install -r requirements-dev.txt` + `npm install` |
| Suites runnable | 2 of 25 | 28 of 28 |
| Full-suite command | did not exist | `scripts/run-tests.sh` |
| Result reporting | n/a | PASS / FAIL / SKIP / **BLOCKED**, with the reason printed |

Verified from scratch: after the sandbox discarded `.venv/` and `node_modules/`, both were rebuilt
from the manifests alone in about 7 seconds, and the full suite then ran.

**4 · Tests executed and actual results**
Full suite, twice. Final: **27 PASS / 0 FAIL / 1 BLOCKED / 0 SKIP** in ~83 s.
Baseline for comparison, captured before any change: **23 PASS / 2 FAIL**.

**5 · Security verification evidence**
Partly satisfies **SR-90 / AC-T1** (a suite that actually executes). This is infrastructure, so the
evidence is the executed tally itself. Each suite provisions a throwaway PostgreSQL cluster via
`pgserver`: **no test touches an operational database, and every fixture is synthetic.**

**6 · Tests that remain blocked**
`test_server.py` — blocked by **N-7** (§7). It runs the whole suite and stops at line 1013.

**7 · Database / migration impact**
**None.** No DDL, no migration. Test databases are created and destroyed per suite.

**8 · Rollback**
`git revert e7263d7`, or delete the four new files and `git checkout a9096c8 -- backend/test_server.py
backend/test_conduct_frontend.mjs`. No runtime effect — nothing here ships with the application.

### Honesty note on the harness repair

I corrected five **stale test expectations** and did **not** weaken any assertion:

- Three checkpoint-role expectations still used the retired `CheckpointSouth/East/West` roles; the
  canonical `checkpoint_officer` is correct.
- Two station-analytics fixtures predated the Branch Management feature, which mirrors branches into
  the station registry (8 → 10 stations).
- One expectation was **tightened**, not relaxed: `fp.officer` requesting `/api/analytics?module=vehicles`
  was expected to return 200, but the server correctly returns 401 because `ROLE_MODULES` does not
  grant that role the vehicles module. I changed the **test** to match the stricter server.
- One legacy sub-test (`audit_instant_approvals.py`, SQLite-only, pre-PostgreSQL, unused) is now
  skipped behind an explicit opt-in and prints **SKIP**. It is never reported as passing.

---

## 3. WP-45g — Removal of fabricated biometric matching

**1 · Files changed**
`index.html` (matcher at line 4536 and two caller paths),
`backend/test_biometric_no_fabricated_match.mjs` (new, 9 checks).

**2 · Exact problem corrected**
`matchPersonByFingerprint()` accepted a third argument `allowFallbackScan`. When every real
comparison failed, it executed:

```js
const captured = list.filter(p => ...status === 'captured');
const pool     = captured.length ? captured : list;
const idx      = (window._bioScanCursor || 0) % pool.length;
window._bioScanCursor = idx + 1;
return pool[idx] || list[0];
```

It returned an **arbitrary person** by rotating a cursor through the registry. Four call sites passed
`true` — including the live-scan and Central Person Registry paths — and then announced the result as
**"⚡ Biometric Fingerprint Match Found — Linked to Central Person Record #…"**.

At a checkpoint, that is a wrongful-identification path, and therefore a wrongful-detention path.

**3 · Before and after — measured on the same unknown fingerprint, submitted six times**

```
BEFORE (pre-fix index.html)          AFTER (e7263d7)
  attempt 1: P-0001 Ayaan Cabdi…       attempt 1: null
  attempt 2: P-0002 Maxamed Nuur…      attempt 2: null
  attempt 3: P-0003 Sahra Yuusuf…      attempt 3: null
  attempt 4: P-0001 Ayaan Cabdi…       attempt 4: null
  attempt 5: P-0002 Maxamed Nuur…      attempt 5: null
  attempt 6: P-0003 Sahra Yuusuf…      attempt 6: null
```

**One unknown print identified three different citizens in rotation.** It now returns no match,
every time. The parameter, the fallback and the cursor are gone; the only outcomes are a real
comparison hit or `null`.

Additionally, the two "simulate scan" paths previously returned **silently** on no-match, leaving the
officer with no feedback. They now display an explicit no-match warning stating that no identity has
been assigned.

**4 · Tests executed and actual results**
`node backend/test_biometric_no_fabricated_match.mjs` → **9/9 ok, exit 0**:

1. no `allowFallbackScan`, `_bioScanCursor` or `pool[idx]` in executable code
2. matcher arity is exactly 2 (no re-added opt-in flag)
3. unknown probes return `null`
4. **ten successive identical unknown probes all return `null`** (the anti-rotation guard)
5. empty and null probes match nobody
6. genuine matches still work (hash, national ID, biometric filename)
7. unknown probe with **no captured biometrics in the registry** still returns `null` (the old code
   fell back to the whole person list in exactly this case)
8. a failed scan reports "no match" and assigns no identity
9. a failed scan leaves no person selected

**5 · Security verification evidence — your explicit requirement**
You asked for proof that *no unavailable or failed matching operation can produce an arbitrary
successful identity match.* Evidence:

- **Negative control:** the new suite was run against the **pre-fix** `index.html` and **failed**
  (`AssertionError: the allowFallbackScan parameter must be gone`). The test genuinely detects the old
  behaviour — it is not vacuously passing.
- Check 4 is the direct proof: a rotating fallback returns *different people* on successive calls;
  ten identical probes all returning `null` is incompatible with any rotation.
- Check 7 covers the "matching unavailable" case — no biometrics captured at all — which is precisely
  when the old code was most dangerous.
- Addresses **SR-22**; **FPR-901 (genuine matching) remains open** and is unfunded pending D-31/32/33/34.

**6 · Tests that remain blocked**
None for this work package. **FPR-901 is not blocked — it is not started**, by instruction.

**7 · Database / migration impact**
**None.** The `localStorage` biometric store (WP-45a) was deliberately left untouched — out of scope.

**8 · Rollback**
`git checkout a9096c8 -- index.html`. **Not recommended:** it restores the fabricated-match path.

---

## 4. WP-02 — Seeded default credentials eliminated

**1 · Files changed**
`backend/server.py` (seed block; new `bootstrap_password_for()` 3489, `report_bootstrap_credentials()` 3502),
`index.html` (login screen + role-shortcut buttons), `backend/migrate_rbac.py`,
`README.md`, `backend/README.md`, `TESTING.md`, `.gitignore`,
`backend/test_password_security.py` (new).

**2 · Exact problem corrected**
Nine seeded accounts — **including `admin` and `chief`** — were all created with the same hard-coded
password `ChangeMe123!`. The login screen **displayed it in plain text**, and the role-shortcut
buttons **auto-filled it and submitted the form**. Anyone who could load the page was one click from
an administrator session (finding C-2).

**3 · Before and after**

| | Before | After |
|---|---|---|
| Seeded password | `ChangeMe123!`, identical for all nine | `SENTINEL_BOOTSTRAP_PASSWORD`, or a distinct random password per account |
| Shown on login screen | yes, in plain text | no |
| Shortcut buttons | filled the password and submitted | fill the username only, then focus the password field |
| Operator disclosure | none needed — it was public | printed once to stderr and written to a `0600` file, to be deleted after first sign-in |
| In the source tree | 9 occurrences in `server.py`, 2 in `index.html`, plus docs | none |

**4 · Tests executed and actual results**
`backend/test_password_security.py` → **15/15 OK**. Relevant tests:

- `test_01` — the retired constant is absent from `server.py`, `index.html` and `migrate_rbac.py`
  (comments stripped first, so the documentation of the removal is not mistaken for the constant)
- `test_02` — with no bootstrap password, all nine accounts get **distinct** hashes
- `test_03` — **all nine accounts reject `ChangeMe123!` with 401**
- `test_04` — the credentials file exists, is mode **`0600`**, lists all nine accounts, each password
  is distinct, and the reported password actually works
- `test_05` — an explicitly supplied password works, the retired one does not, and a password the
  operator chose is **never** echoed to disk

**5 · Security verification evidence**
Two independent server instances were booted against separate databases — one with
`SENTINEL_BOOTSTRAP_PASSWORD` set, one without — and both paths were exercised over real HTTP.
This is runtime evidence, not code inspection. Addresses **SR-02 / finding C-2**.

**6 · Tests that remain blocked**
None.

**7 · Database / migration impact**
**None.** No DDL. Behaviour applies to first-run seeding only; existing user rows are not modified.
**Operational note:** an already-deployed database still contains accounts whose password is
`ChangeMe123!`. This change prevents *new* installations from being seeded that way — **it does not
retroactively rotate existing credentials.** If any environment already exists, every seeded password
must be changed manually. I have not done this, and no environment is known to exist.

**8 · Rollback**
`git checkout a9096c8 -- backend/server.py index.html backend/migrate_rbac.py`. **Not recommended.**
To keep the fix but retain a known password, set `SENTINEL_BOOTSTRAP_PASSWORD`.

---

## 5. WP-03 — Secure password hashing

**1 · Files changed**
`backend/server.py` — `hash_password()` 3391, `verify_password()` 3407, `password_needs_upgrade()`,
`upgrade_password_hash()` 3446, `revoke_user_sessions()` 4224; login, self-service change, admin
create and admin PATCH call sites. `backend/migrate_rbac.py`, `README.md`,
`backend/test_password_security.py` (new), `backend/test_checkpoint_roles_audit.py` (one call renamed).

**2 · Exact problem corrected**
Passwords were stored as `hashlib.sha256(value.encode()).hexdigest()` — a bare, **unsalted,
single-round** digest (finding C-3). That is an *encoding* of the password, not a password hash:
GPU-crackable at billions of guesses per second, and because it is unsalted, two officers with the
same password share a digest and the table falls to one rainbow-table lookup. Login also compared it
**inside a SQL predicate** (`WHERE username=%s AND password_hash=%s`), so the comparison was not
constant-time.

**3 · Before and after**

| | Before | After |
|---|---|---|
| Algorithm | SHA-256, 1 round, no salt | **PBKDF2-HMAC-SHA256, 600,000 iterations** |
| Salt | none | 16 random bytes per password |
| Stored form | 64 hex chars | `pbkdf2_sha256$600000$<b64 salt>$<b64 key>` |
| Comparison | SQL equality | `hmac.compare_digest`, constant time |
| Username enumeration | timing difference on unknown users | dummy verification equalises the work |
| Legacy rows | n/a | accepted **once**, then transparently re-hashed |
| Dependencies added | — | **none** (standard library, per decision D-03) |

Measured cost: ~0.23 s per hash on this machine, applied once per login.

**4 · Tests executed and actual results**
`backend/test_password_security.py` → **15/15 OK**:

- `test_06` — no stored hash is a bare 64-hex SHA-256 digest
- `test_07` — every hash is `pbkdf2_sha256` with **≥ 600,000** iterations and a ≥16-byte salt
- `test_08` — nine accounts sharing the **same** password have **nine different hashes** (direct proof of salting)
- `test_09` — a legacy SHA-256 row authenticates once, is rewritten to PBKDF2 in place, still works
  afterwards, and the old digest is **not** accepted as a password
- `test_10` — wrong, empty, whitespace, case-shifted, truncated and SQL-injection-shaped passwords all 401
- `test_11` — **the stored hash is not accepted as the password** (no pass-the-hash)
- `test_12` — unknown username and wrong password return **identical** status and body
- `test_13` — the correct password still authenticates and `/api/me` returns 200

**5 · Security verification evidence — your explicit requirement**
You asked for coverage of *seeded accounts, password verification, and existing-session implications.*

- **Seeded accounts:** §4, tests 01–05.
- **Password verification:** tests 10–13, including pass-the-hash and enumeration.
- **Existing sessions:** test_14 and test_15, below.

**N-8 — a new defect found and fixed here.** The self-service password change ran
`DELETE FROM sessions WHERE user_id=… AND token<>…`, which removed the database rows but left the
in-process `TOKENS` cache untouched. `require_auth()` consults `TOKENS` **before** the sessions table,
so **every other browser stayed signed in** — exactly what a victim tries to stop after a credential
compromise. Now fixed by `revoke_user_sessions()`, which purges both.

- **Negative control:** with the fix temporarily reverted, `test_14` **fails**
  (`AssertionError: 200 != 401 : the second session must be revoked`). With it restored, it passes.
  The test genuinely detects the defect.
- `test_14` also confirms the session that performed the change **stays** signed in, the new password
  works, and the old one stops working immediately.

**H-5 — measured and recorded, not fixed.** `test_15` proves that an **administrator-initiated**
password reset does **not** end the target officer's existing sessions: a stolen session survives the
reset. This is finding H-5, which is not one of the five authorised items. The test records the
current behaviour so the exposure is visible and any future change is noticed.

**6 · Tests that remain blocked**
None for this work package.

**7 · Database / migration impact**
**No schema change, and this was checked before the work started.** `users.password_hash` is already
`TEXT`, so the ~130-character PBKDF2 string fits with no `ALTER TABLE`. Existing rows migrate
**lazily on next successful sign-in** — no DDL, no bulk rewrite, no forced reset, no downtime.
A row that is never used is never rewritten, and still authenticates.

**8 · Rollback**
`git checkout a9096c8 -- backend/server.py`. **Important:** any password already upgraded to PBKDF2
will **not** be verifiable by the reverted single-round SHA-256 code, and those users would be locked
out. Rolling this back safely requires a password reset for every account that has signed in since
deployment. This is the one change in Stage 0 that is not cleanly reversible, and that is inherent to
re-hashing credentials.

---

## 6. WP-08 / WP-09 — Upload validation and document access control

**1 · Files changed**
`backend/server.py` — `UPLOAD_ALLOWED_EXTS` 4118, `UPLOAD_MAGIC`, `_content_matches_extension()`,
`save_upload()` 4147, `save_upload_validated()` 4606, the `/uploads/` route 8186, `send_file()`
extended with `extra_headers`. `backend/test_upload_access_control.py` (new),
`backend/test_server.py` / `backend/test_conduct_frontend.mjs` (three malformed PDF fixtures corrected).

**2 · Exact problem corrected**

- **C-1:** the `/uploads/` route performed **no authentication whatsoever**. Passport scans, applicant
  photographs, guardian identity documents and case evidence were readable by **any anonymous caller**.
- **M-7:** `save_upload()` performed **no validation at all** — the extension was copied from the
  client onto disk with no allow-list and no size cap. Nine call sites used it directly. A `.svg`,
  `.html` or `.xhtml` could be stored and later served **from the application's own origin**
  (stored XSS against an authenticated officer), and a single large POST could fill the disk.

**3 · Before and after**

| | Before | After |
|---|---|---|
| Anonymous GET of a document | **200 + the file** | **401** |
| Authentication accepted | n/a | Bearer token **or** session cookie (so `<img src>` still works) |
| Response headers | none relevant | `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Content-Disposition: inline` |
| Allowed types | **anything** | jpg, jpeg, png, gif, webp, tif, tiff, pdf |
| Size cap | **none** | 20 MB default; the stricter 5 MB per-feature caps still apply |
| Content check | none | magic-number check — content must match the claimed extension |
| File mode on disk | default | `0640`, never executable |
| Double extension | `x.pdf.html` treated as PDF-ish | judged on the **final** extension → refused |

**4 · Tests executed and actual results**
`backend/test_upload_access_control.py` → **15/15 OK**:

| Test | Result |
|---|---|
| 01 anonymous GET of a real document | **401**, and the body contains no file bytes |
| 02 anonymous GET of **every** file in the uploads directory | all 401 |
| 03 authenticated owner reads it | 200, real PDF returned, `nosniff` + sandbox CSP present |
| 04 session **cookie** authenticates | 200 — browser image loads keep working |
| 05 forged tokens (empty, junk, random 64-hex, `Bearer`) | all 401 |
| 06 **logged-out** token | 401 — revocation is immediate |
| 07 cross-branch read | **200 — recorded exposure, see below** |
| 08 `.html`, `.svg`, `.php`, `.exe`, `.txt`, `.zip`, `.xhtml` | all refused 400 |
| 09 `invoice.pdf.html` | refused 400 |
| 10 HTML bytes renamed `.pdf` | refused 400, error names the mismatch |
| 11 oversized file | refused 400 |
| 11b empty file | never reaches disk; `save_upload` raises directly |
| 12 genuine PDF and JPEG | accepted 201 |
| 13 every file on disk | allowed extension, non-executable mode |
| 14 path traversal (3 forms) | refused, no server source leaked |

Each hostile upload is submitted as part of an **otherwise complete and valid** application (two real
applicant documents, two real guardian documents), and the assertion explicitly rejects a 400 whose
message is about a missing document. This prevents the tests passing for the wrong reason.

**5 · Security verification evidence — your explicit requirement**
You asked for *authenticated AND unauthenticated access, including cross-branch.* All three were
tested over real HTTP against the running server:

- **Unauthenticated:** tests 01, 02, 05, 06 — refused.
- **Authenticated:** tests 03, 04 — permitted, with hardening headers.
- **Cross-branch:** test 07 — **permitted (200). This is the remaining exposure.**

**The cross-branch result, stated plainly:** an authenticated checkpoint officer posted to a
different branch **can still read another branch's documents**. Authentication is fixed;
**per-file authorisation is not**. Implementing it requires a document → record ownership link,
which does not exist because documents are stored as JSON blobs inside the owning row (finding N-6).
That is a schema change, and you instructed that none be made without approval. The test asserts the
200 **with an explanatory failure message**, and automatically fails if the behaviour ever changes —
so this cannot be quietly forgotten.

Addresses **SR-01** (anonymous access) and **SR-15** (validation). **Does not fully close H-2a.**

**6 · Tests that remain blocked**
None for this work package. The cross-branch case is **not blocked** — it is implemented, executed,
and deliberately asserts the current (insufficient) behaviour.

**7 · Database / migration impact**
**None.** The per-file authorisation that *would* require a schema change was **not** made. For when
you authorise it, the shape is: a `documents` table (id, owning record type and id, branch_id,
stored path, content hash, uploader, uploaded_at) replacing the JSON blobs, plus a backfill.
**This has not been applied and is not proposed for Stage 0.**

**8 · Rollback**
`git checkout a9096c8 -- backend/server.py`. **Not recommended** — it reopens anonymous access to
every stored document. If a specific file type must be allowed, extend `UPLOAD_ALLOWED_EXTS` and
`UPLOAD_MAGIC` rather than reverting. Note that files written since deployment are mode `0640`;
reverting the code does not change permissions already applied.

---

## 7. Defects found and deliberately NOT fixed

### N-7 — closing a disciplinary action is impossible *(new, application defect)*

In `backend/server.py`, inside `update_discipline()`:

```python
placeholders = ','.join('%s' * len(DISCIPLINE_OPEN_STATUSES))
```

`'%s' * 3` is `'%s%s%s'`; joining **its characters** with commas produces `'%,s,%,s,%,s'`, not
`'%s,%s,%s'`. psycopg2 raises `unsupported format character ',' (0x2c) at index 94`, surfacing as
HTTP 400.

**Operational effect: a disciplinary action can never be closed, so a suspended officer can never be
returned to Active duty.** The correct form is `','.join(['%s'] * len(...))`.

**Why I did not fix it:** the HR/conduct module is not one of the five authorised items and you
instructed that no unrelated changes be made. It is a one-line fix and I can apply it on your word.
It blocks `test_server.py`.

### H-5 — an admin password reset does not end the target's sessions
Measured by `test_password_security.py::test_15`. Not one of the five items.

### Analytics RBAC inconsistency
`/api/analytics` is not gated purely by `ROLE_MODULES`. `ROLE_CID` is
`{dashboard, people, cid, crimes}`, yet `cid.officer` receives `['cid','stations','vehicles']`, and
`cp.south` receives `['cid','vehicles']`. Only `fp.officer` is correctly narrowed. This leaks station
and vehicle analytics to roles with no such module. Reported, not changed.

---

## 8. Constraints — compliance statement

| Constraint | Status |
|---|---|
| Stop after Stage 0; do not begin Stage 1 | **Honoured.** Nothing beyond the five items was implemented. |
| No production deployment | **Honoured.** Nothing deployed; no production system contacted. |
| No real police records in testing | **Honoured.** Every fixture is synthetic. |
| No unrelated UI, feature or architecture changes | **Honoured.** The only UI changes are the login-screen credential removal (item 3) and the biometric no-match messages (item 2). |
| No silent database structure changes | **Honoured.** **Zero DDL.** Two schema changes were identified as necessary (document ownership for N-6; `suspect_alerts.branch_id` for N-1) and **neither was applied**. |
| Preserve `main` and audit history; do not merge | **Honoured.** `main` verified at `a1c2478` after the push. No merge, no history rewrite. PR #23 untouched. |
| Separate, clearly identified implementation branch | **Deviation — see §0.1.** Technically impossible in this session; work is on the session branch, unmerged. |
| Procurement and legal plans as separate documents, in parallel | **Done.** `planning/BIOMETRIC_PROCUREMENT_PLAN.md`, `planning/LEGAL_ACTION_PLAN.md`. |
| Do not begin genuine biometric matcher implementation | **Honoured.** Stage 0 **removed** fake matching; it did not add real matching. |
| Never claim unexecuted tests pass | **Honoured.** Every result quoted was executed; BLOCKED is reported as blocked. |
| Code inspection is never proof of runtime security | **Honoured.** Every security claim is backed by an executed HTTP-level or DOM-level test, with negative controls for the two most important fixes. |

---

## 9. What I recommend next — for your decision, not mine to take

1. **Authorise the N-7 one-line fix.** A suspended officer cannot currently be reinstated. It is the
   cheapest high-impact fix available and it unblocks the last test suite.
2. **Start the legal and procurement plans now.** They have 4–12 week and 4–16 week lead times and
   nothing in engineering can shorten them.
3. **Decide on the document-ownership schema change** so cross-branch document authorisation can be
   closed. Until then, treat every authenticated officer as able to read every uploaded document.
4. **If any environment is already deployed**, rotate all nine seeded passwords manually — WP-02
   prevents new installations from being seeded with a shared password but does not change existing rows.

**I have stopped here and started nothing from Stage 1.**
