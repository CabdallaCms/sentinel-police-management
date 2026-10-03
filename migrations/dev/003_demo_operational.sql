-- =============================================================================
-- DEV / DEMO ONLY — never apply to production.
-- Operational-unit demo data for Phase 2.  Requires 001 + 002 + 003 and dev/001_demo_accounts.sql.
--
-- 1. A DATA-ONLY expansion of the org tree: Buuhoodle Airport under the Buuhoodle district
--    (East Togdheer).  No schema or code change is needed for a new airport — it is an INSERT into
--    org_units plus a role assignment; every record rule (region scope, RLS, append-only, active-unit)
--    applies automatically.  The code, name and status are placeholders for the Chief Commander to confirm.
-- 2. Station accounts (the legacy demo set had none) and two desk officers.
-- =============================================================================
INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs)
VALUES ((SELECT id FROM org_units WHERE code = 'D-BUUHOODLE'), 'airport', 'AP-BUU', 'Buuhoodle Airport', 'active',
        '{"needs_confirmation": true}');

INSERT INTO users (username, display_name, password_hash) VALUES
 ('ap.buuhoodle', 'Officer C. Jaamac (Buuhoodle Airport)', '!seed'),
 ('st.laas',      'Officer K. Diiriye (Las Anod Station)',   '!seed'),
 ('st.buuhoodle', 'Officer Z. Faarax (Buuhoodle Station)',   '!seed'),
 ('rc.sool',      'Col. I. Aadan (Sool Regional Commander)', '!seed');

CREATE FUNCTION pg_temp.assign_op(p_user text, p_role text, p_unit text, p_desc boolean DEFAULT true) RETURNS void LANGUAGE sql AS $$
    INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants)
    VALUES ((SELECT id FROM users WHERE username = p_user),
            (SELECT id FROM roles WHERE code = p_role),
            (SELECT id FROM org_units WHERE code = p_unit), p_desc)
$$;
SELECT pg_temp.assign_op('ap.buuhoodle', 'airport_officer',    'AP-BUU',  false);
SELECT pg_temp.assign_op('st.laas',      'station_officer',    'ST-004',  false);
SELECT pg_temp.assign_op('st.buuhoodle', 'station_officer',    'ST-007',  false);
SELECT pg_temp.assign_op('rc.sool',      'regional_commander', 'SOOL');

INSERT INTO officers (service_ref, unit_id, rank, unit_role, full_name) VALUES
 ('OFF-DEMO-001', (SELECT id FROM org_units WHERE code = 'ST-004'), 'Sergeant',  'Front Desk', 'Sgt. Mahad Cismaan'),
 ('OFF-DEMO-002', (SELECT id FROM org_units WHERE code = 'ST-007'), 'Inspector', 'Front Desk', 'Insp. Hodan Saciid');

-- 3. One fictional active alert, so the checkpoint "FLAGGED MATCH" screen can be seen in the demo.
SELECT set_config('sentinel.maintenance', 'on', true);          -- seed data has no authenticated author
INSERT INTO suspect_alerts (alert_ref, person_id, notes)
SELECT next_ref('AL'), id, 'DEMO ONLY — fictional alert'
  FROM persons WHERE national_id = 'SO-100004';
SELECT set_config('sentinel.maintenance', 'off', true);
