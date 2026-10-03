-- =============================================================================
-- DEV / DEMO ONLY — never apply to production.
-- The nine legacy demo accounts, mapped to unit assignments (blueprint §3.2).
-- Placeholder password hash '!seed' cannot authenticate; set real hashes in the app.
-- Requires migrations/001_initial_schema.sql. Apply in one session (uses pg_temp).
-- =============================================================================

INSERT INTO users (username, display_name, password_hash) VALUES
 ('admin','Officer A. Hassan','!seed'), ('fp.officer','Officer H. Xasan','!seed'),
 ('ap.officer','Officer S. Cabdi','!seed'), ('cid.officer','Officer M. Nuur','!seed'),
 ('hr.officer','Officer S. Warsame','!seed'), ('cp.south','Officer F. Cali','!seed'),
 ('cp.east','Officer A. Maxamed','!seed'), ('cp.west','Officer N. Yuusuf','!seed'),
 ('chief','Gen. C. Warsame','!seed');

CREATE FUNCTION pg_temp.assign(p_user text, p_role text, p_unit text, p_desc boolean DEFAULT true) RETURNS void LANGUAGE sql AS $$
    INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants)
    VALUES ((SELECT id FROM users WHERE username = p_user),
            (SELECT id FROM roles WHERE code = p_role),
            (SELECT id FROM org_units WHERE code = p_unit), p_desc)
$$;
SELECT pg_temp.assign('admin',      'system_admin',       'HQ');
SELECT pg_temp.assign('chief',      'chief_commander',    'HQ');            -- D2: root, read-only, inherits all
SELECT pg_temp.assign('fp.officer', 'fingerprint_officer','DIR-FP');
SELECT pg_temp.assign('cid.officer','cid_officer',        'DIR-CID');
SELECT pg_temp.assign('hr.officer', 'hr_officer',         'DIR-HR');
SELECT pg_temp.assign('ap.officer', 'airport_officer',    'AP-LAA', false);  -- legacy was global; only one airport existed
SELECT pg_temp.assign('cp.south',   'checkpoint_officer', 'CP-SOUTH', false);
SELECT pg_temp.assign('cp.east',    'checkpoint_officer', 'CP-EAST',  false);
SELECT pg_temp.assign('cp.west',    'checkpoint_officer', 'CP-WEST',  false);
