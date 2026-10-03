"""Common fixtures for identity tests (rolled back per test)."""
import contextlib
import unittest

import psycopg2

from app.db import Actor
from . import pg_support


class DbCase(unittest.TestCase):
    DBNAME = 'sentinel_identity_test'
    uri = None

    @classmethod
    def setUpClass(cls):
        cls.uri = pg_support.create_database(cls.DBNAME)

    def setUp(self):
        self.conn = psycopg2.connect(self.uri)
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    # ---- raw helpers ----------------------------------------------------------
    def one(self, sql, params=None):
        self.cur.execute(sql, params)
        r = self.cur.fetchone()
        return r[0] if r else None

    def all(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur.fetchall()

    def uid(self, username):
        return self.one('SELECT id FROM users WHERE username=%s', (username,))

    def unit(self, code):
        return self.one('SELECT id FROM org_units WHERE code=%s', (code,))

    def new_user(self, username, role, unit, descendants=True):
        u = self.one("INSERT INTO users(username,display_name,password_hash) VALUES(%s,%s,'!t') RETURNING id",
                     (username, username))
        self.cur.execute('INSERT INTO user_assignments(user_id,role_id,unit_id,include_descendants) '
                         'VALUES(%s,(SELECT id FROM roles WHERE code=%s),%s,%s)',
                         (u, role, self.unit(unit), descendants))
        return u

    def actor(self, username, unit=None):
        return Actor(user_id=self.uid(username), username=username, unit_id=self.unit(unit) if unit else None)

    def bind(self, username, reason=''):
        """Act as `username` for raw SQL in this transaction (what the API does per request)."""
        self.cur.execute("SELECT set_config('app.user_id',%s,true), set_config('app.change_reason',%s,true)",
                         (str(self.uid(username)), reason))

    def raw_person(self, name='Ayaan Cabdi Xasan Axmed', dob='1990-05-17', pob='Laascaanood', **extra):
        """Insert a person AS an authenticated officer (goes through the guard)."""
        self.bind('fp.officer')
        parts = (name.split() + [None] * 4)[:4]
        cols = dict(first_name=parts[0], second_name=parts[1], third_name=parts[2], fourth_name=parts[3],
                    date_of_birth=dob, place_of_birth=pob, **extra)
        ref = self.one("SELECT next_ref('P')")
        keys = ['person_ref', 'full_name'] + list(cols)
        return self.one(f"INSERT INTO persons ({','.join(keys)}) VALUES ({','.join(['%s'] * len(keys))}) RETURNING id",
                        [ref, ''] + list(cols.values()))

    def fails(self, sql, params=None, code=None):
        self.cur.execute('SAVEPOINT chk')
        try:
            self.cur.execute(sql, params)
        except psycopg2.Error as e:
            self.cur.execute('ROLLBACK TO SAVEPOINT chk')
            if code:
                self.assertEqual(e.pgcode, code, str(e))
            return e
        self.cur.execute('RELEASE SAVEPOINT chk')
        self.fail('statement should have failed: ' + sql[:100])
