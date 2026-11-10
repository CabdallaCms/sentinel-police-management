# A-2(a) Rehearsal — Reconciliation Report

**Status: COMPLETED AS A PROCEDURE VALIDATION, NOT AS THE AUTHORIZED REHEARSAL.**
Read section 1 before any other section. The counts in this report describe a
synthetic fixture, not your corpus.

| | |
|---|---|
| Branch | `arena/6303ef2f-sentinel-police-management` |
| Commit at execution | `a8a1450c737a1b18cddf031cb7a24c7d0098bef0` (remote tip; local `HEAD` showed `a1c2478` under the known session anomaly — all 105 tracked files verified byte-identical to the remote tip by sha256) |
| Database used | Throwaway `pgserver` PostgreSQL cluster in `/tmp`, built from scratch, destroyed at exit. **No operational database exists and none was contacted.** |
| Executed | 2026-11-10, sandbox clock (platform header says 2026-11-05; sandbox governs; discrepancy disclosed) |
| Stopped at | Step 3. Step 4 not attempted. |
| Suite after | 28 pass / 0 fail / 1 blocked — the pre-existing baseline, unchanged |

---

## 1. The authorized rehearsal could not be performed as specified

Your Step 1 was *"verify the backup and confirm successful restoration."* That
step has no subject:

* **No backup exists.** No pre-`e7263d7` database was ever created.
* **No operational database exists.** Per R-1 the corpus is demo data only.
* **No PostgreSQL was installed** in the sandbox (`which postgres psql pg_ctl
  initdb pg_dump pg_restore` → all absent; no cluster; no running process).
  PostgreSQL binaries were obtained from the `pgserver` PyPI package that the
  existing test harness already depends on.

So there was nothing to restore and nothing to reconcile against.

**What was run instead:** the full Step 0 → Step 3 sequence against a database
built from scratch, seeded with a fixture designed to trigger every branch of
the procedure. This validates **the procedure and the DDL**. It says **nothing
about your real corpus**: every count below is a property of the fixture I
wrote. Treat the numbers as a demonstration that the tooling detects each
defect class, not as a measurement of anything.

The orphan and dangling counts for the real corpus remain, in the proposal's
own words, *"genuinely unknown until measured."*

A second gap: **the backfill script did not exist.** M-01 §4 states *"A backfill
script is NOT included in this proposal … listed as deliverable M-01-S, to be
written after approval."* I wrote it (`m01_backfill.py`) as part of this work.

---

## 2. What ran

| Step | Action | Result |
|---|---|---|
| 0 | Build origin DB via `server.init_db()`; seed fixture; `pg_dump`; restore into a second database; compare | **PASS** — 21 tables / 61 rows identical on both sides |
| 1 | Apply `m01_schema.sql` **to the restored copy** | **PASS** — table + 4 explicit indexes + implicit PK index; all 4 FKs `confdeltype = r` (RESTRICT) |
| 2 | Run `m01_backfill.py` across all 11 sources | 16 references discovered, 9 inserted |
| 3 | Reconcile | **HARD STOP.** Step 4 not attempted. |

### Your five A-1 conditions, each verified by execution

1. **Four FKs `ON DELETE RESTRICT`** — `pg_constraint.confdeltype = 'r'` on all
   four. Proved live: `DELETE FROM police_branches WHERE id=901` was **refused**
   with `violates foreign key constraint "documents_branch_id_fkey"`.
2. **`station_id` and `idx_documents_station` retained** — both present
   (`schema_applied.txt`) despite station visibility being deferred.
3. **Deactivate, never delete** — condition 1 now enforces this mechanically:
   the database physically refuses the delete.
4. **Export classifications before rollback** — not exercised; no rollback was
   performed. The requirement stands.
5. **No source record or file modified** — **proved, not asserted.** All 20
   source table counts identical before/after; sha256 of all 16 uploaded files
   identical before/after (`no_mutation_proof.json`).

---

## 3. Reconciliation findings (fixture)

```
discovered 16  |  approved 12  |  held 4  |  insertable 9  |  inserted 9
12 approved − 1 scope failure − 2 collision rows = 9 inserted  ✓
```

**(a) Orphans** — on disk, referenced by nothing: **2**
`f_orphan_never_referenced.pdf`, `f_inc_2.jpg`.

**(b) Dangling** — referenced, absent from disk: **1**
`clearance_applications.applicant_docs#902` → `f_missing_from_disk.pdf`.

**(c) Unclassified / scope-check failures** — **1**
`clearance_applications#902` (`FP-REH-0002`): class `branch`, but `branch_id IS
NULL`. It would violate `documents_scope_present`, so it was **excluded, not
guessed**. Goes to Step 4.

**(d) Duplicate `stored_name` collisions** — **1 name, 2 rows**
`f_shared_dup.pdf` claimed by `crime_incidents.evidence1_path#902` **and**
`crime_incidents.evidence2_path#901`.

**(e) Counts by visibility class**

| Class | Inserted | Held (discovered, deliberately not inserted) |
|---|---|---|
| `branch` | 8 | — |
| `self` | 1 | — |
| `station` | 0 | 3 (`officers.photo_path`, `officers.doc1_path`, `officer_conduct_actions.documents`) |
| `national` | 0 | 1 (`persons.photo_path`) |

The held rows are **A-3 classifications you have not approved**. The script
discovers and counts them but never inserts them. With no row, the serving path
refuses — fail-closed, as intended.

**(f) Malformed JSON** — **1**, not in your list, reported because it is a
data-loss risk: `clearance_applications#903.applicant_docs` contains
`{not valid json`. Any file it names is **invisible to the backfill** and would
404 after Phase B.

---

## 4. Unexpected findings

**4.1 — A duplicate `stored_name` aborts the entire backfill transaction.**
`idx_documents_stored_name` is UNIQUE, so the second insert raises
`UniqueViolation` and rolls back **everything**. M-01 §4 does not mention this
case. I made the script **exclude** colliding rows and report them for Step 4
rather than guess which owner wins — but **the procedure as written would have
failed outright** on the first collision. If two owners legitimately share a
file, the current one-row-per-file model cannot express it, and the UNIQUE index
is the wrong shape. **This needs your decision before any real run.**

**4.2 — The reconciliation is only as good as the data it can parse.** A
malformed JSON blob silently hides files. Recommend treating the malformed-blob
count as a release gate: it must be zero before Phase B.

**4.3 — `crime_incidents` requires `station_id NOT NULL`** while its documents
are classified `branch`. Not a defect, but it confirms a station pointer exists
on incident rows and not on users — consistent with the A-3 blocking finding.

### Data-loss risks

| Risk | Consequence |
|---|---|
| Malformed JSON blobs | Files never indexed → 404 after Phase B |
| Dangling references | Row points at a file that is already gone |
| Collisions | Second owner's claim silently absent unless resolved at Step 4 |
| Step-4 classifications | **Only irrecoverable artifact.** Export before any DROP (your condition 4) |

---

## 5. Boundaries respected

* **A-2(b) not approached.** No operational or production database contacted.
  `m01_backfill.py` requires `--i-confirm-this-is-a-restored-copy`.
* **Stopped at Step 3.** No classification, no re-insert, no Step 6.
* **`backend/server.py` not modified** — sha256 `a8211f4f…b3b9fc`, unchanged.
  The table is created by a standalone script, never by editing the app schema.
* **No commit, no push, no PR, no merge, no change to `main`.**
* **A-3/A-4/A-5 not implemented.** A-3's six proposed classifications are
  encoded in the script because the backfill cannot run without a class per
  source; the three held ones are inert.
* All 105 tracked files verified byte-identical to the remote tip.

## 6. Files produced

| Path | Contents |
|---|---|
| `m01_schema.sql` | A-1 DDL with your five conditions applied |
| `m01_backfill.py` | **M-01-S**, Steps 2–3, hard stop |
| `rehearse.py` | Step 0–3 harness |
| `evidence/reconciliation.json` | Full machine-readable findings |
| `evidence/no_mutation_proof.json` | Condition-5 proof |
| `evidence/restore_verification.json` | Step 0 table/row comparison |
| `evidence/schema_applied.txt` | Index + FK `confdeltype` listing |
| `evidence/rehearsal_log.txt` | Complete command log |

## 7. Stopping here

Awaiting your decision on **4.1 (collision policy)** and on whether to repeat
this against a real restored copy once a backup exists. No further step will be
taken without explicit approval.
