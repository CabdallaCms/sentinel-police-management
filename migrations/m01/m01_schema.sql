-- ============================================================================
-- M-01 Phase A — document ownership index
-- ============================================================================
-- Owner decision A-1, approved 10 November 2026, with five mandatory conditions:
--   1. All four foreign keys use ON DELETE RESTRICT.
--   2. station_id and its index are retained even though station visibility
--      (A-3) is deferred.
--   3. Referenced users and stations are deactivated, never physically deleted.
--   4. Human classifications are exported before any rollback that drops this
--      table.
--   5. No source record and no uploaded file is modified by this migration.
--
-- Differences from the original proposal in
-- security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md section 3, all approved:
--   * ON DELETE SET NULL -> ON DELETE RESTRICT on branch_id, station_id and
--     user_id. SET NULL fired an UPDATE that violated documents_scope_present,
--     so a delete failed with a constraint error instead of cascading.
--     RESTRICT removes the conflict at the source.
--   * uploaded_by made explicitly ON DELETE RESTRICT. It previously carried no
--     ON DELETE clause at all and silently defaulted to NO ACTION.
--   * idx_documents_station added, mirroring idx_documents_branch.
--
-- ADDITIVE ONLY. No ALTER, no DROP, no UPDATE of any existing object.
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents(
  id              SERIAL PRIMARY KEY,

  -- '/uploads/f_<hex>.<ext>' exactly as stored in the owning row.
  stored_path     TEXT NOT NULL,
  -- Basename only ('f_ab12....pdf'), the unit the HTTP route actually receives.
  stored_name     TEXT NOT NULL,
  original_name   TEXT,

  -- What owns this file.
  owner_table     TEXT NOT NULL,     -- 'clearance_applications', 'case_evidence', ...
  owner_pk        INTEGER NOT NULL,  -- the owning row's integer id
  owner_ref       TEXT,              -- human key: 'FP-12345678', 'CID-2026-008'
  owner_field     TEXT NOT NULL,     -- 'applicant_docs', 'doc1_path', ...

  -- How it is authorized. Exactly one class applies.
  visibility      TEXT NOT NULL
                  CHECK (visibility IN ('branch','station','national','self')),

  -- Condition 1: RESTRICT, not SET NULL. Condition 3: deactivate, never delete.
  branch_id       INTEGER REFERENCES police_branches(id) ON DELETE RESTRICT,
  station_id      INTEGER REFERENCES police_stations(id) ON DELETE RESTRICT,
  user_id         INTEGER REFERENCES users(id)           ON DELETE RESTRICT,

  -- Provenance and integrity (supports decision D-24, chain of custody).
  content_sha256  TEXT,
  byte_size       INTEGER,
  uploaded_by     INTEGER REFERENCES users(id)           ON DELETE RESTRICT,
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
CREATE INDEX IF NOT EXISTS idx_documents_owner   ON documents(owner_table, owner_pk);
CREATE INDEX IF NOT EXISTS idx_documents_branch  ON documents(branch_id);
-- Condition 2: retained even while station visibility is deferred under A-3.
CREATE INDEX IF NOT EXISTS idx_documents_station ON documents(station_id);
