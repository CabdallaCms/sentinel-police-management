# Security Issue Register — post-Stage-0 triage

**Date:** 7 November 2026 · **Baseline commit:** `e7263d7` (Stage 0) · **Report commit:** `41b4843`
**Status:** investigation and design only. **No application code was modified and no migration was
executed in producing this register.**

Severity scale: **Critical** (exploitable now, severe harm) · **High** · **Medium** · **Low**.
"Release-blocking" means Release 1.0 must not go live with the issue open.

---

## 1. Register

| ID | Issue | Severity | Release-blocking | State | Evidence |

**Evidence class:** **[E1]** execution-tested in the latest investigation · **[E2]** execution-tested earlier (reference in the evidence column) · **[C]** code-reviewed only · **[N]** not yet verified in this engagement · **[O]** resolved by owner ruling — *not an engineering evidence class*. Full traceability: `OWNER_REVIEW_PACKAGE.md` §5.

|---|---|---|---|---|---|
| **S-01** [E2] | **Cross-branch document access.** Any authenticated officer can read any uploaded document, including another branch's. | **High** | **YES** | **OPEN** — Stage 0 closed anonymous access only | `test_upload_access_control.py::test_07` returns **200** |
| **S-02** [E1] | **Admin password reset does not revoke the target's sessions** (H-5). A stolen session survives the reset. **PROVEN BY EXECUTION (9 Nov 2026):** admin `PATCH /api/admin/users/<id>` with a new password → **200**; the victim's pre-existing token still returns **200** from `/api/me`; the old password now fails and the new one works, yet **3 session rows survive**. The self-service path (`POST /api/me/password`) *does* revoke correctly — the gap is the administrator path, which never calls `revoke_user_sessions()`. | **High** | **YES** | **OPEN** → P0-WP-2 | `S08_S09_EXECUTION_VERIFICATION.md` §3.5 |
| **S-03** [C] | **Suspect alerts can never be cleared.** `alert_status` is written `'Active alert'` at INSERT and **no code path ever updates it**. A person cleared by CID keeps flagging at every checkpoint, forever. | **High** | **YES** | **OPEN** | Only `UPDATE suspect_alerts` in the codebase is `SET origin=…` (line 3232). No status transition exists. |
| **S-04** [E2] | **Suspect alerts carry no `branch_id`** (N-1), so alerts are unscoped across branches. **PROVEN BY EXECUTION (5 Nov 2026):** an Erigavo CID officer reads a Buuhoodle alert from `GET /api/suspect-alerts` — `200`, no branch clause exists in the route. Also leaks via `/api/persons/<id>`. **Severity raised Medium → High**: it is not a latent schema gap, it is a live cross-branch read. Architecture and fix: `SUSPECT_ALERT_OWNERSHIP.md` (requires schema change M-02 Phase A). | **High** *(raised)* | **YES** (coupled to S-03) | **OPEN** → M-02-A + SEC-1 | `S16_REGISTER_VERIFICATION.md` §4; `suspect_alerts` DDL line 299 |
| **S-05** [E1] | **Analytics RBAC leak** (N-3). `crimes` acts as a skeleton key: `cid.officer` receives vehicle and station analytics it has no module for; the CID bundle is ungated entirely. **PROVEN BY EXECUTION (9 Nov 2026)** across a 20-endpoint × 7-role matrix: `cid.officer` → `/api/stations/analytics` **200**, `/api/vehicles/analytics` **200**, `?module=stations|vehicles` **200**; `/api/analytics?module=all` reachable by every role and silently assembling whatever that role can touch; `/api/analytics?module=cid` has **no route-level gate** (reachable by `hr.officer`, though its sections come back empty — a gate gap, not a data leak). Root cause: the `crimes` bypass at `server.py:8396–8397`. **Severity raised Medium → High** and moved to *mandatory before production* because of **S-20**, which shares this root cause. | **High** *(raised)* | **YES** *(reclassified 9 Nov 2026 — flagged, owner may still accept the risk)* | **OPEN** | `S08_S09_EXECUTION_VERIFICATION.md` §2; §3 of this register |
| **S-06** [O] | ~~Existing databases still hold `ChangeMe123!`~~ → **R-1 (7 Nov 2026): no operational database has ever existed.** No emergency rotation is required. **Residual:** no documented production initialization exists, so the *next* install is the exposure. | **High** | **No longer** blocking on existing data; **YES** for the first production install | **REDUCED** — rotation discharged, initialization open → **P0-WP-3** | Owner decision R-1; `PRODUCTION_INITIALIZATION.md` |
| **S-07** [E2] | **N-7 — closing a disciplinary action is impossible**, so a suspended officer can never be returned to Active duty. Functional defect with a direct human consequence. | **High** (operational, not security) | **YES** for the HR module | **OPEN** | `server.py:6828`, `','.join('%s' * n)` → `'%,s,%,s,%,s'` |
| **S-08** [E1] | **No session expiry (H-3).** The `sessions` table holds only `(token, user_id, created_at)` — no expiry column anywhere, and `users` carries no lockout or idle-timeout column. **PROVEN BY EXECUTION (9 Nov 2026):** a session whose `created_at` was forced to **678 days old** returned **200** from `/api/me`, and still returned 200 **after a server restart** cleared the in-memory token cache — so the token is re-validated from storage and accepted. The aged token also read `/api/persons`, `/api/clearance-applications`, `/api/dashboard` and `/api/fingerprint/applications`. Five concurrent sessions for one account all worked; logging one out left four alive; no endpoint can enumerate them. | **High** | **YES** | **OPEN** | `S08_S09_EXECUTION_VERIFICATION.md` §3 |
| **S-09** [E1] | **No authentication throttling, no lockout, and no authentication audit (H-4).** **PROVEN BY EXECUTION (9 Nov 2026):** 30 consecutive wrong passwords → **all 401**, no 429/423, a flat 212 ms each (that is the PBKDF2 cost, which is work, not a defence); the **correct password immediately afterwards returned 200**, so no threshold exists at any value. A one-guess spray across all nine accounts met no global or per-source limit. `audit_events` went **4 → 4** across fifty failed logins and several successful ones — **neither failed nor successful authentication is audited at all**, and `/api/admin/audit` shows 0 rows mentioning login. | **High** | **YES** | **OPEN** | `S08_S09_EXECUTION_VERIFICATION.md` §4 |
| S-10 [N] | **Mutable audit log (H-7).** Deliberately **not** probed: demonstrating it proves a property of PostgreSQL table permissions, not of the application, and the open question — whether the audit store must be tamper-evident — is decision **D-04 / A-6 (legal)**. Reason recorded in `OWNER_REVIEW_PACKAGE.md` §5.3. | High | YES — needs decision D-04 | OPEN | Carried; not probed, by design |
| **S-11** [E1-partial] | **No TLS (H-8).** **MEASURED (9 Nov 2026):** the session cookie is issued `Path=/; HttpOnly; SameSite=Lax` and **without `Secure`** (`server.py:8970`), served over plaintext HTTP — so after TLS is terminated the cookie would still travel in clear. **One application change is required**, correcting the earlier description of S-11 as purely a deployment concern. TLS termination itself remains **[N]** until the staging acceptance test **TLS-1…TLS-10** is run. | **High** | **YES** | **OPEN** | `S08_S09_EXECUTION_VERIFICATION.md` §5.1–§5.2 |
| **S-12** *(new, 7 Nov)* [E2] | **One environment variable gives all nine seeded accounts the same password.** `bootstrap_password_for()` returns `SENTINEL_BOOTSTRAP_PASSWORD` **unchanged for every username**; per-account randomness happens only when it is unset. No warning is emitted. The test runner sets it to `ChangeMe123!` by design — an operator copying that into production recreates the defect Stage 0 removed. | **High** | **YES** for the first production install | **OPEN** → **P0-WP-3** | `server.py:3489`; `test_password_security.py::test_05` |
| **S-13** *(new, 7 Nov)* [E2] | **First run seeds demonstration data into any empty database** — 3 fictional persons with national IDs, 2 crime cases, 1 clearance application, 1 checkpoint event, and **1 `'Active alert'` suspect alert**. There is no production mode. Combined with **S-03**, that seeded alert **can never be cleared**. | **High** | **YES** for the first production install | **OPEN** → **P0-WP-3** | `server.py:3302` (accounts), `:3324`+ (data); alert INSERT verified |
| **S-14** *(new)* [E2] | **Branch-scope authorization fails open.** `user_branch_scope()` returns `None` both for a deliberately unrestricted session (admin / Chief) **and** for an officer whose posting is empty, misspelled, unknown or ambiguous. Every call site then skips the `WHERE branch_id=…` filter, and `require_record_branch_scope()` returns early. **Proven by execution:** an officer posted to `Zzz Nowhere Posting` listed records from every branch (3 vs 1), opened another branch's record (**200** where a correctly-posted officer got **403**), and **filed a new record into another branch** (**201**, landed in branch 11). | **CRITICAL** | **YES** | **OPEN** — release blocker | `BRANCH_SCOPE_FAIL_OPEN.md` §3, probes P1–P4; `server.py:2790`, `2742`, `8465`, `8481`, `8524`, `8544`, `8563`, `8837` |
| **S-15** *(new)* [E1] | **`/api/crimes` scopes on the wrong unit type.** The list filters on `user_branch_scope(…, 'police_station')` (`server.py:8837`) while `register_crime()` stores a **`crime`** branch id (`server.py:5288`). Measured on one CID session: `/api/crime-cases` → `branch_id=2`, `/api/crimes` → `branch_id=5`; the id sets are disjoint. **Fails closed today** (a posted CID officer sees zero incidents) but **becomes a total disclosure of the crime register if A-18 removes the `police_station` branch rows first.** **FULLY PROVEN BY EXECUTION (5 Nov 2026):** posted CID officers at Buuhoodle (scope `police_station`=5) and Erigavo (=15) each returned **0 of 1** incidents, including their own branch's; unresolvable and missing postings returned **1 of 1** with `branch_scope=None`, indistinguishable from the administrator. Deleting the 3 `police_station` branch rows in a disposable database moved both posted officers from **0 rows to 8 (all)** — the A-18 blocker is measured, not inferred. No direct-ID endpoint exists (`/api/crimes/<id>` → 404), and the `WHERE` clause is correct when the ids align (1 of 9). | **High** | **YES** — ordering constraint on A-18 | **OPEN** → SEC-3 (needs SEC-2) | `S15_EXECUTION_VERIFICATION.md`; `BRANCH_SCOPE_FAIL_OPEN.md` §4, probe P5 |
| **S-16a** *(new)* [E2] | **`GET /api/persons/<id>` applies NO module, branch or location filtering to the unit records it attaches.** The route is deliberately not module-gated (`server.py:8374`), yet the handler attaches four unit registers — `clearance_applications`, `airport_passengers`, `suspect_alerts`, `checkpoint_events` — each an unfiltered `WHERE person_id=%s` (`:8449–8461`). **Proven by execution:** `cp.south` (modules `['checkpoints','dashboard']`) was refused `/api/clearance-applications` with **401** yet received application `FP-40964580` from `/api/persons/<id>` (**200**); and a **correctly posted** Fingerprint officer, whose scoped list excluded the record and whose direct fetch returned **403**, received it here. The sibling `/linked-records` filtered correctly (`units_returned=[]`) — the omission is local to this handler. **No precondition: needs no misconfiguration.** | **CRITICAL** | **YES** | **OPEN** → SEC-1 | `AUTHORIZATION_REMEDIATION_PLAN.md` §2, probes Q1–Q4 |
| **S-16b** *(new)* [E2] | **The three sibling person endpoints apply module and checkpoint-location filtering but NO branch filtering.** `linked_person_records()`, `person_document_records()` and `person_audit_history()` each gate sources on `user_module_set(user)` and apply `checkpoint_scope_sql(...)`, but return `branch_id`/`branch_name` purely as display metadata and never constrain on them. A correctly posted officer therefore sees other branches' records through `/linked-records`, `/documents` and `/audit-history`. **PROVEN BY EXECUTION (5 Nov 2026):** an Erigavo Fingerprint officer filtered out of `/api/clearance-applications` still receives the Buuhoodle record from `/linked-records`; same result for Airport. **`/documents` and `/audit-history` also PROVEN (5 Nov 2026):** an Erigavo Fingerprint officer receives a Buuhoodle application's 4 documents and its clearance audit events in full, identical to the owning officer, while the module gate correctly returns 0 to a checkpoint officer — so only the branch dimension is missing. **All three sibling endpoints measured.** | **High** | **YES** | **OPEN** → SEC-1 | `S16_REGISTER_VERIFICATION.md` §2–§3; tests T-41…T-43 |
| **S-17** *(new)* [E1] | **`crime_incidents.branch_id` accepts NULL from the API.** `register_crime()` calls `resolve_branch(..., 'crime')` without `required=True` (`server.py:5288`), so omitting `branch_id` stores **NULL**. **PROVEN:** `POST /api/crimes` with no `branch_id` → **201**, stored `branch_id=NULL`. A NULL-branch incident is invisible to every scoped officer and visible to every unscoped one, permanently. | **High** | **YES** | **OPEN** → SEC-3 (no extra estimate) | `S15_EXECUTION_VERIFICATION.md` §4, §5 |
| **S-18** *(new)* [E1] | **Cross-branch and cross-region crime filing accepted from a scoped account.** `register_crime()` has **no `require_branch_write_scope()` call at all**, unlike airport (`:9215`) and checkpoint (`:9511`). **PROVEN:** a Buuhoodle-scoped CID officer filed under **Erigavo** crime branch 12 → **201**, stored `branch_id=12`; also accepted against stations in Sanaag and Sool. Server-side, not a frontend gap. | **High** | **YES** | **OPEN** → SEC-3 (no extra estimate) | `S15_EXECUTION_VERIFICATION.md` §4 |
| **S-19** *(new)* [E1] | **Crime file numbers encode the station region, not the filing branch.** `new_crime_file_number()` (`:4737`) builds `CRM-<year>-<station code>-NNNN`. **PROVEN:** a Buuhoodle-posted officer produced `CRM-2026-SAN-C-01-0006` — a permanent identifier asserting Sanaag. Record-integrity issue overlapping SS-1; needs an owner view, not a code fix alone. | **Medium** | Not release-blocking | **OPEN** | `S15_EXECUTION_VERIFICATION.md` §4, §5 |
| **S-20** *(new)* [E1] | **The officer register leaks to the CID unit.** `ROLE_CID` holds `{dashboard, people, cid, crimes}` and **no `officers` module**, yet **`GET /api/officers` returns 200** with the full register. **PROVEN BY EXECUTION (9 Nov 2026):** the payload carries `date_of_birth`, `mother_name`, `place_of_birth`, `contact_number` and the **`guarantor_name`, `guarantor_address` and `guarantor_contact` of a third-party civilian** who never dealt with the CID unit. Cause: the `crimes` bypass at `server.py:8396–8397` skips `require_module()`, and the `/api/officers` handler (`:8833`) has no internal gate of its own. **Same root cause and same one-line fix as S-05 — costed once, inside S-05's 2–4 days; no double-counting.** Negative controls passed: HR analytics, discipline, promotions and conduct are correctly refused to CID/FP/AP/CP, and `/api/admin/*` is refused to every role but `admin`. | **High** | **YES** | **OPEN** | `S08_S09_EXECUTION_VERIFICATION.md` §2.2, §2.4 |

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

> **DECISIONS RECORDED 9 November 2026.** All eight owner decisions are approved
> (`DECISION_REGISTER.md` §1A). **S-04** is unblocked for remediation (D-1a, D-4, D-7 → M-02-A).
> **S-03 remains blocked by one decision only**: D-4b approved withdrawal but **only for the
> authorized Crime Unit supervisor**, and the system cannot yet identify that person — **D-21**
> (`security/OWNER_DECISION_SHEET_D21.md`). **D-23.6 closed 9 Nov 2026**: five states, `Closed`
> excluded, A-13 writes **`Withdrawn`**; adopting the approved `Active` spelling adds package
> **M-02-B** (0.75–1.25 d) because the code stores `'Active alert'` in 14 places. **S-19** is now covered by a mandatory SS-1 (D-5). **No finding's severity or
> release-blocking status changed**, and no finding was closed by a decision — an owner ruling is
> not execution evidence.
>
> **Remediation planning for every row in this register is specified in
> `SECURITY_REMEDIATION_PROGRAMME.md` §2** (root cause, affected endpoints, required change,
> dependencies, mandatory-before-production, negative tests, effort), and the decisions that gate
> it in `OWNER_DECISION_PACKAGE_R1.md`. **This register remains the authoritative list of findings,
> severities and evidence classes.**

Release-blocking and still open: **S-16a, S-16b, S-14, S-15, S-04, S-17, S-18** (authorization — all
now proven by execution), **S-01, S-02, S-03, S-07**, **S-12, S-13** (first production install),
plus the carried items
**S-08, S-09, S-10, S-11** (**S-08, S-09 and the S-11 cookie finding are now proven by execution —
9 Nov 2026**; S-10 remains unprobed by design), **S-05** and **S-20** (reclassified 9 Nov 2026),
and **H-2b** (checkpoint scope — now proven by execution on all three
counts: no branch filter, unrecognised locations accepted and stored as fabricated codes, and
`South` matching `Southwest` by substring).
~~**S-05** should be fixed before release but is not itself a gate.~~
**CORRECTED 9 Nov 2026 — S-05 and the new S-20 ARE release-blocking.** Execution showed a CID
officer with no `officers` module reading the full officer register, including officers' dates of
birth and mothers' names and the name, home address and telephone number of their civilian
guarantors (`S08_S09_EXECUTION_VERIFICATION.md` §2.2). Sensitive police information reachable
outside authorized roles may not be deferred without an explicit recorded risk acceptance. The
original sentence is struck through rather than deleted so the change of position stays visible.
**S-06** is **reduced** by R-1 — no rotation needed; its live residual is S-12/S-13.

| Band | Items | Days |
|---|---|---|
| **SEC** — authorization, **first** | **SEC-0** unified model · **SEC-2** S-14 · **SEC-3** S-15 · **SEC-4** H-2b/checkpoint · **M-02-A** alert `branch_id` · **SEC-1** S-16a/b + alert reads (**last** — depends on SEC-4 and M-02-A) · **SEC-5** staging diagnostics | **11–17.5** |
| **SS-1** — station safeguards, **separate, awaiting approval** | G-a…G-d | 1–2 |
| **P0** — approve now | S-07, S-02, (S-06 residual + S-12 + S-13) | 5–6.5 *(7–9.5 with A-11a/A-13)* |
| **P1** — release-blocking | S-01, S-03, S-04, S-05, S-08, S-09 | 23–37 |
| **P2** — before deployment | S-10 *(D-04)*, S-11, full lifecycle *(D-23)* | 34–57 |

> **Do not add these bands together, and do not reuse the 23–37 figure as a pre-production
> subtotal.** They are the original `REMEDIATION_PLAN.md` groupings and they overlap the SEC band:
> **S-04** appears in P1 at 4–6 d *and* in the SEC band as **M-02-A** at 1–1.5 d, and **S-05**
> appears in P1 while also being tracked separately. Revision 2 of the owner-review package quoted
> 23–37 as "the additional work before production" and was wrong by exactly that overlap. **The
> authoritative, non-overlapping classification and totals are now
> `SECURITY_REMEDIATION_PROGRAMME.md` §3, which re-derives them from the individual work items
> W-01…W-80 and tabulates every double-count:
> **updated 9 Nov 2026 after the owner decisions — 14–21 d before staging, +26.75–44 d before
> production, 40.75–65 d in total.** The increase over the previously published 37–59 is entirely
> A-13's re-scope under **D-4b** (+2 – 3.25 d) and **SS-1** becoming mandatory under **D-5**
> (+1 – 1.5 d), plus **M-02-B** under **D-23.6** (+0.75 – 1.25 d); no package was re-estimated. These band rows are kept
> unaltered as the historical record of how the work was first grouped.

**Ordering constraint:** **SEC-0 → SEC-2 → SEC-3 → A-18.** *(Corrected: this line previously read
"SEC-1 → SEC-2 → SEC-3", which went stale when SEC-1 moved last in revision 3. SEC-1 depends on
SEC-4 and M-02 Phase A and does not gate A-18.)* Implementing A-18 first would remove the
`police_station` branch rows, leaving `/api/crimes` with no `WHERE` clause — converting an
accidental fail-closed into disclosure of the whole crime register.

**Nothing in this register has been fixed.** This document is investigation and design only. P0 is
specified to implementation detail in `P0_WORK_PACKAGES.md` and awaits approvals **A-10, A-11,
A-16…A-19**; the SEC packages await approval of `AUTHORIZATION_REMEDIATION_PLAN.md`.
