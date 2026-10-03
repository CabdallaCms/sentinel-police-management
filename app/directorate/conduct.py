"""HR — conduct / disciplinary files.  Ported from legacy submit_conduct_action / review_conduct_action
(backend/server.py l.2555–2700, routes /api/conduct, /submit, /review).

Legacy                                          Unified (decision T2)
----------------------------------------------  ---------------------------------------------------------------
any HR/admin user files for any officer         FILING is local: the filer needs conduct:submit at the unit and may
                                                file only against officers posted at that unit or BELOW it; the DB
                                                records the filing unit and rejects a unit that is not above the officer.
rank changes applied by hand-written code        approving applies rank / duty effects ATOMICALLY in the DB trigger and
                                                writes an immutable service-history row.
reviewer could be the filer                      separation of duties in the DB: the filer can never review the file.
status strings in code                           policy data: conduct.classifications / statuses / rank_direction.
HR review                                        NATIONAL: conduct:review at the HR directorate.
"""
from typing import Dict, List, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity.errors import Duplicate, NotFound, PermissionDenied, ValidationError
from ..operations import common as C


def vocabularies(cur) -> Dict:
    return {'classifications': C.policy(cur, 'conduct.classifications', {}), 'statuses': C.policy(cur, 'conduct.statuses', {}),
            'rank_direction': C.policy(cur, 'conduct.rank_direction', {}), 'duty_effects': C.policy(cur, 'conduct.duty_effects', {}),
            'ranks': C.policy(cur, 'officer.ranks', []), 'min_narrative_chars': C.policy(cur, 'conduct.min_narrative_chars', 20)}


def submit(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    oref = C.text(data, 'officer')
    if not oref:
        raise ValidationError('Choose the officer this file is about', fields=['officer'])
    cur.execute("""SELECT o.id, o.service_ref, o.full_name, o.rank, o.duty_status, o.unit_id, u.code AS unit_code
                     FROM officers o JOIN org_units u ON u.id = o.unit_id WHERE o.service_ref = %s""", (oref,))
    off = cur.fetchone()
    if not off:
        raise NotFound(f'Officer {oref} was not found in your jurisdiction. Conduct files can only be filed against '
                       'officers posted at your unit or below it.')
    # the unit the filer acts for: default = the officer's own unit; it must be at or above the officer (DB re-checks)
    unit = C.resolve_unit(cur, actor, data.get('unit') or off['unit_code'], 'conduct:submit', None, 'filing unit', scope='state')
    cur.execute('SELECT 1 FROM org_unit_closure WHERE ancestor_id = %s AND descendant_id = %s', (unit['id'], off['unit_id']))
    if not cur.fetchone():
        raise ValidationError(f'{unit["name"]} is not the officer\'s unit or above it; file from a unit that commands '
                              f'{off["full_name"]}', fields=['unit'])
    voc = C.policy(cur, 'conduct.classifications', {})
    atype = C.choice(data.get('action_type'), list(voc), 'Action type', 'action_type', required=True)
    cls = C.choice(data.get('classification'), voc[atype], 'Classification', 'classification', required=True)
    narrative = C.text(data, 'narrative')
    minlen = int(C.policy(cur, 'conduct.min_narrative_chars', 20))
    if len(narrative) < minlen:
        raise ValidationError(f'The narrative must be a detailed justification (at least {minlen} characters)', fields=['narrative'])
    proposed = C.choice(data.get('proposed_rank'), C.policy(cur, 'officer.ranks', []), 'Proposed rank', 'proposed_rank')
    cur.execute("SELECT conduct_rank_ok(%s, %s, %s) AS problem", (off['rank'], proposed, cls))
    problem = cur.fetchone()['problem']
    if problem:
        raise ValidationError(problem, fields=['proposed_rank'])
    docs = C.check_uploads(cur, actor, data.get('documents') or [], 'documents', 'Supporting document')
    cur.execute("SELECT next_ref('ACT') AS ref")
    ref = cur.fetchone()['ref']
    try:
        cur.execute('SAVEPOINT ins_cond')
        cur.execute("""INSERT INTO conduct_actions (action_ref, officer_id, officer_unit_id, action_type, classification, proposed_rank,
                                                     narrative, submitted_by, submitted_unit_id, documents)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING status, submitted_at""",
                    (ref, off['id'], off['unit_id'], atype, cls, proposed if proposed and cls in
                     C.policy(cur, 'conduct.rank_direction', {}) else None, narrative, actor.user_id, unit['id'],
                     psycopg2.extras.Json(docs)))
        row = cur.fetchone()
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_cond')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'CONDUCT_SUBMIT', 'conduct_action', ref,
            {'officer': oref, 'type': atype, 'classification': cls, 'officer_unit': off['unit_code']})
    return {'conduct': {'action_ref': ref, 'status': row['status'], 'officer': oref, 'officer_name': off['full_name'],
                        'action_type': atype, 'classification': cls, 'proposed_rank': proposed,
                        'filed_for_unit': unit['code'], 'submitted_at': row['submitted_at']}}


_SQL = """SELECT a.action_ref, a.status, a.action_type, a.classification, a.proposed_rank, a.narrative, a.documents,
                 a.submitted_at, a.reviewed_at, a.reviewer_notes, a.rank_applied, a.duty_applied,
                 o.service_ref AS officer_ref, o.full_name AS officer_name, o.rank AS officer_rank, o.duty_status AS officer_duty_status,
                 ou.code AS officer_unit, fu.code AS filed_for_unit, su.display_name AS submitted_by_name,
                 ru.display_name AS reviewed_by_name,
                 (a.status NOT IN (%(approved)s, %(rejected)s) AND authz_can(%(u)s, 'conduct:review', a.owner_unit_id)
                  AND a.submitted_by <> %(u)s) AS can_review
            FROM conduct_actions a JOIN officers o ON o.id = a.officer_id JOIN org_units ou ON ou.id = a.officer_unit_id
            LEFT JOIN org_units fu ON fu.id = a.submitted_unit_id LEFT JOIN users su ON su.id = a.submitted_by
            LEFT JOIN users ru ON ru.id = a.reviewed_by"""


def _args(cur, actor, **kw):
    st = C.policy(cur, 'conduct.statuses', {})
    return {'u': actor.user_id, 'approved': st.get('approved'), 'rejected': st.get('rejected'), **kw}


def list_conduct(conn, actor: db.Actor, status: Optional[str] = None, officer: Optional[str] = None, limit: int = 100) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute(_SQL + """ WHERE (%(s)s::text IS NULL OR a.status = %(s)s) AND (%(o)s::text IS NULL OR o.service_ref = %(o)s)
                           ORDER BY a.submitted_at DESC, a.id DESC LIMIT %(n)s""",
                _args(cur, actor, s=status or None, o=officer or None, n=max(1, min(500, limit))))
    return {'items': cur.fetchall(), 'vocabularies': vocabularies(cur)}


def get_conduct(conn, actor: db.Actor, ref: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute(_SQL + ' WHERE a.action_ref = %(r)s', _args(cur, actor, r=ref))
    row = cur.fetchone()
    if not row:
        raise NotFound('Conduct file not found (or outside your scope)')
    return row


def review(conn, actor: db.Actor, ref: str, decision: str, notes: Optional[str] = None) -> Dict:
    """decision: 'review' (take it up), 'approve' or 'reject'.  National: conduct:review at the HR directorate."""
    cur = C.new_cursor(conn, actor)
    st = C.policy(cur, 'conduct.statuses', {})
    target = {'review': st.get('reviewing'), 'approve': st.get('approved'), 'reject': st.get('rejected')}.get((decision or '').strip().lower())
    if not target:
        raise ValidationError('decision must be "review", "approve" or "reject"', fields=['decision'])
    cur.execute("""SELECT a.id, a.status, a.submitted_by, a.owner_unit_id, a.officer_id,
                          authz_can(%s, 'conduct:review', a.owner_unit_id) AS can
                     FROM conduct_actions a WHERE a.action_ref = %s""", (actor.user_id, ref))
    a = cur.fetchone()
    if not a:
        raise NotFound('Conduct file not found (or outside your scope)')
    if not a['can']:
        raise PermissionDenied('Conduct review is national: only the HR directorate may review conduct files')
    cur.execute('SELECT status FROM conduct_actions WHERE id = %s FOR UPDATE', (a['id'],))
    a['status'] = cur.fetchone()['status']
    if a['status'] in (st['approved'], st['rejected']):
        raise Duplicate(f'Conduct file {ref} is closed ({a["status"]})')
    notes = C.text({'n': notes}, 'n') or None
    if target == st['rejected'] and not notes:
        raise ValidationError('A rejection needs reviewer notes', fields=['notes'])
    try:
        cur.execute('SAVEPOINT rev')
        cur.execute('UPDATE conduct_actions SET status = %s, reviewer_notes = COALESCE(%s, reviewer_notes) WHERE id = %s '
                    'RETURNING reviewed_at, rank_applied, duty_applied', (target, notes, a['id']))
        r = cur.fetchone()
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT rev')
        C.translate_db_error(e)
    cur.execute('SELECT service_ref, rank, duty_status FROM officers WHERE id = %s', (a['officer_id'],))
    off = cur.fetchone()
    C.audit(cur, actor, {'id': a['owner_unit_id']}, 'CONDUCT_' + decision.strip().upper(), 'conduct_action', ref,
            {'status': target, 'rank_applied': r['rank_applied'], 'duty_applied': r['duty_applied']})
    return {'action_ref': ref, 'status': target, 'reviewed_at': r['reviewed_at'], 'rank_applied': r['rank_applied'],
            'duty_applied': r['duty_applied'], 'officer': off}
