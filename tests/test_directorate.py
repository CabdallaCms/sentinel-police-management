"""Phase 3 — Directorate & specialised services: fingerprint clearance, CID cases / alerts, HR officers / conduct,
and the configuration-driven structure.  ONE comprehensive module (the project's final suite runs it once).

Real PostgreSQL built from migrations/ (001–004); every service call runs as the non-owner role app_rw so
row-level security is ON.  Fixtures extend the org tree with DATA ONLY (bureaus, a station outside the state).
"""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

import psycopg2

from app import server
from app.db import Actor
from app.directorate import cid, clearance, conduct, officers, signing, structure
from app.identity.errors import (Duplicate, NeedsConfirmation, NotFound, PermissionDenied, ReviewLocked, ValidationError)
from app.operations import checkpoint
from . import pg_support
from .base import DbCase

_state = {}
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32

APPLICANT = dict(first_name='Faadumo', second_name='Jaamac', third_name='Warsame', fourth_name='Ismaaciil',
                 date_of_birth='1992-03-04', place_of_birth='Burao', national_id='SO9001', mother_name='Hawa Cali',
                 phone='+252 63 000 1111')
GUARDIAN = dict(first_name='Warsame', second_name='Ismaaciil', third_name='Dhegaweyne', national_id='SO9002',
                phone='+252 63 111 2222', residence='Laascaanood', occupation='Trader')
SUSPECT = dict(first_name='Guuleed', second_name='Xirsi', third_name='Cabdi', date_of_birth='1985-01-02')
WITNESS = dict(first_name='Sahra', second_name='Cismaan', third_name='Ducaale')
RECRUIT = dict(first_name='Mustafe', second_name='Cabdillaahi', third_name='Samatar', fourth_name='Yuusuf',
               date_of_birth='1996-06-06', place_of_birth='Ceerigaabo', mother_name='Amina Nuur',
               phone='+252 63 222 3333', national_id='SO9100')

FIXTURES = """
    INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs) VALUES
      ((SELECT id FROM org_units WHERE code='DIR-CID'), 'bureau', 'BR-CID-SOOL',  'CID Sool Bureau',   'active', '{"region":"SOOL"}'),
      ((SELECT id FROM org_units WHERE code='DIR-FP'),  'bureau', 'BR-FP-SANAAG', 'FP Sanaag Intake',  'active', '{"region":"SANAAG"}'),
      ((SELECT id FROM org_units WHERE code='HQ'),      'region',  'XREG',        'Unlisted Test Region', 'active', '{}');
    INSERT INTO org_units (parent_id, unit_type, code, name, status) VALUES
      ((SELECT id FROM org_units WHERE code='XREG'), 'district', 'D-X', 'X District', 'active');
    INSERT INTO org_units (parent_id, unit_type, code, name, status) VALUES
      ((SELECT id FROM org_units WHERE code='D-X'), 'station', 'ST-X', 'X Station', 'active');
    INSERT INTO users (username, display_name, password_hash) VALUES
      ('st.laas','Station Las Anod','!t'), ('cmd.laas','Commander Las Anod','!t'), ('cmd.buu','Commander Buuhoodle','!t'),
      ('rc.sool','Sool commander','!t'), ('cid.sool','CID Sool','!t'), ('fp.sanaag','FP Sanaag','!t'),
      ('hr.reviewer','HR reviewer','!t'), ('x.cmd','X commander','!t'), ('cp.south2','Checkpoint','!t'),
      ('builder.sool','Sool unit builder','!t');
    -- roles are DATA too: a delegated "unit builder" for one region needs no code
    INSERT INTO roles (code, name) VALUES ('region_builder', 'Regional unit builder');
    INSERT INTO role_permissions SELECT (SELECT id FROM roles WHERE code='region_builder'), p
      FROM unnest(ARRAY['unit:view','unit:manage','assignment:manage']) p;
    CREATE FUNCTION pg_temp.asg(u text, r text, unit text, d boolean DEFAULT false) RETURNS void LANGUAGE sql AS $f$
      INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants)
      VALUES ((SELECT id FROM users WHERE username=u), (SELECT id FROM roles WHERE code=r),
              (SELECT id FROM org_units WHERE code=unit), d) $f$;
    SELECT pg_temp.asg('st.laas','station_officer','ST-004'), pg_temp.asg('cmd.laas','station_commander','ST-004'),
           pg_temp.asg('cmd.buu','station_commander','ST-007'), pg_temp.asg('rc.sool','regional_commander','SOOL', true),
           pg_temp.asg('cid.sool','cid_officer','BR-CID-SOOL', true), pg_temp.asg('fp.sanaag','fingerprint_officer','BR-FP-SANAAG', true),
           pg_temp.asg('hr.reviewer','hr_officer','DIR-HR', true), pg_temp.asg('x.cmd','station_commander','ST-X'),
           pg_temp.asg('cp.south2','checkpoint_officer','CP-SOUTH'), pg_temp.asg('builder.sool','region_builder','SOOL', true);
"""


def setUpModule():
    os.environ['SENTINEL_DB_ROLE'] = 'app_rw'
    os.environ['SENTINEL_DEV_AUTH'] = '1'
    uri = pg_support.create_database('sentinel_directorate')
    c = psycopg2.connect(uri)
    c.cursor().execute(FIXTURES)
    c.commit()
    c.close()
    _state['uri'] = uri


def tearDownModule():
    os.environ.pop('SENTINEL_DB_ROLE', None)


class DirCase(DbCase):
    @classmethod
    def setUpClass(cls):
        cls.uri = _state['uri']

    _keep_role = False

    def one(self, sql, params=None):
        if not self._keep_role:
            self.cur.execute('RESET ROLE')
        return super().one(sql, params)

    def all(self, sql, params=None):
        if not self._keep_role:
            self.cur.execute('RESET ROLE')
        return super().all(sql, params)

    def as_db_user(self, username):
        self._keep_role = False
        uid = self.uid(username)
        self.cur.execute("SELECT set_config('app.user_id', %s, true)", (str(uid),))
        self.cur.execute('SET ROLE app_rw')
        self._keep_role = True

    def done_as_db_user(self):
        self._keep_role = False
        self.cur.execute('RESET ROLE')

    def error(self, exc, fn, *a, **kw):
        with self.assertRaises(exc) as cm:
            fn(*a, **kw)
        return cm.exception

    def upload(self, username, kind='png'):
        name = os.urandom(16).hex() + '.' + kind
        self.one("INSERT INTO uploads (name, content_type, size_bytes, uploaded_by) VALUES (%s, %s, 10, %s) RETURNING name",
                 (name, 'image/png' if kind == 'png' else 'application/pdf', self.uid(username)))
        return name

    def no_delete(self, sql, params=None):
        """A DELETE under RLS: refused by the trigger, or it simply sees no row (there is no DELETE policy)."""
        self.cur.execute('SAVEPOINT nd')
        try:
            self.cur.execute(sql, params)
            self.assertEqual(self.cur.rowcount, 0)
        except psycopg2.Error as e:
            self.assertEqual(e.pgcode, '42501')
            self.cur.execute('ROLLBACK TO SAVEPOINT nd')

    def maintenance(self, sql, params=None):
        self.cur.execute('RESET ROLE')
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute(sql, params)
        self.cur.execute("SELECT set_config('sentinel.maintenance','off',true)")

    # ---- clearance --------------------------------------------------------------------------------
    def clr_payload(self, who='st.laas', unit='ST-004', **over):
        p = dict(unit=unit, purpose='Travel', applicant=dict(APPLICANT), applicant_photo=self.upload(who),
                 applicant_docs=[self.upload(who, 'pdf'), self.upload(who, 'pdf')], guardian=dict(GUARDIAN),
                 guardian_relationship='Uncle', guardian_docs=[self.upload(who, 'pdf'), self.upload(who, 'pdf')])
        p.update(over)
        return p

    def file_clr(self, who='st.laas', unit='ST-004', **over):
        return clearance.file_application(self.conn, self.actor(who, unit), self.clr_payload(who, unit, **over))

    def age(self, ref, hours=13):
        self.maintenance("UPDATE clearance_applications SET created_at = now() - make_interval(hours => %s) WHERE application_ref = %s",
                         (hours, ref))

    # ---- people / officers ----------------------------------------------------------------------------
    def officer_payload(self, who='hr.officer', unit='ST-004', person=None, **over):
        p = dict(unit=unit, rank='Sergeant', unit_role='General Patrol', date_of_enlistment='2019-01-01',
                 person=dict(person or RECRUIT), photo=self.upload(who),
                 guarantor=dict(name='Cali Nuur', address='Ceerigaabo', contact='+252 63 999 0000', relationship='Parent'),
                 doc1_type='National ID', doc1_file=self.upload(who, 'pdf'))
        p.update(over)
        return p

    def mk_officer(self, unit='ST-004', rank='Sergeant', n=[0], who='hr.officer'):
        n[0] += 1
        firsts, seconds, thirds = ['Cabdi', 'Siciid', 'Nuur', 'Khadar', 'Ismaaciil', 'Maxamed'], ['Xaashi', 'Geedi', 'Dalmar', 'Roble', 'Aw-Cali', 'Barkhad'], ['Ducaale', 'Guure', 'Hirsi', 'Liibaan', 'Mursal', 'Sh.Cumar']
        person = dict(RECRUIT, first_name=firsts[n[0] % 6], second_name=seconds[(n[0] * 5) % 6], third_name=thirds[(n[0] * 7) % 6],
                      fourth_name='', date_of_birth=f'19{70 + n[0]}-0{1 + n[0] % 9}-1{n[0] % 9}', national_id=f'SO95{n[0]:02d}', mother_name='Mother ' + thirds[n[0] % 6])
        return officers.register_officer(self.conn, self.actor(who), self.officer_payload(who, unit, person, rank=rank))['officer']['service_ref']

    def conduct_payload(self, officer, **over):
        p = dict(officer=officer, action_type='Promotion / Commendation', classification='Rank Advancement',
                 proposed_rank='Inspector', narrative='Led the station through a difficult year with outstanding results.')
        p.update(over)
        return p


# =====================================================================================================
class TestClearance(DirCase):

    def test_local_intake_national_decision_and_signed_certificate(self):
        r = self.file_clr()
        ref = r['application']['application_ref']
        self.assertTrue(ref.startswith('FP-ST-004-'))
        self.assertEqual(r['application']['status'], 'Pending Review')
        self.assertTrue(r['application']['review_locked'])
        self.assertEqual(self.one("SELECT u.code FROM clearance_applications a JOIN org_units u ON u.id = a.owner_unit_id "
                                  "WHERE a.application_ref = %s", (ref,)), 'DIR-FP')            # national owner by default
        self.assertEqual(self.one("SELECT u.code FROM clearance_applications a JOIN org_units u ON u.id = a.intake_unit_id "
                                  "WHERE a.application_ref = %s", (ref,)), 'ST-004')
        self.assertEqual(r['person']['full_name'], 'Faadumo Jaamac Warsame Ismaaciil')
        self.assertEqual(r['guardian']['relationship'], 'Uncle')
        self.assertEqual(self.one("SELECT count(*) FROM person_guardians"), 1)                  # the guardian is a registry person

        # intake scope grants NO approval right ...
        for who, unit in (('st.laas', 'ST-004'), ('cmd.laas', 'ST-004'), ('rc.sool', None), ('chief', None)):
            e = self.error(PermissionDenied, clearance.decide, self.conn, self.actor(who, unit), ref, 'approve')
            self.assertIn('national', e.message.lower(), who)
        self.error(NotFound, clearance.decide, self.conn, self.actor('fp.sanaag', 'BR-FP-SANAAG'), ref, 'approve')   # another intake: cannot even see it
        # ... and the 12 h window binds the Fingerprint directorate itself
        e = self.error(ReviewLocked, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'approve')
        self.assertEqual((e.status, e.code), (400, 'review_period_active'))
        self.assertGreater(e.extra['hours_remaining'], 11)
        self.assertEqual(self.one("SELECT status FROM clearance_applications WHERE application_ref = %s", (ref,)), 'Pending Review')

        self.age(ref)
        self.assertFalse(clearance.get_application(self.conn, self.actor('fp.officer'), ref)['review_locked'])
        out = clearance.decide(self.conn, self.actor('fp.officer'), ref, 'approve')
        cert = out['certificate']
        self.assertEqual((out['status'], out['review_period_bypassed']), ('Approved', False))
        self.assertTrue(out['certificate_number'].startswith('CL-DIR-FP-'))
        self.assertEqual((cert['issuer'], cert['purpose'], cert['key_id']), ('DIR-FP', 'Travel', 'dev-1'))
        self.error(Duplicate, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'reject', 'too late')   # decisions are final

        # public verification: no login, masked holder, signature checked
        v = clearance.verify_public(self.conn, out['certificate_number'])
        self.assertTrue(v['valid'])
        self.assertEqual(v['holder'], 'Faadumo J. W. I.')
        self.assertNotIn('national_id', v)
        self.assertFalse(clearance.verify_public(self.conn, 'CL-NOPE-0')['valid'])
        # tamper with the stored snapshot: the signature no longer matches
        self.maintenance("UPDATE clearance_applications SET certificate_snapshot = jsonb_set(certificate_snapshot, '{holder}', '\"Forged Name\"') "
                         "WHERE application_ref = %s", (ref,))
        t = clearance.verify_public(self.conn, out['certificate_number'])
        self.assertFalse(t['valid'])
        self.assertIn('altered', t['reason'])

    def test_printing_is_national_logged_and_only_for_approved(self):
        ref = self.file_clr()['application']['application_ref']
        self.error(ValidationError, clearance.certificate, self.conn, self.actor('fp.officer'), ref)      # not approved yet
        self.age(ref)
        clearance.decide(self.conn, self.actor('fp.officer'), ref, 'approve')
        for who, unit in (('st.laas', 'ST-004'), ('rc.sool', None)):
            self.error(PermissionDenied, clearance.certificate, self.conn, self.actor(who, unit), ref)
        self.error(NotFound, clearance.certificate, self.conn, self.actor('fp.sanaag', 'BR-FP-SANAAG'), ref)
        self.assertEqual(clearance.certificate(self.conn, self.actor('fp.officer'), ref, log_print=False)['print_count'], 0)
        self.assertEqual(clearance.certificate(self.conn, self.actor('fp.officer'), ref)['print_count'], 1)
        c = clearance.certificate(self.conn, self.actor('fp.officer'), ref)
        self.assertEqual(c['print_count'], 2)
        self.assertTrue(signing.verify(c['certificate'], c['signature'], self.one("SELECT public_key FROM signing_keys WHERE key_id='dev-1'")))
        self.assertEqual(self.one("SELECT count(*) FROM audit_events WHERE action = 'CLEARANCE_PRINT'"), 2)
        self.as_db_user('fp.officer')                                          # the log is append-only even for its writer
        self.no_delete("UPDATE clearance_prints SET printed_by = printed_by")
        self.done_as_db_user()

    def test_reject_override_and_the_window_is_policy_data(self):
        ref = self.file_clr()['application']['application_ref']
        self.error(ReviewLocked, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'reject', 'x')       # a rejection waits too
        self.age(ref)
        self.error(ValidationError, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'reject')    # a reason is required
        self.assertEqual(clearance.decide(self.conn, self.actor('fp.officer'), ref, 'reject', 'Documents unreadable')['status'], 'Rejected')
        self.error(ValidationError, clearance.certificate, self.conn, self.actor('fp.officer'), ref)   # rejected -> no certificate (not Approved)
        # override permission (system_admin holds every permission, blueprint §8-O1) skips the window, and says so
        ref2 = self.file_clr(applicant=dict(APPLICANT, national_id='SO9003', first_name='Hodan', second_name='Dahir', third_name='Jibriil', fourth_name='', date_of_birth='1988-02-02'))['application']['application_ref']
        out = clearance.decide(self.conn, self.actor('admin'), ref2, 'approve')
        self.assertTrue(out['review_period_bypassed'])
        self.assertEqual(self.one("SELECT details->>'review_period_bypassed' FROM audit_events WHERE action='CLEARANCE_APPROVE' "
                                  "ORDER BY id DESC LIMIT 1"), 'true')
        # the window is a policy row, not a constant
        self.maintenance("UPDATE policy_settings SET value = '1' WHERE key = 'clearance.review_window_hours'")
        ref3 = self.file_clr(applicant=dict(APPLICANT, national_id='SO9004', first_name='Ladan', second_name='Sheekh', third_name='Daahir', fourth_name='', date_of_birth='1991-07-07'))['application']['application_ref']
        self.assertEqual(clearance.get_application(self.conn, self.actor('fp.officer'), ref3)['review_window_hours'], 1.0)

    def test_intake_rules_and_state_boundary(self):
        e = self.error(ValidationError, clearance.file_application, self.conn, self.actor('st.laas', 'ST-004'),
                       self.clr_payload(applicant_photo='', applicant_docs=[]))
        self.assertIn('applicant_photo', e.extra['fields'])
        self.assertIn('applicant_docs', e.extra['fields'])
        self.error(ValidationError, clearance.file_application, self.conn, self.actor('st.laas', 'ST-004'),
                   self.clr_payload(applicant=dict(APPLICANT, national_id='', passport_id='')))        # legacy: an ID is required
        self.error(ValidationError, clearance.file_application, self.conn, self.actor('st.laas', 'ST-004'),
                   self.clr_payload(purpose='Tourism'))
        # a station outside Sool / Sanaag / East Togdheer cannot file, nor can anyone insert there directly
        e = self.error(ValidationError, clearance.file_application, self.conn, self.actor('x.cmd', 'ST-X'), self.clr_payload('x.cmd', 'ST-X'))
        self.assertIn('Northeastern State', e.message)
        pid = self.raw_person(national_id=None)
        self.as_db_user('x.cmd')
        self.fails("INSERT INTO clearance_applications (application_ref, person_id, intake_unit_id, purpose) VALUES ('FP-RAW-1', %s, %s, 'Travel')",
                   (pid, self.unit('ST-X')), code='23514')              # RLS lets x.cmd file at ST-X; the state-boundary trigger refuses
        self.done_as_db_user()
        # a Fingerprint intake BUREAU (data-only) may file for its region; it still cannot approve (T1)
        r = self.file_clr('fp.sanaag', 'BR-FP-SANAAG')
        self.assertEqual(r['application']['intake_unit']['region'], 'Sanaag')
        # DB guard, not the service: a filed application is immutable except for its decision
        self.maintenance("SELECT 1")
        ref = r['application']['application_ref']
        self.as_db_user('fp.officer')
        self.fails("UPDATE clearance_applications SET purpose = 'Education', status = 'Rejected', review_notes = 'x' WHERE application_ref = %s",
                   (ref,), code='42501')                                             # anything but the decision is immutable
        self.fails("UPDATE clearance_applications SET purpose = 'Education' WHERE application_ref = %s", (ref,), code='23514')
        self.fails("UPDATE clearance_applications SET status = 'Approved', certificate_number = 'CL-X', certificate_signature = 'x', "
                   "signing_key_id = 'dev-1' WHERE application_ref = %s", (ref,), code='55000')        # inside the review window
        self.done_as_db_user()

    def test_guardian_policy_and_confirmation(self):
        # the guardian rule is policy data: switch to "minors only" and an adult needs none
        self.maintenance("""UPDATE policy_settings SET value = '{"photo": true, "applicant_docs": 2, "guardian": "minors", "guardian_docs": 2}'
                             WHERE key = 'clearance.required'""")
        r = self.file_clr(guardian=None, guardian_relationship=None, guardian_docs=[])
        self.assertIsNone(r['guardian'])
        minor = dict(APPLICANT, national_id='SO9010', first_name='Yuusuf', date_of_birth=f'{date.today().year - 10}-01-01')
        e = self.error(ValidationError, clearance.file_application, self.conn, self.actor('st.laas', 'ST-004'),
                       self.clr_payload(applicant=minor, guardian=None, guardian_relationship=None, guardian_docs=[]))
        self.assertIn('guardian', e.extra['fields'])

    def test_visibility_follows_the_tree(self):
        ref = self.file_clr()['application']['application_ref']
        seen = lambda who, unit=None: [a['application_ref'] for a in clearance.list_applications(self.conn, self.actor(who, unit))['items']]
        self.assertEqual(seen('st.laas', 'ST-004'), [ref])
        self.assertEqual(seen('rc.sool'), [ref])                    # the region's commander sees its subtree
        self.assertEqual(seen('fp.officer'), [ref])                 # the owning directorate sees all
        self.assertEqual(seen('chief'), [ref])                      # read-only root
        self.assertEqual(seen('cmd.buu', 'ST-007'), [])             # another station
        self.assertEqual(seen('hr.officer'), [])
        self.error(NotFound, clearance.get_application, self.conn, self.actor('cmd.buu', 'ST-007'), ref)
        self.assertFalse(clearance.get_application(self.conn, self.actor('st.laas', 'ST-004'), ref)['can_decide'])
        self.age(ref)
        self.assertTrue(clearance.get_application(self.conn, self.actor('fp.officer'), ref)['can_decide'])

    def test_fails_closed_without_a_signing_key(self):
        ref = self.file_clr()['application']['application_ref']
        self.age(ref)
        saved = os.environ.pop('SENTINEL_DEV_AUTH')
        try:
            e = self.error(signing.SigningUnavailable, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'approve')
            self.assertEqual(e.status, 503)
        finally:
            os.environ['SENTINEL_DEV_AUTH'] = saved
        self.assertEqual(self.one("SELECT status FROM clearance_applications WHERE application_ref = %s", (ref,)), 'Pending Review')
        # a key that is not the registered one is refused too
        os.environ['SENTINEL_SIGNING_KEY'] = 'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE='
        os.environ['SENTINEL_SIGNING_KEY_ID'] = 'rogue-1'
        try:
            self.error(signing.SigningUnavailable, clearance.decide, self.conn, self.actor('fp.officer'), ref, 'approve')
        finally:
            os.environ.pop('SENTINEL_SIGNING_KEY'); os.environ.pop('SENTINEL_SIGNING_KEY_ID')


# =====================================================================================================
class TestCid(DirCase):

    def case(self, who='cid.officer', unit=None, **over):
        p = dict(category='Armed Robbery', location='Laascaanood', incident_summary='Shop robbed at gunpoint',
                 participants=[dict(role='Suspect', **SUSPECT), dict(role='Witness', **WITNESS)])
        if unit:
            p['owner_unit'] = unit
        p.update(over)
        return cid.create_case(self.conn, self.actor(who), p)

    def flagged(self, person_ref):
        pid = self.one('SELECT id FROM persons WHERE person_ref = %s', (person_ref,))
        return self.one("SELECT person_alert_flag(%s, %s)", (self.uid('cp.south'), pid))

    def test_case_participants_alerts_and_lifting(self):
        r = self.case()
        ref = r['case']['case_ref']
        self.assertTrue(ref.startswith('CS-DIR-CID-'))
        suspect, witness = r['participants']
        self.assertEqual((suspect['raises_alert'], witness['raises_alert']), (True, False))
        self.assertTrue(self.flagged(suspect['person_ref']))            # a checkpoint's yes/no screening finds the SAME person
        self.assertFalse(self.flagged(witness['person_ref']))
        # the checkpoint officer learns "yes" only: no CID detail is readable to them
        self.as_db_user('cp.south')
        self.assertEqual(self.one("SELECT count(*) FROM suspect_alerts"), 0)
        self.assertEqual(self.one("SELECT count(*) FROM crime_cases"), 0)
        self.done_as_db_user()
        d = cid.get_case(self.conn, self.actor('cid.officer'), ref)
        self.assertEqual(sorted(p['role'] for p in d['participants']), ['Suspect', 'Witness'])
        self.assertIn('Linked to CID case', d['participants'][0]['notes'])
        # the same person cannot be a second participant of the same case
        self.error(Duplicate, cid.add_participants, self.conn, self.actor('cid.officer'), ref,
                   dict(role='Suspect', person_ref=suspect['person_ref']))
        # lift: reason required, once, never deleted
        self.error(ValidationError, cid.lift_alert, self.conn, self.actor('cid.officer'), suspect['alert_ref'], ' ')
        self.assertEqual(cid.lift_alert(self.conn, self.actor('cid.officer'), suspect['alert_ref'], 'Cleared by the court')['alert_status'], 'Lifted')
        self.assertFalse(self.flagged(suspect['person_ref']))
        self.error(Duplicate, cid.lift_alert, self.conn, self.actor('cid.officer'), suspect['alert_ref'], 'again')
        self.as_db_user('cid.officer')
        self.no_delete("DELETE FROM suspect_alerts WHERE alert_ref = %s", (suspect['alert_ref'],))
        self.done_as_db_user()
        # unidentified suspects can be re-listed later by linking
        self.assertEqual(len(cid.list_alerts(self.conn, self.actor('cid.officer'), status='Lifted')['items']), 1)

    def test_bureaus_scope_cases_and_alerts(self):
        dir_case = self.case()['case']['case_ref']
        bur = self.case('cid.sool', 'BR-CID-SOOL', participants=[dict(role='Suspect', first_name='Maxamuud', second_name='Faarax', third_name='Yaasiin', date_of_birth='1979-09-09')])
        bref = bur['case']['case_ref']
        self.assertTrue(bref.startswith('CS-BR-CID-SOOL-'))
        self.assertEqual([c['case_ref'] for c in cid.list_cases(self.conn, self.actor('cid.sool'))['items']], [bref])
        self.assertEqual(sorted(c['case_ref'] for c in cid.list_cases(self.conn, self.actor('cid.officer'))['items']), sorted([dir_case, bref]))
        self.error(NotFound, cid.get_case, self.conn, self.actor('cid.sool'), dir_case)             # not the bureau's case
        self.error(PermissionDenied, cid.create_case, self.conn, self.actor('cid.sool'),
                   dict(category='Theft', participants=[]))                                           # default owner = directorate
        self.assertEqual(cid.get_case(self.conn, self.actor('chief'), bref)['case_ref'], bref)       # read-only root sees all
        self.error(PermissionDenied, cid.update_case, self.conn, self.actor('chief'), bref, dict(status='Closed'))
        # unrelated roles see nothing
        for who, unit in (('hr.officer', None), ('cmd.laas', 'ST-004'), ('fp.officer', None)):
            self.assertEqual(cid.list_cases(self.conn, self.actor(who, unit))['items'], [], who)
            self.assertEqual(cid.list_alerts(self.conn, self.actor(who, unit))['items'], [], who)
            self.error(PermissionDenied, cid.create_case, self.conn, self.actor(who, unit), dict(category='Theft'))

    def test_update_evidence_and_immutability(self):
        ref = self.case()['case']['case_ref']
        d = cid.update_case(self.conn, self.actor('cid.officer'), ref, dict(status='Referred to Court', notes='File sent'))
        self.assertEqual((d['status'], d['notes']), ('Referred to Court', 'File sent'))
        self.error(ValidationError, cid.update_case, self.conn, self.actor('cid.officer'), ref, dict(status='Won'))
        e = self.error(ValidationError, cid.update_case, self.conn, self.actor('cid.officer'), ref, dict(case_ref='X', owner_unit_id=1))
        self.assertEqual(sorted(e.extra['fields']), ['case_ref', 'owner_unit_id'])
        self.as_db_user('cid.officer')
        self.fails("UPDATE crime_cases SET case_ref = 'CS-HACK' WHERE case_ref = %s", (ref,), code='42501')
        self.no_delete("DELETE FROM crime_cases WHERE case_ref = %s", (ref,))
        self.done_as_db_user()
        ev = cid.add_evidence(self.conn, self.actor('cid.officer'), ref,
                              dict(file=self.upload('cid.officer', 'pdf'), caption='Witness statement', file_type='Statement'))
        self.assertTrue(ev['evidence']['evidence_ref'].startswith('EV-DIR-CID-'))
        self.error(ValidationError, cid.add_evidence, self.conn, self.actor('cid.officer'), ref, dict(file=self.upload('hr.officer', 'pdf')))   # not your upload
        self.error(ValidationError, cid.add_evidence, self.conn, self.actor('cid.officer'), ref,
                   dict(file=self.upload('cid.officer', 'pdf'), file_type='Rumour'))
        self.assertEqual(len(cid.get_case(self.conn, self.actor('cid.officer'), ref)['evidence']), 1)
        self.error(NotFound, cid.add_evidence, self.conn, self.actor('cmd.laas', 'ST-004'), ref, dict(file='x'))
        self.as_db_user('cid.officer')
        self.no_delete("UPDATE case_evidence SET caption = 'edited'")                                 # append-only (no UPDATE policy / trigger)
        self.done_as_db_user()

    def test_direct_listing_and_confirmation(self):
        self.error(ValidationError, cid.create_alert, self.conn, self.actor('cid.officer'), dict(person=dict(SUSPECT)))   # reason required
        a = cid.create_alert(self.conn, self.actor('cid.officer'), dict(person=dict(SUSPECT), reason='Intelligence report 77'))
        self.assertEqual(a['alert']['origin'], 'Direct Intelligence Listing')
        self.assertTrue(self.flagged(a['alert']['person_ref']))
        self.error(Duplicate, cid.create_alert, self.conn, self.actor('cid.officer'),
                   dict(person_ref=a['alert']['person_ref'], reason='again'))
        # a near-identical name asks for confirmation instead of silently creating a duplicate person
        e = self.error(NeedsConfirmation, cid.create_alert, self.conn, self.actor('cid.officer'),
                       dict(person=dict(SUSPECT, date_of_birth='1985-01-03'), reason='Second report'))
        self.assertEqual(e.extra['scope'], 'person')

    def test_cases_outside_the_state_are_refused_by_the_database(self):
        self.maintenance("""INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs) VALUES
                              ((SELECT id FROM org_units WHERE code='DIR-CID'), 'bureau', 'BR-CID-OK', 'CID OK', 'active', '{"region":"ETOG"}')""")
        self.cur.execute('SAVEPOINT s')
        try:
            self.cur.execute("""INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs) VALUES
                              ((SELECT id FROM org_units WHERE code='DIR-CID'), 'bureau', 'BR-CID-X', 'CID X', 'active', '{"region":"XREG"}')""")
            self.fail('a bureau must not claim an unlisted region')
        except psycopg2.Error as e:
            self.assertEqual(e.pgcode, '23514')
            self.cur.execute('ROLLBACK TO SAVEPOINT s')
        self.cur.execute('SAVEPOINT s')
        try:
            self.cur.execute("""INSERT INTO org_units (parent_id, unit_type, code, name, status, attrs) VALUES
                              ((SELECT id FROM org_units WHERE code='D-X'), 'station', 'ST-Y', 'Y', 'active', '{"region":"SOOL"}')""")
            self.fail('only bureaus claim a region')
        except psycopg2.Error as e:
            self.assertEqual(e.pgcode, '23514')
            self.cur.execute('ROLLBACK TO SAVEPOINT s')


# =====================================================================================================
class TestHr(DirCase):

    def test_register_officer_into_the_registry_with_history(self):
        r = officers.register_officer(self.conn, self.actor('hr.officer'), self.officer_payload())
        ref = r['officer']['service_ref']
        self.assertTrue(ref.startswith('POL-'))
        self.assertEqual(r['person']['full_name'], 'Mustafe Cabdillaahi Samatar Yuusuf')
        d = officers.get_officer(self.conn, self.actor('hr.officer'), ref)
        self.assertEqual(d['unit_code'], 'ST-004')
        self.assertEqual(d['history'][0]['entry_type'], 'Enlistment')
        self.assertEqual(d['details']['guarantor']['name'], 'Cali Nuur')
        # the person is global: a second registration of the same person is a duplicate officer, not a new person
        e = self.error(Duplicate, officers.register_officer, self.conn, self.actor('hr.officer'), self.officer_payload())
        self.assertEqual(e.extra['service_ref'], ref)
        self.assertEqual(self.one("SELECT count(*) FROM persons WHERE national_id = 'SO9100'"), 1)

    def test_registration_rules_and_boundaries(self):
        e = self.error(ValidationError, officers.register_officer, self.conn, self.actor('hr.officer'),
                       self.officer_payload(rank='Admiral', photo='', guarantor={}))
        for f in ('rank', 'photo', 'guarantor'):
            self.assertIn(f, e.extra['fields'])
        e = self.error(ValidationError, officers.register_officer, self.conn, self.actor('hr.officer'),
                       self.officer_payload(unit='ST-X'))
        self.assertIn('Northeastern State', e.message)
        self.error(PermissionDenied, officers.register_officer, self.conn, self.actor('cmd.laas', 'ST-004'), self.officer_payload('cmd.laas'))
        self.error(PermissionDenied, officers.register_officer, self.conn, self.actor('cid.officer'), self.officer_payload('cid.officer'))   # CID has no HR rights
        # a posting is data: a Fingerprint bureau can be a posting too
        self.assertEqual(officers.register_officer(self.conn, self.actor('hr.officer'),
                         self.officer_payload(unit='BR-FP-SANAAG', person=dict(RECRUIT, national_id='SO9101', first_name='Cabdi')))
                         ['officer']['unit']['region'], 'Sanaag')

    def test_roster_is_national_for_hr_and_scoped_for_commanders(self):
        a = self.mk_officer('ST-004')
        b = self.mk_officer('ST-007')
        names = lambda who, unit=None: sorted(o['service_ref'] for o in officers.list_officers(self.conn, self.actor(who, unit))['items'])
        self.assertEqual(names('hr.officer'), sorted([a, b]))
        self.assertEqual(names('cmd.laas', 'ST-004'), [a])
        self.assertEqual(names('cmd.buu', 'ST-007'), [b])
        self.assertEqual(names('rc.sool'), [a])                         # the Sool commander: ST-004 is Sool, Buuhoodle is East Togdheer
        self.assertEqual(names('cid.officer'), [])
        self.assertIsNone(officers.get_officer(self.conn, self.actor('cmd.laas', 'ST-004'), a)['details'])    # guarantor & documents are HR-only
        self.error(NotFound, officers.get_officer, self.conn, self.actor('cmd.laas', 'ST-004'), b)

    def test_duty_status_is_audited_and_termination_goes_through_conduct(self):
        ref = self.mk_officer()
        self.error(ValidationError, officers.set_duty_status, self.conn, self.actor('hr.officer'), ref, 'Leave', '')
        self.error(PermissionDenied, officers.set_duty_status, self.conn, self.actor('cmd.laas', 'ST-004'), ref, 'Leave', 'x')
        self.assertEqual(officers.set_duty_status(self.conn, self.actor('hr.officer'), ref, 'Leave', 'Annual leave')['duty_status'], 'Leave')
        self.error(ValidationError, officers.set_duty_status, self.conn, self.actor('hr.officer'), ref, 'Leave', 'again')
        e = self.error(PermissionDenied, officers.set_duty_status, self.conn, self.actor('hr.officer'), ref, 'Terminated', 'shortcut')
        self.assertIn('Formal Dismissal', e.message)
        hist = officers.get_officer(self.conn, self.actor('hr.officer'), ref)['history']
        self.assertIn('Annual leave', hist[0]['summary'])
        self.as_db_user('hr.officer')                                                 # rank is never a plain UPDATE
        self.fails("UPDATE officers SET rank = 'General' WHERE service_ref = %s", (ref,), code='42501')
        self.no_delete("DELETE FROM officers WHERE service_ref = %s", (ref,))
        self.done_as_db_user()

    def test_conduct_filing_review_and_effects(self):
        off = self.mk_officer('ST-004', 'Sergeant')
        other = self.mk_officer('ST-007', 'Sergeant')
        c = conduct.submit(self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off))
        ref = c['conduct']['action_ref']
        self.assertEqual((c['conduct']['status'], c['conduct']['filed_for_unit']), ('Submitted to HR', 'ST-004'))
        # T2: only against officers at or below your unit
        self.error(NotFound, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(other))
        self.error(PermissionDenied, conduct.submit, self.conn, self.actor('hr.officer'), self.conduct_payload(off))
        self.error(PermissionDenied, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, unit='ST-007'))
        r = conduct.submit(self.conn, self.actor('rc.sool'), self.conduct_payload(off, unit='SOOL', action_type='Disciplinary / Penalty',
                           classification='Official Reprimand', proposed_rank=None))
        self.assertEqual(r['conduct']['filed_for_unit'], 'SOOL')                      # a commander files from above
        # rules from policy data
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, narrative='Good.'))
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, proposed_rank='Corporal'))   # not higher
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, proposed_rank=None))
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'),
                   self.conduct_payload(off, classification='Official Reprimand'))        # classification belongs to the other type
        # review is national and never by the filer
        self.error(PermissionDenied, conduct.review, self.conn, self.actor('cmd.laas', 'ST-004'), ref, 'approve')
        self.error(PermissionDenied, conduct.review, self.conn, self.actor('rc.sool'), ref, 'approve')
        adm = conduct.submit(self.conn, self.actor('admin'), self.conduct_payload(off))['conduct']['action_ref']     # admin can file ...
        e = self.error(PermissionDenied, conduct.review, self.conn, self.actor('admin'), adm, 'approve')               # ... but not review its own file
        self.assertIn('separation', e.message.lower())
        self.assertEqual(conduct.review(self.conn, self.actor('hr.officer'), ref, 'review')['status'], 'Under HR Review')
        self.error(ValidationError, conduct.review, self.conn, self.actor('hr.officer'), ref, 'reject')                 # reason needed
        out = conduct.review(self.conn, self.actor('hr.reviewer'), ref, 'approve', 'Verified against the record')
        self.assertEqual((out['status'], out['rank_applied'], out['officer']['rank']), ('Verified & Approved', True, 'Inspector'))
        d = officers.get_officer(self.conn, self.actor('hr.officer'), off)
        self.assertEqual(d['rank'], 'Inspector')
        self.assertEqual(d['history'][0]['entry_type'], 'Rank Advancement')
        self.assertEqual((d['history'][0]['from_rank'], d['history'][0]['to_rank']), ('Sergeant', 'Inspector'))
        self.error(Duplicate, conduct.review, self.conn, self.actor('hr.officer'), ref, 'approve')                      # closed
        # a stale proposal is re-checked against the CURRENT rank at approval (the officer is an Inspector now)
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, proposed_rank='Inspector'))
        self.error(ValidationError, conduct.submit, self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off, proposed_rank='Sergeant'))
        # a dismissal ends the career: duty status Terminated, and nobody can reinstate through the duty route
        dis = conduct.submit(self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(
            off, action_type='Disciplinary / Penalty', classification='Formal Dismissal', proposed_rank=None))['conduct']['action_ref']
        o = conduct.review(self.conn, self.actor('hr.officer'), dis, 'approve')
        self.assertEqual((o['duty_applied'], o['officer']['duty_status']), ('Terminated', 'Terminated'))
        self.error(PermissionDenied, officers.set_duty_status, self.conn, self.actor('hr.officer'), off, 'Active', 'oops')
        # visibility: the filer's commander sees the file at the officer's unit; the other station does not
        self.assertIn(ref, [x['action_ref'] for x in conduct.list_conduct(self.conn, self.actor('cmd.laas', 'ST-004'))['items']])
        self.assertEqual(conduct.list_conduct(self.conn, self.actor('cmd.buu', 'ST-007'))['items'], [])
        self.assertTrue(any(x['can_review'] for x in conduct.list_conduct(self.conn, self.actor('hr.officer'), status='Submitted to HR')['items']))

    def test_conduct_rejection_has_no_effect(self):
        off = self.mk_officer()
        ref = conduct.submit(self.conn, self.actor('cmd.laas', 'ST-004'), self.conduct_payload(off))['conduct']['action_ref']
        self.assertEqual(conduct.review(self.conn, self.actor('hr.officer'), ref, 'reject', 'Not substantiated')['rank_applied'], False)
        self.assertEqual(officers.get_officer(self.conn, self.actor('hr.officer'), off)['rank'], 'Sergeant')
        self.as_db_user('hr.officer')
        self.fails("UPDATE conduct_actions SET narrative = 'rewritten' WHERE action_ref = %s", (ref,), code='42501')
        self.done_as_db_user()


# =====================================================================================================
class TestStructureIsData(DirCase):
    """New bureaus, branches and assignments are admin actions on data — no code change anywhere."""

    def test_new_cid_bureau_for_east_togdheer_works_the_moment_it_exists(self):
        u = structure.create_unit(self.conn, self.actor('admin'), dict(parent='DIR-CID', unit_type='bureau', code='br-cid-etog',
                                                                      name='CID East Togdheer Bureau', attrs={'region': 'ETOG'}))['unit']
        self.assertEqual((u['code'], u['region_code'], u['in_state']), ('BR-CID-ETOG', 'ETOG', True))
        g = structure.grant(self.conn, self.actor('admin'), dict(username='cid.sool', role='cid_officer', unit='BR-CID-ETOG'))
        self.assertTrue(g['assignment']['id'])
        r = cid.create_case(self.conn, self.actor('cid.sool'), dict(category='Smuggling', owner_unit='BR-CID-ETOG'))
        self.assertTrue(r['case']['case_ref'].startswith('CS-BR-CID-ETOG-'))
        # and the same data-only rule binds the boundary: a bureau cannot claim a region outside the state
        e = self.error(ValidationError, structure.create_unit, self.conn, self.actor('admin'),
                       dict(parent='DIR-CID', unit_type='bureau', code='BR-CID-X', name='Bad', attrs={'region': 'XREG'}))
        self.assertIn('not one of the state regions', e.message)
        self.error(ValidationError, structure.create_unit, self.conn, self.actor('admin'),
                   dict(parent='DIR-CID', unit_type='station', code='ST-NOPE', name='Wrong parent type'))
        self.error(ValidationError, structure.create_unit, self.conn, self.actor('admin'),
                   dict(parent='HQ', unit_type='region', code='NEWREG', name='Invented region'))
        self.error(Duplicate, structure.create_unit, self.conn, self.actor('admin'),
                   dict(parent='DIR-CID', unit_type='bureau', code='BR-CID-SOOL', name='again'))

    def test_new_branches_under_districts_and_assignments_are_scoped(self):
        s = structure.create_unit(self.conn, self.actor('builder.sool'), dict(parent='D-CAYNABO', unit_type='station', code='ST-CAY-2', name='Caynabo North'))
        self.assertEqual(s['unit']['region'], 'Sool')
        self.error(PermissionDenied, structure.create_unit, self.conn, self.actor('rc.sool'),
                   dict(parent='D-CAYNABO', unit_type='station', code='ST-Z', name='regional commanders do not manage units'))
        self.error(PermissionDenied, structure.create_unit, self.conn, self.actor('builder.sool'),
                   dict(parent='D-BURAO', unit_type='station', code='ST-BUR-9', name='Not my region'))
        self.error(PermissionDenied, structure.create_unit, self.conn, self.actor('cmd.laas', 'ST-004'),
                   dict(parent='D-CAYNABO', unit_type='station', code='ST-Q', name='x'))
        # no privilege escalation: rc.sool cannot hand out roles holding permissions it lacks (person:create ...)
        self.error(PermissionDenied, structure.grant, self.conn, self.actor('rc.sool'), dict(username='st.laas', role='station_commander', unit='ST-004'))
        self.error(PermissionDenied, structure.grant, self.conn, self.actor('rc.sool'), dict(username='st.laas', role='station_commander', unit='ST-007'))
        g = structure.grant(self.conn, self.actor('rc.sool'), dict(username='st.laas', role='regional_commander', unit='ST-004'))
        self.error(Duplicate, structure.grant, self.conn, self.actor('rc.sool'), dict(username='st.laas', role='regional_commander', unit='ST-004'))
        self.assertTrue(any(a['id'] == g['assignment']['id'] for a in structure.list_assignments(self.conn, self.actor('rc.sool'))['items']))
        self.assertEqual(structure.list_assignments(self.conn, self.actor('cmd.laas', 'ST-004'))['items'], [])
        self.error(PermissionDenied, structure.revoke, self.conn, self.actor('cmd.buu', 'ST-007'), g['assignment']['id'])
        self.assertTrue(structure.revoke(self.conn, self.actor('rc.sool'), g['assignment']['id'])['revoked'])
        self.error(Duplicate, structure.revoke, self.conn, self.actor('rc.sool'), g['assignment']['id'])
        # a new unit is usable at once: a station added by data can receive clearance intake
        self.assertEqual(structure.update_unit(self.conn, self.actor('admin'), 'ST-CAY-2', dict(status='inactive'))['unit']['status'], 'inactive')

    def test_move_rename_and_vocabularies(self):
        structure.create_unit(self.conn, self.actor('admin'), dict(parent='DIR-CID', unit_type='bureau', code='BR-T', name='Temp'))
        self.assertEqual(structure.move_unit(self.conn, self.actor('admin'), 'BR-T', 'DIR-FP')['unit']['parent_code'], 'DIR-FP')
        self.error(ValidationError, structure.move_unit, self.conn, self.actor('admin'), 'DIR-CID', 'BR-T')       # directorate under a bureau
        self.error(ValidationError, structure.update_unit, self.conn, self.actor('admin'), 'BR-T', dict(unit_type='station'))
        self.assertEqual(structure.update_unit(self.conn, self.actor('admin'), 'BR-T', dict(name='Renamed'))['unit']['name'], 'Renamed')
        v = structure.vocabularies(self.conn, self.actor('admin'))
        self.assertEqual(v['regions'], ['SOOL', 'SANAAG', 'ETOG'])
        self.assertEqual(v['officer']['ranks'][0], 'Constable')
        names = json.dumps(v).lower() + json.dumps(structure.list_units(self.conn, self.actor('chief'))['items'], default=str).lower()
        for banned in ('hargeisa', 'waqooyi'):
            self.assertNotIn(banned, names)


# =====================================================================================================
class TestHttpDirectorate(DirCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['SENTINEL_DATABASE_URL'] = cls.uri
        os.environ['SENTINEL_UPLOAD_DIR'] = os.path.join(pg_support.ROOT, 'tests', '_uploads_tmp3')
        cls.srv = server.make_server('127.0.0.1', 0)
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        import shutil
        shutil.rmtree(os.environ.pop('SENTINEL_UPLOAD_DIR'), ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.clean()

    def tearDown(self):
        self.clean()
        super().tearDown()

    def clean(self):
        self.conn.rollback()
        self.cur.execute('RESET ROLE')
        self.cur.execute('TRUNCATE persons, crime_cases, clearance_applications, officers, conduct_actions, ref_sequences, audit_events, '
                         'uploads RESTART IDENTITY CASCADE')
        self.cur.execute('DELETE FROM user_assignments WHERE id > (SELECT max(id) FROM user_assignments WHERE granted_by IS NULL)')
        self.conn.commit()

    def call(self, method, path, body=None, user=None, unit=None, raw=None, headers=None):
        h = {'Content-Type': 'application/json', **(headers or {})}
        if user:
            h['X-Dev-User'] = user
        if unit:
            h['X-Unit'] = unit
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                b = r.read()
                return r.status, (json.loads(b) if r.headers['Content-Type'].startswith('application/json') else b)
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b[:1] == b'{' else b)

    def put(self, user, name='a.png', data=PNG):
        s, b = self.call('POST', '/api/uploads', user=user, raw=data, headers={'X-Filename': name, 'Content-Type': 'application/octet-stream'})
        self.assertEqual(s, 201, b)
        return b['name']

    def test_authentication_and_the_one_public_endpoint(self):
        for path in ('/api/clearance-applications', '/api/crime-cases', '/api/officers', '/api/conduct', '/api/suspect-alerts',
                     '/api/admin/units', '/api/directorate/vocabularies'):
            self.assertEqual(self.call('GET', path)[0], 401, path)
        s, b = self.call('GET', '/api/verify/CL-DIR-FP-2026-000099')                           # public: answers without login
        self.assertEqual((s, b['valid']), (200, False))

    def test_clearance_end_to_end_over_http(self):
        body = dict(unit='ST-004', purpose='Education', applicant=dict(APPLICANT), applicant_photo=self.put('st.laas'),
                    applicant_docs=[self.put('st.laas', 'a.pdf', b'%PDF-1.4 a'), self.put('st.laas', 'b.pdf', b'%PDF-1.4 b')],
                    guardian=dict(GUARDIAN), guardian_relationship='Uncle',
                    guardian_docs=[self.put('st.laas', 'c.pdf', b'%PDF-1.4 c'), self.put('st.laas', 'd.pdf', b'%PDF-1.4 d')])
        s, b = self.call('POST', '/api/clearance-applications', body, 'st.laas')
        self.assertEqual(s, 201, b)
        ref = b['application']['application_ref']
        self.assertEqual(self.call('POST', f'/api/clearance-applications/{ref}/decision', dict(decision='approve'), 'st.laas')[0], 403)
        s, b = self.call('POST', f'/api/clearance-applications/{ref}/approve', {}, 'fp.officer')
        self.assertEqual((s, b['error']), (400, 'review_period_active'))
        self.maintenance_http("UPDATE clearance_applications SET created_at = now() - interval '13 hours'")
        s, b = self.call('POST', f'/api/clearance-applications/{ref}/decision', dict(decision='approve'), 'fp.officer')
        self.assertEqual((s, b['status']), (200, 'Approved'))
        number = b['certificate_number']
        s, p = self.call('POST', f'/api/clearance-applications/{ref}/print', {}, 'fp.officer')
        self.assertEqual((s, p['print_count']), (200, 1))
        self.assertEqual(self.call('POST', f'/api/clearance-applications/{ref}/print', {}, 'st.laas')[0], 403)
        s, v = self.call('GET', f'/api/verify/{number}')
        self.assertEqual((s, v['valid'], v['holder']), (200, True, 'Faadumo J. W. I.'))
        s, lst = self.call('GET', '/api/clearance-applications?status=Approved', None, 'st.laas')
        self.assertEqual([a['application_ref'] for a in lst['items']], [ref])
        self.assertEqual(self.call('GET', f'/api/clearance-applications/{ref}', None, 'cmd.buu')[0], 404)

    def maintenance_http(self, sql):
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute(sql)
        self.conn.commit()

    def test_cid_hr_and_admin_over_http(self):
        s, b = self.call('POST', '/api/crime-cases', dict(category='Assault', participants=[dict(role='Suspect', **SUSPECT)]), 'cid.officer')
        self.assertEqual(s, 201, b)
        ref = b['case']['case_ref']
        self.assertEqual(self.call('PATCH', f'/api/crime-cases/{ref}', dict(changes=dict(status='Closed')), 'cid.officer')[1]['status'], 'Closed')
        self.assertEqual(self.call('GET', f'/api/crime-cases/{ref}', None, 'hr.officer')[0], 404)
        s, al = self.call('GET', '/api/suspect-alerts', None, 'cid.officer')
        self.assertEqual(len(al['items']), 1)
        self.assertEqual(self.call('POST', f'/api/suspect-alerts/{al["items"][0]["alert_ref"]}/lift', dict(reason='Mistaken identity'), 'cid.officer')[0], 200)
        # HR
        body = dict(unit='ST-004', rank='Sergeant', unit_role='General Patrol', date_of_enlistment='2019-01-01', person=dict(RECRUIT),
                    photo=self.put('hr.officer'), guarantor=dict(name='Cali Nuur', address='Ceerigaabo', contact='+252 1'),
                    doc1_type='National ID', doc1_file=self.put('hr.officer', 'id.pdf', b'%PDF-1.4 x'))
        s, o = self.call('POST', '/api/officers', body, 'hr.officer')
        self.assertEqual(s, 201, o)
        oref = o['officer']['service_ref']
        s, c = self.call('POST', '/api/conduct/submit', dict(officer=oref, action_type='Disciplinary / Penalty', classification='Temporary Suspension',
                         narrative='Absent from post for three consecutive shifts without notice.'), 'cmd.laas', 'ST-004')
        self.assertEqual(s, 201, c)
        aref = c['conduct']['action_ref']
        self.assertEqual(self.call('POST', f'/api/conduct/{aref}/review', dict(decision='approve'), 'cmd.laas', 'ST-004')[0], 403)
        s, r = self.call('POST', f'/api/conduct/{aref}/review', dict(decision='approve'), 'hr.officer')
        self.assertEqual((s, r['duty_applied']), (200, 'Suspended'))
        self.assertEqual(self.call('GET', f'/api/officers/{oref}', None, 'hr.officer')[1]['duty_status'], 'Suspended')
        # admin
        s, u = self.call('POST', '/api/admin/units', dict(parent='D-OODWEYNE', unit_type='checkpoint', code='CP-OOD-1', name='Oodweyne Checkpoint'), 'admin')
        self.assertEqual((s, u['unit']['region']), (201, 'East Togdheer'))
        self.assertEqual(self.call('POST', '/api/admin/units', dict(parent='D-OODWEYNE', unit_type='checkpoint', code='CP-OOD-2', name='x'), 'st.laas', 'ST-004')[0], 403)
        self.assertEqual(self.call('GET', '/api/directorate/vocabularies', None, 'hr.officer')[1]['regions'], ['SOOL', 'SANAAG', 'ETOG'])


if __name__ == '__main__':
    unittest.main()
