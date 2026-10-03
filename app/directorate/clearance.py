"""Fingerprint clearance — ported from legacy POST /api/clearance-applications and .../approve (backend/server.py ~l.5388).

Legacy                                              Unified (decision T1)
--------------------------------------------------  ------------------------------------------------------------
any fingerprint-module user files AND approves      FILING is local: any unit where the user holds clearance:create
 (`ensure_person`, free-text guardian)               (a station, a checkpoint, a regional bureau ...), through the
                                                     Central Person Registry; the guardian is a person, too.
                                                    DECISION + SIGNING + PRINTING are national: clearance:approve /
                                                     clearance:print at the OWNING directorate. An intake unit's
                                                     scope grants no approval right — by construction (RLS on owner).
12 h review lock in two handlers + a boot self-test  policy `clearance.review_window_hours`, enforced by the database
 (admin bypasses by role NAME)                       trigger; the bypass is the PERMISSION clearance:override_review_lock.
'CL-'+epoch ms certificate number                    next_ref('CL', directorate) + an Ed25519 signature over the
 (no signature; anyone could print)                  canonical certificate payload; public verification endpoint.
no reject, no print log                             reject (with reason); every print is logged.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity import registry
from ..identity.errors import (Duplicate, NeedsConfirmation, NotFound, PermissionDenied, ReviewLocked,
                               ValidationError)
from ..operations import common as C
from . import signing

PERSON_KEYS = registry.PROFILE_FIELDS


def _person_data(d: Optional[Dict]) -> Dict:
    return {k: d[k] for k in PERSON_KEYS if d and d.get(k) not in (None, '')}


def review_state(created_at: datetime, hours: float, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now(timezone.utc)
    eligible = created_at + timedelta(hours=float(hours))
    remaining = max(0.0, (eligible - now).total_seconds() / 3600.0)
    return {'review_window_hours': float(hours), 'submitted_at': created_at, 'review_eligible_at': eligible,
            'hours_elapsed': round(max(0.0, (now - created_at).total_seconds() / 3600.0), 2),
            'hours_remaining': round(remaining, 2), 'review_locked': remaining > 0}


def _window(cur) -> float:
    v = C.policy(cur, 'clearance.review_window_hours', 12)
    return float(v)


def _ref(cur, unit_code: str) -> str:
    cur.execute("SELECT next_ref('FP', %s) AS ref", (unit_code,))
    return cur.fetchone()['ref']


# =============================================================================================
def file_application(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = C.resolve_unit(cur, actor, data.get('unit'), 'clearance:create', None, 'intake unit', scope='state')
    act = C.at_unit(actor, unit)
    req = C.policy(cur, 'clearance.required', {})
    purposes = C.policy(cur, 'clearance.purposes', [])
    applicant = _person_data(data.get('applicant'))
    guardian_in = _person_data(data.get('guardian'))
    guardian_rel = C.text(data, 'guardian_relationship')
    problems: List[Dict] = []

    def need(ok, field, message):
        if not ok:
            problems.append({'field': field, 'message': message})

    purpose = None
    try:
        purpose = C.choice(data.get('purpose'), purposes, 'Clearance reason', 'purpose', required=True)
    except ValidationError as e:
        problems.append({'field': 'purpose', 'message': e.message})
    try:
        dob = registry._parse_dob(applicant.get('date_of_birth'), required=False)
    except ValidationError as e:
        dob = None
        problems.append({'field': 'date_of_birth', 'message': e.message})
    photo = (data.get('applicant_photo') or '').strip()
    docs = [d for d in (data.get('applicant_docs') or []) if str(d or '').strip()]
    gdocs = [d for d in (data.get('guardian_docs') or []) if str(d or '').strip()]
    need(photo or not req.get('photo', True), 'applicant_photo', 'Applicant photo is required')
    n_docs = int(req.get('applicant_docs', 2))
    need(len(docs) >= n_docs, 'applicant_docs', f'At least {n_docs} applicant documents are required')

    mode = req.get('guardian', 'all')
    age = registry._age(dob)
    guardian_needed = mode == 'all' or (mode == 'minors' and age is not None and age < 18)
    if guardian_needed or guardian_in:
        n_g = int(req.get('guardian_docs', 2))
        need(guardian_in, 'guardian', 'Guardian full name is required')
        need(guardian_rel, 'guardian_relationship', 'Guardian relationship is required')
        need(len(gdocs) >= n_g, 'guardian_docs', f'At least {n_g} guardian documents are required')
    if problems:
        raise ValidationError(' · '.join(p['message'] for p in problems), fields=[p['field'] for p in problems],
                              problems=problems)
    photo = C.check_uploads(cur, actor, [photo], 'applicant_photo', 'Applicant photo', images_only=True)[0] if photo else None
    docs = C.check_uploads(cur, actor, docs, 'applicant_docs', 'Applicant document')
    gdocs = C.check_uploads(cur, actor, gdocs, 'guardian_docs', 'Guardian document')

    person_in = dict(applicant)
    if photo:
        person_in['photo_path'] = photo
    try:
        reg = registry.register(conn, act, person_in, confirm_new=bool(data.get('confirm_new')),
                                link_person_ref=data.get('link_person_ref'))      # legacy: ID or passport required
    except NeedsConfirmation as e:
        e.extra['scope'] = 'applicant'
        raise
    ref = reg['person']['person_ref']
    pid = C.person_id(cur, ref)

    guardian_out = None
    if guardian_needed or guardian_in:
        try:
            g = registry.add_guardian(conn, act, ref, guardian_in, relationship=guardian_rel,
                                      guardian_person_ref=data.get('guardian_person_ref'),
                                      confirm_new=bool(data.get('guardian_confirm_new')))
        except NeedsConfirmation as e:
            e.extra['scope'] = 'guardian'
            raise
        guardian_out = {'person_ref': g['guardian']['person_ref'], 'full_name': g['guardian']['full_name'],
                        'relationship': guardian_rel, 'created': g['guardian_created']}

    details = {'applicant_photo': photo, 'applicant_docs': docs, 'guardian_docs': gdocs,
               'sex': C.text(data, 'sex'), 'email': C.text(data, 'email'),
               'legal_document_ref': C.text(data, 'legal_document_ref'), 'notes': C.text(data, 'notes')}
    if guardian_out:
        details['guardian'] = {**guardian_out, 'phone': C.text(guardian_in, 'phone'),
                               'address': C.text(guardian_in, 'residence'), 'occupation': C.text(guardian_in, 'occupation')}
    app_ref = _ref(cur, unit['code'])
    try:
        cur.execute('SAVEPOINT ins_clr')
        cur.execute("""INSERT INTO clearance_applications (application_ref, person_id, intake_unit_id, purpose, details)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at, owner_unit_id""",
                    (app_ref, pid, unit['id'], purpose, psycopg2.extras.Json(details)))
        row = cur.fetchone()
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_clr')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'CLEARANCE_FILE', 'clearance_application', app_ref,
            {'person': ref, 'purpose': purpose, 'person_created': reg['created'],
             'guardian': guardian_out and guardian_out['person_ref']})
    state = review_state(row['created_at'], _window(cur))
    return {'application': {'application_ref': app_ref, 'status': 'Pending Review', 'purpose': purpose,
                            'intake_unit': {'code': unit['code'], 'name': unit['name'], 'region': unit['region']},
                            'created_at': row['created_at'], **state},
            'person': reg['person'], 'guardian': guardian_out,
            'identity': {'created': reg['created'], 'exists': reg['exists'], 'filled': reg['filled'],
                         'updated': reg['updated'], 'ignored': reg['ignored'], 'match': reg['match']}}


# =============================================================================================
_LIST_SQL = """
    SELECT a.application_ref, a.status, a.purpose, a.created_at, a.reviewed_at, a.certificate_number,
           iu.code AS intake_code, iu.name AS intake_name, ou.code AS owner_code, ou.name AS owner_name,
           p.person_ref, p.full_name, p.national_id, p.passport_id, p.phone,
           authz_can(%(u)s, 'clearance:approve', a.owner_unit_id)             AS can_approve,
           authz_can(%(u)s, 'clearance:override_review_lock', a.owner_unit_id) AS can_override,
           authz_can(%(u)s, 'clearance:print',   a.owner_unit_id)             AS can_print
      FROM clearance_applications a
      JOIN org_units iu ON iu.id = a.intake_unit_id
      JOIN org_units ou ON ou.id = a.owner_unit_id
      JOIN persons p ON p.id = a.person_id
     WHERE (authz_can(%(u)s, 'clearance:view', a.intake_unit_id) OR authz_can(%(u)s, 'clearance:view', a.owner_unit_id))
"""


def _decorate(cur, row: Dict) -> Dict:
    row = dict(row)
    row.update(review_state(row['created_at'], _window(cur)))
    pending = row['status'] == 'Pending Review'
    row['can_decide'] = bool(pending and row['can_approve'] and (not row['review_locked'] or row['can_override']))
    row['can_print'] = bool(row['can_print'] and row['status'] == 'Approved')
    return row


def list_applications(conn, actor: db.Actor, status: Optional[str] = None, unit: Optional[str] = None,
                      person_ref: Optional[str] = None, limit: int = 50) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute(_LIST_SQL + """ AND (%(status)s::text IS NULL OR a.status = %(status)s)
                               AND (%(unit)s::text IS NULL OR iu.code = %(unit)s OR ou.code = %(unit)s)
                               AND (%(ref)s::text IS NULL OR p.person_ref = %(ref)s)
                             ORDER BY a.created_at DESC, a.id DESC LIMIT %(n)s""",
                {'u': actor.user_id, 'status': status or None, 'unit': unit or None, 'ref': person_ref or None,
                 'n': max(1, min(200, limit))})
    rows = [_decorate(cur, r) for r in cur.fetchall()]
    return {'items': rows, 'review_window_hours': _window(cur)}


def _load(cur, actor: db.Actor, ref: str, lock=False) -> Dict:
    cur.execute(_LIST_SQL + ' AND a.application_ref = %(ref)s', {'u': actor.user_id, 'ref': ref})
    row = cur.fetchone()
    if not row:
        raise NotFound('Application not found')
    if lock:
        cur.execute('SELECT 1 FROM clearance_applications WHERE application_ref = %s FOR UPDATE', (ref,))
    return row


def get_application(conn, actor: db.Actor, ref: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    row = _decorate(cur, _load(cur, actor, ref))
    cur.execute("""SELECT a.details, a.reviewed_by, a.review_notes, a.signing_key_id,
                          p.date_of_birth, p.place_of_birth, p.mother_name, p.residence, p.occupation, p.photo_path,
                          ru.display_name AS reviewed_by_name, cu.display_name AS filed_by_name
                     FROM clearance_applications a JOIN persons p ON p.id = a.person_id
                     LEFT JOIN users ru ON ru.id = a.reviewed_by LEFT JOIN users cu ON cu.id = a.created_by
                    WHERE a.application_ref = %s""", (ref,))
    row.update(cur.fetchone())
    return row


def decide(conn, actor: db.Actor, ref: str, decision: str, notes: Optional[str] = None) -> Dict:
    """Approve (and sign) or reject.  National: needs clearance:approve at the OWNING directorate."""
    decision = (decision or '').strip().lower()
    if decision not in ('approve', 'reject'):
        raise ValidationError('decision must be "approve" or "reject"', fields=['decision'])
    cur = C.new_cursor(conn, actor)
    row = _load(cur, actor, ref, lock=True)
    if not row['can_approve']:
        raise PermissionDenied('Approval, signing and printing are national: only the Fingerprint directorate may '
                               'decide clearance applications (an intake unit cannot).')
    if row['status'] != 'Pending Review':
        raise Duplicate(f'Application {ref} was already decided ({row["status"]}); decisions are final.')
    state = review_state(row['created_at'], _window(cur))
    bypassed = bool(state['review_locked'] and row['can_override'])
    if state['review_locked'] and not row['can_override']:
        raise ReviewLocked('Review period active. Standard officers must wait '
                           f'{state["review_window_hours"]:g} hours before approving.',
                           application_ref=ref, reason='review window open', **{k: state[k] for k in (
                               'review_window_hours', 'hours_elapsed', 'hours_remaining')},
                           review_eligible_at=state['review_eligible_at'].strftime('%Y-%m-%dT%H:%M:%SZ'))
    cur.execute('SELECT id, code, name FROM org_units WHERE code = %s', (row['owner_code'],))
    owner = cur.fetchone()
    cur.execute('SELECT id FROM clearance_applications WHERE application_ref = %s', (ref,))
    app_id = cur.fetchone()['id']
    notes = C.text({'n': notes}, 'n') or None
    try:
        cur.execute('SAVEPOINT decide')
        if decision == 'reject':
            if not notes:
                raise ValidationError('A rejection needs a reason', fields=['notes'])
            cur.execute("UPDATE clearance_applications SET status = 'Rejected', review_notes = %s "
                        "WHERE id = %s RETURNING reviewed_at", (notes, app_id))
            out = {'application_ref': ref, 'status': 'Rejected', 'reviewed_at': cur.fetchone()['reviewed_at'],
                   'review_notes': notes}
            cert = None
        else:
            priv, key_id = signing.active_key(cur)
            cur.execute("SELECT next_ref('CL', %s) AS n, now() AS issued_at", (owner['code'],))
            r = cur.fetchone()
            cur.execute("""SELECT p.person_ref, p.full_name, p.date_of_birth, p.national_id, a.purpose
                             FROM clearance_applications a JOIN persons p ON p.id = a.person_id WHERE a.id = %s""", (app_id,))
            p = cur.fetchone()
            payload = {'v': 1, 'certificate_number': r['n'], 'application_ref': ref, 'person_ref': p['person_ref'],
                       'holder': p['full_name'], 'date_of_birth': p['date_of_birth'].isoformat() if p['date_of_birth'] else None,
                       'national_id': p['national_id'], 'purpose': p['purpose'], 'issuer': owner['code'],
                       'issuer_name': owner['name'], 'issued_at': r['issued_at'].astimezone(timezone.utc).isoformat(),
                       'key_id': key_id}
            sig = signing.sign(priv, payload)
            cur.execute("""UPDATE clearance_applications SET status = 'Approved', certificate_number = %s,
                                  certificate_signature = %s, signing_key_id = %s, certificate_snapshot = %s, review_notes = %s
                            WHERE id = %s RETURNING reviewed_at""",
                        (r['n'], sig, key_id, psycopg2.extras.Json(payload), notes, app_id))
            out = {'application_ref': ref, 'status': 'Approved', 'certificate_number': r['n'],
                   'reviewed_at': cur.fetchone()['reviewed_at'], 'signing_key_id': key_id}
            cert = payload
    except pgerr.InsufficientPrivilege as e:
        cur.execute('ROLLBACK TO SAVEPOINT decide')
        C.translate_db_error(e)
    except (pgerr.CheckViolation, pgerr.ObjectNotInPrerequisiteState) as e:
        cur.execute('ROLLBACK TO SAVEPOINT decide')
        C.translate_db_error(e)
    C.audit(cur, actor, owner, 'CLEARANCE_APPROVE' if decision == 'approve' else 'CLEARANCE_REJECT',
            'clearance_application', ref, {'certificate': out.get('certificate_number'), 'review_period_bypassed': bypassed,
                                          'intake': row['intake_code']})
    return {**out, 'review_period_bypassed': bypassed, 'review_window_hours': state['review_window_hours'],
            'certificate': cert}


def certificate(conn, actor: db.Actor, ref: str, log_print: bool = True) -> Dict:
    """The signed certificate for printing.  National: clearance:print at the owner.  Every call is logged."""
    cur = C.new_cursor(conn, actor)
    row = _load(cur, actor, ref)
    if not row['can_print']:
        raise PermissionDenied('Printing certificates is restricted to the national Fingerprint directorate')
    if row['status'] != 'Approved':
        raise ValidationError(f'Application {ref} is {row["status"]}; only an approved application has a certificate')
    cur.execute("""SELECT a.id, a.owner_unit_id, a.certificate_number, a.certificate_signature, a.signing_key_id,
                          a.certificate_snapshot FROM clearance_applications a WHERE a.application_ref = %s""", (ref,))
    a = cur.fetchone()
    if log_print:
        try:
            cur.execute('INSERT INTO clearance_prints (application_id, owner_unit_id, printed_by) VALUES (%s, %s, %s)',
                        (a['id'], a['owner_unit_id'], actor.user_id))
        except pgerr.InsufficientPrivilege as e:
            C.translate_db_error(e)
        cur.execute('SELECT id FROM org_units WHERE id = %s', (a['owner_unit_id'],))
        C.audit(cur, actor, cur.fetchone(), 'CLEARANCE_PRINT', 'clearance_application', ref, {'certificate': a['certificate_number']})
    cur.execute('SELECT count(*) AS n FROM clearance_prints WHERE application_id = %s', (a['id'],))
    return {'certificate': a['certificate_snapshot'], 'signature': a['certificate_signature'], 'key_id': a['signing_key_id'],
            'certificate_number': a['certificate_number'], 'print_count': cur.fetchone()['n'],
            'verify_path': '/api/verify/' + a['certificate_number']}


def _mask(name: str) -> str:
    parts = (name or '').split()
    return ' '.join([parts[0]] + [p[0] + '.' for p in parts[1:]]) if parts else ''


def verify_public(conn, number: str) -> Dict:
    """PUBLIC (no login).  Minimal output: validity, purpose, issue date and a masked holder name."""
    cur = db.cursor(conn)
    db.bind_anonymous(cur)
    cur.execute('SELECT * FROM certificate_for_verification(%s)', (number,))
    r = cur.fetchone()
    if not r or r['status'] != 'Approved' or not r['snapshot'] or not r['signature']:
        return {'valid': False, 'certificate_number': number, 'reason': 'No approved certificate has this number'}
    snap = r['snapshot']
    ok = (snap.get('certificate_number') == r['certificate_number'] and snap.get('application_ref') == r['application_ref']
          and snap.get('key_id') == r['key_id'] and bool(r['public_key'])
          and signing.verify(snap, r['signature'], r['public_key']))
    out = {'valid': bool(ok), 'certificate_number': number}
    if not ok:
        out['reason'] = 'The signature does not match — this certificate was altered or is forged'
        return out
    out.update({'holder': _mask(snap.get('holder')), 'purpose': snap.get('purpose'), 'issued_at': snap.get('issued_at'),
                'issuer': snap.get('issuer_name'), 'key_id': r['key_id'], 'key_status': r['key_status']})
    if r['key_status'] != 'active':
        out['notice'] = 'Signed with a retired key (still cryptographically valid)'
    return out
