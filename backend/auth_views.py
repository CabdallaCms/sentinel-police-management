"""Sentinel authentication, sessions and RBAC.

Session lifecycle (create / lookup / destroy), request authentication,
role normalisation, module + permission enforcement, location scoping,
the fingerprint 12-hour review gate and the audit writer — moved verbatim
out of ``backend/server.py``. Endpoint URLs, payloads and role semantics
are unchanged.

Standard library only.
"""
import datetime, re, secrets, time
from config import *
from utils import *
from database import *


def canonical_api_path(path):
    """Resolve the /api/fingerprint/applications alias onto /api/clearance-applications."""
    if path == FINGERPRINT_API_ALIAS or path.startswith(FINGERPRINT_API_ALIAS + '/'):
        return CLEARANCE_API + path[len(FINGERPRINT_API_ALIAS):]
    return path


def _role_key(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def is_fingerprint_officer(user):
    """True for Fingerprint Unit officers (canonical role or the spec alias)."""
    if not user:
        return False
    keys = {_role_key(user.get('role')), _role_key(user.get('role_alias'))}
    keys.add(_role_key(normalize_role(user.get('role') or '')))
    return bool(keys & FINGERPRINT_ROLE_KEYS)


def is_admin_user(user):
    """True only for administrators — the ONLY role allowed to bypass the
    mandatory 12-hour fingerprint review window.

    Accepts the canonical 'SystemAdmin' role and the spec's 'admin' alias
    (case/format-insensitive). Everything else (`FingerprintUnit`,
    `fingerprint_officer`, …) is a standard officer and is gated.
    """
    if not user:
        return False
    role = user.get('role')
    keys = {_role_key(role), _role_key(user.get('role_alias')),
            _role_key(normalize_role(role or ''))}
    return bool(keys & ADMIN_ROLE_KEYS)


def review_gate_decision(app_row, user):
    """Gate an approval request. Returns None when it may proceed, otherwise
    (status_code, payload) for the rejection.

    FAIL-CLOSED — mirroring the mandated implementation:

        is_admin  = user.role in ('admin', 'SystemAdmin')
        if not is_admin:
            if not created_at:                -> 400 (missing stamp = locked)
            hours_elapsed = (utc_now - created_at) / 3600
            if hours_elapsed < 12.0:          -> 400

    The decision uses ONLY the stored row and the server-side role, never
    anything the client supplied.
    """
    if is_admin_user(user):
        return None
    created_at = parse_created_at((app_row or {}).get('created_at'))
    reason = 'submission timestamp missing' if created_at is None else 'review window open'
    if created_at is not None:
        hours_elapsed = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds() / 3600.0
        if hours_elapsed >= float(FINGERPRINT_REVIEW_WINDOW_HOURS):
            return None
    payload = {
        'detail': REVIEW_LOCK_MESSAGE,
        'error': REVIEW_LOCK_MESSAGE,
        'code': 'review_period_active',
        'reason': reason,
        'review_window_hours': FINGERPRINT_REVIEW_WINDOW_HOURS,
        'submitted_at': (app_row or {}).get('created_at'),
    }
    if created_at is not None:
        payload['hours_elapsed'] = round(max(0.0, hours_elapsed), 2)
        payload['hours_remaining'] = round(float(FINGERPRINT_REVIEW_WINDOW_HOURS) - max(0.0, hours_elapsed), 2)
        payload['review_eligible_at'] = (created_at + datetime.timedelta(
            hours=FINGERPRINT_REVIEW_WINDOW_HOURS)).strftime('%Y-%m-%dT%H:%M:%SZ')
    if (app_row or {}).get('application_id'):
        payload['application_id'] = app_row['application_id']
    return 400, payload


def review_lock_self_test():
    """Prove at boot that the mandatory review gate is armed. Returns a log line."""
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = lambda **kw: (now - datetime.timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')
    officer = {'role': 'FingerprintUnit'}
    alias_officer = {'role': 'fingerprint_officer'}
    admin = {'role': 'SystemAdmin'}
    admin_alias = {'role': 'admin'}
    cases = [
        ('officer @0h blocked', {'application_id': 'X', 'created_at': stamp(hours=0)}, officer, True),
        ('officer @11.5h blocked', {'application_id': 'X', 'created_at': stamp(hours=11.5)}, officer, True),
        ('officer @13h allowed', {'application_id': 'X', 'created_at': stamp(hours=13)}, officer, False),
        ('officer, missing stamp blocked', {'application_id': 'X', 'created_at': None}, officer, True),
        ('officer, bad stamp blocked', {'application_id': 'X', 'created_at': 'not-a-date'}, officer, True),
        ('fingerprint_officer alias blocked', {'application_id': 'X', 'created_at': stamp(hours=1)}, alias_officer, True),
        ('SystemAdmin bypasses', {'application_id': 'X', 'created_at': stamp(hours=0)}, admin, False),
        ('admin alias bypasses', {'application_id': 'X', 'created_at': stamp(hours=0)}, admin_alias, False),
    ]
    failures = []
    for name, row, user, expect_rejected in cases:
        rejected = review_gate_decision(row, user) is not None
        if rejected != expect_rejected:
            failures.append(name)
    return ('review lock self-test: PASS (8/8 cases)' if not failures
            else 'review lock self-test: FAILED -> ' + ', '.join(failures))


# True once the boot self-test has been run and passed. /api/health reports it,
# so a health response without build == BUILD_TAG / review_lock_active == true
# means the process answering is NOT this build — kill it and start this one.
# Resolved lazily because the helpers it exercises are defined below.
_REVIEW_LOCK_ARMED = None


def review_lock_armed():
    """Run the review-lock self-test once and cache the verdict."""
    global _REVIEW_LOCK_ARMED
    if _REVIEW_LOCK_ARMED is None:
        _REVIEW_LOCK_ARMED = review_lock_self_test().startswith('review lock self-test: PASS')
    return _REVIEW_LOCK_ARMED


def normalise_reason(value):
    """Return the canonical CLEARANCE_REASONS spelling for `value`, or None."""
    s = (value or '').strip()
    for reason in CLEARANCE_REASONS:
        if s.lower() == reason.lower():
            return reason
    return None


def fingerprint_review_state(app, now=None):
    """12-hour review-window state for a clearance application row.

    `review_locked` is True while `created_at + 12h` is still in the future.
    Fail-closed: a row with a missing / unparseable `created_at` cannot prove
    that the mandatory window has elapsed, so it stays locked. Admins remain
    exempt — the bypass is applied by the caller, not by this helper.
    """
    hours = FINGERPRINT_REVIEW_WINDOW_HOURS
    created = parse_stamp(app.get('created_at') if app else None)
    if created is None:
        return {'review_window_hours': hours, 'review_eligible_at': None,
                'hours_elapsed': None, 'hours_remaining': float(hours),
                'review_locked': True, 'submitted_at_missing': True,
                'submitted_at': app.get('created_at') if app else None}
    now_ts = time.time() if now is None else now
    elapsed = max(0.0, (now_ts - created) / 3600.0)
    remaining = max(0.0, hours - elapsed)
    return {
        'review_window_hours': hours,
        'submitted_at': app.get('created_at'),
        'review_eligible_at': datetime.datetime.fromtimestamp(
            created + hours * 3600, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hours_elapsed': round(elapsed, 2),
        'hours_remaining': round(remaining, 2),
        'review_locked': remaining > 0,
    }


# A role is a Checkpoint officer iff:
#   - it normalises to ROLE_CHECKPOINT_OFFICER (any accepted spelling), OR
#   - it starts with 'Checkpoint' (legacy compound form), OR
#   - it includes the 'cp' / 'Checkpoint' substring (defensive against
#     future role names that follow the same family).
def is_checkpoint_role(role):
    if not role:
        return False
    r = str(role)
    if r in CHECKPOINT_ROLE_ALIASES:
        return True
    if r.lower() in CHECKPOINT_ROLE_ALIASES:
        return True
    if r.startswith('Checkpoint') or r.startswith('checkpoint'):
        return True
    if 'cp' in r.lower().split('_') or 'checkpoint' in r.lower():
        return True
    return False

def canonical_unit_role(role):
    """Resolve a unit-role alias ('admin', 'fingerprint_officer', ...) to the
    canonical stored role ('SystemAdmin', 'FingerprintUnit', ...).

    The spec refers to the reviewer roles by their snake_case names
    (`admin` / `fingerprint_officer`), so a user row stored in either
    spelling must resolve to the same canonical role everywhere —
    module gates, visibility flags, role labels and the 12-hour review
    window. Unknown roles pass through unchanged.
    """
    if not role:
        return role
    r = str(role).strip()
    if r in UNIT_ROLE_ALIASES:
        return UNIT_ROLE_ALIASES[r]
    key = _role_key(r)
    for alias, canonical in UNIT_ROLE_ALIASES.items():
        if _role_key(alias) == key:
            return canonical
    return r


def normalize_role(role):
    """Map any accepted Checkpoint-officer spelling to the canonical
    normalised form ('checkpoint_officer') and any unit alias
    ('fingerprint_officer', 'admin', ...) to its canonical role.
    All other roles pass through unchanged. This is the single source
    of truth for the spec-mandated role string normalization.
    """
    if not role:
        return role
    r = str(role)
    # Unit aliases first: 'fingerprint_officer' -> 'FingerprintUnit', ...
    canonical = canonical_unit_role(r)
    if canonical != r:
        return canonical
    if r in CHECKPOINT_ROLE_ALIASES:
        return CHECKPOINT_ROLE_ALIASES[r]
    if r.lower() in CHECKPOINT_ROLE_ALIASES:
        return CHECKPOINT_ROLE_ALIASES[r.lower()]
    # Defensive: any 'Checkpoint*' / 'checkpoint_*' / 'cp.*' spelling.
    if r.startswith('Checkpoint') and r.endswith(('South', 'East', 'West')):
        return ROLE_CHECKPOINT_OFFICER
    if r.lower().startswith('checkpoint') or 'cp' in r.lower().split('_'):
        return ROLE_CHECKPOINT_OFFICER
    return r


def spec_role_for(role):
    """Snake-case spec alias for a canonical role (never defaults to admin)."""
    canonical = canonical_unit_role(role)
    if canonical in SPEC_ROLE_ALIASES:
        return SPEC_ROLE_ALIASES[canonical]
    if is_checkpoint_role(role):
        return ROLE_CHECKPOINT_OFFICER
    return SPEC_ROLE_DEFAULT


def user_permissions(user):
    """Every capability permission a user holds (raw role + aliases)."""
    if not user:
        return set()
    role = user.get('role') or ''
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    perms |= set(ROLE_PERMISSIONS.get(normalize_role(role), set()))
    perms |= set(ROLE_PERMISSIONS.get(canonical_unit_role(role), set()))
    return perms


def has_permission(user, permission):
    return permission in user_permissions(user)


def require_permission(user, permission):
    """Raise PermissionError unless the user holds `permission`."""
    if has_permission(user, permission):
        return
    role = (user or {}).get('role') or ''
    raise PermissionError(
        f'Requires {permission} — restricted to {ROLE_LABELS.get(role, role)}')


def is_chief_commander(user):
    return bool(user) and canonical_unit_role(user.get('role') or '') == ROLE_CHIEF


def canonical_location_scope(scope):
    """Map a location value ('south', 'South Checkpoint', ' SOUTH '...) to the
    canonical short code ('South' / 'East' / 'West'). Returns the trimmed
    original when it does not match any known location (callers validate)."""
    s = str(scope or '').strip()
    if not s:
        return None
    for code in CHECKPOINT_LOCATIONS:
        if s.lower() == code.lower():
            return code
    first = s.split()[0]
    for code in CHECKPOINT_LOCATIONS:
        if first.lower() == code.lower():
            return code
    return s


def normalize_incoming_role(role):
    """Normalise a role string supplied on user create/update.

    Every accepted Checkpoint-officer spelling ('CheckpointSouth',
    'checkpoint_south', 'cp_south', 'cp.east', 'Checkpoint Officer
    (West)', 'checkpoint_officer', ...) is mapped to the canonical
    'checkpoint_officer'. All other canonical roles pass through
    unchanged. Returns (canonical_role, derived_location_scope_or_None)
    — the derived scope is pulled from the alias itself ('cp_south' ->
    'South') so normalizing NEVER loses the officer's location.
    Unit aliases are canonicalised too: 'fingerprint_officer' is stored as
    'FingerprintUnit' and 'admin' as 'SystemAdmin'.
    """
    r = str(role or '').strip()
    if not r:
        return r, None
    # 'fingerprint_officer' -> 'FingerprintUnit', 'admin' -> 'SystemAdmin', ...
    canonical = canonical_unit_role(r)
    if canonical != r:
        return canonical, None
    if r in set(ALL_ROLES) | {ROLE_CHECKPOINT_OFFICER}:
        derived = ROLE_LOCATION_SCOPE.get(r) or None
        if is_checkpoint_role(r):
            return ROLE_CHECKPOINT_OFFICER, derived
        return r, None
    if is_checkpoint_role(r):
        derived = None
        rl = r.lower()
        for code in CHECKPOINT_LOCATIONS:
            if code.lower() in rl:
                derived = code
                break
        return ROLE_CHECKPOINT_OFFICER, derived
    return r, None


def user_view(user):
    """Return the public-facing user payload (no password hash) with RBAC info.

    Surfaces BOTH the raw stored role (e.g. 'CheckpointSouth') AND the
    normalised alias ('checkpoint_officer') so the frontend can use
    either form. The raw role is preserved in 'role' for back-compat
    (existing checks use role === 'CheckpointSouth' etc.); the
    canonical normalized form is in 'role_alias' for the spec-mandated
    unified checks.
    """
    raw_role = user.get('role') or ''
    # Spec step 1: normalise the role string. The session payload now
    # carries the canonical 'checkpoint_officer' alias as 'role_alias'
    # for any Checkpoint officer, regardless of the underlying
    # storage form.
    role_alias = normalize_role(raw_role)
    # Snake-case spec alias ('fingerprint_officer' / 'admin' / ...).
    spec_role = spec_role_for(raw_role)
    scope = user.get('location_scope') or ROLE_LOCATION_SCOPE.get(raw_role)
    # Normalise legacy/derived scope for display: checkpoint users see a
    # human-friendly location label, everyone else sees their branch.
    if raw_role.startswith('Checkpoint') and raw_role.endswith(('South', 'East', 'West')):
        location = raw_role[len('Checkpoint'):]
    else:
        location = scope or user.get('branch') or ''
    # The module set must resolve for BOTH the raw stored role AND the
    # normalised alias. Without the alias lookup a user stored as
    # 'cp_south' / 'checkpoint_officer' would get modules: [] and the
    # frontend would never fetch /api/checkpoint-events (the "0 records"
    # bug).
    modules = set(ROLE_MODULES.get(raw_role, set())) | \
        set(ROLE_MODULES.get(role_alias, set())) | \
        set(ROLE_MODULES.get(spec_role, set()))
    return {
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'role': raw_role,
        'role_alias': role_alias,
        # Spec-facing snake_case name ('fingerprint_officer', 'admin', ...).
        # Never defaults to 'admin': an unknown role is treated as a standard
        # officer, which keeps the 12-hour review lock fail-closed.
        'role_spec': spec_role,
        'spec_role': spec_role,
        'role_label': ROLE_LABELS.get(raw_role, raw_role),
        'branch': user.get('branch') or '',
        'location_scope': scope,
        'location': location,
        'modules': sorted(modules),
        'permissions': sorted(user_permissions(user)),
        'active': bool(user.get('active', 1)),
    }


def require_role(user, role):
    """Raise PermissionError unless the user's role matches."""
    if user.get('role') != role:
        raise PermissionError(f'Requires {ROLE_LABELS.get(role, role)} role')


def require_module(user, module):
    """Raise PermissionError unless the user can access the given module/page.

    Spec step 1: the module check is now also performed against the
    normalised role alias. A Checkpoint officer whose stored role is
    'CheckpointSouth' (or 'cp_south' or any other accepted spelling)
    is treated exactly like one whose role is 'checkpoint_officer'.
    """
    role = user.get('role') or ''
    # Try the raw role first, then the normalised alias — so the
    # module set is resolved for both spellings of the same logical
    # role.
    modules = ROLE_MODULES.get(role, set())
    if module in modules:
        return
    normalised = normalize_role(role)
    modules = ROLE_MODULES.get(normalised, set())
    if module in modules:
        return
    raise PermissionError(
        f'Restricted to {ROLE_LABELS.get(role, role)}')


def user_module_set(user):
    """Every module a user can reach, resolved for the raw role AND its aliases.

    `require_auth` hands out `user_view()` payloads (which already carry a
    resolved `modules` list); internal callers sometimes pass the raw row, so
    the role is re-resolved here to keep the answer identical either way.
    """
    if not user:
        return set()
    mods = set(user.get('modules') or [])
    role = user.get('role') or ''
    mods |= set(ROLE_MODULES.get(role, set()))
    mods |= set(ROLE_MODULES.get(normalize_role(role), set()))
    mods |= set(ROLE_MODULES.get(spec_role_for(role), set()))
    return mods


def require_any_module(user, modules):
    """Raise PermissionError unless the user holds at least ONE of `modules`.

    Departmental analytics are shared surfaces: the CID bundle is read by the
    Fingerprint / Crime / Checkpoint / Airport units, so an any-of gate is the
    correct RBAC shape (each caller still only receives its own sections).
    """
    allowed = set(modules or ())
    if user_module_set(user) & allowed:
        return
    role = (user or {}).get('role') or ''
    raise PermissionError(
        f'Restricted to {ROLE_LABELS.get(role, role)}')


def checkpoint_scope(user):
    """Return the location code this user is allowed to see for checkpoint data.

    Admins see all locations (None). Checkpoint users see only their own.
    Other unit users see no checkpoint data (empty string).
    """
    role = user.get('role') or ''
    if role == ROLE_ADMIN or canonical_unit_role(role) in (ROLE_ADMIN, ROLE_CHIEF):
        return None
    # Spec step 3: prefer the stored location_scope on the user
    # record over the role-based derivation. A PATCH from
    # 'CheckpointSouth' to 'checkpoint_officer' must NOT wipe the
    # officer's location. The location_scope column is the
    # authoritative source for any Checkpoint officer.
    stored_scope = user.get('location_scope')
    if stored_scope and stored_scope in CHECKPOINT_LOCATIONS:
        return stored_scope
    # Otherwise, derive the scope from the role (legacy code path).
    aliases_to_try = [role, role.lower(), normalize_role(role)]
    for r in aliases_to_try:
        if r in ROLE_LOCATION_SCOPE:
            return ROLE_LOCATION_SCOPE[r] or ''
    # Last-ditch: if the role is a Checkpoint officer but the scope
    # lookup failed, derive the scope from the role string itself
    # ('CheckpointSouth' -> 'South', 'CheckpointEast' -> 'East',
    # 'CheckpointWest' -> 'West', 'cp_west' -> 'West', etc.).
    if is_checkpoint_role(role):
        rl = role.lower()
        for code in CHECKPOINT_LOCATIONS:
            if code.lower() in rl:
                return code
    return ''


def filter_visibility(user):
    """Small dict of RBAC booleans used by the /api/me view and frontend."""
    role = user.get('role') or ''
    # Resolve aliases first so 'admin' / 'system_admin' behave like the
    # canonical SystemAdmin row.
    is_admin = canonical_unit_role(role) == ROLE_ADMIN
    chief = canonical_unit_role(role) == ROLE_CHIEF
    return {
        'is_admin': is_admin,
        'is_chief_commander': chief,
        'can_manage_users': is_admin,
        'can_view_analytics': is_admin,
        'can_view_global_analytics': has_permission(user, PERM_ANALYTICS_GLOBAL),
        'can_manage_stations': is_admin or has_permission(user, PERM_STATIONS_MANAGE),
        'checkpoint_scope': checkpoint_scope(user),
    }


def session_token_from_cookie(handler):
    """Read the sentinel_session cookie (fallback to the Bearer header)."""
    raw = handler.headers.get('Cookie','') or ''
    for part in raw.split(';'):
        name, _, value = part.partition('=')
        if name.strip() == 'sentinel_session':
            return value.strip()
    return ''


def lookup_session(token):
    """Resolve a token from the persistent sessions table.

    Sessions used to live only in the in-memory TOKENS map, so every server
    restart invalidated every signed-in browser and /api/me started answering
    401 — which pushed the frontends into their offline fallbacks. Sessions
    are now stored in SQLite and survive a restart.
    """
    if not token:
        return None
    c = db()
    try:
        row = c.execute('SELECT user_id FROM sessions WHERE token=?', (token,)).fetchone()
    finally:
        c.close()
    return row['user_id'] if row else None


def create_session(user_id):
    """Issue a new session token (memory cache + persistent row)."""
    token = secrets.token_urlsafe(32)
    TOKENS[token] = user_id
    c = db()
    try:
        c.execute('INSERT OR REPLACE INTO sessions(token,user_id) VALUES(?,?)', (token, user_id))
        c.commit()
    finally:
        c.close()
    return token


def destroy_session(token):
    """Revoke a session (logout / stale-token cleanup)."""
    if not token:
        return
    TOKENS.pop(token, None)
    c = db()
    try:
        c.execute('DELETE FROM sessions WHERE token=?', (token,))
        c.commit()
    finally:
        c.close()


def require_auth(handler):
    token = (handler.headers.get('Authorization','') or '').replace('Bearer ','')
    if not token:
        token = session_token_from_cookie(handler)
    if not token: raise PermissionError('Authentication required')
    user_id = TOKENS.get(token)
    if not user_id:
        user_id = lookup_session(token)
        if user_id: TOKENS[token] = user_id
    if not user_id: raise PermissionError('Authentication required')
    c = db()
    user = rowdict(c.execute(
        'SELECT id,username,display_name,role,branch,location_scope,active '
        'FROM users WHERE id=? AND active=1',(user_id,)).fetchone())
    c.close()
    if not user: raise PermissionError('Authentication required')
    return user_view(user)

def audit(c, user, action, entity, entity_id, details=''):
    c.execute('INSERT INTO audit_events(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',
              (user['id'], action, entity, entity_id, details))
