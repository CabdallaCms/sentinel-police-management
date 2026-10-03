"""Configuration-driven structure: units, bureaus, branches and role assignments are DATA.

There is no hardcoded list of stations, bureaus or branches anywhere in the code.  These are the admin actions
that write that data (the same rows a SQL `INSERT` would write — the database triggers validate both identically):

  * unit_types / unit_type_rules   which kinds of unit may sit under which (rows)
  * org_units                      a new bureau under a directorate, a new station under a district, an airport ...
  * user_assignments               who holds which role where  (grant bounded by can_grant: no privilege escalation)

The boundaries are enforced by the database, not by this module:
  - a `region` unit must be one of the state's regions (policy operations.regions; checked here AND inert otherwise,
    because every record trigger refuses units outside those regions),
  - a bureau may claim a region (attrs.region) only from that same list,
  - parent/type pairs follow unit_type_rules; the tree, closure table and paths are maintained by triggers.
"""
from typing import Dict, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity.errors import Duplicate, NotFound, PermissionDenied, ValidationError
from ..operations import common as C

_UNIT_SQL = """SELECT o.code, o.name, o.name_local, o.unit_type, o.status, o.service_key, o.attrs, o.depth,
                      p.code AS parent_code, unit_region_name(o.id) AS region,
                      unit_claimed_region(o.id) AS region_code, unit_in_state(o.id) AS in_state,
                      authz_can(%(u)s, 'unit:manage', o.id) AS can_manage,
                      authz_can(%(u)s, 'assignment:manage', o.id) AS can_assign
                 FROM org_units o LEFT JOIN org_units p ON p.id = o.parent_id"""


def _unit(cur, code: str) -> Dict:
    cur.execute('SELECT id, code, name, unit_type, parent_id FROM org_units WHERE code = %s', ((code or '').strip(),))
    u = cur.fetchone()
    if not u:
        raise NotFound(f'Unknown unit "{code}"')
    return u


def _need(cur, actor: db.Actor, perm: str, unit: Dict, what: str):
    cur.execute('SELECT authz_can(%s, %s, %s) AS ok', (actor.user_id, perm, unit['id']))
    if not cur.fetchone()['ok']:
        raise PermissionDenied(f'You may not {what} at {unit["name"]} ({unit["code"]})')


def vocabularies(conn, actor: db.Actor) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute('SELECT code, label, is_geographic FROM unit_types ORDER BY sort_order')
    types = cur.fetchall()
    cur.execute('SELECT parent_type, child_type FROM unit_type_rules ORDER BY 1, 2')
    rules = cur.fetchall()
    cur.execute("SELECT code, name FROM roles WHERE code <> 'system_admin' ORDER BY name")
    roles = cur.fetchall()
    return {'unit_types': types, 'unit_type_rules': rules, 'roles': roles,
            'regions': C.policy(cur, 'operations.regions', []),
            'case_statuses': C.policy(cur, 'case.statuses', []), 'participant_roles': C.policy(cur, 'case.participant_roles', []),
            'evidence_types': C.policy(cur, 'case.evidence_types', []),
            'clearance_purposes': C.policy(cur, 'clearance.purposes', []),
            'clearance_required': C.policy(cur, 'clearance.required', {}),
            'review_window_hours': C.policy(cur, 'clearance.review_window_hours', 12),
            'officer': {k: C.policy(cur, 'officer.' + k, []) for k in ('ranks', 'duty_statuses', 'divisions', 'blood_groups',
                                                                       'guarantor_relationships', 'doc_types_primary', 'doc_types_secondary')},
            'conduct': {'classifications': C.policy(cur, 'conduct.classifications', {}),
                        'rank_direction': C.policy(cur, 'conduct.rank_direction', {}),
                        'statuses': C.policy(cur, 'conduct.statuses', {}),
                        'min_narrative_chars': C.policy(cur, 'conduct.min_narrative_chars', 20)}}


def directorate_units(conn, actor: db.Actor, kind: Optional[str] = None) -> Dict:
    """Unit pickers for the Directorate page — read from the tree, never hardcoded:
    items = directorates and their bureaus; filing = where THIS user may file each kind of record."""
    cur = C.new_cursor(conn, actor)
    cur.execute(_UNIT_SQL + """ WHERE o.unit_type IN ('directorate', 'bureau') AND o.status = 'active'
                                 ORDER BY o.depth, o.name""", {'u': actor.user_id})
    items = cur.fetchall()
    filing = {}
    for key, perm, extra in (('clearance', 'clearance:create', ''), ('conduct', 'conduct:submit', ''),
                             ('cid', 'case:create', " AND o.id IN (SELECT descendant_id FROM org_unit_closure WHERE ancestor_id = service_unit('cid'))"),
                             ('alert', 'alert:create', " AND o.id IN (SELECT descendant_id FROM org_unit_closure WHERE ancestor_id = service_unit('cid'))")):
        cur.execute(f"""SELECT o.code, o.name, o.unit_type, unit_region_name(o.id) AS region
                         FROM org_units o WHERE o.status = 'active' AND unit_in_state(o.id)
                          AND o.id IN (SELECT authz_scope(%s, %s)) {extra} ORDER BY o.depth, o.name""", (actor.user_id, perm))
        filing[key] = cur.fetchall()
    cur.execute("""SELECT o.code, o.name, o.unit_type, unit_region_name(o.id) AS region FROM org_units o
                    WHERE o.status = 'active' AND unit_in_state(o.id) AND o.unit_type <> 'hq'
                      AND authz_can(%s, 'officer:create', service_unit('hr')) ORDER BY o.path""", (actor.user_id,))
    filing['posting'] = cur.fetchall()
    return {'items': items, 'filing': filing}


def list_units(conn, actor: db.Actor, parent: Optional[str] = None) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute(_UNIT_SQL + """ WHERE (authz_can(%(u)s, 'unit:view', o.id) OR authz_can(%(u)s, 'unit:manage', o.id))
                                   AND (%(p)s::text IS NULL OR p.code = %(p)s)
                                 ORDER BY o.path""", {'u': actor.user_id, 'p': parent or None})
    return {'items': cur.fetchall()}


def create_unit(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    parent = _unit(cur, C.text(data, 'parent'))
    _need(cur, actor, 'unit:manage', parent, 'create units')
    code, name, utype = C.text(data, 'code').upper(), C.text(data, 'name'), C.text(data, 'unit_type')
    problems = [f for f, v in (('code', code), ('name', name), ('unit_type', utype)) if not v]
    if problems:
        raise ValidationError('code, name and unit_type are required', fields=problems)
    status = C.choice(data.get('status'), ['planned', 'active', 'inactive'], 'Status', 'status') or 'active'
    attrs = data.get('attrs') or {}
    if not isinstance(attrs, dict):
        raise ValidationError('attrs must be an object', fields=['attrs'])
    if utype == 'region' and code not in C.policy(cur, 'operations.regions', []):
        raise ValidationError(f'{code} is not one of the state regions (policy operations.regions); a new region needs a '
                              'policy decision first', fields=['unit_type'])
    try:
        cur.execute('SAVEPOINT ins_unit')
        cur.execute("""INSERT INTO org_units (parent_id, unit_type, code, name, name_local, status, attrs)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (parent['id'], utype, code, name, C.text(data, 'name_local') or None, status, psycopg2.extras.Json(attrs)))
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT ins_unit')
        raise Duplicate(f'A unit with code {code} already exists', fields=['code'])
    except (pgerr.CheckViolation, pgerr.ForeignKeyViolation, pgerr.RaiseException) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_unit')
        raise ValidationError(getattr(getattr(e, 'diag', None), 'message_primary', None) or str(e), fields=['unit_type'])
    C.audit(cur, actor, parent, 'UNIT_CREATE', 'org_unit', code, {'parent': parent['code'], 'type': utype, 'attrs': attrs})
    return _get(cur, actor, code)


def _get(cur, actor: db.Actor, code: str) -> Dict:
    cur.execute(_UNIT_SQL + ' WHERE o.code = %(c)s', {'u': actor.user_id, 'c': code})
    return {'unit': cur.fetchone()}


def update_unit(conn, actor: db.Actor, code: str, changes: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = _unit(cur, code)
    _need(cur, actor, 'unit:manage', unit, 'change units')
    allowed = {'name', 'name_local', 'status', 'attrs'}
    unknown = [k for k in (changes or {}) if k not in allowed]
    if unknown:
        raise ValidationError('These fields cannot be changed here: ' + ', '.join(unknown) +
                              ' (type and parent change only through a move)', fields=unknown)
    sets = {}
    if 'name' in changes:
        sets['name'] = C.text(changes, 'name')
        if not sets['name']:
            raise ValidationError('Name cannot be empty', fields=['name'])
    if 'name_local' in changes:
        sets['name_local'] = C.text(changes, 'name_local') or None
    if 'status' in changes:
        sets['status'] = C.choice(changes['status'], ['planned', 'active', 'inactive'], 'Status', 'status', required=True)
    if 'attrs' in changes:
        if not isinstance(changes['attrs'], dict):
            raise ValidationError('attrs must be an object', fields=['attrs'])
        sets['attrs'] = psycopg2.extras.Json(changes['attrs'])
    if not sets:
        raise ValidationError('Nothing to update', fields=sorted(allowed))
    try:
        cur.execute('SAVEPOINT upd_unit')
        cur.execute('UPDATE org_units SET ' + ', '.join(f'{k} = %({k})s' for k in sets) + ' WHERE id = %(id)s', {**sets, 'id': unit['id']})
    except (pgerr.CheckViolation, pgerr.RaiseException) as e:
        cur.execute('ROLLBACK TO SAVEPOINT upd_unit')
        raise ValidationError(e.diag.message_primary or str(e))
    C.audit(cur, actor, unit, 'UNIT_UPDATE', 'org_unit', unit['code'], {k: (v.adapted if hasattr(v, 'adapted') else v) for k, v in sets.items()})
    return _get(cur, actor, unit['code'])


def move_unit(conn, actor: db.Actor, code: str, new_parent: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = _unit(cur, code)
    parent = _unit(cur, new_parent)
    _need(cur, actor, 'unit:manage', unit, 'move units')
    _need(cur, actor, 'unit:manage', parent, 'move units into')
    try:
        cur.execute('SAVEPOINT mv')
        cur.execute('SELECT move_unit(%s, %s, %s)', (unit['id'], parent['id'], actor.user_id))
    except (pgerr.RaiseException, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT mv')
        raise ValidationError(e.diag.message_primary or str(e), fields=['parent'])
    C.audit(cur, actor, unit, 'UNIT_MOVE', 'org_unit', unit['code'], {'to': parent['code']})
    return _get(cur, actor, unit['code'])


# ---- assignments -----------------------------------------------------------------------------
def list_assignments(conn, actor: db.Actor, unit: Optional[str] = None, user: Optional[str] = None) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute("""SELECT a.id, u.username, u.display_name, r.code AS role, r.name AS role_name, o.code AS unit, o.name AS unit_name,
                          a.include_descendants, a.valid_from, a.valid_until, a.revoked_at,
                          authz_can(%(u)s, 'assignment:manage', a.unit_id) AS can_revoke
                     FROM user_assignments a JOIN users u ON u.id = a.user_id JOIN roles r ON r.id = a.role_id
                     JOIN org_units o ON o.id = a.unit_id
                    WHERE authz_can(%(u)s, 'assignment:manage', a.unit_id)
                      AND (%(unit)s::text IS NULL OR o.code = %(unit)s) AND (%(user)s::text IS NULL OR u.username = %(user)s)
                    ORDER BY a.revoked_at IS NOT NULL, a.id DESC""", {'u': actor.user_id, 'unit': unit or None, 'user': user or None})
    return {'items': cur.fetchall()}


def grant(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = _unit(cur, C.text(data, 'unit'))
    cur.execute('SELECT id, username FROM users WHERE username = %s', (C.text(data, 'username'),))
    user = cur.fetchone()
    if not user:
        raise ValidationError('Unknown user', fields=['username'])
    cur.execute('SELECT id, code FROM roles WHERE code = %s', (C.text(data, 'role'),))
    role = cur.fetchone()
    if not role:
        raise ValidationError('Unknown role', fields=['role'])
    cur.execute('SELECT can_grant(%s, %s, %s) AS ok', (actor.user_id, role['id'], unit['id']))
    if not cur.fetchone()['ok']:
        raise PermissionDenied(f'You may not grant {role["code"]} at {unit["name"]}: you can only delegate roles whose '
                               'every permission you already hold there')
    until = None
    if data.get('valid_until'):
        until = C.parse_local_datetime(data['valid_until'], 'valid_until', 'Valid until')
    try:
        cur.execute('SAVEPOINT sp_grant')
        cur.execute("""INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants, valid_until, granted_by)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (user['id'], role['id'], unit['id'], data.get('include_descendants', True) is not False, until, actor.user_id))
        aid = cur.fetchone()['id']
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT sp_grant')
        raise Duplicate(f'{user["username"]} already holds {role["code"]} at {unit["code"]}')
    except (pgerr.CheckViolation, pgerr.RaiseException) as e:
        cur.execute('ROLLBACK TO SAVEPOINT sp_grant')
        raise ValidationError(e.diag.message_primary or str(e))
    C.audit(cur, actor, unit, 'ASSIGNMENT_GRANT', 'user_assignment', str(aid), {'user': user['username'], 'role': role['code']})
    return {'assignment': {'id': aid, 'username': user['username'], 'role': role['code'], 'unit': unit['code']}}


def revoke(conn, actor: db.Actor, assignment_id: int) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute('SELECT a.id, a.unit_id, a.revoked_at, o.code, o.name, u.username FROM user_assignments a '
                'JOIN org_units o ON o.id = a.unit_id JOIN users u ON u.id = a.user_id WHERE a.id = %s', (assignment_id,))
    a = cur.fetchone()
    if not a:
        raise NotFound('Assignment not found')
    _need(cur, actor, 'assignment:manage', {'id': a['unit_id'], 'name': a['name'], 'code': a['code']}, 'revoke assignments')
    if a['revoked_at']:
        raise Duplicate('That assignment is already revoked')
    cur.execute('UPDATE user_assignments SET revoked_at = now() WHERE id = %s', (a['id'],))
    C.audit(cur, actor, {'id': a['unit_id']}, 'ASSIGNMENT_REVOKE', 'user_assignment', str(a['id']), {'user': a['username']})
    return {'id': a['id'], 'revoked': True}
