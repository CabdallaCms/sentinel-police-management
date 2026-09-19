"""Sentinel analytics and dashboards.

Departmental bundles (CID · Officers · Vehicles · Stations), the global
and per-module analytics builders and the role-aware dashboard cards +
activity feed — moved verbatim out of ``backend/server.py``.

Standard library only.
"""
import datetime, time
from vehicles import (
    VEHICLE_CATEGORIES, VEHICLE_OP_STATUSES, VEHICLE_ALERTS,
)
from config import *
from utils import *
from database import *
from auth_views import *
from case_views import *


def build_analytics(c, user):
    """Aggregate analytics for the Executive Dashboard (admin only)."""
    # --- 1) Operational summary metrics ----------------------------------
    total_persons = c.execute('SELECT COUNT(*) FROM persons').fetchone()[0]
    active_alerts = c.execute(
        "SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0]
    airport_records = c.execute('SELECT COUNT(*) FROM airport_passengers').fetchone()[0]
    fingerprint_records = c.execute('SELECT COUNT(*) FROM clearance_applications').fetchone()[0]
    case_total = c.execute('SELECT COUNT(*) FROM crime_cases').fetchone()[0]
    open_cases = c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0]
    checkpoint_total = c.execute('SELECT COUNT(*) FROM checkpoint_events').fetchone()[0]
    checkpoint_flagged = c.execute(
        "SELECT COUNT(*) FROM checkpoint_events WHERE screening_result='Flagged match'").fetchone()[0]
    summary = {
        'total_central_persons': total_persons,
        'active_suspect_alerts': active_alerts,
        'airport_movements': airport_records,
        'fingerprint_records': fingerprint_records,
        'crime_cases_total': case_total,
        'crime_cases_open': open_cases,
        'checkpoint_events': checkpoint_total,
        'checkpoint_flagged': checkpoint_flagged,
    }

    # --- 2) Crime distribution by location and time-of-day bucket --------
    # "location" of a crime is the location stored on the crime_cases row.
    # time-of-day is bucketed from the created_at timestamp (24h clock).
    crime_rows = c.execute(
        "SELECT location, created_at FROM crime_cases").fetchall()
    by_location = {}
    by_time = {'Morning (06-12)': 0, 'Afternoon (12-18)': 0,
               'Evening (18-24)': 0, 'Night (00-06)': 0}
    for r in crime_rows:
        loc = (r['location'] or 'Unspecified').strip() or 'Unspecified'
        by_location[loc] = by_location.get(loc, 0) + 1
        # created_at is a SQLite 'YYYY-MM-DD HH:MM:SS' string — bucketed by
        # the shared helper so the executive and CID views always agree.
        bucket = time_of_day_bucket(r['created_at'])
        by_time[bucket] = by_time.get(bucket, 0) + 1
    # Pad the matrix so the dashboard has stable axes.
    location_order = sorted(by_location.items(), key=lambda x: -x[1])
    crime_distribution = {
        'by_location': [{'label': k, 'count': v} for k, v in location_order],
        'by_time_of_day': [{'label': k, 'count': by_time.get(k, 0)} for k in
                            ('Morning (06-12)', 'Afternoon (12-18)',
                             'Evening (18-24)', 'Night (00-06)')],
    }

    # --- 3) Checkpoint volume by location and traveler demographics ------
    # Travelers link to a central person; we use the stored date_of_birth
    # to bucket their age at the time of travel.
    def age_to_bucket(age):
        if age is None: return 'Unknown'
        if age < 18: return '<18'
        if age <= 30: return '18-30'
        if age <= 50: return '31-50'
        return '50+'
    today = time.gmtime()
    current_year = today.tm_year
    by_loc = {code: 0 for code in CHECKPOINT_LOCATIONS}
    by_loc_age = {code: {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0}
                  for code in CHECKPOINT_LOCATIONS}
    rows = c.execute('''SELECT ce.location, p.date_of_birth
        FROM checkpoint_events ce JOIN persons p ON p.id=ce.person_id''').fetchall()
    for r in rows:
        loc = (r['location'] or '').strip()
        if loc not in by_loc:
            by_loc[loc] = 0
            by_loc_age[loc] = {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0}
        by_loc[loc] = by_loc.get(loc, 0) + 1
        dob = (r['date_of_birth'] or '').strip()
        age = None
        if len(dob) >= 4 and dob[:4].isdigit():
            age = current_year - int(dob[:4])
        bucket = age_to_bucket(age)
        by_loc_age.setdefault(loc, {'<18': 0, '18-30': 0, '31-50': 0, '50+': 0, 'Unknown': 0})
        by_loc_age[loc][bucket] = by_loc_age[loc].get(bucket, 0) + 1
    volume = {
        'by_location': [{'label': k, 'count': by_loc.get(k, 0)} for k in CHECKPOINT_LOCATIONS],
        'demographics': {loc: [{'label': k, 'count': v.get(k, 0)} for k in
                                ('<18', '18-30', '31-50', '50+', 'Unknown')]
                         for loc, v in by_loc_age.items()},
    }

    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', today),
        'summary': summary,
        'crime_distribution': crime_distribution,
        'checkpoint_volume': volume,
    }


# ---------------------------------------------------------------------------
# Departmental analytics.
#
# The monolithic executive analytics page was split into four departmental
# bundles that are embedded directly in the register they describe:
#
#   GET /api/cid/analytics        — CID directorate (Fingerprint · Crime ·
#                                   Checkpoint · Airport sections)
#   GET /api/officers/analytics   — Police Officers Registration Office (HR)
#   GET /api/vehicles/analytics   — Police Car Registration module
#   GET /api/stations/analytics   — Police Station Master Registry
#   GET /api/analytics?module=…   — the same four builders behind one route
#                                   (module=all returns every bundle the
#                                   caller is entitled to see)
#
# Every bundle returns the same envelope shape so the frontend can render any
# of them with one painter:
#
#   {generated_at, module, role, kpis: [card], charts: {name: series},
#    lists: {name: [row]}, …flat metric keys…}
#
# `kpis` drives the tab-specific summary cards, `charts` the lightweight
# canvas visuals and `lists` the badge lists (green promotion nominations /
# red disciplinary actions / flagged vehicles / unstaffed stations).
# ---------------------------------------------------------------------------

def _generated_at():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _today():
    return time.strftime('%Y-%m-%d', time.gmtime())


def _val(row, key, default=None):
    """Read a column from a sqlite3.Row or a plain dict (None -> default)."""
    if row is None:
        return default
    keys = row.keys() if hasattr(row, 'keys') else ()
    if key not in keys:
        return default
    v = row[key]
    return default if v is None else v


def pct(part, total, digits=1):
    """Percentage of `part` over `total` — 0.0 when the denominator is 0.

    Every rate in the departmental bundles is produced by this one helper so
    the arithmetic (and its rounding) is identical server- and client-side.
    """
    try:
        part = float(part or 0)
        total = float(total or 0)
    except (TypeError, ValueError):
        return 0.0
    if total <= 0:
        return 0.0
    return round((part / total) * 100.0, digits)


def count_by(rows, key, blank='Unspecified', transform=None):
    """Tally a column across rows -> {label: count} (blank/NULL -> `blank`)."""
    counts = {}
    for r in rows:
        v = _val(r, key, '')
        v = str(v).strip()
        if transform:
            v = str(transform(v) or '').strip()
        v = v or blank
        counts[v] = counts.get(v, 0) + 1
    return counts


def series_from_counts(counts, order=(), limit=None):
    """Build a stable [{label, count}] chart series.

    Labels in `order` come first and are ALWAYS present (zero-padded) so the
    canvas axes never jump between renders; any other observed label is
    appended sorted by count desc then alphabetically. `limit` trims the
    trailing (unordered) extras for "top N" charts.
    """
    remaining = dict(counts or {})
    out = []
    for label in order:
        out.append({'label': label, 'count': int(remaining.pop(label, 0) or 0)})
    extras = sorted(remaining.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0])))
    if limit is not None:
        extras = extras[:max(0, limit)]
    for label, n in extras:
        out.append({'label': str(label) or 'Unspecified', 'count': int(n or 0)})
    return out


def sorted_series(counts, limit=None):
    """[{label,count}] sorted by count desc (no fixed axis) for free text."""
    return series_from_counts(counts, (), limit)


def time_of_day_bucket(ts):
    """Bucket a 'YYYY-MM-DD HH:MM:SS' / ISO stamp into a 24-hour band."""
    s = str(ts or '').strip().replace('T', ' ')
    hour = None
    if len(s) >= 13 and s[11:13].isdigit():
        hour = int(s[11:13])
    if hour is None:
        return 'Unspecified'
    if 6 <= hour < 12:
        return 'Morning (06-12)'
    if 12 <= hour < 18:
        return 'Afternoon (12-18)'
    if 18 <= hour < 24:
        return 'Evening (18-24)'
    return 'Night (00-06)'


def _years_since(date_str, today=None):
    """Whole-decimal years between an ISO date and today (None if unparsable)."""
    s = str(date_str or '').strip()[:10]
    if len(s) < 10:
        return None
    try:
        d = datetime.date.fromisoformat(s)
    except ValueError:
        return None
    t = today or datetime.datetime.now(datetime.timezone.utc).date()
    if d > t:
        return None
    return round((t - d).days / 365.25, 1)


def checkpoint_scope_sql(scope, alias='ce'):
    """Flexible, case-insensitive location filter for checkpoint_events.

    Mirrors the /api/checkpoint-events read path: a row written with only the
    friendly label ('South Checkpoint') still matches the officer's scope.
    Returns ('', ()) when no scope applies (admins see every location).
    """
    if not scope:
        return ('', ())
    s = str(scope).strip().lower()
    sql = (f"WHERE (LOWER(TRIM(COALESCE({alias}.location_code,'')))=? "
           f"OR LOWER(TRIM(COALESCE({alias}.checkpoint_location,'')))=? "
           f"OR LOWER(TRIM(COALESCE({alias}.checkpoint_location,'')))=? "
           f"OR LOWER(TRIM(COALESCE({alias}.location,'')))=? "
           f"OR LOWER(TRIM(COALESCE({alias}.location,''))) LIKE ? "
           f"OR LOWER(TRIM(COALESCE({alias}.checkpoint_location,''))) LIKE ?)")
    return (sql, (s, s, f'{s} checkpoint', s, f'%{s}%', f'%{s}%'))


def checkpoint_code_of(row):
    """Canonical checkpoint code (South / East / West) for an event row."""
    for key in ('location_code', 'checkpoint_location', 'location'):
        v = str(_val(row, key, '') or '').strip()
        if not v:
            continue
        code = canonical_location_scope(v)
        if code in CHECKPOINT_LOCATIONS:
            return code
        first = v.split()[0]
        if first in CHECKPOINT_LOCATIONS:
            return first
    return 'Other'


def kpi(label, value, tone='blue', icon='▦', hint=''):
    """One summary card for a departmental analytics header."""
    return {'label': label, 'value': value, 'tone': tone, 'icon': icon, 'hint': hint}


# ---- 1) CID · Fingerprint Unit ---------------------------------------------
def cid_fingerprint_analytics(c):
    """Biometric capture volume + identity match / suspect hit rates.

    Definitions (fixed so the numbers are reproducible in tests):
      * total_biometrics_logged  — one clearance application = one logged
        biometric capture set.
      * repeat_captures          — captures against a Central Person that was
        already fingerprinted (total − distinct persons), i.e. the capture
        matched an existing identity record.
      * identity_match_rate      — repeat_captures / total_biometrics_logged.
      * suspect_hits             — captures whose Central Person carries an
        ACTIVE suspect alert at query time.
      * hit_rate                 — suspect_hits / total_biometrics_logged.
    """
    rows = c.execute('''SELECT ca.person_id, ca.status, ca.purpose, ca.created_at,
            (SELECT COUNT(*) FROM suspect_alerts sa
              WHERE sa.person_id = ca.person_id
                AND sa.role = 'Suspect'
                AND sa.alert_status = 'Active alert') AS active_alerts
        FROM clearance_applications ca ORDER BY ca.id''').fetchall()
    total = len(rows)
    unique = len({_val(r, 'person_id') for r in rows})
    repeat = total - unique
    hits = sum(1 for r in rows if int(_val(r, 'active_alerts', 0) or 0) > 0)
    statuses = count_by(rows, 'status', 'Unknown')
    today = _today()
    logged_today = sum(1 for r in rows
                       if str(_val(r, 'created_at', '') or '').strip()[:10] == today)
    approved = int(statuses.get('Approved', 0))
    pending = int(statuses.get('Pending Review', 0))
    return {
        'unit': 'Fingerprint Unit',
        'total_biometrics_logged': total,
        'biometrics_logged_today': logged_today,
        'unique_persons_fingerprinted': unique,
        'repeat_captures': repeat,
        'identity_match_rate': pct(repeat, total),
        'suspect_hits': hits,
        'hit_rate': pct(hits, total),
        'approved': approved,
        'pending_review': pending,
        'rejected': int(statuses.get('Rejected', 0)),
        'clearance_rate': pct(approved, total),
        'kpis': [
            kpi('Biometrics logged', total, 'blue', '⌁', 'Clearance captures on file'),
            kpi('Identity match rate', f'{pct(repeat, total)}%', 'purple', '◈',
                'Captures matched to an existing Central Person'),
            kpi('Suspect hits', hits, 'red', '!', 'Captures tied to an active suspect alert'),
            kpi('Hit rate', f'{pct(hits, total)}%', 'red', '%', 'Suspect hits ÷ captures logged'),
            kpi('Pending review', pending, 'amber', '⧗', 'Awaiting the 12-hour review window'),
            kpi('Clearances approved', approved, 'green', '✓', f'{pct(approved, total)}% clearance rate'),
        ],
        'charts': {
            'by_status': series_from_counts(statuses, ('Pending Review', 'Approved', 'Rejected')),
            'by_purpose': series_from_counts(count_by(rows, 'purpose'), CLEARANCE_REASONS),
        },
        'lists': {},
    }


# ---- 2) CID · Crime Department ---------------------------------------------
def cid_crime_analytics(c):
    """Case volume by location, time-of-day band, category and open/closed."""
    rows = c.execute('SELECT case_id, category, location, status, created_at '
                     'FROM crime_cases ORDER BY id').fetchall()
    total = len(rows)
    closed = sum(1 for r in rows
                 if str(_val(r, 'status', '') or '').strip().lower() == 'closed')
    open_cases = total - closed
    active_suspects = c.execute(
        "SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' "
        "AND alert_status='Active alert'").fetchone()[0]
    categories = count_by(rows, 'category')
    top_category = max(categories.items(), key=lambda kv: kv[1])[0] if categories else '—'
    return {
        'unit': 'Crime Department',
        'total_cases': total,
        'open_cases': open_cases,
        'closed_cases': closed,
        'closure_rate': pct(closed, total),
        'active_suspects': active_suspects,
        'categories_tracked': len(categories),
        'top_category': top_category,
        'kpis': [
            kpi('Crime cases', total, 'blue', '⚖', 'CID case files on record'),
            kpi('Open cases', open_cases, 'amber', '◔', 'Everything not yet Closed'),
            kpi('Closed cases', closed, 'green', '✓', f'{pct(closed, total)}% closure rate'),
            kpi('Active suspects', active_suspects, 'red', '!', 'Live suspect alerts'),
            kpi('Top category', top_category, 'purple', '▤', 'Most reported crime category'),
        ],
        'charts': {
            'by_location': sorted_series(count_by(rows, 'location')),
            'by_time_of_day': series_from_counts(
                count_by(rows, 'created_at', 'Unspecified', time_of_day_bucket),
                TIME_OF_DAY_BUCKETS),
            'by_category': series_from_counts(categories, CRIME_CATEGORIES),
            'by_status': series_from_counts(count_by(rows, 'status'), CASE_STATUSES),
            'open_vs_closed': [{'label': 'Open', 'count': open_cases},
                               {'label': 'Closed', 'count': closed}],
        },
        'lists': {},
    }


# ---- 3) CID · Checkpoint Unit ----------------------------------------------
def cid_checkpoint_analytics(c, user):
    """Traveler screening volume + flagged suspect hits per checkpoint.

    Scoped exactly like /api/checkpoint-events: a Checkpoint officer only ever
    sees (and only ever counts) their own South / East / West location.
    """
    scope = checkpoint_scope(user)
    where, params = checkpoint_scope_sql(scope)
    rows = c.execute(f'''SELECT ce.person_id, ce.location, ce.location_code,
            ce.checkpoint_location, ce.screening_result, ce.created_at
        FROM checkpoint_events ce {where} ORDER BY ce.id''', params).fetchall()
    total = len(rows)
    flagged = sum(1 for r in rows
                  if str(_val(r, 'screening_result', '') or '').strip().lower() == 'flagged match')
    travelers = len({_val(r, 'person_id') for r in rows})
    today = _today()
    today_count = sum(1 for r in rows
                      if str(_val(r, 'created_at', '') or '').strip()[:10] == today)
    locations = (scope,) if scope in CHECKPOINT_LOCATIONS else CHECKPOINT_LOCATIONS
    per_location = []
    for code in locations:
        at = [r for r in rows if checkpoint_code_of(r) == code]
        hits = sum(1 for r in at
                   if str(_val(r, 'screening_result', '') or '').strip().lower() == 'flagged match')
        per_location.append({'label': code, 'checkpoint': f'{code} Checkpoint',
                             'count': len(at), 'screenings': len(at),
                             'flagged': hits, 'cleared': len(at) - hits,
                             'flag_rate': pct(hits, len(at))})
    other = [r for r in rows if checkpoint_code_of(r) not in CHECKPOINT_LOCATIONS]
    if other:
        per_location.append({'label': 'Other', 'checkpoint': 'Unassigned location',
                             'count': len(other), 'screenings': len(other),
                             'flagged': sum(1 for r in other if str(
                                 _val(r, 'screening_result', '') or '').strip().lower() == 'flagged match'),
                             'cleared': 0, 'flag_rate': 0.0})
        per_location[-1]['cleared'] = per_location[-1]['count'] - per_location[-1]['flagged']
        per_location[-1]['flag_rate'] = pct(per_location[-1]['flagged'], per_location[-1]['count'])
    return {
        'unit': 'Checkpoint Unit',
        'scope': scope or None,
        'total_screenings': total,
        'screenings_today': today_count,
        'flagged_hits': flagged,
        'cleared': total - flagged,
        'flag_rate': pct(flagged, total),
        'distinct_travelers': travelers,
        'kpis': [
            kpi('Travelers screened', total, 'blue', '⊙',
                f'{scope} Checkpoint only' if scope else 'All checkpoints'),
            kpi('Flagged suspect hits', flagged, 'red', '!', 'Screenings matching an active alert'),
            kpi('Flag rate', f'{pct(flagged, total)}%', 'amber', '%', 'Flagged ÷ screened'),
            kpi('Distinct travelers', travelers, 'purple', '◉', 'Unique Central Persons stopped'),
            kpi('Screened today', today_count, 'green', '⧗', 'UTC day to date'),
        ],
        'charts': {
            'by_location': [{'label': x['label'], 'count': x['count']} for x in per_location],
            'flagged_by_location': [{'label': x['label'], 'count': x['flagged']} for x in per_location],
            'screening_by_location': per_location,
            'by_result': series_from_counts(count_by(rows, 'screening_result'),
                                            ('Flagged match', 'No active alert', 'Cleared')),
        },
        'lists': {'checkpoints': per_location},
    }


# ---- 4) CID · Airport Unit --------------------------------------------------
def cid_airport_analytics(c):
    """Inbound / outbound movement counts + active suspect movement alerts."""
    rows = c.execute('''SELECT ap.person_id, ap.movement, ap.route, ap.travel_date,
            ap.origin_city, ap.destination_city,
            (SELECT COUNT(*) FROM suspect_alerts sa
              WHERE sa.person_id = ap.person_id
                AND sa.role = 'Suspect'
                AND sa.alert_status = 'Active alert') AS active_alerts
        FROM airport_passengers ap ORDER BY ap.id''').fetchall()
    total = len(rows)
    movements = count_by(rows, 'movement')
    inbound = int(movements.get('Arrival', 0))
    outbound = int(movements.get('Departure', 0))
    suspect_movements = sum(1 for r in rows if int(_val(r, 'active_alerts', 0) or 0) > 0)
    suspect_passengers = len({_val(r, 'person_id') for r in rows
                              if int(_val(r, 'active_alerts', 0) or 0) > 0})
    active_alerts = c.execute(
        "SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' "
        "AND alert_status='Active alert'").fetchone()[0]
    today = _today()
    today_count = sum(1 for r in rows
                      if str(_val(r, 'travel_date', '') or '').strip()[:10] == today)
    routes = {}
    for r in rows:
        label = str(_val(r, 'route', '') or '').strip() or ' / '.join(
            filter(None, [str(_val(r, 'origin_city', '') or '').strip(),
                          str(_val(r, 'destination_city', '') or '').strip()]))
        routes[label or 'Unspecified'] = routes.get(label or 'Unspecified', 0) + 1
    alert_items = [{'person_id': _val(r, 'person_id'),
                    'movement': _val(r, 'movement'),
                    'route': _val(r, 'route') or ' / '.join(
                        filter(None, [_val(r, 'origin_city'), _val(r, 'destination_city')])),
                    'travel_date': _val(r, 'travel_date'),
                    'alert': 'Active suspect alert'}
                   for r in rows if int(_val(r, 'active_alerts', 0) or 0) > 0]
    return {
        'unit': 'Airport Unit',
        'total_movements': total,
        'inbound': inbound,
        'outbound': outbound,
        'other_movements': total - inbound - outbound,
        'inbound_share': pct(inbound, total),
        'outbound_share': pct(outbound, total),
        'movements_today': today_count,
        'suspect_movements': suspect_movements,
        'suspect_passengers': suspect_passengers,
        'active_suspect_alerts': active_alerts,
        'kpis': [
            kpi('Passenger movements', total, 'blue', '✈', 'Airport register total'),
            kpi('Inbound', inbound, 'green', '↓', f'{pct(inbound, total)}% of movements'),
            kpi('Outbound', outbound, 'purple', '↑', f'{pct(outbound, total)}% of movements'),
            kpi('Suspect movements', suspect_movements, 'red', '!',
                'Movements by persons on an active alert'),
            kpi('Active suspect alerts', active_alerts, 'red', '⚑', 'Directorate-wide'),
        ],
        'charts': {
            'by_movement': series_from_counts(movements, AIRPORT_MOVEMENTS),
            'inbound_vs_outbound': [{'label': 'Inbound', 'count': inbound},
                                    {'label': 'Outbound', 'count': outbound}],
            'by_route': sorted_series(routes, limit=6),
        },
        'lists': {'suspect_movements': alert_items},
    }


def build_cid_analytics(c, user):
    """CID directorate bundle — one section per unit the caller may access."""
    mods = user_module_set(user)
    see_all = 'analytics' in mods or has_permission(user, PERM_ANALYTICS_GLOBAL)  # SystemAdmin / Chief Commander
    payload = {'generated_at': _generated_at(), 'module': 'cid',
               'role': (user or {}).get('role') or '',
               'checkpoint_scope': checkpoint_scope(user) or None,
               'sections': [], 'kpis': [], 'charts': {}, 'lists': {}}
    builders = {'fingerprint': lambda: cid_fingerprint_analytics(c),
                'crime': lambda: cid_crime_analytics(c),
                'checkpoint': lambda: cid_checkpoint_analytics(c, user),
                'airport': lambda: cid_airport_analytics(c)}
    for name in CID_ANALYTICS_SECTIONS:
        if not (see_all or CID_SECTION_MODULES[name] in mods):
            continue
        section = builders[name]()
        payload[name] = section
        payload['sections'].append(name)
        # The umbrella header shows the two most important cards per unit.
        payload['kpis'].extend(section.get('kpis', [])[:2])
    return payload


def build_officer_analytics(c, user):
    """HR Directorate bundle: roster metrics + green/red badge lists."""
    rows = c.execute('''SELECT o.*, s.region AS station_region, s.district AS station_district,
            s.name AS station_name, s.station_id AS station_code
        FROM officers o LEFT JOIN police_stations s ON s.id = o.station_id
        ORDER BY o.id''').fetchall()
    total = len(rows)
    duty = count_by(rows, 'duty_status', 'Unknown')
    active = int(duty.get('Active', 0))
    suspended = int(duty.get('Suspended', 0))
    ranks = count_by(rows, 'rank', 'Unranked')
    units = count_by(rows, 'unit', 'Unassigned')
    regions = {}
    for r in rows:
        region = str(_val(r, 'station_region', '') or _val(r, 'region_of_origin', '') or '').strip()
        regions[region or 'Unassigned'] = regions.get(region or 'Unassigned', 0) + 1
    service = [v for v in (_years_since(_val(r, 'date_of_enlistment')) for r in rows)
               if v is not None]
    avg_service = round(sum(service) / len(service), 1) if service else 0.0

    promotions = [promotion_view(r) for r in promotion_rows(c)]
    discipline = [discipline_view(r) for r in discipline_rows(c)]
    # The badge lists are FIFO queues (oldest nomination / action first) so a
    # commander always works the longest-waiting record next; the *_history
    # lists stay newest-first for the register view.
    awaiting = sorted((p for p in promotions if p['awaiting_verification']),
                      key=lambda p: str(p['nomination_id']))
    open_actions = sorted((d for d in discipline if d['open']),
                          key=lambda d: str(d['action_id']))
    pending_suspensions = sum(1 for d in discipline
                              if d['action_type'] == 'Suspension' and d['open'])
    demotions = sum(1 for d in discipline if d['action_type'] == 'Demotion')
    misconduct = sum(1 for d in discipline if d['action_type'] in ('Misconduct', 'Investigation'))
    return {
        'generated_at': _generated_at(),
        'module': 'officers',
        'role': (user or {}).get('role') or '',
        # --- roster metrics -------------------------------------------------
        'total_officers': total,
        'active_force': active,
        'suspended_officers': suspended,
        'on_leave': int(duty.get('Leave', 0)),
        'terminated': int(duty.get('Terminated', 0)),
        'retired': int(duty.get('Retired', 0)),
        'active_share': pct(active, total),
        'ranks_tracked': len(ranks),
        'average_service_years': avg_service,
        # --- promotion list (green badge) -----------------------------------
        'promotion_nominations': len(promotions),
        'promotions_awaiting_verification': len(awaiting),
        'promotions_verified': sum(1 for p in promotions if p['verification_status'] == 'Verified'),
        'promotions_rejected': sum(1 for p in promotions if p['verification_status'] == 'Rejected'),
        # --- disciplinary list (red badge) ----------------------------------
        'disciplinary_actions': len(discipline),
        'disciplinary_open': len(open_actions),
        'misconduct_actions': misconduct,
        'pending_suspensions': pending_suspensions,
        'rank_demotions': demotions,
        'badges': {'promotion': len(awaiting), 'discipline': len(open_actions)},
        'kpis': [
            kpi('Total active force', active, 'green', '👤', f'{pct(active, total)}% of {total} registered'),
            kpi('Officers registered', total, 'blue', '▤', 'Police Officers Registration Office'),
            kpi('Ranks in service', len(ranks), 'purple', '★', f'Avg {avg_service} years of service'),
            kpi('Promotions awaiting', len(awaiting), 'green', '▲', 'Active nominations awaiting commander verification'),
            kpi('Open disciplinary', len(open_actions), 'red', '▼',
                f'{pending_suspensions} pending suspension(s), {demotions} demotion(s)'),
            kpi('Suspended officers', suspended, 'amber', '⧗', 'Duty status = Suspended'),
        ],
        'charts': {
            'rank_distribution': series_from_counts(ranks, OFFICER_RANKS),
            'by_unit': series_from_counts(units, OFFICER_UNITS),
            'by_duty_status': series_from_counts(duty, OFFICER_DUTY_STATUSES),
            'by_region': series_from_counts(regions, STATION_REGIONS),
            'by_action_type': series_from_counts(count_by(discipline, 'action_type'),
                                                 DISCIPLINE_ACTION_TYPES),
            'by_promotion_status': series_from_counts(count_by(promotions, 'verification_status'),
                                                      PROMOTION_STATUSES),
        },
        'lists': {
            'promotions': awaiting,
            'promotion_history': promotions[:25],
            'discipline': open_actions,
            'discipline_history': discipline[:25],
        },
    }


# ---- 6) Police Car Registration module -------------------------------------
def build_vehicle_analytics(c, user):
    """Fleet operational status + security alert breakdown."""
    rows = c.execute('''SELECT v.*, s.name AS station_name, s.region AS station_region,
            s.station_id AS station_code
        FROM vehicles v LEFT JOIN police_stations s ON s.id = v.station_id
        ORDER BY v.id''').fetchall()
    total = len(rows)
    categories = count_by(rows, 'category', 'Unknown')
    fleet = int(categories.get('Police Fleet', 0))
    civilian = int(categories.get('Civilian / Commercial', 0))
    statuses = {}
    for r in rows:
        v = str(_val(r, 'operational_status', '') or '').strip() or 'Unassigned'
        statuses[v] = statuses.get(v, 0) + 1
    in_service = int(statuses.get('In Service', 0))
    maintenance = int(statuses.get('Maintenance', 0))
    out_of_service = int(statuses.get('Out of Service', 0))
    decommissioned = int(statuses.get('Decommissioned', 0))
    non_operational = maintenance + out_of_service + decommissioned
    alerts = count_by(rows, 'security_alert', 'Clean / Normal')
    clean = int(alerts.get('Clean / Normal', 0))
    stolen = int(alerts.get('Stolen', 0))
    wanted = int(alerts.get('Wanted in Crime', 0))
    impounded = int(alerts.get('Impounded', 0))
    suspicious = int(alerts.get('Unregistered / Suspicious', 0))
    flagged = total - clean
    civilian_clean = sum(1 for r in rows
                         if str(_val(r, 'category', '') or '') == 'Civilian / Commercial'
                         and str(_val(r, 'security_alert', 'Clean / Normal') or 'Clean / Normal')
                         == 'Clean / Normal')
    civilian_flagged = civilian - civilian_clean
    fleet_regions = {}
    for r in rows:
        if str(_val(r, 'category', '') or '') != 'Police Fleet':
            continue
        region = str(_val(r, 'station_region', '') or '').strip() or 'Unassigned'
        fleet_regions[region] = fleet_regions.get(region, 0) + 1
    flagged_items = [{
        'vehicle_id': r['vehicle_id'],
        'plate_number': r['plate_number'],
        'category': _val(r, 'category'),
        'security_alert': _val(r, 'security_alert'),
        'alert_reason': _val(r, 'alert_reason'),
        'make_model': _val(r, 'make_model'),
        'station_name': _val(r, 'station_name'),
        'owner_full_name': _val(r, 'owner_full_name'),
        'registration_expiry': _val(r, 'registration_expiry'),
    } for r in rows
        if str(_val(r, 'security_alert', 'Clean / Normal') or 'Clean / Normal') != 'Clean / Normal']
    return {
        'generated_at': _generated_at(),
        'module': 'vehicles',
        'role': (user or {}).get('role') or '',
        'total_vehicles': total,
        'police_fleet': fleet,
        'civilian_registrations': civilian,
        # --- fleet operational status --------------------------------------
        'in_service': in_service,
        'maintenance': maintenance,
        'out_of_service': out_of_service,
        'decommissioned': decommissioned,
        'non_operational': non_operational,
        'serviceable_ratio': pct(in_service, fleet),
        'fleet_availability': pct(in_service, total),
        'maintenance_rate': pct(non_operational, fleet),
        # --- security alert breakdown --------------------------------------
        'clean_registrations': clean,
        'flagged_vehicles': flagged,
        'stolen': stolen,
        'wanted_in_crime': wanted,
        'impounded': impounded,
        'unregistered_suspicious': suspicious,
        'alert_rate': pct(flagged, total),
        'civilian_clean': civilian_clean,
        'civilian_flagged': civilian_flagged,
        'kpis': [
            kpi('Vehicles registered', total, 'blue', '🚓', f'{fleet} fleet · {civilian} civilian'),
            kpi('In service', in_service, 'green', '✓', f'{pct(in_service, fleet)}% of the police fleet'),
            kpi('Maintenance / out', non_operational, 'amber', '⚒',
                f'{maintenance} in maintenance · {decommissioned} decommissioned'),
            kpi('Serviceable ratio', f'{pct(in_service, fleet)}%', 'purple', '%', 'In service ÷ police fleet'),
            kpi('Stolen / wanted', stolen + wanted, 'red', '!',
                f'{stolen} stolen · {wanted} wanted in crime'),
            kpi('Clean registrations', clean, 'green', '◈',
                f'{civilian_clean} clean civilian registrations'),
        ],
        'charts': {
            'by_operational_status': series_from_counts(statuses, VEHICLE_OP_STATUSES + ('Unassigned',)),
            'fleet_status_ratio': [{'label': 'In Service', 'count': in_service},
                                   {'label': 'Maintenance', 'count': maintenance},
                                   {'label': 'Out of Service', 'count': out_of_service},
                                   {'label': 'Decommissioned', 'count': decommissioned}],
            'by_alert': series_from_counts(alerts, VEHICLE_ALERTS),
            'alert_breakdown': [{'label': 'Stolen', 'count': stolen},
                                {'label': 'Wanted in Crime', 'count': wanted},
                                {'label': 'Impounded', 'count': impounded},
                                {'label': 'Unregistered / Suspicious', 'count': suspicious},
                                {'label': 'Clean / Normal', 'count': clean}],
            'by_category': series_from_counts(categories, VEHICLE_CATEGORIES),
            'fleet_by_region': series_from_counts(fleet_regions, STATION_REGIONS),
        },
        'lists': {'flagged_vehicles': flagged_items},
    }


# ---- 7) Police Station Master Registry -------------------------------------
def build_station_analytics(c, user):
    """Operational capacity by tier + the officer deployment matrix."""
    rows = c.execute('''SELECT s.*,
            (SELECT COUNT(*) FROM officers o WHERE o.station_id = s.id) AS officer_count,
            (SELECT COUNT(*) FROM officers o
              WHERE o.station_id = s.id AND o.duty_status = 'Active') AS active_officer_count,
            (SELECT COUNT(*) FROM vehicles v WHERE v.station_id = s.id) AS vehicle_count
        FROM police_stations s ORDER BY s.id''').fetchall()
    total = len(rows)
    tiers = count_by(rows, 'station_tier', 'Unclassified')
    statuses = count_by(rows, 'operational_status', 'Active')
    cell_capacity = sum(int(_val(r, 'cell_capacity', 0) or 0) for r in rows)
    reporting_cells = sum(1 for r in rows if _val(r, 'cell_capacity') is not None)
    officers_deployed = sum(int(_val(r, 'officer_count', 0) or 0) for r in rows)
    active_deployed = sum(int(_val(r, 'active_officer_count', 0) or 0) for r in rows)
    vehicles_deployed = sum(int(_val(r, 'vehicle_count', 0) or 0) for r in rows)
    unassigned = [{'station_id': r['station_id'], 'name': r['name'], 'region': r['region'],
                   'station_tier': _val(r, 'station_tier')}
                  for r in rows if int(_val(r, 'officer_count', 0) or 0) == 0]
    by_region = []
    matrix = []
    region_names = list(STATION_REGIONS)
    for r in rows:                                  # keep any unexpected region visible
        if r['region'] not in region_names:
            region_names.append(r['region'])
    for region in region_names:
        at = [r for r in rows if r['region'] == region]
        stations = [{'station_id': r['station_id'], 'name': r['name'], 'code': r['code'],
                     'district': r['district'], 'village': _val(r, 'village'),
                     'station_tier': _val(r, 'station_tier') or 'Unclassified',
                     'operational_status': _val(r, 'operational_status') or 'Active',
                     'officers': int(_val(r, 'officer_count', 0) or 0),
                     'active_officers': int(_val(r, 'active_officer_count', 0) or 0),
                     'vehicles': int(_val(r, 'vehicle_count', 0) or 0)} for r in at]
        stations.sort(key=lambda s: (-s['officers'], s['name']))
        block = {'region': region,
                 'stations': len(at),
                 'officers': sum(s['officers'] for s in stations),
                 'active_officers': sum(s['active_officers'] for s in stations),
                 'vehicles': sum(s['vehicles'] for s in stations),
                 'station_list': stations}
        matrix.append(block)
        by_region.append({'label': region, 'count': block['stations'],
                          'officers': block['officers'],
                          'active_officers': block['active_officers'],
                          'vehicles': block['vehicles']})
    largest = max(({'name': r['name'], 'station_id': r['station_id'],
                    'officers': int(_val(r, 'officer_count', 0) or 0)} for r in rows),
                  key=lambda x: x['officers'], default=None)
    return {
        'generated_at': _generated_at(),
        'module': 'stations',
        'role': (user or {}).get('role') or '',
        'total_stations': total,
        'regional_hq': int(tiers.get('Regional HQ', 0)),
        'district_hq': int(tiers.get('District HQ', 0)),
        'outposts': int(tiers.get('Outpost', 0)),
        'checkpoints': int(tiers.get('Checkpoint', 0)),
        'border_posts': int(tiers.get('Border Post', 0)),
        'active_stations': int(statuses.get('Active', 0)),
        'inactive_stations': int(statuses.get('Inactive', 0)),
        'maintenance_stations': int(statuses.get('Maintenance', 0)),
        'total_cell_capacity': cell_capacity,
        'average_cell_capacity': round(cell_capacity / reporting_cells, 1) if reporting_cells else 0.0,
        'stations_reporting_cells': reporting_cells,
        # --- deployment matrix ---------------------------------------------
        'officers_deployed': officers_deployed,
        'active_officers_deployed': active_deployed,
        'vehicles_deployed': vehicles_deployed,
        'average_officers_per_station': round(officers_deployed / total, 1) if total else 0.0,
        'unassigned_stations': len(unassigned),
        'largest_deployment': largest,
        'kpis': [
            kpi('Stations registered', total, 'blue', '🏛', f'{int(statuses.get("Active", 0))} active'),
            kpi('Regional / District HQ', int(tiers.get('Regional HQ', 0)) + int(tiers.get('District HQ', 0)),
                'purple', '▣',
                f'{int(tiers.get("Regional HQ", 0))} regional · {int(tiers.get("District HQ", 0))} district'),
            kpi('Outposts & checkpoints', int(tiers.get('Outpost', 0)) + int(tiers.get('Checkpoint', 0))
                + int(tiers.get('Border Post', 0)), 'amber', '⊙',
                f'{int(tiers.get("Outpost", 0))} outpost(s) · {int(tiers.get("Checkpoint", 0))} checkpoint(s)'),
            kpi('Officers deployed', officers_deployed, 'green', '👤',
                f'Avg {round(officers_deployed / total, 1) if total else 0.0} per station'),
            kpi('Unstaffed stations', len(unassigned), 'red', '!', 'No officer assigned yet'),
            kpi('Cell capacity', cell_capacity, 'blue', '▦', 'Detention capacity across the registry'),
        ],
        'charts': {
            'by_tier': series_from_counts(tiers, STATION_TIERS),
            'by_status': series_from_counts(statuses, STATION_STATUSES),
            'stations_by_region': [{'label': b['label'], 'count': b['count']} for b in by_region],
            'deployment_by_region': by_region,
            'officers_by_station': sorted_series(
                {r['name']: int(_val(r, 'officer_count', 0) or 0) for r in rows}, limit=8),
        },
        'lists': {'deployment_matrix': matrix, 'by_region': by_region,
                  'unassigned_stations': unassigned},
    }


# ---- dispatcher -------------------------------------------------------------
def _officers_bundle(c, user):
    require_module(user, 'officers')
    return build_officer_analytics(c, user)


def _vehicles_bundle(c, user):
    require_any_module(user, ('cars', 'policesearch', 'checkpoints', 'crimes'))
    return build_vehicle_analytics(c, user)


def _stations_bundle(c, user):
    require_any_module(user, ('stations', 'crimes'))
    return build_station_analytics(c, user)


def _global_bundle(c, user):
    require_permission(user, PERM_ANALYTICS_GLOBAL)
    return build_global_analytics(c, user)


ANALYTICS_BUILDERS = {
    'cid': build_cid_analytics,
    'officers': _officers_bundle,
    'vehicles': _vehicles_bundle,
    'stations': _stations_bundle,
    'global': _global_bundle,
}

# Accepted ?module= spellings (aliases keep the frontend free of guesswork).
ANALYTICS_MODULE_ALIASES = {
    'cid': 'cid', 'criminal_investigation': 'cid', 'crime': 'cid',
    'officers': 'officers', 'hr': 'officers', 'police_officers': 'officers',
    'vehicles': 'vehicles', 'cars': 'vehicles', 'car': 'vehicles',
    'stations': 'stations', 'station': 'stations', 'police_stations': 'stations',
    'global': 'global', 'executive': 'global', 'hq': 'global', 'command': 'global',
}


# ---- 9) Chief Commander · Global executive analytics ------------------------
def build_global_analytics(c, user):
    """Cross-department HQ bundle for the Chief Commander (HQ / Command).

    Aggregates every directorate into one executive envelope (same
    {kpis, charts, lists} shape as the departmental bundles, plus a
    `departments` block and a per-station `stations` oversight table):

      * CID          — crime case clearance rate, open cases, active suspects,
                       fingerprint clearance rate, checkpoint threat hits,
                       airport movements / suspect alerts
      * Personnel    — officer headcount, active / suspended, pending
                       promotions & open disciplinary actions
      * Transport    — fleet readiness (in-service ÷ police fleet), flagged
                       vehicles
      * Stations     — regional statistics + the station oversight table
                       (code · name · region · district · tier · status ·
                       officers · active officers · vehicles · crime reports)

    Gated by the `analytics:global` permission (SystemAdmin + Chief
    Commander). Never scoped: HQ sees every location.
    """
    cid = build_cid_analytics(c, {**(user or {}), 'role': ROLE_ADMIN, 'modules': ['analytics']})
    crime = cid.get('crime') or {}
    fp = cid.get('fingerprint') or {}
    cp = cid.get('checkpoint') or {}
    ap = cid.get('airport') or {}
    officers = build_officer_analytics(c, user)
    vehicles = build_vehicle_analytics(c, user)
    stations = build_station_analytics(c, user)

    # --- CID ------------------------------------------------------------
    total_cases = int(crime.get('total_cases', 0) or 0)
    closed_cases = int(crime.get('closed_cases', 0) or 0)
    clearance_rate = pct(closed_cases, total_cases)
    fp_rows = c.execute('SELECT status FROM clearance_applications').fetchall()
    fp_total = len(fp_rows)
    fp_approved = sum(1 for r in fp_rows
                      if str(_val(r, 'status', '') or '').strip().lower() == 'approved')
    checkpoint_hits = int(cp.get('flagged_hits', 0) or 0)
    active_suspects = int(crime.get('active_suspects', 0) or 0)

    # --- Personnel --------------------------------------------------------
    total_officers = int(officers.get('total_officers', 0) or 0)
    active_officers = int(officers.get('active_force', 0) or 0)
    suspended_officers = int(officers.get('suspended_officers', 0) or 0)
    pending_promotions = len((officers.get('lists') or {}).get('promotions', []) or [])
    open_discipline = len((officers.get('lists') or {}).get('discipline', []) or [])

    # --- Transport --------------------------------------------------------
    fleet_total = int(vehicles.get('police_fleet', 0) or 0)
    fleet_in_service = int(vehicles.get('in_service', 0) or 0)
    fleet_readiness = pct(fleet_in_service, fleet_total)
    flagged_vehicles = int(vehicles.get('flagged_vehicles', 0) or 0)

    # --- Stations & regions -------------------------------------------------
    crime_by_station = {}
    for r in c.execute('SELECT station_id, COUNT(*) AS n FROM crime_incidents GROUP BY station_id'):
        crime_by_station[r['station_id']] = int(r['n'] or 0)
    rows = c.execute('''SELECT s.id, s.station_id, s.name, s.code, s.region, s.district, s.village,
            s.station_tier, s.operational_status,
            (SELECT COUNT(*) FROM officers o WHERE o.station_id = s.id) AS officer_count,
            (SELECT COUNT(*) FROM officers o
              WHERE o.station_id = s.id AND o.duty_status = 'Active') AS active_officer_count,
            (SELECT COUNT(*) FROM vehicles v WHERE v.station_id = s.id) AS vehicle_count
        FROM police_stations s ORDER BY s.region, s.district, s.name''').fetchall()
    station_table = []
    for r in rows:
        station_table.append({
            'station_id': r['station_id'],
            'code': r['code'],
            'name': r['name'],
            'region': r['region'],
            'district': r['district'],
            'village': _val(r, 'village'),
            'station_tier': _val(r, 'station_tier') or 'Unclassified',
            'operational_status': _val(r, 'operational_status') or 'Active',
            'officers': int(_val(r, 'officer_count', 0) or 0),
            'active_officers': int(_val(r, 'active_officer_count', 0) or 0),
            'vehicles': int(_val(r, 'vehicle_count', 0) or 0),
            'crime_reports': int(crime_by_station.get(r['id'], 0)),
        })
    region_names = list(STATION_REGIONS)
    for st in station_table:
        if st['region'] not in region_names:
            region_names.append(st['region'])
    regions = []
    for region in region_names:
        at = [s for s in station_table if s['region'] == region]
        regions.append({
            'region': region, 'code': REGION_CODES.get(region, region[:3].upper()),
            'stations': len(at),
            'active_stations': sum(1 for s in at if s['operational_status'] == 'Active'),
            'officers': sum(s['officers'] for s in at),
            'active_officers': sum(s['active_officers'] for s in at),
            'vehicles': sum(s['vehicles'] for s in at),
            'crime_reports': sum(s['crime_reports'] for s in at),
        })
    total_crime_reports = sum(s['crime_reports'] for s in station_table)
    hotspot = max(station_table, key=lambda s: s['crime_reports'], default=None)

    return {
        'generated_at': _generated_at(),
        'module': 'global',
        'role': (user or {}).get('role') or '',
        'scope': 'global',
        # --- flat executive metrics ---------------------------------------
        'total_officers': total_officers,
        'active_officers': active_officers,
        'suspended_officers': suspended_officers,
        'cid_total_cases': total_cases,
        'cid_closed_cases': closed_cases,
        'cid_clearance_rate': clearance_rate,
        'fingerprint_applications': fp_total,
        'fingerprint_approved': fp_approved,
        'fingerprint_clearance_rate': pct(fp_approved, fp_total),
        'checkpoint_hits': checkpoint_hits,
        'checkpoint_screenings': int(cp.get('total_screenings', 0) or 0),
        'active_suspects': active_suspects,
        'fleet_total': fleet_total,
        'fleet_in_service': fleet_in_service,
        'fleet_readiness': fleet_readiness,
        'flagged_vehicles': flagged_vehicles,
        'total_stations': len(station_table),
        'total_crime_reports': total_crime_reports,
        'kpis': [
            kpi('Total officers', total_officers, 'blue', '👤',
                f'{active_officers} active · {suspended_officers} suspended'),
            kpi('CID clearance rate', f'{clearance_rate}%', 'green', '⚖',
                f'{closed_cases} of {total_cases} cases closed'),
            kpi('Active checkpoint hits', checkpoint_hits, 'red', '!',
                f'{int(cp.get("total_screenings", 0) or 0)} travelers screened · all checkpoints'),
            kpi('Fleet readiness', f'{fleet_readiness}%', 'amber', '🚓',
                f'{fleet_in_service} of {fleet_total} police vehicles in service'),
            kpi('Stations', len(station_table), 'purple', '🏛',
                f'{len(regions)} regions · {total_crime_reports} crime reports'),
            kpi('Active suspect alerts', active_suspects, 'red', '◉',
                'Live CID suspect listings'),
        ],
        'departments': {
            'cid': {
                'label': 'Dep. of CID',
                'total_cases': total_cases, 'open_cases': int(crime.get('open_cases', 0) or 0),
                'closed_cases': closed_cases, 'clearance_rate': clearance_rate,
                'active_suspects': active_suspects,
                'fingerprint_applications': fp_total, 'fingerprint_approved': fp_approved,
                'fingerprint_clearance_rate': pct(fp_approved, fp_total),
                'fingerprint_suspect_hits': int(fp.get('suspect_hits', 0) or 0),
                'checkpoint_screenings': int(cp.get('total_screenings', 0) or 0),
                'checkpoint_hits': checkpoint_hits,
                'checkpoint_flag_rate': cp.get('flag_rate', 0.0),
                'checkpoints': (cp.get('lists') or {}).get('checkpoints', []),
                'airport_movements': int(ap.get('total_movements', 0) or 0),
                'airport_suspect_alerts': int(ap.get('suspect_movements', 0) or 0),
            },
            'personnel': {
                'label': 'Dep. of Police Personnel',
                'total_officers': total_officers, 'active_officers': active_officers,
                'suspended_officers': suspended_officers,
                'pending_promotions': pending_promotions,
                'open_disciplinary_actions': open_discipline,
                'by_rank': (officers.get('charts') or {}).get('rank_distribution', []),
            },
            'transport': {
                'label': 'Dep. of Transport',
                'fleet_total': fleet_total, 'in_service': fleet_in_service,
                'fleet_readiness': fleet_readiness,
                'maintenance': int(vehicles.get('maintenance', 0) or 0),
                'out_of_service': int(vehicles.get('out_of_service', 0) or 0),
                'flagged_vehicles': flagged_vehicles,
                'total_vehicles': int(vehicles.get('total_vehicles', 0) or 0),
            },
            'stations': {
                'label': 'Stations & regions',
                'total_stations': len(station_table),
                'active_stations': sum(1 for s in station_table if s['operational_status'] == 'Active'),
                'unstaffed_stations': sum(1 for s in station_table if s['officers'] == 0),
                'crime_hotspot': hotspot,
            },
        },
        'charts': {
            'officers_by_region': [{'label': r['region'], 'count': r['officers']} for r in regions],
            'crime_reports_by_region': [{'label': r['region'], 'count': r['crime_reports']} for r in regions],
            'checkpoint_hits_by_location': (cp.get('charts') or {}).get('flagged_by_location', []),
            'cases_open_vs_closed': (crime.get('charts') or {}).get('open_vs_closed', []),
            'fleet_status': [{'label': 'In Service', 'count': fleet_in_service},
                             {'label': 'Not ready', 'count': max(fleet_total - fleet_in_service, 0)}],
        },
        'lists': {'stations': station_table, 'regions': regions},
        'stations': station_table,
        'regions': regions,
    }


def build_module_analytics(c, user, module):
    """Resolve `?module=` to a departmental bundle ('all' returns every one).

    Unknown module names raise ValueError -> HTTP 400 (never a silent empty
    payload), so a typo in the frontend shows up immediately.
    """
    key = str(module or '').strip().lower()
    if key in ('', 'all', 'everything'):
        bundles = {}
        for name in ANALYTICS_MODULES:
            try:
                bundles[name] = ANALYTICS_BUILDERS[name](c, user)
            except PermissionError:
                continue                     # omit bundles the caller may not see
        return {'generated_at': _generated_at(), 'module': 'all',
                'role': (user or {}).get('role') or '',
                'modules': sorted(bundles), 'bundles': bundles}
    resolved = ANALYTICS_MODULE_ALIASES.get(key)
    if not resolved:
        raise ValueError('module must be one of: ' + ', '.join(ANALYTICS_MODULES + ('global', 'all')))
    return ANALYTICS_BUILDERS[resolved](c, user)


def build_dashboard(c, user):
    """Role- and location-scoped operations dashboard payload.

    Returns a single JSON envelope the frontend renders as KPI cards,
    quick-action buttons, and a real-time activity feed. Every field
    is filtered to the caller's modules and (for Checkpoint users)
    their assigned location scope, so the dashboard can never leak
    metrics for a unit or location the officer is not authorised to
    see.

    Each unit role receives a tailored set of mini-analytics that
    summarise their specific operational responsibilities (e.g.
    'Peak Travel Hour' for Checkpoint officers, 'Open investigation
    cases' for CID, 'Today's passenger movements' for Airport). The
    activity feed is enriched with the actual screened-person /
    traveller / suspect name and a human-friendly "N mins ago" stamp
    so the real-time feed reads like a live operations log.

    Spec step 2: the dashboard ALWAYS returns HTTP 200 for any
    authenticated user — no 404, no role-rejection. The response
    payload surfaces BOTH the role-specific cards AND the spec's
    mandated alias keys (screenings_today, travelers_flagged,
    total_travelers, peak_travel_hour, activity_feed) for Checkpoint
    officers so any frontend that reads those flat keys still works.
    """
    role = (user.get('role') or '') if user else ''
    is_admin = (role == ROLE_ADMIN)
    # Spec step 1: normalise the role string. A token whose role is
    # 'CheckpointSouth' (or 'cp_south' or 'checkpoint_officer') is
    # treated exactly like the canonical normalised form for the
    # downstream branching below.
    role_alias = normalize_role(role)
    scope = checkpoint_scope(user) if user else None
    now_ts = time.time()
    today = time.strftime('%Y-%m-%d', time.gmtime(now_ts))
    # Spec step 1: is_checkpoint now also recognises every accepted
    # Checkpoint-officer spelling — 'CheckpointSouth',
    # 'CheckpointEast', 'CheckpointWest', 'checkpoint_officer', and
    # any other accepted alias. The role_alias doubles as a safety
    # net: even if the stored role string drifts in the future, as
    # long as it normalises to ROLE_CHECKPOINT_OFFICER this branch
    # fires correctly.
    is_checkpoint = bool(role and (
        role in (ROLE_CHECKPOINT_SOUTH, ROLE_CHECKPOINT_EAST, ROLE_CHECKPOINT_WEST)
        or role_alias == ROLE_CHECKPOINT_OFFICER
    ))

    def cp_scope_sql():
        """Flexible case-insensitive match against any of the four
        location columns so a row that was just saved with the friendly
        checkpoint label is returned in the very next poll even if
        `location_code` was not populated. Adds a LIKE '%scope%'
        fallback so any trailing space, casing, or punctuation variation
        in 'location' / 'checkpoint_location' is still caught.
        """
        if not scope: return ("", ())
        sql = ("WHERE (LOWER(TRIM(COALESCE(ce.location_code,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.location,'')))=? "
               "OR LOWER(TRIM(COALESCE(ce.location,''))) LIKE ? "
               "OR LOWER(TRIM(COALESCE(ce.checkpoint_location,''))) LIKE ?)")
        return (sql, (scope.lower(), scope.lower(), f"{scope.lower()} checkpoint",
                      scope.lower(), f"%{scope.lower()}%", f"%{scope.lower()}%"))

    # ---- KPI cards (mini-analytics) ---------------------------------------
    cards = []
    is_chief = canonical_unit_role(role) == ROLE_CHIEF
    if is_admin or is_chief:
        # HQ / Command sees the same cross-unit overview as SystemAdmin.
        cards.extend(_admin_dashboard_cards(c))
    elif is_checkpoint:
        cards.extend(_checkpoint_dashboard_cards(c, scope, today, cp_scope_sql))
    elif role == ROLE_FINGERPRINT or role_alias == ROLE_FINGERPRINT:
        cards.extend(_fingerprint_dashboard_cards(c, today))
    elif role == ROLE_AIRPORT or role_alias == ROLE_AIRPORT:
        cards.extend(_airport_dashboard_cards(c, today))
    elif role == ROLE_CID or role_alias == ROLE_CID:
        cards.extend(_cid_dashboard_cards(c, today))
    elif role == ROLE_REGISTRATION or role_alias == ROLE_REGISTRATION:
        cards.extend(_registration_dashboard_cards(c, today))
    else:
        # Spec step 2: a token whose role is not one of the canonical
        # units still gets an empty-but-valid dashboard so the
        # endpoint NEVER 404s. The frontend can render an empty state
        # instead of a "Not Found" placeholder.
        cards = []

    # ---- Quick-registration buttons ----------------------------------------
    quick = []
    if is_admin or role == ROLE_AIRPORT or role_alias == ROLE_AIRPORT:
        quick.append({'id':'add_airport','label':'+ Airport passenger','kind':'primary','page':'airport','module':'airport'})
    if is_admin or role == ROLE_FINGERPRINT or role_alias == ROLE_FINGERPRINT:
        quick.append({'id':'add_clearance','label':'+ Clearance application','kind':'secondary','page':'fingerprint','module':'fingerprint'})
    if is_admin or role == ROLE_CID or role_alias == ROLE_CID:
        quick.append({'id':'add_case','label':'+ New crime case','kind':'secondary','page':'cid','module':'cid'})
    if is_admin or is_checkpoint:
        quick.append({'id':'add_checkpoint','label':'+ Record checkpoint stop','kind':'primary','page':'checkpoints','module':'checkpoints'})
    if is_admin or role == ROLE_REGISTRATION or role_alias == ROLE_REGISTRATION:
        quick.append({'id':'add_conduct','label':'+ New conduct action','kind':'primary','page':'conduct','module':'conduct'})

    # ---- Real-time activity stream (filtered to the user's scope) ---------
    events = _build_activity_feed(c, role, is_admin or is_chief, scope, is_checkpoint, now_ts, cp_scope_sql)

    # ---- Spec step 2 alias keys --------------------------------------------
    # The spec's mandated top-level keys for the Checkpoint-officer
    # dashboard (screenings_today, travelers_flagged,
    # total_travelers, peak_travel_hour, activity_feed) are also
    # surfaced as flat top-level fields. Any frontend that reads
    # those keys (instead of cards[].id) works out of the box.
    screenings_today = 0
    travelers_flagged = 0
    total_travelers = 0
    peak_travel_hour = '—'
    if is_checkpoint:
        for card in cards:
            if card.get('id') == 'cp_screenings_today':
                screenings_today = card.get('value', 0)
            elif card.get('id') == 'cp_travelers_flagged':
                travelers_flagged = card.get('value', 0)
            elif card.get('id') == 'cp_total_travelers':
                total_travelers = card.get('value', 0)
            elif card.get('id') == 'cp_peak_hour':
                peak_travel_hour = card.get('value', '—')

    # Spec step 1: also surface the modules list under the
    # normalized role so the frontend can gate on either form.
    modules_raw = sorted(ROLE_MODULES.get(role, set()))
    modules_alias = sorted(ROLE_MODULES.get(role_alias, set()))
    modules = sorted(set(modules_raw) | set(modules_alias))

    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ts)),
        'role': role,
        'role_alias': role_alias,
        'is_admin': is_admin,
        'location_scope': scope,
        'modules': modules,
        'cards': cards,
        'quick_actions': quick,
        'activity': events,
        'stream': events[:8],
        # Spec step 2: alias keys at the top level for Checkpoint
        # officers (and zeroed for other roles so the keys exist).
        'screenings_today': screenings_today,
        'travelers_flagged': travelers_flagged,
        'total_travelers': total_travelers,
        'peak_travel_hour': peak_travel_hour,
        'activity_feed': events,
        'is_chief_commander': is_chief,
        'subhead': (
            'System overview · all units' if is_admin else
            'HQ / Command · global overview' if is_chief else
            (f'{scope} Checkpoint operations · live' if is_checkpoint else
             f'{ROLE_LABELS.get(role, role)} · live operations feed')
        ),
    }


def _admin_dashboard_cards(c):
    return [
        {'id':'central_persons','label':'Central persons','icon':'◉',
         'value':c.execute('SELECT COUNT(*) FROM persons').fetchone()[0],
         'trend':'Unified identity records','module':'people'},
        {'id':'open_cases','label':'Open crime cases','icon':'⌂',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0],
         'trend':'Active investigations','module':'cid'},
        {'id':'pending_clearances','label':'Pending clearances','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Pending Review'").fetchone()[0],
         'trend':'Require officer review','module':'fingerprint'},
        {'id':'active_alerts','label':'Active suspect alerts','icon':'!',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0],
         'trend':'Restricted operational data','trend_kind':'alert','module':'cid'},
        {'id':'conduct_pending','label':'Conduct files pending HR review','icon':'🎖',
         'value':c.execute("SELECT COUNT(*) FROM officer_conduct_actions WHERE status IN (?, ?)",
                           CONDUCT_PENDING_STATUSES).fetchone()[0],
         'trend':'Promotions & disciplinary actions','module':'conduct'},
    ]


def _registration_dashboard_cards(c, today):
    """Tailored mini-analytics for the Police Officer Registration Office
    (HR Directorate): conduct files pending review, promotion vs
    disciplinary counts, approved rank changes and the officer register."""
    def count(sql, args=()):
        return c.execute(sql, args).fetchone()[0]
    return [
        {'id':'reg_conduct_pending','label':'Conduct files pending review','icon':'🎖',
         'value':count("SELECT COUNT(*) FROM officer_conduct_actions WHERE status IN (?, ?)",
                       CONDUCT_PENDING_STATUSES),
         'trend':'Awaiting HR verification','module':'conduct'},
        {'id':'reg_conduct_promotions','label':'Promotion / commendation files','icon':'↑',
         'value':count("SELECT COUNT(*) FROM officer_conduct_actions WHERE action_type=?",
                       ('Promotion / Commendation',)),
         'trend':'Nominations for exemplary service','module':'conduct'},
        {'id':'reg_conduct_disciplinary','label':'Disciplinary / misconduct files','icon':'!',
         'value':count("SELECT COUNT(*) FROM officer_conduct_actions WHERE action_type=?",
                       ('Disciplinary / Penalty',)),
         'trend':'Violations & penalties','trend_kind':'alert','module':'conduct'},
        {'id':'reg_rank_changes','label':'Approved rank changes','icon':'≡',
         'value':count('SELECT COUNT(*) FROM officer_conduct_actions WHERE rank_applied=1'),
         'trend':'Applied to the officer register','module':'conduct'},
        {'id':'reg_officers','label':'Officers on the register','icon':'👤',
         'value':count("SELECT COUNT(*) FROM officers WHERE duty_status='Active'"),
         'trend':'Active across Sool · Sanaag · East Togdheer','module':'officers'},
    ]


def _checkpoint_dashboard_cards(c, scope, today, cp_scope_sql):
    """Tailored mini-analytics for Checkpoint South / East / West officers.

    4 compact stat cards, all filtered to the officer's assigned
    location: 'Screenings today', 'Travelers flagged', 'Total
    location travelers', and 'Peak travel hour' (the 2-hour bucket
    with the most events in the last 7 days).
    """
    cards = []
    filter_sql, filter_args = cp_scope_sql()
    # If the officer has no scope (shouldn't happen for checkpoint users),
    # fall back to the most permissive filter so the cards still render
    # rather than throwing a 500.
    if not filter_sql:
        filter_sql, filter_args = "WHERE 1=1", ()

    screenings_today = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql} "
        f"AND substr(ce.created_at,1,10)=?",
        (*filter_args, today)).fetchone()[0]
    flagged_today = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql} "
        f"AND ce.screening_result='Flagged match' "
        f"AND substr(ce.created_at,1,10)=?",
        (*filter_args, today)).fetchone()[0]
    total_local = c.execute(
        f"SELECT COUNT(*) FROM checkpoint_events ce {filter_sql}", filter_args).fetchone()[0]
    unique_travelers = c.execute(
        f"SELECT COUNT(DISTINCT ce.person_id) FROM checkpoint_events ce {filter_sql}",
        filter_args).fetchone()[0]

    # Peak travel hour — bucket created_at into 2-hour slices for the
    # last 7 days. SQLite has no native date arithmetic on TEXT so we
    # use a LIKE prefix on the YYYY-MM-DD portion.
    seven_days_ago = time.strftime('%Y-%m-%d', time.gmtime(time.time() - 7 * 86400))
    peak_row = c.execute(
        f"SELECT substr(ce.created_at,12,2) AS hh, COUNT(*) AS n "
        f"FROM checkpoint_events ce {filter_sql} "
        f"AND substr(ce.created_at,1,10) >= ? "
        f"GROUP BY hh ORDER BY n DESC, hh ASC LIMIT 1",
        (*filter_args, seven_days_ago)).fetchone()
    if peak_row and peak_row['hh']:
        hh = int(peak_row['hh'])
        bucket_end = (hh + 2) % 24
        peak_label = f'{hh:02d}:00 – {bucket_end:02d}:00'
        peak_value = peak_row['n']
    else:
        peak_label = '—'
        peak_value = 0

    cards.append({
        'id': 'cp_screenings_today',
        'label': f'{scope} · screenings today',
        'icon': '⊙',
        'value': screenings_today,
        'trend': f'Stops recorded at {scope} Checkpoint · {today}',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_screenings_today',
    })
    cards.append({
        'id': 'cp_travelers_flagged',
        'label': f'{scope} · travelers flagged',
        'icon': '!',
        'value': flagged_today,
        'trend': f'Flagged matches at {scope} Checkpoint today',
        'trend_kind': 'alert',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_travelers_flagged',
    })
    cards.append({
        'id': 'cp_total_travelers',
        'label': f'{scope} · total travelers',
        'icon': '◉',
        'value': unique_travelers,
        'trend': f'Distinct Central Persons screened at {scope} · {total_local} screening(s)',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_total_travelers',
    })
    cards.append({
        'id': 'cp_peak_hour',
        'label': f'{scope} · peak travel hour',
        'icon': '⌁',
        'value': peak_label,
        'trend': f'{peak_value} stop(s) in the last 7 days',
        'module': 'checkpoints',
        'location_scope': scope,
        'kind': 'cp_peak_hour',
    })
    return cards


def _fingerprint_dashboard_cards(c, today):
    return [
        {'id':'fp_pending','label':'Pending clearances','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Pending Review'").fetchone()[0],
         'trend':'Require officer review','module':'fingerprint'},
        {'id':'fp_today','label':'Applications today','icon':'◉',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
         'trend':f'New intake · {today}','module':'fingerprint'},
        {'id':'fp_approved','label':'Approved clearances','icon':'✓',
         'value':c.execute("SELECT COUNT(*) FROM clearance_applications WHERE status='Approved'").fetchone()[0],
         'trend':'Certificates issued','module':'fingerprint'},
        {'id':'fp_total','label':'Total applications','icon':'⌂',
         'value':c.execute('SELECT COUNT(*) FROM clearance_applications').fetchone()[0],
         'trend':'All-time clearance volume','module':'fingerprint'},
    ]


def _airport_dashboard_cards(c, today):
    total = c.execute('SELECT COUNT(*) FROM airport_passengers').fetchone()[0]
    arrivals = c.execute("SELECT COUNT(*) FROM airport_passengers WHERE movement='Arrival'").fetchone()[0]
    departures = c.execute("SELECT COUNT(*) FROM airport_passengers WHERE movement='Departure'").fetchone()[0]
    today_movements = c.execute(
        "SELECT COUNT(*) FROM airport_passengers WHERE travel_date=?", (today,)).fetchone()[0]
    return [
        {'id':'ap_today','label':'Movements today','icon':'✈',
         'value':today_movements,'trend':f'Travel date {today}','module':'airport'},
        {'id':'ap_arrivals','label':'Arrivals (all-time)','icon':'↓',
         'value':arrivals,'trend':'Inbound movements on register','module':'airport'},
        {'id':'ap_departures','label':'Departures (all-time)','icon':'↑',
         'value':departures,'trend':'Outbound movements on register','module':'airport'},
        {'id':'ap_total','label':'Total movements','icon':'◉',
         'value':total,'trend':'All-time passenger register','module':'airport'},
    ]


def _cid_dashboard_cards(c, today):
    return [
        {'id':'cid_open','label':'Open crime cases','icon':'⌂',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE status<>'Closed'").fetchone()[0],
         'trend':'Active investigations','module':'cid'},
        {'id':'cid_active_alerts','label':'Active suspect alerts','icon':'!',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect' AND alert_status='Active alert'").fetchone()[0],
         'trend':'Restricted operational data','trend_kind':'alert','module':'cid'},
        {'id':'cid_cases_today','label':'Cases reported today','icon':'◉',
         'value':c.execute("SELECT COUNT(*) FROM crime_cases WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
         'trend':f'New intake · {today}','module':'cid'},
        {'id':'cid_suspects','label':'Suspects on file','icon':'⌁',
         'value':c.execute("SELECT COUNT(*) FROM suspect_alerts WHERE role='Suspect'").fetchone()[0],
         'trend':'All-time suspect listings','module':'cid'},
    ]


def _time_ago(iso_ts, now_ts):
    """Best-effort "N mins ago" formatter for the live activity feed.

    Accepts SQLite CURRENT_TIMESTAMP-style strings ("YYYY-MM-DD HH:MM:SS")
    or date-only strings ("YYYY-MM-DD"). Returns '' on parse failure.
    """
    if not iso_ts:
        return ''
    s = str(iso_ts).strip().replace('T', ' ')
    try:
        if len(s) >= 19 and s[10] == ' ':
            tm = time.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
        elif len(s) == 10:
            tm = time.strptime(s + ' 12:00:00', '%Y-%m-%d %H:%M:%S')
        else:
            return ''
        ts = time.mktime(tm)
    except Exception:
        return ''
    delta = max(0, int(now_ts - ts))
    if delta < 60: return 'just now'
    if delta < 3600: return f'{delta // 60} min ago'
    if delta < 86400: return f'{delta // 3600} hr ago'
    return f'{delta // 86400} d ago'


def _build_activity_feed(c, role, is_admin, scope, is_checkpoint, now_ts, cp_scope_sql):
    """Build the real-time activity stream for the dashboard.

    Each entry is a dict with:
      module       'fingerprint' | 'airport' | 'cid' | 'checkpoints'
      kind         short identifier
      id           record id
      title        human-friendly headline (e.g. 'Screened Jama Abdi')
      subtitle     status / location context
      at           raw ISO-ish timestamp
      time_ago     formatted 'N mins ago' string
      dot_color    'blue' | 'cyan' | 'amber' | 'green' | 'red'
      location_code  (checkpoint only) 'South' / 'East' / 'West'
    """
    events = []

    if is_admin or role == ROLE_FINGERPRINT:
        for r in c.execute('''SELECT a.application_id AS id, a.purpose AS title,
            a.status AS subtitle, a.created_at AS at,
            p.full_name AS person_name
            FROM clearance_applications a
            JOIN persons p ON p.id=a.person_id
            ORDER BY a.id DESC LIMIT 8''').fetchall():
            name = r['person_name'] or 'applicant'
            events.append({
                'module': 'fingerprint',
                'kind': 'clearance',
                'id': r['id'],
                'title': f'Clearance · {name}',
                'subtitle': f'{r["title"]} · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'blue',
            })

    if is_admin or role == ROLE_AIRPORT:
        for r in c.execute('''SELECT a.record_id AS id, a.route AS route,
            a.movement AS movement, a.travel_date AS at,
            p.full_name AS person_name
            FROM airport_passengers a
            JOIN persons p ON p.id=a.person_id
            ORDER BY a.id DESC LIMIT 8''').fetchall():
            name = r['person_name'] or 'traveller'
            events.append({
                'module': 'airport',
                'kind': 'airport',
                'id': r['id'],
                'title': f'{r["movement"]} · {name}',
                'subtitle': r['route'] or '',
                'at': r['at'] or '',
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'cyan',
            })

    if is_admin or role == ROLE_CID:
        for r in c.execute('''SELECT cc.case_id AS id, cc.category AS title,
            cc.status AS subtitle, cc.created_at AS at
            FROM crime_cases cc ORDER BY cc.id DESC LIMIT 8''').fetchall():
            events.append({
                'module': 'cid',
                'kind': 'case',
                'id': r['id'],
                'title': f'Case · {r["title"]}',
                'subtitle': f'CID · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'amber',
            })

    if is_admin or is_checkpoint:
        cp_filter, cp_args = cp_scope_sql()
        for r in c.execute(
            f"SELECT ce.event_id AS id, ce.checkpoint_location AS location_label, "
            f"ce.location_code, ce.screening_result AS subtitle, ce.created_at AS at, "
            f"ce.action_taken, "
            f"p.full_name AS person_name, p.person_id AS person_code "
            f"FROM checkpoint_events ce JOIN persons p ON p.id=ce.person_id "
            f"{cp_filter} ORDER BY ce.id DESC LIMIT 10",
            cp_args).fetchall():
            loc_label = r['location_label'] or (f"{(r['location_code'] or '')} Checkpoint" if r['location_code'] else 'Checkpoint')
            name = r['person_name'] or r['person_code'] or 'traveller'
            verb = 'Flagged' if r['subtitle'] == 'Flagged match' else 'Screened'
            events.append({
                'module': 'checkpoints',
                'kind': 'checkpoint',
                'id': r['id'],
                'title': f'{verb} {name}',
                'subtitle': f'{loc_label} · {r["subtitle"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'red' if r['subtitle'] == 'Flagged match' else 'green',
                'location_code': r['location_code'],
            })

    if is_admin or role == ROLE_REGISTRATION:
        for r in c.execute('''SELECT a.action_id AS id, a.action_type AS action_type,
            a.classification AS subtitle, a.status AS status, a.created_at AS at,
            o.full_name AS officer_name, o.service_id AS officer_code
            FROM officer_conduct_actions a JOIN officers o ON o.id=a.officer_id
            ORDER BY a.id DESC LIMIT 8''').fetchall():
            name = r['officer_name'] or r['officer_code'] or 'officer'
            events.append({
                'module': 'conduct',
                'kind': 'conduct',
                'id': r['id'],
                'title': f'Conduct · {name}',
                'subtitle': f'{r["subtitle"]} · {r["status"]}',
                'at': r['at'],
                'time_ago': _time_ago(r['at'], now_ts),
                'dot_color': 'red' if r['action_type'] == 'Disciplinary / Penalty' else 'green',
            })

    events.sort(key=lambda e: e.get('at') or '', reverse=True)
    return events[:16]
