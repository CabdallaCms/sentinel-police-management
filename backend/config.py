"""Sentinel shared configuration.

Single source of truth for filesystem paths, environment-derived settings,
the in-memory session-token map and every domain constant (roles,
permissions, module maps, officer / station / crime / conduct vocabularies,
review-gate window, API aliases and shared SQL SELECT fragments).

Moved verbatim out of ``backend/server.py`` — values are unchanged.
Standard library only.
"""
import datetime, os


# When this process started — surfaced by /api/health so an operator can tell
# a freshly started server from one that has been serving for hours.
SERVER_STARTED_AT = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DB_PATH = os.environ.get('SENTINEL_DB', os.path.join(ROOT, 'sentinel.db'))
UPLOAD_DIR = os.environ.get('SENTINEL_UPLOADS', os.path.join(ROOT, 'uploads'))
TOKENS = {}


# Columns added after the initial migration (applied to existing databases).
ADDED_COLUMNS = {
    'users': [
        ('location_scope', "ALTER TABLE users ADD COLUMN location_scope TEXT"),
    ],
    'persons': [
        ('first_name', "ALTER TABLE persons ADD COLUMN first_name TEXT"),
        ('second_name', "ALTER TABLE persons ADD COLUMN second_name TEXT"),
        ('third_name', "ALTER TABLE persons ADD COLUMN third_name TEXT"),
        ('fourth_name', "ALTER TABLE persons ADD COLUMN fourth_name TEXT"),
        ('mother_name', "ALTER TABLE persons ADD COLUMN mother_name TEXT"),
        ('place_of_birth', "ALTER TABLE persons ADD COLUMN place_of_birth TEXT"),
        ('residence', "ALTER TABLE persons ADD COLUMN residence TEXT"),
        ('occupation', "ALTER TABLE persons ADD COLUMN occupation TEXT"),
        ('passport_id', "ALTER TABLE persons ADD COLUMN passport_id TEXT"),
        ('photo_path', "ALTER TABLE persons ADD COLUMN photo_path TEXT"),
    ],
    'airport_passengers': [
        ('airline', "ALTER TABLE airport_passengers ADD COLUMN airline TEXT"),
        ('origin_city', "ALTER TABLE airport_passengers ADD COLUMN origin_city TEXT"),
        ('destination_city', "ALTER TABLE airport_passengers ADD COLUMN destination_city TEXT"),
    ],
    'clearance_applications': [
        ('guardian_id', "ALTER TABLE clearance_applications ADD COLUMN guardian_id TEXT"),
        ('guardian_occupation', "ALTER TABLE clearance_applications ADD COLUMN guardian_occupation TEXT"),
        ('guardian_address', "ALTER TABLE clearance_applications ADD COLUMN guardian_address TEXT"),
        ('guardian_phone', "ALTER TABLE clearance_applications ADD COLUMN guardian_phone TEXT"),
        ('applicant_docs', "ALTER TABLE clearance_applications ADD COLUMN applicant_docs TEXT"),
        ('guardian_docs', "ALTER TABLE clearance_applications ADD COLUMN guardian_docs TEXT"),
        ('applicant_photo', "ALTER TABLE clearance_applications ADD COLUMN applicant_photo TEXT"),
        # Printable-application extras (Section 01 of the Good Conduct form).
        ('sex', "ALTER TABLE clearance_applications ADD COLUMN sex TEXT"),
        ('email', "ALTER TABLE clearance_applications ADD COLUMN email TEXT"),
    ],
    'crime_cases': [
        ('incident_summary', "ALTER TABLE crime_cases ADD COLUMN incident_summary TEXT"),
    ],
    'suspect_alerts': [
        ('role', "ALTER TABLE suspect_alerts ADD COLUMN role TEXT NOT NULL DEFAULT 'Suspect'"),
        ('origin', "ALTER TABLE suspect_alerts ADD COLUMN origin TEXT NOT NULL DEFAULT 'Direct Intelligence Listing'"),
    ],
    'checkpoint_events': [
        ('purpose_of_visit', "ALTER TABLE checkpoint_events ADD COLUMN purpose_of_visit TEXT"),
        ('current_address', "ALTER TABLE checkpoint_events ADD COLUMN current_address TEXT"),
        ('permanent_address', "ALTER TABLE checkpoint_events ADD COLUMN permanent_address TEXT"),
        ('traveler_photo', "ALTER TABLE checkpoint_events ADD COLUMN traveler_photo TEXT"),
        ('traveler_docs', "ALTER TABLE checkpoint_events ADD COLUMN traveler_docs TEXT"),
        ('guardian_person_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_person_id INTEGER REFERENCES persons(id)"),
        ('guardian_name', "ALTER TABLE checkpoint_events ADD COLUMN guardian_name TEXT"),
        ('guardian_relationship', "ALTER TABLE checkpoint_events ADD COLUMN guardian_relationship TEXT"),
        ('guardian_phone', "ALTER TABLE checkpoint_events ADD COLUMN guardian_phone TEXT"),
        ('guardian_address', "ALTER TABLE checkpoint_events ADD COLUMN guardian_address TEXT"),
        ('guardian_occupation', "ALTER TABLE checkpoint_events ADD COLUMN guardian_occupation TEXT"),
        ('guardian_national_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_national_id TEXT"),
        ('guardian_passport_id', "ALTER TABLE checkpoint_events ADD COLUMN guardian_passport_id TEXT"),
        ('guardian_docs', "ALTER TABLE checkpoint_events ADD COLUMN guardian_docs TEXT"),
        # Explicit location metadata: 'location_code' is the canonical short code
        # (South / East / West); 'checkpoint_location' is the human-friendly label
        # (e.g. 'South Checkpoint'). Both are written on every create so dashboards,
        # the identity profile, and the activity feed can show the exact location
        # without joining the locations table.
        ('location_code', "ALTER TABLE checkpoint_events ADD COLUMN location_code TEXT"),
        ('checkpoint_location', "ALTER TABLE checkpoint_events ADD COLUMN checkpoint_location TEXT"),
    ],
    'police_stations': [
        ('station_tier', "ALTER TABLE police_stations ADD COLUMN station_tier TEXT"),
        ('commander_id', "ALTER TABLE police_stations ADD COLUMN commander_id INTEGER REFERENCES officers(id)"),
        ('deputy_id', "ALTER TABLE police_stations ADD COLUMN deputy_id INTEGER REFERENCES officers(id)"),
        ('contact_phone', "ALTER TABLE police_stations ADD COLUMN contact_phone TEXT"),
        ('cell_capacity', "ALTER TABLE police_stations ADD COLUMN cell_capacity INTEGER"),
        ('operational_status', "ALTER TABLE police_stations ADD COLUMN operational_status TEXT DEFAULT 'Active'"),
    ],
}

NAME_PART_FIELDS = ('first_name', 'second_name', 'third_name', 'fourth_name')
PERSON_FIELDS = NAME_PART_FIELDS + ('full_name', 'national_id', 'date_of_birth', 'phone',
                                    'mother_name', 'place_of_birth', 'residence',
                                    'occupation', 'passport_id', 'photo_path')

# ---------------------------------------------------------------------------
# Fingerprint / clearance-application policy.
# ---------------------------------------------------------------------------
# The mandatory `clearance_reason` values offered by the application form.
# Submissions are validated against exactly this list (case-insensitive) and
# the printable application template prints the selected reason verbatim.
CLEARANCE_REASONS = ('Education', 'Travel', 'Employment', 'Citizenship', 'Licence')

# A clearance application may only be approved once the mandatory review
# window has elapsed. System Administrators bypass the gate entirely;
# Fingerprint Officers (and every other non-admin reviewer) must wait.
FINGERPRINT_REVIEW_WINDOW_HOURS = 12

# Accepted spellings for the two roles the approval gate cares about. The
# stored role is canonical ('SystemAdmin' / 'FingerprintUnit') but the API
# also tolerates the spec's snake_case aliases ('admin',
# 'fingerprint_officer') and the historical compound forms.
ADMIN_ROLE_KEYS = {'admin', 'systemadmin', 'systemadministrator'}
FINGERPRINT_ROLE_KEYS = {'fingerprint', 'fingerprintunit', 'fingerprintofficer',
                         'fingerprintunitofficer', 'fpofficer'}

# Build marker — surfaced by /api/health and printed on startup so an operator
# can confirm the running process carries the review-lock rules.
BUILD_TAG = 'sentinel-fingerprint-review-lock-12h'

# /api/fingerprint/applications* is the spec-facing alias for the clearance
# register; both prefixes resolve to the same handler and module gate.
FINGERPRINT_API_ALIAS = '/api/fingerprint/applications'
CLEARANCE_API = '/api/clearance-applications'


# The exact rejection text mandated by the spec for a non-admin approving
# inside the mandatory review window.
REVIEW_LOCK_MESSAGE = ('Review period active. Standard officers must wait 12 hours '
                       'before approving.')


# ---------------------------------------------------------------------------
# Role-Based Access Control (RBAC) — central definition of roles, the modules
# they are allowed to use, and any data-scoping (e.g. checkpoint location).
# ---------------------------------------------------------------------------
# Canonical role identifiers (stored in users.role and seed data).
ROLE_ADMIN = 'SystemAdmin'
ROLE_FINGERPRINT = 'FingerprintUnit'
ROLE_AIRPORT = 'AirportControl'
ROLE_CID = 'CIDUnit'
# HR Directorate — the Police Officers Registration Office. Holds the
# 'officers' module (roster, green-badge promotions, red-badge discipline)
# plus the station register it needs for postings, WITHOUT any admin rights.
ROLE_HR = 'hr_officer'
# The Police Officer Registration Office IS the HR Directorate — the
# dashboard builders refer to it by this name.
ROLE_REGISTRATION = ROLE_HR
ROLE_CHECKPOINT_SOUTH = 'CheckpointSouth'
ROLE_CHECKPOINT_EAST = 'CheckpointEast'
ROLE_CHECKPOINT_WEST = 'CheckpointWest'
# Chief Commander of Police Office (HQ / Command). A GLOBAL, cross-department
# oversight role: it reads every directorate (CID, Personnel, Transport),
# owns the executive analytics surface and manages the station registry —
# but it is NOT a SystemAdmin (no user management, no unit-record writes).
ROLE_CHIEF = 'chief_commander'

# Fine-grained permission strings. Modules (below) gate which PAGES a role
# can open; permissions gate cross-cutting CAPABILITIES that do not map onto
# a single register (global analytics, station management, read-only
# department views). `has_permission()` is the single lookup.
PERM_ANALYTICS_GLOBAL = 'analytics:global'
PERM_STATIONS_MANAGE = 'stations:manage'
PERM_CID_VIEW = 'cid:view'
PERM_PERSONNEL_VIEW = 'personnel:view'
PERM_TRANSPORT_VIEW = 'transport:view'
CHIEF_PERMISSIONS = frozenset({PERM_ANALYTICS_GLOBAL, PERM_STATIONS_MANAGE,
                               PERM_CID_VIEW, PERM_PERSONNEL_VIEW, PERM_TRANSPORT_VIEW})

# Canonical normalized alias for any Checkpoint officer regardless of
# location. The spec mandates that role-checking logic accept BOTH the
# legacy compound form ('CheckpointSouth' / 'CheckpointEast' /
# 'CheckpointWest') AND the canonical normalized form
# ('checkpoint_officer'). The session payload always surfaces the
# normalized form so the frontend never has to special-case the
# compound role strings.
ROLE_CHECKPOINT_OFFICER = 'checkpoint_officer'

# Map every accepted Checkpoint-officer spelling to the normalized
# alias. /api/login, /api/me, and every module gate consult this
# alias so a token whose role is 'CheckpointSouth' is treated
# exactly like one whose role is 'checkpoint_officer'.
CHECKPOINT_ROLE_ALIASES = {
    ROLE_CHECKPOINT_SOUTH: ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_EAST: ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_WEST: ROLE_CHECKPOINT_OFFICER,
    'CheckpointSouth': ROLE_CHECKPOINT_OFFICER,
    'CheckpointEast': ROLE_CHECKPOINT_OFFICER,
    'CheckpointWest': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_south': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_east': ROLE_CHECKPOINT_OFFICER,
    'checkpoint_west': ROLE_CHECKPOINT_OFFICER,
    'cp_south': ROLE_CHECKPOINT_OFFICER,
    'cp_east': ROLE_CHECKPOINT_OFFICER,
    'cp_west': ROLE_CHECKPOINT_OFFICER,
    'cp.south': ROLE_CHECKPOINT_OFFICER,
    'cp.east': ROLE_CHECKPOINT_OFFICER,
    'cp.west': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (South)': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (East)': ROLE_CHECKPOINT_OFFICER,
    'Checkpoint Officer (West)': ROLE_CHECKPOINT_OFFICER,
    ROLE_CHECKPOINT_OFFICER: ROLE_CHECKPOINT_OFFICER,
}


ALL_ROLES = (ROLE_ADMIN, ROLE_FINGERPRINT, ROLE_AIRPORT, ROLE_CID, ROLE_HR,
             ROLE_CHECKPOINT_SOUTH, ROLE_CHECKPOINT_EAST, ROLE_CHECKPOINT_WEST,
             ROLE_CHIEF)

# Spec-facing snake_case name for every canonical role. Surfaced by
# /api/me as `role_alias` (and `spec_role`) so a client can key its UI off
# `fingerprint_officer` / `admin` exactly as the spec describes, while the
# stored `role` stays canonical.
SPEC_ROLE_ALIASES = {
    ROLE_ADMIN: 'admin',
    ROLE_FINGERPRINT: 'fingerprint_officer',
    ROLE_AIRPORT: 'airport_officer',
    ROLE_CID: 'cid_officer',
    ROLE_HR: 'hr_officer',
    ROLE_CHIEF: 'chief_commander',
}
SPEC_ROLE_DEFAULT = 'fingerprint_officer'


# Spec-facing / snake_case aliases for the unit roles. A user stored as
# 'fingerprint_officer' (or signed in as `admin`) must behave exactly like
# the canonical 'FingerprintUnit' / 'SystemAdmin' row: same modules, same
# RBAC gates, same role label, same 12-hour review rule.
UNIT_ROLE_ALIASES = {
    ROLE_ADMIN: ROLE_ADMIN,
    'admin': ROLE_ADMIN,
    'system_admin': ROLE_ADMIN,
    'systemadministrator': ROLE_ADMIN,
    'administrator': ROLE_ADMIN,
    ROLE_FINGERPRINT: ROLE_FINGERPRINT,
    'fingerprint_officer': ROLE_FINGERPRINT,
    'fingerprintofficer': ROLE_FINGERPRINT,
    'fingerprint_unit': ROLE_FINGERPRINT,
    'fp_officer': ROLE_FINGERPRINT,
    'fp.officer': ROLE_FINGERPRINT,
    ROLE_AIRPORT: ROLE_AIRPORT,
    'airport_officer': ROLE_AIRPORT,
    'airport_control': ROLE_AIRPORT,
    'ap_officer': ROLE_AIRPORT,
    ROLE_CID: ROLE_CID,
    'cid_officer': ROLE_CID,
    'cidunit': ROLE_CID,
    'criminal_investigation': ROLE_CID,
    # HR Directorate aliases — 'HROfficer', 'hr', 'Human Resources', … all
    # resolve to the canonical 'hr_officer' role so a token issued for any
    # spelling still carries the officers module set.
    ROLE_HR: ROLE_HR,
    'hr': ROLE_HR,
    'hrofficer': ROLE_HR,
    'hr_officer': ROLE_HR,
    'hr.officer': ROLE_HR,
    'hr_directorate': ROLE_HR,
    'hrdirectorate': ROLE_HR,
    'human_resources': ROLE_HR,
    'humanresources': ROLE_HR,
    'personnel_officer': ROLE_HR,
    # Chief Commander of Police Office (HQ / Command) aliases.
    ROLE_CHIEF: ROLE_CHIEF,
    'chief_commander': ROLE_CHIEF,
    'chiefcommander': ROLE_CHIEF,
    'chief.commander': ROLE_CHIEF,
    'ChiefCommander': ROLE_CHIEF,
    'commander_hq': ROLE_CHIEF,
    'hq_command': ROLE_CHIEF,
    'police_hq': ROLE_CHIEF,
}

# Canonical checkpoint location codes. The data uses the short codes ('South',
# 'East', 'West') so the scoping stays in sync with existing seed data.
CHECKPOINT_LOCATIONS = ('South', 'East', 'West')

# ---------------------------------------------------------------------------
# Officer Registration domain (Police Registrations & Management module).
# ---------------------------------------------------------------------------
# Fixed option lists for the officer register. The API validates every
# dropdown value against exactly these lists (case-insensitive), and the
# frontend renders the same lists so client- and server-side rules match.
OFFICER_RANKS = ('Constable', 'Corporal', 'Sergeant', 'Inspector',
                 'Chief Inspector', 'Superintendent', 'Commander', 'General')

OFFICER_UNITS = ('General Patrol', 'CID / Criminal Investigation',
                 'Traffic Control', 'Rapid Response Unit',
                 'Special Protection Unit', 'Logistics')

OFFICER_DUTY_STATUSES = ('Active', 'Suspended', 'Leave', 'Terminated', 'Retired')

OFFICER_BLOOD_GROUPS = ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')

GUARANTOR_RELATIONSHIPS = ('Parent', 'Spouse', 'Relative', 'Community Leader', 'Other')

OFFICER_DOC_TYPES_PRIMARY = ('National ID', 'Passport', 'Birth Certificate',
                             'Letter of Guarantee')
OFFICER_DOC_TYPES_SECONDARY = ('Background Check', 'Reference Letter',
                               'Military Discharge', 'Other')

OFFICER_ORIGIN_REGIONS = ('Sool', 'Sanaag', 'East Togdheer', 'Togdheer', 'Awdal',
                          'Woqooyi Galbeed', 'Bari', 'Nugaal', 'Mudug', 'Galguduud',
                          'Hiiraan', 'Middle Shabelle', 'Lower Shabelle', 'Banaadir',
                          'Bay', 'Bakool', 'Gedo', 'Lower Juba', 'Middle Juba')

COMMANDER_RANKS = ('Inspector', 'Chief Inspector', 'Superintendent', 'Commander', 'General')
STATION_TIERS = ('Regional HQ', 'District HQ', 'Outpost', 'Checkpoint', 'Border Post')
STATION_STATUSES = ('Active', 'Inactive', 'Maintenance')
STATION_REGIONS = ('Sool', 'Sanaag', 'East Togdheer')
STATION_DISTRICTS = {
    'Sool': ('Laascaanood', 'Caynabo', 'Xudun', 'Taleex'),
    'Sanaag': ('Ceerigaabo', 'Ceel Afweyn', 'Garadag', 'Badhan', 'Dhahar'),
    'East Togdheer': ('Burao', 'Oodweyne', 'Buuhoodle'),
}
REGION_CODES = {'Sool': 'SOL', 'Sanaag': 'SAN', 'East Togdheer': 'ETG'}
CRIME_CATEGORIES = ('Theft/Burglary', 'Assault', 'Robbery', 'Traffic Accident', 'Homicide',
                    'Fraud', 'Domestic Incident', 'Public Order', 'Cybercrime', 'Other')
CRIME_SEVERITIES = ('Low', 'Medium', 'High', 'Critical')
CRIME_STATUSES = ('Reported / Open', 'Under Investigation', 'Referred to Court', 'Closed', 'Unresolved')

# ---------------------------------------------------------------------------
# Departmental analytics vocabularies.
# ---------------------------------------------------------------------------
# Case lifecycle labels used by the CID crime register. `crime_cases.status`
# predates CRIME_STATUSES (the intake form), so the union of both lists keeps
# the analytics axes stable for either spelling.
CASE_STATUSES = ('Reported', 'Reported / Open', 'Under Investigation',
                 'Submitted for Prosecution', 'Referred to Court', 'Closed', 'Unresolved')

# 24-hour bands used by every time-of-day chart (fixed order = fixed axis).
TIME_OF_DAY_BUCKETS = ('Morning (06-12)', 'Afternoon (12-18)',
                       'Evening (18-24)', 'Night (00-06)')

# Airport movement directions (inbound / outbound counters).
AIRPORT_MOVEMENTS = ('Arrival', 'Departure')

# HR Directorate (Police Officers Registration Office) lists.
PROMOTION_STATUSES = ('Awaiting Verification', 'Verified', 'Rejected')
PROMOTION_PENDING_STATUS = 'Awaiting Verification'
DISCIPLINE_ACTION_TYPES = ('Misconduct', 'Suspension', 'Demotion', 'Warning', 'Investigation')
DISCIPLINE_STATUSES = ('Pending', 'In Review', 'Confirmed', 'Closed', 'Appealed')
# "Open" disciplinary actions — the ones counted by the red badge.
DISCIPLINE_OPEN_STATUSES = ('Pending', 'In Review', 'Appealed')

# Analytics module names accepted by GET /api/analytics?module=<name>.
ANALYTICS_MODULES = ('cid', 'officers', 'vehicles', 'stations')
# The CID analytics bundle covers the four Criminal Investigation Directorate
# units; a unit officer only ever receives the section for their own module.
CID_ANALYTICS_SECTIONS = ('fingerprint', 'crime', 'checkpoint', 'airport')
CID_SECTION_MODULES = {'fingerprint': 'fingerprint', 'crime': 'cid',
                       'checkpoint': 'checkpoints', 'airport': 'airport'}

REPORTING_PARTY_TYPES = ('Victim', 'Witness', 'Third-Party Representative', 'Police')
VICTIM_GENDERS = ('Male', 'Female', 'Other / Prefer not to say')
EVIDENCE_TYPES = ('Photo', 'Statement', 'Physical item', 'Digital file', 'Other')

# Upload policy for the officer register.
OFFICER_IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
OFFICER_DOC_EXTS = {'.pdf', '.jpg', '.jpeg', '.png'}
OFFICER_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# Officer Conduct, Promotions & Disciplinary Management domain
# (Police Officer Registration Office — HR Directorate).
# ---------------------------------------------------------------------------
# The two top-level action types. Promotions/commendations render green
# (#2e7d32) in the UI, disciplinary actions render red (#c62828).
CONDUCT_ACTION_TYPES = ('Promotion / Commendation', 'Disciplinary / Penalty')

# Colour key for the split-view dashboard (surfaced to the frontend).
CONDUCT_TYPE_COLOURS = {'Promotion / Commendation': '#2e7d32',
                        'Disciplinary / Penalty': '#c62828'}

# The specific conduct classification within each action type. A
# submission's classification MUST belong to its action type — the pair
# is validated server-side on both submit and review.
CONDUCT_PROMOTION_CLASSES = ('Rank Advancement', 'Official Commendation',
                             'Medal of Bravery', 'Merit Award')
CONDUCT_DISCIPLINARY_CLASSES = ('Rank Demotion', 'Official Reprimand',
                                'Temporary Suspension', 'Formal Dismissal')
CONDUCT_CLASSIFICATIONS = {
    'Promotion / Commendation': CONDUCT_PROMOTION_CLASSES,
    'Disciplinary / Penalty': CONDUCT_DISCIPLINARY_CLASSES,
}

# Classifications that carry a rank change and therefore REQUIRE a
# proposed_rank that is a valid transition from the officer's current rank
# (strictly HIGHER for Rank Advancement, strictly LOWER for Rank Demotion).
CONDUCT_RANK_CLASSIFICATIONS = ('Rank Advancement', 'Rank Demotion')

# Disciplinary classifications that also adjust the officer's duty status
# once HR verifies & approves the file.
CONDUCT_DUTY_EFFECTS = {'Formal Dismissal': 'Terminated',
                        'Temporary Suspension': 'Suspended'}

# Verification & approval pipeline. Every submission defaults to
# 'Submitted to HR'; only Officer Registration Office / HR staff may move
# a file along the pipeline (Under HR Review -> Verified & Approved /
# Rejected) via POST /api/conduct/<id>/review.
CONDUCT_STATUSES = ('Submitted to HR', 'Under HR Review',
                    'Verified & Approved', 'Rejected')
CONDUCT_STATUS_DEFAULT = 'Submitted to HR'
CONDUCT_STATUS_APPROVED = 'Verified & Approved'
CONDUCT_STATUS_REJECTED = 'Rejected'
CONDUCT_STATUS_REVIEWING = 'Under HR Review'
CONDUCT_PENDING_STATUSES = (CONDUCT_STATUS_DEFAULT, CONDUCT_STATUS_REVIEWING)

# Short aliases accepted for the category query parameter / action type.
CONDUCT_CATEGORY_ALIASES = {
    'promotion': 'Promotion / Commendation',
    'commendation': 'Promotion / Commendation',
    'disciplinary': 'Disciplinary / Penalty',
    'penalty': 'Disciplinary / Penalty',
    'discipline': 'Disciplinary / Penalty',
}

# Supporting report documents: PDF/JPG only, max 5 MB (spec).
CONDUCT_DOC_EXTS = {'.pdf', '.jpg', '.jpeg'}
CONDUCT_MAX_UPLOAD_BYTES = OFFICER_MAX_UPLOAD_BYTES  # 5 MB

# A conduct narrative is a mandatory detailed justification — a few words
# is not an acceptable record for a personnel file.
CONDUCT_MIN_NARRATIVE_CHARS = 20

ROLE_LABELS = {
    ROLE_ADMIN: 'System Administrator',
    ROLE_FINGERPRINT: 'Fingerprint Unit Officer',
    ROLE_AIRPORT: 'Airport Control Officer',
    ROLE_CID: 'CID Criminal Unit Officer',
    ROLE_HR: 'HR Directorate Officer',
    ROLE_CHECKPOINT_SOUTH: 'Checkpoint Officer (South)',
    ROLE_CHECKPOINT_EAST: 'Checkpoint Officer (East)',
    ROLE_CHECKPOINT_WEST: 'Checkpoint Officer (West)',
    ROLE_CHIEF: 'Chief Commander (HQ / Command)',
}

# Map a role to the operational modules it is allowed to use. Admins get
# everything; unit users get their single module; checkpoint users only get
# the Checkpoint module and their own location scope.
#
# Regional registration modules (frontend-only registers for now):
#   * 'policesearch' — Central Police Search (officers/stations/cars filter
#     by Region → District → Village); granted to the same roles that can
#     see the Central Person Search ('people').
#   * 'stations' / 'officers' / 'cars' — Police Registrations & Management;
#     administrative operations, granted to SystemAdmin only.
ROLE_MODULES = {
    ROLE_ADMIN: {'dashboard', 'analytics', 'admin', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints',
                 'policesearch', 'stations', 'officers', 'cars', 'crimes', 'conduct'},
    ROLE_FINGERPRINT: {'dashboard', 'people', 'fingerprint', 'policesearch'},
    ROLE_AIRPORT: {'dashboard', 'people', 'airport', 'policesearch'},
    ROLE_CID: {'dashboard', 'people', 'cid', 'policesearch', 'crimes'},
    # HR Directorate: the full Police Officers register (roster + promotions +
    # discipline, and their analytics bundle) plus the station register it
    # posts officers against and the central registries it searches. No
    # 'admin', no 'analytics', no CID/checkpoint/airport/fingerprint modules.
    ROLE_HR: {'dashboard', 'people', 'policesearch', 'stations', 'officers'},
    ROLE_CHECKPOINT_SOUTH: {'dashboard', 'checkpoints'},
    ROLE_CHECKPOINT_EAST: {'dashboard', 'checkpoints'},
    ROLE_CHECKPOINT_WEST: {'dashboard', 'checkpoints'},
    # Chief Commander (HQ / Command): the executive dashboard + station
    # oversight pages, plus READ access to every departmental register
    # (CID units, Personnel, Transport). Deliberately no 'admin' (user
    # management) and no 'analytics' (the legacy SystemAdmin flag) — the
    # global analytics surface is its own module, gated by
    # `analytics:global`.
    ROLE_CHIEF: {'dashboard', 'executive', 'oversight', 'people', 'policesearch',
                 'fingerprint', 'airport', 'cid', 'checkpoints', 'crimes',
                 'stations', 'officers', 'conduct', 'cars'},
    # Spec step 1: the canonical normalized alias is also a first-class
    # role. Whether the stored role is 'CheckpointSouth' or
    # 'checkpoint_officer', the module set and scope lookup resolve to
    # the same answer.
    ROLE_CHECKPOINT_OFFICER: {'dashboard', 'checkpoints'},
}

# Map a role to the checkpoint location it is scoped to (or None for non-checkpoint roles).
ROLE_LOCATION_SCOPE = {
    ROLE_ADMIN: None,
    ROLE_FINGERPRINT: None,
    ROLE_AIRPORT: None,
    ROLE_CID: None,
    ROLE_HR: None,
    ROLE_CHIEF: None,
    ROLE_CHECKPOINT_SOUTH: 'South',
    ROLE_CHECKPOINT_EAST: 'East',
    ROLE_CHECKPOINT_WEST: 'West',
    # Spec step 3: 'checkpoint_officer' is the canonical normalised
    # alias; its default scope is empty so the SQL filter never
    # leaks other locations. The CheckpointSouth/East/West seed
    # users keep their explicit location_scope from the users table.
    ROLE_CHECKPOINT_OFFICER: '',
}

# Every unit alias inherits the modules / scope / label of the canonical
# role it resolves to, so a row stored as 'fingerprint_officer' (or a token
# issued for 'admin') is never left with an empty module list.
for _alias, _canonical in UNIT_ROLE_ALIASES.items():
    ROLE_MODULES.setdefault(_alias, ROLE_MODULES[_canonical])
    ROLE_LOCATION_SCOPE.setdefault(_alias, ROLE_LOCATION_SCOPE[_canonical])
    ROLE_LABELS.setdefault(_alias, ROLE_LABELS[_canonical])

# Capability permissions per canonical role. SystemAdmin keeps every
# permission (it already sees everything); the Chief Commander holds the
# global HQ set; unit roles carry only the view permission of their own
# department so `has_permission()` answers consistently for every role.
ROLE_PERMISSIONS = {
    ROLE_ADMIN: set(CHIEF_PERMISSIONS),
    ROLE_CHIEF: set(CHIEF_PERMISSIONS),
    ROLE_FINGERPRINT: {PERM_CID_VIEW},
    ROLE_AIRPORT: {PERM_CID_VIEW},
    ROLE_CID: {PERM_CID_VIEW},
    ROLE_CHECKPOINT_SOUTH: {PERM_CID_VIEW},
    ROLE_CHECKPOINT_EAST: {PERM_CID_VIEW},
    ROLE_CHECKPOINT_WEST: {PERM_CID_VIEW},
    ROLE_CHECKPOINT_OFFICER: {PERM_CID_VIEW},
    ROLE_HR: {PERM_PERSONNEL_VIEW},
}
for _alias, _canonical in UNIT_ROLE_ALIASES.items():
    ROLE_PERMISSIONS.setdefault(_alias, ROLE_PERMISSIONS.get(_canonical, set()))


CONDUCT_SELECT = '''SELECT a.*, o.service_id AS officer_service_id, o.full_name AS officer_name,
       o.rank AS officer_rank, o.duty_status AS officer_duty_status,
       s.station_id AS station_code, s.name AS station_name, s.region AS station_region,
       s.district AS station_district,
       os.station_id AS officer_station_code, os.name AS officer_station_name,
       os.region AS officer_station_region,
       ro.service_id AS reporting_service_id, ro.full_name AS reporting_name,
       rv.service_id AS reviewer_service_id, rv.full_name AS reviewer_name
       FROM officer_conduct_actions a
       JOIN officers o ON o.id = a.officer_id
       LEFT JOIN police_stations s ON s.id = a.station_id
       LEFT JOIN police_stations os ON os.id = o.station_id
       LEFT JOIN officers ro ON ro.id = a.reporting_officer_id
       LEFT JOIN officers rv ON rv.id = a.reviewer_officer_id'''


# ---- identity resolution (universal matching engine) ------------------------
TIER_LABELS = {
    1: 'Tier 1 · Exact National ID / Passport match (auto merge / link)',
    2: 'Tier 2 · Exact 4-part name + date of birth match (high-confidence link)',
    3: 'Tier 3 · 3-part name + mother\u2019s name (fuzzy warning only)',
    4: 'Tier 4 · Partial name match (2\u20134 parts) \u2014 select the record to auto-fill',
}


PROMOTION_SELECT = '''SELECT pr.*, o.service_id, o.full_name, o.rank AS officer_rank,
        o.unit, o.duty_status, s.name AS station_name, s.station_id AS station_code,
        s.region AS station_region, u.display_name AS nominated_by_name,
        v.display_name AS verified_by_name
    FROM officer_promotions pr
    JOIN officers o ON o.id = pr.officer_id
    LEFT JOIN police_stations s ON s.id = o.station_id
    LEFT JOIN users u ON u.id = pr.nominated_by
    LEFT JOIN users v ON v.id = pr.verified_by'''

DISCIPLINE_SELECT = '''SELECT da.*, o.service_id, o.full_name, o.rank AS officer_rank,
        o.unit, o.duty_status, s.name AS station_name, s.station_id AS station_code,
        s.region AS station_region, u.display_name AS reported_by_name
    FROM officer_discipline da
    JOIN officers o ON o.id = da.officer_id
    LEFT JOIN police_stations s ON s.id = o.station_id
    LEFT JOIN users u ON u.id = da.reported_by'''
