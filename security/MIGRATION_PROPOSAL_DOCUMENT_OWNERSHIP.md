# Migration Proposal M-01 — Document Ownership and Branch Authorization

**Date:** 7 November 2026 · **Status:** **PROPOSAL — NOT APPLIED**
**Addresses:** S-01 (cross-branch document access), finding N-6 (documents stored as JSON blobs)
**Requires:** explicit owner approval before any execution

> **Nothing in this document has been run.** No DDL was executed, no table was created, no data was
> written. The SQL below is a proposal for review.

---

## 1. The problem this solves

`/uploads/<file>` is now authenticated (Stage 0, WP-08), but **not authorized**. The server cannot
answer the question *"which record does this file belong to, and which branch owns that record?"*
because the link does not exist in a queryable form.

### Where upload paths actually live today — full inventory

| # | Table | Column(s) | Storage form | Branch resolvable? |
|---|---|---|---|---|
| 1 | `clearance_applications` | `applicant_docs`, `guardian_docs` | **JSON array in TEXT** | Yes — `branch_id` on the row |
| 2 | `clearance_applications` | `applicant_photo` | single path in TEXT | Yes |
| 3 | `clearance_signed_documents` | `file_path` | single path, **proper row** | Indirect — via `application_id` |
| 4 | `checkpoint_events` | `traveler_docs`, `guardian_docs` | **JSON array in TEXT** | Yes — `branch_id` on the row |
| 5 | `checkpoint_events` | `traveler_photo` | single path | Yes |
| 6 | `case_evidence` | `file_path` | single path, **proper row** | Indirect — via `case_id` → `crime_cases.branch_id` |
| 7 | `crime_incidents` | `evidence1_path`, `evidence2_path` | single paths | Yes — `branch_id` on the row |
| 8 | `officers` | `photo_path`, `guarantor_photo`, `doc1_path`, `doc2_path` | single paths | **No** — `station_id` only, no `branch_id` |
| 9 | `officer_conduct_actions` | `documents` | **JSON in TEXT** | **No** — `station_id` only |
| 10 | `persons` | `photo_path` | single path | **No branch at all** — persons are national |
| 11 | `users` | `avatar_path` | single path | **No branch** — it is the user's own avatar |

Three structural facts follow, and they shape the whole design:

- **Four of the eleven are JSON blobs.** They cannot be joined, indexed or authorized against.
- **Four have no branch at all** (8, 9, 10, 11). Two of those are *correctly* unscoped: a person's
  photograph is national data, and a user avatar belongs to the user. Officer and conduct documents
  are scoped by **station**, not branch — a different axis.
- **Two are already proper rows** (3, 6) and only need a resolver, not restructuring.

**Design consequence: a single `branch_id` on a document is the wrong model.** It cannot express
"national", "station-scoped" or "own-user-only". The proposal below uses an explicit
**visibility class** instead.

---

## 2. Design principles

1. **Additive only.** No column is dropped, no column is rewritten, no existing query changes
   meaning. The JSON blobs stay exactly where they are and keep working.
2. **The index is derived, not authoritative.** `documents` is a *lookup* built from existing data.
   If it disagrees with the owning row, the owning row wins and the index is rebuilt.
3. **Fail closed.** A file with no index row is **denied** to a scoped officer. This matches the
   existing `require_record_branch_scope()` contract: *"unknown must never mean everything."*
4. **Reversible.** Rollback is `DROP TABLE documents` plus reverting the code. No data is lost
   because no source data is modified.
5. **No behaviour change until the code is enabled.** Phase A creates the table and backfills it;
   nothing reads it. Enforcement is a separate, independently revertible step.

---

## 3. Proposed schema

```sql
-- M-01 Phase A — additive. Creates one new table and nothing else.
CREATE TABLE IF NOT EXISTS documents(
  id              SERIAL PRIMARY KEY,
  -- '/uploads/f_<hex>.<ext>' exactly as stored in the owning row.
  stored_path     TEXT NOT NULL,
  -- Basename only ('f_ab12….pdf'), the unit the HTTP route actually receives.
  stored_name     TEXT NOT NULL,
  original_name   TEXT,

  -- What owns this file.
  owner_table     TEXT NOT NULL,     -- 'clearance_applications', 'case_evidence', …
  owner_pk        INTEGER NOT NULL,  -- the owning row's integer id
  owner_ref       TEXT,              -- human key: 'FP-12345678', 'CID-2026-008'
  owner_field     TEXT NOT NULL,     -- 'applicant_docs', 'doc1_path', …

  -- How it is authorized. Exactly one class applies.
  visibility      TEXT NOT NULL
                  CHECK (visibility IN ('branch','station','national','self')),
  branch_id       INTEGER REFERENCES police_branches(id) ON DELETE SET NULL,
  station_id      INTEGER REFERENCES police_stations(id) ON DELETE SET NULL,
  user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,

  -- Provenance and integrity (supports decision D-24, chain of custody).
  content_sha256  TEXT,
  byte_size       INTEGER,
  uploaded_by     INTEGER REFERENCES users(id),
  created_at      TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS')),

  CONSTRAINT documents_scope_present CHECK (
    (visibility = 'branch'   AND branch_id  IS NOT NULL) OR
    (visibility = 'station'  AND station_id IS NOT NULL) OR
    (visibility = 'national') OR
    (visibility = 'self'     AND user_id    IS NOT NULL)
  )
);

-- The authorization lookup is by basename: one row per stored file.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_stored_name ON documents(stored_name);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_table, owner_pk);
CREATE INDEX IF NOT EXISTS idx_documents_branch ON documents(branch_id);
```

**Why `stored_name` is unique:** `save_upload()` generates `f_<16 hex>.<ext>`, so collisions are not
expected. A UNIQUE index turns any duplicate into a loud error at backfill time rather than a silent
authorization ambiguity.

**Why `content_sha256` is included now:** it is one column, it costs nothing to populate during the
backfill, and it is a prerequisite for decision **D-24** (evidence integrity). Adding it later means
a second migration over the same rows.

### Visibility class per source

| Source | Visibility | Scope column | Rationale |
|---|---|---|---|
| `clearance_applications.*` | `branch` | `branch_id` from the row | Filed under a fingerprint branch |
| `clearance_signed_documents.file_path` | `branch` | via `application_id` → application's `branch_id` | Inherits the application |
| `checkpoint_events.*` | `branch` | `branch_id` from the row | Filed under a checkpoint branch |
| `case_evidence.file_path` | `branch` | via `case_id` → `crime_cases.branch_id` | Inherits the case |
| `crime_incidents.evidence*_path` | `branch` | `branch_id` from the row | Filed under a crime branch |
| `officers.*` | `station` | `station_id` from the row | Personnel files are station-scoped, not branch-scoped |
| `officer_conduct_actions.documents` | `station` | `station_id` from the row | Same axis as the officer record |
| `persons.photo_path` | `national` | — | The person registry is national by design |
| `users.avatar_path` | `self` | `user_id` | A user's own avatar |

**`branch_id` may legitimately be NULL** on a row whose placement was never recorded (the
"Unassigned" legacy rows that Branch Management cleans up). Those rows **fail the CHECK
constraint**, so they must be classified during backfill — see §4, step 3. This is deliberate: it
forces the unknown cases to be *seen* rather than silently defaulting to visible.

---

## 4. Backfill procedure

Run inside one transaction, on a **restored copy of the database first**.

```
Step 0  Take a verified backup. Confirm the restore works before touching anything.
Step 1  CREATE TABLE documents (+ indexes). Additive; no existing object altered.
Step 2  Insert one row per upload path discovered in each of the 11 sources.
        - JSON blob columns: parse the array, emit one row per element.
        - Single-path columns: emit one row if non-empty.
        - Compute content_sha256 and byte_size by reading the file from UPLOAD_DIR.
Step 3  RECONCILE. Produce three reports and STOP for review:
          (a) files on disk with no documents row        -> orphans
          (b) documents rows whose file is missing        -> dangling references
          (c) rows that would violate documents_scope_present (NULL branch/station)
Step 4  Classify every item in (c) explicitly. Do not auto-assign.
Step 5  Re-run the insert for the classified rows.
Step 6  Verify: COUNT(documents) == number of distinct upload paths found in Step 2.
```

**Step 3 is a hard stop, not a formality.** `UPLOAD_DIR` has never been validated against the
database, so the orphan and dangling counts are genuinely unknown until measured. I have not run
this, so I cannot state the counts, and I will not estimate them.

**A backfill script is NOT included in this proposal.** Writing one means writing code that reads
and writes the database, which the current authorization forbids. It is listed as deliverable
**M-01-S** in the remediation plan, to be written after approval.

---

## 5. Enforcement design (Phase B — separate approval)

The `/uploads/` route gains an authorization step after the existing authentication step:

```python
# backend/server.py, /uploads/ route — DESIGN, NOT IMPLEMENTED
user = require_auth(self)                     # Stage 0: already in place
name = os.path.basename(p.path)

doc = lookup_document(c, name)                # SELECT … WHERE stored_name=%s
if doc is None:
    return self.send_json(404, {'error': 'Not found'})   # fail closed

authorize_document(c, user, doc)              # raises BranchScopeError -> 403
return self.send_file(...)
```

```python
def authorize_document(c, user, doc):
    """Fail-closed document authorization. Mirrors require_record_branch_scope()."""
    if is_admin_user(user) or is_records_admin(user):
        return                                  # administrators: full access
    if is_read_only_user(user):
        return                                  # Chief Commander: global read-only
    vis = doc['visibility']
    if vis == 'national':
        return
    if vis == 'self':
        if int(doc['user_id']) != int(user['id']):
            raise BranchScopeError('That file belongs to another user.')
        return
    if vis == 'station':
        if not user_station_matches(c, user, doc['station_id']):
            raise BranchScopeError('That file belongs to another station.')
        return
    if vis == 'branch':
        # Reuses the EXISTING Stage-0 helper and its fail-closed contract.
        require_record_branch_scope(c, user, doc_unit_type(doc), doc['branch_id'],
                                    'document', doc['stored_name'])
        return
    raise BranchScopeError('Unclassified document.')   # never fail open
```

**Three deliberate choices, flagged for owner review:**

1. **Unknown file → 404, not 403.** A 403 confirms the file exists. Since stored names are random
   128-bit tokens, a 404 leaks nothing and is the safer default.
2. **Administrators and the Chief Commander keep full read access.** This matches the existing
   model (`branch_scope_view()` returns `None` for them). If the owner wants administrator document
   access *audited* or *restricted*, that is a policy decision — say so and it changes.
3. **Every denial is audited.** A cross-branch document attempt is exactly the signal a police
   system should record. This adds rows to `audit_events`; no schema change.

---

## 6. Impact assessment

| Area | Impact |
|---|---|
| Existing tables | **None.** No ALTER, no DROP, no UPDATE of source rows. |
| Existing queries | **None.** The JSON blobs still work exactly as before. |
| New objects | One table, four indexes. |
| Storage | ~200 bytes per document row. Negligible. |
| Request latency | One indexed lookup by `stored_name` per `/uploads/` request. |
| Rollback | `DROP TABLE documents;` + revert the route change. No data loss. |
| Downtime | None for Phase A. Phase B is a code deploy. |
| Risk of locking out legitimate users | **This is the real risk.** A missed source column means a legitimate document 404s. Mitigated by the Step 3 reconciliation and by the staged rollout in §7. |

---

## 7. Recommended rollout

| Phase | Action | Revert |
|---|---|---|
| **A** | Create the table, backfill, reconcile. **Nothing reads it.** | `DROP TABLE documents` |
| **B1** | Deploy enforcement in **report-only** mode: authorize, log what *would* have been denied, serve the file anyway. Run for an agreed period. | flag off |
| **B2** | Review the report-only log. Zero unexpected denials → proceed. | — |
| **B3** | Enforce. | flag off |

**I strongly recommend B1.** The failure mode of getting this wrong is an officer unable to open a
case document during an operation. Report-only mode converts that risk into a log line.

---

## 8. What this does NOT do

- It does **not** restructure the JSON blobs into relational rows. That is a larger change
  (finding N-6 proper) and is not required to close S-01.
- It does **not** address evidence chain of custody (D-24) beyond providing `content_sha256`.
- It does **not** scope `persons.photo_path`. Person records are national by design; if the owner
  wants them scoped, that is a separate policy decision with wide consequences.
- It does **not** add `branch_id` to `suspect_alerts` (S-04) — that is proposal **M-02**, specified
  in the suspect-alert lifecycle document.

---

## 9. Approvals required before any execution

| # | Approval | Why |
|---|---|---|
| A-1 | Create the `documents` table (DDL) | Standing instruction: no silent schema change |
| A-2 | Run the backfill against a real database | It reads every upload and writes an index |
| A-3 | Confirm the visibility class per source (§3 table) | Policy, not engineering — especially officer/conduct = station |
| A-4 | Confirm administrators and Chief Commander retain full document read access | Policy |
| A-5 | Confirm 404-not-403 for unknown files | Security trade-off |
| A-6 | Approve the report-only rollout period (B1) | Operational risk tolerance |

**Estimate:** schema + backfill script + reconciliation tooling **5–8 engineering days**;
enforcement + tests **6–10 days**; report-only soak **1–2 weeks elapsed, low effort**.
