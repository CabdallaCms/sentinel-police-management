-- =============================================================================
-- Migration 002 — Person identity: smart-search keys + field-level immutability
-- Northeastern Police System (unified platform)
--
-- Requires: 001_initial_schema.sql.  Apply inside ONE transaction. No extensions.
--
-- WHAT THIS ADDS
--   1. Matching support on the global `persons` registry: normalisation functions,
--      trigger-maintained name tokens / prefix keys (GIN-indexed) so fuzzy candidate
--      search never scans the whole table, and place_of_birth (a legacy column that
--      Migration 001 omitted).
--   2. FIELD-LEVEL IMMUTABILITY, enforced in the database so no code path can bypass it:
--        core        first/second/third/fourth name, date_of_birth, place_of_birth
--        identifier  national_id, passport_id
--        protected   mother_name
--        dynamic     phone, residence (address), occupation, photo_path
--      A BLANK field may be filled once by anyone who can create persons (profile
--      enrichment). A NON-BLANK field may only be changed with the permission named in
--      `person_field_policy`. Core and identifier changes need `person:edit_core`, which
--      is honoured ONLY for an assignment at the root (HQ) unit — the National Admin —
--      and always requires a recorded reason.
--   3. `person_guardians`: guardians are persons too; the link is append-only enrichment.
--   4. Every change is written to the append-only `person_field_audit`.
--
-- Fail-closed: a write with no authenticated user (app.user_id unset) is rejected.
-- Bulk imports / back-fills must opt in explicitly with
--     SELECT set_config('sentinel.maintenance', 'on', true);
-- (transaction-local; audited with user_id NULL).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Normalisation + matching columns
-- ---------------------------------------------------------------------------
-- Names: lower-case, punctuation/whitespace collapsed to single spaces. [:punct:] (not
-- [:alnum:]) is used so non-ASCII letters (e.g. Arabic-script names) are preserved.
CREATE FUNCTION norm_text(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(btrim(regexp_replace(lower(coalesce(t, '')), '[[:space:][:punct:]]+', ' ', 'g')), '')
$$;

-- Identifiers: upper-case, all whitespace/punctuation removed ('so 123-45' = 'SO12345').
CREATE FUNCTION norm_ident(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(upper(regexp_replace(coalesce(t, ''), '[[:space:][:punct:]]+', '', 'g')), '')
$$;

-- 3-character prefix keys: the extension-free substitute for trigram candidate search.
CREATE FUNCTION name_key_array(tokens text[]) RETURNS text[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(DISTINCT left(t, 3)), '{}') FROM unnest(tokens) AS t
$$;

CREATE FUNCTION person_is_empty(v text) RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT v IS NULL OR btrim(v) = ''
$$;

ALTER TABLE persons
    ADD COLUMN place_of_birth text,
    ADD COLUMN name_tokens    text[] NOT NULL DEFAULT '{}',   -- trigger-maintained
    ADD COLUMN name_keys      text[] NOT NULL DEFAULT '{}',   -- trigger-maintained
    ADD COLUMN mother_norm    text;                           -- trigger-maintained

CREATE INDEX ix_persons_name_keys  ON persons USING gin (name_keys);
CREATE INDEX ix_persons_dob        ON persons (date_of_birth);
CREATE INDEX ix_persons_mother     ON persons (mother_norm);
-- National ID / passport are unique after normalisation ('so-123' and 'SO123' collide).
CREATE UNIQUE INDEX ux_persons_nid_norm  ON persons (norm_ident(national_id)) WHERE national_id IS NOT NULL;
CREATE UNIQUE INDEX ux_persons_pass_norm ON persons (norm_ident(passport_id)) WHERE passport_id IS NOT NULL;
-- Live "type the start of an ID" lookups (LIKE 'abc%') without a table scan, in any collation.
CREATE INDEX ix_persons_nid_prefix  ON persons (norm_ident(national_id) text_pattern_ops);
CREATE INDEX ix_persons_pass_prefix ON persons (norm_ident(passport_id) text_pattern_ops);

-- ---------------------------------------------------------------------------
-- 2. Field policy (DATA, so rules can be tuned without a deploy)
-- ---------------------------------------------------------------------------
INSERT INTO permissions (code, module, action, is_write, scope_kind, description) VALUES
 ('person:update_dynamic', 'person', 'update_dynamic', true, 'global',
  'Update dynamic profile fields (address, phone, occupation, photo)'),
 ('person:edit_core',      'person', 'edit_core',      true, 'global',
  'Change locked core-identity fields (names, DoB, PoB, IDs). National Admin only: honoured at the root unit');

UPDATE permissions SET description = 'Correct a locked, non-core profile field (e.g. mother''s name)'
 WHERE code = 'person:update';

-- Every role that can create a person may also maintain the dynamic fields.
INSERT INTO role_permissions (role_id, permission_code)
SELECT rp.role_id, 'person:update_dynamic'
  FROM role_permissions rp
 WHERE rp.permission_code = 'person:create';

-- The National Admin (system_admin at HQ) holds the new permissions explicitly.
INSERT INTO role_permissions (role_id, permission_code)
SELECT r.id, p.code FROM roles r, permissions p
 WHERE r.code = 'system_admin' AND p.code IN ('person:edit_core', 'person:update_dynamic')
ON CONFLICT DO NOTHING;

CREATE TABLE person_field_policy (
    field         text PRIMARY KEY,
    mutability    text    NOT NULL CHECK (mutability IN ('core', 'identifier', 'protected', 'dynamic')),
    fill_perm     text    NOT NULL REFERENCES permissions(code),   -- fill a BLANK field
    change_perm   text    NOT NULL REFERENCES permissions(code),   -- change a NON-BLANK field
    national_only boolean NOT NULL DEFAULT false,                  -- change_perm must be held at the ROOT unit
    needs_reason  boolean NOT NULL DEFAULT false,                  -- a change must carry a reason
    label         text    NOT NULL
);
INSERT INTO person_field_policy (field, mutability, fill_perm, change_perm, national_only, needs_reason, label) VALUES
 ('first_name',    'core',       'person:create', 'person:edit_core',      true,  true,  'First name'),
 ('second_name',   'core',       'person:create', 'person:edit_core',      true,  true,  'Second name'),
 ('third_name',    'core',       'person:create', 'person:edit_core',      true,  true,  'Third name'),
 ('fourth_name',   'core',       'person:create', 'person:edit_core',      true,  true,  'Fourth name'),
 ('date_of_birth', 'core',       'person:create', 'person:edit_core',      true,  true,  'Date of birth'),
 ('place_of_birth','core',       'person:create', 'person:edit_core',      true,  true,  'Place of birth'),
 ('full_name',     'core',       'person:create', 'person:edit_core',      true,  true,  'Full name'),      -- only enforced when no name parts exist
 ('national_id',   'identifier', 'person:create', 'person:edit_core',      true,  true,  'National ID'),
 ('passport_id',   'identifier', 'person:create', 'person:edit_core',      true,  true,  'Passport ID'),
 ('mother_name',   'protected',  'person:create', 'person:update',         false, false, 'Mother''s name'),
 ('phone',         'dynamic',    'person:create', 'person:update_dynamic', false, false, 'Phone'),
 ('residence',     'dynamic',    'person:create', 'person:update_dynamic', false, false, 'Address'),
 ('occupation',    'dynamic',    'person:create', 'person:update_dynamic', false, false, 'Occupation'),
 ('photo_path',    'dynamic',    'person:create', 'person:update_dynamic', false, false, 'Photo');

-- One permission check used by the trigger AND the API (so they cannot disagree).
CREATE FUNCTION person_perm_ok(p_user bigint, p_perm text, p_national boolean) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p_user IS NULL THEN false
        WHEN p_national     THEN authz_can(p_user, p_perm, (SELECT id FROM org_units WHERE parent_id IS NULL))
        ELSE                     authz_has(p_user, p_perm)
    END
$$;

-- What may THIS user do to each field of THIS person?  locked | fillable | editable
CREATE FUNCTION person_field_states(p_user bigint, p_person bigint)
RETURNS TABLE (field text, mutability text, label text, state text)
LANGUAGE sql STABLE AS $$
    SELECT pol.field, pol.mutability, pol.label,
           CASE WHEN NOT person_is_empty(to_jsonb(p) ->> pol.field)
                THEN CASE WHEN person_perm_ok(p_user, pol.change_perm, pol.national_only) THEN 'editable' ELSE 'locked' END
                ELSE CASE WHEN person_perm_ok(p_user, pol.fill_perm, false)               THEN 'fillable' ELSE 'locked' END
           END
      FROM person_field_policy pol
      JOIN persons p ON p.id = p_person
     WHERE pol.field <> 'full_name'
$$;

-- ---------------------------------------------------------------------------
-- 3. Audit + guard
-- ---------------------------------------------------------------------------
ALTER TABLE person_field_audit
    ADD COLUMN kind   text NOT NULL DEFAULT 'change' CHECK (kind IN ('fill', 'change')),
    ADD COLUMN reason text;
CREATE INDEX ix_pfa_person ON person_field_audit (person_id, at DESC);

CREATE FUNCTION person_field_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'person_field_audit is append-only'; END $$;
CREATE TRIGGER trg_pfa_immutable BEFORE UPDATE OR DELETE ON person_field_audit
    FOR EACH ROW EXECUTE FUNCTION person_field_audit_immutable();

CREATE FUNCTION persons_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    uid    bigint  := current_app_user();
    maint  boolean := coalesce(current_setting('sentinel.maintenance', true), 'off') = 'on';
    unit   bigint  := NULLIF(current_setting('app.unit_id', true), '')::bigint;
    why    text    := NULLIF(btrim(coalesce(current_setting('app.change_reason', true), '')), '');
    pol    record;
    o      text;
    n      text;
    oj     jsonb;
    nj     jsonb;
    is_fill boolean;
    parts  boolean;
BEGIN
    -- ---- normalise (so whitespace / case noise is never a "change") ------------------
    NEW.first_name     := NULLIF(btrim(NEW.first_name), '');
    NEW.second_name    := NULLIF(btrim(NEW.second_name), '');
    NEW.third_name     := NULLIF(btrim(NEW.third_name), '');
    NEW.fourth_name    := NULLIF(btrim(NEW.fourth_name), '');
    NEW.place_of_birth := NULLIF(btrim(NEW.place_of_birth), '');
    NEW.mother_name    := NULLIF(btrim(NEW.mother_name), '');
    NEW.phone          := NULLIF(btrim(NEW.phone), '');
    NEW.residence      := NULLIF(btrim(NEW.residence), '');
    NEW.occupation     := NULLIF(btrim(NEW.occupation), '');
    NEW.photo_path     := NULLIF(btrim(NEW.photo_path), '');
    NEW.national_id    := NULLIF(upper(btrim(NEW.national_id)), '');
    NEW.passport_id    := NULLIF(upper(btrim(NEW.passport_id)), '');

    -- ---- derived columns -------------------------------------------------------------
    parts := NEW.first_name IS NOT NULL OR NEW.second_name IS NOT NULL
          OR NEW.third_name IS NOT NULL OR NEW.fourth_name IS NOT NULL;
    IF parts THEN
        NEW.full_name := concat_ws(' ', NEW.first_name, NEW.second_name, NEW.third_name, NEW.fourth_name);
    ELSE
        NEW.full_name := btrim(coalesce(NEW.full_name, ''));
    END IF;
    NEW.name_tokens := coalesce(string_to_array(norm_text(NEW.full_name), ' '), '{}');
    NEW.name_keys   := name_key_array(NEW.name_tokens);
    NEW.mother_norm := norm_text(NEW.mother_name);

    -- ---- INSERT ------------------------------------------------------------------------
    IF TG_OP = 'INSERT' THEN
        IF NOT maint AND NOT person_perm_ok(uid, 'person:create', false) THEN
            RAISE EXCEPTION 'creating a person requires an authenticated user holding person:create'
                USING ERRCODE = '42501';
        END IF;
        IF uid IS NOT NULL THEN NEW.created_by := uid; END IF;
        NEW.created_in_unit_id := coalesce(NEW.created_in_unit_id, unit);
        NEW.updated_at := now();
        RETURN NEW;
    END IF;

    -- ---- UPDATE ------------------------------------------------------------------------
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.person_ref IS DISTINCT FROM OLD.person_ref
       OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_in_unit_id IS DISTINCT FROM OLD.created_in_unit_id THEN
        RAISE EXCEPTION 'person id, reference and provenance are immutable (even for administrators)'
            USING ERRCODE = '42501';
    END IF;

    oj := to_jsonb(OLD);
    nj := to_jsonb(NEW);
    FOR pol IN SELECT * FROM person_field_policy ORDER BY field LOOP
        CONTINUE WHEN pol.field = 'full_name' AND parts;          -- derived from the (checked) parts
        o := oj ->> pol.field;
        n := nj ->> pol.field;
        CONTINUE WHEN o IS NOT DISTINCT FROM n;

        is_fill := person_is_empty(o);
        IF NOT maint AND NOT person_perm_ok(uid,
                CASE WHEN is_fill THEN pol.fill_perm ELSE pol.change_perm END,
                (NOT is_fill) AND pol.national_only) THEN
            RAISE EXCEPTION '% is locked: it is already registered and % can change it',
                    pol.label, CASE WHEN pol.national_only THEN 'only the National Admin' ELSE 'your role cannot' END
                USING ERRCODE = '42501', COLUMN = pol.field,
                      HINT = pol.mutability;
        END IF;
        IF NOT is_fill AND pol.needs_reason AND why IS NULL AND NOT maint THEN
            RAISE EXCEPTION 'a reason is required to change % after registration', pol.label
                USING ERRCODE = '23514', COLUMN = pol.field;
        END IF;

        INSERT INTO person_field_audit (person_id, field, old_value, new_value, user_id, unit_id, kind, reason)
        VALUES (OLD.id, pol.field, o, n, uid, unit, CASE WHEN is_fill THEN 'fill' ELSE 'change' END,
                CASE WHEN is_fill THEN NULL ELSE why END);
    END LOOP;
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE TRIGGER trg_persons_guard BEFORE INSERT OR UPDATE ON persons
    FOR EACH ROW EXECUTE FUNCTION persons_guard();

-- No physical deletes of master records through the application path.
CREATE FUNCTION persons_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('sentinel.maintenance', true), 'off') <> 'on' THEN
        RAISE EXCEPTION 'persons cannot be deleted; merge duplicates instead' USING ERRCODE = '42501';
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER trg_persons_no_delete BEFORE DELETE ON persons
    FOR EACH ROW EXECUTE FUNCTION persons_no_delete();

-- ---------------------------------------------------------------------------
-- 4. Guardians: a guardian is a person; the link is append-only profile enrichment
-- ---------------------------------------------------------------------------
CREATE TABLE person_guardians (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id          bigint NOT NULL REFERENCES persons(id),
    guardian_person_id bigint NOT NULL REFERENCES persons(id),
    relationship       text,
    added_by           bigint REFERENCES users(id),
    added_in_unit_id   bigint REFERENCES org_units(id),   -- provenance only, grants nothing
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (person_id <> guardian_person_id),
    UNIQUE (person_id, guardian_person_id)
);
CREATE INDEX ix_pg_guardian ON person_guardians (guardian_person_id);

CREATE FUNCTION person_guardians_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    uid   bigint  := current_app_user();
    maint boolean := coalesce(current_setting('sentinel.maintenance', true), 'off') = 'on';
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NOT maint AND NOT person_perm_ok(uid, 'person:create', false) THEN
            RAISE EXCEPTION 'adding a guardian requires an authenticated user holding person:create'
                USING ERRCODE = '42501';
        END IF;
        NEW.relationship := NULLIF(btrim(NEW.relationship), '');
        IF uid IS NOT NULL THEN NEW.added_by := uid; END IF;
        NEW.added_in_unit_id := coalesce(NEW.added_in_unit_id,
                                         NULLIF(current_setting('app.unit_id', true), '')::bigint);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.person_id <> OLD.person_id OR NEW.guardian_person_id <> OLD.guardian_person_id
           OR NEW.created_at <> OLD.created_at OR NEW.added_by IS DISTINCT FROM OLD.added_by THEN
            RAISE EXCEPTION 'a guardian link cannot be re-pointed' USING ERRCODE = '42501';
        END IF;
        NEW.relationship := NULLIF(btrim(NEW.relationship), '');
        -- the relationship may be filled once; correcting it afterwards needs person:update
        IF NEW.relationship IS DISTINCT FROM OLD.relationship AND NOT person_is_empty(OLD.relationship)
           AND NOT maint AND NOT person_perm_ok(uid, 'person:update', false) THEN
            RAISE EXCEPTION 'guardian relationship is already recorded' USING ERRCODE = '42501';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT maint THEN
        RAISE EXCEPTION 'guardian links are append-only' USING ERRCODE = '42501';
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER trg_person_guardians_guard BEFORE INSERT OR UPDATE OR DELETE ON person_guardians
    FOR EACH ROW EXECUTE FUNCTION person_guardians_guard();

INSERT INTO schema_migrations (version, name) VALUES ('002', 'person_identity');
