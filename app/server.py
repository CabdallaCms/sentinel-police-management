"""HTTP adapter for the Central Person Registry service (stdlib only).

    SENTINEL_DATABASE_URL=postgresql://... SENTINEL_DEV_AUTH=1 python -m app.server --port 8080

Endpoints (JSON, same-origin; the UI in web/ is served from `/`):
    GET   /api/health
    GET   /api/me                          who am I, which units may I work at, what may I do
    GET   /api/field-policy                the lock rules (labels + mutability class per field)
    GET   /api/persons/search?q=...        the single search box
    POST  /api/persons/search              {query:{first_name,...,national_id,...}}   structured smart search
    GET   /api/persons/{ref}               master profile + what THIS user may edit
    POST  /api/persons                     {person:{...}, link_person_ref?, confirm_new?, allow_no_id?}  register-or-link
    PATCH /api/persons/{ref}               {changes:{...}, reason?}                   strict, field-locked edit
    POST  /api/persons/{ref}/guardians     {guardian:{...}, relationship?, guardian_person_ref?, confirm_new?}

Operational units (Phase 2) — every record is filed AT a unit (`unit` = unit code) and goes through the registry:
    GET   /api/operations/units            checkpoints / airports / stations this user may file at or view
    GET   /api/operations/vocabularies     incident dropdown lists + checkpoint / airport form rules (policy data)
    POST  /api/checkpoint-events           {unit, traveler:{...}, purpose_of_visit, current_address, guardian:{...}, ...}
    GET   /api/checkpoint-events?unit=&person=&limit=
    POST  /api/airport-records             {unit, passenger:{...}, movement, travel_date, flight_number, origin_city, ...}
    GET   /api/airport-records?unit=&person=&movement=&from=&to=&limit=
    POST  /api/crimes                      {unit, category, incident_at, location_of_occurrence, description, victim_*, ...}
    GET   /api/crimes?unit=&category=&limit=
    POST  /api/uploads                     raw bytes, X-Filename header  ->  {name}   (photos / documents / evidence)
    GET   /api/uploads/{name}              only if you uploaded it or may view a record that references it
    GET   /api/persons/{ref}/timeline      this person's stops / movements / clearances that YOU may see

Directorate & specialised services (Phase 3): see app/directorate/routes.py for the full list
(clearance, CID cases and alerts, HR officers and conduct, admin units / assignments, public /api/verify/{number}).

AUTHENTICATION — read this before deploying.  The unified auth stack (blueprint open item O9) is
not built yet.  Until it is, requests are authenticated ONLY when SENTINEL_DEV_AUTH=1, by the
header `X-Dev-User: <username>`.  Without that variable every /api call except /api/health is
answered 401 (fail closed).  Replace `authenticate()` with the real session check; nothing else
here depends on how the user was identified.  Optional header `X-Unit: <unit code>` names the unit
the officer is working at; it is validated against their assignments.
"""
import argparse
import json
import logging
import mimetypes
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg2

from .db import Actor, connect, cursor
from .identity import registry
from .directorate import clearance as clearance_svc, routes as directorate_routes
from .operations import airport, checkpoint, incidents, timeline, uploads, units as op_units
from .identity.errors import IdentityError, PermissionDenied

log = logging.getLogger('sentinel.api')
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web'))
MAX_BODY = 1_000_000


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(f'not serialisable: {type(o)}')


class HttpError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def dev_auth_enabled():
    return os.environ.get('SENTINEL_DEV_AUTH') == '1'


def authenticate(conn, headers) -> Actor:
    """DEV ONLY (see module docstring).  Returns the Actor or raises HttpError(401/403)."""
    if not dev_auth_enabled():
        raise HttpError(401, 'unauthenticated', 'Authentication is not configured (set SENTINEL_DEV_AUTH=1 for development).')
    username = (headers.get('X-Dev-User') or '').strip()
    if not username:
        raise HttpError(401, 'unauthenticated', 'Sign in first.')
    cur = cursor(conn)
    cur.execute('SELECT id, username FROM users WHERE username = %s AND active', (username,))
    u = cur.fetchone()
    if not u:
        raise HttpError(401, 'unauthenticated', 'Unknown or inactive user.')
    unit_id = None
    code = (headers.get('X-Unit') or '').strip()
    if code:
        cur.execute('SELECT id FROM org_units WHERE code = %s', (code,))
        unit = cur.fetchone()
        if not unit:
            raise HttpError(403, 'unit_not_allowed', f'Unknown unit {code}.')
        cur.execute("SELECT authz_can(%s, 'person:search', %s) AS ok", (u['id'], unit['id']))
        if not cur.fetchone()['ok']:
            raise HttpError(403, 'unit_not_allowed', f'You are not assigned to {code}.')
        unit_id = unit['id']
    return Actor(user_id=u['id'], username=u['username'], unit_id=unit_id)


# ---------------------------------------------------------------------------------------
def me(conn, actor: Actor):
    cur = cursor(conn)
    cur.execute('SELECT username, display_name FROM users WHERE id = %s', (actor.user_id,))
    user = cur.fetchone()
    cur.execute("""SELECT o.code, o.name, o.unit_type FROM org_units o
                    WHERE o.status = 'active' AND o.id IN (SELECT authz_scope(%s, 'person:search'))
                    ORDER BY o.depth, o.name""", (actor.user_id,))
    units = cur.fetchall()
    cur.execute("""SELECT authz_has(%(u)s,'person:search') AS can_search, authz_has(%(u)s,'person:create') AS can_register,
                          authz_has(%(u)s,'person:update_dynamic') AS can_update_dynamic,
                          person_perm_ok(%(u)s,'person:edit_core', true) AS is_national_admin""", {'u': actor.user_id})
    return {'user': user, 'units': units, 'abilities': cur.fetchone()}


def field_policy(conn):
    cur = cursor(conn)
    cur.execute('SELECT field, mutability, label, national_only, needs_reason FROM person_field_policy '
                "WHERE field <> 'full_name' ORDER BY field")
    return {'fields': cur.fetchall()}


class Raw:
    """A non-JSON response body (a downloaded file)."""
    def __init__(self, data, ctype):
        self.data, self.ctype = data, ctype


class Handler(BaseHTTPRequestHandler):
    server_version = 'SentinelRegistry/1'

    # ---- plumbing -----------------------------------------------------------------
    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)

    def _send(self, status, payload, ctype='application/json', extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, default=_json_default).encode()
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            raise HttpError(413, 'too_large', 'Request body too large')
        if not n:
            return {}
        try:
            data = json.loads(self.rfile.read(n))
        except ValueError:
            raise HttpError(400, 'bad_json', 'Body must be JSON')
        if not isinstance(data, dict):
            raise HttpError(400, 'bad_json', 'Body must be a JSON object')
        return data

    def _raw_body(self, limit=uploads.MAX_BYTES):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise HttpError(413, 'too_large', 'The file is larger than 5 MB')
        return self.rfile.read(n) if n else b''

    def _static(self, path):
        rel = 'index.html' if path in ('', '/') else path.lstrip('/')
        full = os.path.abspath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR + os.sep) or not os.path.isfile(full):
            raise HttpError(404, 'not_found', 'Not found')
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        with open(full, 'rb') as f:
            self._send(200, f.read(), ctype + ('; charset=utf-8' if ctype.startswith('text/') or 'javascript' in ctype else ''))

    # ---- dispatch -------------------------------------------------------------------
    def _handle(self, method):
        url = urlparse(self.path)
        path = url.path
        try:
            if not path.startswith('/api/'):
                if method not in ('GET', 'HEAD'):
                    raise HttpError(405, 'method_not_allowed', 'Method not allowed')
                return self._static(path)
            if path == '/api/health' and method == 'GET':
                return self._send(200, {'status': 'ok', 'dev_auth': dev_auth_enabled()})
            if path == '/api/dev/users' and method == 'GET':          # login picker for development only
                if not dev_auth_enabled():
                    raise HttpError(404, 'not_found', 'Not found')
                conn = connect()
                try:
                    cur = cursor(conn)
                    cur.execute("""SELECT u.username, u.display_name,
                                          (SELECT string_agg(r.name, ', ') FROM active_assignments a
                                             JOIN roles r ON r.id = a.role_id WHERE a.user_id = u.id) AS roles
                                     FROM users u WHERE u.active ORDER BY u.username""")
                    return self._send(200, {'users': cur.fetchall()})
                finally:
                    conn.close()

            m = re.match(r'^/api/verify/([A-Za-z0-9-]{3,64})$', path)
            if m and method == 'GET':                                  # PUBLIC: certificate verification, no login
                conn = connect()
                try:
                    result = clearance_svc.verify_public(conn, m.group(1))
                    conn.commit()
                finally:
                    conn.close()
                return self._send(200, result)

            raw_upload = path == '/api/uploads' and method == 'POST'
            body = self._body() if method in ('POST', 'PATCH', 'PUT') and not raw_upload else {}
            conn = connect()
            try:
                actor = authenticate(conn, self.headers)
                result, status = self._route(conn, actor, method, path, parse_qs(url.query), body)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
            if isinstance(result, Raw):
                return self._send(status, result.data, result.ctype, {'Content-Security-Policy': "sandbox",
                                                                     'Content-Disposition': 'inline'})
            self._send(status, result)
        except HttpError as e:
            self._send(e.status, {'error': e.code, 'message': e.message})
        except IdentityError as e:
            self._send(e.status, e.payload())
        except psycopg2.Error:
            log.exception('database error')
            self._send(500, {'error': 'database_error', 'message': 'The request could not be completed.'})
        except Exception:                                                   # pragma: no cover
            log.exception('unhandled error')
            self._send(500, {'error': 'server_error', 'message': 'Unexpected server error.'})

    def _route(self, conn, actor, method, path, qs, body):
        if path == '/api/me' and method == 'GET':
            return me(conn, actor), 200
        if path == '/api/field-policy' and method == 'GET':
            return field_policy(conn), 200
        if path == '/api/persons/search':
            if method == 'GET':
                return registry.search(conn, actor, q=(qs.get('q') or [''])[0],
                                       limit=_limit(qs)), 200
            if method == 'POST':
                return registry.search(conn, actor, query=body.get('query') or {}, q=body.get('q'),
                                       limit=int(body.get('limit') or 8)), 200
        if path == '/api/persons' and method == 'POST':
            person = body.get('person')
            if not isinstance(person, dict):
                raise HttpError(400, 'bad_request', '`person` object is required')
            res = registry.register(conn, actor, person, confirm_new=bool(body.get('confirm_new')),
                                    link_person_ref=body.get('link_person_ref'),
                                    allow_no_id=bool(body.get('allow_no_id')))
            return res, (201 if res['created'] else 200)
        m = re.match(r'^/api/persons/(P-\d{4}-\d+)$', path)
        if m:
            if method == 'GET':
                return registry.get_person(conn, actor, m.group(1)), 200
            if method == 'PATCH':
                changes = body.get('changes')
                if not isinstance(changes, dict) or not changes:
                    raise HttpError(400, 'bad_request', '`changes` object is required')
                return registry.update_profile(conn, actor, m.group(1), changes, body.get('reason')), 200
        m = re.match(r'^/api/persons/(P-\d{4}-\d+)/guardians$', path)
        if m and method == 'POST':
            guardian = body.get('guardian') or {}
            if not isinstance(guardian, dict):
                raise HttpError(400, 'bad_request', '`guardian` must be an object')
            res = registry.add_guardian(conn, actor, m.group(1), guardian, relationship=body.get('relationship'),
                                        guardian_person_ref=body.get('guardian_person_ref'),
                                        confirm_new=bool(body.get('confirm_new')))
            return res, (201 if res['link_created'] else 200)
        # ---- operational units (Phase 2) ----------------------------------------------------------------
        if path == '/api/operations/units' and method == 'GET':
            return op_units.operational_units(conn, actor), 200
        if path == '/api/operations/vocabularies' and method == 'GET':
            return op_units.vocabularies(conn, actor), 200
        if path == '/api/checkpoint-events':
            if method == 'POST':
                res = checkpoint.record_stop(conn, actor, body)
                return res, 201
            if method == 'GET':
                return checkpoint.list_stops(conn, actor, unit=_q(qs, 'unit'), person_ref=_q(qs, 'person'),
                                             limit=_int(qs, 'limit', 50)), 200
        if path == '/api/airport-records':
            if method == 'POST':
                return airport.record_passenger(conn, actor, body), 201
            if method == 'GET':
                return airport.list_passengers(conn, actor, unit=_q(qs, 'unit'), person_ref=_q(qs, 'person'),
                                               movement=_q(qs, 'movement'), date_from=_q(qs, 'from'),
                                               date_to=_q(qs, 'to'), limit=_int(qs, 'limit', 50)), 200
        if path == '/api/crimes':
            if method == 'POST':
                return incidents.file_incident(conn, actor, body), 201
            if method == 'GET':
                return incidents.list_incidents(conn, actor, unit=_q(qs, 'unit'), category=_q(qs, 'category'),
                                                limit=_int(qs, 'limit', 50)), 200
        if path == '/api/uploads' and method == 'POST':
            from urllib.parse import unquote
            name = unquote(self.headers.get('X-Filename') or '')
            return uploads.store(conn, actor, name, self._raw_body()), 201
        m = re.match(r'^/api/uploads/([0-9a-f]{32}\.[a-z]{3,4})$', path)
        if m and method == 'GET':
            data, ctype = uploads.open_file(conn, actor, m.group(1))
            return Raw(data, ctype), 200
        m = re.match(r'^/api/persons/(P-\d{4}-\d+)/timeline$', path)
        if m and method == 'GET':
            return timeline.person_timeline(conn, actor, m.group(1)), 200
        hit = directorate_routes.route(conn, actor, method, path, qs, body)
        if hit is not None:
            return hit
        raise HttpError(404, 'not_found', 'Not found')

    def do_GET(self): self._handle('GET')
    def do_HEAD(self): self._handle('HEAD')
    def do_POST(self): self._handle('POST')
    def do_PATCH(self): self._handle('PATCH')
    def do_PUT(self): self._handle('PUT')
    def do_DELETE(self): self._handle('DELETE')


def _q(qs, key):
    v = (qs.get(key) or [''])[0].strip()
    return v or None


def _int(qs, key, default):
    try:
        return int((qs.get(key) or [default])[0])
    except ValueError:
        return default


def _limit(qs):
    try:
        return max(1, min(20, int((qs.get('limit') or ['8'])[0])))
    except ValueError:
        return 8


def make_server(host='0.0.0.0', port=8080):
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8080)))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if dev_auth_enabled():
        log.warning('SENTINEL_DEV_AUTH=1: requests are authenticated by the X-Dev-User header. DEVELOPMENT ONLY.')
    srv = make_server(args.host, args.port)
    log.info('listening on %s:%s', args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
