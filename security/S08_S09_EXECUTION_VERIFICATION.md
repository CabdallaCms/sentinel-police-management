# Execution verification — S-05, S-08, S-09 (and S-11 transport evidence)

**Date:** 9 November 2026 · **Status:** MEASURED, not inferred
**Method:** disposable PostgreSQL cluster (`pgserver`), a real `backend/server.py` process, real
HTTP, the nine seeded role accounts, two disposable officer records.
**Probe:** `backend/zz_sec_probe.py` — throwaway, run once, **deleted after the run**.
**Raw output:** reproduced verbatim in §6.

> **Why this document exists.** Revision 2 of the owner-review package classified S-08, S-09,
> S-10 and S-11 as **[N] — not verified in this engagement**, carried from the Phase 2 static
> register. The owner directed that S-08 and S-09 be executed and that S-05 be reassessed. This
> document records what was measured. **S-10 remains [N]** — see §5.4.

---

## 1. What was and was not touched

| | |
|---|---|
| Database | A temporary cluster created for the run and destroyed with it. **No existing database was opened.** |
| Application code | **None modified.** `backend/server.py` sha256 `a8211f4f…b3b9fc`, unchanged before and after. |
| Schema / migrations | **None.** The probe only ran `SELECT`, plus `INSERT`/`UPDATE` of its own disposable rows. |
| Fixtures | Two officer rows (`POL-PROBE-01/02`) SQL-seeded into the throwaway database. **Disclosed** — see §5.5. Every *measurement* below is a real HTTP request. |
| Probe file | Deleted. The working tree is clean. |

---

## 2. S-05 — analytics and cross-module RBAC. **Reassessed: materially worse than recorded.**

### 2.1 The status matrix (measured)

`200` = the role reached the endpoint. `401` = refused. Roles are the seeded accounts; their
modules come from `ROLE_MODULES` (`server.py:1865`).

| Endpoint | cid.officer | fp.officer | ap.officer | cp.south | hr.officer | chief | admin |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `/api/officers` | **200** | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/officers/analytics` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/officers/discipline` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/officers/promotions` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/conduct` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/stations` | **200** | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/stations/analytics` | **200** | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/vehicles` | 200 | 401 | 401 | 200 | 200 | 200 | 200 |
| `/api/vehicles/analytics` | 200 | 401 | 401 | 200 | 200 | 200 | 200 |
| `/api/cid/analytics` | 200 | 200 | 200 | 200 | 401 | 200 | 200 |
| `/api/analytics?module=officers` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/analytics?module=hr` | 401 | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/analytics?module=stations` | **200** | 401 | 401 | 401 | 200 | 200 | 200 |
| `/api/analytics?module=vehicles` | 200 | 401 | 401 | 200 | 200 | 200 | 200 |
| `/api/analytics?module=cid` | 200 | 200 | 200 | 200 | **200** | 200 | 200 |
| `/api/analytics?module=global` | 401 | 401 | 401 | 401 | 401 | 200 | 200 |
| `/api/analytics?module=all` | **200** | 200 | 200 | 200 | 200 | 200 | 200 |
| `/api/analytics/global` | 401 | 401 | 401 | 401 | 401 | 200 | 200 |
| `/api/admin/analytics` | 401 | 401 | 401 | 401 | 401 | 401 | 200 |
| `/api/admin/users` | 401 | 401 | 401 | 401 | 401 | 401 | 200 |

### 2.2 The finding that changes S-05's severity

`ROLE_CID` holds `{dashboard, people, cid, crimes}` — **no `officers` module**. It nevertheless
reads the officer register:

```
cid.officer  GET /api/officers -> 200, 2 officer records, personal fields present:
  ['contact_number', 'date_of_birth', 'duty_status', 'full_name', 'guarantor_address',
   'guarantor_contact', 'guarantor_name', 'mother_name', 'place_of_birth', 'service_id']
```

**That is police officer personal data**, not operational metadata: date of birth, mother's name,
place of birth, personal contact number, and the **name, home address and telephone number of the
officer's guarantor** — a third-party civilian who never interacted with the CID unit. It is also
exactly the data set used elsewhere in this system to verify identity.

**Root cause (one line).** `server.py:8396–8397`, inside the GET module gate:

```python
if prefix in ('/api/stations', '/api/officers') and 'crimes' in (user.get('modules') or []):
    break          # <- skips require_module() entirely
```

The `crimes` module was given a bypass so the crime-intake form could populate its station
dropdown. The same bypass covers `/api/officers`, which has **no internal gate of its own**
(`server.py:8833` is a bare `SELECT`).

### 2.3 Everything else the matrix establishes

- **`cid.officer` receives the station and vehicle analytics bundles** it has no module for —
  confirming the original S-05 text by execution: `/api/stations/analytics` returns
  `active_stations`, `inactive_stations`, `average_cell_capacity`, `largest_deployment`,
  `active_officers_deployed`, `border_posts`, `checkpoints`, `district_hq`;
  `/api/vehicles/analytics` returns `flagged_vehicles`, `alert_rate`, `impounded`,
  `civilian_flagged`, `decommissioned`, `in_service`.
- **`/api/analytics?module=all` is reachable by every authenticated role** and silently assembles
  whatever that role can reach: `cid.officer` → `['cid', 'stations', 'vehicles']`,
  `cp.south` → `['cid', 'vehicles']`, `fp.officer` → `['cid']`.
- **`/api/analytics?module=cid` has no route-level gate at all.** `hr.officer` — who is refused
  `/api/cid/analytics` with 401 — gets **200** from the `?module=cid` alias. The payload comes
  back with `sections: []`, so **no CID data escaped**; the *gate* is missing, the *data* was
  still filtered by the per-section check inside `build_cid_analytics` (`server.py:6578`).
  **Recorded precisely: a gate gap, not a data leak.**

### 2.4 Negative controls that PASSED (the measurement is not uniformly red)

| Control | Result |
|---|---|
| HR analytics / discipline / promotions / conduct refused to CID, FP, AP, CP | **401 — correct** |
| `/api/admin/analytics` and `/api/admin/users` refused to every role except `admin` — **including `chief`** | **401 — correct** |
| Global executive bundle (`?module=global`, `/api/analytics/global`) restricted to `chief` + `admin` via `analytics:global` | **correct** |
| `fp.officer` and `ap.officer` receive **only** their own section from `?module=all` | **correct** |
| `cp.south` reaching `/api/vehicles*` | **by design** — `checkpoints` is in the documented OR-list; a checkpoint officer needs vehicle lookups. Not counted as a leak. |

### 2.5 Consequence for classification

Revision 2 placed S-05 in *permitted after Release 1.0* at **Medium**. On the measured evidence
that is no longer defensible: **personal data of police officers and of their civilian guarantors
is readable by a role with no HR module.** Under the owner's standing instruction, this cannot be
classified as safe to defer without an explicit, recorded risk acceptance.

- **S-05 is re-rated Medium → High** and moved to *mandatory before production Release 1.0*.
- The officer-register half is recorded as a **new finding, S-20**, because it exposes a different
  data class (personal data) than the analytics aggregates S-05 describes. **Same root cause, same
  one-line fix — it is costed once, inside S-05's 2–4 days. No double-counting.**
- This is a **classification change, flagged**, exactly as D-4b was. It is not a decision taken on
  the owner's behalf: the owner may still elect deferral with a signed risk acceptance.

---

## 3. S-08 — session lifetime, revocation and concurrency. **CONFIRMED by execution.**

### 3.1 Structure

```
sessions table columns: ['token', 'user_id', 'created_at']
users columns related to expiry/lockout: NONE
```

There is no `expires_at`, no `last_seen_at`, no `absolute_deadline`, and no lockout column
anywhere. `require_auth()` (`server.py:4256`) resolves a token through `TOKENS` then
`SELECT user_id FROM sessions WHERE token=%s` — **no time predicate on either path.**

### 3.2 Token expiry — a 678-day-old session is still valid

| Step | Result |
|---|---|
| Issue a token, force its `sessions.created_at` to `2025-01-01` (**678 days old**) | — |
| `GET /api/me` with the in-memory cache warm | **200** |
| **Restart the server** (clears the `TOKENS` cache so only the database path can answer) | — |
| `GET /api/me`, database path only | **200** |

The restart matters: it proves the token is not merely cached, but **re-validated from storage and
accepted**, so no expiry exists in either code path.

### 3.3 The aged token reaches protected police data

| Endpoint | Status |
|---|---|
| `/api/persons` | **200** |
| `/api/clearance-applications` | **200** |
| `/api/dashboard` | **200** |
| `/api/fingerprint/applications` | **200** |

### 3.4 Concurrent sessions

| Measurement | Result |
|---|---|
| Five consecutive logins for one account | **5 distinct tokens** |
| All five used simultaneously | `[200, 200, 200, 200, 200]` |
| Rows in `sessions` for that user | **6** (five plus one earlier) |
| Log out token #1 | `[401, 200, 200, 200, 200]` — the other four survive |

**No cap, no eviction, no enumeration.** There is no endpoint that lists a user's active sessions,
so neither the officer nor an administrator can see that five sessions exist, let alone which
device holds them. Logout revokes only the token presented.

### 3.5 Password-change revocation — one path works, the other does not

| Path | Measured |
|---|---|
| **Self-service** `POST /api/me/password` | changer's session **200**, other browser **401** — **the Stage 0 / N-8 fix works** |
| **Administrator reset** `PATCH /api/admin/users/<id>` with `{"password": …}` | **200**; victim's pre-existing token still **200**; old password now 401, new password 200; **3 session rows still present** |

**This is finding S-02 — "Admin password reset does not revoke the target's sessions (H-5)" — and
it is now proven by direct measurement rather than inferred from a unit test.** The operational
meaning is the one case that matters: when an account is *known to be compromised*, the
administrator's reset changes the password and **leaves the attacker's session fully alive**.
`PATCH /api/admin/users/<id>` writes `password_hash` (`server.py:~10008`) and never calls
`revoke_user_sessions()`, which only the self-service branch (`server.py:9053`) invokes.

### 3.6 Control — one emergency lever does work

Deactivating the account (`PATCH …{"active": false}`) causes the existing token to fail with
**401** at the next request, because `require_auth()` re-reads `WHERE id=%s AND active=1` on every
call. So there *is* a way to evict a compromised session — but it disables the officer's account
entirely, which is a blunt instrument during an active shift.

### 3.7 Effect on the estimate

**2–3 days stands**, with one correction to revision 2: an **idle** timeout needs a new column
(`last_seen_at`), so S-08 is **not purely a code change** — it carries a small additive migration
and therefore falls under the D-7 migration-safety procedure. An **absolute** timeout alone could
be computed from the existing `created_at` with no DDL. That choice is an engineering option, not
an owner decision, and is noted so the schedule is not surprised by it.

---

## 4. S-09 — authentication throttling and audit. **CONFIRMED by execution.**

### 4.1 Repeated failed logins

| Measurement | Result |
|---|---|
| 30 consecutive wrong passwords for an existing account | **all 401** — no `429`, no `423`, no lockout |
| Elapsed | 6.4 s total, **212 ms per attempt**, flat from attempt #1 to #30 |
| 20 consecutive attempts against a non-existent username | **all 401** |
| **Correct password immediately after the 30 failures** | **200** |

The flat 212 ms is the PBKDF2 verification cost delivered in Stage 0 — **it is work, not a
defence**. There is no progressive delay: attempt #30 is as fast as attempt #1. The successful
login at the end is the decisive measurement: **no protection threshold exists at any value**,
because if one existed the account would have been locked before the legitimate attempt.

Single-connection throughput is ≈4.7 guesses/second ≈ **407,000 per day from one client**, and
nothing observed prevents running many clients in parallel.

### 4.2 Password spray

One guess (`Password1`) against all nine accounts: `{admin: 401, fp.officer: 401, ap.officer: 401,
cid.officer: 401, hr.officer: 401, cp.south: 401, cp.east: 401, cp.west: 401, chief: 401}`.
No global limit and no per-source limit was encountered. A spray is the attack PBKDF2 does not
mitigate, because it never repeats against one account.

### 4.3 Authentication is not audited **at all**

| Measurement | Result |
|---|---|
| `audit_events` rows before the burst | **4** |
| `audit_events` rows after 50 failed logins and several successful ones | **4** |
| Rows whose action/entity mentions login, auth or session | **NONE** |
| `GET /api/admin/audit?limit=200` | 200 OK, 4 rows, **0 mentioning "login"** |

**Neither failed nor successful authentication produces an audit record.** A sustained attack
leaves no trace, and after an incident there is no way to establish who signed in, from where, or
when. For a police system this is an accountability failure as much as a security one: the audit
register can attribute a *record change* to a user, but cannot establish that the user's
**session** was legitimately established.

### 4.4 Effect on the estimate

**2–3 days stands.** The measurement sharpens the content: S-09 must deliver throttling *and* the
authentication audit event, because the audit half is currently at zero, not merely thin.

---

## 5. S-11, S-10, and the limits of this evidence

### 5.1 S-11 — what was measured

```
Set-Cookie: sentinel_session=<token>; Path=/; HttpOnly; SameSite=Lax
Secure flag present : False
HttpOnly present    : True
SameSite present    : True
served over         : http (plaintext)
```

**`HttpOnly` and `SameSite=Lax` are set; `Secure` is not** (`server.py:8970`). This corrects a
statement in revision 2 §1.3, which called S-11 *"not an application task"*. It is **mostly**
infrastructure, but **one application change is required**: without the `Secure` attribute the
session cookie will still be transmitted over plain HTTP after TLS is terminated, so the
termination alone does not close the finding. The 2–4 day estimate is unchanged; its composition
is corrected.

### 5.2 S-11 — staging HTTPS acceptance test (specification, not yet executed)

This cannot be executed here: there is no TLS terminator, certificate or DNS name in this
environment. It is written so it can be run against staging unchanged.

| # | Test | Method | Pass condition |
|---|---|---|---|
| **TLS-1** | Plaintext is not served | `curl -sS http://<host>/api/health` | Connection refused, **or** `301`/`308` to `https://<host>/api/health`. Never a `200` over HTTP |
| **TLS-2** | HTTPS serves the application | `curl -sS https://<host>/api/health` | `200` |
| **TLS-3** | Certificate validates | `curl` with default CA bundle (no `-k`) | No verification error; CN/SAN matches the host; not expired; chain complete |
| **TLS-4** | Protocol floor | `openssl s_client -tls1_1` then `-tls1_2`, `-tls1_3` | TLS 1.0/1.1 **refused**; 1.2 and/or 1.3 accepted |
| **TLS-5** | Session cookie is `Secure` | Log in over HTTPS, inspect `Set-Cookie` | Contains `Secure`, `HttpOnly`, `SameSite` — **this is the application change in §5.1** |
| **TLS-6** | Cookie never travels in clear | Log in over HTTPS, then request `http://<host>/api/me` with the cookie jar | The cookie is **not** sent; the response is a redirect or refusal, not `200` |
| **TLS-7** | HSTS | Inspect HTTPS response headers | `Strict-Transport-Security: max-age≥15552000; includeSubDomains` |
| **TLS-8** | Uploads are protected too | Fetch an `/uploads/<file>` URL over HTTP | Refused or redirected — documents must not be retrievable in clear |
| **TLS-9** | Login credentials in clear | Packet capture on the server interface during one login | No cleartext username/password/token observable |
| **TLS-10** | Mixed content | Load `index.html` over HTTPS, read the browser console | No mixed-content warnings; no absolute `http://` asset or API URL |

**Required infrastructure controls (owner/IT, not engineering):** a terminating reverse proxy
(nginx/Caddy/managed load balancer) in front of `server.py`; a certificate with a renewal
procedure and an expiry alarm; the application bound to loopback or a private interface so it
cannot be reached without passing the terminator; HTTP→HTTPS redirection at the edge; HSTS once
TLS is stable; and a documented owner for certificate renewal. **None of these is in this
repository**, which is why TLS-1…TLS-10 are an acceptance test for staging and not a code change.

### 5.3 What S-11 evidence class this earns

**[E1-partial].** The cookie-flag and plaintext facts are measured. TLS termination itself is a
deployment property of an environment that does not exist yet and is therefore **[N] until
TLS-1…TLS-10 are run in staging.** Both halves are stated rather than averaged into one
comfortable label.

### 5.4 S-10 remains [N] — and why that is the honest answer

S-10 (mutable audit log) was **not** probed. Demonstrating it is trivial — an `UPDATE
audit_events …` succeeds because nothing prevents it — but that would prove a property of
PostgreSQL permissions, not of the application, and the finding's real question is **whether the
audit store must be tamper-evident**, which is decision **D-04 / A-6 (legal)**. Running a probe
would produce evidence that does not move the decision. **It stays [N], and the reason is
recorded rather than disguised.**

### 5.5 Disclosed limitations of this run

1. **Two officer rows were SQL-seeded**, because `POST /api/officers` is a multipart flow and the
   point of §2.2 was *who can read the register*, not who can write it. Every access measurement
   in §2 is a real HTTP request made by a real logged-in role account.
2. **The 678-day age in §3.2 was created by updating `sessions.created_at`**, not by waiting. This
   is the only way to test an absolute lifetime in one run. It proves the absence of a check on
   that column — which is the finding.
3. **Nine seeded accounts were used**, not production identities. `ROLE_MODULES` is role-derived,
   so the matrix generalises to any holder of those roles; it does **not** generalise to roles
   that do not exist in the seed (there are none outstanding).
4. **Throughput in §4.1 was measured on a loopback connection** in a sandbox. Real-world rates
   will differ with network latency and server hardware; the *absence* of throttling does not.
5. **No negative control is possible for "throttling exists"** — the control is the successful
   login in §4.1, which demonstrates the absence directly.

---

## 6. Raw probe output (verbatim)

```text
database: temporary pgserver PostgreSQL cluster
logged in: 8 seeded role accounts
seeded 2 disposable officers (1 Active, 1 Suspended)

PART B — S-08 session lifetime, revocation, concurrency
B.1 sessions table columns: ['token', 'user_id', 'created_at']
    users columns related to expiry/lockout: NONE

B.2 token expiry
    session created_at forced to 2025-01-01 00:00:00 (≈678 days old)
    aged token -> GET /api/me (TOKENS cache warm) : 200
    server restarted (in-memory TOKENS cache cleared)
    aged token -> GET /api/me (DB path only)       : 200

B.3 aged token against protected endpoints
    /api/persons                         : 200
    /api/clearance-applications          : 200
    /api/dashboard                       : 200
    /api/fingerprint/applications        : 200

B.4 concurrent sessions for one account
    5 logins -> 5 distinct tokens
    simultaneous /api/me statuses: [200, 200, 200, 200, 200]
    rows in sessions for ap.officer: 6
    after logging out token[0]: [401, 200, 200, 200, 200]

B.5 SELF-SERVICE password change (expected: revokes other sessions)
    POST /api/me/password (session A) -> 200 {'ok': True, 'password_changed': True}
    session A (changer)      -> /api/me : 200
    session B (other browser)-> /api/me : 401

B.6 ADMIN password reset (PATCH /api/admin/users/<id>)
    admin PATCH password -> 200
    victim OLD token after admin reset -> /api/me : 200
    login with OLD password: 401   login with NEW password: 200
    sessions rows still present for cp.south: 3

B.7 control — admin deactivation (active=0)
    token after active=0 -> /api/me : 401

PART C — S-09 authentication throttling and audit
C.1 repeated failed logins, existing account (fp.officer)
    30 attempts in 6.4s (212 ms each)
    distinct statuses: [401]  (429/423 would indicate throttling)
    attempt #1=401  #15=401  #30=401

C.2 repeated failed logins, non-existent account
    20 attempts, distinct statuses: [401]

C.3 legitimate login AFTER the failed-attempt burst
    correct password -> 200  (200 proves no lockout threshold exists)

C.4 password spray — one guess against every account
    statuses: {'admin': 401, 'fp.officer': 401, 'ap.officer': 401, 'cid.officer': 401,
               'hr.officer': 401, 'cp.south': 401, 'cp.east': 401, 'cp.west': 401, 'chief': 401}
    (no source-IP or global rate limit was encountered)

C.5 audit trail for authentication
    audit_events rows before burst: 4, after: 4
    authentication-related audit rows: NONE
    last 5 audit rows: [('UPDATE','user'), ('UPDATE','user'), ('UPDATE','user'),
                        ('UPDATE','user_password')]
    /api/admin/audit -> 200, 4 rows, 0 mentioning "login"

PART D — S-11 transport evidence (cookie flags)
    Set-Cookie: sentinel_session=<redacted>; Path=/; HttpOnly; SameSite=Lax
    Secure flag present : False
    HttpOnly present    : True
    SameSite present    : True
    scheme actually served: http (plaintext)

PROBE COMPLETE
```

*(Part A's full matrix is reproduced in §2.1 rather than duplicated here.)*

---

## 7. Findings arising from this run

| ID | Statement | Severity | New or confirming |
|---|---|---|---|
| **S-05** | Analytics RBAC leak — confirmed; **re-rated Medium → High**; now *mandatory before production* | **High** | Confirming, re-rated |
| **S-20** | **`GET /api/officers` returns the full officer register — including date of birth, mother's name, personal contact number and guarantor name/address/telephone — to `ROLE_CID`, which holds no `officers` module.** Same root cause as S-05 (`server.py:8396–8397`); fixed by the same change and costed once inside S-05's 2–4 days | **High** | **NEW** |
| **S-08** | No session expiry — confirmed by execution; a 678-day-old session survives a server restart and reads police data | **High** | Confirming, now [E1] |
| **S-09** | No throttling, no lockout, **no authentication audit whatsoever** — confirmed by execution | **High** | Confirming, now [E1] |
| **S-02** | Administrator password reset does not revoke the target's sessions — now proven by direct HTTP measurement, not inferred | **High** | Confirming, upgraded to [E1] |
| **S-11** | Cookie lacks `Secure`; served in plaintext — measured. TLS termination itself still unverified | **High** | Confirming, [E1-partial] |
| **S-10** | Not probed. Deliberately — the open question is legal (D-04), not technical | **High** | Unchanged **[N]** |

**No estimate increased as a result of this run.** S-05 moved bands; nothing was re-costed, and
S-20 adds no days because it shares S-05's one-line fix.
