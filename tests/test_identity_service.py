"""Service-level tests: smart search, register-or-link, strict profile updates, guardians."""
import threading
import unittest
from datetime import date, timedelta

import psycopg2

from app.db import Actor
from app.identity import registry
from app.identity.errors import (FieldLocked, IdentifierInUse, NeedsConfirmation, NotFound, PermissionDenied,
                                 ValidationError)
from .base import DbCase

AYAAN = dict(first_name='Ayaan', second_name='Cabdi', third_name='Xasan', fourth_name='Axmed',
             date_of_birth='1990-05-17', place_of_birth='Laascaanood', national_id='SO1001',
             mother_name='Hodan Cali')


NUUR = dict(first_name='Nuur', second_name='Faarax', third_name='Cali', fourth_name='Yuusuf',
            date_of_birth='1985-01-01', place_of_birth='Burao', national_id='SO2002', mother_name=None)


class Service(DbCase):
    DBNAME = 'sentinel_identity_service'

    def seed(self, who='fp.officer', unit='DIR-FP', **over):
        return registry.register(self.conn, self.actor(who, unit), {**AYAAN, **over})

    def search(self, who='ap.officer', unit='AP-LAA', **q):
        return registry.search(self.conn, self.actor(who, unit), query=q)

    def count(self):
        return self.one('SELECT count(*) FROM persons')


class TestSmartSearch(Service):
    def test_exact_national_id_reports_that_the_master_profile_already_exists(self):
        self.seed()
        r = self.search(national_id=' so-1001 ')                       # case / punctuation / spacing insensitive
        self.assertEqual((r['status'], r['exists'], r['tier'], r['auto_select']), ('exists', True, 1, True))
        self.assertEqual(r['person']['full_name'], 'Ayaan Cabdi Xasan Axmed')
        self.assertEqual(r['person']['registered_at']['code'], 'DIR-FP')
        self.assertIn('Exact', r['reason'])

    def test_exact_passport_also_matches(self):
        self.seed(national_id=None, passport_id='A1234567')
        self.assertEqual(self.search(passport_id='a 1234567')['tier'], 1)

    def test_name_and_dob_is_a_high_confidence_match_without_any_id(self):
        self.seed()
        r = self.search(first_name='ayaan', second_name='CABDI', third_name='xasan', fourth_name='axmed',
                        date_of_birth='1990-05-17')
        self.assertEqual((r['status'], r['tier']), ('exists', 2))

    def test_typo_with_matching_mother_is_a_warning_to_confirm_not_an_auto_link(self):
        self.seed()
        r = self.search(first_name='Ayaan', second_name='Cabdii', third_name='Xasan', fourth_name='Ahmed',
                        mother_name='hodan cali')
        self.assertEqual((r['status'], r['exists'], r['tier'], r['auto_select']), ('confirm', False, 3, False))
        self.assertEqual(r['person']['person_ref'], self.seed()['person']['person_ref'])

    def test_partial_input_returns_suggestions_for_the_dropdown(self):
        self.seed()
        r = self.search(first_name='Ayaan', second_name='Cabdi')
        self.assertEqual(r['status'], 'suggestions')
        self.assertEqual(r['candidates'][0]['full_name'], 'Ayaan Cabdi Xasan Axmed')

    def test_unknown_person_is_new(self):
        self.seed()
        r = self.search(first_name='Zeynab', second_name='Warsame', third_name='Nuur', date_of_birth='2000-01-01',
                        national_id='SO7777')
        self.assertEqual((r['status'], r['exists'], r['candidates']), ('new', False, []))

    def test_free_text_box_understands_person_id_national_id_and_names(self):
        ref = self.seed()['person']['person_ref']
        a = self.actor('ap.officer', 'AP-LAA')
        self.assertEqual(registry.search(self.conn, a, q=ref.lower())['tier'], 1)
        self.assertEqual(registry.search(self.conn, a, q='so1001')['status'], 'exists')
        self.assertEqual(registry.search(self.conn, a, q='SO10')['status'], 'suggestions')      # typing an ID prefix
        self.assertEqual(registry.search(self.conn, a, q='cabdi ayaan')['candidates'][0]['person_ref'], ref)

    def test_id_match_with_different_stored_dob_reports_the_disagreement_not_a_silent_overwrite(self):
        self.seed()
        r = self.search(national_id='SO1001', first_name='Ayaan', second_name='Cabdi', third_name='Xasan',
                        date_of_birth='1991-05-17')
        self.assertTrue(r['exists'])
        self.assertEqual([(d['field'], d['stored'], d['entered']) for d in r['core_differences']],
                         [('date_of_birth', '1990-05-17', '1991-05-17')])

    def test_conflict_when_the_id_and_the_name_point_at_different_people(self):
        self.seed()
        self.seed(**NUUR)
        r = self.search(national_id='SO1001', first_name='Nuur', second_name='Faarax', third_name='Cali',
                        fourth_name='Yuusuf', date_of_birth='1985-01-01')
        self.assertEqual(r['conflicts'][0]['code'], 'name_dob_other_person')

    def test_field_states_in_the_result_tell_the_ui_what_to_lock_for_this_officer(self):
        self.seed()
        r = self.search(national_id='SO1001')
        st = r['person']['field_states']
        self.assertEqual(st['first_name']['state'], 'locked')
        self.assertEqual(st['date_of_birth']['state'], 'locked')
        self.assertEqual(st['residence']['state'], 'fillable')
        self.assertEqual(st['occupation']['state'], 'fillable')
        admin = registry.search(self.conn, self.actor('admin', 'HQ'), query={'national_id': 'SO1001'})
        self.assertEqual(admin['person']['field_states']['first_name']['state'], 'editable')

    def test_missing_fields_drive_the_enrichment_prompt(self):
        self.seed()
        miss = {m['field'] for m in self.search(national_id='SO1001')['person']['missing_fields']}
        self.assertTrue({'residence', 'phone', 'occupation', 'photo_path'} <= miss)
        self.assertNotIn('mother_name', miss)

    def test_alert_flag_is_yes_no_only_and_only_for_roles_that_may_check(self):
        ref = self.seed()['person']['person_ref']
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("RESET ROLE")          # fixture seeding is done as the owner, not as an app user
        self.cur.execute("INSERT INTO suspect_alerts(alert_ref, person_id) SELECT 'AL-1', id FROM persons WHERE person_ref=%s", (ref,))
        self.assertIs(self.search(national_id='SO1001')['has_active_alert'], True)             # airport officer
        r = self.search(who='hr.officer', unit='DIR-HR', national_id='SO1001')                 # HR cannot check alerts
        self.assertIsNone(r['has_active_alert'])
        self.assertNotIn('alert', ' '.join(r['person'].keys()).replace('has_active_alert', ''))

    def test_search_requires_the_search_permission(self):
        self.new_user('nobody', 'unit_admin', 'HQ')
        with self.assertRaises(PermissionDenied):
            registry.search(self.conn, self.actor('nobody'), query={'national_id': 'SO1001'})


class TestRegisterOrLink(Service):
    def test_second_unit_links_to_the_master_record_instead_of_creating_a_duplicate(self):
        first = self.seed()
        self.assertTrue(first['created'])
        n = self.count()
        # later visit at the Airport: same person, with newly-learned dynamic details + typed-wrong DoB
        again = registry.register(self.conn, self.actor('ap.officer', 'AP-LAA'),
                                  {**AYAAN, 'residence': 'Laascaanood, Xero Awr', 'occupation': 'Teacher',
                                   'date_of_birth': '1992-02-02'})
        self.assertEqual(self.count(), n)                                   # NO duplicate
        self.assertEqual((again['created'], again['exists']), (False, True))
        self.assertEqual(again['person']['person_ref'], first['person']['person_ref'])
        self.assertEqual(sorted(again['filled']), ['occupation', 'residence'])
        self.assertEqual(again['person']['date_of_birth'], date(1990, 5, 17))   # locked value untouched
        self.assertEqual([i['field'] for i in again['ignored']], ['date_of_birth'])

    def test_blanks_are_filled_and_dynamic_fields_refreshed_on_a_later_visit(self):
        self.seed(mother_name=None)
        a = registry.register(self.conn, self.actor('ap.officer', 'AP-LAA'),
                              {**AYAAN, 'mother_name': 'Hodan Cali', 'residence': 'Burao'})
        self.assertEqual(sorted(a['filled']), ['mother_name', 'residence'])
        b = registry.register(self.conn, self.actor('cp.south', 'CP-SOUTH'), {**AYAAN, 'residence': 'Caynabo'})
        self.assertEqual(b['updated'], ['residence'])
        c = registry.register(self.conn, self.actor('cp.south', 'CP-SOUTH'), {**AYAAN, 'mother_name': 'Someone Else'})
        self.assertEqual([i['field'] for i in c['ignored']], ['mother_name'])          # protected: not overwritten
        self.assertEqual(c['person']['mother_name'], 'Hodan Cali')

    def test_possible_duplicate_needs_confirmation_and_an_override_is_audited(self):
        self.seed()
        typo = {**AYAAN, 'second_name': 'Cabdii', 'fourth_name': 'Ahmed', 'national_id': 'SO5555'}
        n = self.count()
        with self.assertRaises(NeedsConfirmation) as cm:
            registry.register(self.conn, self.actor('ap.officer', 'AP-LAA'), typo)
        self.assertEqual(cm.exception.extra['search']['status'], 'confirm')
        self.assertEqual(self.count(), n)
        res = registry.register(self.conn, self.actor('ap.officer', 'AP-LAA'), typo, confirm_new=True)
        self.assertTrue(res['created'])
        self.assertEqual(self.count(), n + 1)
        self.assertEqual(self.one("SELECT count(*) FROM audit_events WHERE action='PERSON_DUPLICATE_OVERRIDE'"), 1)

    def test_officer_can_choose_to_link_to_the_suggested_record(self):
        ref = self.seed()['person']['person_ref']
        n = self.count()
        res = registry.register(self.conn, self.actor('ap.officer', 'AP-LAA'),
                                {**AYAAN, 'second_name': 'Cabdii', 'national_id': 'SO5555', 'occupation': 'Pilot'},
                                link_person_ref=ref)
        self.assertEqual((self.count(), res['person']['person_ref']), (n, ref))
        self.assertEqual(res['filled'], ['occupation'])

    def test_validation(self):
        a = self.actor('fp.officer', 'DIR-FP')
        for bad, field in (({**AYAAN, 'first_name': ''}, 'first_name'), ({**AYAAN, 'date_of_birth': None}, 'date_of_birth'),
                           ({**AYAAN, 'date_of_birth': '17/05/1990'}, 'date_of_birth'),
                           ({**AYAAN, 'date_of_birth': (date.today() + timedelta(days=2)).isoformat()}, 'date_of_birth'),
                           ({**AYAAN, 'national_id': None}, 'national_id')):
            with self.assertRaises(ValidationError) as cm:
                registry.register(self.conn, a, bad)
            self.assertIn(field, str(cm.exception.extra['fields']), bad)

    def test_provenance_records_the_registering_unit(self):
        res = self.seed()
        self.assertEqual(res['person']['registered_at']['code'], 'DIR-FP')
        self.assertEqual(self.one('SELECT created_by FROM persons WHERE person_ref=%s', (res['person']['person_ref'],)),
                         self.uid('fp.officer'))

    def test_chief_commander_can_look_up_but_cannot_register(self):
        self.seed()
        chief = self.actor('chief', 'HQ')
        self.assertTrue(registry.search(self.conn, chief, query={'national_id': 'SO1001'})['exists'])
        n = self.count()
        with self.assertRaises(PermissionDenied):
            registry.register(self.conn, chief, {**NUUR, 'national_id': 'SO3333'})
        link = registry.register(self.conn, chief, {**AYAAN, 'occupation': 'x'})            # existing person: read-only link
        self.assertEqual((link['filled'], link['updated'], self.count()), ([], [], n))

    def test_read_only_user_gets_permission_denied_not_a_confirmation_prompt(self):
        self.seed()
        typo = {**AYAAN, 'second_name': 'Cabdii', 'national_id': 'SO5555'}      # would be Tier 3 for an officer
        with self.assertRaises(PermissionDenied):
            registry.register(self.conn, self.actor('chief', 'HQ'), typo)

    def test_officer_without_create_cannot_register_new_people(self):
        self.new_user('trn.officer', 'transport_officer', 'DIR-TRN')            # person:search only (HR gained person:create in 004)
        with self.assertRaises(PermissionDenied):
            registry.register(self.conn, self.actor('trn.officer', 'DIR-TRN'), AYAAN)


class TestStrictProfileUpdates(Service):
    def setUp(self):
        super().setUp()
        self.ref = self.seed()['person']['person_ref']

    def update(self, who, changes, reason=None, unit=None):
        return registry.update_profile(self.conn, self.actor(who, unit), self.ref, changes, reason)

    def test_regular_user_cannot_touch_core_identity_and_nothing_is_written(self):
        with self.assertRaises(FieldLocked) as cm:
            self.update('ap.officer', {'first_name': 'Nuur', 'date_of_birth': '1991-01-01', 'place_of_birth': 'Burao',
                                       'occupation': 'Teacher'}, reason='typo')          # includes a LEGAL change
        self.assertEqual({f['field'] for f in cm.exception.extra['fields']},
                         {'first_name', 'date_of_birth', 'place_of_birth'})
        p = registry.get_person(self.conn, self.actor('ap.officer'), self.ref)
        self.assertEqual((p['first_name'], p['occupation']), ('Ayaan', None))               # atomic: occupation not applied either

    def test_dynamic_fields_update_freely_and_blank_fields_can_be_enriched(self):
        r = self.update('ap.officer', {'residence': 'Laascaanood', 'occupation': 'Teacher', 'phone': '+252 63 000'})
        self.assertEqual(sorted(r['filled']), ['occupation', 'phone', 'residence'])
        r = self.update('cp.south', {'residence': 'Caynabo'})
        self.assertEqual(r['updated'], ['residence'])

    def test_posting_the_whole_form_back_unchanged_is_not_a_violation(self):
        p = registry.get_person(self.conn, self.actor('ap.officer'), self.ref)
        form = {k: p[k] for k in registry.PROFILE_FIELDS}
        form['occupation'] = 'Teacher'
        r = self.update('ap.officer', form)
        self.assertEqual((r['filled'], r['updated']), (['occupation'], []))

    def test_only_a_blank_place_of_birth_may_be_filled_later(self):
        ref2 = self.seed(**{**NUUR, 'place_of_birth': None})['person']['person_ref']
        a = self.actor('ap.officer')
        self.assertEqual(registry.update_profile(self.conn, a, ref2, {'place_of_birth': 'Burao'})['filled'], ['place_of_birth'])
        with self.assertRaises(FieldLocked):
            registry.update_profile(self.conn, a, ref2, {'place_of_birth': 'Ceerigaabo'})

    def test_national_admin_can_correct_core_identity_with_a_reason(self):
        with self.assertRaises(ValidationError):                                           # reason is mandatory
            self.update('admin', {'date_of_birth': '1990-05-18'})
        r = self.update('admin', {'date_of_birth': '1990-05-18', 'first_name': 'Ayaana'}, reason='Birth certificate')
        self.assertEqual(sorted(r['updated']), ['date_of_birth', 'first_name'])
        self.assertEqual(r['person']['full_name'], 'Ayaana Cabdi Xasan Axmed')
        self.assertEqual(self.one("SELECT details->>'reason' FROM audit_events WHERE action='PERSON_CORE_CHANGE'"),
                         'Birth certificate')

    def test_admin_scoped_below_the_root_is_not_the_national_admin(self):
        self.new_user('local_admin', 'system_admin', 'D-LAASCAANOOD')
        with self.assertRaises(FieldLocked):
            self.update('local_admin', {'first_name': 'Changed'}, reason='x')

    def test_changing_an_id_to_one_that_belongs_to_someone_else_is_rejected(self):
        self.seed(**NUUR)
        with self.assertRaises(IdentifierInUse):
            self.update('admin', {'national_id': 'so-2002'}, reason='x')

    def test_ids_and_internal_columns_cannot_be_edited_through_the_api(self):
        for bad in ('person_ref', 'id', 'created_by', 'full_name', 'created_in_unit_id'):
            with self.assertRaises(ValidationError):
                self.update('admin', {bad: 'x'}, reason='x')

    def test_unknown_person(self):
        with self.assertRaises(NotFound):
            registry.update_profile(self.conn, self.actor('admin'), 'P-999999', {'occupation': 'x'})


class TestGuardianEnrichment(Service):
    CHILD = dict(first_name='Hodan', second_name='Nuur', third_name='Cali', date_of_birth=None,
                 place_of_birth='Burao')

    def child(self, **over):
        dob = (date.today() - timedelta(days=365 * 7)).isoformat()
        return registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), {**self.CHILD, 'date_of_birth': dob, **over},
                                 allow_no_id=True)

    def test_a_minor_is_flagged_missing_a_guardian_until_one_is_added_at_another_unit(self):
        c = self.child()
        self.assertIn('guardian', [m['field'] for m in c['person']['missing_fields']])
        ref = c['person']['person_ref']
        res = registry.add_guardian(
            self.conn, self.actor('ap.officer', 'AP-LAA'), ref,
            {'first_name': 'Cabdi', 'second_name': 'Faarax', 'third_name': 'Cali', 'national_id': 'SO900',
             'phone': '+25263111', 'residence': 'Laascaanood', 'occupation': 'Trader'}, relationship='Parent')
        self.assertTrue(res['link_created'] and res['guardian_created'])
        self.assertNotIn('guardian', [m['field'] for m in res['person']['missing_fields']])
        g = res['person']['guardians'][0]
        self.assertEqual((g['full_name'], g['relationship'], g['phone'], g['occupation']),
                         ('Cabdi Faarax Cali', 'Parent', '+25263111', 'Trader'))
        self.assertEqual(res['person']['registered_at']['code'], 'DIR-FP')     # provenance of the child unchanged

    def test_the_same_guardian_is_reused_not_duplicated_and_blank_details_are_filled(self):
        ref = self.child()['person']['person_ref']
        sib = self.child(first_name='Faadumo')['person']['person_ref']
        base = {'first_name': 'Cabdi', 'second_name': 'Faarax', 'third_name': 'Cali', 'national_id': 'SO900'}
        registry.add_guardian(self.conn, self.actor('ap.officer', 'AP-LAA'), ref, base, relationship='Parent')
        n = self.count()
        r = registry.add_guardian(self.conn, self.actor('cp.south', 'CP-SOUTH'), sib,
                                  {**base, 'occupation': 'Trader'}, relationship='Parent')      # same ID, new detail
        self.assertEqual((self.count(), r['guardian_created'], r['guardian_filled']), (n, False, ['occupation']))
        again = registry.add_guardian(self.conn, self.actor('cp.south', 'CP-SOUTH'), sib, base)
        self.assertFalse(again['link_created'])                                              # idempotent

    def test_guardian_without_an_id_but_a_similar_name_requires_confirmation(self):
        ref = self.child()['person']['person_ref']
        g = {'first_name': 'Cabdi', 'second_name': 'Faarax', 'third_name': 'Cali'}
        registry.add_guardian(self.conn, self.actor('ap.officer', 'AP-LAA'), ref, g, relationship='Parent')
        other = self.child(first_name='Axmed')['person']['person_ref']
        with self.assertRaises(NeedsConfirmation):
            registry.add_guardian(self.conn, self.actor('ap.officer', 'AP-LAA'), other, g)
        res = registry.add_guardian(self.conn, self.actor('ap.officer', 'AP-LAA'), other, g, confirm_new=True)
        self.assertTrue(res['guardian_created'])

    def test_cannot_be_own_guardian_and_needs_permission(self):
        ref = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), AYAAN)['person']['person_ref']
        with self.assertRaises(ValidationError):
            registry.add_guardian(self.conn, self.actor('ap.officer', 'AP-LAA'), ref, {}, guardian_person_ref=ref)
        self.new_user('trn.officer', 'transport_officer', 'DIR-TRN')
        with self.assertRaises(PermissionDenied):
            registry.add_guardian(self.conn, self.actor('trn.officer', 'DIR-TRN'), ref, {'first_name': 'x'})


class TestConcurrentIntake(DbCase):
    """Two units register the SAME person at the same instant: exactly one master record."""
    DBNAME = 'sentinel_identity_race'

    def test_race_creates_one_record(self):
        results, errors = [], []

        def intake(who, unit):
            try:
                conn = psycopg2.connect(self.uri)
                cur = conn.cursor()
                cur.execute('SELECT id FROM users WHERE username=%s', (who,))
                uid = cur.fetchone()[0]
                cur.execute('SELECT id FROM org_units WHERE code=%s', (unit,))
                a = Actor(uid, who, cur.fetchone()[0])
                res = registry.register(conn, a, AYAAN)
                conn.commit()
                results.append(res['created'])
                conn.close()
            except Exception as e:                    # pragma: no cover
                errors.append(repr(e))

        ts = [threading.Thread(target=intake, args=w) for w in
              (('fp.officer', 'DIR-FP'), ('ap.officer', 'AP-LAA'), ('cp.south', 'CP-SOUTH'), ('cid.officer', 'DIR-CID'))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [False, False, False, True])
        self.assertEqual(self.one("SELECT count(*) FROM persons WHERE national_id='SO1001'"), 1)
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("DELETE FROM persons")
        self.conn.commit()


if __name__ == '__main__':
    unittest.main()
