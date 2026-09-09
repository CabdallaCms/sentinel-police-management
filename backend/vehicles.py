"""Vehicle / car registration helpers for Sentinel."""
import datetime
import re

VEHICLE_CATEGORIES = ('Police Fleet', 'Civilian / Commercial')
VEHICLE_BODY_TYPES = ('Pickup 4x4', 'SUV', 'Sedan', 'Armored Patrol', 'Truck', 'Patrol Motorcycle')
VEHICLE_OP_STATUSES = ('In Service', 'Maintenance', 'Out of Service', 'Decommissioned')
VEHICLE_ALERTS = ('Clean / Normal', 'Stolen', 'Wanted in Crime', 'Impounded', 'Unregistered / Suspicious')

VEHICLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles(
  id INTEGER PRIMARY KEY, vehicle_id TEXT UNIQUE NOT NULL,
  category TEXT NOT NULL, plate_number TEXT UNIQUE NOT NULL,
  vin TEXT UNIQUE NOT NULL, engine_number TEXT NOT NULL,
  make_model TEXT NOT NULL, year_of_manufacture INTEGER,
  body_type TEXT, primary_color TEXT, secondary_color TEXT,
  station_id INTEGER REFERENCES police_stations(id),
  officer_id INTEGER REFERENCES officers(id),
  operational_status TEXT,
  owner_full_name TEXT, owner_phone TEXT, owner_national_id TEXT, owner_address TEXT,
  security_alert TEXT NOT NULL DEFAULT 'Clean / Normal',
  alert_reason TEXT, registration_expiry TEXT, photo_path TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

VIN_RE = re.compile(r'[A-HJ-NPR-Z0-9]{17}')


def new_vehicle_id(c):
    year = datetime.datetime.now(datetime.timezone.utc).year
    prefix = 'VEH-%s-' % year
    n = 1
    for row in c.execute('SELECT vehicle_id FROM vehicles WHERE vehicle_id LIKE ?', (prefix + '%',)):
        try:
            n = max(n, int(str(row['vehicle_id']).rsplit('-', 1)[1]) + 1)
        except (ValueError, IndexError):
            pass
    return '%s%04d' % (prefix, n)


def vehicle_sql_row(c, vid):
    return c.execute(
        "SELECT v.*, s.station_id AS station_code, s.name AS station_name, "
        "o.service_id AS officer_service_id, o.full_name AS officer_name, "
        "s.region AS station_region, s.district AS station_district, s.village AS station_village "
        "FROM vehicles v "
        "LEFT JOIN police_stations s ON s.id=v.station_id "
        "LEFT JOIN officers o ON o.id=v.officer_id "
        "WHERE v.vehicle_id=?",
        (vid,)).fetchone()


def register_vehicle(c, user, fields, files, helpers):
    """helpers: dict with normalise_choice, resolve_officer_row, save_upload_validated, OFFICER_IMAGE_EXTS."""
    normalise_choice = helpers['normalise_choice']
    resolve_officer_row = helpers['resolve_officer_row']
    save_upload_validated = helpers['save_upload_validated']
    image_exts = helpers['OFFICER_IMAGE_EXTS']
    category = normalise_choice(fields.get('category'), VEHICLE_CATEGORIES)
    if not category:
        raise ValueError('Category is required and must be one of: ' + ', '.join(VEHICLE_CATEGORIES))
    plate = str(fields.get('plate_number') or fields.get('plate') or '').strip().upper()
    if not plate:
        raise ValueError('License plate number is required')
    vin = str(fields.get('vin') or '').strip().upper().replace(' ', '')
    if len(vin) != 17 or not VIN_RE.fullmatch(vin):
        raise ValueError('VIN / chassis number must be exactly 17 characters (no I, O or Q)')
    engine = str(fields.get('engine_number') or '').strip()
    if not engine:
        raise ValueError('Engine number is required')
    make_model = str(fields.get('make_model') or '').strip()
    if not make_model:
        raise ValueError('Make & model is required')
    year = None
    yraw = str(fields.get('year_of_manufacture') or fields.get('year') or '').strip()
    if yraw:
        if not re.fullmatch(r'\d{4}', yraw):
            raise ValueError('Year of manufacture must be YYYY')
        year = int(yraw)
    body = normalise_choice(fields.get('body_type'), VEHICLE_BODY_TYPES)
    if fields.get('body_type') and not body:
        raise ValueError('Body type is invalid')
    primary = str(fields.get('primary_color') or '').strip() or None
    secondary = str(fields.get('secondary_color') or '').strip() or None
    station = officer = op_status = None
    owner_name = owner_phone = owner_nid = owner_addr = None
    if category == 'Police Fleet':
        scode = str(fields.get('station_id') or '').strip()
        if not scode:
            raise ValueError('Assigned station is required for police fleet vehicles')
        station = c.execute('SELECT * FROM police_stations WHERE station_id=?', (scode,)).fetchone()
        if not station:
            raise ValueError('Station "%s" does not exist' % scode)
        officer = resolve_officer_row(c, fields.get('officer_id'))
        if str(fields.get('officer_id') or '').strip() and not officer:
            raise ValueError('Assigned officer does not exist')
        op_status = normalise_choice(fields.get('operational_status'), VEHICLE_OP_STATUSES) or 'In Service'
    else:
        owner_name = str(fields.get('owner_full_name') or '').strip()
        owner_phone = str(fields.get('owner_phone') or '').strip()
        owner_nid = str(fields.get('owner_national_id') or '').strip()
        owner_addr = str(fields.get('owner_address') or '').strip() or None
        if not owner_name:
            raise ValueError('Owner full name is required for civilian vehicles')
        if not owner_phone:
            raise ValueError('Owner phone number is required for civilian vehicles')
        if not owner_nid:
            raise ValueError('Owner national ID / passport is required for civilian vehicles')
    alert = normalise_choice(fields.get('security_alert'), VEHICLE_ALERTS) or 'Clean / Normal'
    reason = str(fields.get('alert_reason') or '').strip() or None
    if alert != 'Clean / Normal' and not reason:
        raise ValueError('Alert reason is required when security alert is not Clean / Normal')
    expiry = str(fields.get('registration_expiry') or '').strip() or None
    photo = save_upload_validated(files.get('photo') or files.get('vehicle_photo'),
                                  image_exts, 'Vehicle picture')
    if c.execute('SELECT 1 FROM vehicles WHERE plate_number=?', (plate,)).fetchone():
        raise ValueError('A vehicle with this plate number already exists')
    if c.execute('SELECT 1 FROM vehicles WHERE vin=?', (vin,)).fetchone():
        raise ValueError('A vehicle with this VIN already exists')
    vid = new_vehicle_id(c)
    c.execute(
        "INSERT INTO vehicles(vehicle_id,category,plate_number,vin,engine_number,make_model,"
        "year_of_manufacture,body_type,primary_color,secondary_color,station_id,officer_id,operational_status,"
        "owner_full_name,owner_phone,owner_national_id,owner_address,security_alert,alert_reason,"
        "registration_expiry,photo_path,created_by) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (vid, category, plate, vin, engine, make_model, year, body, primary, secondary,
         station['id'] if station else None, officer['id'] if officer else None, op_status,
         owner_name, owner_phone, owner_nid, owner_addr, alert, reason, expiry,
         photo['path'] if photo else None, user['id']))
    return dict(vehicle_sql_row(c, vid))


def update_vehicle_alert(c, user, vehicle_id, data, helpers):
    normalise_choice = helpers['normalise_choice']
    row = c.execute('SELECT * FROM vehicles WHERE vehicle_id=?', (vehicle_id,)).fetchone()
    if not row:
        raise LookupError('Vehicle not found')
    alert = normalise_choice(data.get('security_alert') or data.get('alert'), VEHICLE_ALERTS)
    if not alert:
        raise ValueError('Security alert is required and must be one of: ' + ', '.join(VEHICLE_ALERTS))
    reason = str(data.get('alert_reason') or data.get('reason') or '').strip() or None
    if alert != 'Clean / Normal' and not reason:
        raise ValueError('Alert reason is required when security alert is not Clean / Normal')
    c.execute('UPDATE vehicles SET security_alert=?, alert_reason=? WHERE vehicle_id=?',
              (alert, reason, vehicle_id))
    return dict(vehicle_sql_row(c, vehicle_id))


def list_vehicles(c, q=''):
    rows = c.execute(
        "SELECT v.*, s.station_id AS station_code, s.name AS station_name, "
        "o.service_id AS officer_service_id, o.full_name AS officer_name, "
        "s.region AS station_region, s.district AS station_district, s.village AS station_village "
        "FROM vehicles v "
        "LEFT JOIN police_stations s ON s.id=v.station_id "
        "LEFT JOIN officers o ON o.id=v.officer_id "
        "ORDER BY v.id DESC").fetchall()
    items = [dict(r) for r in rows]
    q = (q or '').strip().upper()
    if q:
        items = [it for it in items if q in (it.get('plate_number') or '').upper()
                 or q in (it.get('vin') or '').upper()
                 or q in (it.get('vehicle_id') or '').upper()
                 or q in (it.get('make_model') or '').upper()]
    return items
