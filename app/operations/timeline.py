"""A person's cross-unit history: checkpoint stops, airport movements and clearances, filtered by what
THIS viewer may see (Migration 001 person_timeline).  Crime incidents are deliberately NOT in a person's
timeline: a victim must never be browsable from the registry."""
from ..db import Actor
from ..identity import registry
from ..identity.errors import NotFound, PermissionDenied
from .common import new_cursor


def person_timeline(conn, actor: Actor, person_ref: str) -> dict:
    cur = new_cursor(conn, actor)
    cur.execute("SELECT authz_has(%s, 'person:search') AS ok", (actor.user_id,))
    if not cur.fetchone()['ok']:
        raise PermissionDenied('You are not allowed to search the Central Person Registry')
    row = registry._get_by_ref(cur, person_ref)
    if not row:
        raise NotFound('Person not found')
    cur.execute("""SELECT t.occurred_at, t.kind, u.code AS unit_code, u.name AS unit_name, t.ref, t.summary
                     FROM person_timeline(%s, %s) t JOIN org_units u ON u.id = t.unit_id
                    ORDER BY t.occurred_at DESC""", (actor.user_id, row['id']))
    return {'person_ref': person_ref, 'full_name': row['full_name'], 'events': cur.fetchall()}
