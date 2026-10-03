-- =============================================================================
-- Migration 001 — Initial schema
-- Northeastern Police System (unified platform)
--
-- Contents
--   PART 1  Org-unit tree, RBAC, unified scope engine, audit, reference numbers, policy
--   PART 2  Domain tables, integrity guards, person timeline / alert flag, row-level security
--   PART 3  Reference data: unit types + structure rules, permissions, roles,
--           and the official org tree (HQ → Sool / Sanaag / East Togdheer → districts → units)
--
-- Conventions
--   * Apply inside ONE transaction on ONE session (PART 3 uses pg_temp helper functions).
--   * Requires PostgreSQL 14+. No extensions.
--   * Demo/dev accounts are NOT part of this migration: see migrations/dev/001_demo_accounts.sql.
--   * Design rationale: docs/UNIFIED_SCHEMA_BLUEPRINT.md. Acceptance tests:
--     python docs/blueprint/test_blueprint.py
--
-- Official regional scope: the regions under HQ are exactly Sool, Sanaag and East Togdheer.
-- Units flagged attrs.needs_relocation_review are placeholders awaiting operational
-- confirmation of their district; fix with SELECT move_unit(<unit>, <district>).
-- =============================================================================

CREATE TABLE schema_migrations (
    version    text PRIMARY KEY,
    name       text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);


-- #############################################################################
-- PART 1 — ORG TREE, RBAC, SCOPE ENGINE
-- #############################################################################

-- ---------------------------------------------------------------------------
-- A. ORG TREE
-- ---------------------------------------------------------------------------
-- Unit types are DATA. Adding a new kind of unit (e.g. 'border_post') is an
-- INSERT into unit_types + unit_type_rules, not a code change.
CREATE TABLE unit_types (
    code          text PRIMARY KEY,
    label         text    NOT NULL,
    is_geographic boolean NOT NULL DEFAULT false,   -- region / district
    sort_order    integer NOT NULL DEFAULT 0
);

-- Which child types may sit under which parent types (structure rules).
CREATE TABLE unit_type_rules (
    parent_type text NOT NULL REFERENCES unit_types(code),
    child_type  text NOT NULL REFERENCES unit_types(code),
    PRIMARY KEY (parent_type, child_type)
);

CREATE TABLE org_units (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id   bigint REFERENCES org_units(id),
    unit_type   text   NOT NULL REFERENCES unit_types(code),
    code        text   NOT NULL UNIQUE,              -- stable human code, e.g. 'ST-004'
    name        text   NOT NULL,
    name_local  text,                                -- Somali / Arabic display name
    -- Set ONLY on national-directorate units: 'fingerprint','cid','hr','transport'.
    -- Lets national services find their owner unit without hardcoding IDs.
    service_key text,
    status      text   NOT NULL DEFAULT 'active'
                CHECK (status IN ('planned','active','inactive')),
    depth       integer NOT NULL DEFAULT 0,          -- maintained by trigger
    path        text    NOT NULL DEFAULT '',         -- '/1/7/42/' (display / breadcrumbs)
    attrs       jsonb   NOT NULL DEFAULT '{}'::jsonb,-- small, type-specific extras
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT root_is_hq   CHECK ((parent_id IS NULL) = (unit_type = 'hq')),
    CONSTRAINT service_key_on_directorate
        CHECK (service_key IS NULL OR unit_type = 'directorate')
);
CREATE UNIQUE INDEX uq_org_single_root   ON org_units (unit_type) WHERE unit_type = 'hq';
CREATE UNIQUE INDEX uq_org_service_key   ON org_units (service_key) WHERE service_key IS NOT NULL;
CREATE UNIQUE INDEX uq_org_sibling_name  ON org_units (COALESCE(parent_id, 0), lower(name));
CREATE INDEX        ix_org_parent        ON org_units (parent_id);
CREATE INDEX        ix_org_type          ON org_units (unit_type);

-- Closure table: one row for every (ancestor, descendant) pair, including
-- (self, self, 0). "Is X inside Y?" is one indexed lookup; no extension needed.
CREATE TABLE org_unit_closure (
    ancestor_id   bigint  NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
    descendant_id bigint  NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
    depth         integer NOT NULL,
    PRIMARY KEY (ancestor_id, descendant_id)
);
CREATE INDEX ix_closure_descendant ON org_unit_closure (descendant_id, ancestor_id);

-- Structure change log (create / rename / move / status).
CREATE TABLE org_unit_events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id    bigint NOT NULL REFERENCES org_units(id),
    action     text   NOT NULL,
    old_value  jsonb,
    new_value  jsonb,
    actor_id   bigint,
    at         timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- B. TREE OPERATIONS
-- ---------------------------------------------------------------------------
CREATE FUNCTION org_units_before_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p org_units%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (NEW.parent_id IS DISTINCT FROM OLD.parent_id OR NEW.unit_type <> OLD.unit_type)
           AND COALESCE(current_setting('sentinel.moving', true), '') <> 'on' THEN
            RAISE EXCEPTION 'parent/type of a unit can only be changed with move_unit()';
        END IF;
        NEW.updated_at := now();
        RETURN NEW;
    END IF;

    IF NEW.parent_id IS NULL THEN
        NEW.depth := 0;
        NEW.path  := '/' || NEW.id || '/';
    ELSE
        SELECT * INTO p FROM org_units WHERE id = NEW.parent_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'parent unit % does not exist', NEW.parent_id;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM unit_type_rules
                        WHERE parent_type = p.unit_type AND child_type = NEW.unit_type) THEN
            RAISE EXCEPTION 'a % cannot be placed under a %', NEW.unit_type, p.unit_type
                USING ERRCODE = '23514';
        END IF;
        NEW.depth := p.depth + 1;
        NEW.path  := p.path || NEW.id || '/';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_org_units_before
BEFORE INSERT OR UPDATE ON org_units
FOR EACH ROW EXECUTE FUNCTION org_units_before_write();

CREATE FUNCTION org_units_after_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO org_unit_closure (ancestor_id, descendant_id, depth)
    VALUES (NEW.id, NEW.id, 0);
    IF NEW.parent_id IS NOT NULL THEN
        INSERT INTO org_unit_closure (ancestor_id, descendant_id, depth)
        SELECT c.ancestor_id, NEW.id, c.depth + 1
          FROM org_unit_closure c WHERE c.descendant_id = NEW.parent_id;
    END IF;
    INSERT INTO org_unit_events (unit_id, action, new_value)
    VALUES (NEW.id, 'create', to_jsonb(NEW) - 'path');
    RETURN NEW;
END $$;

CREATE TRIGGER trg_org_units_after_insert
AFTER INSERT ON org_units
FOR EACH ROW EXECUTE FUNCTION org_units_after_insert();

-- Re-parent a whole subtree. Rebuilds paths, depths and closure rows.
CREATE FUNCTION move_unit(p_unit bigint, p_new_parent bigint, p_actor bigint DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE u org_units%ROWTYPE; np org_units%ROWTYPE; old_path text; new_prefix text;
BEGIN
    SELECT * INTO u  FROM org_units WHERE id = p_unit FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'unit % not found', p_unit; END IF;
    IF u.parent_id IS NULL THEN RAISE EXCEPTION 'the root unit cannot be moved'; END IF;
    SELECT * INTO np FROM org_units WHERE id = p_new_parent;
    IF NOT FOUND THEN RAISE EXCEPTION 'new parent % not found', p_new_parent; END IF;
    IF EXISTS (SELECT 1 FROM org_unit_closure
                WHERE ancestor_id = p_unit AND descendant_id = p_new_parent) THEN
        RAISE EXCEPTION 'cannot move a unit into its own subtree';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM unit_type_rules
                    WHERE parent_type = np.unit_type AND child_type = u.unit_type) THEN
        RAISE EXCEPTION 'a % cannot be placed under a %', u.unit_type, np.unit_type
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_config('sentinel.moving', 'on', true);
    old_path   := u.path;
    new_prefix := np.path || u.id || '/';

    UPDATE org_units SET parent_id = p_new_parent WHERE id = p_unit;
    UPDATE org_units
       SET path  = new_prefix || substr(path, length(old_path) + 1),
           depth = np.depth + 1 + (depth - u.depth)
     WHERE path LIKE old_path || '%';

    -- detach the subtree from its old ancestors …
    DELETE FROM org_unit_closure
     WHERE descendant_id IN (SELECT descendant_id FROM org_unit_closure WHERE ancestor_id = p_unit)
       AND ancestor_id  NOT IN (SELECT descendant_id FROM org_unit_closure WHERE ancestor_id = p_unit);
    -- … and attach it to the new ones
    INSERT INTO org_unit_closure (ancestor_id, descendant_id, depth)
    SELECT sup.ancestor_id, sub.descendant_id, sup.depth + 1 + sub.depth
      FROM org_unit_closure sup, org_unit_closure sub
     WHERE sup.descendant_id = p_new_parent AND sub.ancestor_id = p_unit;

    PERFORM set_config('sentinel.moving', 'off', true);
    INSERT INTO org_unit_events (unit_id, action, old_value, new_value, actor_id)
    VALUES (p_unit, 'move', jsonb_build_object('parent_id', u.parent_id),
            jsonb_build_object('parent_id', p_new_parent), p_actor);
END $$;

-- ---------------------------------------------------------------------------
-- C. RBAC
-- ---------------------------------------------------------------------------
-- NOTE: if the unified codebase already has a users table, keep it. The only
-- requirement of this blueprint is a bigint user id and an `active` flag.
CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      text UNIQUE NOT NULL,
    display_name  text NOT NULL,
    password_hash text NOT NULL,              -- use argon2/bcrypt, never bare SHA-256
    active        boolean NOT NULL DEFAULT true,
    home_unit_id  bigint REFERENCES org_units(id),   -- display only; grants nothing
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- A permission is "module:action".
--   is_write    — false for pure reads. Roles flagged read_only may hold ONLY these.
--   scope_kind  — 'unit'  : checked against a unit in the tree (authz_can)
--                 'global': not tied to a unit (authz_has), e.g. person:search
CREATE TABLE permissions (
    code        text PRIMARY KEY CHECK (code ~ '^[a-z_]+:[a-z_]+$'),
    module      text    NOT NULL,
    action      text    NOT NULL,
    is_write    boolean NOT NULL,
    scope_kind  text    NOT NULL CHECK (scope_kind IN ('unit','global')),
    description text
);

CREATE TABLE roles (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         text UNIQUE NOT NULL,
    name         text NOT NULL,
    is_read_only boolean NOT NULL DEFAULT false,
    is_system    boolean NOT NULL DEFAULT false
);

CREATE TABLE role_permissions (
    role_id         bigint NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_code text   NOT NULL REFERENCES permissions(code),
    PRIMARY KEY (role_id, permission_code)
);

-- Replaces the old hardcoded read-only firewall (enforce_read_only): a role
-- flagged read_only physically cannot be given a write permission.
CREATE FUNCTION role_permissions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM roles r, permissions p
                WHERE r.id = NEW.role_id AND r.is_read_only
                  AND p.code = NEW.permission_code AND p.is_write) THEN
        RAISE EXCEPTION 'read-only role cannot hold write permission %', NEW.permission_code
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_role_permissions_guard
BEFORE INSERT OR UPDATE ON role_permissions
FOR EACH ROW EXECUTE FUNCTION role_permissions_guard();

-- The ONLY place a user is tied to the tree. Replaces users.branch and
-- users.location_scope. A user may hold several assignments.
CREATE TABLE user_assignments (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             bigint NOT NULL REFERENCES users(id),
    role_id             bigint NOT NULL REFERENCES roles(id),
    unit_id             bigint NOT NULL REFERENCES org_units(id),
    include_descendants boolean NOT NULL DEFAULT true,
    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_until         timestamptz,
    revoked_at          timestamptz,
    granted_by          bigint REFERENCES users(id),
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_active_assignment
    ON user_assignments (user_id, role_id, unit_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_assignment_user ON user_assignments (user_id) WHERE revoked_at IS NULL;

CREATE VIEW active_assignments AS
SELECT a.*
  FROM user_assignments a
  JOIN users u ON u.id = a.user_id AND u.active
 WHERE a.revoked_at IS NULL
   AND a.valid_from <= now()
   AND (a.valid_until IS NULL OR a.valid_until > now());

-- ---------------------------------------------------------------------------
-- D. THE UNIFIED SCOPE ENGINE
--    Every read filter and every write check in the platform goes through these.
-- ---------------------------------------------------------------------------

-- All unit ids where the user holds `perm` (assignment unit + descendants when
-- include_descendants). Use for list queries:  WHERE unit_id IN (SELECT authz_scope(:u,'x:view'))
CREATE FUNCTION authz_scope(p_user bigint, p_perm text) RETURNS SETOF bigint
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT c.descendant_id
      FROM active_assignments a
      JOIN role_permissions rp ON rp.role_id = a.role_id AND rp.permission_code = p_perm
      JOIN org_unit_closure c  ON c.ancestor_id = a.unit_id
                              AND (a.include_descendants OR c.depth = 0)
     WHERE a.user_id = p_user
$$;

-- Point check. Use for detail views and EVERY mutation:  authz_can(:u,'x:create', target_unit)
CREATE FUNCTION authz_can(p_user bigint, p_perm text, p_unit bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT p_unit IS NOT NULL AND EXISTS (
        SELECT 1
          FROM active_assignments a
          JOIN role_permissions rp ON rp.role_id = a.role_id AND rp.permission_code = p_perm
          JOIN org_unit_closure c  ON c.ancestor_id = a.unit_id
                                  AND c.descendant_id = p_unit
                                  AND (a.include_descendants OR c.depth = 0)
         WHERE a.user_id = p_user)
$$;

-- Global permissions (person:search, alert:check, …): held anywhere = held.
CREATE FUNCTION authz_has(p_user bigint, p_perm text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM active_assignments a
          JOIN role_permissions rp ON rp.role_id = a.role_id AND rp.permission_code = p_perm
         WHERE a.user_id = p_user)
$$;

-- National service owner unit, e.g. service_unit('fingerprint') = the Fingerprint directorate.
CREATE FUNCTION service_unit(p_key text) RETURNS bigint
LANGUAGE sql STABLE AS $$ SELECT id FROM org_units WHERE service_key = p_key $$;

-- Nearest ancestor-or-self directorate with a service_key (NULL for geographic units).
CREATE FUNCTION owning_service_unit(p_unit bigint) RETURNS bigint
LANGUAGE sql STABLE AS $$
    SELECT o.id FROM org_unit_closure c JOIN org_units o ON o.id = c.ancestor_id
     WHERE c.descendant_id = p_unit AND o.service_key IS NOT NULL
     ORDER BY c.depth LIMIT 1
$$;

-- Delegated administration without privilege escalation: a grantor may assign a
-- role at a unit only if they hold assignment:manage there AND already hold every
-- permission of that role at that unit.
CREATE FUNCTION can_grant(p_grantor bigint, p_role bigint, p_unit bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT authz_can(p_grantor, 'assignment:manage', p_unit)
       AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
             WHERE rp.role_id = p_role
               AND CASE (SELECT scope_kind FROM permissions WHERE code = rp.permission_code)
                       WHEN 'global' THEN NOT authz_has(p_grantor, rp.permission_code)
                       ELSE NOT authz_can(p_grantor, rp.permission_code, p_unit)
                   END)
$$;

-- ---------------------------------------------------------------------------
-- E. PLATFORM TABLES
-- ---------------------------------------------------------------------------
-- Append-only audit trail. unit_id = the unit the action concerned.
CREATE TABLE audit_events (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id   bigint REFERENCES users(id),
    unit_id   bigint REFERENCES org_units(id),
    action    text NOT NULL,
    entity    text NOT NULL,
    entity_id text,
    details   jsonb NOT NULL DEFAULT '{}'::jsonb,
    at        timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION audit_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$;
CREATE TRIGGER trg_audit_immutable BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

-- Concurrency-safe reference numbers (replaces 'CP-'||time-derived ids).
-- next_ref('CP','ST-004') -> 'CP-ST-004-2026-000001'
CREATE TABLE ref_sequences (
    prefix     text    NOT NULL,
    scope      text    NOT NULL DEFAULT '',
    year       integer NOT NULL,
    last_value bigint  NOT NULL,
    PRIMARY KEY (prefix, scope, year)
);
CREATE FUNCTION next_ref(p_prefix text, p_scope text DEFAULT '',
                         p_year integer DEFAULT EXTRACT(year FROM now())::integer)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    INSERT INTO ref_sequences AS r (prefix, scope, year, last_value)
    VALUES (p_prefix, p_scope, p_year, 1)
    ON CONFLICT (prefix, scope, year) DO UPDATE SET last_value = r.last_value + 1
    RETURNING r.last_value INTO n;
    RETURN p_prefix || '-' || CASE WHEN p_scope = '' THEN '' ELSE p_scope || '-' END
           || p_year || '-' || lpad(n::text, 6, '0');
END $$;

-- Tunable policy values (replaces hardcoded constants such as the 12 h lock).
CREATE TABLE policy_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    description text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- #############################################################################
-- PART 2 — DOMAIN TABLES, GUARDS, ROW-LEVEL SECURITY
-- #############################################################################

-- ---------------------------------------------------------------------------
-- Generic guards (replace the legacy hardcoded CHECKPOINT_LOCATIONS logic)
-- ---------------------------------------------------------------------------
-- enforce_unit_type('unit_id','checkpoint')  — column must point at a unit of one of the listed types
CREATE FUNCTION enforce_unit_type() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; v bigint; t text;
BEGIN
    v := (to_jsonb(NEW) ->> col)::bigint;
    IF v IS NULL THEN RETURN NEW; END IF;
    SELECT unit_type INTO t FROM org_units WHERE id = v;
    IF t IS NULL OR NOT (t = ANY (TG_ARGV[1:array_length(TG_ARGV, 1) - 1])) THEN
        RAISE EXCEPTION '%.% must reference a unit of type (%), got %',
            TG_TABLE_NAME, col, array_to_string(TG_ARGV[1:array_length(TG_ARGV, 1) - 1], ','), COALESCE(t, 'none')
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

-- enforce_active_unit('unit_id') — NEW records may only be created in ACTIVE units
-- (history in inactive/planned units stays readable; nothing new is written).
CREATE FUNCTION enforce_active_unit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; v bigint; s text;
BEGIN
    v := (to_jsonb(NEW) ->> col)::bigint;
    IF v IS NULL THEN RETURN NEW; END IF;
    SELECT status INTO s FROM org_units WHERE id = v;
    IF s IS DISTINCT FROM 'active' THEN
        RAISE EXCEPTION 'unit % is not active (status: %)', v, COALESCE(s, 'missing')
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

-- enforce_service_owner('owner_unit_id','fingerprint') — owner must be that directorate or a bureau below it
CREATE FUNCTION enforce_service_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE col text := TG_ARGV[0]; key text := TG_ARGV[1]; v bigint;
BEGIN
    v := (to_jsonb(NEW) ->> col)::bigint;
    IF v IS NULL OR owning_service_unit(v) IS DISTINCT FROM service_unit(key) THEN
        RAISE EXCEPTION '%.% must be the % directorate or one of its bureaus', TG_TABLE_NAME, col, key
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- GLOBAL: persons (Central Person Registry)
-- ---------------------------------------------------------------------------
CREATE TABLE persons (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_ref         text UNIQUE NOT NULL,             -- 'P-000123'
    first_name         text, second_name text, third_name text, fourth_name text,
    full_name          text NOT NULL,
    date_of_birth      date,
    national_id        text UNIQUE,
    passport_id        text UNIQUE,
    mother_name        text,
    phone              text,
    residence          text,
    occupation         text,
    photo_path         text,
    created_by         bigint REFERENCES users(id),
    created_in_unit_id bigint REFERENCES org_units(id),  -- provenance only, grants nothing
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_persons_name ON persons (lower(full_name));

-- Fill-only enrichment now writes to a shared record from many units: log who/where.
CREATE TABLE person_field_audit (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES persons(id),
    field     text   NOT NULL,
    old_value text,
    new_value text,
    user_id   bigint REFERENCES users(id),
    unit_id   bigint REFERENCES org_units(id),
    at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- UNIT-SCOPED events
-- ---------------------------------------------------------------------------
CREATE TABLE checkpoint_events (                          -- was: checkpoint_events (3 text location columns)
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_ref        text UNIQUE NOT NULL,
    unit_id          bigint NOT NULL REFERENCES org_units(id),   -- a 'checkpoint' unit
    person_id        bigint NOT NULL REFERENCES persons(id),
    screening_result text   NOT NULL,
    action_taken     text   NOT NULL DEFAULT 'Cleared',
    purpose_of_visit text,
    notes            text,
    details          jsonb  NOT NULL DEFAULT '{}'::jsonb,    -- guardian_*, docs … (port legacy columns)
    created_by       bigint REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_cpe_unit   ON checkpoint_events (unit_id, created_at DESC);
CREATE INDEX ix_cpe_person ON checkpoint_events (person_id);
CREATE TRIGGER trg_cpe_type   BEFORE INSERT OR UPDATE ON checkpoint_events
    FOR EACH ROW EXECUTE FUNCTION enforce_unit_type('unit_id', 'checkpoint');
CREATE TRIGGER trg_cpe_active BEFORE INSERT ON checkpoint_events
    FOR EACH ROW EXECUTE FUNCTION enforce_active_unit('unit_id');

CREATE TABLE airport_passengers (                         -- was: airport_passengers (no location)
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_ref       text UNIQUE NOT NULL,
    unit_id          bigint NOT NULL REFERENCES org_units(id),   -- an 'airport' unit
    person_id        bigint NOT NULL REFERENCES persons(id),
    movement         text   NOT NULL CHECK (movement IN ('Arrival','Departure')),
    travel_date      date   NOT NULL,
    flight_number    text   NOT NULL,
    airline          text, origin_city text, destination_city text, notes text,
    created_by       bigint REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ap_unit   ON airport_passengers (unit_id, travel_date DESC);
CREATE INDEX ix_ap_person ON airport_passengers (person_id);
CREATE TRIGGER trg_ap_type   BEFORE INSERT OR UPDATE ON airport_passengers
    FOR EACH ROW EXECUTE FUNCTION enforce_unit_type('unit_id', 'airport');
CREATE TRIGGER trg_ap_active BEFORE INSERT ON airport_passengers
    FOR EACH ROW EXECUTE FUNCTION enforce_active_unit('unit_id');

CREATE TABLE crime_incidents (                            -- station crime intake ("Register Crime")
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_number text UNIQUE NOT NULL,
    unit_id     bigint NOT NULL REFERENCES org_units(id),   -- station / checkpoint / airport
    officer_id  bigint,                                      -- FK added after officers
    category    text NOT NULL,
    incident_at timestamptz NOT NULL,
    severity    text,
    description text NOT NULL,
    case_status text NOT NULL DEFAULT 'Reported / Open',
    details     jsonb NOT NULL DEFAULT '{}'::jsonb,          -- victim_*, statement, evidence
    created_by  bigint REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_inc_unit ON crime_incidents (unit_id, incident_at DESC);
CREATE TRIGGER trg_inc_type   BEFORE INSERT OR UPDATE ON crime_incidents
    FOR EACH ROW EXECUTE FUNCTION enforce_unit_type('unit_id', 'station', 'checkpoint', 'airport');
CREATE TRIGGER trg_inc_active BEFORE INSERT ON crime_incidents
    FOR EACH ROW EXECUTE FUNCTION enforce_active_unit('unit_id');

CREATE TABLE officers (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_ref        text UNIQUE NOT NULL,
    person_id          bigint REFERENCES persons(id),        -- link officer to the master record
    unit_id            bigint NOT NULL REFERENCES org_units(id),  -- posting (was: station_id)
    rank               text NOT NULL,
    unit_role          text NOT NULL,                        -- was: officers.unit ('General Patrol', …)
    duty_status        text NOT NULL DEFAULT 'Active',
    full_name          text NOT NULL,
    details            jsonb NOT NULL DEFAULT '{}'::jsonb,   -- origin, guarantor, documents … (port legacy)
    created_by         bigint REFERENCES users(id),
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_off_unit ON officers (unit_id);
CREATE TRIGGER trg_off_active BEFORE INSERT ON officers
    FOR EACH ROW EXECUTE FUNCTION enforce_active_unit('unit_id');
ALTER TABLE crime_incidents ADD CONSTRAINT fk_inc_officer FOREIGN KEY (officer_id) REFERENCES officers(id);

CREATE TABLE vehicles (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_ref        text UNIQUE NOT NULL,
    category           text NOT NULL CHECK (category IN ('Police Fleet','Civilian / Commercial')),
    plate_number       text UNIQUE NOT NULL,
    vin                text UNIQUE NOT NULL,
    make_model         text NOT NULL,
    unit_id            bigint REFERENCES org_units(id),      -- police fleet: assigned unit; civilian: NULL
    officer_id         bigint REFERENCES officers(id),
    operational_status text,
    security_alert     text NOT NULL DEFAULT 'Clean / Normal',
    alert_reason       text,
    details            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by         bigint REFERENCES users(id),
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fleet_has_unit CHECK (category <> 'Police Fleet' OR unit_id IS NOT NULL)
);
CREATE INDEX ix_veh_unit ON vehicles (unit_id);

-- ---------------------------------------------------------------------------
-- NATIONAL SERVICES
-- ---------------------------------------------------------------------------
-- Clearance (T1): filed anywhere (intake_unit_id), owned/approved nationally.
CREATE TABLE clearance_applications (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_ref       text UNIQUE NOT NULL,
    person_id             bigint NOT NULL REFERENCES persons(id),
    intake_unit_id        bigint NOT NULL REFERENCES org_units(id),  -- where it was filed
    owner_unit_id         bigint NOT NULL DEFAULT service_unit('fingerprint')
                          REFERENCES org_units(id),                  -- directorate (or bureau)
    purpose               text NOT NULL
                          CHECK (purpose IN ('Education','Travel','Employment','Citizenship','Licence')),
    status                text NOT NULL DEFAULT 'Pending Review'
                          CHECK (status IN ('Pending Review','Approved','Rejected')),
    details               jsonb NOT NULL DEFAULT '{}'::jsonb,        -- guardian, docs, sex, email …
    created_by            bigint REFERENCES users(id),
    created_at            timestamptz NOT NULL DEFAULT now(),
    reviewed_by           bigint REFERENCES users(id),
    reviewed_at           timestamptz,
    certificate_number    text UNIQUE,
    -- "cryptographic signing": the service layer signs the canonical certificate
    -- payload with the directorate key and stores the result; verification is public.
    certificate_signature text,
    signing_key_id        text,
    CONSTRAINT approved_is_complete CHECK (
        status <> 'Approved'
        OR (certificate_number IS NOT NULL AND certificate_signature IS NOT NULL
            AND signing_key_id IS NOT NULL AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX ix_clr_intake ON clearance_applications (intake_unit_id, created_at DESC);
CREATE INDEX ix_clr_person ON clearance_applications (person_id);
CREATE TRIGGER trg_clr_owner  BEFORE INSERT OR UPDATE ON clearance_applications
    FOR EACH ROW EXECUTE FUNCTION enforce_service_owner('owner_unit_id', 'fingerprint');
CREATE TRIGGER trg_clr_active BEFORE INSERT ON clearance_applications
    FOR EACH ROW EXECUTE FUNCTION enforce_active_unit('intake_unit_id');

-- CID (national). owner_unit_id is the directorate by default, or a CID bureau.
CREATE TABLE crime_cases (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_ref           text UNIQUE NOT NULL,
    owner_unit_id      bigint NOT NULL DEFAULT service_unit('cid') REFERENCES org_units(id),
    source_incident_id bigint REFERENCES crime_incidents(id),     -- explicit escalation link
    category           text NOT NULL,
    status             text NOT NULL DEFAULT 'Reported',
    incident_summary   text,
    created_by         bigint REFERENCES users(id),
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_case_owner BEFORE INSERT OR UPDATE ON crime_cases
    FOR EACH ROW EXECUTE FUNCTION enforce_service_owner('owner_unit_id', 'cid');

CREATE TABLE suspect_alerts (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_ref      text UNIQUE NOT NULL,
    person_id      bigint NOT NULL REFERENCES persons(id),
    case_id        bigint REFERENCES crime_cases(id),
    owner_unit_id  bigint NOT NULL DEFAULT service_unit('cid') REFERENCES org_units(id),
    role           text NOT NULL DEFAULT 'Suspect',
    alert_status   text NOT NULL DEFAULT 'Active alert',
    origin         text NOT NULL DEFAULT 'Direct Intelligence Listing',
    notes          text,
    created_by     bigint REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_alert_person ON suspect_alerts (person_id) WHERE alert_status = 'Active alert';
CREATE TRIGGER trg_alert_owner BEFORE INSERT OR UPDATE ON suspect_alerts
    FOR EACH ROW EXECUTE FUNCTION enforce_service_owner('owner_unit_id', 'cid');

-- HR conduct (T2): filed by units against officers in their subtree, reviewed nationally.
CREATE TABLE conduct_actions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_ref      text UNIQUE NOT NULL,
    officer_id      bigint NOT NULL REFERENCES officers(id),
    officer_unit_id bigint NOT NULL REFERENCES org_units(id),   -- snapshot of the officer's unit at filing time
    owner_unit_id   bigint NOT NULL DEFAULT service_unit('hr') REFERENCES org_units(id),
    action_type     text NOT NULL,
    classification  text NOT NULL,
    proposed_rank   text,
    narrative       text NOT NULL,
    status          text NOT NULL DEFAULT 'Submitted to HR',
    submitted_by    bigint NOT NULL REFERENCES users(id),
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    reviewed_by     bigint REFERENCES users(id),
    reviewed_at     timestamptz,
    reviewer_notes  text
);
CREATE INDEX ix_cond_unit ON conduct_actions (officer_unit_id);
CREATE TRIGGER trg_cond_owner BEFORE INSERT OR UPDATE ON conduct_actions
    FOR EACH ROW EXECUTE FUNCTION enforce_service_owner('owner_unit_id', 'hr');

-- ---------------------------------------------------------------------------
-- Cross-cutting reads that must NOT leak detail
-- ---------------------------------------------------------------------------
-- A checkpoint officer must learn "this person has an active alert" without being
-- able to read the CID case. SECURITY DEFINER bypasses the RLS on suspect_alerts and
-- returns ONLY a boolean. Requires the global permission alert:check.
CREATE FUNCTION person_alert_flag(p_user bigint, p_person bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT authz_has(p_user, 'alert:check')
       AND EXISTS (SELECT 1 FROM suspect_alerts
                    WHERE person_id = p_person AND alert_status = 'Active alert'
                      AND role = 'Suspect')
$$;

-- Person timeline: the union of the person's unit-scoped events, filtered by what
-- THIS viewer may see. Unit officers see their own unit; commanders see their subtree;
-- the Chief Commander (root assignment) sees everything.
CREATE FUNCTION person_timeline(p_user bigint, p_person bigint)
RETURNS TABLE (occurred_at timestamptz, kind text, unit_id bigint, ref text, summary text)
LANGUAGE sql STABLE AS $$
    SELECT e.created_at, 'checkpoint', e.unit_id, e.event_ref, e.screening_result
      FROM checkpoint_events e
     WHERE e.person_id = p_person AND authz_can(p_user, 'checkpoint:view', e.unit_id)
    UNION ALL
    SELECT a.created_at, 'airport', a.unit_id, a.record_ref, a.movement || ' ' || a.flight_number
      FROM airport_passengers a
     WHERE a.person_id = p_person AND authz_can(p_user, 'airport:view', a.unit_id)
    UNION ALL
    SELECT c.created_at, 'clearance', c.intake_unit_id, c.application_ref, c.purpose || ' — ' || c.status
      FROM clearance_applications c
     WHERE c.person_id = p_person
       AND (authz_can(p_user, 'clearance:view', c.intake_unit_id)
         OR authz_can(p_user, 'clearance:view', c.owner_unit_id))
    ORDER BY 1 DESC
$$;

-- ---------------------------------------------------------------------------
-- DEFENCE IN DEPTH: PostgreSQL row-level security
-- The API sets, per request/transaction:  SELECT set_config('app.user_id', '<id>', true);
-- and connects as a NON-owner role (e.g. sentinel_app). Even a forgotten WHERE clause
-- in application code cannot cross a unit boundary.
-- ---------------------------------------------------------------------------
CREATE FUNCTION current_app_user() RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::bigint
$$;

-- helper to keep the policy list short
DO $$
DECLARE
    spec record;
BEGIN
    FOR spec IN
        SELECT * FROM (VALUES
            -- table               unit column       view perm            insert perm          update perm
            ('checkpoint_events',  'unit_id',        'checkpoint:view',   'checkpoint:create', 'checkpoint:create'),
            ('airport_passengers', 'unit_id',        'airport:view',      'airport:create',    'airport:create'),
            ('crime_incidents',    'unit_id',        'incident:view',     'incident:create',   'incident:create'),
            ('officers',           'unit_id',        'officer:view',      'officer:create',    'officer:update'),
            ('crime_cases',        'owner_unit_id',  'case:view',         'case:create',       'case:update'),
            ('suspect_alerts',     'owner_unit_id',  'alert:view_detail', 'alert:create',      'alert:create')
        ) AS t(tbl, col, vperm, iperm, uperm)
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', spec.tbl);
        EXECUTE format($p$CREATE POLICY p_select ON %I FOR SELECT
            USING (authz_can(current_app_user(), %L, %I))$p$, spec.tbl, spec.vperm, spec.col);
        EXECUTE format($p$CREATE POLICY p_insert ON %I FOR INSERT
            WITH CHECK (authz_can(current_app_user(), %L, %I))$p$, spec.tbl, spec.iperm, spec.col);
        EXECUTE format($p$CREATE POLICY p_update ON %I FOR UPDATE
            USING (authz_can(current_app_user(), %L, %I))
            WITH CHECK (authz_can(current_app_user(), %L, %I))$p$,
            spec.tbl, spec.uperm, spec.col, spec.uperm, spec.col);
    END LOOP;
END $$;

-- Clearance: visible from the intake unit's side OR the owning directorate's side;
-- INSERT needs clearance:create at the INTAKE unit; UPDATE (approve/print) needs the
-- permission at the OWNER unit — a bureau user's assignment does not cover the directorate,
-- so approval stays national by construction.
ALTER TABLE clearance_applications ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON clearance_applications FOR SELECT
    USING (authz_can(current_app_user(), 'clearance:view', intake_unit_id)
        OR authz_can(current_app_user(), 'clearance:view', owner_unit_id));
CREATE POLICY p_insert ON clearance_applications FOR INSERT
    WITH CHECK (authz_can(current_app_user(), 'clearance:create', intake_unit_id));
CREATE POLICY p_update ON clearance_applications FOR UPDATE
    USING (authz_can(current_app_user(), 'clearance:approve', owner_unit_id))
    WITH CHECK (authz_can(current_app_user(), 'clearance:approve', owner_unit_id));

-- Conduct: readable by the HR desk (owner) and by anyone with conduct:view over the
-- officer's unit; INSERT requires conduct:submit over the OFFICER's unit (T2);
-- UPDATE (review) requires conduct:review at the owner unit.
ALTER TABLE conduct_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON conduct_actions FOR SELECT
    USING (authz_can(current_app_user(), 'conduct:view', officer_unit_id)
        OR authz_can(current_app_user(), 'conduct:view', owner_unit_id));
CREATE POLICY p_insert ON conduct_actions FOR INSERT
    WITH CHECK (authz_can(current_app_user(), 'conduct:submit', officer_unit_id));
CREATE POLICY p_update ON conduct_actions FOR UPDATE
    USING (authz_can(current_app_user(), 'conduct:review', owner_unit_id))
    WITH CHECK (authz_can(current_app_user(), 'conduct:review', owner_unit_id));

-- Vehicles: police fleet follows its assigned unit; civilian vehicles (unit_id NULL) are
-- plate-lookup data governed by the GLOBAL permission vehicle:lookup (no registry browsing).
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_select ON vehicles FOR SELECT
    USING (authz_can(current_app_user(), 'vehicle:view', unit_id)
        OR authz_has(current_app_user(), 'vehicle:lookup'));
CREATE POLICY p_insert ON vehicles FOR INSERT
    WITH CHECK (authz_can(current_app_user(), 'vehicle:create', unit_id)
        OR (unit_id IS NULL AND authz_has(current_app_user(), 'vehicle:create')));
CREATE POLICY p_update ON vehicles FOR UPDATE
    USING (authz_can(current_app_user(), 'vehicle:update_alert', unit_id)
        OR (unit_id IS NULL AND authz_has(current_app_user(), 'vehicle:update_alert')));

-- #############################################################################
-- PART 3 — REFERENCE DATA & OFFICIAL ORG TREE
-- #############################################################################

-- ---- unit types & structure rules ------------------------------------------
INSERT INTO unit_types (code, label, is_geographic, sort_order) VALUES
    ('hq',          'Police HQ / Command',     false, 0),
    ('directorate', 'National Directorate',    false, 1),
    ('bureau',      'Directorate Bureau',      false, 2),
    ('region',      'Region',                  true,  3),
    ('district',    'District',                true,  4),
    ('station',     'Police Station',          false, 5),
    ('checkpoint',  'Checkpoint',              false, 6),
    ('airport',     'Airport',                 false, 7);

INSERT INTO unit_type_rules (parent_type, child_type) VALUES
    ('hq','directorate'), ('hq','region'),
    ('directorate','bureau'), ('bureau','bureau'),
    ('region','district'), ('region','station'), ('region','checkpoint'), ('region','airport'),
    ('district','station'), ('district','checkpoint'), ('district','airport'),
    ('station','station'),  ('station','checkpoint');

-- ---- permissions ------------------------------------------------------------
INSERT INTO permissions (code, module, action, is_write, scope_kind, description) VALUES
 ('person:search',           'person',     'search',           false, 'global', 'Search the Central Person Registry'),
 ('person:create',           'person',     'create',           true,  'global', 'Create a person master record'),
 ('person:update',           'person',     'update',           true,  'global', 'Correct a person master record'),
 ('person:merge',            'person',     'merge',            true,  'global', 'Merge duplicate persons (national role only)'),
 ('alert:check',             'alert',      'check',            false, 'global', 'Learn only whether a person has an active alert'),
 ('vehicle:lookup',          'vehicle',    'lookup',           false, 'global', 'Plate / VIN lookup'),
 ('user:manage',             'user',       'manage',           true,  'global', 'Create / disable user accounts'),
 ('checkpoint:view',         'checkpoint', 'view',             false, 'unit',   NULL),
 ('checkpoint:create',       'checkpoint', 'create',           true,  'unit',   NULL),
 ('airport:view',            'airport',    'view',             false, 'unit',   NULL),
 ('airport:create',          'airport',    'create',           true,  'unit',   NULL),
 ('clearance:view',          'clearance',  'view',             false, 'unit',   NULL),
 ('clearance:create',        'clearance',  'create',           true,  'unit',   'File an application at a unit'),
 ('clearance:approve',       'clearance',  'approve',          true,  'unit',   'Approve / reject / sign — grant ONLY at the directorate node'),
 ('clearance:print',         'clearance',  'print',            true,  'unit',   NULL),
 ('clearance:override_review_lock','clearance','override_review_lock', true, 'unit', 'Bypass the review window (separation-of-duties decision, see blueprint §8)'),
 ('case:view',               'case',       'view',             false, 'unit',   NULL),
 ('case:create',             'case',       'create',           true,  'unit',   NULL),
 ('case:update',             'case',       'update',           true,  'unit',   NULL),
 ('alert:view_detail',       'alert',      'view_detail',      false, 'unit',   'Read suspect-alert details'),
 ('alert:create',            'alert',      'create',           true,  'unit',   NULL),
 ('incident:view',           'incident',   'view',             false, 'unit',   NULL),
 ('incident:create',         'incident',   'create',           true,  'unit',   NULL),
 ('officer:view',            'officer',    'view',             false, 'unit',   NULL),
 ('officer:create',          'officer',    'create',           true,  'unit',   NULL),
 ('officer:update',          'officer',    'update',           true,  'unit',   NULL),
 ('conduct:view',            'conduct',    'view',             false, 'unit',   NULL),
 ('conduct:submit',          'conduct',    'submit',           true,  'unit',   'File against officers in this unit''s subtree'),
 ('conduct:review',          'conduct',    'review',           true,  'unit',   'HR review desk'),
 ('vehicle:view',            'vehicle',    'view',             false, 'unit',   NULL),
 ('vehicle:create',          'vehicle',    'create',           true,  'unit',   NULL),
 ('vehicle:update_alert',    'vehicle',    'update_alert',     true,  'unit',   NULL),
 ('unit:view',               'unit',       'view',             false, 'unit',   NULL),
 ('unit:manage',             'unit',       'manage',           true,  'unit',   'Create / rename / move / deactivate units'),
 ('analytics:view',          'analytics',  'view',             false, 'unit',   'Aggregates for the scoped subtree'),
 ('assignment:manage',       'assignment', 'manage',           true,  'unit',   'Delegated admin, bounded by can_grant()'),
 ('audit:view',              'audit',      'view',             false, 'unit',   NULL);

-- ---- roles ------------------------------------------------------------------
INSERT INTO roles (code, name, is_read_only, is_system) VALUES
 ('system_admin',      'System Administrator',                 false, true),
 ('chief_commander',   'Chief Commander (HQ / Command)',       true,  true),
 ('regional_commander','Regional Commander',                   false, true),
 ('station_commander', 'Station Commander',                    false, true),
 ('station_officer',   'Station Officer',                      false, true),
 ('checkpoint_officer','Checkpoint Officer',                   false, true),
 ('airport_officer',   'Airport Control Officer',              false, true),
 ('fingerprint_officer','Fingerprint Directorate Officer',     false, true),
 ('cid_officer',       'CID Officer',                          false, true),
 ('hr_officer',        'HR Directorate Officer',               false, true),
 ('transport_officer', 'Transport Directorate Officer',        false, true),
 ('unit_admin',        'Delegated Unit Administrator',         false, true);

CREATE FUNCTION pg_temp.grant_perms(p_role text, p_perms text[]) RETURNS void LANGUAGE sql AS $$
    INSERT INTO role_permissions (role_id, permission_code)
    SELECT (SELECT id FROM roles WHERE code = p_role), unnest(p_perms)
$$;

-- system_admin: parity with the legacy SystemAdmin (everything). See §8: recommend splitting later.
INSERT INTO role_permissions (role_id, permission_code)
SELECT (SELECT id FROM roles WHERE code='system_admin'), code FROM permissions;

-- chief_commander: EVERY read permission, zero write permission (guard trigger enforces it).
INSERT INTO role_permissions (role_id, permission_code)
SELECT (SELECT id FROM roles WHERE code='chief_commander'), code FROM permissions WHERE NOT is_write;

SELECT pg_temp.grant_perms('checkpoint_officer',  ARRAY['person:search','person:create','alert:check','vehicle:lookup','checkpoint:view','checkpoint:create']);
SELECT pg_temp.grant_perms('airport_officer',     ARRAY['person:search','person:create','alert:check','airport:view','airport:create']);
SELECT pg_temp.grant_perms('station_officer',     ARRAY['person:search','person:create','alert:check','incident:view','incident:create','clearance:view','clearance:create']);
SELECT pg_temp.grant_perms('station_commander',   ARRAY['person:search','person:create','alert:check','incident:view','incident:create','clearance:view','clearance:create',
                                                         'officer:view','conduct:view','conduct:submit','unit:view','analytics:view','vehicle:view']);
SELECT pg_temp.grant_perms('regional_commander',  ARRAY['person:search','alert:check','incident:view','checkpoint:view','airport:view','clearance:view','officer:view',
                                                         'conduct:view','conduct:submit','unit:view','analytics:view','vehicle:view','assignment:manage','audit:view']);
SELECT pg_temp.grant_perms('fingerprint_officer', ARRAY['person:search','person:create','person:update','alert:check','clearance:view','clearance:create','clearance:approve','clearance:print']);
SELECT pg_temp.grant_perms('cid_officer',         ARRAY['person:search','person:create','alert:check','alert:view_detail','alert:create','case:view','case:create','case:update',
                                                         'incident:view','incident:create','analytics:view']);
SELECT pg_temp.grant_perms('hr_officer',          ARRAY['person:search','officer:view','officer:create','officer:update','conduct:view','conduct:review','unit:view','vehicle:view','analytics:view']);
SELECT pg_temp.grant_perms('transport_officer',   ARRAY['person:search','vehicle:lookup','vehicle:view','vehicle:create','vehicle:update_alert','unit:view']);
SELECT pg_temp.grant_perms('unit_admin',          ARRAY['unit:view','assignment:manage']);

-- ---- policy -----------------------------------------------------------------
INSERT INTO policy_settings (key, value, description) VALUES
 ('clearance.review_window_hours', '12', 'Standard officers cannot approve until created_at + N hours; override needs clearance:override_review_lock');

-- ---- org tree (data only!) ---------------------------------------------------
CREATE FUNCTION pg_temp.u(p_code text, p_name text, p_type text, p_parent text DEFAULT NULL,
                          p_service text DEFAULT NULL, p_status text DEFAULT 'active',
                          p_attrs jsonb DEFAULT '{}') RETURNS bigint LANGUAGE sql AS $$
    INSERT INTO org_units (parent_id, unit_type, code, name, service_key, status, attrs)
    VALUES ((SELECT id FROM org_units WHERE code = p_parent), p_type, p_code, p_name, p_service, p_status, p_attrs)
    RETURNING id
$$;

SELECT pg_temp.u('HQ',     'Police HQ / Command', 'hq');
-- national directorates (T3)
SELECT pg_temp.u('DIR-FP',  'Fingerprint & Clearance Directorate', 'directorate', 'HQ', 'fingerprint');
SELECT pg_temp.u('DIR-CID', 'Criminal Investigation Directorate',  'directorate', 'HQ', 'cid');
SELECT pg_temp.u('DIR-HR',  'HR Directorate (Registration Office)','directorate', 'HQ', 'hr');
SELECT pg_temp.u('DIR-TRN', 'Transport Directorate',               'directorate', 'HQ', 'transport');
-- regions: STRICTLY the three official regions under HQ (the legacy LOCATIONS constant, now rows)
SELECT pg_temp.u('SOOL',   'Sool',          'region', 'HQ');
SELECT pg_temp.u('SANAAG', 'Sanaag',        'region', 'HQ');
SELECT pg_temp.u('ETOG',   'East Togdheer', 'region', 'HQ');
-- districts
SELECT pg_temp.u('D-LAASCAANOOD','Laascaanood','district','SOOL');
SELECT pg_temp.u('D-CAYNABO','Caynabo','district','SOOL');
SELECT pg_temp.u('D-XUDUN','Xudun','district','SOOL');
SELECT pg_temp.u('D-TALEEX','Taleex','district','SOOL');
SELECT pg_temp.u('D-CEERIGAABO','Ceerigaabo','district','SANAAG');
SELECT pg_temp.u('D-CEEL-AFWEYN','Ceel Afweyn','district','SANAAG');
SELECT pg_temp.u('D-GARADAG','Garadag','district','SANAAG');
SELECT pg_temp.u('D-BADHAN','Badhan','district','SANAAG');
SELECT pg_temp.u('D-DHAHAR','Dhahar','district','SANAAG');
SELECT pg_temp.u('D-BURAO','Burao','district','ETOG');
SELECT pg_temp.u('D-OODWEYNE','Oodweyne','district','ETOG');
SELECT pg_temp.u('D-BUUHOODLE','Buuhoodle','district','ETOG');
-- stations (legacy seed; codes normalised to ST-nnn)
SELECT pg_temp.u('ST-001','Ceerigaabo Central Station','station','D-CEERIGAABO',NULL,'active','{"tier":"Regional HQ","cells":24}');
SELECT pg_temp.u('ST-002','Badhan Station',            'station','D-BADHAN',    NULL,'active','{"tier":"District HQ","cells":12}');
SELECT pg_temp.u('ST-003','Caynabo Station',           'station','D-CAYNABO',   NULL,'active','{"tier":"District HQ","cells":10}');
SELECT pg_temp.u('ST-004','Las Anod Station',          'station','D-LAASCAANOOD',NULL,'active','{"tier":"Regional HQ","cells":20}');
SELECT pg_temp.u('ST-005','Burao Station',             'station','D-BURAO',     NULL,'active','{"tier":"Regional HQ","cells":24}');
SELECT pg_temp.u('ST-006','Oodweyne Station',          'station','D-OODWEYNE',  NULL,'active','{"tier":"District HQ","cells":12}');
SELECT pg_temp.u('ST-007','Buuhoodle Station',         'station','D-BUUHOODLE', NULL,'active','{"tier":"Outpost","cells":6,"village":"Widh Widh"}');
SELECT pg_temp.u('ST-008','Adhi Cadeeye Outpost',      'station','D-LAASCAANOOD',NULL,'active','{"tier":"Checkpoint","cells":4,"village":"Adhi Cadeeye"}');
-- checkpoints: legacy South/East/West had NO parent district. PLACEHOLDER parent below
-- (Laascaanood) — ops must confirm the real location and call move_unit(). attrs flags it.
SELECT pg_temp.u('CP-SOUTH','South Checkpoint','checkpoint','D-LAASCAANOOD',NULL,'active','{"needs_relocation_review":true}');
SELECT pg_temp.u('CP-EAST', 'East Checkpoint', 'checkpoint','D-LAASCAANOOD',NULL,'active','{"needs_relocation_review":true}');
SELECT pg_temp.u('CP-WEST', 'West Checkpoint', 'checkpoint','D-LAASCAANOOD',NULL,'active','{"needs_relocation_review":true}');
-- Airport: the seeded active airport is placed in Sool / Laascaanood (operational HQ district).
-- PLACEHOLDER placement: ops must confirm the airport's real district; correct it with
-- SELECT move_unit(<airport>, <district>). Scope follows the move automatically.
SELECT pg_temp.u('AP-LAA','Laascaanood Airport','airport','D-LAASCAANOOD',NULL,'active','{"needs_relocation_review":true}');

INSERT INTO schema_migrations (version, name) VALUES ('001', 'initial_schema');
