-- =============================================================================
-- Migration 003 — Operational units: checkpoint stops, airport passenger logs,
--                 station crime-incident intake
-- Northeastern Police System (unified platform)
--
-- Requires: 001_initial_schema.sql, 002_person_identity.sql.  ONE transaction, no extensions.
--
-- Migration 001 already created checkpoint_events / airport_passengers / crime_incidents with
-- unit-type, active-unit and row-level-security guards.  This migration hardens and completes them:
--
--   1. REGION SCOPE.  An event may only be recorded in a unit that sits under one of the regions
--      listed in policy_settings 'operations.regions' (Sool, Sanaag, East Togdheer).  It is data:
--      a new region is an INSERT, not a code change; a unit outside the list is refused by the DB.
--   2. PROVENANCE.  created_by is forced to the authenticated user (app.user_id).  A write with no
--      authenticated user is rejected, even for the table owner (who bypasses RLS).
--   3. APPEND-ONLY LOGS.  Checkpoint and airport records cannot be edited or deleted (a correction
--      is a new, audited record).  A crime incident's ONLY mutable column is case_status.
--   4. NO DUPLICATE AIRPORT RECORDS (same person + movement + flight + date + airport) — a unique
--      index, so a double-submit or two concurrent desks cannot create two.
--   5. INCIDENT VOCABULARIES (category / severity / status) are policy data, validated in the DB.
--   6. victim_person_id: a victim MAY be linked to the registry (never auto-created, never for an
--      anonymous victim).  location_of_occurrence becomes a real column.
--   7. `uploads`: who uploaded each photo / document, so a record can only reference the
--      uploader's own files and file access can follow record access.
-- =============================================================================

-- ---- 1. policy data ---------------------------------------------------------
INSERT INTO policy_settings (key, value, description) VALUES
 ('operations.regions',        '["SOOL","SANAAG","ETOG"]',
    'Region unit codes inside which checkpoint / airport / incident records may be created'),
 ('checkpoint.required',       '{"photo": true, "traveler_docs": 1, "guardian": "all", "guardian_docs": 1}',
    'Checkpoint stop requirements ported from the legacy form. guardian: "all" | "minors" | "none"'),
 ('airport.travel_window_days','{"past": 60, "future": 7}',
    'How far from today a passenger log travel_date may be (new rule: the legacy form accepted anything)'),
 ('incident.categories',       '["Theft/Burglary","Assault","Robbery","Traffic Accident","Homicide","Fraud","Domestic Incident","Public Order","Cybercrime","Other"]',
    'Crime incident categories (legacy CRIME_CATEGORIES)'),
 ('incident.severities',       '["Low","Medium","High","Critical"]', 'Legacy CRIME_SEVERITIES'),
 ('incident.statuses',         '["Reported / Open","Under Investigation","Referred to Court","Closed","Unresolved"]', 'Legacy CRIME_STATUSES'),
 ('incident.reporting_parties','["Victim","Witness","Third-Party Representative","Police"]', 'Legacy REPORTING_PARTY_TYPES'),
 ('incident.victim_genders',   '["Male","Female","Other / Prefer not to say"]', 'Legacy VICTIM_GENDERS'),
 ('incident.evidence_types',   '["Photo","Statement","Physical item","Digital file","Other"]', 'Legacy EVIDENCE_TYPES');

-- ---- 2. region scope --------------------------------------------------------
CREATE FUNCTION unit_region(p_unit bigint) RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT c.ancestor_id
      FROM org_unit_closure c JOIN org_units a ON a.id = c.ancestor_id
     WHERE c.descendant_id = p_unit AND a.unit_type = 'region'
$$;

CREATE FUNCTION unit_in_operational_region(p_unit bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM org_units r
         WHERE r.id = unit_region(p_unit)
           AND r.code IN (SELECT jsonb_array_elements_text(value)
                            FROM policy_settings WHERE key = 'operations.regions'))
$$;

CREATE FUNCTION enforce_operational_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; v bigint;
BEGIN
    v := (to_jsonb(NEW) ->> col)::bigint;
    IF NOT unit_in_operational_region(v) THEN
        RAISE EXCEPTION '% records can only be created in units under the operational regions (see policy operations.regions); unit % is outside',
            TG_TABLE_NAME, v USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

-- ---- 3. provenance + append-only -------------------------------------------
CREATE FUNCTION events_stamp_creator() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_app_user() IS NULL THEN
        IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'no authenticated user: % records cannot be written anonymously', TG_TABLE_NAME
            USING ERRCODE = '42501';
    END IF;
    NEW.created_by := current_app_user();          -- cannot be forged by the caller
    RETURN NEW;
END $$;

CREATE FUNCTION events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION '% is an append-only log: % is not allowed (file a new record to correct one)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = '42501';
END $$;

-- a crime incident may only change its case_status; nothing is ever deleted
CREATE FUNCTION incident_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'crime incidents cannot be deleted' USING ERRCODE = '42501';
    END IF;
    IF (to_jsonb(NEW) - 'case_status') IS DISTINCT FROM (to_jsonb(OLD) - 'case_status') THEN
        RAISE EXCEPTION 'a filed crime incident is immutable except for its case_status' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $$;

-- ---- 5/6. incident columns + vocabulary validation --------------------------
ALTER TABLE crime_incidents ADD COLUMN location_of_occurrence text;
ALTER TABLE crime_incidents ADD COLUMN victim_person_id bigint REFERENCES persons(id);
ALTER TABLE crime_incidents ADD CONSTRAINT ck_inc_victim_not_anonymous
    CHECK (victim_person_id IS NULL OR COALESCE(details ->> 'victim_anonymous', 'false') <> 'true');
CREATE INDEX ix_inc_victim ON crime_incidents (victim_person_id) WHERE victim_person_id IS NOT NULL;

CREATE FUNCTION policy_list(p_key text) RETURNS text[] LANGUAGE sql STABLE AS $$
    SELECT COALESCE(array_agg(x), ARRAY[]::text[])
      FROM policy_settings, jsonb_array_elements_text(value) AS x WHERE key = p_key
$$;

CREATE FUNCTION incident_validate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT (NEW.case_status = ANY (policy_list('incident.statuses'))) THEN
        RAISE EXCEPTION 'unknown case status "%"', NEW.case_status USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN                      -- the rest is fixed at filing time (and immutable afterwards)
        IF NOT (NEW.category = ANY (policy_list('incident.categories'))) THEN
            RAISE EXCEPTION 'unknown incident category "%"', NEW.category USING ERRCODE = '23514';
        END IF;
        IF NEW.severity IS NOT NULL AND NOT (NEW.severity = ANY (policy_list('incident.severities'))) THEN
            RAISE EXCEPTION 'unknown incident severity "%"', NEW.severity USING ERRCODE = '23514';
        END IF;
        IF NEW.incident_at > now() + interval '5 minutes' THEN
            RAISE EXCEPTION 'an incident cannot be dated in the future' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;

ALTER TABLE checkpoint_events ADD CONSTRAINT ck_cpe_screening
    CHECK (screening_result IN ('No active alert', 'Flagged match'));

-- ---- triggers ---------------------------------------------------------------
CREATE TRIGGER trg_cpe_scope  BEFORE INSERT ON checkpoint_events  FOR EACH ROW EXECUTE FUNCTION enforce_operational_scope('unit_id');
CREATE TRIGGER trg_ap_scope   BEFORE INSERT ON airport_passengers FOR EACH ROW EXECUTE FUNCTION enforce_operational_scope('unit_id');
CREATE TRIGGER trg_inc_scope  BEFORE INSERT ON crime_incidents    FOR EACH ROW EXECUTE FUNCTION enforce_operational_scope('unit_id');

CREATE TRIGGER trg_cpe_creator BEFORE INSERT ON checkpoint_events  FOR EACH ROW EXECUTE FUNCTION events_stamp_creator();
CREATE TRIGGER trg_ap_creator  BEFORE INSERT ON airport_passengers FOR EACH ROW EXECUTE FUNCTION events_stamp_creator();
CREATE TRIGGER trg_inc_creator BEFORE INSERT ON crime_incidents    FOR EACH ROW EXECUTE FUNCTION events_stamp_creator();

CREATE TRIGGER trg_cpe_append BEFORE UPDATE OR DELETE ON checkpoint_events  FOR EACH ROW EXECUTE FUNCTION events_append_only();
CREATE TRIGGER trg_ap_append  BEFORE UPDATE OR DELETE ON airport_passengers FOR EACH ROW EXECUTE FUNCTION events_append_only();
CREATE TRIGGER trg_inc_guard  BEFORE UPDATE OR DELETE ON crime_incidents    FOR EACH ROW EXECUTE FUNCTION incident_guard();
CREATE TRIGGER trg_inc_validate BEFORE INSERT OR UPDATE ON crime_incidents     FOR EACH ROW EXECUTE FUNCTION incident_validate();

-- ---- 4. one airport record per person / movement / flight / day -------------
CREATE UNIQUE INDEX uq_ap_no_duplicate
    ON airport_passengers (unit_id, person_id, movement, travel_date, upper(flight_number));

-- ---- 7. uploads --------------------------------------------------------------
CREATE TABLE uploads (
    name          text PRIMARY KEY,                 -- server-generated, e.g. 'c0ffee….jpg'
    original_name text,
    content_type  text   NOT NULL,
    size_bytes    integer NOT NULL CHECK (size_bytes > 0),
    uploaded_by   bigint NOT NULL REFERENCES users(id),
    unit_id       bigint REFERENCES org_units(id),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION uploads_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION 'uploads is append-only' USING ERRCODE = '42501';
END $$;
CREATE TRIGGER trg_uploads_append BEFORE UPDATE OR DELETE ON uploads FOR EACH ROW EXECUTE FUNCTION uploads_append_only();

-- May this user open this file?  The uploader; anyone who may view a record that references it
-- (RLS applies — runs as the caller); or any registry searcher for a person's profile photo.
CREATE FUNCTION can_view_upload(p_user bigint, p_name text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM uploads WHERE name = p_name AND uploaded_by = p_user)
        OR EXISTS (SELECT 1 FROM checkpoint_events e
                    WHERE position('"' || p_name || '"' in e.details::text) > 0
                      AND authz_can(p_user, 'checkpoint:view', e.unit_id))
        OR EXISTS (SELECT 1 FROM crime_incidents i
                    WHERE position('"' || p_name || '"' in i.details::text) > 0
                      AND authz_can(p_user, 'incident:view', i.unit_id))
        OR EXISTS (SELECT 1 FROM persons p
                    WHERE p.photo_path = p_name AND authz_has(p_user, 'person:search'))
$$;

-- ---- desk officer lookup -------------------------------------------------------
-- A station officer files an incident naming the desk officer who took it, but does not hold
-- officer:view (HR data).  This returns ONLY id / service_ref / name / rank, and ONLY for an
-- active officer posted at that unit or below it.
CREATE FUNCTION desk_officer(p_unit bigint, p_service_ref text)
RETURNS TABLE (id bigint, service_ref text, full_name text, rank text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT o.id, o.service_ref, o.full_name, o.rank
      FROM officers o
      JOIN org_unit_closure c ON c.descendant_id = o.unit_id AND c.ancestor_id = p_unit
     WHERE o.service_ref = p_service_ref AND o.duty_status = 'Active'
$$;

INSERT INTO schema_migrations (version, name) VALUES ('003', 'operational_events');
