# Document Authorization — Test Design

**Date:** 7 November 2026 · **Status:** design + prepared executable harness
**Pairs with:** `security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md` (M-01)
**Prepared harness:** `backend/test_document_branch_authorization.py`

---

## 1. What the owner asked for, and how it maps

| Required case | Tests | Expected after M-01 |
|---|---|---|
| **Same-branch access** | 2.1 | **200** — the file is served |
| **Cross-branch denial** | 2.2 | **403** — currently **200** |
| **Unauthenticated access** | 2.3 | **401** — already correct since Stage 0 |
| **Administrator access** | 2.4 | **200** — must not be broken by the fix |

Four more groups are included because each is a way the fix can be wrong in practice: unclassified
files (2.5), the non-branch visibility classes (2.6), audit (2.7) and regression (2.8).

---

## 2. Test specification

### 2.1 Same-branch access — the fix must not break legitimate work

| # | Case | Expected |
|---|---|---|
| T-01 | Officer posted to branch B reads a document filed under B | 200, correct bytes |
| T-02 | A second officer of the same role, same branch, reads it | 200 |
| T-03 | The uploading officer reads their own upload | 200 |
| T-04 | Same-branch access via **session cookie** (how `<img src>` loads) | 200 |
| T-05 | Every document type (clearance, checkpoint, case evidence, crime incident) is readable in-branch | 200 each |

T-05 matters: a missed source column in the backfill shows up here as a 404 on a legitimate file.

### 2.2 Cross-branch denial — the issue being fixed

| # | Case | Now | After M-01 |
|---|---|---|---|
| T-10 | Checkpoint officer (East) reads a South checkpoint document | **200** | **403** |
| T-11 | Fingerprint officer, branch A, reads branch B's clearance document | **200** | **403** |
| T-12 | CID officer reads another branch's case evidence | **200** | **403** |
| T-13 | The 403 body does not contain the file bytes | — | assert |
| T-14 | The denial is recorded in `audit_events` | — | assert |
| T-15 | Enumeration: 50 random `f_<hex>` names → never 200, never a distinguishable "exists" signal | — | assert |

### 2.3 Unauthenticated access — Stage 0 behaviour must not regress

| # | Case | Expected |
|---|---|---|
| T-20 | Anonymous GET of a real document | 401 |
| T-21 | Forged / random bearer token | 401 |
| T-22 | Logged-out (revoked) token | 401 |
| T-23 | Expired-looking / malformed cookie | 401 |
| T-24 | Anonymous GET of **every** file in the uploads directory | 401 for all |

These already pass today (`test_upload_access_control.py`). They are repeated here so the M-01
change cannot silently reopen C-1.

### 2.4 Administrator access

| # | Case | Expected |
|---|---|---|
| T-30 | `admin` reads a document from **any** branch | 200 |
| T-31 | `chief` (global read-only) reads any document | 200 |
| T-32 | Administrator access is **audited** | row in `audit_events` |
| T-33 | A non-admin cannot reach admin behaviour by sending an `admin` header/param | 403 |

T-32 is a recommendation, not a given — see approval A-4 in the migration proposal.

### 2.5 Unclassified and missing documents — fail closed

| # | Case | Expected |
|---|---|---|
| T-40 | File exists on disk, **no `documents` row** → scoped officer | **404** (fail closed, not served) |
| T-41 | Same file → administrator | 404 (consistent) or 200 with audit — **owner decision A-5** |
| T-42 | `documents` row exists, file missing from disk | 404 |
| T-43 | Path traversal (`..`, encoded, doubled) | never 200, no server source leaked |

**T-40 is the most important negative test in this suite.** It proves "unknown" is denied rather
than served, which is the exact failure the current system has.

### 2.6 Non-branch visibility classes

| # | Case | Expected |
|---|---|---|
| T-50 | `national` (person photo) read by any authenticated officer | 200 |
| T-51 | `self` (user avatar) read by its owner | 200 |
| T-52 | `self` avatar read by a **different** officer | 403 |
| T-53 | `station` (officer file) read from the same station | 200 |
| T-54 | `station` read from a different station by a non-HR role | 403 |
| T-55 | `station` read by HR Directorate | 200 — HR owns the personnel register |

T-55 encodes a policy assumption. If HR must be station-limited too, the owner must say so.

### 2.7 Audit

| # | Case | Expected |
|---|---|---|
| T-60 | Every denied document access writes one `audit_events` row with actor, file and reason | assert |
| T-61 | Audit writing never blocks or fails the request | assert |

### 2.8 Regression — Stage 0 guarantees still hold

| # | Case | Expected |
|---|---|---|
| T-70 | `X-Content-Type-Options: nosniff` present | assert |
| T-71 | Sandbox CSP present | assert |
| T-72 | Upload validation still rejects `.html`, `.svg`, double extensions, content mismatch | 400 |
| T-73 | Files on disk remain mode `0640`, non-executable | assert |

---

## 3. Prepared harness: `backend/test_document_branch_authorization.py`

The owner asked for tests to be *prepared*. The harness is written and included in this change, and
it is **executable today** — but it must not turn the suite red for a migration that has not been
approved. It therefore has two modes, selected automatically:

```
documents table ABSENT  ->  PRE-MIGRATION MODE
    Records today's real behaviour and SKIPS with an explicit message naming M-01.
    Cross-branch currently returns 200; the suite stays green and the exposure is stated.

documents table PRESENT ->  ENFORCEMENT MODE
    Runs the full strict matrix above. Cross-branch MUST be 403 or the suite fails.
```

This means the moment M-01 Phase A is approved and applied, the tests become live with **no edit**.

**Verified behaviour today — executed, not assumed.** The harness was run on 7 November 2026:
`Ran 15 tests ... OK (skipped=4)`. Eleven checks executed and passed (anonymous refusal, forged
token, revoked session, path traversal, administrator access, read-only commander access, the
Stage 0 response headers); the four checks that depend on M-01 skipped with an explicit message
naming the migration. It printed:

```
[document authorization] mode: PRE-MIGRATION
[document authorization] S-01 is OPEN: an authenticated officer can read another branch's documents.
```

With this suite added, the full run is **28 PASS / 0 FAIL / 1 BLOCKED / 0 SKIP** — the Stage 0
baseline of 27 PASS is preserved and this harness is the 28th.

> Read the suite-level PASS correctly: it means *no regression was introduced*. It does **not** mean
> cross-branch document access is safe. S-01 is open, and the four assertions that would prove it
> fixed are the ones currently skipping.

### Fixtures

- Two fingerprint branches and two checkpoint branches, created through the API.
- Officers posted to each, created through the API — never by direct SQL, so the posting resolution
  path is exercised the way production does it.
- Documents filed through the real multipart endpoints, with genuine PDF/JPEG magic bytes.
- **All identities synthetic.** No real police record is used, per the standing instruction.

### What the harness deliberately does not do

- It does not create the `documents` table. Creating schema is exactly what requires approval.
- It does not modify `server.py`.
- It does not assert a *specific* 403 message, only the status and the absence of file bytes —
  message wording should not be a test dependency.

---

## 4. Coverage gaps this design does not close

Stated explicitly so they are not mistaken for covered:

1. **Concurrency.** Two officers racing a document move between branches is untested. Low risk,
   but real (finding H-6 family).
2. **Direct filesystem access.** Anyone with shell access to `UPLOAD_DIR` bypasses all of this.
   That is an infrastructure control, not an application one.
3. **Re-sharing.** Nothing stops an authorized officer downloading a document and sending it on.
   Out of scope for access control; belongs with D-05 policy.
4. **Historical exposure.** These tests prove the system is sound *after* the fix. They say nothing
   about whether documents were already read cross-branch. If that matters, it is a log-forensics
   question — and the current audit log would not answer it, because reads were never audited.

---

## 5. Estimate

| Item | Days |
|---|---|
| Harness completion once `documents` exists (fixtures are already written) | 1–2 |
| Enforcement implementation + iteration against the tests | 4–6 |
| Report-only mode and its log assertions | 1–2 |
| **Total** | **6–10** |
