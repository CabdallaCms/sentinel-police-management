"""Sentinel case-domain workflows.

Identity resolution (the Tier 1/2/3 person matcher), person upsert,
police stations, the officer register, the crime register, officer
conduct actions and the green-promotion / red-discipline registers —
moved verbatim out of ``backend/server.py``.

Thin HTTP dispatch stays in :mod:`server`; every business rule lives here.
Standard library only.
"""
import json, re
from config import *
from utils import *
from database import *
from auth_views import *


def station_view(row):
    """Public station payload (the frontend resolves stations by station_id)."""
    keys = row.keys() if hasattr(row, 'keys') else []
    def col(name, default=None):
        return row[name] if name in keys else default
    return {
        'id': row['station_id'],
        'station_id': row['station_id'],
        'name': row['name'],
        'code': row['code'],
        'region': row['region'],
        'district': row['district'],
        'village': row['village'],
        'notes': row['notes'],
        'station_tier': col('station_tier'),
        'commander_id': col('commander_id'),
        'deputy_id': col('deputy_id'),
        'contact_phone': col('contact_phone'),
        'cell_capacity': col('cell_capacity'),
        'operational_status': col('operational_status') or 'Active',
        'created_at': row['created_at'],
    }


def resolve_officer_row(c, value):
    v = str(value or '').strip()
    if not v:
        return None
    if v.isdigit():
        return c.execute('SELECT * FROM officers WHERE id=?', (int(v),)).fetchone()
    return c.execute('SELECT * FROM officers WHERE service_id=?', (v,)).fetchone()


def crime_view(row):
    return dict(row) if row else None


def officer_rows(c):
    """Officers joined with their assigned station (code + name)."""
    return c.execute('''SELECT o.*, s.station_id AS station_code, s.name AS station_name
                        FROM officers o
                        LEFT JOIN police_stations s ON s.id = o.station_id
                        ORDER BY o.id DESC''').fetchall()


def officer_view(r):
    """Public officer payload. `station_id` is the human-readable station code."""
    return {
        'id': r['service_id'],
        'service_id': r['service_id'],
        'rank': r['rank'],
        'unit': r['unit'],
        'station_id': r['station_code'],
        'station_name': r['station_name'],
        'date_of_enlistment': r['date_of_enlistment'],
        'duty_status': r['duty_status'],
        'full_name': r['full_name'],
        'mother_name': r['mother_name'],
        'date_of_birth': r['date_of_birth'],
        'place_of_birth': r['place_of_birth'],
        'contact_number': r['contact_number'],
        'height_cm': r['height_cm'],
        'weight_kg': r['weight_kg'],
        'blood_group': r['blood_group'],
        'photo_path': r['photo_path'],
        'region_of_origin': r['region_of_origin'],
        'district_of_origin': r['district_of_origin'],
        'town_village': r['town_village'],
        'guarantor_name': r['guarantor_name'],
        'guarantor_address': r['guarantor_address'],
        'guarantor_occupation': r['guarantor_occupation'],
        'guarantor_relationship': r['guarantor_relationship'],
        'guarantor_contact': r['guarantor_contact'],
        'guarantor_photo': r['guarantor_photo'],
        'doc1_type': r['doc1_type'],
        'doc1_path': r['doc1_path'],
        'doc2_type': r['doc2_type'],
        'doc2_path': r['doc2_path'],
        'created_at': r['created_at'],
    }


def register_officer(c, user, fields, files):
    """Validate and persist an officer registration (multipart or JSON).

    Raises ValueError with a human-readable message on the first failing rule.
    Returns the created officer view (the caller commits the transaction)."""
    def req(key, label):
        v = str(fields.get(key) or '').strip()
        if not v:
            raise ValueError(f'{label} is required')
        return v

    # ---- Section 1: Official & System identifiers -------------------------
    rank = normalise_choice(fields.get('rank'), OFFICER_RANKS)
    if not rank:
        raise ValueError('Rank is required and must be one of: ' + ', '.join(OFFICER_RANKS))
    unit = normalise_choice(fields.get('unit'), OFFICER_UNITS)
    if not unit:
        raise ValueError('Unit / Division is required and must be one of: '
                         + ', '.join(OFFICER_UNITS))
    station_code = req('station_id', 'Assigned station')
    station = c.execute('SELECT * FROM police_stations WHERE station_id=?',
                        (station_code,)).fetchone()
    if not station:
        raise ValueError(f'Assigned station "{station_code}" does not exist')
    date_of_enlistment = req('date_of_enlistment', 'Date of enlistment')
    duty_status = normalise_choice(fields.get('duty_status'), OFFICER_DUTY_STATUSES) or 'Active'

    # ---- Section 2: Personal identification --------------------------------
    full_name = req('full_name', 'Full name')
    mother_name = req('mother_name', "Mother's name")
    date_of_birth = req('date_of_birth', 'Date of birth')
    place_of_birth = req('place_of_birth', 'Place of birth')
    contact_number = req('contact_number', 'Contact number')
    height_cm = str(fields.get('height_cm') or '').strip()
    weight_kg = str(fields.get('weight_kg') or '').strip()
    blood_group = normalise_choice(fields.get('blood_group'), OFFICER_BLOOD_GROUPS)
    if (fields.get('blood_group') or '').strip() and not blood_group:
        raise ValueError('Blood group must be one of: ' + ', '.join(OFFICER_BLOOD_GROUPS))
    photo = save_upload_validated(files.get('photo'), OFFICER_IMAGE_EXTS,
                                  'Officer picture', required=True)

    # ---- Section 3: Regional & origin data ---------------------------------
    region_of_origin = normalise_choice(fields.get('region_of_origin'), OFFICER_ORIGIN_REGIONS)
    if (fields.get('region_of_origin') or '').strip() and not region_of_origin:
        raise ValueError('Region of origin must be one of: ' + ', '.join(OFFICER_ORIGIN_REGIONS))
    district_of_origin = str(fields.get('district_of_origin') or '').strip()
    town_village = str(fields.get('town_village') or '').strip()
    if district_of_origin and not region_of_origin:
        raise ValueError('Select the Region of origin before the District of origin')
    if town_village and not district_of_origin:
        raise ValueError('Select the District of origin before entering the Town / Village')

    # ---- Section 4: Guarantor / emergency contact --------------------------
    guarantor_name = req('guarantor_name', 'Guarantor name')
    guarantor_address = req('guarantor_address', 'Guarantor permanent address')
    guarantor_occupation = str(fields.get('guarantor_occupation') or '').strip()
    guarantor_relationship = normalise_choice(fields.get('guarantor_relationship'),
                                              GUARANTOR_RELATIONSHIPS)
    if (fields.get('guarantor_relationship') or '').strip() and not guarantor_relationship:
        raise ValueError('Guarantor relationship must be one of: '
                         + ', '.join(GUARANTOR_RELATIONSHIPS))
    guarantor_contact = req('guarantor_contact', 'Guarantor contact')
    guarantor_photo = save_upload_validated(files.get('guarantor_photo'),
                                            OFFICER_IMAGE_EXTS, 'Guarantor picture')

    # ---- Section 5: Verification & supporting documents --------------------
    doc1_type = normalise_choice(fields.get('doc1_type'), OFFICER_DOC_TYPES_PRIMARY)
    if not doc1_type:
        raise ValueError('Document Slot 1 type is required and must be one of: '
                         + ', '.join(OFFICER_DOC_TYPES_PRIMARY))
    doc1_path = save_upload_validated(files.get('doc1_file'), OFFICER_DOC_EXTS,
                                      'Document Slot 1 file', required=True)
    doc2_type = normalise_choice(fields.get('doc2_type'), OFFICER_DOC_TYPES_SECONDARY)
    if (fields.get('doc2_type') or '').strip() and not doc2_type:
        raise ValueError('Document Slot 2 type must be one of: '
                         + ', '.join(OFFICER_DOC_TYPES_SECONDARY))
    doc2_file = files.get('doc2_file')
    if doc2_file and not doc2_type:
        raise ValueError('Document Slot 2 type is required when a Slot 2 file is attached')
    if doc2_type and not doc2_file:
        raise ValueError('Document Slot 2 file is required when a Slot 2 type is selected')
    doc2_path = save_upload_validated(doc2_file, OFFICER_DOC_EXTS, 'Document Slot 2 file')

    service_id = new_service_id(c)
    c.execute('''INSERT INTO officers(service_id,rank,unit,station_id,date_of_enlistment,duty_status,
        full_name,mother_name,date_of_birth,place_of_birth,contact_number,
        height_cm,weight_kg,blood_group,photo_path,
        region_of_origin,district_of_origin,town_village,
        guarantor_name,guarantor_address,guarantor_occupation,guarantor_relationship,
        guarantor_contact,guarantor_photo,
        doc1_type,doc1_path,doc2_type,doc2_path,created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (service_id, rank, unit, station['id'], date_of_enlistment, duty_status,
         full_name, mother_name, date_of_birth, place_of_birth, contact_number,
         height_cm or None, weight_kg or None, blood_group,
         photo['path'] if photo else None,
         region_of_origin, district_of_origin or None, town_village or None,
         guarantor_name, guarantor_address, guarantor_occupation or None,
         guarantor_relationship, guarantor_contact,
         guarantor_photo['path'] if guarantor_photo else None,
         doc1_type, doc1_path['path'], doc2_type, doc2_path['path'] if doc2_path else None,
         user['id'], utc_now_stamp()))
    row = c.execute('SELECT o.*, s.station_id AS station_code, s.name AS station_name '
                    'FROM officers o LEFT JOIN police_stations s ON s.id = o.station_id '
                    'WHERE o.service_id=?', (service_id,)).fetchone()
    return officer_view(row)


def register_station(c, user, data):
    """Validate and persist a police station. Returns the station view."""
    name = str(data.get('name') or '').strip()
    region = normalise_choice(data.get('region'), STATION_REGIONS)
    district = str(data.get('district') or '').strip()
    village = str(data.get('village') or '').strip()
    tier = normalise_choice(data.get('station_tier') or data.get('tier'), STATION_TIERS)
    phone = str(data.get('contact_phone') or data.get('phone') or '').strip()
    status = normalise_choice(data.get('operational_status') or data.get('status'), STATION_STATUSES) or 'Active'
    if not name:
        raise ValueError('Station name is required')
    if not tier:
        raise ValueError('Station tier is required and must be one of: ' + ', '.join(STATION_TIERS))
    if not region:
        raise ValueError('Station region is required and must be one of: ' + ', '.join(STATION_REGIONS))
    if not district:
        raise ValueError('Station district is required')
    allowed = STATION_DISTRICTS.get(region, ())
    if district not in allowed:
        raise ValueError(f'District must belong to {region}: ' + ', '.join(allowed))
    if not phone:
        raise ValueError('Contact phone is required')
    commander = resolve_officer_row(c, data.get('commander_id') or data.get('commander'))
    deputy = resolve_officer_row(c, data.get('deputy_id') or data.get('deputy'))
    if commander and commander['rank'] not in COMMANDER_RANKS:
        raise ValueError('Commander must hold rank Inspector or above')
    cap_raw = data.get('cell_capacity')
    cell_capacity = None
    if cap_raw not in (None, ''):
        try:
            cell_capacity = int(cap_raw)
        except (TypeError, ValueError):
            raise ValueError('Cell capacity must be an integer')
        if cell_capacity < 0:
            raise ValueError('Cell capacity must be zero or greater')
    code = new_station_code(c, region)
    station_id = new_station_id(c)
    c.execute('''INSERT INTO police_stations(station_id,name,code,region,district,village,
        station_tier,commander_id,deputy_id,contact_phone,cell_capacity,operational_status,notes,created_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (station_id, name, code, region, district, village or None,
         tier, commander['id'] if commander else None, deputy['id'] if deputy else None,
         phone, cell_capacity, status,
         str(data.get('notes') or '').strip() or None, user['id']))
    row = c.execute('SELECT * FROM police_stations WHERE station_id=?',
                    (station_id,)).fetchone()
    return station_view(row)


def register_crime(c, user, fields, files):
    station_code = str(fields.get('station_id') or '').strip()
    if not station_code:
        raise ValueError('station_id is required')
    station = c.execute('SELECT * FROM police_stations WHERE station_id=?', (station_code,)).fetchone()
    if not station:
        raise ValueError(f'Station "{station_code}" does not exist')
    officer = resolve_officer_row(c, fields.get('officer_id'))
    if not officer:
        raise ValueError('Desk officer_id is required and must refer to an existing officer')
    category = normalise_choice(fields.get('category'), CRIME_CATEGORIES)
    if not category:
        raise ValueError('Crime category is required and must be one of: ' + ', '.join(CRIME_CATEGORIES))
    incident_at = str(fields.get('incident_at') or fields.get('datetime') or '').strip()
    if not incident_at:
        raise ValueError('Incident date/time is required')
    location = str(fields.get('location_of_occurrence') or fields.get('location') or '').strip()
    if not location:
        raise ValueError('Location of occurrence is required')
    description = str(fields.get('description') or '').strip()
    if not description:
        raise ValueError('Incident description is required')
    severity = normalise_choice(fields.get('severity'), CRIME_SEVERITIES)
    if fields.get('severity') and not severity:
        raise ValueError('Severity must be one of: ' + ', '.join(CRIME_SEVERITIES))
    status = normalise_choice(fields.get('case_status') or fields.get('status'), CRIME_STATUSES) or 'Reported / Open'
    party = normalise_choice(fields.get('reporting_party_type'), REPORTING_PARTY_TYPES)
    if fields.get('reporting_party_type') and not party:
        raise ValueError('Reporting party type is invalid')
    gender = normalise_choice(fields.get('victim_gender'), VICTIM_GENDERS)
    anon = str(fields.get('victim_anonymous') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    age = None
    if str(fields.get('victim_age') or '').strip():
        try:
            age = int(fields.get('victim_age'))
        except (TypeError, ValueError):
            raise ValueError('Victim age must be an integer')
    e1_type = normalise_choice(fields.get('evidence1_type'), EVIDENCE_TYPES)
    e2_type = normalise_choice(fields.get('evidence2_type'), EVIDENCE_TYPES)
    e1 = save_upload_validated(files.get('evidence1') or files.get('evidence1_file'),
                               OFFICER_DOC_EXTS, 'Evidence slot 1')
    e2 = save_upload_validated(files.get('evidence2') or files.get('evidence2_file'),
                               OFFICER_DOC_EXTS, 'Evidence slot 2')
    if e1 and not e1_type:
        raise ValueError('Evidence slot 1 type is required when a file is attached')
    if e2 and not e2_type:
        raise ValueError('Evidence slot 2 type is required when a file is attached')
    file_number = new_crime_file_number(c, station['code'])
    c.execute('''INSERT INTO crime_incidents(file_number,station_id,officer_id,category,incident_at,
        location_of_occurrence,severity,description,case_status,reporting_party_type,
        victim_anonymous,victim_full_name,victim_contact,victim_national_id,victim_gender,victim_age,
        victim_address,statement,evidence1_type,evidence1_path,evidence2_type,evidence2_path,created_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (file_number, station['id'], officer['id'], category, incident_at,
         location,
         severity, description, status, party, 1 if anon else 0,
         str(fields.get('victim_full_name') or '').strip() or None,
         str(fields.get('victim_contact') or '').strip() or None,
         str(fields.get('victim_national_id') or '').strip() or None,
         gender, age, str(fields.get('victim_address') or '').strip() or None,
         str(fields.get('statement') or '').strip() or None,
         e1_type, e1['path'] if e1 else None, e2_type, e2['path'] if e2 else None, user['id']))
    row = c.execute('''SELECT ci.*, s.station_id AS station_code, s.code AS station_short_code,
        o.service_id AS officer_service_id, o.full_name AS officer_name
        FROM crime_incidents ci
        JOIN police_stations s ON s.id=ci.station_id
        JOIN officers o ON o.id=ci.officer_id
        WHERE ci.file_number=?''', (file_number,)).fetchone()
    return crime_view(row)


def normalise_conduct_type(value):
    """Resolve an action type / category to its canonical option.

    Accepts the two exact dropdown values (case-insensitive) plus the short
    aliases 'promotion' / 'disciplinary' (used by the category filter).
    Returns None when nothing matches."""
    v = str(value or '').strip()
    if not v:
        return None
    for o in CONDUCT_ACTION_TYPES:
        if v.lower() == o.lower():
            return o
    return CONDUCT_CATEGORY_ALIASES.get(v.lower())


def resolve_station_row(c, value):
    """Resolve a police station by numeric id, station code (ST-001) or name."""
    v = str(value or '').strip()
    if not v:
        return None
    if v.isdigit():
        return c.execute('SELECT * FROM police_stations WHERE id=?', (int(v),)).fetchone()
    row = c.execute('SELECT * FROM police_stations WHERE station_id=?', (v,)).fetchone()
    if not row:
        row = c.execute('SELECT * FROM police_stations WHERE LOWER(name)=LOWER(?)', (v,)).fetchone()
    return row


def rank_index(rank):
    """Position of a rank in the standard officer rank ladder (0 = lowest)."""
    try:
        return OFFICER_RANKS.index(rank)
    except ValueError:
        raise ValueError(f'Unknown rank "{rank}" — must be one of: ' + ', '.join(OFFICER_RANKS))


def validate_rank_transition(current_rank, proposed_rank, classification):
    """Enforce a valid rank transition for a rank-changing conduct action.

    Rank Advancement must propose a rank STRICTLY HIGHER than the officer
    currently holds; Rank Demotion must propose a rank STRICTLY LOWER.
    Raises ValueError with a human-readable message otherwise."""
    if classification not in CONDUCT_RANK_CLASSIFICATIONS:
        return
    if not proposed_rank:
        raise ValueError(f'{classification} requires a proposed rank '
                         '(select from the standard officer ranks)')
    cur, new = rank_index(current_rank), rank_index(proposed_rank)
    if classification == 'Rank Advancement' and new <= cur:
        raise ValueError(f'Rank Advancement must propose a HIGHER rank — '
                         f'the officer currently holds {current_rank}')
    if classification == 'Rank Demotion' and new >= cur:
        raise ValueError(f'Rank Demotion must propose a LOWER rank — '
                         f'the officer currently holds {current_rank}')


def conduct_view(row):
    """Public payload for one conduct action file (joins resolved)."""
    item = dict(row)
    try:
        item['documents'] = json.loads(item.get('documents') or '[]')
    except (TypeError, ValueError):
        item['documents'] = []
    item['rank_applied'] = bool(item.get('rank_applied'))
    item['is_rank_action'] = item.get('classification') in CONDUCT_RANK_CLASSIFICATIONS
    return item


def conduct_summary(c):
    """Status/category counts over the whole conduct register (for badges)."""
    def count(sql, args=()):
        return c.execute(sql, args).fetchone()[0]
    return {
        'total': count('SELECT COUNT(*) FROM officer_conduct_actions'),
        'promotion': count("SELECT COUNT(*) FROM officer_conduct_actions WHERE action_type=?", ('Promotion / Commendation',)),
        'disciplinary': count("SELECT COUNT(*) FROM officer_conduct_actions WHERE action_type=?", ('Disciplinary / Penalty',)),
        'pending': count("SELECT COUNT(*) FROM officer_conduct_actions WHERE status IN (?, ?)", CONDUCT_PENDING_STATUSES),
        'approved': count("SELECT COUNT(*) FROM officer_conduct_actions WHERE status=?", (CONDUCT_STATUS_APPROVED,)),
        'rejected': count("SELECT COUNT(*) FROM officer_conduct_actions WHERE status=?", (CONDUCT_STATUS_REJECTED,)),
    }


def submit_conduct_action(c, user, fields, files):
    """Validate and persist a conduct nomination / misconduct report.

    Called by POST /api/conduct/submit — the intake endpoint used by
    station commanders (and Registration Office staff entering a file on
    their behalf). Every file defaults to status 'Submitted to HR'.
    Raises ValueError on the first failing rule; the caller commits."""
    # ---- target officer (mandatory) ---------------------------------------
    officer = resolve_officer_row(c, fields.get('officer_id'))
    if not officer:
        raise ValueError('Target officer is required and must refer to an '
                         'existing officer (service ID or numeric id)')

    # ---- action type / category (mandatory) -------------------------------
    action_type = normalise_conduct_type(fields.get('action_type') or fields.get('category'))
    if not action_type:
        raise ValueError('Action category is required and must be one of: '
                         + ', '.join(CONDUCT_ACTION_TYPES))

    # ---- specific conduct classification (mandatory, must match type) -----
    classification = normalise_choice(fields.get('classification'),
                                      CONDUCT_CLASSIFICATIONS[action_type])
    if not classification:
        raise ValueError(f'Conduct classification is required and must be one of: '
                         + ', '.join(CONDUCT_CLASSIFICATIONS[action_type]))

    # ---- proposed rank adjustment -----------------------------------------
    proposed_rank = normalise_choice(fields.get('proposed_rank'), OFFICER_RANKS)
    if (fields.get('proposed_rank') or '').strip() and not proposed_rank:
        raise ValueError('Proposed rank must be one of: ' + ', '.join(OFFICER_RANKS))
    validate_rank_transition(officer['rank'], proposed_rank, classification)

    # ---- incident / case narrative (mandatory, detailed) ------------------
    narrative = re.sub(r'\s+', ' ', str(fields.get('narrative') or '')).strip()
    if not narrative:
        raise ValueError('Incident / case narrative is required — provide the '
                         'detailed justification, station report numbers or case references')
    if len(narrative) < CONDUCT_MIN_NARRATIVE_CHARS:
        raise ValueError(f'The incident / case narrative must be a detailed '
                         f'justification (at least {CONDUCT_MIN_NARRATIVE_CHARS} characters)')

    # ---- submitting station / commander (at least one required) -----------
    station = resolve_station_row(c, fields.get('station_id'))
    if (fields.get('station_id') or '').strip() and not station:
        raise ValueError(f'Submitting station "{fields.get("station_id")}" does not exist')
    reporting_officer = resolve_officer_row(c, fields.get('reporting_officer_id'))
    if (fields.get('reporting_officer_id') or '').strip() and not reporting_officer:
        raise ValueError('Submitting commander must refer to an existing officer '
                         '(service ID or numeric id)')
    if not station and not reporting_officer:
        raise ValueError('Submitting station or reporting commander is required — '
                         'the file must record its originating station or officer')

    # ---- submission date ---------------------------------------------------
    submitted_at = re.sub(r'\s+', ' ', str(fields.get('submitted_at') or '')).strip() \
        or utc_now_stamp()

    # ---- supporting report documents (PDF/JPG <= 5MB) ----------------------
    documents = []
    for key in sorted(files):
        if not key.startswith('document'):
            continue
        f = files[key]
        ext = file_ext(f['filename'])
        if ext not in CONDUCT_DOC_EXTS:
            raise ValueError(f'Supporting document must be a PDF or JPG '
                             f'(got {ext or "no extension"})')
        if len(f['content']) > CONDUCT_MAX_UPLOAD_BYTES:
            raise ValueError(f'Supporting document exceeds the '
                             f'{CONDUCT_MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit')
        documents.append(save_upload(f))

    action_id = new_conduct_action_id(c)
    c.execute('''INSERT INTO officer_conduct_actions(action_id,officer_id,action_type,
        classification,proposed_rank,narrative,station_id,reporting_officer_id,
        submitted_at,status,documents,created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (action_id, officer['id'], action_type, classification, proposed_rank,
         narrative, station['id'] if station else None,
         reporting_officer['id'] if reporting_officer else None,
         submitted_at, CONDUCT_STATUS_DEFAULT,
         json.dumps(documents) if documents else None,
         user['id'], utc_now_stamp()))
    row = c.execute(CONDUCT_SELECT + ' WHERE a.action_id=?', (action_id,)).fetchone()
    return conduct_view(row)


def review_conduct_action(c, user, action_row, data):
    """HR review step: move a conduct file through the approval pipeline.

    Restricted to Officer Registration Office / HR staff by the route
    handler. `data` carries:
      decision      — 'review' (-> Under HR Review), 'approve'
                      (-> Verified & Approved) or 'reject' (-> Rejected);
                      a full status name is also accepted.
      reviewer_officer_id — Registration Office staff processing the file
                            (officers(id) FK, validated when supplied)
      reviewer_notes     — free-text verification notes
    Returns the updated conduct view plus the rank-update outcome."""
    decision = str(data.get('decision') or data.get('status') or '').strip().lower()
    decision_map = {
        'review': CONDUCT_STATUS_REVIEWING,
        'under review': CONDUCT_STATUS_REVIEWING,
        'under hr review': CONDUCT_STATUS_REVIEWING,
        'approve': CONDUCT_STATUS_APPROVED,
        'approved': CONDUCT_STATUS_APPROVED,
        'verified': CONDUCT_STATUS_APPROVED,
        'verified & approved': CONDUCT_STATUS_APPROVED,
        'reject': CONDUCT_STATUS_REJECTED,
        'rejected': CONDUCT_STATUS_REJECTED,
    }
    new_status = decision_map.get(decision)
    if not new_status:
        raise ValueError("decision must be one of: approve, reject, review")
    if action_row['status'] in (CONDUCT_STATUS_APPROVED, CONDUCT_STATUS_REJECTED):
        raise ValueError(f'Action file {action_row["action_id"]} is already closed '
                         f'(status: {action_row["status"]}) — no further review is possible')

    reviewer = None
    if (data.get('reviewer_officer_id') or '').strip():
        reviewer = resolve_officer_row(c, data.get('reviewer_officer_id'))
        if not reviewer:
            raise ValueError('Reviewing HR officer must refer to an existing officer '
                             '(service ID or numeric id)')
    reviewer_notes = re.sub(r'\s+', ' ', str(data.get('reviewer_notes') or '')).strip() or None

    rank_update = None
    duty_update = None
    officer = c.execute('SELECT * FROM officers WHERE id=?', (action_row['officer_id'],)).fetchone()

    if new_status == CONDUCT_STATUS_APPROVED:
        classification = action_row['classification']
        # Re-validate the rank transition against the officer's CURRENT rank —
        # it may have changed since the file was submitted. Rank changes are
        # only ever applied through an approved HR action.
        if classification in CONDUCT_RANK_CLASSIFICATIONS:
            proposed = action_row['proposed_rank']
            validate_rank_transition(officer['rank'], proposed, classification)
            c.execute('UPDATE officers SET rank=? WHERE id=?', (proposed, officer['id']))
            c.execute('UPDATE officer_conduct_actions SET rank_applied=1 WHERE id=?',
                      (action_row['id'],))
            rank_update = {'from': officer['rank'], 'to': proposed}
        # Disciplinary penalties that adjust the duty status.
        duty_target = CONDUCT_DUTY_EFFECTS.get(classification)
        if duty_target and officer['duty_status'] != duty_target:
            c.execute('UPDATE officers SET duty_status=? WHERE id=?',
                      (duty_target, officer['id']))
            duty_update = {'from': officer['duty_status'], 'to': duty_target}
        # Immutable personnel record in the officer's service history.
        summary = f'{action_row["action_type"]} — {classification} verified & approved by HR'
        if rank_update:
            summary += f' · rank {rank_update["from"]} → {rank_update["to"]}'
        if duty_update:
            summary += f' · duty status {duty_update["from"]} → {duty_update["to"]}'
        c.execute('''INSERT INTO officer_service_history(officer_id,action_id,entry_type,
            summary,from_rank,to_rank,duty_status,recorded_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)''',
            (officer['id'], action_row['action_id'], classification, summary,
             rank_update['from'] if rank_update else None,
             rank_update['to'] if rank_update else None,
             duty_update['to'] if duty_update else officer['duty_status'],
             user['id'], utc_now_stamp()))

    c.execute('''UPDATE officer_conduct_actions SET status=?, reviewer_officer_id=?,
        reviewer_notes=?, reviewed_at=? WHERE id=?''',
        (new_status, reviewer['id'] if reviewer else action_row['reviewer_officer_id'],
         reviewer_notes or action_row['reviewer_notes'], utc_now_stamp(), action_row['id']))
    row = c.execute(CONDUCT_SELECT + ' WHERE a.action_id=?', (action_row['action_id'],)).fetchone()
    result = conduct_view(row)
    result['rank_update'] = rank_update
    result['duty_update'] = duty_update
    return result


def find_by_id(c, data):
    """Tier 1: exact National ID or Passport match (case/space insensitive)."""
    national_id = norm(data.get('national_id'))
    passport_id = norm(data.get('passport_id'))
    if national_id:
        row = c.execute("SELECT * FROM persons WHERE LOWER(TRIM(COALESCE(national_id,''))) = ?",
                        (national_id,)).fetchone()
        if row: return rowdict(row), 1
    if passport_id:
        row = c.execute("SELECT * FROM persons WHERE LOWER(TRIM(COALESCE(passport_id,''))) = ?",
                        (passport_id,)).fetchone()
        if row: return rowdict(row), 1
    return None, 0

def name_parts_of(row):
    """Normalised name components of a stored person (4-part columns or legacy full_name)."""
    parts = [str(row.get(k) or '').strip() for k in NAME_PART_FIELDS]
    if any(parts):
        return [norm(p) for p in parts if p]
    return split_parts(row.get('full_name') or '')

def person_suggestions(c, data, limit=8):
    """Flexible, case-insensitive matching for the live dropdown.

    Scores each central person against the entered name components (2, 3 or 4
    parts must all be present in the stored name) and partial/exact National ID
    or Passport values; returns the best matches ordered by score.
    """
    entered = [norm(data.get(k)) for k in NAME_PART_FIELDS]
    entered = [p for p in entered if p]
    nat = norm(data.get('national_id'))
    pas = norm(data.get('passport_id'))
    dob = norm(data.get('date_of_birth'))
    mother = norm(data.get('mother_name'))
    scored = []
    for r in c.execute('SELECT * FROM persons'):
        row = rowdict(r)
        parts = name_parts_of(row)
        partset = set(parts)
        score = 0
        if nat:
            sid = norm(row.get('national_id'))
            if sid == nat:
                score += 60
            elif len(nat) >= 2 and sid.startswith(nat):
                score += 25
        if pas:
            spid = norm(row.get('passport_id'))
            if spid == pas:
                score += 60
            elif len(pas) >= 2 and spid.startswith(pas):
                score += 25
        if len(entered) >= 2 and all(p in partset for p in entered):
            score += len(entered) * 10
            if parts[:len(entered)] == entered:
                score += 8          # entered components are a prefix, in order
            if dob and norm(row.get('date_of_birth')) == dob:
                score += 12
            if mother and norm(row.get('mother_name')) == mother:
                score += 8
        if score >= 18:
            copied = dict(row)
            copied['suggestion_score'] = score
            scored.append(copied)
    scored.sort(key=lambda x: (-x['suggestion_score'], x['person_id']))
    out, seen = [], set()
    for row in scored:
        if row['person_id'] in seen:
            continue
        seen.add(row['person_id'])
        out.append(row)
        if len(out) >= limit:
            break
    return out

def resolve_person(c, data):
    """Universal matching engine.

    Returns (person_row_dict | None, tier, reason, suggestions).
    Tier 1 = exact ID/passport, Tier 2 = exact 4-part name + DOB,
    Tier 3 = fuzzy 3-part name + mother's name, Tier 4 = partial name match.
    """
    rows = [rowdict(r) for r in c.execute('SELECT * FROM persons')]
    row, tier = find_by_id(c, data)
    if row:
        return row, 1, 'Exact National ID / Passport match', []

    parts = [norm(data.get(k)) for k in NAME_PART_FIELDS]
    dob = norm(data.get('date_of_birth'))
    if all(parts) and dob:
        target = ' '.join(parts)
        for r in rows:
            if ' '.join(split_parts(r.get('full_name'))) == target and norm(r.get('date_of_birth')) == dob:
                return r, 2, 'Exact 4-part name + date of birth match', []

    mother = norm(data.get('mother_name'))
    entered = [p for p in parts if p]
    if mother and len(entered) >= 3:
        candidates = []
        for r in rows:
            stored = set(split_parts(r.get('full_name')))
            if norm(r.get('mother_name')) == mother and sum(1 for p in entered if p in stored) >= 3:
                candidates.append(r)
        if candidates:
            reason = ('Fuzzy 3-part name + mother\u2019s name match \u2014 '
                      f'{len(candidates)} candidate(s); officer confirmation required')
            return candidates[0], 3, reason, candidates

    suggestions = person_suggestions(c, data)
    strong = [s for s in suggestions if s['suggestion_score'] >= 30]
    if len(strong) == 1:
        matched = strong[0]
        n = len(entered) if entered else 0
        reason = (f'Partial name match ({n}-part) \u2014 matching Central Person found; '
                  'select it to auto-fill and link')
        return matched, 4, reason, suggestions
    if suggestions:
        return None, 0, 'Possible matches found \u2014 select a record from the matching list', suggestions
    return None, 0, 'No exact central record found \u2014 a new Central Person record will be created on save.', []

def resolve_identity(c, data):
    """JSON-safe response for /api/persons/resolve."""
    row, tier, reason, suggestions = resolve_person(c, data)
    for s in suggestions:
        s.pop('suggestion_score', None)
    return {
        'matched': row is not None,
        'tier': tier,
        'tier_label': TIER_LABELS.get(tier, 'No match'),
        'reason': reason,
        'person': row,
        'candidates': [dict(x) for x in suggestions],
        'suggestions': [dict(x) for x in suggestions],
        'auto_merge': tier in (1, 2),
    }

def create_person(c, data, photo_path=None, allow_no_id=False):
    """Create a new central person record. Returns (row, True)."""
    full_name = build_full_name(data)
    if not full_name:
        raise ValueError('Full name is required')
    national_id = (data.get('national_id') or '').strip().upper() or None
    passport_id = (data.get('passport_id') or '').strip().upper() or None
    if not national_id and not passport_id and not allow_no_id:
        raise ValueError('National ID or Passport ID is required')
    a, b, d, e = raw_parts(full_name)
    pid = new_person_id(c)
    c.execute('''INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,fourth_name,
        national_id,date_of_birth,phone,mother_name,place_of_birth,residence,occupation,
        passport_id,photo_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (pid, full_name, a, b, d, e, national_id,
               data.get('date_of_birth',''), data.get('phone',''),
               data.get('mother_name',''), data.get('place_of_birth',''),
               data.get('residence',''), data.get('occupation',''),
               passport_id, photo_path))
    return rowdict(c.execute('SELECT * FROM persons WHERE person_id=?', (pid,)).fetchone()), True

def enrich_person(c, data, person, photo_path=None):
    """Fill any empty/null central-person fields from incoming unit request data.

    Never overwrites existing non-null values. This lets an officer complete
    missing profile details (mother's name, phone, occupation, address,
    passport, photo, etc.) while recording a unit event, and enriches the
    linked Central Person record in SQLite. Returns (updated_row, changed).
    """
    updates, params = [], []
    for f in PERSON_FIELDS:
        if f == 'photo_path':
            incoming = photo_path or ''
        else:
            raw = data.get(f)
            incoming = str(raw or '').strip() if raw is not None else ''
        if f in ('national_id', 'passport_id'):
            incoming = incoming.upper()
        stored = str(person.get(f) or '').strip()
        if incoming and not stored:
            updates.append(f'{f}=?'); params.append(incoming)
    if updates:
        updates.append('updated_at=CURRENT_TIMESTAMP')
        params.append(person['id'])
        c.execute(f"UPDATE persons SET {', '.join(updates)} WHERE id=?", params)
        return rowdict(c.execute('SELECT * FROM persons WHERE id=?', (person['id'],)).fetchone()), True
    return person, False

def upsert_person(c, data, photo_path=None, allow_no_id=False):
    """Smart identity resolution + merge.

    Tier 1 (exact ID/passport) and Tier 2 (exact 4-part name + DOB) records are
    merged automatically, enriching any empty fields without overwriting
    existing non-null data; otherwise a new Central Person is created.
    Returns (row, created).
    """
    row, tier = find_by_id(c, data)
    if not row:
        row, tier, _, _ = resolve_person(c, data)
    if row and tier in (1, 2):
        row, _ = enrich_person(c, data, row, photo_path)
        return row, False
    return create_person(c, data, photo_path, allow_no_id)

def ensure_person(c, data, photo_path=None, allow_no_id=False):
    """Resolve an existing person_id or auto-create the Central Person record
    from the identity fields carried by a unit request. When a unit record links
    to an existing Central Person ID, any non-empty incoming values for fields
    that are still null/empty are used to enrich the profile (never overwriting
    existing non-null data). Returns (row, created)."""
    pid = norm(data.get('person_id'))
    if pid:
        row = rowdict(c.execute('SELECT * FROM persons WHERE person_id=?', (pid,)).fetchone())
        if row:
            row, _ = enrich_person(c, data, row, photo_path)
            return row, False
    identity_present = any(str(data.get(k) or '').strip() for k in
                           ('first_name','second_name','third_name','fourth_name','full_name',
                            'national_id','passport_id','mother_name'))
    if identity_present:
        return upsert_person(c, data, photo_path, allow_no_id)
    raise ValueError('A person_id or person identity fields are required')

def identity_result(c, data, person):
    """Small match summary returned with unit record POST responses."""
    row, tier, reason, _ = resolve_person(c, data)
    matched = row is not None and row['person_id'] == person['person_id']
    return {'person_id': person['person_id'], 'matched': matched,
            'tier': tier if matched else 0, 'reason': reason}


def promotion_row(c, nomination_id):
    return c.execute(PROMOTION_SELECT + ' WHERE pr.nomination_id=?', (nomination_id,)).fetchone()


def discipline_row(c, action_id):
    return c.execute(DISCIPLINE_SELECT + ' WHERE da.action_id=?', (action_id,)).fetchone()


def promotion_rows(c):
    return c.execute(PROMOTION_SELECT + ' ORDER BY pr.id DESC').fetchall()


def discipline_rows(c):
    return c.execute(DISCIPLINE_SELECT + ' ORDER BY da.id DESC').fetchall()


def promotion_view(r):
    return {
        'nomination_id': r['nomination_id'],
        'service_id': _val(r, 'service_id'),
        'full_name': _val(r, 'full_name'),
        'officer_rank': _val(r, 'officer_rank'),
        'current_rank': r['current_rank'],
        'proposed_rank': r['proposed_rank'],
        'unit': _val(r, 'unit'),
        'duty_status': _val(r, 'duty_status'),
        'station_name': _val(r, 'station_name'),
        'station_code': _val(r, 'station_code'),
        'reason': _val(r, 'reason'),
        'effective_date': _val(r, 'effective_date'),
        'verification_status': r['verification_status'],
        'nominated_by': _val(r, 'nominated_by_name'),
        'verified_by': _val(r, 'verified_by_name'),
        'verified_by_id': _val(r, 'verified_by'),
        'verified_at': _val(r, 'verified_at'),
        'created_at': _val(r, 'created_at'),
        # The green badge only counts nominations for officers still in
        # active service that a commander has not verified yet.
        'awaiting_verification': (r['verification_status'] == PROMOTION_PENDING_STATUS
                                  and _val(r, 'duty_status') == 'Active'),
    }


def discipline_view(r):
    status = r['status']
    return {
        'action_id': r['action_id'],
        'service_id': _val(r, 'service_id'),
        'full_name': _val(r, 'full_name'),
        'officer_rank': _val(r, 'officer_rank'),
        'unit': _val(r, 'unit'),
        'duty_status': _val(r, 'duty_status'),
        'station_name': _val(r, 'station_name'),
        'station_code': _val(r, 'station_code'),
        'action_type': r['action_type'],
        'severity': _val(r, 'severity'),
        'status': status,
        'from_rank': _val(r, 'from_rank'),
        'to_rank': _val(r, 'to_rank'),
        'suspension_start': _val(r, 'suspension_start'),
        'suspension_end': _val(r, 'suspension_end'),
        'incident_summary': _val(r, 'incident_summary'),
        'reported_by': _val(r, 'reported_by_name'),
        'created_at': _val(r, 'created_at'),
        'open': status in DISCIPLINE_OPEN_STATUSES,
    }


def register_promotion(c, user, data):
    """Create a promotion nomination awaiting commander verification."""
    officer = resolve_officer_row(c, data.get('officer_id') or data.get('service_id'))
    if not officer:
        raise ValueError('Officer does not exist')
    current = normalise_choice(data.get('current_rank'), OFFICER_RANKS) or officer['rank']
    proposed = normalise_choice(data.get('proposed_rank'), OFFICER_RANKS)
    if not proposed:
        raise ValueError('Proposed rank is required and must be one of: '
                         + ', '.join(OFFICER_RANKS))
    if proposed == current:
        raise ValueError('Proposed rank must differ from the current rank')
    status = normalise_choice(data.get('verification_status'), PROMOTION_STATUSES) \
        or PROMOTION_PENDING_STATUS
    nid = new_promotion_id(c)
    c.execute('''INSERT INTO officer_promotions(nomination_id, officer_id, current_rank,
            proposed_rank, reason, effective_date, verification_status, nominated_by)
        VALUES(?,?,?,?,?,?,?,?)''',
              (nid, officer['id'], current, proposed,
               str(data.get('reason') or '').strip() or None,
               str(data.get('effective_date') or '').strip() or None,
               status, user['id']))
    return promotion_view(promotion_row(c, nid))


def verify_promotion(c, user, nomination_id, data):
    """Commander verification: Accepted/Verified or Rejected."""
    row = c.execute('SELECT * FROM officer_promotions WHERE nomination_id=?',
                    (nomination_id,)).fetchone()
    if not row:
        raise LookupError('Promotion nomination not found')
    status = normalise_choice(data.get('verification_status') or data.get('status'),
                              PROMOTION_STATUSES)
    if not status:
        raise ValueError('verification_status must be one of: ' + ', '.join(PROMOTION_STATUSES))
    stamp = utc_now_stamp() if status != PROMOTION_PENDING_STATUS else None
    c.execute('UPDATE officer_promotions SET verification_status=?, verified_by=?, verified_at=? '
              'WHERE nomination_id=?',
              (status, user['id'] if status != PROMOTION_PENDING_STATUS else None,
               stamp, nomination_id))
    return promotion_view(promotion_row(c, nomination_id))


def register_discipline(c, user, data):
    """Record a disciplinary action (misconduct / suspension / demotion)."""
    officer = resolve_officer_row(c, data.get('officer_id') or data.get('service_id'))
    if not officer:
        raise ValueError('Officer does not exist')
    action_type = normalise_choice(data.get('action_type'), DISCIPLINE_ACTION_TYPES)
    if not action_type:
        raise ValueError('Action type is required and must be one of: '
                         + ', '.join(DISCIPLINE_ACTION_TYPES))
    status = normalise_choice(data.get('status'), DISCIPLINE_STATUSES) or 'Pending'
    severity = normalise_choice(data.get('severity'), CRIME_SEVERITIES)
    if data.get('severity') and not severity:
        raise ValueError('Severity is invalid')
    from_rank = to_rank = None
    if action_type == 'Demotion':
        from_rank = normalise_choice(data.get('from_rank'), OFFICER_RANKS) or officer['rank']
        to_rank = normalise_choice(data.get('to_rank'), OFFICER_RANKS)
        if not to_rank:
            raise ValueError('Demotions require the rank being demoted to (to_rank)')
        if OFFICER_RANKS.index(to_rank) >= OFFICER_RANKS.index(from_rank):
            raise ValueError('to_rank must be junior to from_rank for a demotion')
    aid = new_discipline_id(c)
    c.execute('''INSERT INTO officer_discipline(action_id, officer_id, action_type, severity,
            status, from_rank, to_rank, suspension_start, suspension_end,
            incident_summary, reported_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (aid, officer['id'], action_type, severity, status, from_rank, to_rank,
               str(data.get('suspension_start') or '').strip() or None,
               str(data.get('suspension_end') or '').strip() or None,
               str(data.get('incident_summary') or data.get('notes') or '').strip() or None,
               user['id']))
    return discipline_view(discipline_row(c, aid))


def update_discipline(c, user, action_id, data):
    """HR Directorate update of an existing disciplinary action.

    Status changes carry the operational side effects the register expects:
    confirming a **Demotion** writes the junior rank onto the officer,
    confirming a **Suspension** takes the officer off duty, and closing an
    action returns an officer with no other open action to Active duty. The
    analytics bundle (rank distribution, suspended officers, red badge) is
    derived from the same rows, so the strips follow immediately.
    """
    row = c.execute('SELECT * FROM officer_discipline WHERE action_id=?',
                    (action_id,)).fetchone()
    if not row:
        raise LookupError('Disciplinary action not found')
    status = normalise_choice(data.get('status'), DISCIPLINE_STATUSES)
    if data.get('status') and not status:
        raise ValueError('status must be one of: ' + ', '.join(DISCIPLINE_STATUSES))
    severity = normalise_choice(data.get('severity'), CRIME_SEVERITIES)
    if data.get('severity') and not severity:
        raise ValueError('Severity is invalid')
    updates, params = [], []
    if severity:
        updates.append('severity=?'); params.append(severity)
    if status:
        updates.append('status=?'); params.append(status)
    for f in ('suspension_start', 'suspension_end'):
        if f in data:
            updates.append(f + '=?')
            params.append(str(data.get(f) or '').strip() or None)
    if 'incident_summary' in data or 'notes' in data:
        updates.append('incident_summary=?')
        params.append(str(data.get('incident_summary') or data.get('notes') or '').strip() or None)
    if 'to_rank' in data:
        to_rank = normalise_choice(data.get('to_rank'), OFFICER_RANKS)
        if not to_rank:
            raise ValueError('to_rank must be one of: ' + ', '.join(OFFICER_RANKS))
        updates.append('to_rank=?'); params.append(to_rank)
    if updates:
        params.append(action_id)
        c.execute('UPDATE officer_discipline SET ' + ', '.join(updates) + ' WHERE action_id=?', params)

    action = discipline_view(discipline_row(c, action_id))
    if status:
        officer_id = row['officer_id']
        if action['action_type'] == 'Demotion' and action['status'] == 'Confirmed' and action['to_rank']:
            c.execute('UPDATE officers SET rank=? WHERE id=?', (action['to_rank'], officer_id))
        elif action['action_type'] == 'Suspension' and action['status'] == 'Confirmed':
            c.execute("UPDATE officers SET duty_status='Suspended' WHERE id=? "
                      "AND duty_status NOT IN ('Terminated','Retired')", (officer_id,))
        elif action['status'] == 'Closed':
            placeholders = ','.join('?' * len(DISCIPLINE_OPEN_STATUSES))
            sql = ('SELECT COUNT(*) FROM officer_discipline WHERE officer_id=? '
                   'AND action_id<>? AND status IN (' + placeholders + ')')
            still_open = c.execute(sql, (officer_id, action_id) + tuple(DISCIPLINE_OPEN_STATUSES)).fetchone()[0]
            if not still_open:
                c.execute("UPDATE officers SET duty_status='Active' WHERE id=? "
                          "AND duty_status='Suspended'", (officer_id,))
        action = discipline_view(discipline_row(c, action_id))
    return action
