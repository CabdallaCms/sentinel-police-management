-- =============================================================================
-- DEV / DEMO ONLY — never apply to production.  Fictional people for trying out
-- the Central Person search and the "already exists" banner.
-- Requires migrations 001 + 002. Imported without a user, hence the explicit opt-in.
-- =============================================================================
SELECT set_config('sentinel.maintenance', 'on', true);

-- Fully completed profile (every field present)
INSERT INTO persons (person_ref, first_name, second_name, third_name, fourth_name, full_name, date_of_birth,
                     place_of_birth, national_id, mother_name, phone, residence, occupation, created_in_unit_id)
VALUES (next_ref('P'), 'Ayaan', 'Cabdi', 'Xasan', 'Axmed', '', '1990-05-17', 'Laascaanood', 'SO-100001',
        'Hodan Cali Faarax', '+252 63 400 0001', 'Laascaanood, Xero Awr', 'Teacher',
        (SELECT id FROM org_units WHERE code = 'DIR-FP'));

-- Incomplete profile (mother's name, address, phone, occupation still to be enriched at a later visit)
INSERT INTO persons (person_ref, first_name, second_name, third_name, fourth_name, full_name, date_of_birth,
                     place_of_birth, passport_id, created_in_unit_id)
VALUES (next_ref('P'), 'Nuur', 'Faarax', 'Cali', 'Yuusuf', '', '1985-01-01', 'Burao', 'A1234567',
        (SELECT id FROM org_units WHERE code = 'AP-LAA'));

-- A minor registered without any ID and WITHOUT a guardian yet (to be added at another unit)
INSERT INTO persons (person_ref, first_name, second_name, third_name, full_name, date_of_birth, place_of_birth,
                     mother_name, created_in_unit_id)
VALUES (next_ref('P'), 'Hodan', 'Nuur', 'Cali', '', (current_date - interval '8 years')::date, 'Ceerigaabo',
        'Faadumo Maxamed', (SELECT id FROM org_units WHERE code = 'DIR-FP'));

INSERT INTO persons (person_ref, first_name, second_name, third_name, fourth_name, full_name, date_of_birth,
                     place_of_birth, national_id, mother_name, residence, occupation, created_in_unit_id)
VALUES (next_ref('P'), 'Cabdiraxmaan', 'Maxamed', 'Jaamac', 'Warsame', '', '1978-11-23', 'Ceel Afweyn', 'SO-100004',
        'Faadumo Axmed', 'Burao', 'Trader', (SELECT id FROM org_units WHERE code = 'CP-SOUTH'));
