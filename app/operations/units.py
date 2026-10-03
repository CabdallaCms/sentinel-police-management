"""Which operational units may THIS user file records at / look at?  Drives the unit pickers.
Units are read from the org tree — there is no hardcoded list of checkpoints, airports or stations."""
from ..db import Actor
from .common import new_cursor

KINDS = {  # kind -> (unit type, create permission, view permission)
    'checkpoint': ('checkpoint', 'checkpoint:create', 'checkpoint:view'),
    'airport':    ('airport',    'airport:create',    'airport:view'),
    'station':    ('station',    'incident:create',   'incident:view'),
}


def operational_units(conn, actor: Actor) -> dict:
    cur = new_cursor(conn, actor)
    out = {}
    for kind, (utype, create, view) in KINDS.items():
        cur.execute("""SELECT o.code, o.name, o.unit_type, o.status,
                              (SELECT d.name FROM org_unit_closure c JOIN org_units d ON d.id = c.ancestor_id
                                WHERE c.descendant_id = o.id AND d.unit_type = 'district') AS district,
                              (SELECT r.name FROM org_units r WHERE r.id = unit_region(o.id)) AS region,
                              o.id IN (SELECT authz_scope(%(u)s, %(create)s)) AS can_create
                         FROM org_units o
                        WHERE o.unit_type = %(t)s AND unit_in_operational_region(o.id)
                          AND (o.id IN (SELECT authz_scope(%(u)s, %(view)s)) OR o.id IN (SELECT authz_scope(%(u)s, %(create)s)))
                        ORDER BY region, district, o.name""",
                    {'u': actor.user_id, 't': utype, 'create': create, 'view': view})
        out[kind] = [dict(r, can_create=bool(r['can_create'] and r['status'] == 'active')) for r in cur.fetchall()]
    return out


def vocabularies(conn, actor: Actor) -> dict:
    """Dropdown lists and form rules that are policy DATA (so the page never hardcodes them)."""
    cur = new_cursor(conn, actor)
    cur.execute("""SELECT key, value FROM policy_settings
                    WHERE key LIKE 'incident.%%' OR key IN ('checkpoint.required', 'airport.travel_window_days')""")
    rows = {r['key']: r['value'] for r in cur.fetchall()}
    return {'incident': {k.split('.', 1)[1]: v for k, v in rows.items() if k.startswith('incident.')},
            'checkpoint': rows.get('checkpoint.required', {}),
            'airport': rows.get('airport.travel_window_days', {})}
