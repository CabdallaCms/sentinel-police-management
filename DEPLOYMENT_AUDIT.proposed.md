# Sentinel Police Management System — Foundation Assessment & Deployment Readiness Audit

**Document status:** PROPOSED replacement for `DEPLOYMENT_AUDIT.md` — *not yet approved*.
Nothing in the repository was modified to produce this report other than adding this file.
**Audit date:** 2026-10-27
**Audited revision:** branch `arena/8834f56d-sentinel-police-management`, commit `381545c8401b36cf18241c2065ea62a42e59606d`, working tree clean.
**Auditor scope:** repository inspection, static code review, and execution of the project's own test suites plus a read-only/synthetic-data probe session against a throwaway PostgreSQL cluster.
**Document revision:** v2 (2026-10-27) — Section 10 rewritten with objective acceptance criteria, verification methods, a negative-test matrix and a remediation tracking table. **No finding, evidence, severity or readiness verdict was changed, downgraded or removed.** Sections 1–9, 11, 12 and the appendices are byte-identical to v1.

> **No production system, operational database, or real police record was accessed.** Every identity, document and record used in live testing was synthetic and generated during the audit. No migration was designed, created or applied. No application file, dependency, configuration or database state outside a disposable `/tmp` cluster was altered.

---

## 1. Executive summary

### 1.1 Where the system stands today

Sentinel is a **substantially more mature application than its own documentation says it is**, and a **substantially less deployable system than its code comments imply**.

The engineering since the previous audit is real and verifiable: role-based modules, a hard unit-module denylist, a global read-only Commander role, per-record audit attribution with badge numbers, server-enforced branch scoping on register reads and writes, a 12-hour fingerprint review gate with a boot-time self-test that refuses to start if the gate is disarmed, a certificate print lock, and roughly two dozen automated suites that genuinely exercise the API rather than just the interface. The `rbac_self_test()` and `review_lock_armed()` startup refusals are unusual and genuinely good defensive engineering.

However, the security model that was built has **three structural holes that the test suite does not cover**, and all three were reproduced live during this audit:

1. **Documents are still public.** `GET /uploads/<file>` is served with no authentication whatsoever. A synthetic applicant photograph and PDF returned HTTP 200 to an anonymous client.
2. **Branch isolation is enforced on the routes the tests exercise and absent on the routes they do not.** A Fingerprint officer posted to the Erigavo branch successfully attached a signed scan to a **Lasanod branch** clearance application (HTTP 201) and then **approved it and received a certificate number** — while the same officer was correctly refused (403) when reading that same application.
3. **Branch isolation fails open.** When an officer's free-text posting does not resolve to a registered branch, the officer is treated as **unscoped** and sees every branch — the opposite of the intended fail-closed default. Reproduced by setting one account's branch to an unregistered label.

Alongside those, the classic blockers from the previous audit are all still present and were re-confirmed: nine seeded demo accounts sharing the password `ChangeMe123!`, **unsalted SHA-256** password hashing (the audit produced a stored hash byte-identical to the publicly known `sha256("abcdef")`), no HTTPS, no secure-cookie flag, no session expiry, no login throttling, and login events that are not audited at all.

Two **new** risks were introduced by the recent user/role work:

- A System Administrator can **demote themselves** and is then permanently locked out of user management with no recovery path (the audit reproduced this and had to correct it with direct SQL on the disposable database). On a fresh install there is exactly one administrator.
- An administrator **resetting a user's password does not revoke that user's live sessions** — a compromised session survives the remediation attempt.

### 1.2 The one-line verdict

| Purpose | Verdict |
|---|---|
| Continued development | **GO** |
| Dedicated staging environment (synthetic data) | **GO with conditions** |
| Controlled pilot with real police data | **NO-GO** |
| Production deployment | **NO-GO** |
| Near-zero-downtime upgrade capability today | **Not achievable** (sessions are fine; schema migrations are not) |

### 1.3 Most important remaining risks (ordered)

| # | Risk | Severity | Status |
|---|---|---|---|
| 1 | Identity documents downloadable without authentication | **Critical** | Verified live |
| 2 | Default accounts with a shared, publicly documented password on every fresh install | **Critical** | Verified in code + live |
| 3 | Unsalted SHA-256 password storage | **Critical** | Verified live (hash matched known value) |
| 4 | Cross-branch write/approve on `/approve` and `/signed-document` | **High** | Verified live |
| 5 | Branch scope fails **open** when a posting does not resolve | **High** | Verified live |
| 6 | Sessions never expire and are not revoked on password reset or reactivation | **High** | Verified live |
| 7 | No login throttling or lockout; no authentication audit trail | **High** | Verified live |
| 8 | Last-administrator self-lockout with no recovery | **High** | Verified live |
| 9 | Registration-number race conditions cause user-visible 409 failures | **High** | Verified live (4 of 12 concurrent writes failed) |
| 10 | No HTTPS, cookie without `Secure`, token duplicated into `localStorage` | **High** | Verified live |

**What is genuinely strong:** RBAC module gating and the read-only Commander firewall (verified with a 7-role × 12-endpoint matrix and the project's own 179-check suite), the review-gate self-test, per-record audit history, branch scoping on the main registers, and a shell/workflow UI that is covered by real jsdom integration tests. The foundation is worth continuing to build on. It is not worth deploying yet.

---

## 2. Baseline verification

### 2.1 Repository and revision

| Item | Value |
|---|---|
| Remote | `CabdallaCms/sentinel-police-management` |
| Active branch | `arena/8834f56d-sentinel-police-management` |
| Commit | `381545c` — *"Scope the sidebar trees to the officer's branch and restrict Unit Directory"* (2026-10-27 16:46:48 +0000) |
| Commit count on branch | **1** (`git rev-list --count HEAD` = 1) |
| Other refs | `main`, `origin/main` |
| Working tree | Clean before the audit (`git status` → nothing to commit) |
| Modified by this audit | Only the addition of this file (and untracked `.venv/`, `node_modules/` used to run tests; both are git-ignored) |

**Important limitation:** the branch history contains **exactly one commit**. There is no incremental commit history to diff against, and **no `DEPLOYMENT_AUDIT.md` exists anywhere in the repository or in `git log --all`/`git ls-files`**. The previous audit is therefore compared against (a) the twelve findings enumerated in the audit request, and (b) the "Important implementation note — development only" section of `README.md`, which restates the same blocker list. See §9 for exact per-finding classification and §12 for the documentation gap.

### 2.2 Repository structure (as found)

```
sentinel-police-management/
├── .env.example                  # PostgreSQL engine settings template (no secrets)
├── .gitignore                    # ignores .env, backend/uploads/, sentinel.db*, .venv, node_modules
├── README.md                     # 1,067 lines — feature + RBAC + testing documentation
├── TESTING.md                    # 680 lines — suite instructions and UAT checklists
├── TROUBLESHOOTING.md            # 267 lines — UI/build-stamp and port diagnostics
├── index.html                    # 12,670 lines / 783 KB — the entire SPA (inline CSS + JS)
├── application.html              #   560 lines — printable Good Conduct application
├── certificate.html              #   568 lines — printable clearance certificate
├── images/police_logo.png        # 1.9 MB brand asset (unoptimised)
├── backend/
│   ├── server.py                 # 9,466 lines / 499 KB — HTTP server + API + RBAC + schema + migrations
│   ├── vehicles.py               #   206 lines — vehicle registry helpers + DDL
│   ├── database.py               #    84 lines — LEGACY/divergent schema bootstrap (see M-10)
│   ├── migrate_rbac.py           #   221 lines — LEGACY SQLite migration script (dead)
│   ├── audit_instant_approvals.py#   213 lines — LEGACY SQLite forensic script (dead)
│   ├── README.md                 #   377 lines — API reference
│   └── test_*                    # 11 Python suites + 12 Node/jsdom suites
└── scripts/
    ├── restart-8001.sh / .ps1    # kill-port + restart + health verify
    ├── uat-stack.sh              # throwaway pgserver cluster + backend (used by this audit)
    └── verify-live-ui.sh         # live UI/build-stamp verification
```

**Absent and notable:** no `requirements.txt`, no `package.json`, no `Dockerfile`, no `systemd` unit, no reverse-proxy configuration, no CI configuration, no `DEPLOYMENT_AUDIT.md`, no `CHANGELOG`, no licence file. Dependencies are installed ad-hoc (`pip install psycopg2-binary pgserver`, `npm install jsdom`).

### 2.3 Runtime inventory

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.11.2 (sandbox) | `server.py` states Python 3 standard library only (+ psycopg2) |
| HTTP server | `http.server.ThreadingHTTPServer`, `BaseHTTPRequestHandler` | One thread per request, no TLS, no WSGI/ASGI, no reverse proxy in front |
| Database | PostgreSQL via `psycopg2` 2.9.13 | Compiled extensions; driver import fails-fast unless `--ui-check` |
| Frontend | Single-file HTML SPA | No build step, no bundler, no framework |
| Test runner (Python) | No framework — plain scripts with `print("ok: …")` assertions and non-zero exit on failure | One `unittest`-based file (`test_linked_records.py`) |
| Test runner (Node) | `node` ESM scripts + `jsdom@26` + a `node:vm` DOM sandbox | No `package.json`; installed with `npm install --no-save` |

---

## 3. Current architecture

### 3.1 Frontend

- **One 783 KB `index.html`** containing markup, ~9,000 lines of inline CSS and ~6,000 lines of inline JavaScript. Zero external bundles. Two companion documents (`application.html`, `certificate.html`) are standalone printable pages that re-read the session from `localStorage` and fetch their record by `?id=`.
- **18 client-rendered pages** (`dashboard`, `people`, `fingerprint`, `airport`, `cid`, `caseworkspace`, `checkpoints`, `policesearch`, `stations`, `officers`, `conduct`, `crimes`, `cars`, `admin`, `branches`, `executive`, `oversight`, `vehiclestatus`).
- **Routing:** a single `go(page)` function (`index.html:3267`) toggles `.page.active` sections. Navigation is a hierarchical, collapsible sidebar with Region → District → unit trees that are filtered by the officer's branch scope (`navUnitScope()` / `unitInNavScope()`).
- **API communication:** one helper, `api(path, options)` (`index.html:2919`), which adds `Authorization: Bearer <token>`, injects a client-side read-only guard for the Commander role, maps HTTP errors to `Error` objects carrying `.status`, and throws `{network:true}` on transport failure.
- **Session persistence:** `saveSession()` writes the token into **`localStorage.sentinel_token`**, the user object into `sentinel_user`, and a legacy `sentinel_session` object (`index.html:2716-2726`). The HttpOnly cookie is set by the server but the frontend does not rely on it, so **the HttpOnly protection is effectively bypassed by design**.
- **Client-side RBAC mirror:** `effectiveModules()`, `go()` redirects, `hardenReadOnlyDom()`, and `canWrite()` hide or disable controls. This is *presentation only*; the server independently rejects the same calls (§5.4).
- **Output escaping:** `esc()` (`index.html:2755`) is applied consistently in the templates that were spot-checked (187 `innerHTML` assignments; 8 interpolate a variable without `esc(`, all of which were inspected and found to insert constants or an `encodeURIComponent`-wrapped id). **No unescaped injection was found in the sample examined, but a full XSS review was not performed** — this is an *unverified* area, not a clean bill of health.
- **Offline behaviour:** the application falls back to a `localStorage` "demo database" (`persist()` / `renderDashboardLocal()`) when the backend is unreachable, with an "Offline" badge rather than a hard failure. Convenient in development; a data-integrity hazard in operations (an officer can be looking at stale or fabricated rows while believing they are live — the badge mitigates but does not prevent misreading).

### 3.2 Backend

`backend/server.py` is a **9,466-line single module** that combines:

| Layer | Location | Notes |
|---|---|---|
| Environment loading | `load_env_file()` :54 | Standard-library `.env` reader, `os.environ.setdefault` so real env wins |
| Connection factory | `get_db_connection()` :187 | New psycopg2 connection **per request**; no pool; `connect_timeout=10` |
| Compatibility shims | `SentinelRow/SentinelCursor/SentinelPGConnection` :136-186 | Emulates `sqlite3` `conn.execute(...).fetchone()` chaining on psycopg2 |
| Schema (DDL) | `SCHEMA` :220 + `VEHICLES_SCHEMA` | 21 tables, created with `CREATE TABLE IF NOT EXISTS` |
| Migrations | `migrate()` :3051 | Column-by-column `information_schema` probing + `DO $$` blocks |
| Seeds | `init_db()` :3227 | Branches, locations, stations, **9 demo users**, demo persons/records |
| RBAC | :1304-3009 | Roles, modules, permissions, denylist, read-only firewall, branch scope |
| Domain logic | :3327-7225 | Identity resolution, clearance, CID, airport, checkpoints, HR, conduct, vehicles, stations, analytics, dashboards |
| HTTP routing | `class API` :7245 | Manual `if p.path == …` dispatch for GET/POST/PATCH/PUT/DELETE |
| Process management | :9281-9360 | Port-eviction helper, bind with retry, startup self-tests |

Routing is a **hand-written `if/elif` chain over `urlparse(self.path)`** (roughly 90 branches), not a router, with a nested module-gate table (`module_for_path`) applied for GET and a second table (`post_module_for_path`) for POST. Adding a route means editing two dictionaries plus two dispatch chains — workable at this size, fragile as it grows.

**Error handling** is centralised per verb in `try/except` ladders that map exception classes to status codes:

| Exception | HTTP | Shape |
|---|---|---|
| `ReadOnlyRoleError` | 403 | `{error, code: 'read_only_role', read_only: true}` |
| `AdminOnlyWriteError` | 403 | `{error, code: 'admin_only', admin_only: true}` |
| `BranchScopeError` | 403 | `{error, code: 'branch_scope_forbidden'}` |
| `PermissionError` | **401** | `{error}` — used for *authorization* failures too (§6 M-9) |
| `LookupError` | 404 | `{error}` |
| `ValueError` | 400 | `{error}` |
| `psycopg2.IntegrityError` | 409 | `{error: 'Database constraint failed', details: str(e)}` |
| `Exception` | 500 | `{error: str(e)}` — **raw exception text to the client** |

### 3.3 Where a request goes

```
Browser (index.html)
  │  api('/api/clearance-applications', {method:'POST', headers:{Authorization:'Bearer <token>'}})
  ▼
ThreadingHTTPServer (0.0.0.0:8001)  ── one thread per request
  ▼
API.do_POST                                  server.py:8111
  ├─ canonical_api_path()   alias normalisation  (:770)
  ├─ /api/login · /api/logout  (unauthenticated paths)
  ├─ require_auth()                              (:3494)
  │     ├─ TOKENS[token] hit-check (process cache)      (:128)
  │     ├─ lookup_session(token) → SELECT ... FROM sessions
  │     └─ SELECT ... FROM users WHERE id=%s AND active=1  → user_view()
  ├─ enforce_read_only(user, 'POST', path)       (:2132)  → 403 for Commander
  ├─ module gate: post_module_for_path[prefix] → require_module()   (:3325)
  ├─ require_branch_write_scope(c, user, branch_row, 'fingerprint')  (:2707)
  │     └─ user_branch_scope() → resolve_posting_branch()  (fuzzy match of
  │        users.branch against police_branches; None ⇒ UNSCOPED)
  ├─ handler body: validation → ensure_person() → save_upload() → INSERT
  ├─ audit(c, user, 'CREATE', 'clearance_application', aid, …)   (:3522)
  ├─ c.commit()
  └─ send_json(201, {...})   (no-store, ACAO: *, no security headers)
  ▼
PostgreSQL (psycopg2, one connection per request, no pool, no TLS)
  └─ tables: persons ← clearance_applications ← clearance_signed_documents
     users ← sessions / audit_events        police_branches ← branch_id FK
```

Every response is `Cache-Control: no-store` (correct for live registers), every JSON response carries `Access-Control-Allow-Origin: *`, and **no response carries `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options` or `Referrer-Policy`** (verified with `curl -I`).

### 3.4 Database

PostgreSQL, 21 tables, all created idempotently at startup.

| Table | Cols | Purpose |
|---|---|---|
| `users` | 11 | Accounts: `username` (case-sensitive UNIQUE), `role`, `branch` (free text), `location_scope`, `badge_number`, `password_hash`, `active` |
| `sessions` | **3** | `token` (PK), `user_id` FK, `created_at` — **no expiry column** |
| `audit_events` | 7 | `user_id` FK, `action`, `entity`, `entity_id`, `details`, `created_at` |
| `persons` | 18 | Central identity registry; `person_id`, `national_id` UNIQUE (nullable) |
| `clearance_applications` | 23 | Fingerprint clearance; `branch_id`, `status`, `certificate_number`, timestamped `created_at` |
| `clearance_signed_documents` | 7 | Versioned signed-scan uploads (additive table) |
| `crime_cases`, `case_evidence`, `suspect_alerts` | 10/9/10 | CID register |
| `airport_passengers` | 14 | Airport movements |
| `checkpoint_events` | 26 | Screening events (location code + label + guardian block) |
| `officers`, `officer_promotions`, `officer_discipline`, `officer_conduct_actions`, `officer_service_history` | 31/12/13/18/10 | HR Directorate |
| `police_stations`, `police_branches`, `locations`, `vehicles`, `crime_incidents` | 18/6/4/24/26 | Registries + lookups |

- **Relationships:** real `REFERENCES` FKs throughout (persons, branches, users, cases, stations). The circular `police_stations.commander_id → officers.id` ↔ `officers.station_id` pair is closed in `migrate()` with named constraints guarded by `pg_constraint` checks — a correct and thoughtful piece of work.
- **Indexes:** primary keys and UNIQUE constraints only, plus three functional indexes (`idx_service_history_officer`, `idx_clearance_signed_documents_application`, `uq_police_branches_name_region_unit`). **There is no index on any foreign key** (`branch_id`, `person_id`, `case_id`, `user_id`) and none on `audit_events(user_id)`, `sessions(user_id)` or search columns. Fine at demo volume; a full scan per branch-filtered list at 10⁵ rows.
- **Timestamps** are stored as `TEXT` in `'YYYY-MM-DD HH24:MI:SS'` UTC (no `timestamptz`). This is the single most consequential schema decision for later work: range queries, retention and timezone reasoning all depend on string parsing (`parse_stamp()`), and the 12-hour gate is computed by parsing that string.
- **Migration mechanism:** see §7.2.

### 3.5 Authentication, sessions, storage

- Login: `POST /api/login` → `SELECT * FROM users WHERE username=%s AND password_hash=%s AND active=1` with `sha256(password)`.
- Session: 32-byte `secrets.token_urlsafe` token; row in `sessions`; process-level `TOKENS` dict as a cache; `Set-Cookie: sentinel_session=<token>; Path=/; HttpOnly; SameSite=Lax` (no `Secure`, no `Max-Age`/`Expires`).
- `require_auth` accepts **either** the cookie **or** `Authorization: Bearer`, re-reads the user row on every request (so role/deactivation changes apply immediately — good), and returns a fully decorated `user_view()` payload.
- Logout: `DELETE FROM sessions WHERE token=%s` + cookie clear. Password change: revokes *other* sessions of the same user (good) but not the current one.
- Passwords: `hashlib.sha256(value.encode()).hexdigest()` — **no salt, no work factor** (`server.py:3328`).
- Uploads: `UPLOAD_DIR = $SENTINEL_UPLOADS or backend/uploads`; filenames regenerated as `f_<16 hex><ext>`; served by `serve_static()` for `/uploads/…` from that directory with `os.path.basename()` (path traversal blocked) — **but with no authentication** (§6 C-1).

### 3.6 Configuration, startup, deployment assumptions

- Config is `.env` (root, git-ignored) + `SENTINEL_DB_*` / `SENTINEL_DATABASE_URL` / `SENTINEL_UPLOADS` / `SENTINEL_UI_DIR` / `PORT`.
- Startup (`__main__`): verify the served `index.html` build stamp → `init_db()` (create schema, run migrations, seed) → verify the review gate self-test → verify the RBAC self-test → `bind_server(port).serve_forever()`.
- **`bind_server()` evicts whatever process is listening on the port** (`terminate_listener()` :9309 sends SIGTERM then SIGKILL). On a shared host this will kill an unrelated service; in a blue-green setup it will kill the other colour. `SENTINEL_NO_PORT_TAKEOVER=1` disables it but is undocumented in the run instructions.
- `/api/health` is unauthenticated and returns build tags, `ui_path`, `ui_cwd`, `ui_git` (branch + commit), `ui_sha256`, `database_name`, `pid`, `started_at`, role lists and the live review-lock self-test result. Excellent operator ergonomics; a meaningful information-disclosure surface (§6 M-4).

### 3.7 Architectural limitations that matter

1. **No connection pooling.** Every request opens and closes a PostgreSQL connection (~5-15 ms + TLS handshake cost once TLS is enabled). At three branches × ~10 users this is survivable; it is the first thing that will break under load.
2. **One process, one port, no reverse proxy story.** TLS, compression, static caching, rate limiting and request limits all have to be added in front.
3. **`server.py` is a single 9.5k-line module.** Business logic, RBAC and DDL are interleaved; there is no import boundary that a reviewer or a test can isolate. The test suites work around this by booting a real server over real HTTP (which is actually the strongest choice available).
4. **DDL at boot.** Schema creation and migration are side effects of starting the web process (§7.2) — the single biggest obstacle to zero-downtime and to safe rollback.
5. **Two divergent schema definitions** (`server.py` and `backend/database.py`) and two dead SQLite tools (`migrate_rbac.py`, `audit_instant_approvals.py`) remain in the tree (§6 M-10).

**Is the architecture maintainable and suitable for the expected workload?** For a headquarters plus three branches with tens of concurrent officers, the runtime shape is adequate: `ThreadingHTTPServer` + PostgreSQL handles that load easily. The bottleneck is not the runtime, it is the **single-module structure, the missing dependency manifest, the missing migration discipline and the absent operational layer** (TLS, proxy, backups, monitoring). Those are the things that make change risky and deployment impossible, not the Python version.

---

## 4. Feature and workflow inventory

Statuses: **Verified** = exercised against a running server during this audit (or by a suite that passed in this audit) and behaving as documented. **Implemented-unverified** = code exists and looks correct but no passing evidence was produced. **Partial** = works with a specific, named gap. **Incomplete** = materially unfinished. **Broken** = does not behave as documented. **N/A** = not a feature.

| Feature / workflow | Status | Evidence or test | Remaining gap |
|---|---|---|---|
| Login / logout | **Partial** | Live: 7 accounts signed in; logout revokes row in `sessions`; cookie `HttpOnly; SameSite=Lax` | No `Secure`, no lockout, no login audit, no MFA, token also in `localStorage` |
| Session persistence across restart | **Verified** | Token acquired pre-restart still returned 200 on `/api/me` after a full process restart | No expiry at all; survives forever |
| User management (list/create/edit/activate/deactivate/password) | **Verified** | Live: create 201, PATCH role/branch/password/active 200, list 200; `test_station_actions.py`/`test_read_only_rbac.py` style API coverage | Self-demotion lockout, no last-admin guard, case-sensitive usernames, reset does not revoke sessions (§6 H-5, H-6, M-6) |
| Roles & module RBAC | **Verified** | 7-role × 12-endpoint GET matrix and 7-role × 9-endpoint POST matrix produced the expected 200/400/401/403 cells; `test_read_only_rbac.py` 179/179 checks | 401 used where 403 is correct (§6 M-9) |
| Global read-only Commander | **Verified** | `test_read_only_rbac.py` (179 checks), `test_station_actions.py` (165 checks); live matrix: every POST → 403 `read_only_role` | Commander cannot read `/api/admin/audit` (401) — arguably should (403 or read) |
| Branch scoping — register **reads** | **Partial** | `test_branch_scope.py` all pass; live: cross-branch `GET /api/clearance-applications/<id>` → 403 | `GET /api/persons/<id>` aggregates and `/api/persons/<id>/documents` are **not** branch-scoped (§6 H-2) |
| Branch scoping — register **writes** | **Partial** | `test_branch_scope.py` §3 all pass (cross-branch filing 403, omitted branch adopted) | `/approve` and `/signed-document` have **no** branch check (§6 H-2) |
| Branch scoping — fail-closed default | **Broken** | Live: unregistered branch label ⇒ `branch_scope: null`, `resolved: false`, and 3 (i.e. all) clearance rows visible | Every no-match path is fail-**open** |
| Central person registry + 3-tier identity resolution | **Implemented-unverified** | Code at `resolve_person()` :4974; `test_linked_records.py` (3 tests) passes | Tier 1/2/3 matching is exercised only by `test_server.py`, which **cannot run** (SQLite-era) |
| Clearance application intake + 4 document slots | **Verified** | Live: 2 applications created (201) with photo + 4 synthetic documents each | No file-size or extension validation on this path (§6 M-7); submission ≠ reviewable |
| 12-hour fingerprint review gate | **Verified** | `test_review_gate.py` (6 scenarios), `test_approval_flow.mjs` (D2/D3/E/F), boot self-test 8/8; live: fresh app → 400 `review_period_active`, backdated → Approved | Admin bypass is absolute; `purpose=Citizenship` bypasses the gate and is officer-selectable (§6 M-3) |
| Separation of duties (submitter ≠ approver) | **Broken** (by design) | Live: the submitting officer approved their own Citizenship application and received `CL-29199707` | No independent reviewer requirement anywhere |
| Signed-scan upload + versioning | **Verified** | Live: 201, row appended to `clearance_signed_documents`; `test_clearance_rbac_ui.mjs` passes | No branch scope; no content sniffing; public retrieval |
| Certificate print lock (signed scan required) | **Verified** | `test_clearance_rbac_ui.mjs` #3, `test_approval_flow.mjs` E/F, `test_field_level_rbac.py` #6 | Certification *verification* (QR/authenticity) absent |
| Certificate generation / printing | **Partial** | `test_print_fit.py`: static A4 geometry only | No end-to-end browser print test; no verify endpoint |
| CID crime cases + participants | **Verified** (happy path) | Live: 18 cases created; dedupe returns 409 | `COUNT(*)+8` id race → 4/12 concurrent writes failed (§6 H-7) |
| CID evidence upload | **Implemented-unverified** | Route exists (`/api/crime-cases/<id>/evidence`) | No test; no branch scope; no file validation |
| Suspect alerts + auto person create/merge | **Implemented-unverified** | Route + duplicate guard read; demo seed present | No audit of alert lifecycle; match tiers unverified |
| Airport records | **Verified** | `test_branch_scope.py` §5 (own-branch only, cross-branch 403); live list 200 | No dedicated integrity suite |
| Checkpoint screening (server-side result) | **Partial** | Live: a Checkpoint officer's event creation was rejected only for a missing mandatory field (`400 Purpose of visit is required`); the screening result and action are computed server-side from active suspect alerts (code review, `server.py:8648-8784`) | The client-sent `screening_result` is not trusted, but scope widens to all locations when `location_scope` is blank (§6 M-2) |
| Police Stations registry + View/Edit | **Verified** | `test_station_actions.py` (165 checks), `test_station_integration.mjs`, `test_station_frontend.mjs` all pass | — |
| Vehicles registry | **Implemented-unverified** | `vehicles.py` + `/api/vehicles` route; live 200/400 | No test suite; id generation race |
| Branch management (SystemAdmin) | **Verified** | `test_dynamic_branches.py` passes; live `POST /api/branches` gating confirmed (admin module) | `district` free text vs seeded gazetteer |
| HR officer register (officers) | **Implemented-unverified** | Multipart wizard code present; `/api/officers` 200 for HR | Registration path untested since the SQLite suite rotted |
| Promotions / discipline / conduct workflow | **Partial** | `test_field_level_rbac.py`, `test_record_audit_ui.mjs` pass; backend review desk is HR-gated | **`test_conduct_frontend.mjs` fails** (SQLite-era harness) → the conduct UI journey is unverified |
| Departmental & executive analytics | **Partial** | Endpoints return 200/400 with correct module gates | No numeric/regression validation of aggregates |
| Central person search | **Verified** | Live: all 7 roles searchable; `national_id`, `passport_id`, `mother_name`, `phone` returned | No result-level audit trail (who searched whom); no purpose-of-search |
| Central Police Search (police registers) | **Verified** | `test_read_only_rbac.py` confirms denylist for Fingerprint/Airport/CID; live matrix matches | — |
| Audit register (`/api/admin/audit`) | **Partial** | Live: `UPDATE user 1 | changed fields: role | admin` present; badge attribution rendered | **No login/logout/failed-login rows, no IP, no user agent, no before/after values** (§6 H-8) |
| Per-record audit history | **Verified** | `test_record_audit_ui.mjs` (7 scenarios), `test_checkpoint_roles_audit.py` | Branch scoping applies only to the entity types in `AUDIT_ENTITY_BRANCH_SOURCES` |
| Account lifecycle (disable/role change) | **Partial** | Live: disable → 401 immediately; role change → 401 on the old module immediately (both correct) | Reactivation revives pre-existing tokens; no deletion path; no recovery for the last admin (§6 H-5) |
| Password change (self-service) | **Verified** | Live: `/api/me/password` 200, other sessions of that user deleted | 6-character minimum only; no history, no strength check |
| Account recovery (forgotten password) | **Incomplete** | — | No flow at all; only an admin can reset, and a reset leaves live sessions intact |
| Identity documents — storage & retrieval | **Broken** | Live: `GET /uploads/f_*.jpg` and `.pdf` returned **200 anonymously** | Must be authenticated, scoped and audited (§6 C-1) |
| Backup / restore / retention | **Incomplete** | — | Nothing in the repository |
| Migrations (versioned, reversible) | **Incomplete** | `migrate()` runs on every boot; no version table | See §7.2 |
| HTTPS / TLS | **Incomplete** | Server is plain HTTP; no proxy config | — |
| Monitoring / alerting / structured logs | **Incomplete** | `log_message()` prints `IP - "METHOD path HTTP/1.1" status` to stdout | No levels, rotation, JSON, correlation ids, metrics or alerts; **unhandled exceptions are never logged server-side** |
| Offline / local demo mode | **N/A for production** | `localStorage` fallback with an "Offline" badge | Risk of stale/fabricated rows being read as live |

---

## 5. Users, roles and authorization review

### 5.1 The role model

Seven assignable roles (`ALL_ROLES`, `server.py:1477`), plus aliases and one legacy family:

| Canonical role | Label | Modules (`ROLE_MODULES`) | Capability permissions | Read-only? |
|---|---|---|---|---|
| `SystemAdmin` | System Administrator | dashboard, analytics, admin, people, fingerprint, airport, cid, checkpoints, policesearch, stations, officers, cars, crimes, conduct | `analytics:global`, `stations:manage`, `cid:view`, `personnel:view`, `transport:view` | no |
| `hr_officer` | HR Directorate Officer | dashboard, people, policesearch, stations, officers, conduct | `personnel:view` | no |
| `FingerprintUnit` | Fingerprint Unit Officer | dashboard, people, fingerprint | `cid:view` | no |
| `AirportControl` | Airport Control Officer | dashboard, people, airport | `cid:view` | no |
| `CIDUnit` | CID Criminal Unit Officer | dashboard, people, cid, crimes | `cid:view` | no |
| `checkpoint_officer` | Checkpoint Officer | dashboard, checkpoints | `cid:view` | no |
| `chief_commander` | Chief Commander (HQ / Command) | dashboard, executive, oversight, people, policesearch, fingerprint, airport, cid, checkpoints, crimes, stations, officers, conduct, cars | `analytics:global`, `cid:view`, `personnel:view`, `transport:view`, `readonly:global` | **yes (global)** |

**Verified behaviour on this model (positive):**

- The **hard unit-module denylist** (`UNIT_MODULE_DENY`) removes `policesearch` from Fingerprint/Airport/CID and is re-applied on every module answer.
- **Unknown role strings fail closed** to `dashboard` only, never to another unit's modules.
- `rbac_self_test()` runs at boot and **refuses to start** if the denylist or the read-only contract is broken.
- The legacy `CheckpointSouth/East/West` roles are normalised to `checkpoint_officer` and can no longer be assigned.
- Live 7×12 GET matrix and 7×9 POST matrix matched the intended design exactly (see §8.3), including `chief` → 403 on every mutation.

### 5.2 Account lifecycle

| Operation | Route | Enforcement | Verified |
|---|---|---|---|
| Create account | `POST /api/admin/users` | `require_module(user,'admin')` + role allow-list + badge uniqueness + password ≥ 6 | Live 201; non-admins 401 |
| List accounts | `GET /api/admin/users` | module `admin` | Live; non-admins 401 / chief 403 |
| Edit role/branch/scope/badge/active/password | `PATCH /api/admin/users/<id>` | module `admin` | Live 200 |
| Activate / deactivate | same PATCH (`active`) | module `admin` | Live: disabled user immediately 401 |
| Self-service password | `POST /api/me/password` | authenticated; verifies current password; revokes other sessions | Live 200 |
| Self-service profile / avatar | `PATCH /api/me`, `POST /api/me/avatar` | authenticated; **blocked for Commander** by the read-only firewall | Code-verified |
| Delete account | — | **no route exists** (DELETE → 405) | Live 405 |
| Recover a forgotten password | — | **no route exists** | — |

**No guard exists anywhere on the consequences of an administrative edit.** There is no check that at least one active `SystemAdmin` remains, no confirmation for self-role-change, no protection on the last administrator, and no break-glass procedure. The audit reproduced a total administrative lockout in a single PATCH (§6 H-5).

### 5.3 Is authorization enforced server-side, or only hidden in the UI?

**Both are true, and that is the good news.** For every route tested, the client-side hiding is mirrored by a server-side rejection — except on the four routes named in §5.4. The UI's job is ergonomics; the server is the boundary. Measured on a live server:

```
role        persons  clearance  airport  crime-cases  checkpoints  officers  stations  vehicles  conduct  admin/audit  admin/analytics
admin        200      200        200       200          200          200       200       200       200      200          200
fp.lasanod   200      200        401       401          401          401       401       401       401      401          401
cp.test      200      401        401       401          200          401       401       200       401      401          401
cid.officer  200      401        401       200          401          200       200       200       401      401          401
hr.officer   200      401        401       401          401          200       200       200       200      401          401
ap.officer   200      401        200       401          401          401       401       401       401      401          401
chief        200      200        200       200          200          200       200       200       200      401          401
```

and on the write surface (`POST`, empty body → 400 means "authorised but invalid", 401/403 means "refused"):

```
role        persons  clearance  airport  crime-cases  checkpoints  officers  stations  vehicles  admin/users
admin        400      400        400       400          400          400       400       400       400
fp.lasanod   400      400        401       401          401          401       401       401       401
cp.test      400      401        401       401          400          401       401       401       401
cid.officer  400      401        401       400          401          401       401       401       401
hr.officer   400      401        401       401          401          400       401       401       401
ap.officer   400      401        400       401          401          401       401       401       401
chief        403      403        403       403          403          403       403       403       403
```

### 5.4 Where the model leaks

Four concrete bypasses were reproduced. Each is a *route that does not re-apply a check its neighbours apply*:

| Route | Intended rule | Observed |
|---|---|---|
| `POST /api/clearance-applications/<id>/approve` | approver must be scoped to the application's branch | Erigavo officer approved a Lasanod application → **201 Approved `CL-29158847`** |
| `POST /api/clearance-applications/<id>/signed-document` | same | Erigavo officer attached a signed scan to a Lasanod application → **201**, row present on the record |
| `GET /api/persons/<id>/documents` | only documents the caller may read, in their branch | Erigavo officer received all 5 Lasanod document records (paths, names, uploader, timestamps) → **200** |
| `GET /api/persons/<id>` | unit/branch-scoped aggregates | A Checkpoint officer received the person's **Fingerprint clearance application** summary → **200** |

The neighbouring route is correct, which is what makes this a defect rather than a design choice: `GET /api/clearance-applications/<same id>` → **403** for the same officer, in the same session, seconds apart.

### 5.5 Is the branch/dept/record-level model sound?

The intent is good and the implementation is elaborate: postings are canonicalised (`canonical_posting_key`), matched with a minimum-confidence score (`POSTING_MATCH_MIN = 45`), and admin/Commander sessions deliberately bypass scoping. But the design has one unacceptable property:

> **`branch_scope_view()` returns `None` when the posting does not resolve, and `None` everywhere else in the code means "unrestricted".**

Verified: setting a Fingerprint officer's branch to `"Some Unregistered Post"` produced `branch_scope: null`, `branch_scope_status.resolved: false`, and the officer then saw **3 of 3** clearance applications instead of their branch's subset. Because `users.branch` is free text validated by nothing (the PATCH handler accepts any non-empty string, and the create handler defaults to `'Central HQ'`), a single typo in User Management silently removes branch isolation for that account. `test_branch_scope.py` §6 actually *asserts* this behaviour ("an unresolved posting is never silently narrowed") — a defensible intent for a legacy migration, but as the permanent default it is fail-open, and it means branch isolation cannot be relied on until postings are foreign-keyed.

### 5.6 Can a user escalate privileges?

| Attempt | Result |
|---|---|
| Non-admin lists/creates/edits users | **Blocked** — 401 for unit roles, 403 for Commander |
| Non-admin changes a role or resets a password | **Blocked** — same |
| User edits own role/branch/`active` via `/api/me` | **Blocked** — `/api/me` accepts only `display_name`, `avatar_preset` |
| User self-registers | **No route exists** |
| Admin grants themselves another role | **Allowed** — and that is the lockout defect (H-5) |
| User reads another branch's record | **Blocked** on register endpoints (403); **allowed** on the four routes in §5.4 |
| Session token reused after role change | **Refused** — role is re-read per request |
| Session token reused after deactivation | **Refused** while disabled; **accepted again after reactivation** |

No privilege-escalation path *upward* was found for a non-administrator. The escalation risk in this build is **lateral (cross-branch data and cross-branch actions)**, not vertical.

### 5.7 Audit coverage of account and permission changes

Present and correct: `CREATE user`, `UPDATE user` with the **list of changed columns** (`"changed fields: role"`), `UPDATE user_password`, `UPDATE user_avatar`, `UPDATE user_profile`, and per-record domain events.

Missing: **every authentication event**. After 15 failed logins, 7 successful logins, logouts, a password reset and a deactivation, `/api/admin/audit` contained only the two domain rows created by the clearance test — **no LOGIN, LOGOUT, FAILED_LOGIN or SESSION rows**. There is no source IP, no user agent, no session identifier, and no before/after value capture, so "who changed the Commander's role and to what" cannot be answered from the log alone.

### 5.8 Regressions or inconsistencies introduced by recent upgrades

1. `POST /api/clearance-applications/<id>/approve` and `/signed-document` were not brought under the new branch-scope helper — every sibling read route was.
2. `person_document_records()` applies the checkpoint location scope but **not** the fingerprint branch scope, so the two units are treated differently inside one function.
3. `checkpoint_scope()` treats a blank `location_scope` as "see all", so clearing the field in the Edit Officer modal widens the account from one checkpoint to the country (verified: `visible_locations` went from `['South']` to `['South','East','West']`).
4. The user-management module introduced self-demotion with no guard — a capability that did not exist before role editing was added.
5. `POST`/`PATCH` permission failures return **401**, and the frontend signs a user out on 401 — so an officer who clicks a control they are not permitted to use is logged out mid-session instead of being told "not permitted" (403).
6. `rbac_self_test()` ends with `return problems` followed by unreachable code that would have populated `ROLE_LOCATION_SCOPE`/`ROLE_LABELS` for unit aliases (`server.py:2040-2044`). Harmless today because the lookup path uses `canonical_unit_role()`, but it is dead code directly under a security self-test.

---

## 6. Security findings

Severity: **Critical** (blocks any real deployment) · **High** (must fix before pilot) · **Medium** (fix before production) · **Low** (harden when convenient).
Verification: **Verified** = reproduced against the running system during this audit · **Code review** = read, not executed · **Unverified** = could not be established.

### C-1 — Identity documents are downloadable without authentication
**Severity:** Critical · **Verified**
**Affected:** `backend/server.py:7404-7412` (`API.serve_static`, `/uploads/` branch) · storage dir `$SENTINEL_UPLOADS`/`backend/uploads/`
**Evidence:** `GET /uploads/f_12293f1bf565e1da.jpg` → `200 image/jpeg`; `GET /uploads/f_608b65f944d6e5e2.pdf` → `200 application/pdf`. Both requests carried **no cookie and no Authorization header**. The file paths are returned by authenticated JSON (`/api/persons/<id>/documents`, `/api/clearance-applications/<id>`), so any leak of a URL — proxy logs, browser history, a shared screenshot, a pasted audit row — grants permanent unauthenticated access to an identity document, a signed clearance scan or a guarantor's ID.
**Impact:** Unbounded disclosure of national IDs, passports, birth certificates, guarantor documents and photographs, at a URL that never expires and cannot be revoked without deleting the file. Combined with H-2 this becomes cross-branch disclosure, not merely cross-session.
**Fix:** Remove `/uploads/` from the public static handler. Serve documents only through `GET /api/documents/<opaque-id>` which (a) authenticates, (b) re-applies the record's branch/module scope, (c) writes an audit row (`READ document`), (d) returns `Content-Disposition: attachment` with `X-Content-Type-Options: nosniff`, and (e) issues a short-lived signed URL only if the UI genuinely needs direct `<img src>` access. Store files outside the served tree.

### C-2 — Nine default accounts with a shared, publicly documented password
**Severity:** Critical · **Verified**
**Affected:** `init_db()` seeds, `server.py:3278-3298`; documented in `README.md:563-586`
**Evidence:** A fresh database contained `admin`, `fp.officer`, `ap.officer`, `cid.officer`, `hr.officer`, `cp.south`, `cp.east`, `cp.west`, `chief` — all with password `ChangeMe123!`. All nine authenticated successfully during the audit. There is no forced password change, no "must change on first login" flag, no expiry, and no indicator on the login screen that demo credentials are in use.
**Impact:** A deployed instance is compromised at first boot by anyone who has read the public README. Full administrative control of every register, and of user management.
**Fix:** Seed demo *roles* only when an explicit `SENTINEL_DEMO_SEED=1` (or equivalent) is set; never seed a working `SystemAdmin`. Generate a random password for the first administrator, print it once to the console (`must_change_password = true`), and refuse to start in a non-development mode if any seeded account still holds its default hash.

### C-3 — Unsalted SHA-256 password storage
**Severity:** Critical · **Verified**
**Affected:** `password_hash()` `server.py:3328`; comparison inside the login SQL
**Evidence:** `SELECT password_hash FROM users WHERE username='admin'` returned `bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721`, which is the publicly published `sha256("abcdef")` — a value the audit produced by setting that password through `POST /api/me/password`, which the API accepted without complaint. Every hash in the table is a bare, unsalted, single-round SHA-256.
**Impact:** Any database disclosure (backup, `pg_dump`, SQL injection, stolen disk) yields near-instant recovery of most operational passwords via rainbow tables or GPU brute force. Users reuse passwords, so the blast radius extends beyond Sentinel. Identical passwords are trivially identifiable by hash equality.
**Fix:** Migrate to Argon2id (`argon2-cffi`) or bcrypt/scrypt with per-user salt and a documented work factor; verify-and-rehash on successful login so existing rows upgrade transparently; add a password policy (length ≥ 12, no reuse of the last N) and force a rotation for every account created before the change.

### H-2 — Branch isolation is missing on the approval, signed-scan and document routes
**Severity:** High · **Verified**
**Affected:** `POST /api/clearance-applications/<id>/approve` (`server.py:8468-8512`), `POST …/signed-document` (`:8433-8467`), `GET /api/persons/<id>/documents` → `person_document_records()` (`:5197`), `GET /api/persons/<id>` aggregates (`:7627-7640`)
**Evidence:** An officer whose posting resolved to **Erigavo Branch** (verified `branch_scope.branch_name = 'Erigavo Branch'`):
- `POST /api/clearance-applications/FP-29144213/signed-document` → **201**, and the Lasanod application then listed 1 signed document;
- after the record's `created_at` was backdated in the *disposable* test database, `POST …/approve` → **201 `{"status":"Approved","certificate_number":"CL-29158847"}`**;
- `GET /api/persons/P-…/documents` → **200** with 5 documents sourced from the Lasanod application;
- while `GET /api/clearance-applications/FP-29144213` → **403** for that same officer.

**Impact:** An officer at one branch can read, alter and **issue a certificate** for another branch's clearance file. This defeats the branch-separation requirement at exactly the point where the system makes a legal/administrative decision. It also makes the audit trail misleading: the record shows an approval by an officer with no authority over that branch.
**Fix:** Call `require_record_branch_scope()` on every member route (`/approve`, `/signed-document`, document manifests, printable pages) with the record's own `branch_id`, exactly as the read route does. Add `fingerprint` branch filtering to the document manifest query. Then add the regression tests that would have caught this (see §10, H-2 test).

### H-3 — Sessions never expire and are not revoked on the events that matter
**Severity:** High · **Verified**
**Affected:** `SCHEMA.sessions` (3 columns, no expiry), `lookup_session()` `:3448`, `create_session()` `:3466`, `PATCH /api/admin/users/<id>` `:9037`
**Evidence:**
- `sessions` has `token`, `user_id`, `created_at` and nothing else. `lookup_session()` selects a row and returns it; there is no age check anywhere. 20 sessions accumulated in a 30-second audit and all remained valid.
- A token issued before a **full server restart** still returned `200` on `/api/me` afterwards (good for deployment, bad for expiry).
- An administrator reset a user's password: the **old token continued to work (200)** while the old password correctly stopped working (401) and the new one worked (200).
- Disabling the account killed the session (401) — but **re-enabling it revived the pre-existing token (200)** without a new login.
**Impact:** A stolen token is valid forever, survives password rotation and every deployment, and is silently resurrected by any reactivation. Password reset — the standard incident response — does not terminate the attacker's access.
**Fix:** Add `expires_at`, `last_seen_at`, `revoked_at`, `user_agent` and `ip` to `sessions`; enforce an absolute lifetime (e.g. 12 h) plus an idle timeout (e.g. 30 min) with sliding renewal; delete all rows for a user on password change/reset, role change, deactivation and explicit logout; add a "sign out everywhere" action and an administrators' session list.

### H-4 — No login throttling, lockout or authentication audit
**Severity:** High · **Verified**
**Affected:** `POST /api/login` `:8122-8137`
**Evidence:** 15 consecutive wrong-password attempts against `admin` all returned 401 with no delay, no counter and no lockout; the 16th attempt with the correct password returned 200. No `LOGIN`, `LOGOUT` or `FAILED_LOGIN` row appeared in `audit_events` after any of it.
**Impact:** Online password guessing against a 9-account system with a 6-character minimum is entirely feasible; the seeded password is publicly known. Credential-stuffing incidents would leave no trace, and successful logins cannot be attributed.
**Fix:** Per-account and per-IP rate limiting with exponential backoff (proxy or application level), temporary lockout after N failures with an administrative unlock, audit rows for `LOGIN_SUCCESS` / `LOGIN_FAILED` / `LOGOUT` (never containing the password), and alerting on failure spikes.

### H-5 — A System Administrator can lock the organisation out of user management
**Severity:** High · **Verified**
**Affected:** `PATCH /api/admin/users/<id>` `:9037-9125`
**Evidence:** Signed in as `admin` (id 1, sole `SystemAdmin`), `PATCH /api/admin/users/1 {"role":"hr_officer"}` → **200**, account role became `hr_officer`. The immediate attempt to undo it, `PATCH … {"role":"SystemAdmin"}` → **401 "Restricted to HR Directorate Officer"** — permanent until an engineer edits the database. The audit restored the row with SQL on the disposable cluster only.
**Impact:** Administrative self-lockout is one click away in the Edit Officer modal (and a plausible *deliberate* denial-of-service by any admin). On a fresh install there is exactly one administrator, so recovery requires direct database access — which, given C-3 and the absence of documented backup/restore, may itself be unavailable.
**Fix:** Refuse any change that would leave zero active `SystemAdmin` rows (checked inside the same transaction, with `SELECT … FOR UPDATE` on the admin rows); require an explicit confirmation token for self-role-change; add a break-glass CLI (`--create-admin`) that requires filesystem access; audit both the refusal and the override.

### H-6 — Registration/identifier generation races
**Severity:** High · **Verified** (and code review for the rest)
**Affected:** crime case id `server.py:8520-8524` (`SELECT COUNT(*)+8`), clearance application id `:8420` (`'FP-'+last 8 digits of epoch ms`), certificate number `:8506` (same), `new_vehicle_id()` `vehicles.py:31`, `next_badge_number()` `:2313`, `new_service_id()` `:3825`, `new_station_id()` `:3813`, `new_person_id()` `:3793` (retry loop)
**Evidence:** 12 concurrent `POST /api/crime-cases` from the CID account produced **8× 201** (`CID-2026-010` … `CID-2026-017`) and **4× 409 `{"error":"Database constraint failed"}`**. No duplicate id was created (the UNIQUE constraint saved the data), but a third of the writes failed with a message that tells the officer nothing. The prefix is also hard-coded to `CID-2026-`, which will be wrong in 2027.
**Impact:** Officers lose work and retry blindly; the 409 body leaks the constraint name; the year prefix will silently mislabel records. Two applications submitted in the same millisecond on the same instance collide at `FP-<ms>`; the same applies to certificates.
**Fix:** Use a PostgreSQL sequence (or `GENERATED` identity) per register and format the human id from it inside one transaction; `INSERT … RETURNING`; derive the year from `CURRENT_DATE`; catch `UniqueViolation` and retry once server-side instead of surfacing a 409 for a generated identifier; return `409` only for genuine user-supplied duplicates.

### H-7 — Incomplete and mutable audit trail
**Severity:** High · **Verified** (coverage) / **Code review** (immutability)
**Affected:** `audit()` `:3522`, `audit_events` table, `audit_trail()` `:3567`
**Evidence:** No authentication, session, export, print or document-read events are recorded. No source IP, user agent, session id, or before/after value is stored. `audit_events` is an ordinary table that the application connection owns and can `UPDATE`/`DELETE`; there is no append-only trigger, no chain/hash, no WORM storage and no retention policy. Rows do not survive a user deletion with any link other than a nullable FK (rendered as `#Not recorded`).
**Impact:** In a police context the audit log must answer "who saw/decided/changed what, when, from where" under challenge. It currently answers "who created this record" and, for user edits, which columns moved — not what changed to what, and nothing at all about access.
**Fix:** Add authentication/session/read events; store `ip`, `user_agent`, `session_id`, `before`/`after` JSON; make the table append-only (`REVOKE UPDATE, DELETE` from the app role, `BEFORE UPDATE/DELETE` trigger raising an exception); optionally hash-chain rows; ship to an external append-only sink; define retention and export for legal discovery.

### H-8 — No HTTPS, no `Secure` cookie, and the token is duplicated into `localStorage`
**Severity:** High · **Verified**
**Affected:** `bind_server()` `:9342` (plain HTTP), cookie construction `:8135`, `index.html:2716-2726`
**Evidence:** `Set-Cookie: sentinel_session=…; Path=/; HttpOnly; SameSite=Lax` — no `Secure` attribute, no `Max-Age`, no `__Host-` prefix. The server has no TLS listener and the repository carries no proxy configuration. `GET /` returned no HSTS. `saveSession()` writes the same bearer token into `localStorage`, where any script on the origin can read it, so `HttpOnly` buys nothing while the frontend relies on the stored copy.
**Impact:** Passwords and bearer tokens cross the network in clear text (trivially captured on a branch LAN or over the public internet); a single XSS becomes total, persistent account takeover; without `Secure`, the cookie can be sent over an HTTP downgrade.
**Fix:** Terminate TLS at a reverse proxy with HSTS (see §11); add `Secure` (and `__Host-`); **choose one transport** — either the cookie (and delete the `localStorage` copy) or the bearer token — not both; shorten session lifetime (H-3); add a CSP with nonce-based inline script or move the inline JS into a static file with a strict policy.

### M-1 — `/api/persons/<id>` exposes every unit's records for a person
**Severity:** Medium · **Verified**
**Affected:** `server.py:7627-7640`
**Evidence:** A Checkpoint officer (`cp.south`) fetched an audit person and received `clearance: [{application_id, purpose, status, certificate_number}]` — a Fingerprint unit record — plus (for persons with such data) airport movements, suspect alerts and **all** checkpoint events regardless of location. No module or branch filter is applied on this route, unlike `/documents`, `/linked-records` and `/audit-history`, which do filter.
**Impact:** Cross-unit and cross-branch metadata disclosure; a checkpoint officer can enumerate a person's clearance and criminal-alert history.
**Fix:** Reuse the same module/scope filter as `linked_person_records()`; return only the sections the caller's modules and branch allow, with an explicit "hidden by policy" marker (already the documented pattern).

### M-2 — Clearing a checkpoint officer's `location_scope` widens them to every checkpoint
**Severity:** Medium · **Verified**
**Affected:** `checkpoint_scope()` `:2939-2976`; `PATCH /api/admin/users/<id>` accepts an empty `location_scope`
**Evidence:** Before: `scope = 'South'`, `visible_locations: ['South']`. After an administrator saved the field empty: `scope = ''`, `visible_locations: ['South','East','West']` and the unfiltered query branch was taken.
**Impact:** A single innocuous edit in the Edit Officer modal converts a location-isolated officer into a national checkpoint viewer, with no warning to the administrator.
**Fix:** Reject a blank `location_scope` for checkpoint roles at the API (the create path already requires one — the update path does not); make "no scope" an explicit deny, never "all"; keep "all" as an admin-only flag.

### M-3 — The 12-hour review gate is bypassable by the submitter, and there is no separation of duties
**Severity:** Medium · **Verified**
**Affected:** `citizenship_wait_exempt()` `:915`, `review_gate_decision()` `:920`, approve route `:8468`
**Evidence:** An officer created an application with `purpose = "Citizenship"` (one of five officer-selectable reasons) and then approved **their own** application in the same session, receiving `CL-29199707` with `review_period_bypassed: true`, seconds after submission. No route requires approver ≠ submitter, and any `SystemAdmin` bypasses the window unconditionally.
**Impact:** The 12-hour control is a speed bump that the data-entry officer can remove by choosing a dropdown value. The gate is the system's headline integrity control for certificates.
**Fix:** Make the `Citizenship` exemption a *server-side attribute* of a verified purpose (or remove it), require the approver to be a different account with a distinct role/permission from the creator, require an approval reason, and record both accounts in the certificate's audit trail.

### M-4 — Unsafe error responses and health-endpoint disclosure
**Severity:** Medium · **Verified**
**Affected:** `except Exception … send_json(500, {'error': str(e)})` throughout; `IntegrityError → {'details': str(e)}`; `/api/health` `:7444`
**Evidence:** A malformed JSON body returned `500 {"error": "'str' object has no attribute 'get'"}`. A duplicate insert returned `409 {"error":"Database constraint failed","details":"…"}` carrying the constraint name. A 404 echoes the caller's input (`Station "DOES-NOT-EXIST" does not exist`). An **unauthenticated** `/api/health` returns `ui_path`, `ui_cwd`, `ui_git.branch`, `ui_git.commit`, `ui_sha256`, `database_name`, `pid`, `started_at` and the internal build tags.
**Impact:** Reconnaissance aid (exact revision, filesystem layout, database name, whether the review lock is armed) and internal-detail leakage that helps targeted exploitation; echoed input is a small reflected-content risk in any consumer that renders errors.
**Fix:** Map unexpected exceptions to a generic `500 {"error":"Internal error","incident":"<id>"}` and log the detail server-side with that id; never return `str(e)` or driver text; reduce `/api/health` to `{status}` for anonymous callers and put the diagnostic payload behind authentication (or a separate admin/metrics port).

### M-5 — No security headers; permissive CORS
**Severity:** Medium · **Verified**
**Affected:** `send_json()` / `send_file()` headers
**Evidence:** Responses carry `Server: BaseHTTP/0.6 Python/3.11.2` and `Access-Control-Allow-Origin: *`; there is no `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy` or HSTS. This is a credential-less CORS policy, so it does not by itself expose the cookie, but it does allow any origin to read unauthenticated responses and to probe the API.
**Impact:** Clickjacking of the operator console, MIME-sniffing of served uploads, no mitigation depth against XSS, and version fingerprinting.
**Fix:** Add the standard header set at the proxy (CSP with `default-src 'self'`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer`, HSTS with preload); restrict `Access-Control-Allow-Origin` to the known origin(s) or drop it entirely (the app is same-origin); suppress the `Server` banner.

### M-6 — Case-sensitive usernames allow confusable duplicate accounts
**Severity:** Medium · **Verified**
**Affected:** `users.username TEXT UNIQUE`; `POST /api/admin/users` duplicate check
**Evidence:** Creating `Audit1baf` and `AUDIT1BAF` both returned **201** — two distinct accounts whose names differ only by case, while the badge-number uniqueness check *is* case-insensitive. Audit attribution prints the username, so the two are indistinguishable in the log at a glance.
**Impact:** Impersonation by near-duplicate account name; ambiguous audit attribution; accidental duplicate provisioning.
**Fix:** Add `CREATE UNIQUE INDEX … ON users (LOWER(username))` (or use `citext`), reject case-insensitive duplicates at the API, and normalise usernames on input.

### M-7 — Upload validation is inconsistent, and storage is unprotected
**Severity:** Medium · **Verified** (bypass) / **Code review** (scanning/retention)
**Affected:** `save_upload()` `:3429` vs `save_upload_validated()` `:3844`; clearance intake `:8400-8405`
**Evidence:** The clearance intake calls `save_upload()` directly for the applicant/guarantor documents, which applies **no extension allow-list and no size cap**; officer/vehicle/conduct paths use `save_upload_validated()` (extension + 5 MB). The signed-scan route validates extension and a 20 MB cap but not content. Files are written to local disk, unencrypted, inside the application directory, with no malware scan, no retention rule and no per-file access log.
**Impact:** Disk exhaustion by an authenticated officer; storage of arbitrary file types; no defence against a malicious document; no evidence of chain-of-custody handling.
**Fix:** One validated upload helper everywhere (allow-list, magic-byte sniffing, size cap, image re-encode), storage outside the web root in an encrypted volume or object store with server-side encryption and versioning, an AV scan hook, retention policy, and an access-audited download route (see C-1).

### M-8 — Database access is superuser, unencrypted and unpooled
**Severity:** Medium · **Code review** / **Verified** (account used)
**Affected:** `get_db_connection()` `:187`; `.env.example`; `backend/database.py`
**Evidence:** The application connects as `postgres` (superuser) by default, with an empty-password default in code and `SENTINEL_DB_PASSWORD=change-me` in `.env.example`. No `sslmode` is specified, so the connection is plaintext unless the server forces TLS. A new connection is opened per request with no pool. PostgreSQL's own `pg_hba`/role configuration is not in the repository and could not be assessed.
**Impact:** A single application compromise yields full database ownership (including the ability to rewrite the audit log); database traffic would be readable on the HQ network segment once the DB is not co-located; connection churn limits throughput and amplifies TLS cost.
**Fix:** Create a least-privilege role (`SELECT/INSERT/UPDATE` on the business tables, **no** `DELETE`/`TRUNCATE`/DDL, **no** rights on `audit_events` beyond `INSERT`/`SELECT`), a separate migration role used only by the migration job, `sslmode=verify-full`, credentials from a secret manager (never a file in the repo), a connection pool (`psycopg2.pool` / pgbouncer), and documented `pg_hba` rules.

### M-9 — Authorization failures return 401, so clients sign users out
**Severity:** Medium · **Verified**
**Affected:** the `except PermissionError → 401` ladders in every verb; `index.html` `api()` (only 401 triggers sign-out)
**Evidence:** A legitimate HR officer calling `/api/clearance-applications` receives `401`, which the client interprets as "session ended". The read-only Commander receives `403` for writes (correct) but `401` for `/api/admin/audit` (a permission outcome).
**Impact:** Users are logged out for permission denials, losing in-progress work; monitoring cannot distinguish an attack (401 storms) from misconfigured roles; the response contract is inconsistent with the three purpose-built 403 shapes the codebase already defines.
**Fix:** Return `403` for authenticated-but-unauthorised and reserve `401` for missing/invalid/expired credentials; update the client to sign out only on `401` **and** a machine-readable `code: 'unauthenticated'`.

### M-10 — Stale SQLite-era artifacts and missing dependency manifests
**Severity:** Medium · **Verified**
**Affected:** `backend/database.py` (divergent DDL), `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`, `backend/test_server.py`, `backend/test_conduct_frontend.mjs`; no `requirements.txt`/`package.json`
**Evidence:** `migrate_rbac.py` and `audit_instant_approvals.py` open `sqlite3.connect(SENTINEL_DB or backend/sentinel.db)` and would silently operate on a **SQLite file that no longer holds the data** — `audit_instant_approvals.py --revert` would report a clean database while changing nothing. `database.py` declares a *different* `officers`/`officer_service_history` schema and, if run first on an empty PostgreSQL database, would create a table missing the columns `server.py` requires. `test_server.py` fails with `RuntimeError: server did not start` and `test_conduct_frontend.mjs` spawns the server against `SENTINEL_DB=<sqlite path>` (both fail — see §8). No dependency manifest exists, so `psycopg2-binary`, `pgserver` and `jsdom@26` versions are unpinned and unknown.
**Impact:** An operator following the README's "standalone migration script" pointer runs a script against the wrong engine and believes migration succeeded; a security auditor runs the review-lock forensic tool and is told the database is clean when it is not; the "conduct" UI journey has no trustworthy test; builds are not reproducible.
**Fix:** Delete the four dead artifacts (or rewrite them for PostgreSQL under a `tools/` directory with explicit engine checks); add `requirements.txt` (pinned, ideally with hashes) and `package.json`; add a CI job that runs the full suite on a throwaway cluster.

### M-11 — Migrations are unversioned boot-time side effects; the process steals its port
**Severity:** Medium · **Verified** (behaviour) / **Code review** (concurrency)
**Affected:** `migrate()` `:3051`, `init_db()` `:3227`, `__main__` startup, `terminate_listener()` `:9309`
**Evidence:** `init_db()` runs on every start: `CREATE TABLE IF NOT EXISTS`, `information_schema` probing for ~60 named columns, four `DO $$` blocks, and backfills. There is no `schema_migrations` table, no ordering, no checksum, no down-migration, no advisory lock (two instances starting together can race the DDL), and no record of which version is applied. `bind_server()` sends SIGTERM/SIGKILL to **any** process holding the port.
**Impact:** A release cannot be rolled back independently of the schema; a blue-green start can migrate the shared database mid-flight for the live colour; two workers starting concurrently can deadlock on DDL; a restart on a shared host can kill an unrelated service.
**Fix:** Extract migrations into a versioned, forward-only `migrations/` directory applied by a separate job under `pg_advisory_lock`, with a `schema_migrations(version, applied_at, checksum)` table; make the web process **verify** the expected version and refuse to serve on mismatch; adopt expand/contract for breaking changes; remove port eviction from the default path.

### M-12 — No backup, restore, retention, monitoring or DB-aware health check
**Severity:** Medium · **Code review** / **Verified** (absence)
**Affected:** repository (nothing present); `/api/health` does not touch the database
**Evidence:** No backup configuration, no restore procedure, no WAL/archive settings, no retention policy, no RPO/RTO statement, no monitoring or alerting integration, no log rotation, no structured logs. `/api/health` returns `200` without executing a single query, so it reports healthy while PostgreSQL is unreachable or the schema is wrong.
**Impact:** Any disk loss is total data loss; a restore has never been rehearsed; an outage is discovered by a user, not an alert; a load balancer would keep routing to a broken instance.
**Fix:** Automated base backup + WAL archiving (PITR) with an off-site copy, encrypted; a documented and **rehearsed** restore runbook with a measured restore time; file-storage backup covering uploads; `/api/health` (`/healthz` for liveness, `/readyz` for a `SELECT 1` + schema-version check); metrics + log shipping; retention policy per record class.

### L-1 — No CSRF tokens
**Severity:** Low · **Verified** (absence) / mitigated
Both cookie and bearer transports are accepted, and no request requires an anti-CSRF token. This is currently mitigated because the cookie is `SameSite=Lax` and because the frontend sends a bearer token that a cross-site form cannot set. **Remediation:** once the cookie is the primary transport (H-8), add a double-submit CSRF token or require a custom header on every mutation.

### L-2 — Weak password policy
**Severity:** Low · **Verified**
Minimum length 6, no complexity, no common-password check, no reuse history, no rotation for seeded accounts. A 6-character password (`abcdef`) was accepted through the self-service change route.

### L-3 — Logging quality and PII in logs
**Severity:** Low · **Verified**
`log_message()` emits `IP - "GET /api/persons?q=<name> HTTP/1.1" 200 -` to stdout: a search query containing a person's name is written in clear text, unrotated, with no retention control. Unhandled exceptions are **not** logged at all (they are only returned to the client), so server-side forensics are impossible.

### L-4 — Predictable identifiers and no certificate verification
**Severity:** Low · **Verified**
Application ids (`FP-<last 8 digits of ms>`), certificate numbers (`CL-…`) and crime case ids (`CID-2026-0NN`) are sequential or timestamp-derived, so they are enumerable. There is no endpoint (or QR target) to verify a printed certificate's authenticity, though `certificate.html` is a public document that a third party will need to validate.

### L-5 — No MFA/SSO, and no account-recovery workflow
**Severity:** Low (blocking for production under §11)
Authentication is a username and password only; there is no identity provider, no MFA, no recovery, no email/phone verification and no "suspicious sign-in" handling. For a police system this is a compliance gap as much as a security one.

### L-6 — Offline/local-demo mode can present non-live data
**Severity:** Low · **Code review**
When the backend is unreachable the UI renders a `localStorage` dataset with an "Offline" badge. A user under pressure can mistake cached or seeded rows for live operational data; writes in that mode are stored locally and reported as drafts.

### L-7 — Dead code inside a security self-test
**Severity:** Low · **Verified**
`rbac_self_test()` returns before the `ROLE_LOCATION_SCOPE.setdefault(...)` / `ROLE_LABELS.setdefault(...)` alias loop (`server.py:2040-2044`), leaving unreachable statements immediately beneath the function's pass/fail return. No impact today (lookups go through `canonical_unit_role()`), but a future edit that relies on those aliases would silently misbehave.

### Dependency vulnerability scan — not performed
No `requirements.txt`/`package.json` exists, and public vulnerability scanning of third-party packages was out of scope under this audit's rules. Installed versions observed: `psycopg2-binary 2.9.13`, `pgserver` (unpinned), `jsdom@26`, Python 3.11.2, PostgreSQL bundled with `pgserver`. **Status: unverified.** A pinned manifest plus an offline `pip-audit`/`npm audit` run against a vendored lock file is required before production.

---

## 7. Database and recovery review

### 7.1 Integrity

**Present and correct:**
- UNIQUE constraints on every human-facing identifier (`person_id`, `national_id`, `application_id`, `case_id`, `event_id`, `alert_id`, `station_id`, `code`, `service_id`, `vehicle_id`, `plate_number`, `vin`, `username`, `action_id`, `nomination_id`, `evidence_id`) — these are what prevented duplicates in the concurrency test.
- Real foreign keys with `ON DELETE SET NULL`/`CASCADE` where appropriate; the circular station↔officer FK is closed correctly after both tables exist.
- `CHECK` on `police_branches.unit_type` (widened idempotently when `police_station` was added).
- One connection per request and a single `commit()` per successful write — no shared cursor or cross-thread transaction reuse, which is the right call for `ThreadingHTTPServer`.
- `ROLLBACK`-by-`close()` semantics: an exception before `commit()` discards the transaction, so a partial write was **not** observed (the 4 failed case inserts left no orphan rows).

**Gaps:**
- **No transaction spans a multi-step business rule that needs it.** Identifier generation reads, then inserts, in separate statements without `SELECT … FOR UPDATE` or a sequence (H-6).
- **No `deferrable`/`SERIALIZABLE` isolation** anywhere; default `READ COMMITTED`.
- **No index on any FK**; no index supporting the branch/location filters used by every list query.
- **Timestamps as `TEXT`**, which blocks efficient range queries and retention jobs and relies on Python-side parsing for the review gate.
- **`persons.national_id` is nullable and UNIQUE**, so duplicate identities are prevented only by application logic when no national ID is supplied (three-tier fuzzy matching, unverified — see §4).
- **`audit_events` is mutable by the application role** (H-7).
- **`sessions` has no expiry column** (H-3) and grows without bound.

### 7.2 Migration behaviour

| Property | Current state |
|---|---|
| Versioned? | **No.** No `schema_migrations` table, no versions, no ordering, no checksums |
| Repeatable? | **Yes, by construction** — `CREATE TABLE IF NOT EXISTS`, per-column `information_schema` probes, `pg_constraint` guards, `ON CONFLICT DO NOTHING`. Repeated starts on a clean database were observed to be no-ops. |
| Safe for existing records? | **Mostly.** Every documented change is additive (`ADD COLUMN`, backfills). The one destructive operation is `ALTER TABLE police_branches DROP CONSTRAINT` inside the `DO $$` widening block — it drops *a* check constraint (the **first** one found by an unordered `SELECT … LIMIT 1`), which is fragile if the table ever gains a second check constraint. |
| Applied when? | **On every application start**, as a side effect of the web process |
| Concurrency-safe? | **No advisory lock** — two processes starting together execute DDL concurrently |
| Reversible? | **No down-migrations.** Rolling back the application does **not** roll back the schema |
| Rollback of a failed deployment | Application: re-deploy the previous code (sessions survive — verified). Database: **only via a restore** (no backup exists) |
| Seeding | Demo users, persons, applications and cases are inserted when their table is empty. A production database created by this code path therefore contains fabricated police records unless the seed block is removed. |

### 7.3 Registration-number generation under concurrency

Measured (12 parallel writes, one process, one database):

| Generator | Mechanism | Under concurrency |
|---|---|---|
| `crime case_id` | `SELECT COUNT(*)+8` then insert | **4 of 12 failed** with `409 Database constraint failed`; no duplicates (UNIQUE held) |
| `clearance application_id` | last 8 digits of epoch **milliseconds** | Collides for sub-millisecond-parallel submissions; UNIQUE would reject the second |
| `certificate_number` | same scheme | Same exposure; a retry is not automatic |
| `vehicle_id` | scan all ids, `max+1` | Same exposure |
| `badge_number` | scan all badges, `max+1`, then app-level uniqueness check | Same exposure; the check-then-insert window is a race |
| `service_id` / `station_id` | `ORDER BY … DESC LIMIT 1` + 1, or `COUNT(*)` | Same exposure |
| `person_id` | timestamp + existence retry loop | Retries; degrades under contention |
| `audit_events.id`, `sessions`, `users.id` | `SERIAL` / UUID-ish token | **Safe** |

The UNIQUE constraints are the only reason this is a reliability defect rather than a data-corruption defect. They are doing load-bearing work that a sequence should be doing.

### 7.4 Failure behaviour

- Database unreachable **at startup**: documented, precise, credential-safe error and a clean exit (`__main__`), including a branch that never prints a connection URL that may embed a password. Good.
- Database unreachable **during operation**: every request raises `OperationalError`, which is **not** caught specifically — it falls into `except Exception` and becomes `500 {"error": "<driver message>"}`, i.e. it leaks driver text and gives the operator no distinguishing signal from a code bug.
- Transaction/serialization failure: falls into the same `500`; no retry, no idempotency key.
- Upload failure: `save_upload()` writes the file **before** the database insert; a failed insert after a successful write leaves an orphan file (unreferenced but publicly downloadable — see C-1). No cleanup job exists.
- Crash mid-request: uncommitted work is discarded (correct); uploaded files are not.

### 7.5 Backup, restoration and rollback — current state

**Nothing exists.** No `pg_dump` schedule, no base backup, no WAL archiving, no off-site copy, no restore runbook, no rehearsal record, no upload-directory backup, no retention policy, no RPO/RTO statement, no integrity verification (e.g. periodic `pg_restore --list` or row-count comparison). Application rollback is limited to re-deploying a previous directory; **database rollback is not possible** because there is no snapshot to return to and no down-migration.

**Minimum before a pilot:** nightly base backup + continuous WAL archiving to encrypted off-site storage; a documented restore procedure; a **rehearsed** restore into a clean environment with a measured restore time and a row-count/file-count verification; upload-directory backup on the same schedule; and a written decision on RPO/RTO (suggest RPO ≤ 15 min, RTO ≤ 4 h).

---

## 8. Test report

### 8.1 What exists

23 suites: 11 Python scripts and 12 Node/jsdom scripts. There is no test framework and no CI; suites print `ok: …` lines, assert with exceptions, and exit non-zero on failure. Suites that need a database either use configured `SENTINEL_DB_*`/`SENTINEL_DATABASE_URL` settings or boot a **throwaway `pgserver` cluster** — the latter is the behaviour observed and is the correct pattern.

Environment used for this audit (created only to run tests, git-ignored):

```bash
python3 -m venv .venv
.venv/bin/pip install psycopg2-binary pgserver      # psycopg2 2.9.13
npm install --no-save --package-lock=false jsdom@26
```

No `.env` exists in the repository, so no suite could reach a configured live database even if one existed; every suite that needs PostgreSQL provisioned its own ephemeral cluster.

### 8.2 Results (exact)

**Python — 10 of 11 passed**

| Suite | Result | Tail |
|---|---|---|
| `test_branch_scope.py` | **PASS** | `ALL BRANCH SCOPE / POSTING RESOLUTION TESTS PASSED` (36 checks incl. §6 fail-open assertion) |
| `test_checkpoint_roles_audit.py` | **PASS** | `ALL CHECKPOINT ROLE / RECORD AUDIT TESTS PASSED` |
| `test_dynamic_branches.py` | **PASS** | `ALL DYNAMIC BRANCH TESTS PASSED` |
| `test_field_level_rbac.py` | **PASS** | checks 2-7 ok (field-level 403, print lock, photo attachment) |
| `test_linked_records.py` | **PASS** | `Ran 3 tests … OK` |
| `test_officer_profile_locations.py` | **PASS** | `ALL OFFICER PROFILE / LOCATION / AUDIT TESTS PASSED` |
| `test_print_fit.py` | **PASS** | `ALL PRINT TEMPLATE TESTS PASSED` (static A4 geometry) |
| `test_read_only_rbac.py` | **PASS** | `179 checks passed, 0 failed` |
| `test_review_gate.py` | **PASS** | `ALL REVIEW-GATE TESTS PASSED` (6 scenarios incl. restart) |
| `test_station_actions.py` | **PASS** | `165 checks passed, 0 failed` |
| `test_server.py` | **FAIL** | `RuntimeError: server did not start` — the suite is SQLite-era (`sqlite3`, `SENTINEL_DB`), and the backend now requires PostgreSQL |

**Node/jsdom — 11 of 12 passed**

| Suite | Result |
|---|---|
| `test_approval_flow.mjs` | **PASS** (`ALL APPROVAL-FRONTEND TESTS PASSED`) |
| `test_clearance_rbac_ui.mjs` | **PASS** |
| `test_conduct_frontend.mjs` | **FAIL** — `Error: timed out waiting for: backend health`; the harness spawns `server.py` with `SENTINEL_DB=<sqlite path>` (retired setting) |
| `test_form_improvements.mjs` | **PASS** |
| `test_frontend_session.mjs` | **PASS** (13 scenario groups) |
| `test_officer_profile_ui.mjs` | **PASS** |
| `test_record_audit_ui.mjs` | **PASS** |
| `test_reverse_sequence_ui.mjs` | **PASS** |
| `test_shell_workflow_integration.mjs` | **PASS** |
| `test_sidebar_navigation.mjs` | **PASS** |
| `test_station_frontend.mjs` | **PASS** |
| `test_station_integration.mjs` | **PASS** |

**Also run:** `python3 backend/server.py --ui-check` → **exit 0**, served template `index.html` matches build `sentinel-sidebar-scope-1-b4d29a71`, checkout `arena/8834f56d… @ 381545c`, `Actions column: yes`.

**Totals: 21 of 23 suites pass.** Both failures are **obsolete harnesses**, not application regressions — but they matter for a different reason (see 8.4).

### 8.3 Additional verification performed by this audit (not part of the project's suite)

A disposable PostgreSQL cluster + `backend/server.py` on port 8123, nine seeded demo accounts, and ~80 synthetic requests:

1. **RBAC read matrix** — 7 roles × 12 endpoints (§5.3). Matches design; `chief` 403 on writes.
2. **RBAC write matrix** — 7 roles × 9 endpoints. Matches design.
3. **Anonymous access** — `/api/me`, `/api/persons`, `/api/admin/users`, `/api/checkpoint-events`, `/api/clearance-applications` → 401; `/api/health` → 200; `/uploads/<file>` → **200** (C-1).
4. **Session lifecycle** — cookie flags; 20 sessions with no expiry; token survives restart; token survives admin password reset; token revived by reactivation.
5. **Authentication abuse** — 15 failed logins, no throttling; zero authentication audit rows.
6. **Privilege changes** — non-admin user-management attempts blocked; admin self-demotion → lockout.
7. **Branch isolation** — cross-branch read 403 (correct) vs cross-branch approve/signed-document/documents 200-201 (H-2); unresolved posting → fail-open (the fail-open half of H-2, see §5.5).
8. **Checkpoint scope** — blank `location_scope` → all locations (M-2).
9. **Review gate** — fresh app 400; backdated app approved; `Citizenship` self-approval (M-3).
10. **Concurrency** — 12 parallel case creations → 8×201 + 4×409 (H-6).
11. **Error handling** — malformed JSON → 500 with Python internals; 409 with driver text; 404 echoing input (M-4).
12. **Uploads and retrieval** — synthetic photo + 4 documents per application; anonymous 200 on all retrievable paths (C-1).

### 8.4 Coverage assessment against the security requirements

| Requirement | Covered? | Comment |
|---|---|---|
| Authentication | **Partially** | Login success/failure paths are exercised; **no test for throttling, expiry, revocation, password reset, or authentication auditing** — precisely the areas that failed this audit |
| Authorization (role/module) | **Well covered** | `test_read_only_rbac.py` (179 checks) and the GET/POST matrices are genuinely strong |
| User management | **Partially** | Create/edit/deny covered; **no test for self-demotion, last-admin, duplicate case-insensitive usernames, or session invalidation after reset** |
| Branch isolation | **Partially** | `test_branch_scope.py` is thorough for registers and per-record history — and **does not touch `/approve`, `/signed-document`, `/documents` or `/persons/<id>`**, the four routes that leak. §6 of that suite asserts the fail-open behaviour as correct |
| Document protection | **Not covered** | No suite requests an upload URL anonymously or cross-branch |
| Database integrity | **Partially** | Unique/dup behaviour implied by 409s; **no concurrency test, no transaction/rollback test, no migration idempotency test on a populated database** |
| Critical workflows | **Well covered for the UI** | Approval, print lock, station edit, sidebar, record audit, print geometry all have real integration tests |

### 8.5 Tests that pass without verifying the security requirement

- `test_sidebar_navigation.mjs` §"the directory is restricted to the admin / cross-command roles" and `test_frontend_session.mjs` §12/13 assert **client-side** behaviour. They prove the UI hides controls; they cannot prove the server refuses. (The server *does* refuse — but that is proven elsewhere, in `test_read_only_rbac.py`, not here.)
- The Commander read-only checks partly key off `filter_visibility()`/`user_view()` flags (presentation) as well as the 403 firewall (enforcement). Both are tested; be deliberate about which one a future test is asserting.
- `test_review_gate.py` §6 proves the gate survives a restart, but no test proves the gate cannot be bypassed by `purpose=Citizenship` or by self-approval (M-3).
- `test_branch_scope.py` §6 asserts an unresolved posting is not narrowed — i.e. it **locks in** the fail-open default rather than flagging it.

### 8.6 Obsolete tests

`backend/test_server.py` (3,035 lines) and `backend/test_conduct_frontend.mjs` (448 lines) target SQLite storage that no longer exists. They fail, they are excluded from `TESTING.md`'s documented list, and `test_server.py` still spawns a server inheriting the process environment — meaning that if a developer has `SENTINEL_DB_*`/`SENTINEL_DATABASE_URL` exported, the harness is wired to reach that database. **Recommended action:** delete or rewrite both; in the meantime, do not run them on a machine with database credentials in the environment.

---

## 9. Comparison with the previous deployment audit

**Locating the previous audit:** `DEPLOYMENT_AUDIT.md` is **not present** in the working tree, in `git log --all`, or in any branch. The branch has a single commit, so there is no history to recover it from. The comparison below is therefore made against (a) the twelve prior findings enumerated in the audit request and (b) `README.md:766-806` ("development only, not for operational police data"), which restates the same list. **Claims about what the previous report said beyond those twelve items are not made.**

| # | Previous finding | Status | Evidence |
|---|---|---|---|
| 1 | Identity documents accessible without authentication | **Still present** | `GET /uploads/<synthetic jpg>` and `<pdf>` → **200** with no cookie/token (C-1) |
| 2 | Default accounts / default passwords on a fresh install | **Still present** | 9 seeded accounts, all `ChangeMe123!`, all logged in successfully (C-2) |
| 3 | Unsalted SHA-256 password hashing | **Still present** | Stored hash equals published `sha256("abcdef")`; `password_hash()` is a bare hex digest (C-3) |
| 4 | Missing HTTPS / insecure session-cookie configuration | **Partially fixed** | `HttpOnly` and `SameSite=Lax` are now set (improvement); still **no `Secure`**, no `Max-Age`, no TLS, no HSTS; token also written to `localStorage`, negating `HttpOnly` (H-8) |
| 5 | Sessions without appropriate expiration or revocation | **Partially fixed** | Sessions are now DB-backed and survive restarts (new, and a prerequisite for rolling deploys); logout revokes; password change revokes *other* sessions. **Still no expiry**, and **no revocation** on admin password reset or on role change, with **reactivation reviving old tokens** (H-3) |
| 6 | Inadequate server-side authorization | **Partially fixed** | Module gates, the read-only firewall, branch scoping on registers and per-record history, and per-record branch enforcement on case/application **reads** are real and tested. **Still open** on `/approve`, `/signed-document`, `/persons/<id>/documents`, `/persons/<id>` aggregates, and the fail-open unresolvable-posting path (H-2, M-1) |
| 7 | Registration-number race conditions and concurrent-write failures | **Still present** | 4 of 12 concurrent writes failed with 409; `COUNT(*)+8`, ms-timestamp ids and scan-max ids throughout. UNIQUE constraints now prevent *duplicates* (an improvement) but not failures (H-6) |
| 8 | Missing or insufficient audit logging | **Partially fixed** | `audit_events` now records domain writes, per-record history, badge attribution and user-edit field lists. **Still missing**: all authentication/session events, IP/user agent/session id, before/after values, immutability, retention (H-7) |
| 9 | Exposed secrets, sensitive information in logs, unsafe error responses | **Partially fixed** | No secrets in the tree; `.env` is git-ignored; the DB URL is never printed; startup failures are credential-safe. **Still open**: `500 {error: str(e)}`, `409 {details: driver text}`, `/api/health` disclosure, search terms in stdout logs, no server-side exception logging (M-4, L-3) |
| 10 | Unsafe upload handling / file-path handling / publicly accessible stored documents | **Partially fixed** | Filenames are regenerated, path traversal is blocked (`basename`), extensions are allow-listed on officer/vehicle/conduct paths. **Still open**: anonymous retrieval, no validation or size cap on clearance documents, no content sniffing, local unencrypted storage, no scan/retention (C-1, M-7) |
| 11 | Unrestricted database access, insecure configuration, vulnerable dependencies | **Still present / unverified** | App connects as `postgres` superuser, empty-password default, no `sslmode`, no pool, no manifests to pin or audit. Dependency CVE status **unverified** (no manifests, scanning out of scope) (M-8) |
| 12 | Any new risks from the user/role/permission upgrades | **New findings** | Last-admin self-demotion lockout (**verified**); password reset does not revoke sessions (**verified**); case-sensitive usernames (**verified**); free-text branch → fail-open scope (**verified**); cross-branch approve/signed-scan (**verified**); self-approval and `Citizenship` bypass (**verified**); checkpoint scope widening (**verified**); 401-for-403 logout behaviour; dead code in `rbac_self_test()` |

**Summary:** **0** findings *fixed and verified* in full; **6 partially fixed** (#4, #5, #6, #8, #9, #10); **5 still present** (#1, #2, #3, #7, #11); **1 category of new risk** (#12); **0 regressed** (nothing that previously worked is now broken); **1 unverified** (dependency vulnerabilities, inside #11).

**Credit where it is due:** items #4, #5, #6, #8 and #10 all moved materially in the right direction, and two of them (#5 persistence, #6 module/read firewall) are now better than "typical" for a system at this stage. The problem is that each improvement landed on the *routes under test* and stopped there, so the audit's job is to point at the four routes and one column that were missed.

---

## 10. Prioritized action plan

> **Revision note (v2 — audit only).** This section was rewritten to add objective, testable acceptance criteria, verification methods and remediation tracking. **No finding in §6 was changed, re-worded, downgraded or removed**, and no evidence in §1–§9 or the appendices was altered. Every remediation item below cites the finding it addresses. Nothing in this section has been implemented.

### 10.0 How to read this section

**Structure.** Every remediation item (B1–B13, M-a–M-j) carries the same eight fields so it can be reviewed, estimated and closed without ambiguity:

| Field | Meaning |
|---|---|
| **Behaviour that must change** | The externally observable behaviour after the fix, stated as an outcome, not a task list |
| **Risk addressed** | The §6 finding ID(s) and the concrete harm the item removes |
| **Acceptance criteria** | Numbered, binary, independently checkable conditions (`AC-<item>.<n>`) |
| **Required tests** | Named automated tests that must exist and pass; negative cases are mandatory where applicable |
| **PASS evidence** | The artefacts an approver must see in the release packet |
| **Dependencies** | Other items, decisions, or prerequisites that must land first |
| **Migration risk** | What could break existing data or a running deployment, and how it is mitigated |
| **Rollback** | How to undo safely, and what cannot be undone |

**Definition of PASS (applies to every item).** An item may be marked PASS only when **all** of the following hold:

1. Every acceptance criterion is demonstrated by an automated test that is committed to the repository and green on a throwaway PostgreSQL cluster (`pgserver`, per `TESTING.md`), **or** by a named manual procedure where the item is explicitly marked *manual* (several M items concern deployment and backup, which cannot be fully automated).
2. The named negative tests in §10.6 that reference the item are green. A fix proven only by the happy path is not PASS.
3. The PASS evidence listed for the item is attached to the release packet.
4. No other finding regressed: the full suite (§8.2) plus the new suites is green in one run.
5. **Code review alone can never produce PASS.** The audit reproduced every Critical and High finding by executing requests against a running system; the fixes must be held to the same standard.

**Test conventions used below.** Proposed new suites are named `backend/test_<topic>.py` (standard-library `urllib` against a booted server with a throwaway cluster) or `backend/test_<topic>.mjs` (jsdom / Node VM), matching the existing conventions. Where an existing suite is the right home, the item says "extend". Tests that write data must use synthetic identities only, as the current suites already do.

**Evidence classes.** `[V]` = verified by execution during this audit · `[C]` = code-review observation, not executed · `[A]` = assumption · `[D]` = decision required from the project owner. The full register is §10.8.

**Sequencing.** §10.5 preserves the original recommended order of work. One sequencing note was added (not a reordering) documenting an additive-only constraint for B5 and B6.

---

### 10.1 Critical blockers — must close before any real data enters the system

| # | Action | Finding | Release gate |
|---|---|---|---|
| B1 | Authenticated document delivery; remove public `/uploads/` | C-1 | Before any real document is uploaded |
| B2 | Remove default credentials from the default startup path | C-2 | Before the first non-development start |
| B3 | Argon2id password storage with transparent rehash | C-3 | Before any real password is stored |
| B4 | Branch scope on approve / signed-scan / document routes | H-2 | Before any branch files its second clearance application |

#### B1 — Authenticated, scoped, audited document delivery

| Field | Requirement |
|---|---|
| **Behaviour that must change** | `serve_static()` must no longer resolve `/uploads/…` at all. Documents are fetched only through `GET /api/documents/<opaque-token>`, which authenticates the caller, resolves the token server-side to the owning record, applies that record's module and branch scope, writes an audit row, and returns the bytes with `Content-Disposition: attachment`. Stored files move out of the served directory. |
| **Risk addressed** | **C-1 `[V]`** — an anonymous `GET` returned `200 image/jpeg` for a synthetic applicant photograph and `200 application/pdf` for a synthetic birth certificate. Permanent, unrevokable disclosure of national IDs, passports, photographs, guarantor documents and signed clearance scans from a URL that appears in logs, screenshots and audit rows. |
| **Acceptance criteria** | **AC-B1.1** Anonymous `GET /uploads/<any existing stored filename>` → `404`, never `200`. **AC-B1.2** Anonymous `GET /api/documents/<any token>` → `401`. **AC-B1.3** Authenticated officer scoped to branch A requesting a document whose owning record is branch B → `403`, response body contains no file bytes. **AC-B1.4** Authenticated officer whose modules do not include the owning register (e.g. Checkpoint officer → clearance document) → `403` or `404`, never `200`. **AC-B1.5** Each successful document read inserts **exactly one** `audit_events` row (verified by count before/after). **AC-B1.6** Response carries `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`. **AC-B1.7** Traversal attempts (`../`, `%2e%2e%2f`, absolute paths, null bytes) → `400`/`404`, never file content. **AC-B1.8** The stored filename is **not** a valid token: requesting `/api/documents/f_<hex>` for a real file → `404`. |
| **Required tests** | New `backend/test_document_access.py`: upload synthetic JPEG + PDF through clearance intake, then assert AC-B1.1–B1.8, plus **NT-01, NT-02, NT-03, NT-04** (§10.6). Existing `test_clearance_rbac_ui.mjs` and `test_form_improvements.mjs` must be updated for the new URL shape and stay green. |
| **PASS evidence** | Suite output `N checks passed, 0 failed`; `grep -n "uploads" backend/server.py` shows no static handler; a redacted `curl` transcript proving `401`/`403`/`404` on the three negative paths; one audit row excerpt for a successful read. |
| **Dependencies** | D-7 (storage backend). Coordinates with **M-e** (same validated-upload helper) and **B4/B5** (same scope helper). **B10** enriches the audit row with IP/agent later — not blocking, since `audit()` already writes. |
| **Migration risk** | Document paths are stored as text in several columns (`persons.photo_path`, `clearance_applications.applicant_docs`/`guardian_docs`/`applicant_photo`, `clearance_signed_documents.file_path`, `case_evidence.file_path`, `checkpoint_events.traveler_docs`/`guardian_docs`). Token↔path resolution can be derived at read time, so **no schema change and no data rewrite is required**. If a `documents` table is preferred, it is additive. Moving files on disk is a one-time copy; keep the old directory read-only until verified, then delete out-of-band (not in the release). |
| **Rollback** | Revert the route and restore the previous `serve_static` branch. **Warning:** doing so re-exposes every document. Therefore rollback of B1 must be paired with a proxy/firewall block on `/uploads/` (documented manual step in the rollback runbook), and the file move must not be reversed. |

#### B2 — No working credentials on a fresh install

| Field | Requirement |
|---|---|
| **Behaviour that must change** | `init_db()` must not create nine accounts with a known password. On an empty database it creates exactly one bootstrap administrator with a cryptographically random password, printed **once** to stdout, flagged `must_change_password`; that account can reach only `/api/me`, `/api/me/password` and `/api/logout` until the password is changed. Demo accounts exist only behind an explicit flag (`SENTINEL_DEMO_SEED=1`) and are marked as demo accounts. Startup refuses to serve when a known default hash is present in a production-mode environment. |
| **Risk addressed** | **C-2 `[V]`** — nine seeded accounts (`admin`, `fp.officer`, `ap.officer`, `cid.officer`, `hr.officer`, `cp.south`, `cp.east`, `cp.west`, `chief`) all authenticated with `ChangeMe123!`, which is published in `README.md:563-586`. A deployed instance is fully compromised at first boot by anyone who can read the repository. |
| **Acceptance criteria** | **AC-B2.1** Fresh database, default environment: `SELECT COUNT(*) FROM users` = 1; the account is the bootstrap administrator; its password is ≥ 20 random characters printed on exactly one line of startup output and stored in no file. **AC-B2.2** That password authenticates; `/api/me` reports `must_change_password: true`; every other route returns `403 code: password_change_required` until the password is changed; `POST /api/me/password` works and clears the flag. **AC-B2.3** Restarting the server does not re-print the password and does not create a second administrator. **AC-B2.4** On the fresh database, none of the nine legacy usernames can authenticate with `ChangeMe123!`. **AC-B2.5** With `SENTINEL_DEMO_SEED=1`, the nine demo accounts exist, are flagged `demo = true`, and `/api/health` reports the demo state. **AC-B2.6** In production mode (D-4), startup exits non-zero with a clear message if any `demo = true` account exists or any hash equals a known default. |
| **Required tests** | New `backend/test_bootstrap_admin.py`: fresh cluster → capture stdout, assert single print, assert bootstrap login, assert gated routes for AC-B2.2, restart for AC-B2.3, legacy credentials for AC-B2.4, demo flag for AC-B2.5, refusal for AC-B2.6 (**NT-05**). |
| **PASS evidence** | Suite green; redacted startup transcript showing exactly one password line; `SELECT username, must_change_password, demo FROM users` output; screenshot/log of the production-mode refusal. |
| **Dependencies** | D-2 (bootstrap account model/name), D-4 (environment-mode flag), D-5 (what to do with already-seeded demo accounts). Must land **before or with B3** so the bootstrap password satisfies the new policy. |
| **Migration risk** | Adds `must_change_password` and `demo` columns (additive, nullable). Bootstrap runs only when `users` is empty, so an existing deployment is untouched. **Removing the seed block does not delete already-seeded accounts** — that is an explicit, separately approved data action (D-5); this item must not delete users silently. |
| **Rollback** | Revert the code path. New columns remain and are ignored by older code. No account is deleted by the rollback. |

#### B3 — Password storage that resists offline attack

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Passwords are stored with Argon2id (per-user salt, configured work factor). Login verifies Argon2id and, on a successful login against a legacy SHA-256 row, transparently rehashes and updates that row. A documented password policy is enforced on set/change. |
| **Risk addressed** | **C-3 `[V]`** — the stored hash for `admin` was byte-identical to the published `sha256("abcdef")`. Any database disclosure (backup, dump, injection, stolen disk) yields near-instant recovery of most operational passwords, and identical passwords are identifiable by hash equality. |
| **Acceptance criteria** | **AC-B3.1** After the change, no `users.password_hash` value matches the bare-hex-SHA-256 pattern `^[0-9a-f]{64}$` (measured by SQL, reported as a count). **AC-B3.2** A legacy row logs in successfully once and its stored value becomes `$argon2id$…` (before/after SQL). **AC-B3.3** Setting a password to `abcdef`-style input through `/api/me/password` stores Argon2id; the known hash `9a4aabf0…` never appears again. **AC-B3.4** Argon2 parameters are read from configuration and are ≥ the approved baseline (D-3). **AC-B3.5** Wrong password → `401`, and the stored hash is unchanged. **AC-B3.6** Policy violations (< min length, common-password list, reuse of current) → `400` with a specific message; the existing 6-character acceptance is gone. |
| **Required tests** | New `backend/test_password_storage.py`: hash-format sweep, legacy-upgrade flow, wrong-password non-mutation, policy cases, parameter assertion. Existing login-dependent suites must run unchanged (they use seeded credentials on throwaway clusters). |
| **PASS evidence** | Suite green; SQL output of hash **prefixes only** (first 10 characters; never full hashes, and only for synthetic accounts); a documented work-factor/timing measurement. |
| **Dependencies** | D-3 (min length, work factor, rotation), D-5 (dormant accounts). Blocks nothing, but the bootstrap password in B2 must satisfy the policy. |
| **Migration risk** | Lazy rehash means a dormant account keeps its weak hash until its next login. Mitigation: report the count of un-upgraded rows to `/api/health` and force a reset deadline for dormant accounts (D-5). Keep dual-verify (legacy accepted for verification only) for one release so a rollback cannot lock users out. |
| **Rollback** | Revert to dual-verify then legacy verify. **Never write SHA-256 again once B3 ships**, including on rollback — the rehash is one-way and the old rows are already gone; rolling back must not recreate them. |

#### B4 — Branch scope on the approval, signed-scan and document routes

| Field | Requirement |
|---|---|
| **Behaviour that must change** | `POST /api/clearance-applications/<id>/approve`, `POST …/signed-document`, the document manifest (`GET /api/persons/<id>/documents`), the per-record audit history and the printable pages must all apply `require_record_branch_scope()` against the record's own `branch_id`, exactly as the read route already does. `person_document_records()` must filter fingerprint documents by branch. |
| **Risk addressed** | **H-2 `[V]`** — an officer posted to Erigavo attached a signed scan to a Lasanod application (`201`), then approved it and received certificate `CL-29158847`, while the same officer was correctly refused (`403`) when reading that same application seconds earlier. Cross-branch authority to change and certify a record, plus misleading audit attribution. |
| **Acceptance criteria** | **AC-B4.1** Branch-B officer `POST /approve` on a branch-A application → `403 code: branch_scope_forbidden`, and the row's `status`/`certificate_number` are **unchanged** (asserted by SQL, not just the response). **AC-B4.2** Same for `POST /signed-document` → `403`, and `clearance_signed_documents` gains **no** row for that application. **AC-B4.3** `GET /api/persons/<id>/documents` as a branch-B officer lists **zero** documents sourced from branch-A records, and `total_count` equals the filtered list length. **AC-B4.4** The branch-A officer performs the same three calls → `200`/`201` (positive control). **AC-B4.5** Administrator and Commander keep their current behaviour (administrator `200`; Commander `403 read_only_role` on writes). **AC-B4.6** A legacy application with `branch_id IS NULL` → scoped officer gets `403` (unknown must never mean "everything"); administrator is permitted. |
| **Required tests** | New `backend/test_clearance_branch_scope.py` (or §7 of `test_branch_scope.py`) reproducing the exact audit sequence — Erigavo officer, Lasanod application, scan then approve — as a **permanent regression test**, plus AC-B4.4–B4.6 and **NT-06, NT-07, NT-08**. |
| **PASS evidence** | Suite green; the pre-fix commit fails the same test (proves the test is meaningful — see M-j); SQL excerpt showing the application row unchanged after the refused approval. |
| **Dependencies** | None to start (independent of B1–B3). Shares the scope helper with **B5**; B4 must land first so B5 has one helper to harden. |
| **Migration risk** | None — no schema change, no data rewrite. Existing cross-branch approvals already in the database are **not** undone; a report listing them is produced for the owner's decision (see §12 item 6). |
| **Rollback** | Revert the added scope calls. This re-opens the cross-branch write path, so rollback is permitted only during a maintenance window with the API closed to non-administrators. |

---

### 10.2 High priority — before a controlled pilot

| # | Action | Finding | Acceptance criteria |
|---|---|---|---|
| B5 | Make branch scoping **fail closed**; replace free-text authorization input with a branch reference | H-2, M-2 | AC-B5.1–B5.7 |
| B6 | Session expiry, idle timeout and revocation | H-3 | AC-B6.1–B6.9 |
| B7 | Login throttling, lockout and authentication audit | H-4 | AC-B7.1–B7.7 |
| B8 | Last-administrator protection and break-glass recovery | H-5 | AC-B8.1–B8.6 |
| B9 | Transactional identifier generation | H-6 | AC-B9.1–B9.6 |
| B10 | Complete and make the audit trail append-only | H-7 | AC-B10.1–B10.6 |
| B11 | TLS, secure cookie, single transport, security headers, CORS | H-8, M-5 | AC-B11.1–B11.7 |
| B12 | Separation of duties on approval; constrain the Citizenship exemption | M-3 | AC-B12.1–B12.5 |
| B13 | Correct 401/403 contract and client sign-out behaviour | M-9 | AC-B13.1–B13.6 |

#### B5 — Fail-closed branch scoping

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Authorization must stop depending on the free-text `users.branch` label. Users gain a nullable `branch_id` reference (label retained for display) and an explicit `branch_unrestricted` boolean that only an administrator can grant, with a mandatory reason. An officer whose branch is unresolved is **denied**: reads return an empty set, writes are refused. `location_scope` becomes mandatory for checkpoint roles on update as well as create. |
| **Risk addressed** | **H-2** (fail-open half) and **M-2 `[V]`** — setting an officer's branch to an unregistered label produced `branch_scope: null`, `resolved: false` and exposed **3 of 3** clearance applications instead of their branch's subset; clearing `location_scope` changed a checkpoint officer's `visible_locations` from `['South']` to `['South','East','West']`. A typo in User Management silently removes isolation for that account. |
| **Acceptance criteria** | **AC-B5.1** `branch_id IS NULL` and `branch_unrestricted = false`: `GET /api/clearance-applications` returns `items: []`, `branch_scope_status.resolved: false`, and the response is **not** the national list. **AC-B5.2** The same officer's create/approve/attach requests → `403 code: branch_scope_unresolved`. **AC-B5.3** Changing the `branch` **label** to an unregistered string no longer changes authorization at all (re-running the exact M-2/H-2 probe yields denial, not widening). **AC-B5.4** Administrator grants `branch_unrestricted = true` with a reason → national scope, and one audit row records actor, target and reason; a missing reason → `400`. **AC-B5.5** `PATCH /api/admin/users/<id> {"location_scope": ""}` on a checkpoint role → `400`, stored value unchanged. **AC-B5.6** Backfill maps existing labels to `branch_id` only where the existing resolver matched at ≥ `POSTING_MATCH_MIN`; unmapped rows are written to a report and remain denied until an administrator assigns. **AC-B5.7** No officer can change their own `branch`, `branch_id`, `location_scope` or `branch_unrestricted` through `/api/me`. |
| **Required tests** | New `backend/test_branch_fail_closed.py` covering AC-B5.1–B5.7 and **NT-09, NT-10, NT-11, NT-12**. **`test_branch_scope.py` §6 must be inverted** — it currently asserts that an unresolved posting is "never silently narrowed"; the new expectation is denial. That deliberate expectation change must be recorded in the test docstring with the reason (this audit's §5.5/§6 H-2). |
| **PASS evidence** | Suite green; the inverted §6 assertion documented; a backfill dry-run report on production-shaped synthetic data showing mapped/unmapped counts; an audit row excerpt for AC-B5.4. |
| **Dependencies** | **B4** (one scope helper to harden), **M-a** strongly recommended before the backfill, **D-6** (may any role be national-scope, and who may grant it). |
| **Migration risk** | **The highest migration risk in this plan.** Adds a FK column plus a backfill on live user rows; ambiguous or mis-spelled labels can be mis-assigned. Mitigations: additive columns only; no assignment below the confidence threshold; `branch_unrestricted` defaults **false**, so the worst failure mode is over-denial (safe), never over-exposure; the dry-run report is reviewed before the real run; the old `branch` column is retained untouched. |
| **Rollback** | Code revert restores the previous behaviour because `users.branch` is untouched by this item. `branch_unrestricted` also acts as a per-account kill switch for urgent recovery. The backfill fills only a new column, so it never destroys information. |

#### B6 — Session expiry, idle timeout and revocation

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Sessions gain an absolute lifetime, an idle timeout, revocation metadata and attribution. A token is accepted only while it is unexpired, unrevoked and within the idle window. Password change, password **reset**, deactivation and explicit logout revoke the affected sessions immediately. Reactivation does not revive them. Administrators can list active sessions and force revocation. |
| **Risk addressed** | **H-3 `[V]`** — `sessions` has no expiry column; a token survived a full server restart, survived an administrator password reset (old token `200` while the old password correctly returned `401`), and a token issued before deactivation was accepted again after reactivation. A stolen token is permanent, and password rotation — the standard incident response — does not evict the attacker. |
| **Acceptance criteria** | **AC-B6.1** `sessions` carries `expires_at`, `idle_expires_at`, `revoked_at`, `revoked_reason`, `ip`, `user_agent`. **AC-B6.2** A session past its absolute lifetime → `401 code: session_expired` (proved with a backdated row). **AC-B6.3** A session idle beyond the timeout → `401`; activity slides the idle clock (two calls within the window stay alive; a call after the window fails). **AC-B6.4** After an administrator resets a user's password, that user's existing token → `401` on the next request. **AC-B6.5** After a self-service password change, the caller's session survives and all their other sessions are revoked (existing good behaviour preserved). **AC-B6.6** Deactivation revokes sessions; **reactivation does not restore the old token** — the user must sign in again. **AC-B6.7** Role change does not require revocation because the role is re-read per request, and this is asserted explicitly (a role downgrade takes effect on the next request — already `[V]`). **AC-B6.8** `GET /api/admin/sessions` lists active sessions per user and is administrator-only (`403` for others); `POST /api/me/sessions/revoke-all` works. **AC-B6.9** An expired or revoked token is refused even when present in the in-process `TOKENS` cache. |
| **Required tests** | New `backend/test_session_lifecycle.py`: absolute expiry, idle expiry, reset-revokes, change-keeps-current, deactivate-then-reactivate (**NT-13**), admin listing and revocation, cache-poisoning case for AC-B6.9, plus the existing restart-persistence check (must stay green). |
| **PASS evidence** | Suite green; SQL excerpt of a revoked row with reason; a two-session transcript showing one survives and one does not after a password change; the restart-persistence test still passing. |
| **Dependencies** | **B13** (error codes so clients distinguish expiry from a permission failure), **M-a** (recommended for the schema change), **D-8** (lifetime policy, revise-on-role-change policy). |
| **Migration risk** | Additive columns; existing rows need a one-time `expires_at` derivation at migration time, which **logs everyone out once** unless the value is future-dated. Plan: set `expires_at = created_at + policy` and announce a one-time re-login; this is the only user-visible migration effect. Do not silently revive expired sessions during the backfill. |
| **Rollback** | Added columns are nullable and ignored by older code; reverting removes enforcement but does not invalidate anything. Revocation rows deleted by rollback would re-enable tokens — therefore the rollback runbook must state: "do not roll back B6 without first forcing a global `DELETE FROM sessions`". |

#### B7 — Login throttling, lockout and authentication audit

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Repeated failed authentication is rate-limited per account and per source, with a temporary lockout and an administrator unlock. Every authentication event (success, failure, logout, revocation) is written to `audit_events` with source attribution. No password or hash is ever written to the log. Lockout responses do not reveal whether an account exists. |
| **Risk addressed** | **H-4 `[V]`** — 15 consecutive wrong-password attempts returned `401` with no delay, no counter and no lockout, and the correct password then worked; **zero** authentication rows appeared in `audit_events` after 15 failures and 7 successes. Combined with C-2/C-3 this makes online guessing cheap and leaves no forensic trace. |
| **Acceptance criteria** | **AC-B7.1** After the configured threshold of failures for one username within the window → `429` with `Retry-After`; a **correct** password during the lockout is also refused (`429`). **AC-B7.2** Per-source limiting: failures spread across different usernames from one source trigger `429`. **AC-B7.3** Known and unknown usernames produce the same status and message, and the response time difference stays within a documented tolerance. **AC-B7.4** `LOGIN_SUCCESS`, `LOGIN_FAILED`, `LOGOUT` and `SESSION_REVOKED` rows appear in `audit_events` with actor (where known), `ip` and `user_agent`. **AC-B7.5** No audit row contains the submitted password, a hash, or a token (asserted by scanning the rows created during the test). **AC-B7.6** `POST /api/admin/users/<id>/unlock` clears a lockout, is audited, and is refused for non-administrators (`401`/`403`). **AC-B7.7** After the lockout window elapses, login succeeds with no administrator action. |
| **Required tests** | New `backend/test_auth_hardening.py` covering AC-B7.1–B7.7 and **NT-14, NT-15**. Must include the exact audit probe (15 failures) as a regression test. |
| **PASS evidence** | Suite green; audit row excerpts for one success, one failure and one unlock; a timing comparison for AC-B7.3; confirmation that no secret appears in any row. |
| **Dependencies** | **B2** (no published credentials to guess), **B10** for the enriched event columns (B7 owns the *events*, B10 owns the *enrichment and immutability* — documented because the recommended order runs B7 before B10), **D-9** (thresholds, lockout duration, unlock authority). |
| **Migration risk** | Counters must **not** live only in process memory: with two application colours, per-process counters halve the effective threshold. Use an additive `login_attempts` table (shared, prunable) or a shared cache. Prune policy required so the table cannot grow without bound. |
| **Rollback** | Revert enforcement; the table and the audit rows remain (correctly — audit rows must not be deleted by a rollback). |

#### B8 — Last-administrator protection and break-glass recovery

| Field | Requirement |
|---|---|
| **Behaviour that must change** | No administrative action may leave zero active administrators. Self-demotion requires an explicit confirmation. A documented out-of-band recovery path exists that requires only filesystem access to the host. |
| **Risk addressed** | **H-5 `[V]`** — the sole administrator demoted themselves (`200`); the immediate attempt to restore the role was refused (`401 Restricted to HR Directorate Officer`), producing permanent lockout that was only recoverable by direct SQL on the disposable audit cluster. On a fresh install there is exactly one administrator, so this is one click away. |
| **Acceptance criteria** | **AC-B8.1** Demoting the only active `SystemAdmin` → `409 code: last_admin_protected`, and the role is unchanged in the database. **AC-B8.2** Deactivating the only active administrator → `409`, `active` unchanged. **AC-B8.3** With two active administrators, demoting one succeeds (positive control). **AC-B8.4** Two concurrent requests demoting the two administrators: exactly one succeeds and the other receives `409`, leaving ≥ 1 active administrator (the negative concurrency case). **AC-B8.5** A documented recovery command (e.g. `python backend/server.py --create-admin`) restores administrative access using only local shell access, prints a one-time password, and writes an audit row. **AC-B8.6** Self-demotion without `{"confirm_self_demotion": true}` → `400` with an explicit message. |
| **Required tests** | New `backend/test_last_admin.py`: AC-B8.1–B8.6, including a two-thread race for AC-B8.4 (**NT-16**) and a simulated recovery run for AC-B8.5. |
| **PASS evidence** | Suite green (including the race, run ≥ 50 iterations without producing a zero-admin state); transcript of the recovery command; one audit row from the recovery. |
| **Dependencies** | None. The recovery tooling overlaps **M-a**/`tools/` conventions. |
| **Migration risk** | None — no schema or data change. The check must run **inside** the same transaction as the update with row locking, or AC-B8.4 cannot be satisfied. |
| **Rollback** | Guard removal is trivial and safe; no data was changed by the guard. |

#### B9 — Transactional identifier generation

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Human-facing identifiers are produced from PostgreSQL sequences inside the same statement/transaction that inserts the row, and the year segment is derived from the database date. A generated-identifier collision never surfaces as a user-facing `409`; it is retried server-side or made impossible. |
| **Risk addressed** | **H-6 `[V]`** — 12 concurrent case creations produced **8 × 201 and 4 × 409 `Database constraint failed`**; the case prefix is hard-coded `CID-2026-`; application and certificate numbers derive from the epoch-millisecond clock, which collides for parallel submissions. UNIQUE constraints prevent duplicates but not lost work. |
| **Acceptance criteria** | **AC-B9.1** 20 concurrent `POST /api/crime-cases` → **20 × 201, 0 × 409**, all identifiers distinct. **AC-B9.2** 20 concurrent clearance applications → 20 distinct `application_id`, `0 × 409`. **AC-B9.3** 10 concurrent creations each for officers, vehicles, badges and stations → no `409`, no duplicates. **AC-B9.4** The year segment equals the database's current year (asserted against `CURRENT_DATE`, not the Python clock). **AC-B9.5** Acceptance is uniqueness + monotonicity; **gaps are explicitly permitted** (a rolled-back transaction may consume a value) — stated so nobody over-specifies gaplessness. **AC-B9.6** Existing identifiers are unchanged and still resolve (no renumbering). |
| **Required tests** | New `backend/test_identifier_concurrency.py`: threaded batches per register reproducing the audit probe, plus AC-B9.4–B9.6 (**NT-17, NT-18**). |
| **PASS evidence** | Suite green across repeated runs (state the run count); before/after concurrency table showing `4/12 failures → 0/20`; `SELECT last_value FROM …` and a sample of new identifiers. |
| **Dependencies** | **M-a** (a clean, versioned place for the `CREATE SEQUENCE` statements), **D-10** (is the existing format contractual?). |
| **Migration risk** | Additive: create sequences and `setval` above the current maximum. **Do not renumber or rewrite existing rows** — printed certificates and audit rows already reference them. If any identifier format is contractual (D-10), the sequence value must continue the existing pattern rather than start at 1. |
| **Rollback** | Keep the previous generator behind a temporary flag for one release; sequences can be dropped without touching row data. |

#### B10 — Complete and append-only audit trail

| Field | Requirement |
|---|---|
| **Behaviour that must change** | The audit trail records authentication, session, read (including document access), approval and administrative changes with source attribution and before/after values, and cannot be altered or deleted by the application's own database role. |
| **Risk addressed** | **H-7 `[V]`/`[C]`** — no authentication or read events; no IP, user agent, session id or before/after values; `audit_events` is an ordinary table the application connection can `UPDATE`/`DELETE`. The log cannot answer "who saw, decided or changed what, from where" under challenge. |
| **Acceptance criteria** | **AC-B10.1** `audit_events` gains `ip`, `user_agent`, `session_id`, `before`, `after`, `request_id` (additive). **AC-B10.2** A role change records the previous and new role as structured values (asserted JSON), not only a column list. **AC-B10.3** The application's database role cannot `UPDATE` or `DELETE` rows in `audit_events` (attempt through the application DSN → error). **AC-B10.4** A trigger rejects `UPDATE`/`DELETE` even for the table owner. **AC-B10.5** Document reads (B1) and `location_scope` edits (M-2) both produce rows. **AC-B10.6** No audit row contains a password, token or document body (row scan asserted). |
| **Required tests** | New `backend/test_audit_integrity.py`: AC-B10.1–B10.6, plus **NT-19, NT-20**. |
| **PASS evidence** | Suite green; `\dp audit_events` output showing the grants; a failed `UPDATE` transcript; sample before/after JSON for one role change. |
| **Dependencies** | **B7** (owns the initial authentication events), **M-b** (role separation makes AC-B10.3 real). Recommended order runs B7 before B10 — documented here because the dependency is partial, not cyclic. |
| **Migration risk** | Adding columns is additive and safe. **Revoking `UPDATE`/`DELETE` is a one-way privilege change on a live database** and must be executed by the migration role, not the application role. Any existing tooling that "cleans up" audit rows will begin failing — that is intended, and must be inventoried first. |
| **Rollback** | Columns may remain. **Do not roll back the privilege revocation or the trigger**: restoring mutability of the audit log silently undermines every row written after the fix. If a rollback is unavoidable, it requires a signed exception. |

#### B11 — Transport security, secure cookie, single session transport, headers

| Field | Requirement |
|---|---|
| **Behaviour that must change** | All traffic is HTTPS via a reverse proxy with HSTS. The session cookie is `Secure`, `HttpOnly`, `SameSite=Lax` and `__Host-`-prefixed. The browser uses **one** transport: the cookie. The bearer token is no longer persisted in `localStorage`. Standard security headers are present and CORS is restricted to the application origin. |
| **Risk addressed** | **H-8 `[V]`, M-5 `[V]`** — plain HTTP; cookie without `Secure`; no HSTS; no CSP/`nosniff`/`frame-ancestors`/`Referrer-Policy`; `Access-Control-Allow-Origin: *`; and the same bearer token written to `localStorage`, which nullifies `HttpOnly`. Credentials and tokens cross the network in clear text and a single XSS becomes permanent takeover. |
| **Acceptance criteria** | **AC-B11.1** The application port is not reachable from branch networks directly; plain HTTP requests to the app port are refused or redirected `308` to HTTPS at the proxy. **AC-B11.2** HTTPS responses carry HSTS `max-age ≥ 31536000; includeSubDomains`. **AC-B11.3** The session cookie carries `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/` and the `__Host-` prefix, and has an explicit short lifetime. **AC-B11.4** After sign-in, `localStorage` contains **no** token (`sentinel_token`, `sentinel_user` and legacy `sentinel_session` are all absent); the SPA, `application.html` and `certificate.html` still work using the cookie. **AC-B11.5** A `Content-Security-Policy` is sent; either enforced without `unsafe-inline` (requires moving the inline script/style) or in report-only with a dated sunset recorded in the release packet (D-11). **AC-B11.6** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'` present; the `Server` banner is suppressed. **AC-B11.7** CORS is no longer `*`. |
| **Required tests** | New `backend/test_http_hardening.py` (header assertions, cookie attributes, CORS) + a jsdom assertion in `test_frontend_session.mjs` for AC-B11.4 + updated printable-page tests for cookie-based access. **NT-21, NT-22**. |
| **PASS evidence** | Suite green; `curl -I` transcripts for HTTPS and the proxy redirect; a browser devtools screenshot showing an empty `localStorage` and a `Secure` cookie; the CSP header and, if report-only, the signed sunset decision. |
| **Dependencies** | **D-1** (hosting/proxy), **D-11** (CSP scope). Must precede any pilot with non-developer users. Note the built-in coupling: `application.html` and `certificate.html` read the session from `localStorage` today and **must** be updated in the same change. |
| **Migration risk** | No data migration. Operational risk: a misconfigured proxy or CSP blocks the UI at cut-over — stage behind the staging environment first and keep a tested rollback of the proxy config. Removing `localStorage` persistence logs every user out once. |
| **Rollback** | Revert the proxy configuration and the cookie attribute change. **Never reintroduce the token into `localStorage`** as a "quick fix"; if the cookie path fails, fix forward or roll back the whole release. |

#### B12 — Separation of duties on approval

| Field | Requirement |
|---|---|
| **Behaviour that must change** | The account that created a clearance application cannot approve it. The 12-hour window is not bypassable through data the submitting officer controls. Administrator bypass remains, but is recorded with actor identity and reason. |
| **Risk addressed** | **M-3 `[V]`** — an officer filed a `Citizenship` application and approved **their own** application seconds later, receiving `CL-29199707` with `review_period_bypassed: true`. The headline integrity control on certificates is removable by the person it constrains. |
| **Acceptance criteria** | **AC-B12.1** `POST /approve` by the creating account → `403 code: approval_requires_independent_reviewer`; status unchanged. **AC-B12.2** `purpose = Citizenship` no longer bypasses the window unless `citizenship_verified` was set by an authorised role (or the exemption is removed — D-12). **AC-B12.3** Administrator bypass records the bypassing account, role and a reason; `review_period_bypassed: true` remains in the response. **AC-B12.4** Two different officers complete the same flow successfully (positive control). **AC-B12.5** The boot self-test still reports `8/8` and gains cases for self-approval and the Citizenship path. |
| **Required tests** | Extend `backend/test_review_gate.py` and `backend/test_approval_flow.mjs`; the audit's self-approval sequence becomes a permanent regression test (**NT-23**). |
| **PASS evidence** | Suite green; self-test output listing the new cases; SQL showing the row unchanged after the refused self-approval; an excerpt of the bypass audit row. |
| **Dependencies** | **D-12** (is independent approval mandatory; is the Citizenship exemption legal?). Blocks nothing else. |
| **Migration risk** | No schema change. **Existing rows where creator = approver already exist** — this item produces a report only and must not retro-invalidate issued certificates (that is a policy decision for the owner). |
| **Rollback** | Revert the guard; the recorded bypass reasons remain in the audit trail. |

#### B13 — Correct the 401/403 contract

| Field | Requirement |
|---|---|
| **Behaviour that must change** | `401` means "not authenticated" (missing, invalid, expired or revoked credential). `403` means "authenticated but not permitted", with a machine-readable `code`. The client signs a user out only on a genuine authentication failure, never on a permission denial. |
| **Risk addressed** | **M-9 `[V]`** — a legitimate HR officer calling a register they may not read receives `401`, which the SPA treats as "session ended", so a permission denial logs the officer out mid-task; monitoring cannot distinguish an attack from a misconfigured role. |
| **Acceptance criteria** | **AC-B13.1** Missing/invalid/expired/revoked credential → `401` with `code: unauthenticated` (or `session_expired`). **AC-B13.2** Authenticated-but-unauthorised → `403` with a specific code (`restricted_module`, `admin_only`, `branch_scope_forbidden`, `read_only_role`, `field_edit_forbidden`, `branch_scope_unresolved`). **AC-B13.3** Every route in the §5.3/§5.4 matrices returns the corrected status (the matrices become the fixture). **AC-B13.4** The SPA signs out only on `code: unauthenticated`/`session_expired`; a `403` renders an in-place refusal and preserves in-progress form state. **AC-B13.5** The Commander still receives `403 read_only_role` for writes and now receives `403` (not `401`) for out-of-scope reads. **AC-B13.6** No route returns `500` for an authorization outcome. |
| **Required tests** | Extend `backend/test_read_only_rbac.py` (its 179 checks already encode intents), update `backend/test_frontend_session.mjs` for AC-B13.4, and add `backend/test_status_contract.py` that walks the old matrices asserting the corrected codes (**NT-24**). |
| **PASS evidence** | Suite green; the two matrices reproduced with corrected status codes; a jsdom assertion that a `403` does not clear the stored session. |
| **Dependencies** | None. **B6** depends on this for expiry codes; **B4/B5** for `branch_scope_unresolved`. Land B13 early — it is small, and it makes every later negative test unambiguous. |
| **Migration risk** | None (no schema, no data). Compatibility risk: any external consumer keying on `401` for permission failures will change behaviour — inventory integrations first (none were found in the repository). |
| **Rollback** | Revert both server mapping and client handling together; reverting only one side reproduces the logout bug. |

---

### 10.3 Medium priority — before production

Each item below has a **verification method**, a **binary pass/fail condition**, and the five fields required for every item. None of these may be marked PASS by code review alone except where explicitly marked **manual**.

#### M-a — Versioned migrations with an advisory lock

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Schema changes ship as ordered, recorded migration files applied by a dedicated job, not as a side effect of the web process. The web process verifies the schema version and refuses to serve on mismatch. Port eviction is removed from the default startup path. |
| **Risk addressed** | **M-11 `[V]`/`[C]`** — unversioned boot-time DDL with no checksum, no ordering, no lock and no down path; two starting instances race; `terminate_listener()` SIGKILLs whatever owns the port (including the other colour of a blue-green pair). |
| **Verification method** | Create `migrations/0001…` applied by `tools/migrate.py`; run twice; start the app with a deliberately wrong expected version; start two migration jobs concurrently. |
| **Pass/fail** | **PASS** = `schema_migrations` lists applied versions in order with checksums; a second run is a no-op (exit 0, zero DDL); the app refuses to serve when `expected_version` ≠ applied (non-zero exit, clear message); two concurrent migration jobs serialise and both exit 0; `/api/health` reports the schema version. **FAIL** = any DDL still emitted by the web process at startup, any race observable, or app serving with a mismatched version. |
| **Required tests** | New `backend/test_migrations.py` (idempotency, version-mismatch refusal, two-process lock) + startup log assertions. **NT-25**. |
| **PASS evidence** | `SELECT * FROM schema_migrations`; logs of the double run; the refusal transcript; a runbook entry for the migration job. |
| **Dependencies** | Should precede **B5**, **B6**, **B9**, **M-b**, **M-g** to reduce their risk. Can proceed in parallel with B1–B4. |
| **Migration risk** | Low, but it **changes the release procedure** (migrations become a separate step) — every later release depends on this being understood by operators. |
| **Rollback** | Forward-only by design; a failed migration run aborts before committing and is retried. Reverting this item restores boot-time DDL and is permitted only before the first versioned schema change ships. |

#### M-b — Least-privilege database access, TLS and pooling

| Field | Requirement |
|---|---|
| **Behaviour that must change** | The application connects with a role holding only the DML it needs (no `DELETE`, no DDL, no rights on `audit_events` beyond `INSERT`/`SELECT`), over TLS with certificate verification, through a connection pool. Migrations use a separate role. Credentials are not stored in the repository. |
| **Risk addressed** | **M-8 `[C]`** — superuser connection, empty-password default, `SENTINEL_DB_PASSWORD=change-me`, no `sslmode`, no pool. One application compromise yields database ownership, including the ability to rewrite the audit log. |
| **Verification method** | Connect as the app role and attempt `DELETE`, `TRUNCATE`, DDL and an `UPDATE` on `audit_events`; inspect `pg_stat_activity` for `sslmode`; measure connection reuse under a small load run. |
| **Pass/fail** | **PASS** = every privilege attempt fails with a permissions error; the TLS state shows an encrypted connection with verification; the pool is bounded and reused (connection count stays flat under 50 sequential requests); no credential literal exists in the repository. **FAIL** = any privilege attempt succeeds, an unencrypted connection is accepted, or a secret appears in the tree. |
| **Required tests** | `backend/test_db_privileges.py` (manual-marked for the infra parts, automated for privilege assertions). |
| **PASS evidence** | Role DDL script, `\dp` output, TLS query output, pooled connection metrics, secret-scan result. |
| **Dependencies** | **M-a** (the migration role), **M-i** (restore must still work with the restricted role), **D-1** (hosting). |
| **Migration risk** | **Privilege revocation can break application paths that rely on `DELETE`/DDL at runtime** — inventory them first (the audit found none, but confirm). Roll out to staging before production. |
| **Rollback** | Re-grant the previous privileges (fast, but weakens security); keep the grant script under version control for both directions. |

#### M-c — Scope the person-detail aggregates

| Field | Requirement |
|---|---|
| **Behaviour that must change** | `GET /api/persons/<id>` returns only the record sections the caller's modules and branch permit, using the same filter as `/documents`, `/linked-records` and `/audit-history`. |
| **Risk addressed** | **M-1 `[V]`** — a Checkpoint officer received a person's Fingerprint clearance summary (and, for other people, airport and all-location checkpoint data). Cross-unit and cross-branch metadata disclosure. |
| **Verification method** | Fetch one synthetic person as each of the seven roles; assert the returned section keys against the role's module set and branch. |
| **Pass/fail** | **PASS** = for every role/person combination, no section appears whose module or branch the caller lacks; the response explicitly marks hidden sections rather than silently omitting them (the documented pattern); administrator and Commander still see everything. **FAIL** = any unauthorised section present. |
| **Required tests** | New `backend/test_person_scope.py` (7-role × section matrix) + update `test_linked_records.py` if expectations change. **NT-26**. |
| **PASS evidence** | The matrix output; one before/after response pair for the Checkpoint officer. |
| **Dependencies** | **B5** (scope helper), **B4** (precedent). |
| **Migration risk** | None. |
| **Rollback** | Revert the filter; no data changed. |

#### M-d — Safe error responses and health payload

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Unexpected exceptions return a generic `500` with a correlation id and are logged server-side with that id. Driver/constraint text is never returned. Echoed input is not reflected in errors. `/api/health` returns only `{status}` to unauthenticated callers; diagnostics move behind authentication or a separate admin/metrics surface. `/readyz` executes `SELECT 1` and checks the schema version. |
| **Risk addressed** | **M-4 `[V]`** (Python internals, constraint names and input echo in responses; unauthenticated disclosure of build/commit/path/database/pid) and **M-12 `[V]`** (health does not touch the database). |
| **Verification method** | Malformed JSON body, duplicate insert, unknown route, unknown identifier, database stopped; then `/api/health` and `/readyz` anonymously and authenticated. |
| **Pass/fail** | **PASS** = every error body matches `{error, incident}` with no `str(e)`, no constraint name and no echoed user input; the exception **is** logged with the same incident id; anonymous `/api/health` returns only `{status}`; `/readyz` returns `503` when the database is stopped and `200` when it is up with the expected schema version. **FAIL** = any internal string leaks, any exception unlogged, or `/readyz` returning `200` with the database down. |
| **Required tests** | New `backend/test_error_contract.py` + `backend/test_health_probes.py` (stop the disposable cluster, assert `503`). **NT-27**. |
| **PASS evidence** | Before/after response bodies; a log line matching its incident id; the `503`/`200` probe transcript. |
| **Dependencies** | **D-4** (environment mode for diagnostics), **M-a** (schema version for `/readyz`). |
| **Migration risk** | None. |
| **Rollback** | Revert; note that restoring the verbose error payload re-opens information disclosure. |

#### M-e — One validated upload path

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Every upload (clearance documents included) goes through one helper enforcing extension allow-list, magic-byte verification, size cap, and safe re-encode for images. Files are stored encrypted outside the web root, scanned, retention-limited, and orphaned files are reconciled. |
| **Risk addressed** | **M-7 `[V]`/`[C]`** — the clearance intake calls the unvalidated `save_upload()`, so arbitrary file types and unbounded sizes are accepted; files are written before the database insert, so a failed insert leaves a publicly retrievable orphan. |
| **Verification method** | Upload `.exe`, a 30 MB file, a `.jpg` whose bytes are not a JPEG, and a valid PDF; then force a database failure after the file write. |
| **Pass/fail** | **PASS** = every invalid upload is rejected `400` with a specific reason and **no file is written**; a valid file is accepted and readable only through the authenticated route; a failed insert leaves no file (or is removed by the reconciler, asserted by a run); oversized input is rejected before the body is fully buffered. **FAIL** = any invalid file stored, or an orphan remains after reconciliation. |
| **Required tests** | Extend `backend/test_document_access.py`; new `backend/test_upload_validation.py`. **NT-28**. |
| **PASS evidence** | Rejection transcript per bad input; storage listing before/after; reconciler run output. |
| **Dependencies** | **B1** (same route), **D-7** (storage). |
| **Migration risk** | Existing non-conforming files (if any) will no longer be served by the old path — inventory first, and do not delete anything during the release. |
| **Rollback** | Revert the helper; already-migrated storage stays valid. |

#### M-f — Case-insensitive unique usernames

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Usernames are unique case-insensitively and normalised on input. |
| **Risk addressed** | **M-6 `[V]`** — `Audit1baf` and `AUDIT1BAF` were both created (`201`), allowing confusable duplicate accounts and ambiguous audit attribution, while badge uniqueness is already case-insensitive. |
| **Verification method** | Create `X` then `x`; create `X` then `X ` with whitespace; check existing duplicates in a synthetic dataset. |
| **Pass/fail** | **PASS** = the second creation returns `409` with a clear message; a functional unique index on `LOWER(username)` exists; a pre-flight query reports any pre-existing case-duplicates for manual resolution. **FAIL** = any case-variant accepted. |
| **Required tests** | New `backend/test_username_uniqueness.py`. **NT-29**. |
| **PASS evidence** | Index definition; the `409` transcript; the pre-existing-duplicates report (expected empty). |
| **Dependencies** | **M-a** (index creation as a migration). |
| **Migration risk** | The index creation **fails** if duplicates already exist — hence the pre-flight report and a manual merge decision. Never auto-merge accounts. |
| **Rollback** | Drop the index; no data changed. |

#### M-g — Indexes and timestamp types

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Foreign keys and the branch/location filters used by every list query are indexed; new timestamp columns use `timestamptz`. |
| **Risk addressed** | **§7.1 `[C]`** — no FK indexes at all, so every branch-filtered list is a sequential scan; text timestamps require parsing and block range queries and retention jobs. |
| **Verification method** | `EXPLAIN (ANALYZE)` the branch-filtered list queries before and after on ≥ 100k synthetic rows. |
| **Pass/fail** | **PASS** = the benchmarked queries use index scans and meet a stated latency target at 100k rows; new timestamp columns are `timestamptz`; existing `TEXT` timestamps are explicitly deferred (documented) rather than half-converted. **FAIL** = any target query still sequential-scans, or a partial type conversion ships. |
| **Required tests** | `backend/test_query_plans.py` (seeds synthetic volume, asserts plan and latency). **Manual** for the deferred-conversion note. |
| **PASS evidence** | Before/after `EXPLAIN` output and timings; the schema diff. |
| **Dependencies** | **M-a**; **B5** for `branch_id`. |
| **Migration risk** | **Converting `TEXT` timestamps to `timestamptz` is a destructive rewrite** and is explicitly **out of scope here** — it belongs to its own expand/contract release with a dual-write period. Adding indexes takes locks: use `CREATE INDEX CONCURRENTLY` outside a transaction. |
| **Rollback** | Drop the added indexes; no data change. A timestamp conversion rollback is a restore — which is why it is deferred. |

#### M-h — Remove stale artifacts; pin dependencies; CI

| Field | Requirement |
|---|---|
| **Behaviour that must change** | The SQLite-era scripts and the two failing suites are removed or rewritten for PostgreSQL; the repository pins its dependencies and runs the full suite in CI on a throwaway cluster. |
| **Risk addressed** | **M-10 `[V]`** — `audit_instant_approvals.py --revert` and `migrate_rbac.py` operate on a SQLite file that holds no data (a clean report is meaningless); `database.py` declares a conflicting schema; no manifest exists, so builds are not reproducible and dependency vulnerabilities cannot be assessed. |
| **Verification method** | Clean-venv install from the manifest; full suite in CI; `grep` for `sqlite3` in the tree. |
| **Pass/fail** | **PASS** = `pip install -r requirements.txt` succeeds in a clean venv; the full suite (including the two rewritten suites) is green in CI; no `sqlite3` import remains; `pip-audit`/`npm audit` runs and its result is recorded. **FAIL** = any SQLite code path remains reachable, or any suite is silently excluded. |
| **Required tests** | The CI job itself is the test; `test_conduct_frontend.mjs` and `test_server.py` rewritten (not skipped). |
| **PASS evidence** | CI run link, manifest files, audit report, the git diff removing the artifacts. |
| **Dependencies** | None; safe to do first and cheap. |
| **Migration risk** | None (no application behaviour changes) — but **deleting `audit_instant_approvals.py` before B12 lands loses a forensic tool**; rewrite it for PostgreSQL rather than deleting it. |
| **Rollback** | Revert the commit; nothing in the running system changes. |

#### M-i — Backups, tested restore, monitoring, log hygiene

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Database and uploaded files are backed up on a schedule with verified restores; logs are structured, rotated, redacted and shipped; metrics and alerts cover availability, error rate, failed-login spikes and audit-write failures. |
| **Risk addressed** | **M-12 `[V]`/`[C]`**, **L-3 `[V]`** — no backup or restore exists, so a failed release cannot be undone and a disk loss is total; PII-bearing search terms are written to unrotated stdout; unhandled exceptions are never logged server-side. |
| **Verification method** | **Manual + rehearsed:** restore the latest backup into a clean environment, compare row counts and file checksums, and record the elapsed time; stop the database and confirm alerts fire. |
| **Pass/fail** | **PASS** = a dated, witnessed restore completes within the agreed RTO with matching row/file counts; backups are encrypted and off-site; alerting fires within the agreed window for database-down and failed-login-spike; logs are JSON with redacted query strings and retention configured. **FAIL** = no rehearsal recorded, any count mismatch, or no alert. |
| **Required tests** | Restore rehearsal is **manual** and produces a signed record; automated probe `backend/test_health_probes.py` covers the alarm path. |
| **PASS evidence** | Restore runbook + rehearsal record (date, operator, RTO achieved, verification counts); backup configuration; an alert screenshot. |
| **Dependencies** | **M-a**, **M-b** (restore must recreate grants), **D-1** (off-site location), RPO/RTO decision (§12 item 8). |
| **Migration risk** | None; however the first restore rehearsal must use a **synthetic** copy, never production, until the data-protection decision is settled. |
| **Rollback** | N/A — this item provides the rollback capability for everything else. |

#### M-j — Regression tests for every finding (the proof gate)

| Field | Requirement |
|---|---|
| **Behaviour that must change** | Each finding in §6 acquires a named automated test that **fails on the pre-fix commit and passes after the fix**, so the audit's evidence becomes a permanent guard rather than a one-off report. |
| **Risk addressed** | **§8.4/§8.5 `[V]`** — the suite is strong where it was aimed and silent where it was not: no test covered document anonymity, cross-branch approval, session reset, self-demotion or concurrency. Four routes leaked precisely because no test asserted them. |
| **Verification method** | For each item, check out the parent commit, run the new test (expect failure), then run it on the fix commit (expect pass). Record both. |
| **Pass/fail** | **PASS** = every Critical/High/Medium finding has a named test; each test fails on the parent commit (proving it detects the defect) and passes on the fix; the full suite is green in one CI run. **FAIL** = any finding without a test, or any test that passes on the pre-fix commit (a test that cannot detect the defect). |
| **Required tests** | The tests themselves, plus a machine-readable mapping table (finding → test → commit pair) checked into the repository. |
| **PASS evidence** | The mapping table; CI runs for both commits; a summary line per finding. |
| **Dependencies** | Runs alongside every item; the "fails before, passes after" check is the release gate for each. |
| **Migration risk** | None. |
| **Rollback** | N/A. |

---

### 10.4 Optional / future

*(Unchanged from the original plan. These items are not gated and carry no acceptance criteria, because they are not required for any of the readiness verdicts in §11.)*

- SSO/MFA (OIDC), account self-service recovery with verified channels.
- Certificate verification endpoint + QR code on the printed certificate; tamper-evident audit export for legal discovery.
- Purpose-of-search recording with mandatory justification for central person queries; search-result auditing.
- Append-only audit sink (WORM object storage) and legal retention automation.
- Read-replica reporting, pgbouncer, horizontal app scaling.

---

### 10.5 Suggested order of work (why this order)

*(Preserved verbatim from the original plan — the order is unchanged.)*

1. **B1-B3** — because each is a one-way door: documents already served cannot be un-leaked, and a compromised password file cannot be un-cracked. Do them before more data exists.
2. **B4-B5** — because branch isolation is the product's core promise and is currently both incomplete and fail-open. Do these before any pilot demonstrates the gap to a user.
3. **B11 + B6** — transport and session lifetime must be correct before users who are not developers ever sign in.
4. **B7-B8** — operational safety: you cannot run a pilot if you can lose your only administrator or cannot see who signed in.
5. **B9-B10** — data integrity and defensibility: sequences first (cheap), then the audit completion (needed before real decisions are recorded).
6. **M-* before production**, in the order given: migrations and database privilege first (they gate every future release), then backups/restore (the only thing that saves you when a release goes wrong), then the rest.

**Sequencing note (added in v2 — a constraint, not a reordering).** Two items in this order introduce schema changes ahead of **M-a**: **B5** (a branch reference plus backfill) and **B6** (session columns). To keep the recommended order intact, both must ship as **additive-only** DDL, hand-written in the existing idempotent style, with **no destructive statement** (no drop, rename, type change or constraint tightening) and no backfill below the documented confidence threshold. If the team instead wants a true backfill of historical rows in B5, **M-a must move ahead of B5**, because an unversioned backfill has no rollback path. That is the only condition under which the order above should change, and it requires your approval.

**Additional note on B13.** It is small and unblocks clean negative-test assertions for B4, B5 and B6, so it may be done first within step 1 without changing the substance of the order.

---

### 10.6 Negative test matrix (mandatory)

Every item's PASS depends on the negative cases that reference it. The audit reproduced each of these classes at least once; each row must become an automated test. "Synthetic only" applies to all rows.

| ID | Negative scenario | Request / method | Expected result | Items |
|---|---|---|---|---|
| NT-01 | Anonymous document retrieval (legacy URL) | `GET /uploads/<existing file>` | `404`, no bytes | B1 |
| NT-02 | Anonymous document retrieval (new route) | `GET /api/documents/<token>` | `401` | B1, B13 |
| NT-03 | Cross-branch document read | branch-B officer, branch-A document | `403`, no bytes | B1, B4 |
| NT-04 | Wrong-module document read | Checkpoint officer, clearance document | `403`/`404` | B1, M-c |
| NT-05 | Default credentials on a fresh install | `POST /api/login` with each legacy seed | `401` for all | B2 |
| NT-06 | Cross-branch approval | branch-B officer, branch-A application | `403`, row unchanged | B4, B12 |
| NT-07 | Cross-branch signed-scan upload | branch-B officer, branch-A application | `403`, no new row | B4 |
| NT-08 | Cross-branch record read (control) | same as NT-06 on the read route | `403` (already correct) | B4 |
| NT-09 | Unresolved branch assignment | officer with `branch_id IS NULL` | empty list + `403` on write | B5 |
| NT-10 | Invalid branch label | set `branch` to an unregistered string | no widening (denied) | B5 |
| NT-11 | Blank `location_scope` | PATCH checkpoint officer, `""` | `400`, unchanged | B5 |
| NT-12 | Self-granted scope | officer `PATCH /api/me` with branch fields | `400`/ignored, no change | B5 |
| NT-13 | Session after deactivation/reactivation | old token while disabled, then after enable | `401` both times | B6 |
| NT-14 | Login brute force | 15 wrong passwords | `429` + `Retry-After` | B7 |
| NT-15 | Unknown-username probing | same threshold, non-existent user | identical status/message, timing within tolerance | B7 |
| NT-16 | Concurrent last-admin demotion | two threads, two admins | one `200`, one `409`, ≥1 admin left | B8 |
| NT-17 | Concurrent identifier generation | 20 parallel creates | 20 unique ids, zero `409` | B9 |
| NT-18 | Duplicate user-supplied key | same national id twice | `409` (correct: genuine duplicate) | B9 |
| NT-19 | Audit row tampering via the app role | `UPDATE`/`DELETE audit_events` on the app DSN | permission error | B10, M-b |
| NT-20 | Audit row tampering via the owner | `UPDATE` as table owner | trigger exception | B10 |
| NT-21 | Plain HTTP / insecure cookie | `http://` request, cookie inspection | redirect or refused; cookie `Secure` | B11 |
| NT-22 | Token in `localStorage` | read storage after login | absent | B11 |
| NT-23 | Self-approval | creator approves own application | `403` | B12 |
| NT-24 | Permission denial must not sign out | `403` on a register the role may not read | no session cleared | B13 |
| NT-25 | Version-mismatched startup | app started against an older schema | refuses to serve | M-a |
| NT-26 | Person-detail section leak | Checkpoint officer, clearance data | section absent/withheld | M-c |
| NT-27 | Exception leakage | malformed JSON, duplicate insert, DB down | generic `500` + incident id; `503` on `/readyz` | M-d |
| NT-28 | Malicious upload | `.exe`, oversize, wrong magic bytes | `400`, nothing written | M-e, B1 |
| NT-29 | Confusable username | `X` then `x` | `409` | M-f |

---

### 10.7 Remediation tracking table

Status values: **Not started** (all items — no remediation has been approved or performed) · In progress · Blocked (dependency or decision outstanding) · Ready for review · PASS · Closed-by-decision.

| Action | Finding(s) | Priority | Depends on | Status | Test evidence required | Release gate |
|---|---|---|---|---|---|---|
| B1 | C-1 | Critical | D-7 | **Not started** | `test_document_access.py` + NT-01–NT-04 | Before any real document |
| B2 | C-2 | Critical | D-2, D-4, D-5 | **Not started** | `test_bootstrap_admin.py` + NT-05 | Before first production-mode start |
| B3 | C-3 | Critical | D-3, D-5 | **Not started** | `test_password_storage.py` | Before any real password |
| B4 | H-2 | Critical | — | **Not started** | `test_clearance_branch_scope.py` + NT-06–NT-08 | Before a second branch's second application |
| B5 | H-2, M-2 | High | B4, M-a*, D-6 | **Not started** | `test_branch_fail_closed.py` + NT-09–NT-12 | Pilot |
| B6 | H-3 | High | B13, M-a*, D-8 | **Not started** | `test_session_lifecycle.py` + NT-13 | Pilot |
| B7 | H-4 | High | B2, B10**, D-9 | **Not started** | `test_auth_hardening.py` + NT-14, NT-15 | Pilot |
| B8 | H-5 | High | — | **Not started** | `test_last_admin.py` + NT-16 | Pilot |
| B9 | H-6 | High | M-a*, D-10 | **Not started** | `test_identifier_concurrency.py` + NT-17, NT-18 | Pilot |
| B10 | H-7 | High | B7, M-b | **Not started** | `test_audit_integrity.py` + NT-19, NT-20 | Pilot |
| B11 | H-8, M-5 | High | D-1, D-11 | **Not started** | `test_http_hardening.py` + NT-21, NT-22 | Pilot |
| B12 | M-3 | High | D-12 | **Not started** | `test_review_gate.py` (extended) + NT-23 | Pilot |
| B13 | M-9 | High | — | **Not started** | `test_status_contract.py` + NT-24 | Pilot |
| M-a | M-11 | Medium | — | **Not started** | `test_migrations.py` + NT-25 | Production |
| M-b | M-8 | Medium | M-a, M-i, D-1 | **Not started** | `test_db_privileges.py` + NT-19 | Production |
| M-c | M-1 | Medium | B4, B5 | **Not started** | `test_person_scope.py` + NT-26 | Production |
| M-d | M-4, M-12 | Medium | D-4, M-a | **Not started** | `test_error_contract.py`, `test_health_probes.py` + NT-27 | Production |
| M-e | M-7 | Medium | B1, D-7 | **Not started** | `test_upload_validation.py` + NT-28 | Production |
| M-f | M-6 | Medium | M-a | **Not started** | `test_username_uniqueness.py` + NT-29 | Production |
| M-g | §7.1 | Medium | M-a, B5 | **Not started** | `test_query_plans.py` | Production |
| M-h | M-10, L-3 | Medium | — | **Not started** | CI green + audit report | Production |
| M-i | M-12, L-3 | Medium | M-a, M-b, D-1, RPO/RTO | **Not started** | Restore rehearsal record (manual) | Production |
| M-j | §8.4 | Medium | all items | **Not started** | finding→test→commit mapping | Every release |
| L-1 | CSRF | Low | B11 | **Not started** | token/header test after cookie-only transport | Production (after B11) |
| L-2 | Weak policy | Low | B3 | **Not started** | covered by `test_password_storage.py` | With B3 |
| L-3 | Logging/PII | Low | M-d, M-i | **Not started** | redaction test + log sample | Production |
| L-4 | Predictable ids / certificate verification | Low | B9 | **Not started** | verification endpoint test (optional) | Post-pilot |
| L-5 | No MFA/SSO, no recovery | Low | D-3, §12 item 3 | **Not started** | IdP integration test | Post-pilot |
| L-6 | Offline mode can show non-live data | Low | §12 item 11 | **Not started** | sync/conflict test if offline is in scope | Post-pilot |
| L-7 | Dead code in `rbac_self_test()` | Low | — | **Not started** | self-test still 8/8 + RBAC suite green | With any release |

\* Additive-only DDL constraint applies (see §10.5 sequencing note). \*\* B7 owns the initial authentication events; B10 adds enrichment and immutability.

**Release-gate definitions used above:** *Before any real document / password / production-mode start* = the system must not accept genuine data until the item is PASS. *Pilot* = a controlled pilot with authorised users and real (or de-identified) police data is blocked until PASS. *Production* = production deployment is blocked until PASS. *Post-pilot* = tracked, not blocking.

---

### 10.8 Evidence classification register

Requirement 6 of this revision: findings must be separable into what was **proven**, what was **read**, what is **assumed**, and what **needs your decision**. Nothing in §6 changes status because of this register.

#### 10.8.1 Verified facts `[V]` — reproduced by execution during this audit

| # | Fact | Where |
|---|---|---|
| V-1 | Anonymous `GET /uploads/<file>` returns `200` for a synthetic JPEG and PDF | C-1 |
| V-2 | Nine seeded accounts all authenticate with `ChangeMe123!` | C-2 |
| V-3 | The stored hash for `admin` equalled the published `sha256("abcdef")` after that password was set | C-3 |
| V-4 | An Erigavo-scoped officer attached a signed scan to, and then approved, a Lasanod application (`201`, certificate issued) while being refused (`403`) on the read route | H-2 |
| V-5 | A token survived a full server restart, survived an administrator password reset, and was revived by reactivation | H-3 |
| V-6 | 15 failed logins produced no throttling; zero authentication rows appeared in the audit log | H-4 |
| V-7 | The sole administrator demoted themselves and could not restore the role (`401`) | H-5 |
| V-8 | 12 concurrent case creations gave 8 × 201 and 4 × 409 | H-6 |
| V-9 | The cookie lacks `Secure`; no HSTS; no security headers; CORS `*`; token present in `localStorage` | H-8, M-5 |
| V-10 | A Checkpoint officer received another unit's clearance summary via `/api/persons/<id>` | M-1 |
| V-11 | Clearing `location_scope` widened a checkpoint officer from `['South']` to all locations | M-2 |
| V-12 | An officer self-approved a Citizenship application seconds after creating it | M-3 |
| V-13 | Malformed JSON returned `500` with Python internals; `409` echoed the constraint name | M-4 |
| V-14 | `Audit1baf` and `AUDIT1BAF` were both accepted | M-6 |
| V-15 | A legitimate HR officer's permission denial returned `401` | M-9 |
| V-16 | 21 of 23 existing suites pass; the two failures are SQLite-era harnesses | §8.2 |

#### 10.8.2 Code-review observations `[C]` — read, not executed

- No FK indexes and no `audit_events`/`sessions(user_id)` index (§7.1).
- Timestamps stored as `TEXT` throughout (§7.1/M-g).
- `/api/health` performs no database query (M-12).
- The application connects as `postgres` with no `sslmode` and no pool (M-8).
- Migrations have no version table, checksum or advisory lock (M-11).
- `person_document_records()` applies checkpoint scope but not fingerprint branch scope (§5.8).
- Unreachable statements after `return` in `rbac_self_test()` (L-7).
- Clearance intake calls the unvalidated `save_upload()` (M-7).

#### 10.8.3 Assumptions `[A]` — stated so they can be corrected

| # | Assumption | If wrong |
|---|---|---|
| A-1 | "Pilot" means real police data with authorised users, so all Critical + High items gate it | If the pilot is synthetic-only, the gate relaxes to **staging**, and B1–B4 still apply |
| A-2 | Deployment target is one HQ plus three branches over a private VPN, with PostgreSQL staying the engine | Changes §11 architecture and M-b/M-i only |
| A-3 | No external identity provider must be integrated before production | If one exists, L-5 becomes a production gate |
| A-4 | The twelve prior findings in the request are the complete prior list | §9 would need reconciliation (see 10.8.4 D-12/§12 item 12) |
| A-5 | No printed certificates are yet in circulation outside the system, so identifier formats may be adjusted (subject to D-10) | If certificates are already issued, identifier formats become frozen |
| A-6 | "Three branches" corresponds to the seeded Sool / Sanaag / East Togdheer units | Mostly affects test fixtures |
| A-7 | Current demo data exists only in throwaway environments | If demo accounts exist in a shared environment, D-5 becomes urgent |
| A-8 | No legal requirement is known for the Citizenship exemption | Determines B12's design (D-12) |

#### 10.8.4 Decisions required from you `[D]` — an item cannot be marked PASS while its decision is open

| # | Decision | Blocks | If unanswered |
|---|---|---|---|
| D-1 | Hosting target, regions, data residency; VPN/certificate ownership | B11, M-b, M-i | Items can be implemented but not deployed/verified |
| D-2 | Bootstrap administrator model and account name | B2 | Use: one `bootstrap_admin`, random 24-char password, forced change |
| D-3 | Password policy: minimum length, work factor, rotation, reuse history | B3, L-2 | Use: ≥ 12 chars, Argon2id at OWASP baseline, no mandatory rotation, block last 5 |
| D-4 | Runtime environment mode flag and its production semantics | B2, M-d | Use: `SENTINEL_ENV` ∈ {development, staging, production} |
| D-5 | Existing demo/dormant accounts: mass reset vs lazy upgrade vs disable | B2, B3 | Use: disable demo accounts in production, lazy upgrade + 30-day reset deadline |
| D-6 | May any role hold national scope, and who may grant it? | B5 | Use: administrator only, mandatory reason, audited |
| D-7 | Document storage backend (encrypted local volume vs object storage) | B1, M-e | Use: encrypted local volume for pilot, object storage before production |
| D-8 | Session lifetime (absolute + idle) and revoke-on-role-change policy | B6 | Use: 12 h absolute, 30 min idle, revoke on deactivate/reset only (role re-read per request) |
| D-9 | Lockout thresholds, window, unlock authority | B7 | Use: 5 failures / 15 min → 15 min lockout, administrator unlock |
| D-10 | Are current identifier formats contractual (printed certificates, integrations)? | B9 | Use: preserve `PREFIX-YYYY-NNNN` shape, continue numbering |
| D-11 | CSP scope: strict now (inline-script refactor) vs report-only with sunset | B11 | Use: report-only at pilot, enforced before production, sunset date recorded |
| D-12 | Is independent approval mandatory, and is the Citizenship exemption a legal requirement? | B12, A-8 | Use: independent approval required; exemption removed until evidenced |

---

## 11. Deployment readiness

### 11.1 Readiness by stage

| Stage | Verdict | Conditions |
|---|---|---|
| **Continued development** | **GO** | Keep all data synthetic. Retire the two SQLite-era suites so "all tests pass" means something. Add the regression tests in M-j as each finding is fixed. Do not seed demo accounts into any shared database. |
| **Dedicated staging environment** | **GO with conditions** | Private network or VPN only; TLS even internally; **synthetic or de-identified data only**; isolated database and upload volume; seeded demo accounts acceptable only here, and clearly labelled; no route to production data. |
| **Controlled pilot with authorised users** | **NO-GO** | Blocked by B1-B4 and B6-B8. A pilot with a real applicant's identity document in `/uploads` is an immediate disclosure incident. |
| **Production** | **NO-GO** | All of B1-B13 plus the M-* set (particularly migrations, database privilege, backups/restore, monitoring). |
| **Near-zero-downtime upgrades** | **Not achievable today** | Sessions are ready (see 11.4); schema migration is not. |

### 11.2 Recommended architecture (headquarters + three branches, private VPN, PostgreSQL)

```
                 ┌──────────────────── HQ data centre (private subnet) ────────────────────┐
                 │                                                                          │
  Branch 1 ──┐   │  ┌──────────────┐   443    ┌─────────────────┐   5432    ┌───────────┐  │
  Branch 2 ──┼── VPN ──►  Firewall   ────────► │ Reverse proxy   │ ────────► │ PostgreSQL │ │
  Branch 3 ──┘   │  │  (only 443    (TLS term, │  (nginx/Caddy)  │  TLS      │  primary   │  │
   (WireGuard)   │  │   from branch HSTS, rate  └────────┬────────┘  verify-  └─────┬─────┘  │
                 │  │   VPN subnets) limit, CSP)          │ 127.0.0.1       │  full   │        │
                 │  │                                      ▼                 ▼         │        │
                 │  │                        ┌──────────────┐        ┌────────────┐     │        │
                 │  │                        │ Sentinel app │        │ WAL stream │     │        │
                 │  │                        │  blue │ green│        │  → standby │     │        │
                 │  │                        └──────┬───────┘        └────────────┘     │        │
                 │  │                               │                                   │        │
                 │  │                     ┌─────────▼──────────┐   ┌──────────────────┐  │        │
                 │  │                     │ Document store     │   │ Backup target    │  │        │
                 │  │                     │ (encrypted volume/ │   │ (encrypted,      │  │        │
                 │  │                     │  object storage)   │   │  off-site)       │  │        │
                 │  │                     └────────────────────┘   └──────────────────┘  │        │
                 │  └──────────────────────────────────────────────────────────────────────┘        │
                 └──────────────────────────────────────────────────────────────────────────────┘
                       Monitoring · structured logs · metrics · alerting (out-of-band)
```

**Practical decisions for this stack:**

- **Do not put `ThreadingHTTPServer` on a public interface.** Bind it to `127.0.0.1` (or a private interface) behind the proxy; the proxy owns TLS, HSTS, rate limiting, request-size limits, compression and access logging. This also removes the need to add TLS to Python's stdlib server.
- **VPN:** WireGuard hub at HQ with a `/24` per branch; firewall allows **only TCP 443** from branch VPN subnets to the proxy, and **nothing** from branches to PostgreSQL. Administrative SSH only from a management subnet. No split tunnelling for police workstations.
- **Database isolation:** PostgreSQL on a dedicated host/instance, listening only on the private interface, `pg_hba` restricted to the app hosts and the migration runner, `sslmode=verify-full` from the app, least-privilege roles (app role without `DELETE`/DDL; a separate migration role), plus a streaming standby for fast recovery.
- **Uploaded files:** move out of the served directory. Either an encrypted block volume mounted only on app hosts, or object storage with SSE and versioning. All access through the authenticated route from B1. This is also the only way to satisfy "uploaded-file protection" as a deployment property.
- **Monitoring and alerting:** JSON logs to a central collector (with query strings redacted, per L-3), metrics for request rate/latency/error rate and database connections, an alert on failed-login spikes and on audit-write failures, `/healthz` (liveness) and `/readyz` (DB + schema version) probes, and a documented on-call path.
- **Release procedure:** build a versioned artefact directory (`/opt/sentinel/releases/<version>/` with `server.py`, `index.html`, `application.html`, `certificate.html`, `images/`), run migrations as a **separate, logged step**, symlink `current`, restart the app, verify `/api/health` (`build` + `review_lock_active`) and `/readyz`. Keep the previous two releases for rollback. Note the built-in guard: the process **refuses to start** if the served `index.html` stamp does not match the build — so shipped templates must always match the server build, and the release artefact (not a checkout) must be what is served via `SENTINEL_UI_DIR`.
- **Remediation of the port-eviction behaviour is mandatory** before running two colours on one host: `terminate_listener()` will kill the other instance.

### 11.3 Can the current application support blue-green or rolling deployment?

**Partially — the session layer is ready, the schema layer is not.**

| Requirement | Status | Notes |
|---|---|---|
| Stateless request handling | **Yes** | No in-process state is authoritative; `TOKENS` is only a cache with a database fallback. |
| Sessions survive an instance restart/replacement | **Yes, verified** | A token issued before a restart authenticated successfully after it. Two app instances can share the database and honour each other's sessions. |
| Shared uploaded-file storage | **No** | Files live on the local disk of the instance that received them; a second colour cannot serve them. Requires shared/object storage first. |
| Schema change without breaking the running colour | **No** | Migrations run inside the web process at startup with no versioning or lock. Two colours starting against the same database will each attempt DDL; a new colour can add columns the old colour ignores (usually survivable) but any rename/drop/constraint tightening breaks the live colour immediately. |
| Feature-flag-safe deployment of new UI | **Partially** | The UI is served from disk per request with a build-stamp check — convenient for a symlink switch, but it means the template and the server must be swapped together; two colours cannot safely serve two different templates from one directory unless `SENTINEL_UI_DIR` points at the release's own directory. |
| Health/readiness gating for traffic switching | **No** | `/api/health` does not touch the database, so a colour with a broken database connection would be reported healthy and receive traffic. |
| Application rollback | **Yes** (fast) | Previous release directory + restart. Sessions are unaffected. |
| Database rollback | **No** | Not possible today (no versioning, no snapshots, no down-migrations). |

**Changes required before near-zero-downtime upgrades are realistic:**

1. Extract migrations into a versioned directory applied by a separate job under `pg_advisory_lock`, with a `schema_migrations` table (M-11).
2. Adopt **expand → migrate → contract** as a rule: a release may only *add*; removal happens one release later. This is what makes old and new code able to share a schema.
3. Have the app **verify** the expected schema version at startup and refuse to serve on mismatch (the codebase already does this for the UI stamp and the RBAC self-test — same pattern).
4. Add `/readyz` that executes a query and checks the version; gate the proxy on it.
5. Move uploads to shared storage so both colours serve the same files.
6. Remove port eviction; give each colour its own port and a proxy upstream switch.
7. Keep `SENTINEL_UI_DIR` pointed at the release directory so template and code move as one artefact.

With those seven changes, blue-green becomes straightforward for this application: sessions already work across instances, and the deployment is small enough that a two-colour switch is trivially affordable.

### 11.4 Explicit warning: rollback is not the inverse of migration

The application contains no down-migrations, no schema version record and no snapshot mechanism. Therefore:

> **Rolling back the application binary does not reverse the database migration that accompanied it.** If release N+1 adds a column and release N is restored, the extra column is harmless — but if N+1 renamed, retyped, dropped or tightened anything (or backfilled data, as `migrate()` does for badges, districts and checkpoint metadata), returning to N leaves the database in a state N does not expect, with **no mechanism to undo the data change**. The only true rollback is a restore from backup — and no backup exists.

Until M-a and M-i are complete, every release must be treated as **forward-only**, scheduled in a maintenance window, and preceded by a manual `pg_dump` verified with `pg_restore --list`.

---

## 12. Remaining questions (only what the repository cannot answer)

1. **Hosting target** — which cloud/provider, which region(s), and is data-residency or sovereignty a constraint? (Affects the VPN hub, backup location and encryption key custody.)
2. **Network design** — is a WireGuard/IPSEC VPN already in place with an agreed IP plan, or must one be designed? Who issues and rotates certificates?
3. **Identity** — is there an organisational identity provider (AD/LDAP/OIDC) that Sentinel must integrate with, and is MFA mandated? If not, who owns account provisioning and password reset policy?
4. **Legal basis and retention** — what are the required retention periods for clearance applications, identity documents, checkpoint events, crime cases and audit logs? Is there a legal obligation for tamper-evident (or externally witnessed) audit trails?
5. **Data-protection approvals** — is there a privacy/DPIA sign-off covering biometric-adjacent data (fingerprints, photographs), guarantor details and cross-branch access? This determines whether the central person registry may be searchable by every role (currently it is).
6. **The `Citizenship` exemption** — is the 12-hour bypass for citizenship files a legal requirement, or a convenience? Is an independent approver required for certificates in general? (This decides B12's design.)
7. **Expected scale** — number of accounts, records per month, peak concurrent users, and document volume per record. This decides whether connection pooling, read replicas and storage architecture are needed at launch or later.
8. **RPO/RTO** — what data loss and downtime are acceptable? (Decides backup frequency, standby requirement and whether blue-green is worth the engineering.)
9. **Deployment authority** — who approves releases, who holds production database access, and is a two-person rule required for administrative changes to users and roles?
10. **Certificate verification** — must a third party (employer, embassy) be able to verify a printed certificate, and if so, online, by QR, or both?
11. **Mobile/field requirements** — is any offline operation genuinely required (e.g. checkpoints with intermittent connectivity)? If yes, the current `localStorage` fallback must be replaced by a designed sync model with conflict resolution before any real use.
12. **Previous audit artefact** — please provide the original `DEPLOYMENT_AUDIT.md` (or confirm it never existed) so this report's §9 can be reconciled against its actual wording rather than against the twelve findings restated in the request.

---

## Appendix A — How this assessment was performed (reproducible)

**Static review:** full read of `backend/server.py` (schema, RBAC, session, upload, routing, migration and startup paths), `backend/vehicles.py`, `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`, `README.md`, `TESTING.md`, `TROUBLESHOOTING.md`, `backend/README.md`, the four scripts, `index.html` (session, `api()`, routing, escaping), and every test file's harness and database provisioning.

**Safe test execution:** the project's 23 suites were run unmodified; two suites that needed `pgserver` and `jsdom` were enabled by installing those packages into a throwaway `.venv`/`node_modules` (both git-ignored). No suite was modified, skipped or retried to change its outcome.

**Live probing (synthetic only):**

```bash
# disposable cluster + backend, no operational data, no .env present
.venv/bin/python -c "import pgserver; pgserver.get_server('/tmp/sentinel_audit_pg', cleanup_mode=None)"
SENTINEL_DB_HOST=/tmp/sentinel_audit_pg SENTINEL_DB_NAME=postgres \
SENTINEL_DB_USER=postgres SENTINEL_UPLOADS=/tmp/sentinel_audit_uploads \
PORT=8123 .venv/bin/python backend/server.py
```

Every identity, document and record created during probing was fabricated in the probe script; the only mutation of application data outside the seeds was backdating one synthetic application's `created_at` **in the disposable cluster** to evaluate the review window, and restoring one role for a synthetic account after the self-demotion test. Both are recorded above and neither touched any real system. No `DROP`, `TRUNCATE` or `DELETE` was issued against any database. No public scanning service was used.

**What was deliberately not done:** no migration written or applied, no dependency installed into the project's runtime, no configuration changed, no code fixed, no file deleted, no deployment performed.

---

## Appendix B — Finding index

| ID | Severity | Title | Verification |
|---|---|---|---|
| C-1 | Critical | Identity documents downloadable without authentication | Verified |
| C-2 | Critical | Nine default accounts with a shared, documented password | Verified |
| C-3 | Critical | Unsalted SHA-256 password storage | Verified |
| H-2 | High | Branch isolation missing on approve / signed-scan / documents / person detail | Verified |
| H-3 | High | Sessions never expire; not revoked on password reset or role change; revived by reactivation | Verified |
| H-4 | High | No login throttling, lockout or authentication audit | Verified |
| H-5 | High | System Administrator self-lockout with no recovery | Verified |
| H-6 | High | Registration/identifier generation races | Verified |
| H-7 | High | Incomplete and mutable audit trail | Verified / code review |
| H-8 | High | No HTTPS, cookie without `Secure`, token duplicated into `localStorage` | Verified |
| M-1 | Medium | `/api/persons/<id>` exposes every unit's records | Verified |
| M-2 | Medium | Blank `location_scope` widens a checkpoint officer to all locations | Verified |
| M-3 | Medium | Review gate bypassable by `Citizenship`; no separation of duties | Verified |
| M-4 | Medium | Error responses leak internals; `/api/health` discloses environment | Verified |
| M-5 | Medium | No security headers; permissive CORS | Verified |
| M-6 | Medium | Case-sensitive usernames allow confusable accounts | Verified |
| M-7 | Medium | Inconsistent upload validation and unprotected storage | Verified / code review |
| M-8 | Medium | Superuser, unencrypted, unpooled database access | Code review |
| M-9 | Medium | Authorization failures return 401, causing client sign-out | Verified |
| M-10 | Medium | Stale SQLite artifacts; no dependency manifests | Verified |
| M-11 | Medium | Unversioned boot-time migrations; port eviction | Verified / code review |
| M-12 | Medium | No backup, restore, monitoring or DB-aware health check | Code review / absence |
| L-1 | Low | No CSRF tokens | Verified |
| L-2 | Low | Weak password policy | Verified |
| L-3 | Low | Logging quality; PII in logs; exceptions not logged | Verified |
| L-4 | Low | Predictable identifiers; no certificate verification | Verified |
| L-5 | Low | No MFA/SSO; no account recovery | Verified |
| L-6 | Low | Offline mode can present non-live data | Code review |
| L-7 | Low | Dead code inside `rbac_self_test()` | Verified |

---

*End of proposed audit. No change to the system's code, schema, configuration or deployment has been made. Implementation should not begin until this assessment has been reviewed and approved.*
