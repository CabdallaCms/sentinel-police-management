# Credential Rotation Procedure — existing databases

**Date:** 7 November 2026 · **Status:** **PROCEDURE — NOT EXECUTED**
**Addresses:** S-06 (existing databases still hold `ChangeMe123!` credentials)
**Applies to:** any database created before commit `e7263d7`

> Nothing in this document has been run. No credential was changed, no database was contacted.

---

## 1. Why this is needed

Stage 0 (WP-02) removed the shared default password from the **seeding path**. It changed how *new*
accounts are created. It did **not** modify any row in any existing database.

**If an environment was ever started before `e7263d7`, all nine seeded accounts still authenticate
with `ChangeMe123!`** — including `admin` (full administrative control) and `chief` (global read
access to every record).

There is a compounding second problem. Stage 0 (WP-03) upgrades a password hash **only on a
successful sign-in**. An account nobody has used since the upgrade therefore still stores an
**unsalted SHA-256 digest of a publicly known password**. The two weaknesses sit on the same row.

**Scope note, stated honestly:** I have no evidence that any environment exists. The repository has
no deployment configuration, no CI, and no infrastructure definitions. This procedure is written so
that it is ready **if** one exists. Determining that is step 1.

---

## 2. Decide whether this applies — do this first

| Question | How to answer | If yes |
|---|---|---|
| Does any PostgreSQL database for this system exist outside a test run? | Ask whoever has run the backend; check for a persisted `SENTINEL_DB_*` / `SENTINEL_DATABASE_URL` configuration | Continue |
| Was it created before `e7263d7`? | `SELECT created_at FROM users ORDER BY id LIMIT 1;` | Continue |
| Do any rows still hold the legacy hash format? | §3, query A | Rotate those accounts |
| Was it ever reachable from a network other than localhost? | Ask the operator | **Treat as compromised — §7** |

If every answer is no, record that finding and stop. Do not rotate what does not exist.

---

## 3. Assessment queries (read-only — safe to run)

**Query A — which accounts still carry a legacy unsalted SHA-256 hash?**

```sql
SELECT id, username, role, active,
       CASE WHEN password_hash ~ '^[0-9a-fA-F]{64}$' THEN 'LEGACY sha256'
            WHEN password_hash LIKE 'pbkdf2_sha256$%' THEN 'pbkdf2'
            ELSE 'unknown' END AS hash_format
FROM users
ORDER BY hash_format, username;
```

**Query B — which accounts still use the retired default password?**
This cannot be answered by SQL for PBKDF2 rows (that is the point of a salted hash). For the legacy
rows it can, because the digest is deterministic:

```sql
-- sha256('ChangeMe123!') = 7f1e0f6d...  (compute locally; do not paste a password into SQL)
SELECT username FROM users
WHERE password_hash = encode(digest('ChangeMe123!', 'sha256'), 'hex');
```

If `pgcrypto` is unavailable, compute the digest in Python and compare:

```sh
python3 -c "import hashlib;print(hashlib.sha256('ChangeMe123!'.encode()).hexdigest())"
```

**Query C — which accounts have live sessions right now?**

```sql
SELECT u.username, COUNT(s.id) AS live_sessions
FROM users u LEFT JOIN sessions s ON s.user_id = u.id
GROUP BY u.username ORDER BY live_sessions DESC;
```

Query C matters because of S-02: **rotating a password does not currently end a session.** Until
S-02 is fixed, rotation alone does not evict anyone.

---

## 4. The rotation procedure

### Pre-conditions

1. A verified database backup, with a tested restore.
2. **S-02 fixed, or §6 applied.** Rotating passwords while sessions survive is theatre.
3. A secure channel to deliver each new password to its officer. Do not use the credential file for
   an established system; that mechanism is for first-run bootstrap only.
4. A maintenance window agreed with whoever depends on the system.

### Steps

```
 1. Announce the window. Every officer will be signed out and must sign in again.
 2. Back up the database. Verify the restore.
 3. Run Query A and Query C. Record the before-state.
 4. For EACH account:
      a. Generate a unique high-entropy password (>= 16 chars, CSPRNG).
      b. Set it via the application:  PATCH /api/admin/users/<id> {"password": "..."}
         - uses the approved PBKDF2 path
         - writes an audit row
         - NEVER write password_hash by direct SQL
      c. Deliver it to the named officer over the secure channel.
 5. Terminate ALL sessions (see §6).
 6. Re-run Query A: every row must read 'pbkdf2'. Zero 'LEGACY sha256'.
 7. Re-run Query C: zero live sessions.
 8. Confirm each officer can sign in and is forced to set their own password.
 9. Record completion, including who rotated what and when.
```

**Step 4b is deliberate.** Writing `password_hash` directly by SQL bypasses the audit trail and
risks an incorrectly formatted hash that silently locks the account out. Use the API.

### Unused accounts

An account that nobody signs into keeps its legacy hash forever. Do not leave it. For each unused
seeded account, either rotate it (step 4) or **deactivate** it:

```sql
UPDATE users SET active = 0 WHERE username = '<unused>';
```

Deactivation takes effect immediately on existing sessions, because `require_auth()` filters on
`active = 1` on every request. **This is the one control that works today without an S-02 fix.**

---

## 5. Preventing recurrence

- Generate bootstrap passwords per install — already enforced by Stage 0.
- Delete `backend/bootstrap-credentials.txt` after first sign-in. It is `0600` and gitignored, but
  it is still a plaintext credential on disk.
- Add a **forced password change on first sign-in**. This needs a `must_change_password` column on
  `users` → a schema change → **owner approval required**. Proposed as migration **M-03**; not
  included here because it is not yet authorised.
- Close S-08 (no session expiry) and S-09 (no throttling). Rotation is far less valuable while a
  session lasts forever and passwords can be guessed without rate limiting.

---

## 6. Terminating all sessions

**Today, the only reliable method is a server restart**, because the in-process `TOKENS` cache is
authoritative before the `sessions` table:

```sql
DELETE FROM sessions;          -- clears persisted sessions
```

```sh
# then restart the backend so the in-memory TOKENS cache is discarded
```

**Both steps are required.** Deleting the rows alone is not sufficient — this is exactly the defect
(N-8) that Stage 0 fixed for the self-service path only.

Once S-02 is implemented, an administrator password reset will revoke sessions directly and this
manual step becomes unnecessary.

---

## 7. If the system was ever network-reachable

Treat the nine default credentials as **publicly known**, because they were published in the
repository, in `README.md`, and on the login screen itself.

1. Rotate everything (§4) and terminate all sessions (§6).
2. Review `audit_events` for activity you cannot attribute to a known officer.
3. **Accept this limitation:** the audit log is mutable (S-10 / H-7), and `/uploads/` reads were
   never audited. **You cannot prove from the logs whether documents were read.** Say so plainly in
   any incident report rather than implying the absence of evidence is evidence of absence.
4. Consider every document stored before the Stage 0 fix to have been potentially exposed, since
   `/uploads/` required no authentication at all.

---

## 8. Approvals required

| # | Approval | Why |
|---|---|---|
| R-1 | Confirm whether any pre-`e7263d7` environment exists | Determines whether any of this runs |
| R-2 | Authorise the maintenance window and the sign-out of all officers | Operational disruption |
| R-3 | Approve the secure delivery channel for new passwords | Policy |
| R-4 | Decide: rotate or deactivate each unused seeded account | Policy |
| R-5 | Approve migration **M-03** (`must_change_password`) if forced rotation is wanted | Schema change |

**Estimate:** 1–2 engineering days to script and rehearse the assessment and rotation against a
restored copy; the live run is operational time proportional to the number of accounts.
