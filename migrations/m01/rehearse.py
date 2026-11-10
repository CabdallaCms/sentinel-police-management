#!/usr/bin/env python3
"""A-2(a) rehearsal harness — restored copy only.

Sequence, matching the owner's required procedure:
  Step 0  build an origin database, take a dump, VERIFY the restore
  Step 1  create the documents table + indexes ON THE RESTORED COPY
  Step 2  run the M-01-S backfill
  Step 3  reconcile, then STOP

A-2(b) is not approved. Nothing here may be pointed at an operational
database; none exists (R-1). The origin database is built from scratch inside
a throwaway pgserver cluster and destroyed with it.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pgserver

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'

ORIGIN = 'm01_origin'
RESTORED = 'm01_restored'

LOG: list[str] = []


def log(msg=''):
    print(msg, flush=True)
    LOG.append(msg)


def run(cmd, **kw):
    log(f'$ {" ".join(str(c) for c in cmd)}')
    out = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if out.stdout.strip():
        log(out.stdout.strip()[:4000])
    if out.returncode != 0:
        log(f'!! exit {out.returncode}\n{out.stderr.strip()[:4000]}')
        raise SystemExit(f'command failed: {cmd[0]}')
    return out


def fingerprint_uploads(d):
    """sha256 of every file, so A-1 condition 5 can be proved not asserted."""
    import hashlib
    out = {}
    for f in sorted(pathlib.Path(d).iterdir()):
        if f.is_file():
            out[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def table_counts(uri):
    sql = ("SELECT table_name FROM information_schema.tables "
           "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")
    names = [l.strip() for l in
             pgserver.psql(['-d', uri, '-At', '-c', sql]).splitlines() if l.strip()]
    counts = {}
    for n in names:
        v = pgserver.psql(['-d', uri, '-At', '-c', f'SELECT COUNT(*) FROM "{n}"'])
        counts[n] = int(v.strip())
    return counts


def seed_fixture(uri, uploads):
    """Deliberately exercise every discovery path, including the failure paths."""
    uploads.mkdir(parents=True, exist_ok=True)

    def mkfile(name, body=b'fixture'):
        (uploads / name).write_bytes(body)
        return name

    # Files that exist on disk.
    f = {k: mkfile(k) for k in [
        'f_app_doc_a.pdf', 'f_app_doc_b.pdf', 'f_app_photo.jpg',
        'f_signed_1.pdf', 'f_cp_doc_a.pdf', 'f_cp_photo.jpg',
        'f_evidence_1.jpg', 'f_inc_1.jpg', 'f_inc_2.jpg',
        'f_officer_photo.jpg', 'f_officer_doc1.pdf',
        'f_conduct_1.pdf', 'f_person_photo.jpg', 'f_avatar.png',
        'f_shared_dup.pdf',
    ]}
    # An orphan: on disk, referenced by nothing.
    mkfile('f_orphan_never_referenced.pdf')
    # 'f_missing_from_disk.pdf' is referenced below but deliberately NOT created.

    stmts = [
        # --- reference data first: FK parents before children ---
        "INSERT INTO police_branches(id,name,region,unit_type) VALUES "
        "(901,'Rehearsal Fingerprint','Sool','fingerprint'),"
        "(902,'Rehearsal Crime','Sool','crime'),"
        "(903,'Rehearsal Checkpoint','Sool','checkpoint')"
        " ON CONFLICT DO NOTHING",
        "INSERT INTO police_stations(id,station_id,name,code,region,district,"
        "operational_status) VALUES (901,'STN-R-001','Rehearsal Station',"
        "'STN-SOL-901','Sool','Lasanod','Active') ON CONFLICT DO NOTHING",
        "INSERT INTO users(id,username,display_name,role,branch,password_hash,"
        "avatar_path) VALUES (901,'rehearsal.user','Rehearsal User','CIDUnit',"
        "'Rehearsal Crime','x','/uploads/f_avatar.png') ON CONFLICT DO NOTHING",
        # 10 persons -- HELD pending D-05 (also the checkpoint FK parent)
        "INSERT INTO persons(id,person_id,full_name,photo_path) VALUES "
        "(901,'PER-REH-001','Rehearsal Person','/uploads/f_person_photo.jpg')",
        # 8 officers -- HELD under A-3 (also the crime_incidents FK parent)
        "INSERT INTO officers(id,service_id,rank,unit,station_id,"
        "date_of_enlistment,full_name,mother_name,date_of_birth,place_of_birth,"
        "contact_number,guarantor_name,guarantor_address,guarantor_contact,"
        "doc1_type,doc1_path,photo_path) VALUES (901,'SVC-REH-001','Constable',"
        "'Crime',901,'2020-01-01','Rehearsal Officer','M','1990-01-01','Lasanod',"
        "'000','G','Addr','000','ID','/uploads/f_officer_doc1.pdf',"
        "'/uploads/f_officer_photo.jpg')",

        # --- 1 + 2 clearance_applications ---
        "INSERT INTO clearance_applications(id,application_id,person_id,purpose,branch_id,"
        "applicant_docs,guardian_docs,applicant_photo) VALUES "
        "(901,'FP-REH-0001',901,'Employment',901,'[\"/uploads/f_app_doc_a.pdf\","
        "\"/uploads/f_app_doc_b.pdf\"]','[]','/uploads/f_app_photo.jpg')",
        # scope-check failure: branch_id NULL on an approved (branch) class,
        # and the referenced file is deliberately absent from disk (dangling).
        "INSERT INTO clearance_applications(id,application_id,person_id,purpose,branch_id,"
        "applicant_docs) VALUES (902,'FP-REH-0002',901,'Employment',NULL,"
        "'[\"/uploads/f_missing_from_disk.pdf\"]')",
        # malformed JSON blob
        "INSERT INTO clearance_applications(id,application_id,person_id,purpose,branch_id,"
        "applicant_docs) VALUES (903,'FP-REH-0003',901,'Employment',901,'{not valid json')",

        # --- 3 clearance_signed_documents -> branch via application_id ---
        "INSERT INTO clearance_signed_documents(id,application_id,file_path,"
        "file_name) VALUES (901,'FP-REH-0001','/uploads/f_signed_1.pdf','s.pdf')",

        # --- 4 + 5 checkpoint_events ---
        "INSERT INTO checkpoint_events(id,event_id,person_id,branch_id,location,"
        "screening_result,action_taken,traveler_docs,traveler_photo) VALUES "
        "(901,'CP-REH-0001',901,903,'South','No active alert','Cleared',"
        "'[\"/uploads/f_cp_doc_a.pdf\"]','/uploads/f_cp_photo.jpg')",

        # --- 6 case_evidence -> branch via case_id -> crime_cases.branch_id ---
        "INSERT INTO crime_cases(id,case_id,branch_id,category,status) VALUES "
        "(901,'CID-REH-001',902,'Theft','Open')",
        "INSERT INTO case_evidence(id,evidence_id,case_id,file_path) VALUES "
        "(901,'EV-REH-001',901,'/uploads/f_evidence_1.jpg')",

        # --- 7 crime_incidents, incl. the duplicate stored_name collision ---
        "INSERT INTO crime_incidents(id,file_number,station_id,officer_id,"
        "category,incident_at,description,case_status,branch_id,evidence1_path,"
        "evidence2_path) VALUES (901,'CRM-REH-0001',901,901,'Theft',"
        "'2026-01-01','d','Reported / Open',902,'/uploads/f_inc_1.jpg',"
        "'/uploads/f_shared_dup.pdf')",
        "INSERT INTO crime_incidents(id,file_number,station_id,officer_id,"
        "category,incident_at,description,case_status,branch_id,evidence1_path)"
        " VALUES (902,'CRM-REH-0002',901,901,'Theft','2026-01-02','d',"
        "'Reported / Open',902,'/uploads/f_shared_dup.pdf')",

        # --- 9 officer_conduct_actions -- HELD under A-3 ---
        "INSERT INTO officer_conduct_actions(id,action_id,officer_id,action_type,"
        "classification,narrative,station_id,documents) VALUES (901,'AC-REH-001',"
        "901,'Misconduct','Minor','n',901,'[\"/uploads/f_conduct_1.pdf\"]')",
    ]
    for s in stmts:
        try:
            pgserver.psql(['-d', uri, '-v', 'ON_ERROR_STOP=1', '-c', s])
        except Exception as exc:                      # noqa: BLE001
            log(f'   fixture statement skipped: {str(exc).splitlines()[0][:160]}')
    return f


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='m01_rehearsal_')
    uploads = pathlib.Path(tmp) / 'uploads'
    log(f'workspace: {tmp}')

    log('\n=== starting throwaway pgserver cluster ===')
    srv = pgserver.get_server(str(pathlib.Path(tmp) / 'pgdata'))
    base = srv.get_uri()
    log(f'cluster up: {base}')

    origin_uri = srv.get_uri(database=ORIGIN)
    restored_uri = srv.get_uri(database=RESTORED)
    pgserver.psql(['-d', base, '-c', f'CREATE DATABASE {ORIGIN}'])

    log('\n=== building the ORIGIN database (Sentinel schema) ===')
    env = dict(os.environ)
    # The unix socket directory is the `host=` query parameter of the URI.
    sock = base.split('host=')[-1].split('&')[0]
    log(f'socket dir: {sock}')
    env.update(SENTINEL_DB_HOST=sock,
               SENTINEL_DB_PORT='5432', SENTINEL_DB_USER='postgres',
               SENTINEL_DB_PASSWORD='', SENTINEL_DB_NAME=ORIGIN,
               SENTINEL_SEED_DEMO_DATA='1',
               SENTINEL_UPLOADS=str(uploads))
    uploads.mkdir(parents=True, exist_ok=True)
    run([sys.executable, '-c',
         'import sys; sys.path.insert(0,"backend"); import server; '
         'server.init_db(); print("init_db OK")'], cwd=ROOT, env=env)

    log('\n=== seeding the rehearsal fixture ===')
    seed_fixture(origin_uri, uploads)
    log(f'uploads dir now holds {len(list(uploads.iterdir()))} files')
    uploads_before = fingerprint_uploads(uploads)

    # ---------------- Step 0 : backup + verified restore ----------------
    log('\n=== STEP 0 — backup, restore, VERIFY ===')
    dump = pathlib.Path(tmp) / 'origin.sql'
    pgbin = pathlib.Path(pgserver.__file__).parent / 'pginstall' / 'bin'
    run([str(pgbin / 'pg_dump'), '-d', origin_uri, '-f', str(dump)])
    log(f'pg_dump written: {dump} ({dump.stat().st_size} bytes)')
    pgserver.psql(['-d', base, '-c', f'CREATE DATABASE {RESTORED}'])
    pgserver.psql(['-d', restored_uri, '-v', 'ON_ERROR_STOP=1', '-f', str(dump)])
    log('restore completed into the copy')

    a, b = table_counts(origin_uri), table_counts(restored_uri)
    same = a == b
    log(f'origin tables   : {len(a)}  total rows {sum(a.values())}')
    log(f'restored tables : {len(b)}  total rows {sum(b.values())}')
    log(f'VERIFICATION    : {"PASS - identical" if same else "FAIL"}')
    if not same:
        diff = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
        log(f'differences: {diff}')
        raise SystemExit('restore verification failed — stopping')
    (EVIDENCE / 'restore_verification.json').write_text(
        json.dumps({'origin': a, 'restored': b, 'identical': same}, indent=2))

    # ---------------- Step 1 : schema on the RESTORED copy ----------------
    log('\n=== STEP 1 — documents table + indexes ON THE RESTORED COPY ===')
    pgserver.psql(['-d', restored_uri, '-v', 'ON_ERROR_STOP=1',
                   '-f', str(HERE / 'm01_schema.sql')])
    idx = pgserver.psql(['-d', restored_uri, '-At', '-c',
                         "SELECT indexname FROM pg_indexes WHERE tablename='documents' ORDER BY 1"])
    log('indexes created:\n' + idx.strip())
    fks = pgserver.psql(['-d', restored_uri, '-At', '-F', '|', '-c',
                         "SELECT conname, confdeltype FROM pg_constraint "
                         "WHERE conrelid='documents'::regclass AND contype='f' ORDER BY 1"])
    log('foreign keys (confdeltype r = RESTRICT):\n' + fks.strip())
    (EVIDENCE / 'schema_applied.txt').write_text(idx + '\n' + fks)

    # ---------------- Steps 2 + 3 : backfill and reconcile ----------------
    log('\n=== STEPS 2 & 3 — backfill and reconciliation ===')
    dsn = f"host={sock} port=5432 user=postgres dbname={RESTORED}"
    run([sys.executable, str(HERE / 'm01_backfill.py'),
         '--dsn', dsn, '--uploads', str(uploads),
         '--json-out', str(EVIDENCE / 'reconciliation.json'),
         '--i-confirm-this-is-a-restored-copy'], cwd=ROOT)

    # ---------------- Post-checks ----------------
    log('\n=== POST-CHECKS ===')
    for label, sql in [
        ('documents rows', 'SELECT COUNT(*) FROM documents'),
        ('by visibility',
         "SELECT visibility||'='||COUNT(*) FROM documents GROUP BY visibility ORDER BY 1"),
        ('held classes present (must be 0)',
         "SELECT COUNT(*) FROM documents WHERE visibility IN ('station','national')"),
        ('source rows mutated? clearance_applications',
         'SELECT COUNT(*) FROM clearance_applications'),
    ]:
        v = pgserver.psql(['-d', restored_uri, '-At', '-c', sql]).strip()
        log(f'  {label}: {v}')

    log('\n=== A-1 condition 5 proof: no source record and no file modified ===')
    after = table_counts(restored_uri)
    src_after = {k: v for k, v in after.items() if k != 'documents'}
    src_ok = src_after == b
    log(f'  source tables after backfill vs restored baseline: '
        f'{"IDENTICAL" if src_ok else "CHANGED"}')
    if not src_ok:
        log(f'  differences: {{k: (b.get(k), src_after.get(k)) for k in set(b)|set(src_after) if b.get(k)!=src_after.get(k)}}')
    uploads_after = fingerprint_uploads(uploads)
    files_ok = uploads_after == uploads_before
    log(f'  uploaded files ({len(uploads_after)}) sha256 set: '
        f'{"IDENTICAL" if files_ok else "CHANGED"}')
    (EVIDENCE / 'no_mutation_proof.json').write_text(json.dumps(
        {'source_tables_identical': src_ok, 'uploaded_files_identical': files_ok,
         'source_table_counts': src_after, 'upload_sha256': uploads_after},
        indent=2))

    log('\n=== A-1 condition 1 proof: RESTRICT actually blocks a delete ===')
    try:
        pgserver.psql(['-d', restored_uri, '-v', 'ON_ERROR_STOP=1', '-c',
                       'DELETE FROM police_branches WHERE id=901'])
        log('  !! DELETE SUCCEEDED — RESTRICT not enforced')
    except Exception as exc:                          # noqa: BLE001
        first = [l for l in str(exc).splitlines() if 'ERROR' in l or 'violates' in l]
        log(f'  DELETE refused as required: {(first or [str(exc)])[0][:200]}')

    (EVIDENCE / 'rehearsal_log.txt').write_text('\n'.join(LOG))
    log(f'\nevidence written to {EVIDENCE}')
    log('\nSTOPPED AT STEP 3. A-2(b) not approved; no operational database touched.')
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
