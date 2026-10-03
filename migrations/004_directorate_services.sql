-- =============================================================================
-- Migration 004 — Directorate & specialised services
--                 Fingerprint clearance · CID cases & alerts · HR officers & conduct
-- Northeastern Police System (unified platform)
--
-- Requires: 001, 002, 003.  ONE transaction, no extensions.
--
-- Migration 001 already created the tables (clearance_applications, crime_cases, suspect_alerts,
-- officers, conduct_actions), their unit-scoped RLS and the permissions.  This migration makes the
-- national services enforceable IN THE DATABASE:
--
--   1. STATE BOUNDARY.  Filings, case ownership, alert ownership and officer postings must sit inside
--      the Northeastern State: a unit under one of the regions listed in policy 'operations.regions'
--      (Sool, Sanaag, East Togdheer), or a national directorate / bureau.  A BUREAU (a branch of a
--      directorate) may claim a region with attrs.region; the claim is validated against the same
--      policy.  New bureaus, branches and postings are therefore INSERTs, never code.
--   2. CLEARANCE (T1).  Intake anywhere; approve / reject / sign only at the owning directorate.
--      The 12 h review window is enforced here (override = clearance:override_review_lock).
--      Decisions are one-way, the filed application is immutable, certificates are Ed25519-signed by
--      the service layer and verifiable publicly (signing_keys holds PUBLIC keys only).
--   3. CID.  Cases and alerts: provenance stamped by the DB, vocabularies are policy data, an alert's
--      owner is its case's owner, one active alert per person per case, alerts are lifted never deleted.
--      Evidence is an append-only table.
--   4. HR (T2).  Officers: rank and duty status change ONLY through an approved conduct file (or the
--      audited duty-status route); conduct files are filed against officers in the filer's subtree,
--      reviewed nationally by someone OTHER than the filer; approval applies its effects atomically and
--      writes an immutable service-history row.
--   5. Policy data for every vocabulary (ranks, classifications, case statuses, ...).
-- =============================================================================

-- ---- 1. policy data ------------------------------------------------------------
INSERT INTO policy_settings (key, value, description) VALUES
 ('clearance.purposes',      '["Education","Travel","Employment","Citizenship","Licence"]', 'Legacy CLEARANCE_REASONS'),
 ('clearance.required',      '{"photo": true, "applicant_docs": 2, "guardian": "all", "guardian_docs": 2}',
    'Clearance intake requirements ported from the legacy form. guardian: "all" | "minors" | "none"'),
 ('case.statuses',           '["Reported","Reported / Open","Under Investigation","Submitted for Prosecution","Referred to Court","Closed","Unresolved"]',
    'Legacy CASE_STATUSES'),
 ('case.participant_roles',  '["Suspect","Victim","Witness","Complainant"]', 'Legacy participant roles (only Suspect raises an alert flag)'),
 ('case.evidence_types',     '["Evidence","Photo","Statement","Physical item","Digital file","Other"]', 'Case evidence file types'),
 ('officer.ranks',           '["Constable","Corporal","Sergeant","Inspector","Chief Inspector","Superintendent","Commander","General"]',
    'Legacy OFFICER_RANKS — ORDER MATTERS (lowest first); it is the promotion ladder'),
 ('officer.duty_statuses',   '["Active","Suspended","Leave","Terminated","Retired"]', 'Legacy OFFICER_DUTY_STATUSES'),
 ('officer.divisions',       '["General Patrol","CID / Criminal Investigation","Traffic Control","Rapid Response Unit","Special Protection Unit","Logistics"]',
    'Legacy OFFICER_UNITS (the division an officer works in)'),
 ('officer.blood_groups',    '["A+","A-","B+","B-","AB+","AB-","O+","O-"]', 'Legacy OFFICER_BLOOD_GROUPS'),
 ('officer.guarantor_relationships', '["Parent","Spouse","Relative","Community Leader","Other"]', 'Legacy GUARANTOR_RELATIONSHIPS'),
 ('officer.doc_types_primary',   '["National ID","Passport","Birth Certificate","Letter of Guarantee"]', 'Legacy OFFICER_DOC_TYPES_PRIMARY'),
 ('officer.doc_types_secondary', '["Background Check","Reference Letter","Military Discharge","Other"]', 'Legacy OFFICER_DOC_TYPES_SECONDARY'),
 ('conduct.classifications', '{"Promotion / Commendation": ["Rank Advancement","Official Commendation","Medal of Bravery","Merit Award"], "Disciplinary / Penalty": ["Rank Demotion","Official Reprimand","Temporary Suspension","Formal Dismissal"]}',
    'Legacy CONDUCT_CLASSIFICATIONS: action type -> allowed classifications'),
 ('conduct.rank_direction',  '{"Rank Advancement": "up", "Rank Demotion": "down"}',
    'Classifications that change rank, and the direction the proposed rank must move on the ladder'),
 ('conduct.duty_effects',    '{"Formal Dismissal": "Terminated", "Temporary Suspension": "Suspended"}',
    'Classifications that also set the officer''s duty status once HR approves'),
 ('conduct.statuses',        '{"submitted": "Submitted to HR", "reviewing": "Under HR Review", "approved": "Verified & Approved", "rejected": "Rejected"}',
    'Conduct pipeline. submitted -> reviewing -> approved | rejected'),
 ('conduct.min_narrative_chars', '20', 'A conduct narrative must be a detailed justification (legacy CONDUCT_MIN_NARRATIVE_CHARS)');

-- policy_list() must keep the order of the JSON array (the rank ladder depends on it)
CREATE OR REPLACE FUNCTION policy_list(p_key text) RETURNS text[] LANGUAGE sql STABLE AS $$
    SELECT COALESCE(array_agg(t.x ORDER BY t.ord), ARRAY[]::text[])
      FROM policy_settings, jsonb_array_elements_text(value) WITH ORDINALITY AS t(x, ord) WHERE key = p_key
$$;

-- ---- 2. state boundary ---------------------------------------------------------
-- The region a unit belongs to, as a CODE: its region ancestor, or — for a bureau — the region it claims.
CREATE FUNCTION unit_claimed_region(p_unit bigint) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (SELECT r.code FROM org_units r WHERE r.id = unit_region(p_unit)),
        (SELECT a.attrs ->> 'region'
           FROM org_unit_closure c JOIN org_units a ON a.id = c.ancestor_id
          WHERE c.descendant_id = p_unit AND a.attrs ? 'region'
          ORDER BY c.depth LIMIT 1))
$$;

-- Display name of the unit's region (own ancestor, or the one a bureau claims).
CREATE FUNCTION unit_region_name(p_unit bigint) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT r.name FROM org_units r WHERE r.unit_type = 'region' AND r.code = unit_claimed_region(p_unit)
$$;

-- Inside the state?  Under a listed region, or a state-level unit (HQ / directorate / bureau) that
-- claims no region.  Unknown units are outside.
CREATE FUNCTION unit_in_state(p_unit bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM org_units WHERE id = p_unit)
       AND CASE WHEN unit_claimed_region(p_unit) IS NULL THEN true
                ELSE unit_claimed_region(p_unit) IN
                     (SELECT jsonb_array_elements_text(value) FROM policy_settings WHERE key = 'operations.regions')
           END
$$;

-- enforce_state_scope('unit_id'): INSERT always; UPDATE only when the column moves.
CREATE FUNCTION enforce_state_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; v bigint;
BEGIN
    v := (to_jsonb(NEW) ->> col)::bigint;
    IF TG_OP = 'UPDATE' AND v IS NOT DISTINCT FROM (to_jsonb(OLD) ->> col)::bigint THEN RETURN NEW; END IF;
    IF v IS NULL THEN RETURN NEW; END IF;
    IF NOT unit_in_state(v) THEN
        RAISE EXCEPTION '%.% unit % is outside the Northeastern State regions (policy operations.regions)',
            TG_TABLE_NAME, col, v USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

-- A bureau claiming a region must claim a LISTED region.  Only bureaus may claim one.
CREATE FUNCTION org_units_region_claim() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.attrs ? 'region' THEN
        IF NEW.unit_type <> 'bureau' THEN
            RAISE EXCEPTION 'only a bureau can claim a region (attrs.region); % is a %', NEW.code, NEW.unit_type
                USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM org_units r
                        WHERE r.unit_type = 'region' AND r.code = NEW.attrs ->> 'region'
                          AND r.code IN (SELECT jsonb_array_elements_text(value) FROM policy_settings
                                          WHERE key = 'operations.regions')) THEN
            RAISE EXCEPTION 'bureau % claims region "%", which is not one of the state regions (policy operations.regions)',
                NEW.code, NEW.attrs ->> 'region' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_org_units_region_claim BEFORE INSERT OR UPDATE ON org_units
    FOR EACH ROW EXECUTE FUNCTION org_units_region_claim();

-- Stamp a column with the authenticated user.  'strict' (default): an unauthenticated write is refused.
CREATE FUNCTION stamp_actor() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; must_auth boolean := COALESCE(TG_ARGV[1], 'strict') = 'strict';
BEGIN
    IF current_app_user() IS NULL THEN
        IF current_setting('sentinel.maintenance', true) = 'on' OR NOT must_auth THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'no authenticated user: % records cannot be written anonymously', TG_TABLE_NAME
            USING ERRCODE = '42501';
    END IF;
    NEW := jsonb_populate_record(NEW, jsonb_build_object(col, current_app_user()));
    RETURN NEW;
END $$;

CREATE FUNCTION no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN OLD; END IF;
    RAISE EXCEPTION '% records are never deleted', TG_TABLE_NAME USING ERRCODE = '42501';
END $$;

-- ---- 3. CLEARANCE (T1) ----------------------------------------------------------
ALTER TABLE clearance_applications DROP CONSTRAINT clearance_applications_purpose_check;   -- now policy data
ALTER TABLE clearance_applications ADD COLUMN review_notes         text;
ALTER TABLE clearance_applications ADD COLUMN certificate_snapshot jsonb;   -- the exact payload that was signed

CREATE TABLE signing_keys (          -- PUBLIC keys only. The private key never enters the database.
    key_id     text PRIMARY KEY,
    algorithm  text NOT NULL CHECK (algorithm = 'ed25519'),
    public_key text NOT NULL,
    status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE signing_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON signing_keys FOR SELECT USING (true);      -- no write policy: only the owner role registers keys
ALTER TABLE clearance_applications ADD CONSTRAINT fk_clr_signing_key
    FOREIGN KEY (signing_key_id) REFERENCES signing_keys(key_id);

CREATE FUNCTION clearance_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE uid bigint := current_app_user(); hours numeric; eligible timestamptz;
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN
        RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'clearance applications are never deleted' USING ERRCODE = '42501';
    END IF;
    IF uid IS NULL THEN
        RAISE EXCEPTION 'no authenticated user: clearance records cannot be written anonymously' USING ERRCODE = '42501';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'Pending Review' OR NEW.certificate_number IS NOT NULL OR NEW.certificate_signature IS NOT NULL
           OR NEW.signing_key_id IS NOT NULL OR NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL THEN
            RAISE EXCEPTION 'a new clearance application must be Pending Review and unsigned' USING ERRCODE = '23514';
        END IF;
        IF NOT (NEW.purpose = ANY (policy_list('clearance.purposes'))) THEN
            RAISE EXCEPTION 'unknown clearance purpose "%"', NEW.purpose USING ERRCODE = '23514';
        END IF;
        NEW.created_by := uid;
        NEW.created_at := now();             -- the review window starts at the DB clock, never the client's
        RETURN NEW;
    END IF;

    -- UPDATE = a decision, once
    IF OLD.status <> 'Pending Review' THEN
        RAISE EXCEPTION 'application % is already % — decisions are final', OLD.application_ref, OLD.status
            USING ERRCODE = '42501';
    END IF;
    IF NEW.status NOT IN ('Approved', 'Rejected') THEN
        RAISE EXCEPTION 'an application can only be Approved or Rejected' USING ERRCODE = '23514';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['status','reviewed_by','reviewed_at','review_notes','certificate_number',
                              'certificate_signature','signing_key_id','certificate_snapshot'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['status','reviewed_by','reviewed_at','review_notes','certificate_number',
                              'certificate_signature','signing_key_id','certificate_snapshot']) THEN
        RAISE EXCEPTION 'a filed clearance application is immutable except for the decision' USING ERRCODE = '42501';
    END IF;
    SELECT COALESCE((SELECT (value #>> '{}')::numeric FROM policy_settings WHERE key = 'clearance.review_window_hours'), 12)
      INTO hours;
    eligible := OLD.created_at + hours * interval '1 hour';
    IF now() < eligible AND NOT authz_can(uid, 'clearance:override_review_lock', OLD.owner_unit_id) THEN
        RAISE EXCEPTION 'Review period active. Standard officers must wait % hours before deciding (eligible %).',
            hours, eligible USING ERRCODE = '55000';
    END IF;
    IF NEW.status = 'Rejected' AND COALESCE(btrim(NEW.review_notes), '') = '' THEN
        RAISE EXCEPTION 'a rejection needs a reason' USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'Rejected' AND (NEW.certificate_number IS NOT NULL OR NEW.certificate_signature IS NOT NULL) THEN
        RAISE EXCEPTION 'a rejected application carries no certificate' USING ERRCODE = '23514';
    END IF;
    NEW.reviewed_by := uid;
    NEW.reviewed_at := now();
    RETURN NEW;
END $$;
CREATE TRIGGER trg_clr_guard BEFORE INSERT OR UPDATE OR DELETE ON clearance_applications
    FOR EACH ROW EXECUTE FUNCTION clearance_guard();
CREATE TRIGGER trg_clr_state BEFORE INSERT ON clearance_applications
    FOR EACH ROW EXECUTE FUNCTION enforce_state_scope('intake_unit_id');

-- Printing is national (clearance:print at the owner) and every print is logged.
CREATE TABLE clearance_prints (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id bigint NOT NULL REFERENCES clearance_applications(id),
    owner_unit_id  bigint NOT NULL REFERENCES org_units(id),
    printed_by     bigint NOT NULL REFERENCES users(id),
    printed_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_prn_stamp  BEFORE INSERT ON clearance_prints FOR EACH ROW EXECUTE FUNCTION stamp_actor('printed_by');
CREATE TRIGGER trg_prn_append BEFORE UPDATE OR DELETE ON clearance_prints FOR EACH ROW EXECUTE FUNCTION events_append_only();
ALTER TABLE clearance_prints ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON clearance_prints FOR SELECT
    USING (authz_can(current_app_user(), 'clearance:print', owner_unit_id));
CREATE POLICY p_insert ON clearance_prints FOR INSERT
    WITH CHECK (authz_can(current_app_user(), 'clearance:print', owner_unit_id)
                AND EXISTS (SELECT 1 FROM clearance_applications a
                             WHERE a.id = application_id AND a.status = 'Approved' AND a.owner_unit_id = clearance_prints.owner_unit_id));

-- Public verification: NO login, minimal output.  SECURITY DEFINER because the caller is anonymous;
-- the service rebuilds the signed payload and checks the Ed25519 signature itself.
CREATE FUNCTION certificate_for_verification(p_number text)
RETURNS TABLE (certificate_number text, application_ref text, status text, signature text, key_id text,
               snapshot jsonb, public_key text, key_status text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT a.certificate_number, a.application_ref, a.status, a.certificate_signature, a.signing_key_id,
           a.certificate_snapshot, k.public_key, k.status
      FROM clearance_applications a LEFT JOIN signing_keys k ON k.key_id = a.signing_key_id
     WHERE a.certificate_number = p_number
$$;

-- ---- 4. CID ---------------------------------------------------------------------
ALTER TABLE crime_cases ADD COLUMN location   text;
ALTER TABLE crime_cases ADD COLUMN notes      text;
ALTER TABLE crime_cases ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE crime_cases ADD CONSTRAINT ck_case_category CHECK (btrim(category) <> '');

CREATE FUNCTION case_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN NEW; END IF;
    IF NOT (NEW.status = ANY (policy_list('case.statuses'))) THEN
        RAISE EXCEPTION 'unknown case status "%"', NEW.status USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - ARRAY['category','status','incident_summary','notes','location','updated_at'])
           IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['category','status','incident_summary','notes','location','updated_at']) THEN
            RAISE EXCEPTION 'a case''s reference, owner, source incident and provenance are immutable' USING ERRCODE = '42501';
        END IF;
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_case_stamp  BEFORE INSERT ON crime_cases FOR EACH ROW EXECUTE FUNCTION stamp_actor('created_by');
CREATE TRIGGER trg_case_guard  BEFORE INSERT OR UPDATE ON crime_cases FOR EACH ROW EXECUTE FUNCTION case_guard();
CREATE TRIGGER trg_case_state  BEFORE INSERT ON crime_cases FOR EACH ROW EXECUTE FUNCTION enforce_state_scope('owner_unit_id');
CREATE TRIGGER trg_case_nodel  BEFORE DELETE ON crime_cases FOR EACH ROW EXECUTE FUNCTION no_delete();

CREATE TABLE case_evidence (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evidence_ref text UNIQUE NOT NULL,
    case_id      bigint NOT NULL REFERENCES crime_cases(id),
    caption      text,
    file_name    text NOT NULL REFERENCES uploads(name),
    file_type    text NOT NULL,
    uploaded_by  bigint NOT NULL REFERENCES users(id),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_evidence_case ON case_evidence (case_id);
CREATE FUNCTION evidence_validate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT (NEW.file_type = ANY (policy_list('case.evidence_types'))) THEN
        RAISE EXCEPTION 'unknown evidence type "%"', NEW.file_type USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_ev_stamp    BEFORE INSERT ON case_evidence FOR EACH ROW EXECUTE FUNCTION stamp_actor('uploaded_by');
CREATE TRIGGER trg_ev_validate BEFORE INSERT ON case_evidence FOR EACH ROW EXECUTE FUNCTION evidence_validate();
CREATE TRIGGER trg_ev_append   BEFORE UPDATE OR DELETE ON case_evidence FOR EACH ROW EXECUTE FUNCTION events_append_only();
ALTER TABLE case_evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON case_evidence FOR SELECT
    USING (EXISTS (SELECT 1 FROM crime_cases c WHERE c.id = case_id AND authz_can(current_app_user(), 'case:view', c.owner_unit_id)));
CREATE POLICY p_insert ON case_evidence FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM crime_cases c WHERE c.id = case_id AND authz_can(current_app_user(), 'case:update', c.owner_unit_id)));

-- suspect_alerts: participants of a case are rows too (legacy); only role 'Suspect' raises a flag.
ALTER TABLE suspect_alerts ADD COLUMN lifted_by  bigint REFERENCES users(id);
ALTER TABLE suspect_alerts ADD COLUMN lifted_at  timestamptz;
ALTER TABLE suspect_alerts ADD COLUMN lift_reason text;
ALTER TABLE suspect_alerts ADD CONSTRAINT ck_alert_status CHECK (alert_status IN ('Active alert', 'Lifted'));
ALTER TABLE suspect_alerts ADD CONSTRAINT ck_alert_lifted CHECK (
    (alert_status = 'Lifted') = (lifted_at IS NOT NULL AND lifted_by IS NOT NULL AND COALESCE(btrim(lift_reason), '') <> ''));
CREATE UNIQUE INDEX uq_alert_active_person_case
    ON suspect_alerts (person_id, COALESCE(case_id, 0)) WHERE alert_status = 'Active alert';

CREATE FUNCTION alert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE co bigint;
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN NEW; END IF;
    IF TG_OP = 'INSERT' THEN
        IF NOT (NEW.role = ANY (policy_list('case.participant_roles'))) THEN
            RAISE EXCEPTION 'unknown participant role "%"', NEW.role USING ERRCODE = '23514';
        END IF;
        IF NEW.alert_status <> 'Active alert' THEN
            RAISE EXCEPTION 'a new alert starts as an Active alert' USING ERRCODE = '23514';
        END IF;
        IF NEW.case_id IS NOT NULL THEN
            SELECT owner_unit_id INTO co FROM crime_cases WHERE id = NEW.case_id;
            IF co IS DISTINCT FROM NEW.owner_unit_id THEN
                RAISE EXCEPTION 'an alert is owned by the unit that owns its case' USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NEW;
    END IF;
    -- UPDATE: the only change is lifting an active alert, once
    IF OLD.alert_status <> 'Active alert' OR NEW.alert_status <> 'Lifted' THEN
        RAISE EXCEPTION 'an alert can only be lifted (Active alert -> Lifted), once' USING ERRCODE = '42501';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['alert_status','lifted_by','lifted_at','lift_reason'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['alert_status','lifted_by','lifted_at','lift_reason']) THEN
        RAISE EXCEPTION 'a filed alert is immutable except for lifting it' USING ERRCODE = '42501';
    END IF;
    NEW.lifted_by := current_app_user();
    NEW.lifted_at := now();
    RETURN NEW;
END $$;
CREATE TRIGGER trg_alert_stamp BEFORE INSERT ON suspect_alerts FOR EACH ROW EXECUTE FUNCTION stamp_actor('created_by');
CREATE TRIGGER trg_alert_guard BEFORE INSERT OR UPDATE ON suspect_alerts FOR EACH ROW EXECUTE FUNCTION alert_guard();
CREATE TRIGGER trg_alert_state BEFORE INSERT ON suspect_alerts FOR EACH ROW EXECUTE FUNCTION enforce_state_scope('owner_unit_id');
CREATE TRIGGER trg_alert_nodel BEFORE DELETE ON suspect_alerts FOR EACH ROW EXECUTE FUNCTION no_delete();

-- ---- 5. HR: officers --------------------------------------------------------------
CREATE UNIQUE INDEX uq_officer_person ON officers (person_id) WHERE person_id IS NOT NULL;

-- Append-only personnel history (rank changes, duty status changes, awards, penalties).
CREATE TABLE officer_service_history (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    officer_id  bigint NOT NULL REFERENCES officers(id),
    conduct_id  bigint REFERENCES conduct_actions(id),
    entry_type  text   NOT NULL,
    summary     text   NOT NULL,
    from_rank   text,
    to_rank     text,
    duty_status text,
    recorded_by bigint REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_hist_officer ON officer_service_history (officer_id, created_at DESC);
CREATE TRIGGER trg_hist_append BEFORE UPDATE OR DELETE ON officer_service_history
    FOR EACH ROW EXECUTE FUNCTION events_append_only();
ALTER TABLE officer_service_history ENABLE ROW LEVEL SECURITY;
-- Readable wherever the officer is (inherits officers' own RLS); written ONLY by the definer triggers below.
CREATE POLICY p_select ON officer_service_history FOR SELECT
    USING (EXISTS (SELECT 1 FROM officers o WHERE o.id = officer_id));

CREATE FUNCTION officer_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE applying boolean := COALESCE(current_setting('sentinel.conduct_apply', true), '') = 'on';
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END; END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'officer records are never deleted (set a duty status instead)' USING ERRCODE = '42501';
    END IF;
    IF NOT (NEW.rank = ANY (policy_list('officer.ranks'))) THEN
        RAISE EXCEPTION 'unknown rank "%"', NEW.rank USING ERRCODE = '23514';
    END IF;
    IF NOT (NEW.duty_status = ANY (policy_list('officer.duty_statuses'))) THEN
        RAISE EXCEPTION 'unknown duty status "%"', NEW.duty_status USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN RETURN NEW; END IF;

    IF NEW.service_ref <> OLD.service_ref OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at <> OLD.created_at OR (OLD.person_id IS NOT NULL AND NEW.person_id IS DISTINCT FROM OLD.person_id) THEN
        RAISE EXCEPTION 'an officer''s service reference, registry link and provenance are immutable' USING ERRCODE = '42501';
    END IF;
    IF NEW.rank <> OLD.rank AND NOT applying THEN
        RAISE EXCEPTION 'rank changes only through an approved HR conduct file' USING ERRCODE = '42501';
    END IF;
    IF NEW.duty_status <> OLD.duty_status AND NOT applying THEN
        IF OLD.duty_status = 'Terminated' THEN
            RAISE EXCEPTION 'a terminated officer cannot be reinstated here' USING ERRCODE = '42501';
        END IF;
        IF NEW.duty_status = 'Terminated' THEN
            RAISE EXCEPTION 'termination only through an approved Formal Dismissal conduct file' USING ERRCODE = '42501';
        END IF;
        INSERT INTO officer_service_history (officer_id, entry_type, summary, duty_status, recorded_by)
        VALUES (OLD.id, 'Duty status change',
                'Duty status ' || OLD.duty_status || ' → ' || NEW.duty_status
                    || COALESCE(' — ' || NULLIF(current_setting('app.change_reason', true), ''), ''),
                NEW.duty_status, current_app_user());
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_off_stamp  BEFORE INSERT ON officers FOR EACH ROW EXECUTE FUNCTION stamp_actor('created_by', 'lenient');
CREATE TRIGGER trg_off_guard  BEFORE INSERT OR UPDATE OR DELETE ON officers FOR EACH ROW EXECUTE FUNCTION officer_guard();
CREATE TRIGGER trg_off_state  BEFORE INSERT OR UPDATE ON officers FOR EACH ROW EXECUTE FUNCTION enforce_state_scope('unit_id');

-- The enlistment entry is written by the database, so a registration can never lack its history.
CREATE FUNCTION officer_after_insert() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN NEW; END IF;
    INSERT INTO officer_service_history (officer_id, entry_type, summary, to_rank, duty_status, recorded_by)
    VALUES (NEW.id, 'Enlistment',
            'Registered at ' || (SELECT name FROM org_units WHERE id = NEW.unit_id) || ' as ' || NEW.rank,
            NEW.rank, NEW.duty_status, NEW.created_by);
    RETURN NEW;
END $$;
CREATE TRIGGER trg_off_enlist AFTER INSERT ON officers FOR EACH ROW EXECUTE FUNCTION officer_after_insert();

-- The national register: whoever holds the permission at the HR directorate holds it for every officer
-- (HR's assignment is on DIR-HR, but the roster it keeps is national — T2).
CREATE POLICY p_hr_select ON officers FOR SELECT
    USING (authz_can(current_app_user(), 'officer:view',   service_unit('hr')));
CREATE POLICY p_hr_insert ON officers FOR INSERT
    WITH CHECK (authz_can(current_app_user(), 'officer:create', service_unit('hr')));
CREATE POLICY p_hr_update ON officers FOR UPDATE
    USING (authz_can(current_app_user(), 'officer:update', service_unit('hr')))
    WITH CHECK (authz_can(current_app_user(), 'officer:update', service_unit('hr')));

-- ---- 6. HR: conduct (T2) -------------------------------------------------------------
ALTER TABLE conduct_actions ADD COLUMN submitted_unit_id bigint REFERENCES org_units(id);  -- the unit the filer acted for
ALTER TABLE conduct_actions ADD COLUMN documents    jsonb   NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE conduct_actions ADD COLUMN rank_applied boolean NOT NULL DEFAULT false;
ALTER TABLE conduct_actions ADD COLUMN duty_applied text;

CREATE FUNCTION conduct_rank_ok(p_current text, p_proposed text, p_classification text) RETURNS text
LANGUAGE plpgsql STABLE AS $$
DECLARE dir text := (SELECT value ->> p_classification FROM policy_settings WHERE key = 'conduct.rank_direction');
        ladder text[] := policy_list('officer.ranks'); cur int; new int;
BEGIN
    IF dir IS NULL THEN RETURN NULL; END IF;                       -- this classification does not change rank
    IF p_proposed IS NULL OR btrim(p_proposed) = '' THEN
        RETURN p_classification || ' requires a proposed rank';
    END IF;
    cur := array_position(ladder, p_current);
    new := array_position(ladder, p_proposed);
    IF new IS NULL THEN RETURN 'unknown rank "' || p_proposed || '"'; END IF;
    IF cur IS NULL THEN RETURN 'the officer holds an unknown rank "' || p_current || '"'; END IF;
    IF dir = 'up'   AND new <= cur THEN RETURN p_classification || ' must propose a HIGHER rank than ' || p_current; END IF;
    IF dir = 'down' AND new >= cur THEN RETURN p_classification || ' must propose a LOWER rank than '  || p_current; END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION conduct_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE uid bigint := current_app_user();
        st jsonb := (SELECT value FROM policy_settings WHERE key = 'conduct.statuses');
        o officers%ROWTYPE; problem text; eff text; summary text; old_rank text;
BEGIN
    IF current_setting('sentinel.maintenance', true) = 'on' THEN RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END; END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'conduct files are never deleted' USING ERRCODE = '42501';
    END IF;
    IF uid IS NULL THEN
        RAISE EXCEPTION 'no authenticated user: conduct files cannot be written anonymously' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO o FROM officers WHERE id = NEW.officer_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'officer % does not exist', NEW.officer_id USING ERRCODE = '23514'; END IF;

    IF TG_OP = 'INSERT' THEN
        IF NOT ((SELECT value FROM policy_settings WHERE key = 'conduct.classifications') ? NEW.action_type) THEN
            RAISE EXCEPTION 'unknown conduct action type "%"', NEW.action_type USING ERRCODE = '23514';
        END IF;
        IF NOT ((SELECT value -> NEW.action_type FROM policy_settings WHERE key = 'conduct.classifications') ? NEW.classification) THEN
            RAISE EXCEPTION 'classification "%" does not belong to "%"', NEW.classification, NEW.action_type USING ERRCODE = '23514';
        END IF;
        IF length(btrim(regexp_replace(COALESCE(NEW.narrative, ''), '\s+', ' ', 'g')))
           < COALESCE((SELECT (value #>> '{}')::int FROM policy_settings WHERE key = 'conduct.min_narrative_chars'), 20) THEN
            RAISE EXCEPTION 'the narrative must be a detailed justification' USING ERRCODE = '23514';
        END IF;
        problem := conduct_rank_ok(o.rank, NEW.proposed_rank, NEW.classification);
        IF problem IS NOT NULL THEN RAISE EXCEPTION '%', problem USING ERRCODE = '23514'; END IF;
        IF NEW.submitted_unit_id IS NULL OR NOT EXISTS (
               SELECT 1 FROM org_unit_closure c WHERE c.ancestor_id = NEW.submitted_unit_id AND c.descendant_id = o.unit_id) THEN
            RAISE EXCEPTION 'a conduct file is filed for the officer''s own unit or a unit above it' USING ERRCODE = '23514';
        END IF;
        NEW.officer_unit_id := o.unit_id;               -- snapshot, never caller-supplied
        NEW.submitted_by    := uid;
        NEW.submitted_at    := now();
        NEW.status          := st ->> 'submitted';
        NEW.reviewed_by := NULL; NEW.reviewed_at := NULL; NEW.reviewer_notes := NULL;
        NEW.rank_applied := false; NEW.duty_applied := NULL;
        RETURN NEW;
    END IF;

    -- UPDATE = one step of the HR pipeline
    IF OLD.status IN (st ->> 'approved', st ->> 'rejected') THEN
        RAISE EXCEPTION 'conduct file % is closed (%)', OLD.action_ref, OLD.status USING ERRCODE = '42501';
    END IF;
    IF NEW.status NOT IN (st ->> 'reviewing', st ->> 'approved', st ->> 'rejected') OR NEW.status = OLD.status THEN
        RAISE EXCEPTION 'a conduct file moves to review, approved or rejected' USING ERRCODE = '23514';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['status','reviewed_by','reviewed_at','reviewer_notes','rank_applied','duty_applied'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['status','reviewed_by','reviewed_at','reviewer_notes','rank_applied','duty_applied']) THEN
        RAISE EXCEPTION 'a filed conduct file is immutable except for the HR decision' USING ERRCODE = '42501';
    END IF;
    IF uid = OLD.submitted_by THEN
        RAISE EXCEPTION 'separation of duties: the filer of a conduct file cannot review it' USING ERRCODE = '42501';
    END IF;
    IF NEW.status = st ->> 'rejected' AND COALESCE(btrim(NEW.reviewer_notes), '') = '' THEN
        RAISE EXCEPTION 'a rejection needs reviewer notes' USING ERRCODE = '23514';
    END IF;
    NEW.reviewed_by := uid;
    NEW.reviewed_at := now();
    NEW.rank_applied := false;  NEW.duty_applied := NULL;

    IF NEW.status = st ->> 'approved' THEN
        old_rank := o.rank;
        problem := conduct_rank_ok(o.rank, NEW.proposed_rank, NEW.classification);       -- vs the CURRENT rank
        IF problem IS NOT NULL THEN RAISE EXCEPTION '%', problem USING ERRCODE = '23514'; END IF;
        summary := NEW.action_type || ' — ' || NEW.classification || ' verified & approved by HR';
        PERFORM set_config('sentinel.conduct_apply', 'on', true);
        IF (SELECT value ->> NEW.classification FROM policy_settings WHERE key = 'conduct.rank_direction') IS NOT NULL THEN
            UPDATE officers SET rank = NEW.proposed_rank WHERE id = o.id;
            NEW.rank_applied := true;
            summary := summary || ' · rank ' || old_rank || ' → ' || NEW.proposed_rank;
        END IF;
        eff := (SELECT value ->> NEW.classification FROM policy_settings WHERE key = 'conduct.duty_effects');
        IF eff IS NOT NULL AND eff <> o.duty_status THEN
            UPDATE officers SET duty_status = eff WHERE id = o.id;
            NEW.duty_applied := eff;
            summary := summary || ' · duty status ' || o.duty_status || ' → ' || eff;
        END IF;
        PERFORM set_config('sentinel.conduct_apply', 'off', true);
        INSERT INTO officer_service_history (officer_id, conduct_id, entry_type, summary, from_rank, to_rank, duty_status, recorded_by)
        VALUES (o.id, NEW.id, NEW.classification, summary,
                CASE WHEN NEW.rank_applied THEN old_rank END, CASE WHEN NEW.rank_applied THEN NEW.proposed_rank END,
                COALESCE(NEW.duty_applied, o.duty_status), uid);
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_cond_guard BEFORE INSERT OR UPDATE OR DELETE ON conduct_actions
    FOR EACH ROW EXECUTE FUNCTION conduct_guard();
CREATE TRIGGER trg_cond_state BEFORE INSERT ON conduct_actions
    FOR EACH ROW EXECUTE FUNCTION enforce_state_scope('officer_unit_id');

-- ---- 7. uploads: file access follows record access (extends 003) -------------------------------
CREATE OR REPLACE FUNCTION can_view_upload(p_user bigint, p_name text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM uploads WHERE name = p_name AND uploaded_by = p_user)
        OR EXISTS (SELECT 1 FROM checkpoint_events e
                    WHERE position('"' || p_name || '"' in e.details::text) > 0
                      AND authz_can(p_user, 'checkpoint:view', e.unit_id))
        OR EXISTS (SELECT 1 FROM crime_incidents i
                    WHERE position('"' || p_name || '"' in i.details::text) > 0
                      AND authz_can(p_user, 'incident:view', i.unit_id))
        OR EXISTS (SELECT 1 FROM persons p
                    WHERE p.photo_path = p_name AND authz_has(p_user, 'person:search'))
        OR EXISTS (SELECT 1 FROM clearance_applications c
                    WHERE position('"' || p_name || '"' in c.details::text) > 0
                      AND (authz_can(p_user, 'clearance:view', c.intake_unit_id)
                        OR authz_can(p_user, 'clearance:view', c.owner_unit_id)))
        OR EXISTS (SELECT 1 FROM case_evidence e JOIN crime_cases cc ON cc.id = e.case_id
                    WHERE e.file_name = p_name AND authz_can(p_user, 'case:view', cc.owner_unit_id))
        OR EXISTS (SELECT 1 FROM conduct_actions a
                    WHERE position('"' || p_name || '"' in a.documents::text) > 0
                      AND (authz_can(p_user, 'conduct:view', a.officer_unit_id)
                        OR authz_can(p_user, 'conduct:view', a.owner_unit_id)))
        OR EXISTS (SELECT 1 FROM officers o
                    WHERE position('"' || p_name || '"' in o.details::text) > 0
                      AND (authz_can(p_user, 'officer:view', o.unit_id)
                        OR authz_can(p_user, 'officer:view', service_unit('hr'))))
$$;

-- HR registers officers INTO the Central Person Registry (an officer is a person; photo / identity live there).
INSERT INTO role_permissions (role_id, permission_code)
SELECT (SELECT id FROM roles WHERE code = 'hr_officer'), 'person:create'
 WHERE NOT EXISTS (SELECT 1 FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE code = 'hr_officer')
                      AND permission_code = 'person:create');

INSERT INTO schema_migrations (version, name) VALUES ('004', 'directorate_services');
