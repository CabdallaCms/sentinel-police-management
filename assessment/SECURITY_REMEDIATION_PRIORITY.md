# Security Remediation Priority List

**Deliverable 5 of 8 · Phase 2 · Assessment only — no vulnerability was fixed, and no application code was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · commit `a1c2478` · 2026-11-06
All line references are to `backend/server.py` at `a1c2478` unless another file is named.

---

## 0. How to read this list

### 0.1 Evidence classes — static vs runtime

| Class | Meaning |
|---|---|
| **[STATIC]** | Confirmed **this session** by reading the code at `a1c2478`. A static finding proves the *defect in the code*; it does **not** prove exploitation against a live deployment. |
| **[RUNTIME-HISTORICAL]** | The earlier audit on PR #23 reported reproducing this against a running instance at commit `381545c` (the immediate **parent** of `a1c2478`). It is **evidence from a previous run**, not a re-verification, and it was **not** reproduced in this session. |
| **[RUNTIME-2026-11-06]** | Executed in this session. Only two checks were runnable: `python3 backend/server.py --ui-check` → **exit 0**, and `backend/test_print_fit.py` → **PASS**. **Neither is a security test.** |
| **[NOT VERIFIED]** | Outcome depends on deployment data or configuration that this repository does not contain. |

> **Why no runtime security verification was performed.** The test suites require `psycopg2-binary`, `pgserver` and `jsdom@26`; none are installed, and installing dependencies is outside the approved scope. **No finding below carries a 2026-11-06 runtime proof.** Every finding marked [STATIC] must be re-confirmed against a live instance before it is signed off as fixed.

### 0.2 Identifier bands — and a correction

| Band | Origin |
|---|---|
| `C-n`, `H-n`, `M-n` | **Inherited from the earlier deployment audit** (PR #23, branch `arena/8834f56d-…` @ `7da888b`, `DEPLOYMENT_AUDIT.proposed.md`, audited revision `381545c`), as carried into `PROJECT_STATUS.md` §6. **These identifiers are preserved exactly.** `H-2` is the only one split — into **H-2a** and **H-2b** — because two distinct defects sit behind one audit finding, and `PROJECT_STATUS.md` §6 already records that split. |
| `N-n` | **New in this assessment** — genuinely absent from the earlier audit. Numbered in a separate band so that **no audit identifier is reused or reassigned**. |

> **Recorded correction.** An earlier draft of this document reassigned several audit identifiers (for example, using `H-5` for the approval endpoint and `H-6` for administrative controls). That conflicted with the audit's own numbering as published in `PROJECT_STATUS.md` §6 — where **H-4** is login throttling, **H-5** is administrator self-demotion, **H-6** is identifier races, **H-7** is the audit trail and **H-8** is transport security. **The audit's numbering is authoritative and has been restored here.** The conflict is reported rather than silently resolved, per the project's documentation rules. The audit report in PR #23 and its history remain untouched.

### 0.3 Severity

Severity below is **this assessment's rating**, based on the code at `a1c2478`. Where it differs from the band implied by the audit's identifier prefix, the difference is stated explicitly — the identifier is never changed to match.

| Severity | Definition in this context |
|---|---|
| **CRITICAL** | Exposes police records or accounts to an unauthenticated party, or compromises every account at once. |
| **HIGH** | Lets an authenticated officer read or alter records outside their lawful authority, or defeats accountability for a privileged action. |
| **MEDIUM** | Weakens a control that is present, or exposes aggregate/derived information beyond scope. |
| **LOW** | Hardening gap with no direct path to records at present. |

---

## 1. Priority summary

| Rank | ID | Finding | Severity | Class |
|---|---|---|---|---|
| 1 | **C-1** | Uploaded police documents retrievable without authentication | CRITICAL | [STATIC] + [RUNTIME-HISTORICAL] |
| 2 | **C-2** | Shared default credentials on nine seeded accounts, published in `README.md` | CRITICAL | [STATIC] + [RUNTIME-HISTORICAL] |
| 3 | **C-3** | Unsalted single-round SHA-256 password hashing | CRITICAL | [STATIC] + [RUNTIME-HISTORICAL] |
| 4 | **H-2b** | Branch scope **fails open** when an officer's posting does not resolve | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 5 | **M-2** | Checkpoint location scope **fails open** for the canonical role (read **and** write) | **HIGH** — *re-rated up from the audit's Medium* | [STATIC] + [RUNTIME-HISTORICAL] |
| 6 | **H-2a** | Cross-branch approval, signed-scan attachment and person-document listing | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 7 | **N-1** | `GET /api/suspect-alerts` is entirely unscoped — nationwide read | HIGH | [STATIC] — **new** |
| 8 | **N-2** | Three Crime Unit write paths bypass branch isolation | HIGH | [STATIC] — **new** |
| 9 | **H-5** | Administrator self-demotion / last-admin lockout; privilege change does not revoke sessions | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 10 | **H-3** | Sessions never expire; administrative password reset does not revoke them | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 11 | **H-8** | No transport security anywhere in the repository; cookie lacks `Secure` | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 12 | **H-4** | No login throttling or lockout; authentication events are not audited | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 13 | **H-7** | Audit trail is mutable, incomplete, and records no before/after values | HIGH | [STATIC] + [RUNTIME-HISTORICAL] |
| 14 | **H-6** | Identifier generation is race-prone and `case_id` hard-codes the year | **MEDIUM** — *re-rated down from the audit's High* | [STATIC] + [RUNTIME-HISTORICAL] |
| 15 | **M-3** | No separation of duties on approval; two review-gate bypasses | MEDIUM | [STATIC] + [RUNTIME-HISTORICAL] |
| 16 | **M-7** | Uploads unvalidated — no extension, MIME or size check on most routes | MEDIUM | [STATIC] + [RUNTIME-HISTORICAL] |
| 17 | **M-11** | Unversioned schema migrations executed at application startup | MEDIUM | [STATIC] + [RUNTIME-HISTORICAL] |
| 18 | **N-3** | Analytics leak national aggregates to branch-scoped officers | MEDIUM | [STATIC] — **new** |
| 19 | **M-8** | Database access is superuser, unencrypted and unpooled | MEDIUM | [STATIC, partial] + [RUNTIME-HISTORICAL] |
| 20 | **M-12** | No backup, restore, retention, monitoring or DB-aware health check | MEDIUM | [STATIC] + [RUNTIME-HISTORICAL] |
| 21 | **M-10** | Stale SQLite-era artefacts; no dependency manifests | MEDIUM | [STATIC] + [RUNTIME-HISTORICAL] |
| 22 | **N-4** | `Access-Control-Allow-Origin: *` on every JSON response | LOW | [STATIC] — **new** |
| 23 | **N-5** | No security response headers (CSP, X-Frame-Options, nosniff, HSTS) | LOW | [STATIC] — **new** |
| 24 | **N-6** | Documents stored as JSON blobs in TEXT columns — no per-document authorization, retention or hash | LOW *(structural)* | [STATIC] — **new** |

**Counts:** 3 CRITICAL · 10 HIGH · 8 MEDIUM · 3 LOW = **24 findings**.
**Zero findings were verified as fixed.** **All eight** of the earlier audit's headline concerns remain present at `a1c2478`, and concern #3 (fail-open scope) is **wider** than reported.
**Six findings are new in this assessment** (N-1…N-6); two carried findings are **re-rated** (M-2 up, H-6 down).

---

## 2. CRITICAL findings

### C-1 — Uploaded police documents retrievable without authentication

| | |
|---|---|
| **Severity** | CRITICAL |
| **Class** | **[STATIC]** confirmed 2026-11-06 · **[RUNTIME-HISTORICAL]** reported reproduced at `381545c` |
| **File / endpoint** | `backend/server.py:7914` — `GET /uploads/<filename>` inside `do_GET` |
| **Evidence** | `do_GET` matches `p.path.startswith('/uploads/')` and returns `self.send_file(os.path.join(UPLOAD_DIR, name), ctype)` **before** any call to `require_auth`. The branch derives a content type from the file extension and streams the bytes. No token, cookie, role or branch check occurs on this path. Writers of these files: `save_upload()` `:3939-3946` (applicant documents, guardian documents, traveller photographs, traveller documents, crime evidence) and the signed-document route `:9009-9018`. |
| **Impact** | Every scanned national ID, passport page, guardian document, traveller photograph, signed police-clearance certificate and item of crime-scene evidence ever uploaded is readable by anyone who can reach the server and knows a filename. Filenames are `f_<16 hex chars><ext>` (`:3943`), so they are not brute-forceable in practice — but the URLs are embedded in API responses and in the printable certificate pages, so any leaked, forwarded, cached or logged URL becomes a permanent, unauthenticated, unrevocable link to a police document. **This is the highest-impact finding in the system.** |
| **Remediation** | Route document retrieval through an authenticated handler that (1) requires a session, (2) resolves the owning record, (3) applies the same branch/module scope as that record's own read route, and (4) writes an audit row per retrieval. Serve bytes from a directory that is not reachable by static path. Use short-lived signed URLs only if a streaming requirement makes the direct route impractical. |
| **Required verification test** | **New — does not exist.** (a) Anonymous `GET /uploads/<known file>` → **401/403**, no file bytes in the body. (b) Authenticated officer from branch A requesting a branch-B document → **403**. (c) Owning-branch officer → **200** *and* an audit row written. (d) Traversal: `GET /uploads/../backend/server.py` → **404/403**. Verified by inspection: **no current suite fetches `/uploads/` anonymously.** |

---

### C-2 — Shared default credentials on nine seeded accounts, published in the repository

| | |
|---|---|
| **Severity** | CRITICAL |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `backend/server.py:3304` onward (seed block, runs when `SELECT COUNT(*) FROM users` is `0`) · `POST /api/login` `:8664` · `README.md:566-589` |
| **Evidence** | The seed list creates `admin`, `fp.officer`, `ap.officer`, `cid.officer`, `hr.officer`, `cp.south`, `cp.east`, `cp.west` and others, **every one** with the literal password `'ChangeMe123!'`. The same credentials are documented in `README.md`. There is no forced change on first login, no expiry flag, no startup check that refuses to run with defaults in place, and no environment override for the seed password. |
| **Impact** | Anyone who can reach the login page — including anyone who has read the public repository — can sign in as **`admin`** and obtain full administrative control: all branches, all modules, user creation, role changes, password resets, approvals. This defeats every other access control in the system by itself. |
| **Remediation** | Source the seed password from the environment and fail startup if it is absent outside development; force a password change on first login for every seeded account; add a startup guard that blocks administrative login while any account still holds the default hash. Move the demo-account documentation firmly under the existing development-only heading (`README.md:769`) rather than presenting it as operational guidance at `:566`. |
| **Required verification test** | **New.** (a) Fresh database with no seed-password environment variable → startup **fails** (or administrative login is refused). (b) `admin` / `ChangeMe123!` → **401** after the fix. (c) First login with a provisioned password demands a change, and no privileged endpoint succeeds until it is completed. (d) A guard test asserting no source file contains a hard-coded login password. |

---

### C-3 — Unsalted, single-round SHA-256 password hashing

| | |
|---|---|
| **Severity** | CRITICAL |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `backend/server.py:3362` — `def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()`. Used at login `:8667`, self-service change `:8746`, administrative reset `:9638+`. |
| **Evidence** | One call to `hashlib.sha256`. No salt, no salt column (`users` carries `password_hash` only), no key-derivation function, no iteration count, no pepper. Because the hash is unsalted and deterministic, **identical passwords produce identical hashes** — so the nine seeded accounts from C-2 are visibly identical rows in the database. |
| **Impact** | Any read of the `users` table — a backup, a misdirected dump, an injection elsewhere, or an insider with read access — yields passwords recoverable by rainbow table or commodity GPU cracking in seconds. Officer accounts are then reusable here and, through password reuse, elsewhere. |
| **Remediation** | Replace with a memory-hard KDF (Argon2id preferred; bcrypt or PBKDF2-HMAC-SHA256 with a high iteration count acceptable) and a per-user random salt. Migrate transparently: on a successful login against a legacy hash, re-hash immediately with the new algorithm and store it. Retire the legacy path once all active accounts have logged in once. **Dependency note:** Argon2 and bcrypt need a third-party package, and the project has **no manifest, no lock file and no dependency policy** — that route is coupled to **D-29**. **PBKDF2-HMAC-SHA256 is in the standard library**, so C-3 can be closed without waiting for D-29. Password policy itself is **D-03**. |
| **Required verification test** | **New.** (a) Two users with the same password have **different** stored hashes. (b) The stored value is not a 64-character hex SHA-256 digest of the password. (c) Login succeeds against a legacy row and upgrades the stored hash in place. (d) The next login still succeeds. (e) A cost-parameter floor is actually in force. |

---

## 3. HIGH findings

### H-2b — Branch scope fails open when the posting does not resolve

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `branch_scope_view()` `:2661-2694`, paired with `resolve_posting_branch()` `:2624`. Governs every scoped route: `:4281`, `:8201`, `:8244`, `:8260`, `:8283`, `:8557`, `:8922`, `:8952`, `:9081`, `:9219`. |
| **Evidence** | When an officer's posting does not match a registered branch, `branch_scope_view()` returns `None`, and every call site treats `None` as "**no restriction**" rather than "**deny**". The paired helper `require_record_branch_scope()` `:2790-2805` is correctly **fail-closed** — *"unknown must never mean everything"* — so both patterns coexist in the same file. This is an inconsistency, not a deliberate global design. |
| **Impact** | A typo, a renamed branch, an inactive branch row, or an officer created with a free-text posting silently **removes** branch isolation for that officer across every unit — fingerprint records, crime cases, checkpoint writes, audit history. The failure is silent and unlogged. Because the outcome depends on branch data, the *current production* blast radius is **[NOT VERIFIED]** from this repository. |
| **Remediation** | Make the default deny. Return an explicit "unresolved" sentinel and have every call site refuse with 403 plus an audit row, rather than widening the query. Make postings a validated, non-free-text field at user creation. Extend the existing boot-time self-test pattern (`rbac_self_test()` `:2010`) to fail if any active user's posting does not resolve. **Do not regress the correct fail-closed behaviour of `require_record_branch_scope()`.** |
| **Required verification test** | **New.** For each scoped route: an unresolvable posting yields **403**, never a wider result set. A startup assertion test: seeding such a user fails the self-test. A regression test that `branch_scope_view()` never returns `None` for a non-administrative role. |

---

### M-2 — Checkpoint location scope fails open for the canonical role *(read and write)*

| | |
|---|---|
| **Severity** | **HIGH** — this assessment **re-rates it up** from the audit's Medium. The identifier is unchanged. Reason: it affects the **canonical, default** role and permits **writes**, not only reads. |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** reported reproduced |
| **File / endpoint** | `ROLE_LOCATION_SCOPE[ROLE_CHECKPOINT_OFFICER] = ''` `:1922` · `checkpoint_scope()` `:2965-3000`, returning `ROLE_LOCATION_SCOPE[r] or ''` at `:2990` · read `GET /api/checkpoint-events` `:8460` · write `POST /api/checkpoint-events` `:9301` |
| **Evidence** | The canonical role's static scope is the **empty string**. Both call sites guard with `if scope:` — an empty string is falsy, so **no location filter is applied**. A `checkpoint_officer` with a blank `users.location_scope` therefore reads every checkpoint's traveller records and may file a screening event at **any** location. The in-code comment at `:1919-1921` asserts the opposite intent, confirming an implementation/intent mismatch. Perverse consequence: the **legacy** `CheckpointSouth/East/West` roles are **safer**, since their scope derives from the role name. There is also no validation requiring `location_scope` when an administrator creates a checkpoint officer. |
| **Impact** | Traveller identity records, guardian details, live photographs and ID scans from every checkpoint are readable by any checkpoint officer with a blank scope — **the default state of the role the project has standardised on**. Fabricated or misattributed screening events can be filed at a checkpoint the officer has never served at, corrupting both the operational record and the analytics. |
| **Remediation** | Make `checkpoint_scope()` fail **closed**: no resolvable location means denied, not widened. Distinguish "administrator — all locations" from "checkpoint officer — none assigned" as two different return values with two different outcomes. Make `location_scope` mandatory on create and edit. Add branch-based read filtering alongside location filtering. |
| **Required verification test** | **New — and the coverage gap is proven: no current suite asserts a blank-scope denial.** (a) `checkpoint_officer` with `location_scope=''` → `GET` returns **403** or an explicitly denied empty result, never another location's rows. (b) Same officer → `POST` to a different location → **403**. (c) Administrator still reads all locations. (d) Legacy `CheckpointSouth` still sees only South after normalisation. (e) Creating a checkpoint officer without `location_scope` is rejected. |

---

### H-2a — Cross-branch approval, signed-scan attachment and person-document listing

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `POST /api/clearance-applications/<id>/approve` `:9032` · `POST /api/clearance-applications/<id>/signed-document` `:8997` · `GET /api/persons/<id>/documents` `:8152` |
| **Evidence** | All three resolve their target by identifier alone (`… WHERE application_id=%s`, `:9034`) and proceed. None calls `require_record_branch_scope()`, which **is** applied on the corresponding read routes at `:8244` and `:8283`. Module gating is prefix-based and applied once per request (`post_module_for_path` `:8869`), so the two clearance paths **are** correctly restricted to the `fingerprint` module — the defect is therefore **intra-role and cross-branch**, not cross-module. |
| **Impact** | Any fingerprint officer in any branch can approve another branch's police-clearance application, mint its certificate number, and attach a signed certificate scan to it. The audit row records the actor, so the act is traceable after the fact — but it is not **prevented**, and the certificate it produces is externally valid. The document-listing route additionally exposes `/uploads/` URLs across branches, which **compounds C-1**. |
| **Remediation** | Apply `require_record_branch_scope()` to all three handlers, using exactly the resolution the read routes use, **before** the review-gate evaluation. Once H-2b is fixed, these inherit fail-closed behaviour. |
| **Required verification test** | **New — gap proven:** `grep -c "approve\|signed-document" backend/test_branch_scope.py` → **0**. (a) Branch-A officer approving a Branch-B application → **403**, status unchanged. (b) Same for `/signed-document` → **403**, no file written to `UPLOAD_DIR`. (c) Own-branch approval still succeeds and still enforces the 12-hour gate. (d) Cross-branch person-document listing → **403**. (e) Administrator behaviour explicitly pinned, whichever way the owner decides. |

---

### N-1 — `GET /api/suspect-alerts` is entirely unscoped *(new)*

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** — **new in this assessment** |
| **File / endpoint** | `GET /api/suspect-alerts` `:8425-8432` |
| **Evidence** | The handler issues its `SELECT` with no branch filter, no location filter and no caller-derived predicate of any kind. It **cannot** apply one: `suspect_alerts` **has no `branch_id` column** (DDL `:299-308`; `ADDED_COLUMNS` entry `:509`). |
| **Impact** | Every CID officer and every checkpoint officer in the country sees **all** suspect, victim, witness and complainant listings nationwide — including the free-text reason recorded for unlinked listings. This is the most sensitive list in the system, naming people who have not been charged, and it has no containment whatsoever. It is also **the only Release 1.0 access-control gap that cannot be closed without a schema change**. |
| **Remediation** | Add `branch_id` (and, if required, a visibility classification) to `suspect_alerts`; backfill from the linked case where one exists and require an explicit branch for unlinked listings; then apply the standard scope filter to the read route and `require_branch_write_scope` to the create route. Because this needs DDL, it is coupled to **M-11** — do it after versioned migrations exist, or accept the startup-migration pattern as a documented one-off with a rollback plan. |
| **Required verification test** | **New.** (a) Branch-A CID officer sees only Branch-A alerts. (b) Branch-B alerts are absent, asserted on record identifiers rather than counts. (c) Checkpoint flagging still works within the officer's own scope after the change. (d) An unlinked listing with no branch is rejected. |

---

### N-2 — Three Crime Unit write paths bypass branch isolation *(new)*

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** — **new in this assessment** (distinct from H-2a, which covers the two clearance routes and the person-document listing) |
| **File / endpoint** | `PATCH /api/crime-cases/<id>` `:9581-9593` · `POST /api/crime-cases/<id>/evidence` `:9092-9105` · `POST /api/suspect-alerts` `:9172-9210` |
| **Evidence** | Each resolves its target by identifier and writes, with no `require_branch_write_scope` and no `require_record_branch_scope`. By contrast the create route `:9081` and the list/detail routes `:8260`/`:8283` **do** scope. The PATCH additionally accepts **free-text** status with no vocabulary check and no state machine `:9586`; the suspect-alert create resolves its case at `:9176-9178` without a scope check. |
| **Impact** | Any CID officer can change the status of any case nationwide — including closing another branch's investigation — attach evidence to it, and attach a named person to it as a suspect. Case status drives the closure-rate figures already shown to commanders, so this also corrupts command-level reporting. The audit row names the actor; the action is not prevented. |
| **Remediation** | Apply the record-scope check used by `GET /api/crime-cases/<id>` to all three handlers before any write. Separately (functional, not security) constrain status to one approved vocabulary with validated transitions — **D-25**. |
| **Required verification test** | **New.** For each endpoint: cross-branch request → **403** with no row mutated or inserted; own-branch request → success; an audit row written in both the allowed and the denied case. |

---

### H-5 — Administrator self-demotion / last-admin lockout; privilege change does not revoke sessions

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed this session *(the audit recorded this as "not re-verified"; it is now statically confirmed)* · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `PATCH /api/admin/users/<id>` `:9638-9730` |
| **Evidence** | Three defects in one handler, all confirmed by reading it: <br>**1. No last-administrator guard and no self-demotion guard.** Nothing prevents the only `SystemAdmin` from changing their own role or deactivating their own account, permanently locking the organisation out of user administration — there is no out-of-band recovery path in the codebase. <br>**2. Privilege changes do not revoke sessions.** The handler sets `password_hash`, `role` and `active` and commits with **no** `DELETE FROM sessions`. The only two session-deleting statements in the file are logout `:3998` and the **self-service** password change `:8759`, which correctly signs out every other browser for that account. The administrative path has no equivalent. *(This half overlaps the audit's H-3; it is remediated with H-3.)* <br>**3. Deactivation is not revocation.** `require_auth()` `:4004-4030` selects `… WHERE id=%s AND active=1`, so a deactivated user is blocked while inactive — but the session **row and token survive**, so reactivating the account silently **revives** every previously issued session. |
| **Impact** | An administrator resetting a compromised officer's password does **not** evict the attacker — the old token keeps working. Demoting a user leaves their elevated session usable until they happen to log out. A deactivate/reactivate cycle, a routine HR action, resurrects stale tokens. And one mis-click can permanently remove the organisation's last administrator. |
| **Remediation** | (a) Refuse to demote or deactivate the last active `SystemAdmin`, and refuse self-demotion and self-deactivation; (b) delete all sessions for the target user on any change to `password_hash`, `role`, `branch`, `location_scope` or `active`; (c) delete sessions on deactivation rather than relying on the `active=1` predicate; (d) audit each with before/after values. A two-person rule for user administration is **D-09**. |
| **Required verification test** | **New.** (a) Last-admin demotion → **400/403**; with a second admin present → allowed. (b) Self-demotion → refused. (c) After an administrative password reset, the target's previous token → **401**. (d) After a role change, the old token → **401**. (e) Deactivate → reactivate → the pre-deactivation token → **401**. |

---

### H-3 — Sessions never expire; administrative reset does not revoke them

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `sessions` DDL `:446-449` · `create_session()` `:3976-3988` · `require_auth()` `:4004-4030` · login `:8664-8678` |
| **Evidence** | The `sessions` table has exactly three columns: `token`, `user_id`, `created_at`. There is **no `expires_at`**, no `last_seen_at`, no IP or user-agent binding, and `require_auth()` performs no age check. Tokens are `secrets.token_urlsafe(32)` — cryptographically strong, which is good — but **valid forever** until an explicit logout. An in-memory `TOKENS` cache is consulted before the database, so a session can be served without touching the row. The cookie is `HttpOnly; SameSite=Lax` but **without `Secure`** `:8677`. Revocation on administrative reset is absent — see H-5(2). |
| **Impact** | A token captured once — from a shared workstation, a browser profile, a backup, a log, or the network (see **H-8**) — grants indefinite access to a police system. Unattended checkpoint and station terminals are the realistic exposure. There is no administrative way to see or terminate active sessions. |
| **Remediation** | Add absolute expiry and idle timeout enforced in `require_auth()` and `lookup_session()` — **the actual values are owner decision D-08**; rotate the token on login and on any privilege change; add `Secure` once TLS exists (**H-8**); provide an administrative "active sessions / revoke" view; purge expired rows on a schedule; invalidate the in-memory cache entry whenever a row is deleted. |
| **Required verification test** | **New.** (a) A session past the absolute limit → **401**. (b) A session idle past the idle limit → **401**. (c) The token changes on re-login. (d) A revoked session fails even with a warm in-memory cache. (e) The cookie carries `Secure`, `HttpOnly` and `SameSite` once TLS is in place. |

---

### H-8 — No transport security anywhere in the repository

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | Whole server — `ThreadingHTTPServer` with **no** `ssl` import, no `wrap_socket`, no HTTPS listener (searched this session: **0 hits** for `ssl.`/`wrap_socket`). No reverse-proxy configuration, no Dockerfile, no nginx/Caddy/systemd artefacts anywhere in the repository. Session cookie set without `Secure` `:8677`. The SPA also keeps the token in `localStorage` alongside the cookie. |
| **Impact** | Unless an operator has placed a TLS terminator in front of the service — which this repository neither provides, documents nor verifies — credentials, bearer tokens, session cookies, personal data and document bytes all travel in cleartext. Whether production has TLS is **[NOT VERIFIED]** and cannot be determined from the repository. This finding gates `Secure` cookies (H-3) and HSTS (N-5). |
| **Remediation** | Decide and **commit** the hosting target and network design (**D-01**, **D-02** — D-02 explicitly covers certificate issuance and rotation): either terminate TLS at a reverse proxy, committing that configuration and making the application require the forwarded-proto header, or terminate in-process. Then set `Secure` on the cookie and redirect plaintext requests. Reconsider duplicating the token into `localStorage`. |
| **Required verification test** | **New.** A deployment smoke test asserting: plaintext request → redirect or refusal; the cookie carries `Secure`; a documented, committed, reproducible deployment configuration exists. |

---

### H-4 — No login throttling or lockout; authentication events are not audited

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed this session · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `POST /api/login` `:8664-8678` · `POST /api/logout` `:8680` · `audit()` `:4032` |
| **Evidence** | The login handler writes **no audit row** on success or on failure — `audit()` is not called on either path — and there is no attempt counter, backoff, lockout or CAPTCHA anywhere (searched this session: no rate-limit implementation exists). Logout is likewise unaudited. |
| **Impact** | Online password guessing is unlimited and invisible — which, combined with **C-2** and **C-3**, turns a known default password into an unmonitored open door. A compromise cannot be investigated afterwards, because there is no record of who signed in, from where, or how many failures preceded it. For a police system this is an accountability failure as much as a security one. |
| **Remediation** | Audit login success, login failure and logout with source address; add per-account and per-source throttling with exponential backoff and temporary lockout (thresholds relate to **D-03**); alert on failure bursts. |
| **Required verification test** | **New.** N consecutive failures → throttle/lockout response; every attempt writes an audit row; a successful login records the source address; the lockout expires as designed. |

---

### H-7 — Audit trail is mutable, incomplete, and records no before/after values

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `audit_events` DDL `:450-454` · `audit()` `:4032-4035` · representative call `:9591` |
| **Evidence** | `audit_events` is a plain table with no hash chain, no append-only constraint, no signing, and no IP, user-agent or session identifier. Any database writer can edit or delete history. Update calls pass no detail — `audit(c, user, 'UPDATE', 'crime_case', cid)` records *that* a case changed but not *what* changed. Authentication events are absent entirely (**H-4**). |
| **Impact** | The audit trail is this system's accountability mechanism and its evidence of lawful handling. In its current form it cannot establish what a record looked like before an edit, cannot attribute an action to a session or device, and cannot demonstrate that it has not itself been altered. If a tamper-evident audit is a legal obligation (**D-04**), the current design does not meet it. |
| **Remediation** | Record structured before/after values on updates; make the table append-only at the database level by revoking UPDATE and DELETE from the application role; add a hash chain or periodic signed digest; capture source address and session identifier; define retention (**D-04**). |
| **Required verification test** | **New.** An update writes both prior and new values; the application role cannot UPDATE or DELETE an audit row; a tampered row is detected by the integrity check; authentication events appear in the trail. |

---

## 4. MEDIUM findings

### H-6 — Identifier generation is race-prone, and `case_id` hard-codes the year

**Severity: MEDIUM** — this assessment **re-rates it down** from the audit's High (the identifier is unchanged). **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]**.
**Evidence:** `case_id = 'CID-2026-' + zfill(COUNT(*)+8, 3)` `:9083` — a **hard-coded year**, a **global counter** (not per-branch, not per-year), and a read-then-write race under concurrency. `FP-`, `CL-` and `CP-` identifiers use the **last 8 digits of epoch milliseconds** (`:9066`, `:9319`), which collide when two records are created in the same millisecond and are effectively sequential and guessable.
**Impact:** duplicate or mislabelled official reference numbers on documents issued to the public and cited externally; cases created in 2027 labelled `CID-2026-…`; spurious `409`s under concurrent registration; a counter that repeats if rows are archived. Re-rated to Medium because it damages data integrity and public-facing correctness rather than granting unauthorised access.
**Remediation:** derive identifiers from a database sequence scoped by year and branch, generated inside the inserting transaction, with a unique constraint as a backstop.
**Verification test (new):** 100 concurrent case creations yield 100 distinct identifiers; a case created with the clock at 2027 is labelled `2027`; the unique constraint exists and is exercised.

### M-3 — No separation of duties on approval; two review-gate bypasses

**Severity MEDIUM · [STATIC] confirmed · [RUNTIME-HISTORICAL].**
**Endpoint:** `POST /api/clearance-applications/<id>/approve` `:9032-9077`.
**Evidence:** the handler enforces the 12-hour review window **twice** — `review_gate_decision()` `:946` and an independent inline `FINGERPRINT_REVIEW_WINDOW_HOURS * 3600` guard `:9057` — which is genuinely good defence-in-depth and is well covered by `test_review_gate.py` (37 references, **NOT RUN** this session). However: `bypassed = is_admin_user(user) or citizenship_wait_exempt(app_row)` `:9052` skips **both** gates for administrators **and** for any application whose stored `purpose` is `Citizenship` — and the purpose is supplied by the submitter, so **the exemption is caller-selectable**. There is **no check that the approver differs from the submitter**. There is also **no reject path at all**: `'Rejected'` exists only in HR/conduct constants and as an unreachable analytics axis (`:6112`, `:6124`).
**Impact:** the headline control of the Fingerprint Unit can be skipped by two routes, one of them attacker-selectable; and the only two outcomes available to an officer are "approve" or "leave pending forever", which is not a defensible adjudication process.
**Remediation — policy input required, not a code decision:** **D-06** (is the `Citizenship` exemption lawful? if so, require an explicit audited justification rather than an implicit property of the row), **D-12** (may the filing officer approve their own application?), **D-19** (define the rejection path). Promote the bypass note already written into the audit detail string `:9071` to a structured, queryable field.
**Verification test:** partly existing (`test_review_gate.py` — **must actually be executed**). New: submitter approving own application → **403**; a `Citizenship` approval writes an explicit bypass record with justification; an administrator bypass writes a distinct queryable record; once D-19 is decided, a rejection test.

### M-7 — Uploads are unvalidated on most routes

| | |
|---|---|
| **Severity** | MEDIUM |
| **Class** | **[STATIC]** confirmed · **[RUNTIME-HISTORICAL]** |
| **File / endpoint** | `save_upload()` `:3939-3946`, used by applicant documents, guardian documents, traveller photographs, traveller documents and crime evidence |
| **Evidence** | `save_upload()` sanitises the filename and stores it as `f_<hex><ext>`, but applies **no extension allow-list, no MIME check and no size limit**. The signed-document route `:9009-9018` **does** apply both an allow-list and a 20 MB cap — so the project already has the correct pattern and simply does not apply it consistently. |
| **Impact** | Arbitrary file types of arbitrary size can be stored and later served from `/uploads/` with a content type derived from the extension `:7916-7919`, which — combined with **C-1** — makes the server an unauthenticated host for attacker-supplied content. Unbounded size is also a denial-of-service and storage-cost issue. |
| **Remediation** | Move the signed-document route's allow-list and size cap into `save_upload()` so every caller inherits them; verify declared MIME against content; serve downloads with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. |
| **Required verification test** | **New.** Disallowed extension → **400**; over the size cap → **413/400**; content/type mismatch → rejected; an allowed file still uploads and is retrievable by an authorised officer. |

### M-11 — Unversioned schema migrations executed at application startup

**Severity MEDIUM · [STATIC] confirmed · [RUNTIME-HISTORICAL].** Base DDL plus the `ADDED_COLUMNS` map `:457+` are applied on every boot. There is **no `schema_migrations` table**, no version number, no ordering guarantee, no down-migration and no record of what has been applied.
**Impact:** schema state cannot be known or reproduced; two instances booting concurrently race on DDL; a failed partial migration leaves no trace; rollback is manual. This **blocks** the schema changes that N-1, H-6 and the document model need, and it is the reason **no zero-downtime claim can be made**.
**Remediation:** a versioned migration mechanism with a recorded version table, run as an explicit, separate step — not an application-boot side effect.
**Verification test (new):** booting against an older schema applies exactly the missing versions and records them; booting twice is a no-op; two concurrent boots do not both apply the same migration.

### N-3 — Analytics leak national aggregates to branch-scoped officers *(new)*

**Severity MEDIUM · [STATIC] · new.** `cid_crime_analytics(c)` `:6132` and `cid_fingerprint_analytics(c)` `:6071` take **no `user` argument**; only `cid_checkpoint_analytics(c, user)` `:6176` is scoped. Dispatch at `:6310-6320`.
**Impact:** a branch-scoped officer who cannot open another branch's records can still read national totals, category and location distributions, match rates, suspect-hit rates and closure rates derived from them. Aggregates of a police caseload are themselves sensitive, and the distributions are fine-grained enough to be informative about individual branches.
**Remediation:** pass `user` to every builder and apply the same branch predicate the record routes use.
**Verification test (new):** an officer in Branch A with 3 cases, while Branch B holds 7, sees **3** in every count, chart axis and rate — not 10.

### M-8 — Database access is superuser, unencrypted and unpooled

**Severity MEDIUM · [STATIC, partial] · [RUNTIME-HISTORICAL].** `.env.example` defaults to `SENTINEL_DB_USER=postgres`; no `sslmode` setting and no connection pooling configuration exist in the repository.
**Impact:** the application connects with more privilege than it needs — which is also why the append-only audit constraint in **H-7** cannot be enforced today — and database traffic may be unencrypted. Actual production configuration is **[NOT VERIFIED]**.
**Remediation:** a least-privilege application role (no DDL in normal operation, no UPDATE/DELETE on `audit_events`), `sslmode=require` or stronger, and a connection pool sized against **D-07**.
**Verification test (new):** the application role cannot execute DDL outside the migration step; the connection asserts TLS; pool limits are exercised under load.

### M-12 — No backup, restore, retention, monitoring or DB-aware health check

**Severity MEDIUM · [STATIC] · [RUNTIME-HISTORICAL].** No such artefacts exist in the repository.
**Impact:** no recovery guarantee for police records; no way to detect a database outage other than a user-visible failure; retention obligations (**D-04**) cannot be met because there is no mechanism to meet them. RPO/RTO are undefined (**D-08**).
**Remediation:** automated backups with a **rehearsed** restore, a retention job, a health check that actually touches the database, and basic monitoring/alerting.
**Verification test (new):** a restore rehearsal from a backup into a clean environment, with a documented and measured RPO/RTO.

### M-10 — Stale SQLite-era artefacts; no dependency manifests

**Severity MEDIUM · [STATIC] confirmed · [RUNTIME-HISTORICAL].** Dead scripts `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`; obsolete suites `backend/test_server.py` (SQLite-era) and `backend/test_conduct_frontend.mjs` (retired `SENTINEL_DB` setting); **no `requirements.txt`, no `package.json`, no lock file**.
**Impact:** this is the direct cause of the single most serious *process* problem in the project — **23 of 25 test suites could not be executed in this assessment**, so no security fix can currently be verified. Obsolete harnesses also risk being run against a real database by mistake.
**Remediation:** add pinned manifests (**D-29**), retire or rewrite the two obsolete suites, delete the dead scripts.
**Verification test (new):** a clean checkout installs from the manifests and runs the full suite to a known result in CI.

---

## 5. LOW findings *(all new in this assessment)*

| ID | Finding | Evidence | Impact | Remediation | Verification test |
|---|---|---|---|---|---|
| **N-4** | `Access-Control-Allow-Origin: *` on every JSON response | `:7773`, with `Allow-Headers: Content-Type, Authorization` `:7774` | Browsers refuse credentialed cross-origin reads when the origin is `*`, so this is not directly exploitable against the cookie session today. It nonetheless invites any origin to call the API with a token obtained elsewhere, and it is unnecessary for a same-origin SPA. | Remove the wildcard, or restrict to an explicit allow-list of deployment origins. | Cross-origin `fetch` with credentials from an unlisted origin is blocked; same-origin is unaffected. |
| **N-5** | No security response headers | No `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` or `Strict-Transport-Security` anywhere (searched: 0 hits) | No defence in depth against clickjacking, MIME sniffing of uploaded content (compounds **M-7** and **C-1**), or protocol downgrade. | Add CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and HSTS once TLS exists (**H-8**). | Header-presence assertions on both the SPA and the API. |
| **N-6** | Documents stored as JSON blobs in TEXT columns | `applicant_docs`, `guardian_docs`, `traveler_docs` (DDL `:519`, `:528`, plus the fingerprint tables) | A document is not an addressable entity, so it cannot carry per-document authorization, a retention date, an integrity hash or its own audit rows. This is the structural reason **C-1** is hard to fix *well*. | Promote documents to a first-class table with owner, type, hash, uploader, retention date and access audit. Schema change — sequence after **M-11**. | Each document row is individually authorizable; retrieval writes an audit row; the stored hash matches the bytes. |

---

## 6. Remediation sequencing

> Sequence only. **No remediation is authorised until the owner approves**, and this assessment performed none.

**Wave 1 — must precede any production exposure**
1. **C-2** default credentials *(needs **D-03**)*
2. **C-1** + the person-document half of **H-2a** — authenticated, scoped, audited document retrieval
3. **H-2b** fail-closed branch scope — *shared control; unblocks H-2a, N-2*
4. **M-2** fail-closed checkpoint scope + mandatory `location_scope` *(do with **D-20**)*
5. **C-3** password hashing *(PBKDF2 needs no new dependency; Argon2/bcrypt couples to **D-29**)*

**Wave 2 — authorization completeness and accountability**
6. **H-2a**, **N-2** record scope on the remaining write paths
7. **H-5** last-admin guard + session revocation on privilege change
8. **H-3** session expiry, rotation, administrative revocation *(values are **D-08**)*
9. **H-4** authentication auditing, throttling, lockout *(thresholds relate to **D-03**)*
10. **M-7** upload validation inside `save_upload()`
11. **M-3** separation of duties + structured bypass auditing *(policy input: **D-06**, **D-12**, **D-19**)*

**Wave 3 — requires a schema, dependency or deployment decision first**
12. **M-10** dependency manifests + retire obsolete suites *(**prerequisite for verifying anything above**)*
13. **M-11** versioned migrations *(gates everything below)*
14. **N-1** `suspect_alerts.branch_id` *(needs 13)*
15. **N-3** scoped analytics
16. **H-6** sequence-based identifiers *(needs 13)*
17. **H-7** tamper-evident audit with before/after values *(needs 13; retention is **D-04**; least-privilege role ties to **M-8**)*
18. **H-8** documented TLS topology *(needs **D-01**, **D-02**)*
19. **M-8**, **M-12** least-privilege database role, backups, restore rehearsal, monitoring *(**D-07**, **D-08**, **D-09**)*
20. **N-4**, **N-5**, **N-6** hardening and the document model

**Dependency note.** Items 3 and 4 are each a **single shared control** closing several findings at once — the highest-leverage changes in this list, and they should not be split across waves. Item 12 is sequenced in Wave 3 by dependency, but in practice it should be done **first of all**, because without it none of Waves 1–2 can be verified.

---

## 7. Statement of verification honesty

- **Nothing in this list was fixed.** No application code, schema, configuration or dependency was changed in this assessment.
- **Nothing in this list was runtime-verified in this session.** The only two executable checks (`--ui-check`, `test_print_fit.py`) are not security tests.
- **[RUNTIME-HISTORICAL]** markers reflect what the earlier audit reported at commit `381545c`. They are recorded as prior evidence, have **not** been re-reproduced, and must not be read as current runtime proof.
- Several findings the earlier audit could only report at runtime (**H-4**, **H-5**) are now **statically confirmed**; `PROJECT_STATUS.md` §6 has been updated accordingly.
- **Every "Required verification test" above does not exist today**, except the partial review-gate coverage noted under M-3 — and that suite was **not run**.
- The earlier audit's identifiers are preserved exactly; the one numbering conflict found during drafting is reported in §0.2 rather than silently resolved.
- The audit report in PR #23 and its history are preserved and unmodified.
