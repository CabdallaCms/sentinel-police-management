#!/usr/bin/env python3
"""
Enterprise Scaling Refactor — Zero-Code Provisioning Unit Tests
No DB required — uses mock cursor to validate code generation and validation logic.
Run: python3 backend/test_enterprise.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import enterprise

class MockRow(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
    def __getitem__(self, key):
        return super().get(key)

class MockCursor:
    def __init__(self):
        self.tables = {
            'regions': [],
            'districts': [],
            'villages': [],
            'facility_types': [],
            'facilities': [],
            'police_stations': [],
        }
        self.last_result = None
        self._id_counter = 1

    def execute(self, sql, params=None):
        sql_low = sql.strip().lower()
        params = params or ()
        # Simplified mock logic for existence checks and inserts
        if 'select 1 from regions where code=%s' in sql_low:
            code = params[0]
            self.last_result = next((r for r in self.tables['regions'] if r['code']==code), None)
            return self
        if 'select 1 from regions where lower(name)=lower(%s)' in sql_low:
            name = params[0].lower()
            self.last_result = next((r for r in self.tables['regions'] if r['name'].lower()==name), None)
            return self
        if 'insert into regions' in sql_low:
            code, name, desc, created_by = params
            row = {'id': self._id_counter, 'code': code, 'name': name, 'description': desc, 'is_active': True, 'created_at': '2026-01-01 00:00:00'}
            self._id_counter+=1
            self.tables['regions'].append(row)
            self.last_result = row
            return self
        if 'select * from regions where code=%s' in sql_low and 'or lower(name)' in sql_low:
            ref = params[0]
            ref2 = params[1] if len(params)>1 else ref
            row = next((r for r in self.tables['regions'] if r['code']==ref or r['name'].lower()==ref2.lower()), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from regions where id=%s' in sql_low:
            row = next((r for r in self.tables['regions'] if r['id']==params[0]), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from regions where' in sql_low and 'code=%s' in sql_low and 'id=%s' not in sql_low and 'lower' not in sql_low:
            # for list or single code lookup
            code = params[0]
            row = next((r for r in self.tables['regions'] if r['code']==code), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select 1 from districts where code=%s' in sql_low:
            code = params[0]
            self.last_result = next((r for r in self.tables['districts'] if r['code']==code), None)
            return self
        if 'select 1 from districts where region_id=%s and lower(name)=lower(%s)' in sql_low:
            rid, name = params
            self.last_result = next((r for r in self.tables['districts'] if r['region_id']==rid and r['name'].lower()==name.lower()), None)
            return self
        if 'insert into districts' in sql_low:
            rid, code, name, desc, created_by = params
            row = {'id': self._id_counter, 'region_id': rid, 'code': code, 'name': name, 'description': desc, 'is_active': True}
            self._id_counter+=1
            self.tables['districts'].append(row)
            self.last_result = row
            return self
        if 'select d.*, r.name as region_name' in sql_low:
            code = params[0]
            d = next((r for r in self.tables['districts'] if r['code']==code), None)
            if d:
                r = next((reg for reg in self.tables['regions'] if reg['id']==d['region_id']), {})
                merged = {**d, 'region_name': r.get('name'), 'region_code': r.get('code')}
                self.last_result = MockRow(merged)
            else:
                self.last_result = None
            return self
        if 'select * from districts where id=%s' in sql_low:
            row = next((r for r in self.tables['districts'] if r['id']==params[0]), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from districts where region_id=%s and (code=%s or lower(name)=lower(%s))' in sql_low:
            rid, code, name = params
            row = next((r for r in self.tables['districts'] if r['region_id']==rid and (r['code']==code or r['name'].lower()==name.lower())), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from districts where code=%s or lower(name)=lower(%s)' in sql_low:
            ref = params[0]
            ref2 = params[1]
            row = next((r for r in self.tables['districts'] if r['code']==ref or r['name'].lower()==ref2.lower()), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from facility_types where code=%s' in sql_low or 'select * from facility_types where id=%s' in sql_low:
            # handle both
            if 'code=%s' in sql_low:
                # check code OR name lower
                if 'or lower(name)' in sql_low:
                    ref = params[0]
                    ref2 = params[1] if len(params)>1 else ref
                    row = next((r for r in self.tables['facility_types'] if r['code']==ref or r['name'].lower()==ref2.lower()), None)
                else:
                    row = next((r for r in self.tables['facility_types'] if r['code']==params[0]), None)
            else:
                row = next((r for r in self.tables['facility_types'] if r['id']==params[0]), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select id from facility_types where code=' in sql_low:
            code = params[0] if params else 'POLICE_STATION'
            row = next((r for r in self.tables['facility_types'] if r['code']==code), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from facilities where facility_id=%s or code=%s' in sql_low:
            ref = params[0]
            row = next((r for r in self.tables['facilities'] if r['facility_id']==ref or r['code']==ref), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select * from facilities where id=%s' in sql_low:
            row = next((r for r in self.tables['facilities'] if r['id']==params[0]), None)
            self.last_result = MockRow(row) if row else None
            return self
        if 'select facility_id from facilities where facility_id ilike' in sql_low:
            # return None to generate first id
            self.last_result = None
            return self
        if 'select code from facilities where code ilike' in sql_low:
            # return empty iterator for code generation
            self._iter_rows = []
            return self
        if 'select 1 from facilities where facility_id=%s' in sql_low:
            fid = params[0]
            self.last_result = next((r for r in self.tables['facilities'] if r['facility_id']==fid), None)
            return self
        if 'select 1 from facilities where code=%s' in sql_low:
            code = params[0]
            self.last_result = next((r for r in self.tables['facilities'] if r['code']==code), None)
            return self
        if 'insert into facilities' in sql_low:
            # params: facility_id,name,code,facility_type_id,region_id,district_id,village_id,parent_id,tier,status,phone,cell_cap,notes,created_by,legacy_region,legacy_district,legacy_village
            fid, name, code, ft_id, rid, did, vid, parent, tier, status, phone, cell_cap, notes, created_by, leg_r, leg_d, leg_v = params
            row = {
                'id': self._id_counter,
                'facility_id': fid,
                'name': name,
                'code': code,
                'facility_type_id': ft_id,
                'region_id': rid,
                'district_id': did,
                'village_id': vid,
                'parent_facility_id': parent,
                'station_tier': tier,
                'operational_status': status,
                'contact_phone': phone,
                'cell_capacity': cell_cap,
                'notes': notes,
                'is_active': True,
                'created_at': '2026-01-01 00:00:00',
            }
            self._id_counter+=1
            self.tables['facilities'].append(row)
            self.last_result = row
            return self
        if 'select f.*, ft.code as facility_type_code' in sql_low:
            fid = params[0]
            f = next((r for r in self.tables['facilities'] if r['facility_id']==fid), None)
            if f:
                ft = next((r for r in self.tables['facility_types'] if r['id']==f['facility_type_id']), {})
                reg = next((r for r in self.tables['regions'] if r['id']==f['region_id']), {}) if f.get('region_id') else {}
                dist = next((r for r in self.tables['districts'] if r['id']==f['district_id']), {}) if f.get('district_id') else {}
                merged = {
                    **f,
                    'facility_type_code': ft.get('code'),
                    'facility_type_name': ft.get('name'),
                    'facility_category': ft.get('category'),
                    'region_name': reg.get('name'),
                    'region_code': reg.get('code'),
                    'district_name': dist.get('name'),
                }
                self.last_result = MockRow(merged)
            else:
                self.last_result = None
            return self
        if 'select * from villages where' in sql_low:
            self.last_result = None
            return self
        if 'insert into villages' in sql_low:
            # district_id, name, created_by or with type
            if len(params)==3:
                did, name, created_by = params
                row = {'id': self._id_counter, 'district_id': did, 'name': name, 'village_type': None}
            else:
                did, name, vtype, created_by = params
                row = {'id': self._id_counter, 'district_id': did, 'name': name, 'village_type': vtype}
            self._id_counter+=1
            self.tables['villages'].append(row)
            self.last_result = MockRow(row)
            return self
        # default: no result
        self.last_result = None
        return self

    def fetchone(self):
        if isinstance(self.last_result, dict):
            return MockRow(self.last_result)
        return self.last_result

    def __iter__(self):
        if hasattr(self, '_iter_rows'):
            return iter(self._iter_rows)
        if isinstance(self.last_result, list):
            return iter(self.last_result)
        return iter([])

    def fetchall(self):
        if hasattr(self, '_iter_rows'):
            return self._iter_rows
        if isinstance(self.last_result, list):
            return self.last_result
        return []

def test_region_creation():
    c = MockCursor()
    user = {'id': 1}
    r = enterprise.create_region(c, user, {'name': 'Sool'})
    assert r['code'] == 'SOO' or r['code'].startswith('SOO')
    assert r['name'] == 'Sool'
    print(f"ok: region creation Sool → {r['code']}")

    # duplicate name should fail
    try:
        enterprise.create_region(c, user, {'name': 'Sool'})
        assert False, "should have raised duplicate"
    except ValueError as e:
        assert 'already exists' in str(e)
        print("ok: duplicate region rejected")

    # custom code
    r2 = enterprise.create_region(c, user, {'name': 'Sanaag', 'code': 'SAN'})
    assert r2['code'] == 'SAN'
    print(f"ok: region Sanaag custom code {r2['code']}")

def test_district_creation():
    c = MockCursor()
    user = {'id': 1}
    # need region
    c.tables['regions'].append({'id': 1, 'code': 'SOL', 'name': 'Sool'})
    c._id_counter = 2
    d = enterprise.create_district(c, user, {'name': 'Taleh', 'region': 'SOL'})
    assert d['code'].startswith('SOL-')
    assert d['name'] == 'Taleh'
    print(f"ok: district Taleh → {d['code']} in SOL")

    # duplicate in same region should fail
    try:
        enterprise.create_district(c, user, {'name': 'Taleh', 'region': 'SOL'})
        assert False
    except ValueError:
        print("ok: duplicate district in same region rejected")

def test_facility_code_generation():
    c = MockCursor()
    user = {'id': 1}
    # Seed facility types
    c.tables['facility_types'].append({'id': 1, 'code': 'POLICE_STATION', 'name': 'Local Police Station', 'category': 'STATION', 'is_global': False})
    c.tables['facility_types'].append({'id': 2, 'code': 'CHECKPOINT', 'name': 'Checkpoint', 'category': 'CHECKPOINT', 'is_global': False})
    c.tables['facility_types'].append({'id': 3, 'code': 'AIRPORT_BRANCH', 'name': 'Airport Branch', 'category': 'SPECIALIZED_BRANCH', 'is_global': False})
    c.tables['facility_types'].append({'id': 4, 'code': 'CID_BRANCH', 'name': 'CID Branch', 'category': 'SPECIALIZED_BRANCH', 'is_global': False})
    c.tables['facility_types'].append({'id': 5, 'code': 'CENTRAL_REGISTRATION', 'name': 'Central Police Registration Office', 'category': 'STATIC_HQ', 'is_global': True})
    # regions/districts
    c.tables['regions'].append({'id': 10, 'code': 'SOL', 'name': 'Sool'})
    c.tables['districts'].append({'id': 20, 'region_id': 10, 'code': 'SOL-TAL', 'name': 'Taleh'})
    c._id_counter = 100

    fac = enterprise.create_facility(c, user, {
        'name': 'Taleh Police Station',
        'facility_type': 'POLICE_STATION',
        'region': 'SOL',
        'district': 'Taleh',
        'contact_phone': '+252 63 555 0001',
        'station_tier': 'District HQ',
        'cell_capacity': 10
    })
    assert fac['code'] == 'SOL-TAL-ST-001', f"got {fac['code']}"
    assert fac['facility_id'].startswith('ST-')
    print(f"ok: facility Taleh Police Station → code {fac['code']}, id {fac['facility_id']}")

    fac2 = enterprise.create_facility(c, user, {
        'name': 'Taleh Checkpoint',
        'facility_type': 'CHECKPOINT',
        'region': 'SOL',
        'district': 'Taleh',
        'contact_phone': '+252 63 555 0002',
    })
    assert fac2['code'] == 'SOL-TAL-CP-001'
    print(f"ok: facility Taleh Checkpoint → {fac2['code']}")

    fac3 = enterprise.create_facility(c, user, {
        'name': 'Lasanod Airport',
        'facility_type': 'AIRPORT_BRANCH',
        'region': 'SOL',
        'district': 'Taleh',
        'contact_phone': '+252 63 555 0003',
    })
    assert 'AP' in fac3['code']
    print(f"ok: facility Lasanod Airport (specialized branch) → {fac3['code']}")

    # global HQ should not require region/district
    fac4 = enterprise.create_facility(c, user, {
        'name': 'Central Police Registration Office',
        'facility_type': 'CENTRAL_REGISTRATION',
        'contact_phone': '+252 63 555 0000',
    })
    assert fac4['code']
    print(f"ok: STATIC_HQ Central Registration → {fac4['code']} (no region required)")

    # missing region for non-global should fail
    try:
        enterprise.create_facility(c, user, {
            'name': 'Bad Facility',
            'facility_type': 'POLICE_STATION',
            'contact_phone': '123',
        })
        assert False
    except ValueError as e:
        assert 'Region is required' in str(e)
        print("ok: non-global facility without region rejected")

def test_facility_scope():
    # Test facility_scope helper
    admin_user = {'role': 'SystemAdmin'}
    scope = enterprise.facility_scope(admin_user)
    assert scope['scope_type'] == 'global'
    print("ok: facility_scope admin → global")

    station_user = {'role': 'station_officer', 'facility_id': 5, 'region_id': 1, 'district_id': 2}
    scope = enterprise.facility_scope(station_user)
    assert scope['scope_type'] == 'facility'
    assert scope['facility_id'] == 5
    print("ok: facility_scope station_officer → facility")

    checkpoint_user = {'role': 'checkpoint_officer', 'location_scope': 'South'}
    scope = enterprise.facility_scope(checkpoint_user)
    assert scope['scope_type'] == 'legacy_checkpoint'
    print("ok: facility_scope checkpoint legacy fallback")

def main():
    print("=== Enterprise Scaling Refactor — Zero-Code Provisioning Tests ===")
    test_region_creation()
    test_district_creation()
    test_facility_code_generation()
    test_facility_scope()
    print("\nALL ENTERPRISE TESTS PASSED — zero-code provisioning prototype works")
    print("Example workflow:")
    print("  Region SOL → District SOL-TAL → Facility SOL-TAL-ST-001 (auto-generated)")
    print("  Admin assigns user via POST /api/facilities/SOL-TAL-ST-001/assign-user {username}")
    print("  No code change required")

if __name__ == '__main__':
    main()
