-- =============================================================================
-- DEV / DEMO ONLY — never apply to production.
-- Phase 3 demo data.  Requires 001–004 and the earlier dev seeds (accounts, persons, operational).
--
--  1. DATA-ONLY branch expansion (no code change): a CID bureau for Sool and a Fingerprint intake bureau
--     for Sanaag, each claiming its region through attrs.region (validated by the database).
--  2. Accounts: station commander, CID Sool bureau, Sanaag fingerprint intake, second HR reviewer.
--  3. One Pending clearance application aged 13 h (so the 12 h window has already passed and the
--     approve / sign / print flow can be shown), one CID case with a suspect, two filed conduct files.
-- All people are fictional.  Helper names are prefixed p3_ (all seed files share one session).
-- =============================================================================
INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs) VALUES
 ((SELECT id FROM org_units WHERE code = 'DIR-CID'), 'bureau', 'BR-CID-SOOL',   'CID Sool Bureau',                'active', '{"region": "SOOL"}'),
 ((SELECT id FROM org_units WHERE code = 'DIR-FP'),  'bureau', 'BR-FP-SANAAG',  'Fingerprint Intake — Sanaag',    'active', '{"region": "SANAAG"}');

INSERT INTO users (username, display_name, password_hash) VALUES
 ('cmd.laas',   'Maj. B. Nuur (Las Anod Station Commander)',  '!seed'),
 ('cid.sool',   'Officer W. Ismaaciil (CID Sool Bureau)',     '!seed'),
 ('fp.sanaag',  'Officer R. Axmed (Fingerprint Intake, Sanaag)', '!seed'),
 ('hr.reviewer','Officer D. Cumar (HR Second Reviewer)',      '!seed');

CREATE FUNCTION pg_temp.p3_assign(p_user text, p_role text, p_unit text, p_desc boolean DEFAULT true) RETURNS void LANGUAGE sql AS $$
    INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants)
    VALUES ((SELECT id FROM users WHERE username = p_user), (SELECT id FROM roles WHERE code = p_role),
            (SELECT id FROM org_units WHERE code = p_unit), p_desc)
$$;
SELECT pg_temp.p3_assign('cmd.laas',    'station_commander',  'ST-004', false);
SELECT pg_temp.p3_assign('cid.sool',    'cid_officer',        'BR-CID-SOOL');
SELECT pg_temp.p3_assign('fp.sanaag',   'fingerprint_officer','BR-FP-SANAAG');
SELECT pg_temp.p3_assign('hr.reviewer', 'hr_officer',         'DIR-HR');

SELECT set_config('sentinel.maintenance', 'on', true);           -- seed data has no authenticated author
INSERT INTO clearance_applications (application_ref, person_id, intake_unit_id, purpose, details, created_by, created_at)
SELECT next_ref('FP', 'ST-004'), p.id, (SELECT id FROM org_units WHERE code = 'ST-004'), 'Travel',
       '{"notes": "DEMO ONLY — fictional application"}'::jsonb, (SELECT id FROM users WHERE username = 'st.laas'),
       now() - interval '13 hours'
  FROM persons p WHERE p.national_id = 'SO-100001';

INSERT INTO crime_cases (case_ref, owner_unit_id, category, status, incident_summary, location, created_by)
VALUES (next_ref('CS', 'BR-CID-SOOL'), (SELECT id FROM org_units WHERE code = 'BR-CID-SOOL'), 'Theft', 'Under Investigation',
        'DEMO ONLY — fictional case: livestock theft reported near Laascaanood.', 'Laascaanood',
        (SELECT id FROM users WHERE username = 'cid.sool'));

INSERT INTO conduct_actions (action_ref, officer_id, officer_unit_id, action_type, classification, proposed_rank, narrative,
                             submitted_by, submitted_unit_id, status)
SELECT next_ref('ACT'), o.id, o.unit_id, 'Promotion / Commendation', 'Rank Advancement', 'Inspector',
       'DEMO ONLY — consistently exemplary service and leadership of the front desk over the past year.',
       (SELECT id FROM users WHERE username = 'cmd.laas'), o.unit_id, 'Submitted to HR'
  FROM officers o WHERE o.service_ref = 'OFF-DEMO-001';
SELECT set_config('sentinel.maintenance', 'off', true);
