# P0 Technical Clarification

**Date:** 7 November 2026 · **Commit:** `389787b` · **Status:** **SPECIFICATION — NOT IMPLEMENTED**
**Companion:** `OWNER_DECISION_SHEET.md` · `P0_WORK_PACKAGES.md`

> Every diff below is a **proposal**. `backend/server.py` is byte-identical to `e7263d7`
> (sha256 `a8211f4f…b3b9fc`, re-verified after the test runs in §1 and §2).

---

## How the P0-WP-1 and P0-WP-2 claims were verified

A throwaway harness drove the real HTTP API against a real PostgreSQL cluster. I ran it **twice**:
once against unmodified code, once with both fixes applied to a scratch copy. Then I restored
`server.py` and deleted the harness.

```
UNMODIFIED CODE                     WITH A-10 + A-11
  8 passed, 4 failed                  14 passed, 0 failed
  FAILED: close action (N-7)
  FAILED: officer stays Suspended     <- unreachable, close failed first
  FAILED: token 1 revoked (got 200)
  FAILED: token 2 revoked (got 200)   <- the in-memory TOKENS control
```

The failures on unmodified code **are** the negative control: they prove the checks detect the
defects rather than passing vacuously.

### A correction I am volunteering

My first corrected run still showed `NEGATIVE CONTROL other action open -> officer STAYS Suspended`
**failing**, with the officer reinstated to `Active`. Reported as-is, that would have said the fix
is dangerous.

It was my fixture. I created the second action with `action_type: 'Reprimand'`, which is not in
`DISCIPLINE_ACTION_TYPES` (`Misconduct`, `Suspension`, `Demotion`, `Warning`, `Investigation`), so
the API rejected it and **the "second open action" never existed**. The control was vacuous and
failed for the wrong reason.

Fixed by using `'Misconduct'` **and** adding an explicit assertion that the fixture exists before
the control is trusted:

```python
check('second OPEN action created (fixture validity)', s == 201 and bool(act2), (s, a2))
```

Any test that ships for P0-WP-1 must contain that guard-the-guard assertion.

---

## 1. P0-WP-1 — exact change and tests

### The diff

```diff
--- a/backend/server.py
+++ b/backend/server.py
@@ -6825,7 +6825,7 @@ def update_discipline(c, user, action_id, data):
         elif action['status'] == 'Closed':
-            placeholders = ','.join('%s' * len(DISCIPLINE_OPEN_STATUSES))
+            placeholders = ','.join(['%s'] * len(DISCIPLINE_OPEN_STATUSES))
             sql = ('SELECT COUNT(*) FROM officer_discipline WHERE officer_id=%s '
                    'AND action_id<>%s AND status IN (' + placeholders + ')')
             still_open = c.execute(sql, (officer_id, action_id) + tuple(DISCIPLINE_OPEN_STATUSES)).fetchone()[0]
```

`'%s' * 3` → `'%s%s%s'`; `','.join()` then joins **per character** → `'%,s,%,s,%,s'`. psycopg2 reads
`%,` as a format specifier and raises `unsupported format character ',' (0x2c) at index 94` → 400.
The list form produces the intended `'%s,%s,%s'`.

**One line. One statement. Verified unique:** `grep -n "join('%s' \*" server.py vehicles.py` matches
only line 6828.

### Confirmation: an officer with another unresolved action is NOT reinstated

**Confirmed by execution.** The surrounding logic is already correct and the fix does not alter it:

```python
still_open = c.execute(sql, (officer_id, action_id) + tuple(DISCIPLINE_OPEN_STATUSES)).fetchone()[0]
if not still_open:
    c.execute("UPDATE officers SET duty_status='Active' WHERE id=%s "
              "AND duty_status='Suspended'", (officer_id,))
```

Three independent guards:

1. `action_id<>%s` — the action being closed is excluded from its own count.
2. `status IN ('Pending','In Review','Appealed')` — any other open action makes `still_open` non-zero
   and the `UPDATE` is skipped entirely.
3. `AND duty_status='Suspended'` — a `Terminated` or `Retired` officer is never reactivated, even
   with zero open actions.

Measured sequence:

| Step | Result |
|---|---|
| Confirm a Suspension | `duty_status = Suspended` ✓ |
| Create a second **open** action (`Misconduct`, `Pending`) — fixture asserted to exist | ✓ |
| Close the **suspension** while the second is open | 200, and **`duty_status` stays `Suspended`** ✓ |
| Close the second action | 200, **`duty_status` becomes `Active`** ✓ |

### Tests to ship

```python
def test_close_last_action_reinstates(self):
    """Positive: no other open action -> officer returns to Active."""

def test_close_with_another_open_action_does_not_reinstate(self):
    """NEGATIVE CONTROL. Officer has a Confirmed Suspension AND a second
    action in an OPEN status. Closing the suspension must leave the officer
    Suspended. Fails against any 'fix' that drops the still_open check."""
    # guard-the-guard: a rejected fixture would make this vacuous
    self.assertEqual(create_status, 201)
    self.assertTrue(second_action_id)

def test_terminated_officer_is_never_reactivated(self):
    """NEGATIVE CONTROL. duty_status='Terminated', zero open actions,
    close an action -> stays Terminated."""

def test_close_requires_hr_permission(self):
    """NEGATIVE CONTROL. Non-HR caller -> 403 and duty_status unchanged."""

def test_pre_fix_control(self):
    """Run against the unfixed line and assert HTTP 400 with
    'unsupported format character'. A regression test never seen to fail
    proves nothing."""
```

---

## 2. P0-WP-2 — exact change and tests

### The diff

```diff
--- a/backend/server.py
+++ b/backend/server.py
@@ -10011,6 +10011,13 @@
                     audit(c, user, 'UPDATE', 'user', uid,
                           'changed fields: ' + ', '.join(columns))
+                    # H-5: an administrator reset must END the target's sessions.
+                    # The token is independent of the password, so without this a
+                    # stolen session survives the reset meant to stop it. No
+                    # keep_token: unlike the self-service change, the caller is
+                    # not the account owner.
+                    if 'password_hash' in sets or sets.get('active') == 0:
+                        revoke_user_sessions(c, int(uid))
+                        audit(c, user, 'REVOKE_SESSIONS', 'user', uid,
+                              'all sessions revoked: '
+                              + ('password reset by administrator'
+                                 if 'password_hash' in sets else 'account deactivated'))
                 c.commit()
                 updated = rowdict(c.execute('SELECT * FROM users WHERE id=%s', (int(uid),)).fetchone())
```

Placed **inside** `if sets:` and **before** `c.commit()`, so the revocation is part of the same
transaction as the password write. A failure rolls back both — the password is never changed while
sessions survive.

**Drop the `or sets.get('active') == 0` clause if you reject A-11a.** Nothing else changes.

### Confirmation: all sessions are revoked, including in-memory tokens

**Confirmed by execution**, using **two concurrent sessions** for the victim — this is the control
that distinguishes a correct fix from the N-8 mistake.

```python
# backend/server.py:4224 — the existing helper, reused
def revoke_user_sessions(conn, user_id, keep_token=None):
    user_id = int(user_id)
    for token, owner in list(TOKENS.items()):          # <-- in-process cache
        if owner == user_id and token != keep_token:
            TOKENS.pop(token, None)
    conn.execute('DELETE FROM sessions WHERE user_id=%s AND token<>%s',   # <-- persisted rows
                 (user_id, keep_token or ''))
```

Both halves are required: `require_auth()` consults `TOKENS` **before** the `sessions` table, so a
bare `DELETE FROM sessions` leaves other browsers authenticated until restart. That was finding
N-8.

| Check | Unfixed | Fixed |
|---|---|---|
| Victim token 1 after reset | **200** | **401** ✓ |
| Victim token 2 after reset (in-memory control) | **200** | **401** ✓ |
| Administrator's own session | 200 | **200** ✓ |
| Unrelated officer's session | 200 | **200** ✓ |
| New password works | ✓ | ✓ |
| Old password refused (401) | ✓ | ✓ |
| Display-name-only PATCH leaves session alive | ✓ | **✓** |

The last four are over-correction controls: they fail if the revoke is too broad (`DELETE FROM
sessions` with no `WHERE`, or revoking on every update).

### Tests to ship

```python
def test_admin_reset_revokes_all_target_sessions(self):
    """Victim holds TWO tokens; after the reset BOTH are 401.
    Fails if only the sessions rows are deleted (finding N-8)."""

def test_admin_own_session_survives(self):            # NEGATIVE CONTROL
def test_third_party_session_survives(self):          # NEGATIVE CONTROL
def test_non_password_patch_does_not_revoke(self):    # NEGATIVE CONTROL
def test_revocation_is_audited(self):
    """An audit_events row with action REVOKE_SESSIONS, correct actor and target."""
def test_15_tightened(self):
    """Existing characterisation test: replace the skipTest escape with a
    hard assertion that the victim's token is 401."""
```

---

## 3. P0-WP-3 — the three changes, separately

All three live in `init_db()` (`server.py:3261`). Current structure:

```
3268-3273  police_branches     reference data   -> KEEP in production
3274-3282  locations           reference data   -> KEEP in production
3283-3301  police_stations     reference data   -> KEEP in production   (A-18)
3302-3323  9 user accounts     demonstration    -> CHANGE  (S-13 / A-17)
3324-3362  demonstration data  demonstration    -> CHANGE  (S-13 / A-16)
3363       c.commit(); c.close()
```

### 3.1 Change for S-06 (residual) — mode selection

No defect to fix in isolation; S-06's live residual is "there is no documented, distinguishable
production path". One helper introduces the distinction everything else keys off.

```diff
+# ---- initialization mode ----------------------------------------------------
+# PRODUCTION (default): administrator account only, zero demonstration records.
+# DEMONSTRATION: the full nine-role dataset, for development, test and training.
+SEED_DEMO_ENV = 'SENTINEL_SEED_DEMO_DATA'
+
+def demo_seeding_enabled():
+    return str(os.environ.get(SEED_DEMO_ENV, '')).strip().lower() in ('1', 'true', 'yes', 'on')
```

**Default off.** An operator who does nothing gets a clean database.

### 3.2 Change for S-12 — shared bootstrap password

**Today** (`server.py:3489`) the environment value is returned **unchanged for every username**, so
one variable gives all nine accounts one password, silently:

```python
def bootstrap_password_for(username):
    explicit = os.environ.get(BOOTSTRAP_PASSWORD_ENV)
    if explicit:
        return explicit            # <-- identical for every account
    return 'Sx-' + secrets.token_hex(16)
```

**Proposed** — honour it only in demonstration mode (**A-19 option b**), warn if present otherwise:

```diff
 def bootstrap_password_for(username):
     explicit = os.environ.get(BOOTSTRAP_PASSWORD_ENV)
-    if explicit:
-        return explicit
+    if explicit:
+        if demo_seeding_enabled():
+            # Demonstration/test only: ~22 suites rely on a known password.
+            return explicit
+        # PRODUCTION: ignore it. A shared credential must not be reachable
+        # through a single environment variable (finding S-12).
+        sys.stderr.write(
+            'WARNING: %s is set but is IGNORED in production initialization. '
+            'A unique random password will be generated. Set %s=1 for a '
+            'demonstration database.\n' % (BOOTSTRAP_PASSWORD_ENV, SEED_DEMO_ENV))
     return 'Sx-' + secrets.token_hex(16)
```

In production only one account is created, so the shared case is **structurally impossible**, not
merely discouraged.

### 3.3 Change for S-13 — demonstration accounts and records

```diff
     if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
-        seeds = [
+        demo = demo_seeding_enabled()
+        # PRODUCTION: the administrator only. Every real officer is created
+        # through POST /api/admin/users with their own identity and badge.
+        production_seeds = [
+            ('admin', 'System Administrator', ROLE_ADMIN, 'Central HQ', None, 'ADM-101'),
+        ]
+        demonstration_seeds = [
             ('admin',       'Officer A. Hassan',  ROLE_ADMIN,              'Central HQ',          None,    'ADM-101'),
             ('fp.officer',  'Officer H. Xasan',   ROLE_FINGERPRINT,        'Fingerprint Unit',    None,    'FP-102'),
             ...
             ('chief',       'Gen. C. Warsame',    ROLE_CHIEF,              'Police HQ / Command', None,    'CMD-901'),
         ]
+        seeds = demonstration_seeds if demo else production_seeds
         issued = []
         for u, dn, role, branch, scope, badge in seeds:
             ...
         report_bootstrap_credentials(issued)

-    if c.execute('SELECT COUNT(*) FROM persons').fetchone()[0] == 0:
+    # Demonstration records: fictional persons, cases, a suspect alert, a
+    # clearance application, a checkpoint event and an airport movement.
+    # NEVER created in production (finding S-13) — a fictional person must not
+    # appear in an operational police database, and a seeded suspect alert
+    # cannot currently be cleared at all (finding S-03).
+    if demo_seeding_enabled() and c.execute('SELECT COUNT(*) FROM persons').fetchone()[0] == 0:
         ... lines 3325-3362 unchanged ...
```

Note the production display name is `'System Administrator'`, not the fictional
`'Officer A. Hassan'` — a production account should not carry an invented officer identity.

---

## 4. How the three initialization modes differ

| | **Production** (default) | **Development** | **Test** |
|---|---|---|---|
| `SENTINEL_SEED_DEMO_DATA` | unset | `1` | `1` (set by the runner) |
| `SENTINEL_BOOTSTRAP_PASSWORD` | ignored + warning | optional | `ChangeMe123!` (runner) |
| User accounts | **`admin` only** | all 9 | all 9 |
| Admin password | random, 128-bit, unique | random unless overridden | `ChangeMe123!` |
| `persons` | **0** | 3 fictional | 3 fictional |
| `crime_cases` | **0** | 2 | 2 |
| **`suspect_alerts`** | **0** | 1 | 1 |
| `clearance_applications` / `checkpoint_events` / `airport_passengers` | **0** | 1 each | 1 each |
| Branches / locations / stations | **yes** (A-18) | yes | yes |
| Database lifetime | permanent | developer's local | ephemeral per run |

**Development and test are the same mode.** The only difference is that the runner also pins the
bootstrap password so ~22 suites can authenticate. Keeping them identical means a developer
reproduces CI exactly.

### Confirmation: demonstration data remains available in non-production

**Yes — fully, and unchanged.** `SENTINEL_SEED_DEMO_DATA=1` reproduces today's behaviour byte for
byte: all nine accounts, all three fictional persons, both crime cases, the suspect alert, the
clearance application, the checkpoint event and the airport movement.

Three things protect this:

- `scripts/run-tests.sh` exports the flag, so **no existing suite changes**.
- **AC-6** requires the full suite to pass unchanged in demonstration mode — a regression here fails
  the work package.
- The developer workflow is one line in `.env`:

```sh
SENTINEL_SEED_DEMO_DATA=1
```

**Nothing is removed. One default is inverted.**

---

## 5. How the first production administrator is created

```sh
# 1. Pre-flight — no credential or demo override may be present
env | grep -E 'SENTINEL_(BOOTSTRAP_PASSWORD|SEED_DEMO_DATA)'    # must print nothing

# 2. Confirm the target database is empty
psql -c 'SELECT COUNT(*) FROM users;'                            # 0, or no schema

# 3. Start the backend once
python3 backend/server.py
```

The server creates the schema, reference branches/locations/stations, and **one** account:

```
========================================================================
SENTINEL FIRST-RUN CREDENTIALS - shown once, store them now
Generated 2026-11-07T...

  admin        Sx-4f9c1ab7e2d5086c3b7e1f0a9d4c2e68

Saved to: backend/bootstrap-credentials.txt
========================================================================
```

Password properties: `secrets.token_hex(16)` = **128 bits** of CSPRNG entropy, unique per
installation, stored as PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte salt. Never written to the
repository, never embedded in source, never shown on the login page.

```sh
# 4. Sign in and change it IMMEDIATELY
curl -X POST .../api/me/password -d '{"current_password":"Sx-…","new_password":"…"}'

# 5. Verify the generated password no longer works   -> 401
# 6. Delete the credentials file
rm backend/bootstrap-credentials.txt

# 7. Acceptance checks
psql -c "SELECT COUNT(*) FROM users;"           --  must be 1
psql -c "SELECT COUNT(*) FROM suspect_alerts;"  --  must be 0
```

If step 7 returns anything else, demonstration seeding ran. **Stop, drop the database, restart from
pre-flight.**

Then create each real officer through `POST /api/admin/users` with their own badge number and a
unique password delivered over a secure channel — **never** by direct SQL, which bypasses PBKDF2
and the audit trail.

### Residual weaknesses at go-live — state these in the deployment record

| ID | Weakness |
|---|---|
| **S-11** | **No TLS — credentials cross the network in clear text.** Decisive: do not expose this system until TLS terminates in front of it |
| S-02 | Until A-11 ships, a reset does not end sessions |
| S-08 / S-09 | No session expiry; no throttling or lockout |
| — | The login page enumerates usernames |
| — | Step 4 is procedural, not enforced — forced rotation needs `must_change_password` (M-03 / A-9) |

---

## 6. Tests proving production stays clean

New suite `backend/test_production_init.py`, written to be **unskippable in production mode**.

```python
class ProductionInitializationTest(unittest.TestCase):
    """Initializes a REAL empty database with no environment overrides."""

    # ---- no demonstration records ------------------------------------
    def test_no_demonstration_persons(self):
        self.assertEqual(self.count('persons'), 0)

    def test_no_suspect_alerts(self):
        """S-13 + S-03. A seeded alert could never be cleared, so a
        fictional person would be flagged at every checkpoint forever."""
        self.assertEqual(self.count('suspect_alerts'), 0)

    def test_no_demonstration_cases_or_events(self):
        for table in ('crime_cases', 'clearance_applications',
                      'checkpoint_events', 'airport_passengers'):
            self.assertEqual(self.count(table), 0, table)

    # ---- exactly one account ----------------------------------------
    def test_only_the_administrator_exists(self):
        self.assertEqual(self.usernames(), {'admin'})

    def test_no_demonstration_personas(self):
        """NEGATIVE CONTROL, named explicitly so a partial revert is caught."""
        for u in ('fp.officer', 'ap.officer', 'cid.officer', 'hr.officer',
                  'cp.south', 'cp.east', 'cp.west', 'chief'):
            self.assertNotIn(u, self.usernames(), u)

    # ---- no shared or known password --------------------------------
    def test_retired_default_is_refused(self):
        self.assertEqual(self.login('admin', 'ChangeMe123!')[0], 401)

    def test_bootstrap_password_env_is_ignored_in_production(self):
        """S-12 / A-19. Initialize WITH the variable set; it must NOT work,
        and the warning must be emitted."""
        srv = self.fresh(env={'SENTINEL_BOOTSTRAP_PASSWORD': 'Shared-Pw-123!'})
        self.assertEqual(srv.login('admin', 'Shared-Pw-123!')[0], 401)
        self.assertIn('IGNORED in production', srv.stderr())

    def test_admin_password_is_unique_per_installation(self):
        """Two independent initializations must not share a password hash."""
        self.assertNotEqual(self.fresh().admin_hash(), self.fresh().admin_hash())

    def test_password_entropy(self):
        self.assertRegex(self.issued_password('admin'), r'^Sx-[0-9a-f]{32}$')

    # ---- idempotence -------------------------------------------------
    def test_second_run_changes_nothing(self):
        before = self.snapshot(); self.restart(); self.assertEqual(self.snapshot(), before)

    # ---- demonstration mode still works ------------------------------
    def test_demo_mode_restores_the_full_dataset(self):
        srv = self.fresh(env={'SENTINEL_SEED_DEMO_DATA': '1'})
        self.assertEqual(len(srv.usernames()), 9)
        self.assertEqual(srv.count('persons'), 3)
        self.assertEqual(srv.count('suspect_alerts'), 1)

    def test_demo_mode_shared_password_is_announced(self):
        """S-12 characterisation: in DEMO mode the variable IS honoured and
        all nine accounts share it. Asserted so it cannot change silently."""
```

### Pre-change control

Run `test_production_init.py` against **today's** code. It must **fail** — a default initialization
currently creates nine users and a suspect alert. A test never seen to fail proves nothing.

### Coverage map

| Requirement | Test |
|---|---|
| No demo records in production | `test_no_demonstration_persons`, `test_no_suspect_alerts`, `test_no_demonstration_cases_or_events` |
| No shared bootstrap password | `test_bootstrap_password_env_is_ignored_in_production`, `test_admin_password_is_unique_per_installation`, `test_retired_default_is_refused` |
| Only the administrator | `test_only_the_administrator_exists`, `test_no_demonstration_personas` |
| Demo still available | `test_demo_mode_restores_the_full_dataset` |
| Safe to re-run | `test_second_run_changes_nothing` |

---

## 7. Reference-data initialization — exact change *(added 5 Nov 2026)*

Specifies the A-18 outcome inside **P0-WP-3**. Answers the owner's question 5.
**Nothing here is implemented.**

### 7.1 What changes

Three edits inside `init_db()`. **No schema change. No `DROP`. No `ALTER`. No `DELETE`.**

**Change 1 — seed only the four CID branch unit types.**

```python
# BEFORE (server.py:3266-3272) — 15 rows: 4 CID unit types + police_station
for branch_name, region, district in DEFAULT_POLICE_BRANCHES:
    for unit_type in BRANCH_UNIT_TYPES:
        c.execute('''INSERT INTO police_branches(name,region,district,unit_type)
                     VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                  (branch_name, region, district, unit_type))

# AFTER — 9 rows. `police_station` is HQ's unit type, not a CID one, and
# seeding it creates a latent station-fabrication path: THREE code paths
# (server.py:4700, 4724, 9145) auto-INSERT a police_stations row from such a
# branch, with a hard-coded 'District HQ' tier and no contact phone.
# See HQ_PROVISIONING_AND_READINESS.md section 0.
# Airport is Release 1.1 and its branch_id FK is nullable, so it is not
# seeded in 1.0. Add it at 1.1 behind gates G-1..G-3.
RELEASE_1_0_BRANCH_UNIT_TYPES = ('fingerprint', 'crime', 'checkpoint')
for branch_name, region, district in DEFAULT_POLICE_BRANCHES:
    for unit_type in RELEASE_1_0_BRANCH_UNIT_TYPES:
        c.execute('''INSERT INTO police_branches(name,region,district,unit_type)
                     VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                  (branch_name, region, district, unit_type))
```

In demonstration mode the loop keeps using the full `BRANCH_UNIT_TYPES`, so the existing fixture —
and the ~22 suites that rely on it — is unchanged.

**Change 2 — stop seeding `locations`.** Wrap `server.py:3274-3281` in the demo-mode guard. The
**table is retained**; nothing reads it (`REFERENCE_DATA_SCOPE_ANALYSIS.md` §1).

**Change 3 — stop seeding the eight stations.** Wrap `server.py:3283-3300` in the demo-mode guard.
The **table and schema are retained unchanged**, and the existing
`IF COUNT(*) == 0` guard already prevented it from touching a populated table.

All three sit inside the single `demo_seeding_enabled()` branch introduced by P0-WP-3 (§3), so the
production path simply does not execute them.

### 7.2 Resulting first-run state

| Table | Production | Demonstration |
|---|---|---|
| `police_branches` | **9** | 15 |
| `police_stations` | **0** | 8 |
| `locations` | **0** | 3 |
| `officers` | 0 | 0 |
| `users` | 1 (`admin`) | 9 |
| `persons`, `crime_cases`, `clearance_applications`, `checkpoint_events`, `suspect_alerts` | 0 | seeded |

### 7.3 AC-8, rewritten

| | Old AC-8 | **New AC-8** |
|---|---|---|
| Production | reference stations and branches **are** created | **`police_branches` = 9 (Release 1.0 unit types only); `police_stations` = 0; `locations` = 0** |
| Demonstration | — | unchanged: 15 / 8 / 3 |
| Schema | — | **`police_stations` and `locations` tables still exist, unaltered** |
| Existing data | — | **no row deleted or modified in any mode** |

### 7.4 Tests — `backend/test_production_init.py`

```python
def test_production_creates_release_1_0_branch_reference_data(self):
    """The three Release 1.0 units FK to police_branches; CID scoping
    resolves against the 'crime' rows (MODULE_UNIT_TYPES maps cid -> crime)."""
    self.assertEqual(self.count('police_branches'), 9)
    self.assertEqual(
        sorted({r['unit_type'] for r in self.rows('police_branches')}),
        ['checkpoint', 'crime', 'fingerprint'])

def test_production_seeds_no_airport_branch_rows(self):
    """Airport is Release 1.1; airport_passengers.branch_id is nullable and
    no 1.0 role holds the airport module."""
    self.assertEqual(
        self.count("police_branches WHERE unit_type='airport'"), 0)

def test_production_seeds_no_police_station_branch_rows(self):
    """The police_station unit type is HQ's. Seeding it would also create a
    latent station-fabrication path via resolve_station_with_branch()."""
    self.assertEqual(
        self.count("police_branches WHERE unit_type='police_station'"), 0)

def test_production_creates_no_stations(self):
    """Station provisioning is HQ's (HQ-1). Catches BOTH the removed seed
    and any auto-mirrored row, since it asserts on the table, not the seed."""
    self.assertEqual(self.count('police_stations'), 0)

def test_production_creates_no_location_rows(self):
    self.assertEqual(self.count('locations'), 0)

def test_station_and_location_tables_still_exist(self):
    """5a: schema preserved. Three FKs depend on police_stations, two of
    them NOT NULL -- the table must exist even while empty."""
    for table in ('police_stations', 'locations'):
        self.assertIsNotNone(self.table_exists(table), table)

def test_checkpoint_scoping_works_without_location_rows(self):
    """NEGATIVE CONTROL for my earlier incorrect claim that the three
    locations rows were load-bearing. Scoping reads CHECKPOINT_LOCATIONS,
    a constant -- a checkpoint officer must still scope correctly with the
    table empty."""

def test_initialization_does_not_modify_existing_reference_data(self):
    """5b: re-running init_db() against a populated database changes
    nothing. Seed a station and a branch, re-run, assert both byte-identical."""

def test_demo_mode_still_seeds_full_reference_data(self):
    db = self.fresh(env={'SENTINEL_SEED_DEMO_DATA': '1'})
    self.assertEqual(db.count('police_branches'), 15)
    self.assertEqual(db.count('police_stations'), 8)
    self.assertEqual(db.count('locations'), 3)
```

**Pre-change control.** Every one of these except the last must be run against **today's** code and
**fail** — a default initialization currently creates 15 branches, 8 stations and 3 locations. A
test never seen to fail proves nothing.

`test_production_creates_no_stations` is deliberately written against the **table**, not against the
seed block, so it also catches a station arriving by any other route.

### 7.5 Coverage of the owner's question 5

| Requirement | Test |
|---|---|
| 5a — station table and schema preserved | `test_station_and_location_tables_still_exist` |
| 5b — existing data not deleted or modified | `test_initialization_does_not_modify_existing_reference_data` |
| 5c — no fictional or placeholder stations | `test_production_creates_no_stations`, `test_production_seeds_no_police_station_branch_rows` |
| 5d — only CID-required branch data | `test_production_creates_release_1_0_branch_reference_data`, `test_production_seeds_no_airport_branch_rows` |
| 5e — no `locations` seeding | `test_production_creates_no_location_rows`, `test_checkpoint_scoping_works_without_location_rows` |
| Demo mode intact | `test_demo_mode_still_seeds_full_reference_data` |

### 7.6 Effort

**Inside P0-WP-3 (2–3 d).** Three guarded edits plus nine tests. Fully reversible — restoring the
seed restores the previous behaviour, and no option deletes data.

**⚠ Blocked by S-14 and S-15 (see §8).** This change must not ship before the branch-scope fail-open is fixed:
removing the `police_station` rows makes `/api/crimes` return every incident to every CID officer
(`BRANCH_SCOPE_FAIL_OPEN.md` §4). S-14 adds **3–5 days**, taking P0 to **10–14.5 days**.

---

## 8. Authorization defects discovered after this clarification was written

Three Critical/High authorization defects were proven by execution **after** §1–§7 were drafted.
They do not change the P0-WP-1/2/3 diffs, but they **reorder the release** and **block §7**.

All four share one root cause: module, branch and checkpoint-location scope each return a falsy
value for both *"explicitly unrestricted"* and *"cannot determine"*, and every call site reads falsy
as *"allow"*. They are therefore remediated by **one consolidated model (SEC-0)**, costed once.

| ID | Defect | Severity | Package | New work |
|---|---|---|---|---|
| — | **Unified authorization model** — three states (`UNRESTRICTED` / `GRANTED` / `INDETERMINATE`) across module, branch and location; no fallback to unrestricted | — | **SEC-0** | **2–3 d** |
| **S-16a** | `GET /api/persons/<id>` attaches clearance, airport, alert and checkpoint records with **no module, branch or location filtering**. **No precondition** | **Critical** | SEC-1 | 2–3 d |
| **S-16b** | `/linked-records`, `/documents`, `/audit-history` apply module + location but **no branch** filtering | **High** | SEC-1 | *(in SEC-1)* |
| **S-14** | Branch scope fails open — 12 enforcing call sites | **Critical** | SEC-2 | 2–3 d |
| **S-15** | `/api/crimes` scopes on `police_station` while records store a `crime` branch id | **High** | SEC-3 | 1–2 d |
| H-2b | Checkpoint location scope fails open identically; no branch filtering at all | **High** | SEC-4 | 2–3 d |
| — | Staging diagnostics + assignment correction | — | SEC-5 | 1–2 d |
| — | Four paths create station records; crime filing can create its own station | **High** | **SS-1 — separate, awaiting owner approval** | 1–2 d |

**Shared identity is preserved.** The `persons` row itself stays readable by every authenticated
session — only the attached unit arrays are filtered. Checkpoint officers do not hold the `people`
module yet legitimately need person lookup for intake, so requiring it would break operations.

**Full plan, endpoint matrix and 44-test strategy: `AUTHORIZATION_REMEDIATION_PLAN.md` (revision 2).**
Enforcement is implemented and verified **in staging before production exists** — there is no
report-only production phase, because per R-1 there is no production database to be compatible
with.

### Effect on §7 (reference-data initialization)

**§7 is blocked by SEC-2 and SEC-3.** Removing the `police_station` branch rows makes
`user_branch_scope(c, user, 'police_station')` unresolvable, so `/api/crimes` drops its `WHERE`
clause entirely and returns **every crime incident to every CID officer**. Today the same mismatch
fails *closed* (a posted CID officer sees zero incidents), so **shipping §7 first converts a
functional bug into a total disclosure.**

Required ordering: **SEC-1 → SEC-2 → SEC-3 → §7 (A-18)**, with PRE-3 (authoritative branch list)
confirmed before A-18.

### Revised totals

| | Before | **Now** |
|---|---|---|
| P0-WP-1/2/3 | 7–9.5 d | 7–9.5 d |
| Authorization (SEC-0…SEC-5) | — | **10–16 d** |
| SS-1 station safeguards *(separate, pending approval)* | — | 1–2 d |
| **Total before Release 1.0** | 7–9.5 d | **17–25.5 d** (+1–2 d with SS-1) |

---

## 9. Limits of this clarification

- **P0-WP-1 and P0-WP-2 are verified by execution. P0-WP-3 is not** — it describes code that does
  not exist. Its tests are specified, not run. **This includes everything in §7, and every remediation in §8.**
- **§7's auto-mirror finding is read from source, not demonstrated.** Three paths
  (`server.py:4700`, `4724`, `9145`) auto-create a `police_stations` row from a `police_station`
  branch; `test_production_creates_no_stations` asserts on the table so it catches all three, but
  it has not been run.
- The diffs are **proposals**. Line numbers are correct at `389787b` and will drift.
- **Completing all three does not make the system deployable.** S-01, S-05, S-08, S-09, S-10 and
  S-11 remain open.
