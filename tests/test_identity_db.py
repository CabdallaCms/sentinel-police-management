"""Database-level field immutability: the guard holds even if application code is bypassed."""
import unittest

from .base import DbCase


class TestFieldGuard(DbCase):
    DBNAME = 'sentinel_identity_guard'

    # ---- normalisation / derived columns --------------------------------------------
    def test_full_name_tokens_and_ids_are_derived_and_normalised(self):
        p = self.raw_person('  Ayaan   Cabdi Xasan Axmed ', national_id=' so-1001 ', mother_name='Hodan  Cali')
        r = self.all('SELECT full_name, name_tokens, national_id, mother_norm FROM persons WHERE id=%s', (p,))[0]
        self.assertEqual(r[0], 'Ayaan Cabdi Xasan Axmed')
        self.assertEqual(r[1], ['ayaan', 'cabdi', 'xasan', 'axmed'])
        self.assertEqual(r[2], 'SO-1001')
        self.assertEqual(r[3], 'hodan cali')

    def test_national_id_is_unique_after_normalisation(self):
        self.raw_person(national_id='SO-1001')
        self.fails("INSERT INTO persons(person_ref, full_name, first_name, national_id) "
                   "VALUES ('P-X','x','Nuur','so 1001')", code='23505')

    def test_writes_without_an_authenticated_user_fail_closed(self):
        e = self.fails("INSERT INTO persons(person_ref, full_name, first_name) VALUES ('P-Z','z','Zed')", code='42501')
        self.assertIn('authenticated', str(e))

    def test_maintenance_flag_is_the_explicit_opt_in_for_imports(self):
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("INSERT INTO persons(person_ref, full_name, first_name) VALUES ('P-IMP','x','Imported')")
        self.assertEqual(self.one("SELECT created_by FROM persons WHERE person_ref='P-IMP'"), None)

    def test_a_role_without_person_create_cannot_insert(self):
        self.new_user('trn.officer', 'transport_officer', 'DIR-TRN')
        self.bind('trn.officer')                      # person:search only
        self.fails("INSERT INTO persons(person_ref, full_name, first_name) VALUES ('P-H','h','Hr')", code='42501')

    # ---- the lock --------------------------------------------------------------------
    CORE = [('first_name', 'Nuur'), ('second_name', 'Faarax'), ('third_name', 'Cali'), ('fourth_name', 'Yuusuf'),
            ('date_of_birth', '1991-01-01'), ('place_of_birth', 'Burao')]

    def test_every_core_field_is_locked_for_regular_officers(self):
        p = self.raw_person()
        for who in ('fp.officer', 'ap.officer', 'cp.south', 'cid.officer'):
            self.bind(who, 'trying anyway')
            for field, value in self.CORE:
                e = self.fails(f'UPDATE persons SET {field}=%s WHERE id=%s', (value, p), code='42501')
                self.assertEqual(e.diag.column_name, field, (who, field))
        self.assertEqual(self.one('SELECT first_name FROM persons WHERE id=%s', (p,)), 'Ayaan')

    def test_identifiers_lock_once_set_but_can_be_added_when_blank(self):
        p = self.raw_person(national_id='SO1001')
        self.bind('fp.officer', 'x')
        self.fails('UPDATE persons SET national_id=%s WHERE id=%s', ('SO9999', p), code='42501')
        self.cur.execute('UPDATE persons SET passport_id=%s WHERE id=%s', ('A1234567', p))    # blank -> fill is fine
        self.fails('UPDATE persons SET passport_id=%s WHERE id=%s', ('B7654321', p), code='42501')

    def test_blank_core_fields_may_be_filled_once_then_lock(self):
        p = self.raw_person(pob=None)
        self.bind('ap.officer')
        self.cur.execute("UPDATE persons SET place_of_birth='Ceerigaabo' WHERE id=%s", (p,))
        self.fails("UPDATE persons SET place_of_birth='Burao' WHERE id=%s", (p,), code='42501')
        self.assertEqual(self.one("SELECT kind FROM person_field_audit WHERE person_id=%s AND field='place_of_birth'", (p,)), 'fill')

    def test_guardian_style_enrichment_of_dynamic_fields_is_allowed(self):
        p = self.raw_person()
        self.bind('ap.officer')
        self.cur.execute("UPDATE persons SET residence='Laascaanood, Xero Awr', occupation='Teacher', phone='+25263000' WHERE id=%s", (p,))
        self.bind('cp.south')                                                                  # a different unit, later visit
        self.cur.execute("UPDATE persons SET residence='Caynabo', occupation='Driver' WHERE id=%s", (p,))
        self.assertEqual(self.one('SELECT residence FROM persons WHERE id=%s', (p,)), 'Caynabo')
        self.assertEqual(self.one("SELECT count(*) FROM person_field_audit WHERE person_id=%s AND field='residence'", (p,)), 2)

    def test_mother_name_is_fill_once_and_only_person_update_can_correct_it(self):
        p = self.raw_person(mother_name='Hodan Cali')
        self.bind('ap.officer')
        self.fails("UPDATE persons SET mother_name='Faadumo' WHERE id=%s", (p,), code='42501')
        self.bind('fp.officer')                                                                # holds person:update
        self.cur.execute("UPDATE persons SET mother_name='Faadumo Cali' WHERE id=%s", (p,))

    def test_only_the_national_admin_may_change_core_identity_and_must_give_a_reason(self):
        p = self.raw_person()
        self.bind('admin')                                                                     # no reason
        e = self.fails("UPDATE persons SET date_of_birth='1990-05-18' WHERE id=%s", (p,), code='23514')
        self.assertIn('reason', str(e))
        self.bind('admin', 'Birth certificate shows the 18th')
        self.cur.execute("UPDATE persons SET date_of_birth='1990-05-18', first_name='Ayaana' WHERE id=%s", (p,))
        self.assertEqual(self.one('SELECT full_name FROM persons WHERE id=%s', (p,)), 'Ayaana Cabdi Xasan Axmed')
        rows = self.all("SELECT field, old_value, new_value, kind, reason, user_id FROM person_field_audit "
                        "WHERE person_id=%s AND kind='change' ORDER BY field", (p,))
        self.assertEqual([r[0] for r in rows], ['date_of_birth', 'first_name'])
        self.assertEqual(rows[0][1:4], ('1990-05-17', '1990-05-18', 'change'))
        self.assertEqual(rows[0][4], 'Birth certificate shows the 18th')
        self.assertEqual(rows[0][5], self.uid('admin'))

    def test_national_admin_means_the_ROOT_unit_not_just_the_role(self):
        p = self.raw_person()
        # the same system_admin role, but assigned only to a district: not "national"
        self.new_user('local_admin', 'system_admin', 'D-LAASCAANOOD')
        self.bind('local_admin', 'reason')
        self.fails("UPDATE persons SET first_name='Changed' WHERE id=%s", (p,), code='42501')
        # …while dynamic fields are still fine for them
        self.cur.execute("UPDATE persons SET occupation='Clerk' WHERE id=%s", (p,))

    def test_chief_commander_cannot_change_anything(self):
        p = self.raw_person()
        self.bind('chief', 'oversight')
        self.fails("UPDATE persons SET occupation='x' WHERE id=%s", (p,), code='42501')
        self.fails("UPDATE persons SET first_name='x' WHERE id=%s", (p,), code='42501')

    def test_person_ref_and_provenance_are_immutable_even_for_the_admin(self):
        p = self.raw_person()
        self.bind('admin', 'because')
        self.fails("UPDATE persons SET person_ref='P-HACK' WHERE id=%s", (p,), code='42501')
        self.fails("UPDATE persons SET created_by=NULL WHERE id=%s", (p,), code='42501')

    def test_unchanged_and_whitespace_only_updates_are_not_changes(self):
        p = self.raw_person(national_id='SO1001')
        self.bind('ap.officer')
        self.cur.execute("UPDATE persons SET first_name='  Ayaan ', national_id=' so1001 ', occupation='x' WHERE id=%s", (p,))
        self.assertEqual(self.one("SELECT count(*) FROM person_field_audit WHERE person_id=%s AND field IN ('first_name','national_id')", (p,)), 0)

    def test_full_name_cannot_be_edited_around_the_locked_parts(self):
        p = self.raw_person()
        self.bind('ap.officer')
        self.cur.execute("UPDATE persons SET full_name='Totally Different Name' WHERE id=%s", (p,))   # ignored: derived
        self.assertEqual(self.one('SELECT full_name FROM persons WHERE id=%s', (p,)), 'Ayaan Cabdi Xasan Axmed')

    def test_legacy_import_row_with_only_a_full_name_is_still_protected(self):
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("INSERT INTO persons(person_ref, full_name) VALUES ('P-OLD','Old Record Name')")
        self.cur.execute("SELECT set_config('sentinel.maintenance','off',true)")
        self.bind('ap.officer')
        self.fails("UPDATE persons SET full_name='Renamed' WHERE person_ref='P-OLD'", code='42501')

    def test_persons_cannot_be_deleted_and_the_audit_is_append_only(self):
        p = self.raw_person()
        self.bind('admin', 'r')
        self.fails('DELETE FROM persons WHERE id=%s', (p,), code='42501')
        self.cur.execute("UPDATE persons SET occupation='x' WHERE id=%s", (p,))
        self.fails('DELETE FROM person_field_audit', None)
        self.fails("UPDATE person_field_audit SET new_value='tampered'", None)

    # ---- policy data ---------------------------------------------------------------
    def test_only_system_admin_holds_edit_core_and_no_read_only_role_can_write(self):
        holders = {r[0] for r in self.all("SELECT r.code FROM role_permissions rp JOIN roles r ON r.id=rp.role_id "
                                          "WHERE rp.permission_code='person:edit_core'")}
        self.assertEqual(holders, {'system_admin'})
        ro = self.all("SELECT r.code FROM role_permissions rp JOIN roles r ON r.id=rp.role_id "
                      "WHERE r.is_read_only AND rp.permission_code IN ('person:edit_core','person:update_dynamic','person:update')")
        self.assertEqual(ro, [])

    def test_field_states_describe_what_each_user_may_do(self):
        p = self.raw_person(national_id='SO1001')
        st = lambda u: {r[0]: r[3] for r in self.all('SELECT * FROM person_field_states(%s,%s)', (self.uid(u), p))}
        officer, admin, chief = st('ap.officer'), st('admin'), st('chief')
        self.assertEqual({officer[f] for f in ('first_name', 'second_name', 'third_name', 'date_of_birth', 'place_of_birth', 'national_id')}, {'locked'})
        self.assertEqual(officer['residence'], 'fillable')          # blank dynamic field: can be filled…
        self.cur.execute("UPDATE persons SET residence='Caynabo' WHERE id=%s", (p,))
        self.assertEqual(st('ap.officer')['residence'], 'editable')  # …and once set, stays editable (dynamic)
        self.assertEqual(officer['passport_id'], 'fillable')        # blank identifier can be added
        self.assertEqual(admin['first_name'], 'editable')
        self.assertEqual(set(chief.values()), {'locked'})


if __name__ == '__main__':
    unittest.main()
