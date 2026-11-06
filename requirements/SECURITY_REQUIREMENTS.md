# Security Requirements (Release 1.0)

**Phase 3 deliverable F · Requirements only. No application code was changed and no runtime
penetration testing was performed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Evidence basis.** Every requirement below converts a finding from
> `assessment/SECURITY_REMEDIATION_PRIORITY.md` (24 findings: 3 Critical, 10 High, 8 Medium, 3 Low)
> into a testable requirement. Finding identifiers are **never renumbered** — audit IDs `C-*`, `H-*`,
> `M-*` retain their original meaning and new findings use the `N-` band.
>
> **All findings were established by static inspection of commit `a1c2478`.** Static inspection is
> **not** proof of runtime security. Every requirement therefore specifies a **verification method
> that executes**, and none may be marked satisfied on code reading alone.

**Verification methods:** `AT` automated test · `NT` automated **negative** test · `MT` manual
verification with recorded evidence · `CFG` configuration review with evidence · `PEN` penetration
test · `PROC` rehearsed procedure.

---

## 1. Release-blocking requirements — CRITICAL

| ID | Requirement | Finding | Severity | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-01** | No police document, evidence file, traveller document, clearance scan or officer photograph is retrievable without an authenticated, authorized, audited request | **C-1** `:7914` | Critical | Remove the static `/uploads/` route; serve via `/api/documents/<id>` with owning-record scope (ARCH-501…506) | `NT` anonymous fetch of a known path returns 401/404 · `NT` cross-branch fetch returns 403 · `AT` every read audited · `PEN` | **YES** |
| **SR-02** | No account exists with a default, shared, published or seeded password in any environment reachable by a user | **C-2** `:3304`, `README.md:566` | Critical | Remove `ChangeMe123!` from all 9 seeds; force first-login change; remove credentials from documentation | `NT` seeded password fails · `AT` first login forces change · `MT` documentation scan | **YES** |
| **SR-03** | Passwords are stored with a salted, iterated, memory- or CPU-hard function | **C-3** `:3362` | Critical | Replace unsalted SHA-256. **Recommendation: stdlib `hashlib.pbkdf2_hmac('sha256', …)` with a per-user salt and ≥600,000 iterations — no new dependency** (**D-03**). Rehash transparently on next login | `AT` hash format and iteration count · `NT` two users with the same password have different hashes · `AT` legacy hash upgrades on login | **YES** |

---

## 2. Release-blocking requirements — HIGH

### 2.1 Authorization and isolation

| ID | Requirement | Finding | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-04** | Branch scope resolution **fails closed**. An unresolvable posting returns 403 | **H-2b** `:2661-2694` | High | `branch_scope_view()` returns deny, not `None`; update all 10 call sites | `NT` unresolvable posting returns 403 · `NT` no national dataset is ever returned · `AT` all 10 sites | **YES** |
| **SR-05** | Checkpoint location scope **fails closed**; a blank scope denies | **M-2** *(re-rated **UP** to High)* `:1922`, `:2990`, `:8460`, `:9301` | High | Blank/unresolvable ⇒ deny at all three consumption sites; startup assertion refuses a blank-scope role | `NT` blank-scope role denied · `NT` cross-location write 403 · `AT` startup assertion · `AT` legacy/canonical parity | **YES** |
| **SR-06** | Every fingerprint and crime route enforces branch scope on read **and** write | **H-2a** `:8997`, `:9032`, `:8152`; **N-2** `:9581`, `:9092`, `:9172` | High | Apply `require_record_branch_scope()` (the fail-closed resolver) at the 7 unscoped sites | `NT` per site: cross-branch approve / signed-document / person-docs / case PATCH / evidence / alert create all return 403 and are audited | **YES** |
| **SR-07** | `GET /api/suspect-alerts` is branch-isolated | **N-1** `:8425` | High | **Requires DDL**: add `branch_id` to `suspect_alerts`, backfill from the linked case where possible, then filter. Sits behind SR-18 (migrations) | `NT` branch-A officer sees only branch-A alerts, asserted **on record ids, not counts** | **YES** |

### 2.2 Authentication and session management

| ID | Requirement | Finding | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-08** | All traffic uses TLS; session cookies carry `Secure`, `HttpOnly`, `SameSite` | **H-8** `:8677` | High | Terminate TLS; set cookie attributes. **Until this is done, no biometric or production data may be handled on any multi-host network** | `CFG` TLS config · `AT` cookie attributes · `NT` plaintext refused | **YES** |
| **SR-09** | Sessions expire after a defined idle and absolute lifetime and can be revoked | **H-3** `:446`, `:4004` | High | Add `expires_at`, enforce on validation, add server-side revocation (**D-08**) | `AT` idle expiry · `AT` absolute expiry · `AT` revocation invalidates immediately | **YES** |
| **SR-10** | Authentication is rate-limited and fully audited | **H-4** `:8664`, `:8680` | High | Per-account and per-source throttling with lockout; audit login success, failure, logout, password change | `AT` lockout after N failures · `AT` each event audited · `NT` enumeration via timing/response differences | **YES** |
| **SR-11** | Privilege changes revoke existing sessions, and the last administrator cannot be removed or demoted | **H-5** `:9638-9730` | High | Delete sessions on role/permission/status change (the self-service password path already does this at `:8759` — apply the same rule); refuse the last-admin operation | `NT` demoted user's session is immediately invalid · `NT` last admin cannot be deleted, demoted or deactivated | **YES** |

### 2.3 Integrity

| ID | Requirement | Finding | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-12** | The audit trail is append-only and records before/after values | **H-7** `:450`, `:4032`, `:9591` | High | Revoke UPDATE/DELETE on `audit_events` from the application role; capture before/after on every mutation; audit denials | `NT` application role cannot UPDATE or DELETE an audit row · `AT` UPDATE records prior and new values · `AT` denial produces an audit row | **YES** |

---

## 3. Release-blocking requirements — biometric *(new, consequent on D-18)*

> D-18 brings genuine biometric processing into Release 1.0. Biometric data is **irrevocable** — a
> breached password is changed, a breached fingerprint is not. These requirements are blocking
> **because the data cannot be remediated after exposure.**

| ID | Requirement | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|
| **SR-20** | Biometric templates and images are encrypted at rest with documented key management and rotation | Critical | Encrypted biometric store (FPR-701) | `CFG` + `AT` ciphertext at rest · `MT` key rotation rehearsed | **YES** |
| **SR-21** | No biometric data is written to browser storage | Critical | Remove `biometricStore` (**FPR-901**) | `NT` `localStorage` contains no biometric data after capture | **YES** |
| **SR-22** | **No code path returns an identification the matcher did not produce.** The rotating-cursor fallback is removed | Critical | **FPR-902**, `index.html:4573-4578` | `NT` non-enrolled probe returns no match · `AT` assertion that no candidate is selected by rotation, position or default | **YES** |
| **SR-23** | No role, including `SystemAdmin` and `chief_commander`, can bulk-export templates or images | High | FPR-703 | `NT` per role | **YES** |
| **SR-24** | Every template or image read is individually audited | High | FPR-704 | `AT` | **YES** |
| **SR-25** | Biometric endpoints never return template bytes to a general-purpose client | High | ARCH-706 | `NT` response bodies contain no template data | **YES** |
| **SR-26** | The capture bridge is reachable on loopback only and its protocol version is validated | High | ARCH-801/802 | `NT` non-local bridge address refused · `AT` unsupported version refused | **YES** |
| **SR-27** | Biometric retention is enforced with automated expiry and audited deletion | High | FPR-706, **D-04** | `AT` expiry job · `AT` deletion audited with tombstone | **YES** — subject to D-04 |

---

## 4. Non-blocking — MEDIUM

| ID | Requirement | Finding | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-13** | Identifiers are unique under concurrency and not year-hard-coded | **H-6** *(re-rated **DOWN** to Medium)* `:9083` | Medium | Year-scoped DB sequences with unique constraints; never rewrite issued identifiers | `AT` 100 concurrent creates yield 100 distinct ids · `AT` year correctness | No — but **required for correct records** |
| **SR-14** | Approval requires separation of duties; review-gate bypasses are explicit, reasoned and audited | **M-3** `:9052`, `:9057` | Medium | Submitter ≠ approver (**D-12**); `is_admin_user` and `citizenship_wait_exempt` cease to be silent bypasses (FPR-402/403, **D-06**) | `NT` self-approval refused · `AT` override produces a structured, queryable record | **YES if D-06 or D-12 requires it** |
| **SR-15** | All uploads are validated for extension, MIME and size, with sanitised filenames | **M-7** `:3939` | Medium | One validation path for every upload; `/signed-document` (`:9009`) already models it | `NT` disallowed type refused · `NT` oversized refused · `NT` traversal filename refused | No |
| **SR-16** | Analytics are branch-scoped | **N-3** `:6071`, `:6132` | Medium | Pass `user` to every builder, as `cid_checkpoint_analytics` (`:6176`) already does | `AT` scoped officer's totals equal their accessible record count | **YES** — it is a data leak |
| **SR-17** | The database uses a least-privilege role and encryption at rest | **M-8** | Medium | Dedicated role without superuser; encrypted storage | `CFG` | No — **required for production** |
| **SR-18** | Schema changes run through versioned, reversible migrations | **M-11** | Medium | `schema_migrations` table; DDL stops running as a startup side effect | `AT` migration applies and rolls back · `NT` startup performs no DDL | **YES** — SR-07 and all Release 1.0 DDL depend on it |
| **SR-19** | Backup, restore and monitoring exist and are **rehearsed** | **M-12** | Medium | Automated backup; documented restore; rehearsal evidence; health monitoring (**D-08**) | `PROC` restore rehearsal with recorded evidence | **YES** for production go-live |
| **SR-28** | Dead code and stale artefacts are removed; dependencies are pinned in manifests | **M-10** | Medium | Delete `backend/database.py`, `backend/migrate_rbac.py`, `backend/audit_instant_approvals.py`; add `requirements.txt` and `package.json` | `AT` imports resolve from manifests · `MT` dead-code scan | No — but it **precedes everything in practice** |

---

## 5. Non-blocking — LOW

| ID | Requirement | Finding | Sev | Correction | Verification | Blocking |
|---|---|---|---|---|---|---|
| **SR-29** | CORS uses an explicit origin allow-list | **N-4** `:7773` | Low | Replace `Access-Control-Allow-Origin: *` | `AT` disallowed origin rejected | No |
| **SR-30** | Standard security headers are present | **N-5** | Low | CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy | `AT` header assertions | No |
| **SR-31** | Attachment metadata is relational, not JSON in TEXT columns | **N-6** | Low | `document_objects` (ARCH-502/508) | `AT` per-document authorization | No |

---

## 6. Verification requirements that gate everything else

| ID | Requirement | Verification | Blocking |
|---|---|---|---|
| **SR-90** | **A runnable test environment exists.** 23 of 25 suites have never been executed in this environment (`psycopg2-binary`, `pgserver`, `jsdom@26` are absent and installation is outside the current authorization). Only `backend/test_print_fit.py` and `python3 backend/server.py --ui-check` run | `PROC` full suite executes and the result is recorded | **YES — this gates every other verification in this document** |
| **SR-91** | CI executes the full suite on every change | `CFG` + run evidence | **YES** |
| **SR-92** | Isolation tests assert on **record identifiers**, never on counts | `MT` test review | **YES** |
| **SR-93** | Every blocking requirement has an executed **negative** test proving the attack fails — not only a positive test proving the feature works | `MT` coverage review | **YES** |
| **SR-94** | An independent security review or penetration test covers authentication, authorization, document access and biometric handling before go-live | `PEN` | **YES** for production |

### 6.1 Proven test gaps *(each must be closed)*

| Gap | Status |
|---|---|
| `test_branch_scope.py` contains **0** references to `approve` or `signed-document` — the two unscoped fingerprint routes | Must add |
| No test fetches `/uploads/` anonymously | Must add |
| No test asserts that a blank `location_scope` **denies** | Must add |
| No test asserts suspect-alert isolation | Must add |
| No test asserts self-approval is refused | Must add |
| No upload-validation test | Must add |
| No concurrency test for identifier generation | Must add |
| **No Crime Unit test suite exists at all** | Must create |

**Well-covered areas (written, but not yet executed):** `test_review_gate.py` (37 references),
`test_branch_scope.py` (28), `test_sidebar_navigation.mjs` (86), `test_checkpoint_roles_audit.py` (76).

---

## 7. Remediation sequence

| Wave | Contents | Rationale |
|---|---|---|
| **Wave 0** | SR-90 (test environment), SR-28 (manifests, dead code) | **Nothing below can be verified without Wave 0.** It is not security work, but it gates all security work |
| **Wave 1** | SR-02, SR-01, SR-06 *(documents)*, **SR-04**, **SR-05**, SR-03 | The three Criticals plus the two fail-open scope resolvers. **SR-04 and SR-05 are the highest-leverage items in the entire programme** — one fail-closed change each, correcting many endpoints |
| **Wave 2** | SR-06 *(remaining)*, SR-18, SR-07, SR-11, SR-09, SR-10, SR-15, SR-14, SR-16 | Remaining isolation, session and integrity work. SR-18 precedes SR-07 because SR-07 needs DDL |
| **Wave 3** | SR-12, SR-13, SR-08, SR-17, SR-19, SR-29, SR-30, SR-31 | Integrity, transport, operations and hardening |
| **Biometric wave** | SR-20…SR-27 | Runs with the biometric work package. **No biometric data may be captured in any environment before SR-08, SR-20, SR-21 and SR-22 are satisfied** |

> **Order note:** SR-08 (TLS) appears in Wave 3 for *engineering sequencing*, but it is a
> **hard precondition for handling any real data**, including biometrics. It is not deferrable to
> after go-live.

---

## 8. Summary — release blockers

**27 of the 36 requirements are release-blocking:**
SR-01 · SR-02 · SR-03 · SR-04 · SR-05 · SR-06 · SR-07 · SR-08 · SR-09 · SR-10 · SR-11 · SR-12 ·
SR-14 *(conditional on D-06/D-12)* · SR-16 · SR-18 · SR-19 *(production)* · SR-20 · SR-21 · SR-22 ·
SR-23 · SR-24 · SR-25 · SR-26 · SR-27 *(conditional on D-04)* · SR-90 · SR-91 · SR-92 · SR-93 ·
SR-94 *(production)*.

**Not blocking, still required (7):** SR-13, SR-15, SR-17, SR-28, SR-29, SR-30, SR-31.

*(Counts verified against the tables above: 36 requirement identifiers, 27 rows flagged blocking.
SR-14, SR-19, SR-27 and SR-94 are blocking **conditionally**, as noted in their rows.)*

> **No security requirement in this document may be deferred to meet a date.** The original 10-day
> window is not a reason to reduce scope or bypass a control. A police system holding biometric,
> criminal and detention records against citizens does not have a minimum-viable security posture.
