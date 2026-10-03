"""Shared helpers for the operational-unit modules (checkpoint, airport, station).

Every record is bound to a UNIT (`unit_id`), and a person is ALWAYS resolved through the Central Person
Registry (`identity.registry.register`) — an operational module never writes to `persons` itself.

Authorisation is layered, outermost first:
  1. this module   : friendly 403/422 errors  (`resolve_unit`)
  2. the database  : region-scope trigger, active-unit trigger, unit-type trigger, provenance trigger,
                     append-only triggers, and row-level security (when connected as a non-owner role)
Nothing here weakens (2); it only explains it.
"""
import dataclasses
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from ..db import Actor, bind_actor, cursor
from ..identity.errors import PermissionDenied, ReviewLocked, ValidationError

# Somalia observes no daylight saving, so a fixed UTC+3 offset is exactly Africa/Mogadishu.
LOCAL_TZ = timezone(timedelta(hours=3), 'EAT')


def text(data: Dict, key: str) -> str:
    v = data.get(key)
    return ' '.join(str(v).split()) if v not in (None, '') else ''


def policy(cur, key: str, default=None):
    cur.execute('SELECT value FROM policy_settings WHERE key = %s', (key,))
    r = cur.fetchone()
    return r['value'] if r else default


def choice(value, options: List[str], label: str, field: str, required=False) -> Optional[str]:
    """Case-insensitive match against a fixed list; returns the canonical spelling (legacy normalise_choice)."""
    v = ' '.join(str(value or '').split())
    if not v:
        if required:
            raise ValidationError(f'{label} is required', fields=[field])
        return None
    for o in options:
        if o.lower() == v.lower():
            return o
    raise ValidationError(f'{label} must be one of: ' + ', '.join(options), fields=[field])


def parse_date(value, field: str, label: str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value or '').strip())
    except ValueError:
        raise ValidationError(f'{label} must be a date (YYYY-MM-DD)', fields=[field])


def parse_local_datetime(value, field: str, label: str) -> datetime:
    """ISO date-time.  No offset given -> the officer's wall clock, i.e. Africa/Mogadishu."""
    s = str(value or '').strip()
    if not s:
        raise ValidationError(f'{label} is required', fields=[field])
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        raise ValidationError(f'{label} must be a date and time (YYYY-MM-DDTHH:MM)', fields=[field])
    return d if d.tzinfo else d.replace(tzinfo=LOCAL_TZ)


def at_unit(actor: Actor, unit: Dict) -> Actor:
    """The actor, acting AT the unit the record belongs to (so persons first met here are stamped with it)."""
    return dataclasses.replace(actor, unit_id=unit['id'])


def resolve_unit(cur, actor: Actor, code: Optional[str], perm: str, types, noun: str, scope: str = 'operational',
                 or_at_service: Optional[str] = None) -> Dict:
    """Find the unit a record is being filed at and prove the actor may write there.

    `code` defaults to the unit the officer says they are working at (X-Unit).
    `types=None` accepts any unit type (the permission is the real gate).
    `scope='operational'` = under a listed region (airports, checkpoints, stations);
    `scope='state'`       = inside the Northeastern State: a listed region OR a national directorate / bureau.
    `or_at_service='hr'`  = a holder of `perm` at that national directorate may also act at this unit."""
    if not code and actor.unit_id:
        cur.execute('SELECT code FROM org_units WHERE id = %s', (actor.unit_id,))
        code = cur.fetchone()['code']
    code = (code or '').strip()
    if not code:
        raise ValidationError(f'Choose the {noun} this record is for', fields=['unit'])
    cur.execute("""SELECT o.id, o.code, o.name, o.unit_type, o.status,
                          (SELECT d.name FROM org_unit_closure c JOIN org_units d ON d.id = c.ancestor_id
                            WHERE c.descendant_id = o.id AND d.unit_type = 'district') AS district,
                          unit_region_name(o.id) AS region
                     FROM org_units o WHERE o.code = %s""", (code,))
    unit = cur.fetchone()
    if not unit:
        raise ValidationError(f'Unknown unit "{code}"', fields=['unit'])
    cur.execute('SELECT authz_can(%s, %s, %s) AS ok', (actor.user_id, perm, unit['id']))
    ok = cur.fetchone()['ok']
    if not ok and or_at_service:
        cur.execute('SELECT authz_can(%s, %s, service_unit(%s)) AS ok', (actor.user_id, perm, or_at_service))
        ok = cur.fetchone()['ok']
    if not ok:
        raise PermissionDenied(f'You are not allowed to file records at {unit["name"]} ({unit["code"]})')
    if types is not None and unit['unit_type'] not in types:
        raise ValidationError(f'{unit["name"]} is a {unit["unit_type"]}, not a {noun}', fields=['unit'])
    if unit['status'] != 'active':
        raise ValidationError(f'{unit["name"]} is not active (status: {unit["status"]}); nothing can be filed there yet',
                              fields=['unit'])
    cur.execute('SELECT ' + ('unit_in_state' if scope == 'state' else 'unit_in_operational_region') + '(%s) AS ok', (unit['id'],))
    if not cur.fetchone()['ok']:
        raise ValidationError(f'{unit["name"]} is outside the Northeastern State regions (Sool, Sanaag, East Togdheer)'
                              if scope == 'state' else f'{unit["name"]} is outside the operational regions', fields=['unit'])
    return unit


def audit(cur, actor: Actor, unit: Dict, action: str, entity: str, ref: str, details: Optional[Dict] = None):
    cur.execute('INSERT INTO audit_events (user_id, unit_id, action, entity, entity_id, details) '
                'VALUES (%s, %s, %s, %s, %s, %s::jsonb)',
                (actor.user_id, unit['id'], action, entity, ref, psycopg2.extras.Json(details or {})))


def person_id(cur, person_ref: str) -> int:
    cur.execute('SELECT id FROM persons WHERE person_ref = %s', (person_ref,))
    return cur.fetchone()['id']


def check_uploads(cur, actor: Actor, names, field: str, label: str, images_only=False) -> List[str]:
    """Every referenced file must be one THIS user uploaded (you cannot attach someone else's file)."""
    names = [str(n).strip() for n in (names or []) if str(n or '').strip()]
    if not names:
        return []
    cur.execute('SELECT name, content_type FROM uploads WHERE name = ANY(%s) AND uploaded_by = %s',
                (names, actor.user_id))
    found = {r['name']: r['content_type'] for r in cur.fetchall()}
    for n in names:
        if n not in found:
            raise ValidationError(f'{label}: file "{n}" was not uploaded by you (upload it first)', fields=[field])
        if images_only and not found[n].startswith('image/'):
            raise ValidationError(f'{label} must be an image', fields=[field])
    return names


def translate_db_error(e: Exception):
    """Turn the database guards into the service's friendly errors (never swallow them)."""
    if isinstance(e, pgerr.InsufficientPrivilege):
        raise PermissionDenied(e.diag.message_primary or 'Not allowed')
    if isinstance(e, pgerr.CheckViolation):
        raise ValidationError(e.diag.message_primary or 'Invalid record')
    if isinstance(e, pgerr.ObjectNotInPrerequisiteState):
        raise ReviewLocked(e.diag.message_primary or 'Not allowed yet')
    raise e


def new_cursor(conn, actor: Actor):
    cur = cursor(conn)
    bind_actor(cur, actor)
    return cur
