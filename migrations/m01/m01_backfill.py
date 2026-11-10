#!/usr/bin/env python3
"""M-01-S — document ownership backfill and reconciliation (Steps 2 and 3).

Owner authorization, 10 November 2026:
  * A-1  approved — the `documents` table (migrations/m01/m01_schema.sql).
  * A-2(a) approved — rehearsal against a verified RESTORED COPY only.
  * A-2(b) NOT approved — this tool must never be pointed at an operational
    database. There is no operational database (R-1), and running one is not
    authorized.

This tool implements Step 2 (discover and insert) and Step 3 (reconcile) of
section 4 of security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md, and then
STOPS. Step 4 (classify the unresolved rows) is a human act and is deliberately
not automated: the proposal says "Do not auto-assign".

A-3 boundary, enforced in code
------------------------------
Only the SIX classifications the owner has put forward for approval are
inserted:
    five branch-scoped sources + users.avatar_path as self-scoped.
The three HELD classifications are discovered and counted but NEVER inserted:
    officers.*                        -> station  (held: no station subject model)
    officer_conduct_actions.documents -> station  (held: no station subject model)
    persons.photo_path                -> national (held: pending D-05)
Holding them is fail-closed: with no row, the serving path refuses.

Source records and uploaded files are never modified (A-1 condition 5).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

import psycopg2
import psycopg2.extras

# --------------------------------------------------------------------------
# The eleven sources, exactly as inventoried in M-01 section 1.
# `status` is 'approved' (insert) or 'held' (discover and count only).
# --------------------------------------------------------------------------
SOURCES = [
    # 1 + 2  clearance_applications
    dict(n=1, table='clearance_applications', field='applicant_docs', json=True,
         visibility='branch', status='approved'),
    dict(n=1, table='clearance_applications', field='guardian_docs', json=True,
         visibility='branch', status='approved'),
    dict(n=2, table='clearance_applications', field='applicant_photo', json=False,
         visibility='branch', status='approved'),
    # 3  clearance_signed_documents -> branch via application_id
    dict(n=3, table='clearance_signed_documents', field='file_path', json=False,
         visibility='branch', status='approved'),
    # 4 + 5  checkpoint_events
    dict(n=4, table='checkpoint_events', field='traveler_docs', json=True,
         visibility='branch', status='approved'),
    dict(n=4, table='checkpoint_events', field='guardian_docs', json=True,
         visibility='branch', status='approved'),
    dict(n=5, table='checkpoint_events', field='traveler_photo', json=False,
         visibility='branch', status='approved'),
    # 6  case_evidence -> branch via case_id -> crime_cases.branch_id
    dict(n=6, table='case_evidence', field='file_path', json=False,
         visibility='branch', status='approved'),
    # 7  crime_incidents
    dict(n=7, table='crime_incidents', field='evidence1_path', json=False,
         visibility='branch', status='approved'),
    dict(n=7, table='crime_incidents', field='evidence2_path', json=False,
         visibility='branch', status='approved'),
    # 8  officers  -- HELD under A-3
    dict(n=8, table='officers', field='photo_path', json=False,
         visibility='station', status='held'),
    dict(n=8, table='officers', field='guarantor_photo', json=False,
         visibility='station', status='held'),
    dict(n=8, table='officers', field='doc1_path', json=False,
         visibility='station', status='held'),
    dict(n=8, table='officers', field='doc2_path', json=False,
         visibility='station', status='held'),
    # 9  officer_conduct_actions  -- HELD under A-3
    dict(n=9, table='officer_conduct_actions', field='documents', json=True,
         visibility='station', status='held'),
    # 10 persons  -- HELD pending D-05
    dict(n=10, table='persons', field='photo_path', json=False,
         visibility='national', status='held'),
    # 11 users
    dict(n=11, table='users', field='avatar_path', json=False,
         visibility='self', status='approved'),
]

# How the scope column is resolved per table.
SCOPE_SQL = {
    'clearance_applications':
        "SELECT id, application_id AS ref, branch_id AS scope, {f} AS val "
        "FROM clearance_applications",
    'clearance_signed_documents':
        "SELECT d.id, d.application_id AS ref, a.branch_id AS scope, d.{f} AS val "
        "FROM clearance_signed_documents d "
        "LEFT JOIN clearance_applications a ON a.application_id = d.application_id",
    'checkpoint_events':
        "SELECT id, event_id AS ref, branch_id AS scope, {f} AS val "
        "FROM checkpoint_events",
    'case_evidence':
        "SELECT e.id, e.evidence_id AS ref, c.branch_id AS scope, e.{f} AS val "
        "FROM case_evidence e LEFT JOIN crime_cases c ON c.id = e.case_id",
    'crime_incidents':
        "SELECT id, NULL AS ref, branch_id AS scope, {f} AS val FROM crime_incidents",
    'officers':
        "SELECT id, service_id AS ref, station_id AS scope, {f} AS val FROM officers",
    'officer_conduct_actions':
        "SELECT id, action_id AS ref, station_id AS scope, {f} AS val "
        "FROM officer_conduct_actions",
    'persons':
        "SELECT id, NULL AS ref, NULL AS scope, {f} AS val FROM persons",
    'users':
        "SELECT id, username AS ref, id AS scope, {f} AS val FROM users",
}

SCOPE_COLUMN = {'branch': 'branch_id', 'station': 'station_id',
                'self': 'user_id', 'national': None}


def column_exists(cur, table, column):
    cur.execute("SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s", (table, column))
    return cur.fetchone() is not None


def split_paths(value, is_json):
    """Return the list of upload paths held in one column value."""
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    if not is_json:
        return [raw]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        # A malformed blob is a finding, not a crash.
        return [('__MALFORMED__', raw)]
    out = []
    if isinstance(parsed, list):
        for el in parsed:
            if isinstance(el, str) and el.strip():
                out.append(el.strip())
            elif isinstance(el, dict):
                for key in ('path', 'file_path', 'stored_path', 'url'):
                    if isinstance(el.get(key), str) and el[key].strip():
                        out.append(el[key].strip())
                        break
    elif isinstance(parsed, str) and parsed.strip():
        out.append(parsed.strip())
    return out


def discover(cur, uploads_dir):
    """Step 2 — find every upload reference across the eleven sources."""
    refs, missing_columns, malformed = [], [], []
    for src in SOURCES:
        if not column_exists(cur, src['table'], src['field']):
            missing_columns.append(f"{src['table']}.{src['field']}")
            continue
        sql = SCOPE_SQL[src['table']].replace('{f}', src['field'])
        cur.execute(sql)
        for row in cur.fetchall():
            for item in split_paths(row['val'], src['json']):
                if isinstance(item, tuple):
                    malformed.append(dict(table=src['table'], field=src['field'],
                                          pk=row['id'], raw=item[1][:200]))
                    continue
                name = os.path.basename(item)
                full = os.path.join(uploads_dir, name)
                try:
                    size = os.path.getsize(full)
                    with open(full, 'rb') as fh:
                        digest = hashlib.sha256(fh.read()).hexdigest()
                    on_disk = True
                except OSError:
                    size, digest, on_disk = None, None, False
                refs.append(dict(
                    inv=src['n'], table=src['table'], field=src['field'],
                    visibility=src['visibility'], status=src['status'],
                    pk=row['id'], ref=row['ref'], scope=row['scope'],
                    stored_path=item, stored_name=name,
                    byte_size=size, sha256=digest, on_disk=on_disk))
    return refs, missing_columns, malformed


def reconcile(refs, uploads_dir):
    """Step 3 — produce the reconciliation report and stop."""
    approved = [r for r in refs if r['status'] == 'approved']
    held = [r for r in refs if r['status'] == 'held']

    # (c) scope-check failures: an approved reference whose scope is NULL and
    #     whose visibility class requires one.
    unclassified = [r for r in approved
                    if SCOPE_COLUMN[r['visibility']] and r['scope'] is None]
    insertable = [r for r in approved if r not in unclassified]

    # (b) dangling: a reference whose file is not on disk.
    dangling = [r for r in refs if not r['on_disk']]

    # (a) orphans: a file on disk that no source column references at all.
    referenced = {r['stored_name'] for r in refs}
    try:
        on_disk = {f for f in os.listdir(uploads_dir)
                   if os.path.isfile(os.path.join(uploads_dir, f))}
    except OSError:
        on_disk = set()
    orphans = sorted(on_disk - referenced)

    # (d) duplicate stored_name collisions among insertable rows.
    #     A collision is an UNRESOLVED classification: the same stored file is
    #     claimed by two owners with possibly different scopes, and the UNIQUE
    #     index would reject the second insert and abort the transaction.
    #     Section 4 does not say what to do with one, so M-01-S refuses to
    #     guess: colliding rows are EXCLUDED from the insert and reported for
    #     Step 4, exactly like a scope-check failure.
    seen = defaultdict(list)
    for r in insertable:
        seen[r['stored_name']].append(f"{r['table']}.{r['field']}#{r['pk']}")
    collisions = {k: v for k, v in seen.items() if len(v) > 1}
    if collisions:
        insertable = [r for r in insertable if r['stored_name'] not in collisions]

    return dict(
        discovered=len(refs), approved=len(approved), held=len(held),
        insertable=len(insertable), unclassified=unclassified,
        dangling=dangling, orphans=orphans, collisions=collisions,
        by_visibility=dict(Counter(r['visibility'] for r in insertable)),
        held_by_visibility=dict(Counter(r['visibility'] for r in held)),
        by_source=dict(Counter(f"{r['table']}.{r['field']}" for r in refs)),
        insertable_rows=insertable)


def insert_rows(cur, rows):
    """Step 2 insert. Only rows that pass the scope check are written."""
    done = 0
    for r in rows:
        col = SCOPE_COLUMN[r['visibility']]
        branch = r['scope'] if col == 'branch_id' else None
        station = r['scope'] if col == 'station_id' else None
        user = r['scope'] if col == 'user_id' else None
        cur.execute(
            "INSERT INTO documents(stored_path, stored_name, original_name, "
            "owner_table, owner_pk, owner_ref, owner_field, visibility, "
            "branch_id, station_id, user_id, content_sha256, byte_size) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (r['stored_path'], r['stored_name'], None, r['table'], r['pk'],
             str(r['ref']) if r['ref'] is not None else None, r['field'],
             r['visibility'], branch, station, user, r['sha256'], r['byte_size']))
        done += 1
    return done


def main():
    ap = argparse.ArgumentParser(description='M-01-S backfill, Steps 2 and 3.')
    ap.add_argument('--dsn', required=True, help='restored-copy DSN ONLY')
    ap.add_argument('--uploads', required=True)
    ap.add_argument('--json-out')
    ap.add_argument('--i-confirm-this-is-a-restored-copy', action='store_true',
                    required=True, help='A-2(b) is not approved.')
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        refs, missing_columns, malformed = discover(cur, args.uploads)
        report = reconcile(refs, args.uploads)
        report['missing_columns'] = missing_columns
        report['malformed_json'] = malformed

        inserted = insert_rows(cur, report.pop('insertable_rows'))
        report['inserted'] = inserted

        cur.execute('SELECT COUNT(*) AS n FROM documents')
        report['documents_rowcount'] = cur.fetchone()['n']
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    if args.json_out:
        with open(args.json_out, 'w') as fh:
            json.dump(report, fh, indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('unclassified', 'dangling')},
                     indent=2, default=str))
    print('\nSTEP 3 REACHED — HARD STOP. Step 4 classification is a human act.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
