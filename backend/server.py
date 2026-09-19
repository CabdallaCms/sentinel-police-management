#!/usr/bin/env python3
"""Sentinel backend — central configuration entry point.

Development-only API using the Python standard library + SQLite.
Supports central persons (with an optional linked case, universal identity
resolution and auto-create/merge), airport records, fingerprint clearance
applications (with file attachments), CID crime cases (participants +
evidence) and checkpoint screening events.

Identity matching tiers (used by /api/persons/resolve and every unit route):
  Tier 1 — exact National ID or Passport match            (auto merge / link)
  Tier 2 — exact 4-part name + date of birth match        (high-confidence link)
  Tier 3 — 3-part name + mother's name match              (fuzzy warning only)

Modular layout (extracted verbatim from the former single-file server;
no endpoint, payload, schema or permission was renamed):
  config.py     paths, environment, session map, domain constants
  utils.py      hashing, HTTP parsing, uploads, ID generators
  database.py   SQLite connectivity, schema, migrations, seeding
  auth_views.py sessions, RBAC, review gate, audit
  case_views.py identity, stations, officers, crimes, conduct
  analytics.py  departmental/global analytics, dashboards
  agents.py     AI-agent seam (disabled by default; no LLM call paths yet)
  vehicles.py   police/civilian vehicle register (unchanged)

``server.py`` itself now only wires those modules together: the HTTP
router (:class:`API`), static-file serving, port takeover and startup.
Everything it used to define is still importable from ``server``
(e.g. ``server.password_hash``) via explicit re-export imports, so
existing tooling keeps working.

Replace SQLite and demo authentication before any operational deployment.
"""
import datetime, json, os, re, secrets, signal, sqlite3, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from vehicles import (
    VEHICLES_SCHEMA, register_vehicle, update_vehicle_alert, list_vehicles,
    VEHICLE_CATEGORIES, VEHICLE_OP_STATUSES, VEHICLE_ALERTS,
)
from config import *
from utils import *
from database import *
from auth_views import *
from case_views import *
from analytics import *
from agents import *


class API(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print('%s - %s' % (self.address_string(), fmt % args))

    def send_json(self, status, data, extra_headers=None):
        out = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(out)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods','GET, POST, PATCH, OPTIONS')
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers(); self.wfile.write(out)

    def send_file(self, path, ctype):
        try:
            with open(path,'rb') as f: data = f.read()
        except OSError:
            self.send_json(404, {'error':'Not found'}); return
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        # Development server: never let a browser serve a stale copy of a
        # template (the printable pages are edited frequently and a cached
        # application.html shows an outdated layout).
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.end_headers(); self.wfile.write(data)
        # Truthy => the caller (serve_static) stops and does NOT fall through
        # to the JSON API, which would append a second response to the body.
        return True

    def do_OPTIONS(self): self.send_json(204, {})

    # ---- static pages & uploads --------------------------------------------
    def serve_static(self, path):
        p = urlparse(path)
        if p.path in ('/','/index.html'):
            return self.send_file(os.path.join(PROJECT_ROOT,'index.html'), 'text/html; charset=utf-8')
        if p.path in ('/application.html','/certificate.html'):
            return self.send_file(os.path.join(PROJECT_ROOT, p.path.lstrip('/')), 'text/html; charset=utf-8')
        if p.path.startswith('/uploads/'):
            name = os.path.basename(p.path)
            ext = os.path.splitext(name)[1].lower()
            ctype = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png',
                     '.gif':'image/gif','.webp':'image/webp','.pdf':'application/pdf'}.get(ext,'application/octet-stream')
            return self.send_file(os.path.join(UPLOAD_DIR, name), ctype)
        # Brand assets for the printable templates — the police emblem used as
        # both the letterhead logo and the page watermark. '/static/images/x'
        # and '/images/x' resolve to the project-root images/ folder.
        for prefix in ('/images/', '/static/images/'):
            if p.path.startswith(prefix):
                rel = os.path.normpath(p.path[len(prefix):]).lstrip('/\\')
                if rel.startswith('..') or os.path.isabs(rel):
                    self.send_json(404, {'error':'Not found'}); return True
                ext = os.path.splitext(rel)[1].lower()
                ctype = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
                         '.gif':'image/gif','.webp':'image/webp','.svg':'image/svg+xml'}.get(ext,'application/octet-stream')
                return self.send_file(os.path.join(PROJECT_ROOT, 'images', rel), ctype)
        return None

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        if self.serve_static(self.path) is not None: return
        c = None
        try:
            p = urlparse(self.path)
            # /api/fingerprint/applications* is served by the clearance handlers.
            if canonical_api_path(p.path) != p.path:
                p = p._replace(path=canonical_api_path(p.path))
            if p.path == '/api/health':
                # The build marker lets an operator confirm at a glance that
                # the running process really is the build with the 12-hour
                # fingerprint review lock (a stale process is the usual cause
                # of "the fix did not take effect").
                return self.send_json(200, {'status':'ok','service':'sentinel-backend',
                                            'database':'sqlite-development',
                                            'build':BUILD_TAG,
                                            # Live proof the gate is armed: the
                                            # boot self-test is re-run on every
                                            # health call, so a response saying
                                            # anything other than PASS means the
                                            # running process is NOT the build
                                            # with the review lock.
                                            'review_lock_active':review_lock_armed(),
                                            'build_ok':review_lock_armed(),
                                            'fingerprint_review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                                            'pid':os.getpid(),
                                            'started_at':SERVER_STARTED_AT,
                                            'clearance_reasons':list(CLEARANCE_REASONS),
                                            'officer_ranks':list(OFFICER_RANKS),
                                            'officer_units':list(OFFICER_UNITS),
                                            'officer_duty_statuses':list(OFFICER_DUTY_STATUSES),
                                            'station_tiers':list(STATION_TIERS),
                                            'crime_categories':list(CRIME_CATEGORIES),
                                            'conduct_action_types':list(CONDUCT_ACTION_TYPES),
                                            'conduct_classifications':{k: list(v) for k, v in CONDUCT_CLASSIFICATIONS.items()},
                                            'conduct_statuses':list(CONDUCT_STATUSES)})
            user = require_auth(self); c = db()
            # RBAC module-gating. Every authenticated user can see /api/me and
            # the central /api/persons registry, but each unit endpoint is
            # restricted to the roles that operate that module.
            module_for_path = {
                '/api/airport-records': 'airport',
                '/api/clearance-applications': 'fingerprint',
                '/api/fingerprint/applications': 'fingerprint',
                '/api/crime-cases': 'cid',
                '/api/suspect-alerts': 'cid',
                '/api/checkpoint-events': 'checkpoints',
                '/api/admin/users': 'admin',
                '/api/admin/analytics': 'analytics',
                '/api/stations': 'stations',
                '/api/officers': 'officers',
                '/api/crimes': 'crimes',
                '/api/vehicles': 'cars',
                '/api/conduct': 'conduct',
            }
            base = '/' + p.path.split('/')[1] + '/' + (p.path.split('/')[2] if len(p.path.split('/')) > 2 else '')
            for prefix, mod in module_for_path.items():
                if p.path == prefix or p.path.startswith(prefix + '/'):
                    if prefix in ('/api/stations', '/api/officers') and 'crimes' in (user.get('modules') or []):
                        break
                    if prefix == '/api/vehicles' and (
                            'cars' in (user.get('modules') or [])
                            or 'policesearch' in (user.get('modules') or [])
                            or 'checkpoints' in (user.get('modules') or [])
                            or 'crimes' in (user.get('modules') or [])):
                        break
                    require_module(user, mod)
                    break
            if p.path == '/api/me':
                result = {**user, 'visibility': filter_visibility(user),
                          'roles': list(ALL_ROLES),
                          'role_labels': ROLE_LABELS,
                          'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
            elif p.path == '/api/persons':
                q = re.sub(r'\s+', ' ', parse_qs(p.query).get('q',[''])[0]).strip()
                like = f'%{q}%'
                rows = c.execute('''SELECT * FROM persons WHERE full_name LIKE ? OR person_id LIKE ?
                    OR national_id LIKE ? OR phone LIKE ? OR passport_id LIKE ? OR mother_name LIKE ?
                    OR first_name LIKE ? OR second_name LIKE ? OR third_name LIKE ? OR fourth_name LIKE ?
                    ORDER BY id DESC''', (like,like,like,like,like,like,like,like,like,like)).fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path.startswith('/api/persons/'):
                pid = p.path.split('/')[3]
                person = rowdict(c.execute('SELECT * FROM persons WHERE person_id=?',(pid,)).fetchone())
                if not person: self.send_json(404,{'error':'Person not found'}); c.close(); return
                person['airport'] = [dict(r) for r in c.execute('SELECT record_id,movement,travel_date,flight_number,route FROM airport_passengers WHERE person_id=?',(person['id'],)).fetchall()]
                person['clearance'] = [dict(r) for r in c.execute('SELECT application_id,purpose,status,certificate_number FROM clearance_applications WHERE person_id=?',(person['id'],)).fetchall()]
                person['alerts'] = [dict(r) for r in c.execute('''SELECT sa.alert_id,sa.role,sa.alert_status,sa.origin,cc.case_id
                    FROM suspect_alerts sa LEFT JOIN crime_cases cc ON cc.id=sa.case_id
                    WHERE sa.person_id=?''',(person['id'],)).fetchall()]
                person['checkpoints'] = [dict(r) for r in c.execute('''SELECT event_id,location,location_code,checkpoint_location,
                    screening_result,action_taken,notes,created_at
                    FROM checkpoint_events WHERE person_id=? ORDER BY id DESC''',(person['id'],)).fetchall()]
                result = person
            elif p.path == '/api/airport-records':
                rows = c.execute('''SELECT a.record_id,a.movement,a.travel_date,a.flight_number,a.airline,
                    a.origin_city,a.destination_city,a.route,a.notes,
                    p.person_id,p.full_name,p.national_id FROM airport_passengers a
                    JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/clearance-applications':
                rows = c.execute('''SELECT a.application_id,a.purpose,a.status,a.certificate_number,a.created_at,
                    a.guardian_name,p.person_id,p.full_name,p.national_id,p.passport_id,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall()
                items = []
                for r in rows:
                    item = rowdict(r)
                    # 12-hour mandatory review window — admins bypass it, so
                    # `can_approve` is resolved per caller.
                    item['review'] = fingerprint_review_state(item)
                    item['can_approve'] = bool(is_admin_user(user) or not item['review']['review_locked'])
                    items.append(item)
                result = {'items': items, 'review_window_hours': FINGERPRINT_REVIEW_WINDOW_HOURS}
            elif p.path.startswith('/api/clearance-applications/'):
                aid = p.path.split('/')[3]
                a = rowdict(c.execute('''SELECT a.*,p.full_name,p.national_id,p.date_of_birth,p.mother_name,
                    p.place_of_birth,p.residence,p.occupation,p.passport_id,p.photo_path,p.phone
                    FROM clearance_applications a JOIN persons p ON p.id=a.person_id
                    WHERE a.application_id=?''',(aid,)).fetchone())
                if not a: self.send_json(404,{'error':'Application not found'}); c.close(); return
                # 12-hour mandatory review window metadata for the printable page.
                a['review'] = fingerprint_review_state(a)
                a['can_approve'] = bool(is_admin_user(user) or not a['review']['review_locked'])
                result = a
            elif p.path == '/api/crime-cases':
                rows = c.execute('''SELECT cc.*, COUNT(sa.id) AS participant_count
                    FROM crime_cases cc LEFT JOIN suspect_alerts sa ON sa.case_id=cc.id
                    GROUP BY cc.id ORDER BY cc.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path.startswith('/api/crime-cases/'):
                cid = p.path.split('/')[3]
                case = rowdict(c.execute('SELECT * FROM crime_cases WHERE case_id=?',(cid,)).fetchone())
                if not case: self.send_json(404,{'error':'Case not found'}); c.close(); return
                case['participants'] = [dict(r) for r in c.execute('''SELECT sa.alert_id,sa.role,sa.notes,sa.alert_status,
                    sa.origin,cc.case_id,p.person_id,p.full_name,p.national_id,p.phone FROM suspect_alerts sa
                    JOIN persons p ON p.id=sa.person_id JOIN crime_cases cc ON cc.id=sa.case_id
                    WHERE sa.case_id=? ORDER BY sa.id''',(case['id'],)).fetchall()]
                case['evidence'] = [dict(r) for r in c.execute('''SELECT evidence_id,caption,file_path,file_name,file_type,created_at
                    FROM case_evidence WHERE case_id=? ORDER BY id DESC''',(case['id'],)).fetchall()]
                result = case
            elif p.path == '/api/admin/users' or p.path.startswith('/api/admin/users/'):
                if p.path == '/api/admin/users':
                    rows = c.execute('''SELECT id,username,display_name,role,branch,location_scope,active
                        FROM users ORDER BY id ASC''').fetchall()
                    result = {'items':[user_view(rowdict(r)) for r in rows],
                              'roles': list(ALL_ROLES),
                              'role_labels': ROLE_LABELS,
                              'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
                else:
                    uid = p.path.split('/')[4]
                    if not uid or not uid.isdigit():
                        self.send_json(400, {'error': 'user id required'}); c.close(); return
                    row = c.execute('''SELECT id,username,display_name,role,branch,location_scope,active
                        FROM users WHERE id=?''', (int(uid),)).fetchone()
                    if not row: self.send_json(404, {'error': 'User not found'}); c.close(); return
                    result = {'user': user_view(rowdict(row)),
                              'roles': list(ALL_ROLES),
                              'role_labels': ROLE_LABELS,
                              'checkpoint_locations': list(CHECKPOINT_LOCATIONS)}
            elif p.path == '/api/admin/analytics':
                # Aggregate analytics — admin only (module gate above).
                result = build_analytics(c, user)
            # ---- departmental analytics -----------------------------------
            # Each register embeds its own analytics bundle; the CID bundle is
            # shared by the four directorate units and is sectioned by module
            # so a unit officer never receives another unit's numbers.
            elif p.path == '/api/cid/analytics':
                require_any_module(user, tuple(CID_SECTION_MODULES.values()) + ('analytics',))
                result = build_cid_analytics(c, user)
            elif p.path == '/api/officers/analytics':
                require_module(user, 'officers')
                result = build_officer_analytics(c, user)
            elif p.path == '/api/vehicles/analytics':
                require_any_module(user, ('cars', 'policesearch', 'checkpoints', 'crimes'))
                result = build_vehicle_analytics(c, user)
            elif p.path == '/api/stations/analytics':
                require_any_module(user, ('stations', 'crimes'))
                result = build_station_analytics(c, user)
            elif p.path in ('/api/analytics/global', '/api/analytics/global/'):
                # Chief Commander (HQ / Command) executive bundle — cross-
                # department aggregate gated by the `analytics:global`
                # permission (SystemAdmin + chief_commander).
                require_permission(user, PERM_ANALYTICS_GLOBAL)
                result = build_global_analytics(c, user)
            elif p.path == '/api/analytics':
                # Unified alias: /api/analytics?module=cid|officers|vehicles|
                # stations|all — gated per bundle inside the dispatcher.
                module = parse_qs(p.query).get('module', [''])[0]
                try:
                    result = build_module_analytics(c, user, module)
                except ValueError as e:
                    self.send_json(400, {'error': str(e),
                                         'modules': list(ANALYTICS_MODULES) + ['all']})
                    c.close(); return
            elif p.path == '/api/officers/promotions':
                require_module(user, 'officers')
                result = {'items': [promotion_view(r) for r in promotion_rows(c)]}
            elif p.path == '/api/officers/discipline':
                require_module(user, 'officers')
                result = {'items': [discipline_view(r) for r in discipline_rows(c)]}
            elif p.path == '/api/dashboard' or p.path.startswith('/api/dashboard/'):
                # Role- and location-scoped operations dashboard. Every
                # authenticated user can call this; the response is filtered
                # to the modules / location scope their role can access.
                # The route is a prefix-match so any trailing path (e.g.
                # /api/dashboard/, /api/dashboard/refresh) is accepted and
                # never returns 404 — guards against router regressions on
                # the frontend.
                try:
                    result = build_dashboard(c, user)
                except Exception as e:
                    # Defensive: never let a transient query error make the
                    # dashboard unreachable. Fall back to an empty payload so
                    # the frontend can still render its offline view.
                    r_role = (user.get('role') or '') if user else ''
                    result = {
                        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        'role': r_role,
                        'role_alias': normalize_role(r_role) if user else '',
                        'is_admin': (r_role == ROLE_ADMIN),
                        'location_scope': checkpoint_scope(user) if user else None,
                        'modules': sorted(ROLE_MODULES.get(r_role, set())),
                        'cards': [],
                        'quick_actions': [],
                        'activity': [],
                        'stream': [],
                        # Spec step 2 alias keys — always present even in degraded mode.
                        'screenings_today': 0,
                        'travelers_flagged': 0,
                        'total_travelers': 0,
                        'peak_travel_hour': '—',
                        'activity_feed': [],
                        'subhead': 'Dashboard temporarily unavailable',
                        'degraded': True,
                        'degraded_reason': str(e),
                    }
            elif p.path == '/api/suspect-alerts':
                rows = c.execute('''SELECT sa.alert_id,sa.role,sa.alert_status,sa.origin,sa.notes,
                    cc.case_id,cc.category,cc.status AS case_status,
                    p.person_id,p.full_name,p.national_id,p.passport_id FROM suspect_alerts sa
                    JOIN persons p ON p.id=sa.person_id
                    LEFT JOIN crime_cases cc ON cc.id=sa.case_id
                    ORDER BY sa.id DESC''').fetchall()
                result = {'items':[rowdict(r) for r in rows]}
            elif p.path == '/api/checkpoint-events':
                # RBAC: Checkpoint users only see events at their own location.
                # Admins see all; non-checkpoint users see all but the frontend
                # won't render the page for them either.
                #
                # The scope filter is matched flexibly against every
                # location-related column so a row that was just saved with
                # the friendly checkpoint label ('South Checkpoint') is
                # returned in the very next poll even if 'location_code' was
                # not populated. The match is also case-insensitive (LOWER
                # on both sides) and uses a LIKE '%south%' fallback so any
                # trailing space, casing, or punctuation variation in
                # 'location' / 'checkpoint_location' is still caught.
                scope = checkpoint_scope(user)
                base_cols = '''ce.event_id,ce.location,ce.location_code,ce.checkpoint_location,
                    ce.screening_result,ce.action_taken,ce.notes,ce.created_at,
                    ce.purpose_of_visit,ce.current_address,ce.permanent_address,
                    ce.traveler_photo,ce.traveler_docs,ce.guardian_person_id,ce.guardian_name,
                    ce.guardian_relationship,ce.guardian_phone,ce.guardian_address,ce.guardian_occupation,
                    ce.guardian_national_id,ce.guardian_passport_id,ce.guardian_docs,
                    p.person_id,p.full_name,p.national_id,p.passport_id'''
                if scope:
                    # Case-insensitive match against all four location columns
                    # plus a LIKE '%scope%' fallback. The OR-clause catches
                    # any combination the data layer might have written
                    # (short code, friendly label, or trailing spaces).
                    rows = c.execute(
                        f"SELECT {base_cols} FROM checkpoint_events ce "
                        f"JOIN persons p ON p.id=ce.person_id "
                        f"WHERE (LOWER(TRIM(COALESCE(ce.location_code,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.location,'')))=? "
                        f"OR LOWER(TRIM(COALESCE(ce.location,''))) LIKE ? "
                        f"OR LOWER(TRIM(COALESCE(ce.checkpoint_location,''))) LIKE ?) "
                        f"ORDER BY ce.id DESC",
                        (scope.lower(), scope.lower(), f"{scope.lower()} checkpoint",
                         scope.lower(), f"%{scope.lower()}%", f"%{scope.lower()}%")).fetchall()
                else:
                    rows = c.execute(f"SELECT {base_cols} FROM checkpoint_events ce "
                                     f"JOIN persons p ON p.id=ce.person_id ORDER BY ce.id DESC").fetchall()
                # Surface the explicit location metadata in every response item
                # so the frontend can render the friendly label without re-deriving it.
                items = []
                for r in rows:
                    item = rowdict(r)
                    if not item.get('location_code'):
                        item['location_code'] = (item.get('location') or '').split()[0] or None
                    if not item.get('checkpoint_location') and item.get('location_code'):
                        item['checkpoint_location'] = f"{item['location_code']} Checkpoint"
                    items.append(item)
                result = {'items': items,
                          'scope': scope,
                          'visible_locations': [scope] if scope else list(CHECKPOINT_LOCATIONS)}
            elif p.path == '/api/stations':
                rows = c.execute('SELECT * FROM police_stations ORDER BY id ASC').fetchall()
                result = {'items': [station_view(r) for r in rows]}
            elif p.path == '/api/officers':
                result = {'items': [officer_view(r) for r in officer_rows(c)]}
            elif p.path == '/api/crimes':
                rows = c.execute('''SELECT ci.*, s.station_id AS station_code, s.code AS station_short_code,
                    o.service_id AS officer_service_id, o.full_name AS officer_name
                    FROM crime_incidents ci
                    JOIN police_stations s ON s.id=ci.station_id
                    JOIN officers o ON o.id=ci.officer_id
                    ORDER BY ci.id DESC''').fetchall()
                result = {'items': [crime_view(r) for r in rows]}
            elif p.path == '/api/vehicles':
                q = parse_qs(p.query).get('q', [''])[0]
                result = {'items': list_vehicles(c, q)}
            elif p.path == '/api/conduct':
                # Conduct, promotions & disciplinary register — filtered by
                # status, category (Promotion vs Disciplinary), region or
                # station. Restricted to the Officer Registration Office /
                # HR staff (module gate above).
                q = parse_qs(p.query)
                where, args = [], []
                status = normalise_choice(q.get('status', [''])[0], CONDUCT_STATUSES)
                if (q.get('status', [''])[0] or '').strip() and not status:
                    raise ValueError('status must be one of: ' + ', '.join(CONDUCT_STATUSES))
                if status:
                    where.append('a.status=?'); args.append(status)
                category = normalise_conduct_type(q.get('category', [''])[0]
                                                  or q.get('action_type', [''])[0])
                if (q.get('category', [''])[0] or q.get('action_type', [''])[0] or '').strip() \
                        and not category:
                    raise ValueError('category must be one of: '
                                     + ', '.join(CONDUCT_ACTION_TYPES))
                if category:
                    where.append('a.action_type=?'); args.append(category)
                region = str(q.get('region', [''])[0] or '').strip()
                if region:
                    # Region of the submitting station OR of the target
                    # officer's assigned station — either anchors the file.
                    where.append('(s.region=? OR os.region=?)')
                    args.extend([region, region])
                station = str(q.get('station', [''])[0]
                              or q.get('station_id', [''])[0] or '').strip()
                if station:
                    where.append('(s.station_id=? OR CAST(s.id AS TEXT)=? '
                                 'OR os.station_id=? OR CAST(os.id AS TEXT)=?)')
                    args.extend([station, station, station, station])
                officer = str(q.get('officer', [''])[0]
                              or q.get('officer_id', [''])[0] or '').strip()
                if officer:
                    where.append('(o.service_id=? OR CAST(o.id AS TEXT)=?)')
                    args.extend([officer, officer])
                sql = CONDUCT_SELECT
                if where:
                    sql += ' WHERE ' + ' AND '.join(where)
                sql += ' ORDER BY a.id DESC'
                rows = c.execute(sql, args).fetchall()
                result = {'items': [conduct_view(r) for r in rows],
                          'summary': conduct_summary(c),
                          'statuses': list(CONDUCT_STATUSES),
                          'action_types': list(CONDUCT_ACTION_TYPES),
                          'classifications': {k: list(v) for k, v in CONDUCT_CLASSIFICATIONS.items()},
                          'ranks': list(OFFICER_RANKS)}
            elif p.path.startswith('/api/conduct/'):
                aid = p.path.split('/')[3]
                row = c.execute(CONDUCT_SELECT + ' WHERE a.action_id=?', (aid,)).fetchone()
                if not row:
                    self.send_json(404, {'error': 'Conduct action file not found'}); c.close(); return
                detail = conduct_view(row)
                # The officer's immutable service history (rank changes,
                # awards and penalties recorded by approved conduct files).
                detail['officer_service_history'] = [dict(r) for r in c.execute('''
                    SELECT h.action_id, h.entry_type, h.summary, h.from_rank, h.to_rank,
                           h.duty_status, h.created_at
                    FROM officer_service_history h WHERE h.officer_id=?
                    ORDER BY h.id DESC''', (row['officer_id'],)).fetchall()]
                result = detail
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(200, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except ValueError as e:
            # A GET route that validates its inputs (e.g. the conduct
            # register's status/category filters) rejects bad values
            # with 400 instead of an opaque 500.
            if c: c.close()
            self.send_json(400,{'error':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        c = None
        try:
            p = urlparse(self.path)
            # /api/fingerprint/applications* is handled by the clearance routes.
            if canonical_api_path(p.path) != p.path:
                p = p._replace(path=canonical_api_path(p.path))
            if p.path == '/api/login':
                data = body_json(self); c = db()
                u = c.execute('SELECT * FROM users WHERE username=? AND password_hash=? AND active=1',
                              (data.get('username'), password_hash(data.get('password','')))).fetchone(); c.close()
                if not u: self.send_json(401,{'error':'Invalid username or password'}); return
                # Persistent session: the token survives a server restart, so
                # /api/me keeps answering 200 for a signed-in officer.
                token = create_session(u['id'])
                self.send_json(200,{'token':token,'user':user_view(rowdict(u))},
                               extra_headers=[('Set-Cookie',
                                               f'sentinel_session={token}; Path=/; HttpOnly; SameSite=Lax')])
                return
            if p.path == '/api/logout':
                # Revoke the session (both transports) so the client is forced
                # into a clean re-login instead of a broken offline state.
                token = (self.headers.get('Authorization','') or '').replace('Bearer ','') \
                    or session_token_from_cookie(self)
                destroy_session(token)
                self.send_json(200, {'ok': True},
                               extra_headers=[('Set-Cookie',
                                               'sentinel_session=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax')])
                return
            user = require_auth(self); c = db()
            # RBAC: same module gate for the POST/PATCH handlers.
            # Writes follow the documented ownership of each register: the
            # station and vehicle registries are SystemAdmin-write (the HR
            # Directorate and CID may READ stations for postings / intake, and
            # checkpoint + Central Police Search may read vehicles for plate
            # lookups), while the officer register belongs to the `officers`
            # module — SystemAdmin and the HR Directorate.
            post_module_for_path = {
                '/api/airport-records': 'airport',
                '/api/clearance-applications': 'fingerprint',
                '/api/fingerprint/applications': 'fingerprint',
                '/api/crime-cases': 'cid',
                '/api/suspect-alerts': 'cid',
                '/api/checkpoint-events': 'checkpoints',
                '/api/admin/users': 'admin',
                '/api/stations': 'admin',
                '/api/officers': 'officers',
                '/api/crimes': 'crimes',
                '/api/vehicles': 'admin',
            }
            for prefix, mod in post_module_for_path.items():
                if p.path == prefix or p.path.startswith(prefix + '/'):
                    # Intake endpoint: station commanders (any authenticated
                    # officer, whatever their unit role) submit promotion
                    # recommendations and misconduct reports. Only the HR
                    # review / listing endpoints are restricted to the
                    # conduct module.
                    if p.path == '/api/conduct/submit':
                        break
                    # Station registry writes: SystemAdmin OR the
                    # `stations:manage` permission (Chief Commander).
                    if prefix == '/api/stations' and has_permission(user, PERM_STATIONS_MANAGE):
                        break
                    require_module(user, mod)
                    break
            if p.path == '/api/persons':
                data = body_json(self)
                if not build_full_name(data):
                    raise ValueError('full_name or a 4-part name is required')
                existing, _ = find_by_id(c, data)
                if existing:
                    self.send_json(409,{'error':'A person with this National ID / Passport already exists','person':existing}); c.close(); return
                person, _ = create_person(c, data); audit(c,user,'CREATE','person',person['person_id'])
                c.commit(); result = {'person':person}
            elif p.path == '/api/persons/resolve':
                data = body_json(self)
                result = resolve_identity(c, data)
            elif p.path == '/api/persons/upsert':
                data = body_json(self); person, created = upsert_person(c, data)
                audit(c,user,'CREATE' if created else 'UPSERT','person',person['person_id'])
                c.commit(); result = {'person':person,'created':created}
            elif p.path == '/api/airport-records':
                data = body_json(self)
                person, created = ensure_person(c, data)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from airport register')
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'airport register filled missing details')
                origin = (data.get('origin_city') or data.get('origin') or '').strip()
                destination = (data.get('destination_city') or data.get('destination') or '').strip()
                route = (data.get('route') or '').strip()
                if not route and (origin or destination):
                    route = (origin + ' / ' + destination) if origin and destination else (origin or destination)
                rid = 'AR-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,
                    flight_number,airline,origin_city,destination_city,route,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid,person['id'],data.get('movement','Arrival'),data.get('travel_date',''),
                     data.get('flight_number',''),data.get('airline',''),origin,destination,
                     route,data.get('notes',''),user['id']))
                audit(c,user,'CREATE','airport_record',rid,person['person_id']); c.commit()
                result = {'record_id':rid,'identity':identity_result(c,data,person)}
            elif p.path == '/api/clearance-applications':
                ctype = self.headers.get('Content-Type','')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                if not build_full_name(fields):
                    raise ValueError('Applicant full name (4-part) is required')
                if not (fields.get('national_id') or '').strip() and not (fields.get('passport_id') or '').strip():
                    raise ValueError('Applicant National ID or Passport ID is required')
                # Mandatory clearance reason — must be one of the approved
                # dropdown options (case-insensitive, legacy values mapped).
                purpose = normalise_reason(fields.get('purpose'))
                if not purpose:
                    raise ValueError('Clearance reason is required and must be one of: '
                                     + ', '.join(CLEARANCE_REASONS))
                photo = save_upload(files['photo']) if 'photo' in files else None
                person, created = ensure_person(c, fields, photo_path=(photo['path'] if photo else None))
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from clearance application')
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'clearance application filled missing details')
                app_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_app_')]
                guard_docs = [save_upload(files[k]) for k in sorted(files) if k.startswith('doc_guard_')]
                if len(app_docs) < 2: raise ValueError('At least 2 applicant documents are required')
                if not fields.get('guardian_name'): raise ValueError('Guardian full name is required')
                if len(guard_docs) < 2: raise ValueError('At least 2 guardian documents are required')
                aid = 'FP-'+str(int(time.time()*1000))[-8:]
                # The submission timestamp is stored explicitly (UTC) so the
                # 12-hour mandatory review window can be evaluated against it.
                submitted_at = utc_now_stamp()
                c.execute('''INSERT INTO clearance_applications(application_id,person_id,purpose,
                    guardian_name,guardian_relationship,guardian_id,guardian_occupation,guardian_address,
                    guardian_phone,legal_document_ref,notes,applicant_docs,guardian_docs,applicant_photo,
                    sex,email,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (aid,person['id'],purpose,fields.get('guardian_name',''),
                     fields.get('guardian_relationship',''),fields.get('guardian_id',''),
                     fields.get('guardian_occupation',''),fields.get('guardian_address',''),
                     fields.get('guardian_phone',''),fields.get('legal_document_ref',''),
                     fields.get('notes',''),json.dumps(app_docs),json.dumps(guard_docs),
                     photo['path'] if photo else None,
                     (fields.get('sex') or '').strip(),(fields.get('email') or '').strip(),
                     user['id'],submitted_at))
                audit(c,user,'CREATE','clearance_application',aid,person['person_id']); c.commit()
                result = {'application_id':aid,'person_id':person['person_id'],
                          'status':'Pending Review','created_at':submitted_at,'purpose':purpose,
                          'review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                          'review_eligible_at':fingerprint_review_state({'created_at':submitted_at})['review_eligible_at'],
                          'identity':identity_result(c,fields,person)}
            elif p.path.startswith('/api/clearance-applications/') and p.path.endswith('/approve'):
                aid = p.path.split('/')[3]
                row = c.execute('SELECT application_id,status,certificate_number,created_at '
                                'FROM clearance_applications WHERE application_id=?', (aid,)).fetchone()
                if not row:
                    self.send_json(404, {'error':'Application not found'}); c.close(); return
                app_row = rowdict(row)
                # ---- 12-hour mandatory review period ----------------------
                # HARD LOCK, evaluated purely server-side from the stored row
                # and the caller's role. System Administrators bypass the gate;
                # every other role must wait until created_at + 12h, and a row
                # without a usable timestamp stays locked (fail-closed).
                verdict = review_gate_decision(app_row, user)
                if verdict is not None:
                    self.send_json(verdict[0], verdict[1]); c.close(); return
                # ---- second, independent lock (defence in depth) ----------
                # Even if review_gate_decision() above were edited or disabled,
                # this write is refused unless the caller is an administrator
                # or the full window has elapsed. Intentionally spelled out
                # rather than factored away.
                bypassed = is_admin_user(user)
                if not bypassed:
                    _created = parse_created_at(app_row.get('created_at'))
                    _elapsed = (None if _created is None else
                                (datetime.datetime.now(datetime.timezone.utc) - _created).total_seconds())
                    if _created is None or _elapsed is None or _elapsed < FINGERPRINT_REVIEW_WINDOW_HOURS * 3600:
                        self.send_json(400, {'detail':REVIEW_LOCK_MESSAGE,
                                             'error':REVIEW_LOCK_MESSAGE,
                                             'code':'review_period_active',
                                             'reason':'submission timestamp missing' if _created is None else 'review window open',
                                             'review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                                             'submitted_at':app_row.get('created_at'),
                                             'application_id':aid,
                                             'enforced_by':'inline_43200s_guard'})
                        c.close(); return
                cert = app_row['certificate_number'] or ('CL-'+str(int(time.time()*1000))[-8:])
                c.execute("UPDATE clearance_applications SET status='Approved',certificate_number=?,reviewed_at=CURRENT_TIMESTAMP WHERE application_id=?",
                          (cert,aid))
                audit(c,user,'APPROVE','clearance_application',aid,
                      f"{cert} by {user.get('role')}"
                      + (' (review period bypassed)' if bypassed else '')); c.commit()
                result = {'application_id':aid,'certificate_number':cert,'status':'Approved',
                          'review_window_hours':FINGERPRINT_REVIEW_WINDOW_HOURS,
                          'review_period_bypassed':bypassed,
                          'approved_by_role':user.get('role'),
                          'reviewer_is_fingerprint_officer':is_fingerprint_officer(user)}
            elif p.path == '/api/crime-cases':
                data = body_json(self)
                if not data.get('category'): raise ValueError('category is required')
                nxt = c.execute('SELECT COUNT(*) FROM crime_cases').fetchone()[0]+8
                case_id = 'CID-2026-'+str(nxt).zfill(3)
                c.execute('''INSERT INTO crime_cases(case_id,category,location,status,incident_summary,notes,created_by)
                    VALUES(?,?,?,?,?,?,?)''',(case_id,data['category'],data.get('location','Not specified'),
                    data.get('status','Reported'),data.get('incident_summary',''),data.get('notes',''),user['id']))
                audit(c,user,'CREATE','crime_case',case_id); c.commit()
                result = {'case_id':case_id,'category':data['category'],'status':'Reported'}
            elif p.path.startswith('/api/crime-cases/') and p.path.endswith('/evidence'):
                cid = p.path.split('/')[3]
                case = c.execute('SELECT id FROM crime_cases WHERE case_id=?',(cid,)).fetchone()
                if not case: raise ValueError('case_id must refer to an existing case')
                fields, files = parse_multipart(self)
                if 'file' not in files: raise ValueError('An evidence file is required')
                meta = save_upload(files['file'])
                eid = 'EV-'+secrets.token_hex(4)
                c.execute('''INSERT INTO case_evidence(evidence_id,case_id,caption,file_path,file_name,file_type,uploaded_by)
                    VALUES(?,?,?,?,?,?,?)''',(eid,case['id'],fields.get('caption',''),meta['path'],
                    meta['name'],fields.get('file_type','Evidence'),user['id']))
                audit(c,user,'UPLOAD','evidence',eid,cid); c.commit()
                result = {'evidence_id':eid,'file_path':meta['path']}
            elif p.path == '/api/admin/users':
                # Create a new officer / admin user. Admin only (module gate above).
                data = body_json(self)
                username = (data.get('username') or '').strip()
                display_name = (data.get('display_name') or '').strip()
                password = data.get('password') or ''
                role = (data.get('role') or '').strip()
                branch = (data.get('branch') or '').strip() or 'Central HQ'
                if not username: raise ValueError('username is required')
                if not display_name: raise ValueError('display_name is required')
                if not password or len(password) < 6:
                    raise ValueError('password must be at least 6 characters')
                # Spec step 1: accept both the legacy compound forms and
                # the canonical 'checkpoint_officer' alias — and ANY
                # accepted checkpoint spelling ('cp_south',
                # 'checkpoint_south', 'Checkpoint Officer (South)', ...).
                # Aliases are normalised to 'checkpoint_officer' here so
                # the stored role is canonical; the location is derived
                # from the alias ('cp_south' -> 'South') when the caller
                # does not pass an explicit location_scope, so
                # normalizing never loses the officer's location.
                role, derived_scope = normalize_incoming_role(role)
                accepted_roles = set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}
                if role not in accepted_roles:
                    raise ValueError(f'role must be one of {", ".join(sorted(accepted_roles))} '
                                     '(Checkpoint aliases such as CheckpointSouth / cp_south are also accepted)')
                scope = canonical_location_scope(
                    data.get('location_scope') or derived_scope or ROLE_LOCATION_SCOPE.get(role))
                if is_checkpoint_role(role) and not scope:
                    raise ValueError('location_scope is required for Checkpoint roles')
                if scope and scope not in CHECKPOINT_LOCATIONS:
                    raise ValueError(f'location_scope must be one of {", ".join(CHECKPOINT_LOCATIONS)}')
                if c.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                    self.send_json(409, {'error': f'Username "{username}" already exists'}); c.close(); return
                c.execute('''INSERT INTO users(username,display_name,role,branch,location_scope,password_hash,active)
                    VALUES(?,?,?,?,?,?,?)''',
                    (username, display_name, role, branch, scope, password_hash(password),
                     1 if data.get('active', True) else 0))
                new = rowdict(c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone())
                audit(c, user, 'CREATE', 'user', str(new['id']), username)
                c.commit()
                result = {'user': user_view(new)}
            elif p.path == '/api/suspect-alerts':
                data = body_json(self)
                case = None
                case_id = (data.get('case_id') or '').strip()
                if case_id:
                    case = c.execute('SELECT id,case_id,category FROM crime_cases WHERE case_id=?',(case_id,)).fetchone()
                    if not case: raise ValueError('case_id must refer to an existing CID case')
                reason = (data.get('notes') or data.get('reason') or '').strip()
                if case and not reason:
                    # Case-linked suspects default the reason to the case details.
                    reason = f'Linked to CID case {case["case_id"]} \u2014 {case["category"]}'
                elif not case and not reason:
                    raise ValueError('Suspect reason / alert details is required for unlinked suspects '
                                     '(Direct Intelligence Listing / Manual Entry)')
                origin = (data.get('origin') or '').strip()
                if not origin: origin = 'Case Link' if case else 'Direct Intelligence Listing'
                person, created = ensure_person(c, data)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from suspect listing')
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'suspect listing filled missing details')
                if case:
                    dup = c.execute('SELECT alert_id FROM suspect_alerts WHERE person_id=? AND case_id=? AND alert_status=?',
                                    (person['id'],case['id'],'Active alert')).fetchone()
                else:
                    dup = c.execute('SELECT alert_id FROM suspect_alerts WHERE person_id=? AND case_id IS NULL AND alert_status=?',
                                    (person['id'],'Active alert')).fetchone()
                if dup:
                    self.send_json(409,{'error':'An active alert already links this person' +
                                        (' to that case' if case else ' without a linked case'),
                                        'alert_id':dup['alert_id']}); c.close(); return
                alert_id = 'AL-'+secrets.token_hex(4)
                c.execute('''INSERT INTO suspect_alerts(alert_id,person_id,case_id,role,alert_status,origin,notes,created_by)
                    VALUES(?,?,?,?,?,?,?,?)''',(alert_id,person['id'], case['id'] if case else None,
                    data.get('role','Suspect'),'Active alert',origin,reason,user['id']))
                audit(c,user,'CREATE','suspect_alert',alert_id,
                      data.get('case_id','') or ('no case - '+origin)); c.commit()
                result = {'alert_id':alert_id,'case_id':case_id or None,'person_id':person['person_id'],
                          'role':data.get('role','Suspect'),'alert_status':'Active alert',
                          'origin':origin,'reason':reason,'identity':identity_result(c,data,person)}
            elif p.path == '/api/checkpoint-events':
                ctype = self.headers.get('Content-Type','')
                if ctype.startswith('multipart/form-data'):
                    data, files = parse_multipart(self)
                else:
                    data, files = body_json(self), {}
                # ---- validate everything before any person/file writes ----
                if not build_full_name(data):
                    raise ValueError('Traveler full name (4-part) is required')
                if not (data.get('date_of_birth') or '').strip():
                    raise ValueError('Traveler date of birth is required')
                purpose = (data.get('purpose_of_visit') or '').strip()
                if not purpose: raise ValueError('Purpose of visit is required')
                current_addr = (data.get('current_address') or data.get('residence') or '').strip()
                if not current_addr: raise ValueError('Traveler current address is required')
                tr_keys = sorted(k for k in files if k.startswith('doc_tr_'))
                gd_keys = sorted(k for k in files if k.startswith('doc_gd_'))
                if len(tr_keys) < 1: raise ValueError('At least 1 traveler document is required')
                if 'photo' not in files: raise ValueError('Traveler real-time photo is required')
                guardian_parts = [str(data.get('guardian_'+k) or '').strip() for k in
                                  ('first_name','second_name','third_name','fourth_name')]
                guardian_name = ' '.join(p for p in guardian_parts if p) or (data.get('guardian_name') or '').strip()
                if not guardian_name:
                    raise ValueError('Guardian full name is required')
                if not (data.get('guardian_relationship') or '').strip():
                    raise ValueError('Guardian relationship is required')
                if not (data.get('guardian_phone') or '').strip():
                    raise ValueError('Guardian contact number is required')
                if not (data.get('guardian_address') or '').strip():
                    raise ValueError('Guardian permanent address is required')
                if not (data.get('guardian_occupation') or '').strip():
                    raise ValueError('Guardian occupation is required')
                if len(gd_keys) < 1: raise ValueError('At least 1 guardian document is required')
                # ---- traveler identity (auto-create/merge, IDs optional) ----
                photo = save_upload(files['photo'])
                person, created = ensure_person(c, data, photo_path=photo['path'], allow_no_id=True)
                if created:
                    audit(c,user,'CREATE','person',person['person_id'],'auto-created from checkpoint stop')
                else:
                    audit(c,user,'ENRICH','person',person['person_id'],'checkpoint stop filled missing details')
                tr_docs = [save_upload(files[k]) for k in tr_keys]
                gd_docs = [save_upload(files[k]) for k in gd_keys]
                gd_identity = {'national_id': data.get('guardian_national_id'),
                               'passport_id': data.get('guardian_passport_id'),
                               'first_name': data.get('guardian_first_name'),
                               'second_name': data.get('guardian_second_name'),
                               'third_name': data.get('guardian_third_name'),
                               'fourth_name': data.get('guardian_fourth_name')}
                guardian_person = None
                gd_pid = (data.get('guardian_person_id') or '').strip()
                if gd_pid:
                    guardian_person = c.execute('SELECT id FROM persons WHERE person_id=?',(gd_pid,)).fetchone()
                if not guardian_person:
                    match, _ = find_by_id(c, gd_identity)
                    guardian_person = c.execute('SELECT id FROM persons WHERE id=?',(match['id'],)).fetchone() if match else None
                location = (data.get('location') or '').strip()
                if not location: raise ValueError('location is required')
                # Normalise casing / trailing whitespace to the canonical
                # short code so every row stored on disk has a clean
                # 'South' / 'East' / 'West' short code in BOTH the legacy
                # 'location' column and the 'location_code' column. The
                # case-insensitive SQL then matches every row and the
                # badge display stays consistent across officers.
                location_lower = location.lower()
                if location_lower in [c.lower() for c in CHECKPOINT_LOCATIONS]:
                    location_code = next(c for c in CHECKPOINT_LOCATIONS
                                          if c.lower() == location_lower)
                else:
                    # 'south checkpoint' / 'South Checkpoint' / etc. -> the
                    # canonical short code (e.g. 'South' / 'East' / 'West').
                    first_token = location_lower.split()[0].strip()
                    matched = next((c for c in CHECKPOINT_LOCATIONS
                                    if c.lower() == first_token), None)
                    if matched:
                        location_code = matched
                    else:
                        # Unknown location: keep the original (lowercased)
                        # token so the error message is informative and the
                        # row can still be stored for audit purposes.
                        location_code = first_token
                # The legacy 'location' column is also normalised to the
                # short code so all three columns agree.
                location = location_code
                # RBAC: a Checkpoint user can only create events at their own
                # location. Admins (and any non-checkpoint officer) may post
                # to any valid checkpoint code.
                scope = checkpoint_scope(user)
                if scope and location != scope:
                    raise ValueError(
                        f'Checkpoint officers can only record stops at their assigned location ({scope})')
                alerted = c.execute('''SELECT 1 FROM suspect_alerts WHERE person_id=? AND role='Suspect'
                    AND alert_status='Active alert' LIMIT 1''',(person['id'],)).fetchone()
                screen = 'Flagged match' if alerted else 'No active alert'
                action = 'Supervisor contacted' if alerted else 'Cleared'
                # Explicit location metadata: 'location_code' is the canonical
                # short code (South/East/West), 'checkpoint_location' is the
                # human-friendly label (e.g. 'South Checkpoint'). The legacy
                # 'location' column is kept for back-compat and mirrors the
                # short code. When the user picks 'South', both fields line up
                # so the dashboard, identity profile, and activity feed can
                # show the exact originating location without re-joining.
                # (location_code is computed earlier from the normalised
                # location string so even lowercase / trailing-space input is
                # persisted in canonical form.)
                checkpoint_location = f'{location_code} Checkpoint'
                event_id = 'CP-'+str(int(time.time()*1000))[-8:]
                c.execute('''INSERT INTO checkpoint_events(event_id,person_id,location,location_code,
                    checkpoint_location,screening_result,action_taken,notes,purpose_of_visit,
                    current_address,permanent_address,traveler_photo,traveler_docs,
                    guardian_person_id,guardian_name,guardian_relationship,guardian_phone,
                    guardian_address,guardian_occupation,guardian_national_id,guardian_passport_id,
                    guardian_docs,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (event_id,person['id'],location,location_code,checkpoint_location,
                     screen,action,(data.get('notes') or '').strip(),
                     purpose,current_addr,(data.get('permanent_address') or '').strip(),
                     photo['path'],json.dumps(tr_docs),
                     guardian_person['id'] if guardian_person else None,
                     guardian_name,(data.get('guardian_relationship') or '').strip(),
                     (data.get('guardian_phone') or '').strip(),
                     (data.get('guardian_address') or '').strip(),
                     (data.get('guardian_occupation') or '').strip(),
                     (data.get('guardian_national_id') or '').strip().upper(),
                     (data.get('guardian_passport_id') or '').strip().upper(),
                     json.dumps(gd_docs),user['id']))
                audit(c,user,'CREATE','checkpoint_event',event_id,
                      f"{location}:{screen} for {person['person_id']}"); c.commit()
                result = {'event_id':event_id,'person_id':person['person_id'],'location':location,
                          'location_code':location_code,
                          'checkpoint_location':checkpoint_location,
                          'screening_result':screen,'action_taken':action,'alerted':bool(alerted),
                          'guardian_person_id':guardian_person['person_id'] if guardian_person else None,
                          'traveler_docs':len(tr_docs),'guardian_docs':len(gd_docs),
                          'identity':identity_result(c,data,person)}
            elif p.path == '/api/stations':
                data = body_json(self)
                station = register_station(c, user, data)
                audit(c, user, 'CREATE', 'police_station', station['station_id'], station['code'])
                c.commit()
                result = {'station': station}
            elif p.path == '/api/officers':
                ctype = self.headers.get('Content-Type', '')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                officer = register_officer(c, user, fields, files)
                audit(c, user, 'CREATE', 'officer', officer['service_id'],
                      f"{officer['full_name']} @ {officer['station_id']}")
                c.commit()
                result = {'service_id': officer['service_id'], 'officer': officer}
            elif p.path == '/api/officers/promotions':
                # HR Directorate: a promotion nomination awaiting commander
                # verification (the green badge on the Police Officers page).
                data = body_json(self)
                promotion = register_promotion(c, user, data)
                audit(c, user, 'CREATE', 'officer_promotion', promotion['nomination_id'],
                      f"{promotion.get('service_id')} {promotion.get('current_rank')} -> "
                      f"{promotion.get('proposed_rank')}")
                c.commit()
                result = {'nomination_id': promotion['nomination_id'], 'promotion': promotion}
            elif p.path == '/api/officers/discipline':
                # HR Directorate: misconduct / suspension / demotion record
                # (the red badge on the Police Officers page).
                data = body_json(self)
                action = register_discipline(c, user, data)
                audit(c, user, 'CREATE', 'officer_discipline', action['action_id'],
                      f"{action.get('service_id')} {action.get('action_type')} · {action.get('status')}")
                c.commit()
                result = {'action_id': action['action_id'], 'discipline': action}
            elif p.path == '/api/crimes':
                ctype = self.headers.get('Content-Type', '')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                crime = register_crime(c, user, fields, files)
                audit(c, user, 'CREATE', 'crime_incident', crime['file_number'], crime.get('category') or '')
                c.commit()
                result = {'file_number': crime['file_number'], 'crime': crime}
            elif p.path == '/api/vehicles':
                ctype = self.headers.get('Content-Type', '')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                helpers = {
                    'normalise_choice': normalise_choice,
                    'resolve_officer_row': resolve_officer_row,
                    'save_upload_validated': save_upload_validated,
                    'OFFICER_IMAGE_EXTS': OFFICER_IMAGE_EXTS,
                }
                vehicle = register_vehicle(c, user, fields, files, helpers)
                audit(c, user, 'CREATE', 'vehicle', vehicle['vehicle_id'], vehicle.get('plate_number') or '')
                c.commit()
                result = {'vehicle_id': vehicle['vehicle_id'], 'vehicle': vehicle}
            elif p.path.startswith('/api/vehicles/') and p.path.endswith('/status'):
                vid = p.path.split('/')[3]
                data = body_json(self)
                helpers = {'normalise_choice': normalise_choice}
                vehicle = update_vehicle_alert(c, user, vid, data, helpers)
                audit(c, user, 'UPDATE', 'vehicle', vid, vehicle.get('security_alert') or '')
                c.commit()
                result = {'vehicle': vehicle}
            elif p.path == '/api/conduct/submit':
                # Station commanders submit promotion recommendations or
                # misconduct reports. The status always defaults to
                # 'Submitted to HR' — the file enters the HR queue.
                ctype = self.headers.get('Content-Type', '')
                if ctype.startswith('multipart/form-data'):
                    fields, files = parse_multipart(self)
                else:
                    fields, files = body_json(self), {}
                action = submit_conduct_action(c, user, fields, files)
                audit(c, user, 'CREATE', 'conduct_action', action['action_id'],
                      f"{action['action_type']} / {action['classification']} "
                      f"for {action['officer_service_id']}")
                c.commit()
                result = {'action_id': action['action_id'], 'action': action,
                          'status': action['status']}
            elif p.path.startswith('/api/conduct/') and p.path.endswith('/review'):
                # HR review desk — restricted to Officer Registration Office
                # / HR staff by the module gate above. Approving a Rank
                # Advancement / Rank Demotion automatically updates
                # officers.rank and writes an immutable service history row.
                aid = p.path.split('/')[3]
                row = c.execute('SELECT * FROM officer_conduct_actions WHERE action_id=?',
                                (aid,)).fetchone()
                if not row:
                    self.send_json(404, {'error': 'Conduct action file not found'}); c.close(); return
                data = body_json(self)
                action = review_conduct_action(c, user, row, data)
                audit(c, user, 'REVIEW', 'conduct_action', aid,
                      f"status -> {action['status']}"
                      + (f" · rank {action['rank_update']['from']} -> {action['rank_update']['to']}"
                         if action.get('rank_update') else ''))
                c.commit()
                result = {'action_id': aid, 'action': action, 'status': action['status']}
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(201, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except LookupError as e:
            if c: c.close()
            self.send_json(404,{'error':str(e)})
        except ValueError as e:
            if c: c.close()
            self.send_json(400,{'error':str(e)})
        except sqlite3.IntegrityError as e:
            if c: c.close()
            self.send_json(409,{'error':'Database constraint failed','details':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

    # ---- PATCH (profile updates / dynamic record updates) --------------------
    def do_PATCH(self):
        c = None
        try:
            p = urlparse(self.path)
            user = require_auth(self); data = body_json(self); c = db()
            # RBAC: only admins can edit user records; CID module updates CID cases.
            if p.path.startswith('/api/admin/users'):
                require_module(user, 'admin')
            elif p.path.startswith('/api/crime-cases'):
                require_module(user, 'cid')
            elif p.path.startswith('/api/officers/'):
                # HR Directorate writes (promotion verification, …) belong to
                # the Police Officers Registration Office module.
                require_module(user, 'officers')
            if p.path.startswith('/api/persons/'):
                pid = p.path.split('/')[3]
                row = c.execute('SELECT * FROM persons WHERE person_id=?',(pid,)).fetchone()
                if not row: self.send_json(404,{'error':'Person not found'}); c.close(); return
                updates, params = [], []
                for f in PERSON_FIELDS:
                    val = data.get(f)
                    if val is not None and str(val).strip()!='':
                        updates.append(f'{f}=?'); params.append(str(val).strip())
                if updates:
                    updates.append('updated_at=CURRENT_TIMESTAMP'); params.append(row['id'])
                    c.execute(f"UPDATE persons SET {', '.join(updates)} WHERE id=?", params)
                    audit(c,user,'UPDATE','person',pid)
                c.commit()
                result = {'person': rowdict(c.execute('SELECT * FROM persons WHERE id=?',(row['id'],)).fetchone())}
            elif p.path.startswith('/api/crime-cases/'):
                cid = p.path.split('/')[3]
                row = c.execute('SELECT id FROM crime_cases WHERE case_id=?',(cid,)).fetchone()
                if not row: self.send_json(404,{'error':'Case not found'}); c.close(); return
                updates, params = [], []
                for f in ('category','location','status','incident_summary','notes'):
                    val = data.get(f)
                    if val is not None: updates.append(f'{f}=?'); params.append(val)
                if updates:
                    params.append(row['id'])
                    c.execute(f"UPDATE crime_cases SET {', '.join(updates)} WHERE id=?", params)
                    audit(c,user,'UPDATE','crime_case',cid)
                c.commit(); result = {'case_id':cid,'updated':True}
            elif p.path.startswith('/api/officers/promotions/'):
                # Commander verification of a promotion nomination.
                nomination_id = p.path.split('/')[4]
                promotion = verify_promotion(c, user, nomination_id, data)
                audit(c, user, 'UPDATE', 'officer_promotion', nomination_id,
                      promotion['verification_status'])
                c.commit()
                result = {'nomination_id': nomination_id, 'promotion': promotion,
                          'updated': True}
            elif p.path.startswith('/api/officers/discipline/'):
                # HR Directorate update of a disciplinary action (status,
                # severity, suspension window, demotion target). Confirmed
                # demotions / suspensions are applied to the officer record.
                action_id = p.path.split('/')[4]
                action = update_discipline(c, user, action_id, data)
                audit(c, user, 'UPDATE', 'officer_discipline', action_id, action['status'])
                c.commit()
                result = {'action_id': action_id, 'discipline': action, 'updated': True}
            elif p.path.startswith('/api/admin/users/'):
                # Update an existing user — change role, branch, location, password, active.
                # /api/admin/users/<id> -> split('/') -> ['', 'api', 'admin', 'users', '<id>']
                parts = p.path.split('/')
                uid = parts[4] if len(parts) > 4 else ''
                if not uid or not uid.isdigit():
                    self.send_json(400, {'error': 'user id required'}); c.close(); return
                row = c.execute('SELECT * FROM users WHERE id=?', (int(uid),)).fetchone()
                if not row: self.send_json(404, {'error': 'User not found'}); c.close(); return
                updates, params = [], []
                for f in ('display_name', 'branch'):
                    if f in data and str(data[f]).strip():
                        updates.append(f'{f}=?'); params.append(str(data[f]).strip())
                if 'role' in data:
                    # Spec step 1: accept both the legacy compound forms
                    # and the canonical 'checkpoint_officer' alias — and
                    # ANY accepted checkpoint spelling. Aliases are
                    # normalised to 'checkpoint_officer'; the location
                    # embedded in the alias ('CheckpointWest' -> 'West')
                    # is carried into location_scope so it is preserved.
                    role, derived_scope = normalize_incoming_role(str(data['role']).strip())
                    accepted_roles = set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}
                    if role not in accepted_roles:
                        raise ValueError(f'role must be one of {", ".join(sorted(accepted_roles))} '
                                         '(Checkpoint aliases such as CheckpointSouth / cp_south are also accepted)')
                    updates.append('role=?'); params.append(role)
                    # If the new role dictates a location_scope, refresh
                    # it. For 'checkpoint_officer' (the canonical alias)
                    # the table-lookup default is empty; in that case
                    # PRESERVE the existing location_scope so a PATCH
                    # from 'CheckpointSouth' -> 'checkpoint_officer'
                    # does not wipe the officer's location. The
                    # caller can still pass an explicit
                    # 'location_scope' to override.
                    if 'location_scope' not in data:
                        default_scope = derived_scope or ROLE_LOCATION_SCOPE.get(role)
                        if default_scope:
                            updates.append('location_scope=?'); params.append(default_scope)
                        # else: keep the existing scope (no-op).
                if 'location_scope' in data:
                    scope = canonical_location_scope(data['location_scope'])
                    if scope and scope not in CHECKPOINT_LOCATIONS:
                        raise ValueError(f'location_scope must be one of {", ".join(CHECKPOINT_LOCATIONS)}')
                    updates.append('location_scope=?'); params.append(scope)
                if 'active' in data:
                    updates.append('active=?'); params.append(1 if data['active'] else 0)
                if data.get('password'):
                    if len(str(data['password'])) < 6:
                        raise ValueError('password must be at least 6 characters')
                    updates.append('password_hash=?'); params.append(password_hash(str(data['password'])))
                if updates:
                    params.append(int(uid))
                    c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
                    audit(c, user, 'UPDATE', 'user', uid)
                c.commit()
                updated = rowdict(c.execute('SELECT * FROM users WHERE id=?', (int(uid),)).fetchone())
                result = {'user': user_view(updated)}
            else:
                self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(200, result)
        except PermissionError as e:
            if c: c.close()
            self.send_json(401,{'error':str(e)})
        except LookupError as e:
            if c: c.close()
            self.send_json(404,{'error':str(e)})
        except ValueError as e:
            if c: c.close()
            self.send_json(400,{'error':str(e)})
        except Exception as e:
            if c: c.close()
            self.send_json(500,{'error':str(e)})

def _pids_listening_on(port):
    """Best-effort, cross-platform list of PIDs listening on TCP `port`."""
    pids = set()
    try:
        if os.name == 'nt':
            pass
        else:
            try:
                out = subprocess.run(['lsof', '-ti', f'tcp:{port}'],
                                     capture_output=True, text=True, timeout=20).stdout
                pids |= {int(x) for x in out.split()}
            except (FileNotFoundError, subprocess.SubprocessError, ValueError):
                pass
            if not pids:                                      # `lsof` may be absent
                try:
                    out = subprocess.run(['ss', '-ltnp'], capture_output=True,
                                         text=True, timeout=20).stdout
                    for line in out.splitlines():
                        if f':{port}' in line and 'LISTEN' in line.upper():
                            pids |= {int(m) for m in re.findall(r'pid=(\d+)', line)}
                except (FileNotFoundError, subprocess.SubprocessError, ValueError):
                    pass
    except Exception:
        pass
    pids.discard(os.getpid())
    return pids


def terminate_listener(port):
    """Kill whatever is holding `port` so a restart always wins the bind.

    The usual cause of "port 8001 is running old code" is that the previous
    server was never stopped: the new process crashes with 'Address already in
    use', nobody reads the message, and the stale process keeps serving.
    Set SENTINEL_NO_PORT_TAKEOVER=1 to disable the eviction.
    """
    if os.environ.get('SENTINEL_NO_PORT_TAKEOVER'):
        return []
    killed = []
    for pid in sorted(_pids_listening_on(port)):
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                               capture_output=True, timeout=20)
            else:
                os.kill(pid, signal.SIGTERM)
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                    time.sleep(0.2)
                else:
                    os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except Exception:
            pass
    return killed


def bind_server(port):
    """Bind `port`, evicting a stale listener first if the bind is refused."""
    last = None
    for attempt in range(3):
        try:
            return ThreadingHTTPServer(('0.0.0.0', port), API)
        except OSError as exc:
            last = exc
            # 98=EADDRINUSE(Linux) 48=EADDRINUSE(macOS) 10048=WSAEADDRINUSE(Windows)
            if getattr(exc, 'errno', None) not in (48, 98, 10048) or attempt == 2:
                raise
            evicted = terminate_listener(port)
            print(f'  port {port} is held by a stale process '
                  f'-> evicted {evicted or "(owner not found)"}; rebinding')
            time.sleep(1.0)
    raise last


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT','8001'))
    if not review_lock_armed():
        # Refuse to serve rather than quietly answer approvals unlocked.
        raise SystemExit('FATAL: fingerprint review lock failed its self-test; '
                         'refusing to start an unlocked server.')
    print(f'Sentinel backend listening on 0.0.0.0:{port}')
    print(f'  build {BUILD_TAG}')
    print(f'  fingerprint review window: {FINGERPRINT_REVIEW_WINDOW_HOURS}h '
          f'(admin/SystemAdmin bypasses, every other role is locked)')
    print(f'  {review_lock_self_test()}')
    print(f'  clearance reasons: {", ".join(CLEARANCE_REASONS)}')
    print(f'  pid {os.getpid()}  started {SERVER_STARTED_AT}')
    bind_server(port).serve_forever()
