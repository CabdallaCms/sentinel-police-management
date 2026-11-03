#!/usr/bin/env python3
"""Crime Department isolation — cases, suspects and branch-bound intake.

This suite is the regression gate for the scoped regional Crime Departments:

  1. CASE REGISTER ISOLATION
     A CID officer posted to Region A gets an EMPTY queryset for Region B on
     `GET /api/crime-cases`, and a 403 `branch_scope_forbidden` when they guess
     a Region B case id (`GET /api/crime-cases/<id>`, `PATCH`, evidence).
  2. SUSPECT REGISTER ISOLATION
     `GET /api/suspect-alerts` / `GET /api/suspects` only list the officer's own
     branch (case-linked suspects inherit their case's branch), the new
     `GET /api/suspects/<alert_id>` detail route answers 403 across regions and
     404 for an unknown id, and the per-record audit history follows suit.
  3. BRANCH-BOUND INTAKE
     `POST /api/crime-cases` and `POST /api/suspect-alerts` bind the officer's
     VERIFIED branch: a tampered `branch_id` is refused with 403 and an omitted
     one is adopted from the posting instead of being stored as NULL.
  4. HQ / ADMIN BYPASS
     The System Administrator and the Chief Commander keep the full
     cross-region register, the detail routes and the national catalogue.
  5. CATALOGUE + UI CONTRACT
     `/api/branches?unit_type=crime` returns the regional Crime Units (Sool,
     Sanaag, East Togdheer, …), and the page ships the locked suspect branch
     selector, the `🔒 Locked to assigned branch` indicator, the branch-bound
     payload and the region-led Crime Department header, with one consistent
     version stamp.

Usage: python3 backend/test_crime_department_scope.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(ROOT, 'server.py')
PROJECT_ROOT = os.path.dirname(ROOT)
INDEX = os.path.join(PROJECT_ROOT, 'index.html')

# Reuse the battle-tested harness (throwaway PostgreSQL, request helpers, …).
sys.path.insert(0, ROOT)
from test_branch_scope import (  # noqa: E402
    PASSWORD, branch_ids, check, create_user, free_port, login,
    provision_database, request)


def suspect_payload(tag, **extra):
    """A valid 'Add suspect' payload (unique identity per call)."""
    body = {
        'first_name': 'Scope', 'second_name': 'Suspect', 'third_name': tag,
        'fourth_name': 'Probe', 'national_id': 'CS-' + tag,
        'date_of_birth': '1991-03-03', 'phone': '+252 63 555 0177',
        'notes': 'Scope probe listing ' + tag,
    }
    body.update(extra)
    return body


def static_contract():
    """The served page / build stamp contract (no database needed)."""
    print('== 0. served page + version stamp contract ==')
    html = open(INDEX, encoding='utf-8').read()
    check('id="spBranch" data-branch-unit="crime"' in html,
          'the Add suspect modal ships a Crime branch selector')
    check('id="caseBranch" data-branch-unit="crime"' in html,
          'the New case modal ships a Crime branch selector')
    check('Filing scope' in html,
          'the Add suspect modal names the filing scope it will store')
    check('branch_id:branchId' in html,
          'the suspect payload explicitly carries the selected branch id')
    check('🔒 Locked to assigned branch' in html,
          'the locked-branch indicator is rendered for scoped officers')
    check('function crimeDepartmentHeader(' in html
          and "'Crime Department Operations'" in html,
          'the Crime Department header is computed from the officer region + branch')
    check("NATIONAL_COMMAND_HEADER='National Command — All Branches Operations'" in html,
          'the admin / HQ header names the national command, not a region')
    check('if(ownType&&wanted&&ownType!==wanted) return null;' in html,
          'a branch posting only scopes its own unit category')
    check('if(scope.hidden) return false;' in html
          and 'function sessionHasBranchScope(' in html,
          'a scoped officer never falls back to the national tree')
    check('function branchIndexForBranch(' in html,
          'same-name branches are disambiguated by region + district')
    check('function getOfficerBranchScope(' in html
          and 'function officerPostingLabel(' in html,
          'the officer branch scope resolves string postings and alternate fields')
    check('// ROLE-FIRST' in html,
          'every standard role is scoped, even before a branch resolves')
    check('// HARD PRUNE' in html
          and 'if(scope.region&&region!==scope.region){ regions.delete(region); return; }' in html
          and 'if(!districts.size) regions.delete(region);' in html,
          'a scoped tree prunes foreign/empty regions before it is painted')
    check('if(unitId!==scopeId) return false;' in html
          and 'if(scope.region&&region!==scope.region) return false;' in html,
          'unitInNavScope refuses a foreign branch, region or district')
    check('function applyBranchLock(' in html,
          'the shared branch-lock helper disables the selector')
    check("refreshBranchSelect('caseBranch','crime')" in html
          and "refreshBranchSelect('spBranch','crime')" in html,
          'both Crime intakes re-read the Crime Unit catalogue on open')
    check('branch_id:x.branch_id||null' in html,
          'the suspect register carries the branch provenance of each listing')

    # The sidebar tree is filtered by the SAME resolved posting as the forms
    # and the API, so a scoped officer never sees another region's hierarchy.
    check('data-nav-regions="crime"' in html,
          'the Crime Unit tree mount is present in the sidebar')
    check('function renderUnitNavTree(' in html and 'function navUnitScope(' in html
          and 'function unitInNavScope(' in html,
          'the regional tree renderer and its scope filter are published')
    check('if(scope.region&&region!==scope.region) return false;' in html,
          'a scoped tree rejects every region outside the posting')
    check('if(scope.district&&district!==scope.district) return false;' in html,
          'a scoped tree rejects every district outside the posting')

    # One version stamp across every page, and the page stamp matches the
    # server's UI_BUILD (a half-finished bump is what serves a stale page).
    server_src = open(SERVER, encoding='utf-8').read()
    asset = None
    ui_build = None
    for line in server_src.splitlines():
        if line.startswith('ASSET_VERSION = '):
            asset = line.split('=', 1)[1].strip().strip("'\"")
        if line.startswith('UI_BUILD = '):
            rhs = line.split('=', 1)[1].strip()
            prefix = rhs.split('+')[0].strip().strip("'\"")
            ui_build = prefix + (asset or '')
    check(bool(asset) and len(asset) >= 8, f'the asset version is published ({asset})')
    check(ui_build and f'content="{ui_build}"' in html,
          f'the page carries the current build stamp ({ui_build})')
    import re
    for name in ('index.html', 'application.html', 'certificate.html'):
        text = open(os.path.join(PROJECT_ROOT, name), encoding='utf-8').read()
        versions = set(re.findall(r'\?v=([A-Za-z0-9._-]+)', text))
        check(bool(versions) and versions == {asset},
              f'{name} carries only the current ?v={asset} stamp ({sorted(versions)})')

    print('== 0b. python backend/server.py --ui-check ==')
    result = subprocess.run([sys.executable, SERVER, '--ui-check'],
                            capture_output=True, text=True, cwd=PROJECT_ROOT)
    check(result.returncode == 0,
          'the UI self-check exits 0:\n' + (result.stdout or result.stderr).strip()
          + ('' if result.returncode == 0 else '\n' + result.stderr))


def run_api_suite(base):
    admin, admin_user = login(base, 'admin')
    ids = branch_ids(base, admin)

    def crime(name):
        key = ('crime', name)
        check(key in ids, f'the catalogue registers {name} as a Crime Unit')
        return ids[key]

    sool_branch = crime('Lasanod Branch')
    sanaag_branch = crime('Erigavo Branch')
    tog_branch = crime('Buuhoodle Branch')

    print('== 1. regional Crime Unit catalogue (Sool / Sanaag / East Togdheer) ==')
    status, catalogue = request(base, 'GET', '/api/branches?unit_type=crime', admin)
    check(status == 200, 'the Crime Unit catalogue is readable')
    items = catalogue.get('items') or []
    check(items and all(item['unit_type'] == 'crime' for item in items),
          'every filtered row is a Crime Unit')
    regions = {item['region'] for item in items}
    check({'Sool', 'Sanaag', 'East Togdheer'} <= regions,
          f'the catalogue covers the regional Crime Units ({sorted(regions)})')
    check({'Sool', 'Sanaag', 'East Togdheer'} <= set(catalogue.get('crime_regions') or []),
          'the response names the Crime Unit regions explicitly')
    check(all(group.get('items') for group in catalogue.get('crime_departments') or []),
          'the Crime Units are grouped by region')
    status, alias = request(base, 'GET', '/api/branches?unit=crime', admin)
    check(status == 200 and {i['id'] for i in alias['items']} == {i['id'] for i in items},
          'the `?unit=crime` spelling resolves to the same filtered catalogue')
    check(alias.get('unit_type') == 'crime',
          'the response echoes the resolved unit filter')

    print('== 2. scoped officers resolve to their own regional Posting ==')
    create_user(base, admin, 'cid.sool', 'CIDUnit',
                unit='Lasanod Branch', district='Laascaanood', region='Sool')
    create_user(base, admin, 'cid.sanaag', 'CIDUnit',
                unit='Erigavo Branch', district='Ceerigaabo', region='Sanaag')
    sool, sool_user = login(base, 'cid.sool')
    sanaag, sanaag_user = login(base, 'cid.sanaag')
    check(sool_user.get('branch_scope', {}).get('branch_id') == sool_branch,
          'the Sool officer is scoped to the Sool Crime Unit')
    check(sool_user.get('branch_scope', {}).get('region') == 'Sool',
          'the session payload names the Sool region')
    check(sanaag_user.get('branch_scope', {}).get('branch_id') == sanaag_branch,
          'the Sanaag officer is scoped to the Sanaag Crime Unit')

    print('== 3. case intake binds the officer branch ==')
    status, own_case = request(base, 'POST', '/api/crime-cases', sool,
                               {'branch_id': sool_branch, 'category': 'Fraud',
                                'location': 'Laascaanood',
                                'incident_summary': 'Sool scope probe'})
    check(status in (200, 201), f'the Sool officer files at their own branch ({status} '
                                f'{own_case.get("error", "")})')
    own_id = own_case.get('case_id')
    check(own_case.get('branch', {}).get('id') == sool_branch,
          'the created case is stored against the verified branch')

    status, tampered = request(base, 'POST', '/api/crime-cases', sool,
                               {'branch_id': sanaag_branch, 'category': 'Fraud',
                                'location': 'Ceerigaabo',
                                'incident_summary': 'Tampered payload'})
    check(status == 403 and tampered.get('code') == 'branch_scope_forbidden',
          f'a tampered branch_id is refused ({status})')

    status, implicit = request(base, 'POST', '/api/crime-cases', sool,
                               {'category': 'Theft/Burglary', 'location': 'Laascaanood',
                                'incident_summary': 'No branch in the payload'})
    check(status in (200, 201),
          f'an omitted branch is adopted from the posting ({status} '
          f'{implicit.get("error", "")})')
    implicit_id = implicit.get('case_id')
    check(implicit.get('branch', {}).get('id') == sool_branch,
          'the omitted branch is pinned, never left NULL')

    status, other_case = request(base, 'POST', '/api/crime-cases', admin,
                                 {'branch_id': sanaag_branch, 'category': 'Robbery',
                                  'location': 'Ceerigaabo',
                                  'incident_summary': 'Sanaag scope probe'})
    check(status in (200, 201), 'the administrator files a Sanaag case')
    other_id = other_case.get('case_id')

    print('== 4. GET /api/crime-cases is ORM-scoped (Region B is invisible) ==')
    status, listing = request(base, 'GET', '/api/crime-cases', sool)
    check(status == 200, 'the Sool officer reads the case register')
    own_ids = {item['case_id'] for item in listing['items']}
    check(own_id in own_ids and implicit_id in own_ids,
          'both of their own cases are listed')
    check(other_id not in own_ids,
          'the Sanaag case is absent from the Sool queryset (empty, not filtered UI)')
    check(all(item.get('branch_id') in (None, sool_branch) for item in listing['items']),
          'no listed row belongs to another branch')
    check(listing.get('branch_scope', {}).get('branch_id') == sool_branch,
          'the register echoes the enforced branch scope')
    check('CID-2026-008' not in own_ids,
          'unassigned legacy cases are not leaked into a scoped queryset')

    status, detail_other = request(base, 'GET', f'/api/crime-cases/{other_id}', sool)
    check(status == 403 and detail_other.get('code') == 'branch_scope_forbidden',
          f'a Region B case id answers 403 by direct lookup ({status})')
    status, detail_own = request(base, 'GET', f'/api/crime-cases/{own_id}', sool)
    check(status == 200, 'their own case opens normally')

    status, patched = request(base, 'PATCH', f'/api/crime-cases/{other_id}', sool,
                              {'status': 'Closed'})
    check(status == 403 and patched.get('code') == 'branch_scope_forbidden',
          f'a Region B case cannot be edited by id ({status})')
    status, patched_own = request(base, 'PATCH', f'/api/crime-cases/{own_id}', sool,
                                  {'notes': 'Sool officer note'})
    check(status == 200, 'their own case accepts an update')

    print('== 5. suspect intake is branch-bound ==')
    status, cross_case = request(base, 'POST', '/api/suspect-alerts', sool,
                                 suspect_payload('XS', case_id=other_id))
    check(status == 403 and cross_case.get('code') == 'branch_scope_forbidden',
          f'a suspect cannot be linked to a Region B case ({status})')

    status, cross_branch = request(base, 'POST', '/api/suspect-alerts', sool,
                                   suspect_payload('XB', branch_id=sanaag_branch))
    check(status == 403 and cross_branch.get('code') == 'branch_scope_forbidden',
          f'a tampered suspect branch_id is refused ({status})')

    status, unlinked = request(base, 'POST', '/api/suspect-alerts', sool,
                               suspect_payload('UL'))
    check(status in (200, 201), f'an unlinked listing is accepted ({status} '
                                f'{unlinked.get("error", "")})')
    unlinked_id = unlinked.get('alert_id')
    check(unlinked.get('branch_id') == sool_branch,
          'the omitted branch is pinned to the Sool Crime Unit')

    status, own_link = request(base, 'POST', '/api/suspect-alerts', sool,
                               suspect_payload('OL', case_id=own_id))
    check(status in (200, 201), 'the Sool officer links a suspect to their own case')
    own_alert = own_link.get('alert_id')
    check(own_link.get('branch_id') == sool_branch,
          'the case-linked listing is stored against the officer branch')

    status, sanaag_link = request(base, 'POST', '/api/suspect-alerts', sanaag,
                                  suspect_payload('SA', case_id=other_id))
    check(status in (200, 201), 'the Sanaag officer files their own linked suspect')
    sanaag_alert = sanaag_link.get('alert_id')
    check(sanaag_link.get('branch_id') == sanaag_branch,
          'the Sanaag listing is stored against the Sanaag branch')

    print('== 6. suspect list + detail routes are ORM-scoped ==')
    status, suspects = request(base, 'GET', '/api/suspect-alerts', sool)
    check(status == 200, 'the Sool officer reads the suspect register')
    alert_ids = {item['alert_id'] for item in suspects['items']}
    check(unlinked_id in alert_ids and own_alert in alert_ids,
          'their own listings are visible')
    check(sanaag_alert not in alert_ids,
          'the Sanaag listing is absent from the Sool queryset')
    check(all(item.get('branch_id') == sool_branch for item in suspects['items']),
          'every listed suspect belongs to the officer branch')
    check(suspects.get('branch_scope', {}).get('branch_id') == sool_branch,
          'the suspect register echoes the enforced scope')

    status, alias_list = request(base, 'GET', '/api/suspects', sool)
    check(status == 200 and {i['alert_id'] for i in alias_list['items']} == alert_ids,
          'the /api/suspects alias returns the same scoped queryset')

    status, cross_detail = request(base, 'GET', f'/api/suspects/{sanaag_alert}', sool)
    check(status == 403 and cross_detail.get('code') == 'branch_scope_forbidden',
          f'GET /api/suspects/<id> refuses another region ({status})')
    status, own_detail = request(base, 'GET', f'/api/suspects/{unlinked_id}', sool)
    check(status == 200 and own_detail.get('branch_id') == sool_branch,
          'GET /api/suspects/<id> opens their own listing')
    status, alias_detail = request(base, 'GET', f'/api/suspect-alerts/{own_alert}', sool)
    check(status == 200 and alias_detail.get('alert_id') == own_alert,
          'the /api/suspect-alerts/<id> alias is scoped identically')
    status, missing = request(base, 'GET', '/api/suspects/AL-does-not-exist', sool)
    check(status == 404, f'an unknown suspect id answers 404 ({status})')

    print('== 7. audit history follows the suspect scope ==')
    status, own_audit = request(base, 'GET', f'/api/audit/entity/suspect_alert/{unlinked_id}',
                                sool)
    check(status == 200 and own_audit.get('items'),
          'the officer reads the history of their own listing')
    status, cross_audit = request(base, 'GET',
                                  f'/api/audit/entity/suspect_alert/{sanaag_alert}', sool)
    check(status == 403 and cross_audit.get('code') == 'branch_scope_forbidden',
          f'another region listing history is refused ({status})')

    print('== 8. HQ / Admin keep the cross-region register ==')
    status, admin_cases = request(base, 'GET', '/api/crime-cases', admin)
    admin_case_ids = {item['case_id'] for item in admin_cases['items']}
    check(status == 200 and own_id in admin_case_ids and other_id in admin_case_ids,
          'the administrator reads every regional case')
    check(admin_cases.get('branch_scope') is None,
          'the administrator payload carries no branch restriction')
    status, admin_case_detail = request(base, 'GET', f'/api/crime-cases/{other_id}', admin)
    check(status == 200, 'the administrator opens a Region B case by id')

    status, admin_suspects = request(base, 'GET', '/api/suspect-alerts', admin)
    admin_alert_ids = {item['alert_id'] for item in admin_suspects['items']}
    check(status == 200 and unlinked_id in admin_alert_ids
          and sanaag_alert in admin_alert_ids,
          'the administrator reads every regional suspect listing')
    status, admin_suspect_detail = request(base, 'GET',
                                           f'/api/suspects/{sanaag_alert}', admin)
    check(status == 200, 'the administrator opens a Region B suspect by id')

    chief, chief_user = login(base, 'chief')
    check(chief_user.get('branch_scope_status', {}).get('override') is True,
          'the Chief Commander holds the cross-region override')
    status, chief_cases = request(base, 'GET', '/api/crime-cases', chief)
    chief_case_ids = {item['case_id'] for item in chief_cases['items']}
    check(status == 200 and own_id in chief_case_ids and other_id in chief_case_ids,
          'the Commander reads every regional case')
    status, chief_suspects = request(base, 'GET', '/api/suspects', chief)
    chief_alert_ids = {item['alert_id'] for item in chief_suspects['items']}
    check(status == 200 and unlinked_id in chief_alert_ids
          and sanaag_alert in chief_alert_ids,
          'the Commander reads every regional suspect listing')
    status, chief_detail = request(base, 'GET', f'/api/suspects/{sanaag_alert}', chief)
    check(status == 200, 'the Commander opens any regional suspect by id')

    print('== 9. dashboard counters follow the same scope ==')
    status, sool_dash = request(base, 'GET', '/api/dashboard', sool)
    check(status == 200, 'the Sool dashboard is readable')
    cards = {card['id']: card for card in (sool_dash.get('cards') or [])}
    check('cid_open' in cards and cards['cid_open']['value'] >= 2,
          'the officer sees their own open cases counted')
    status, admin_dash = request(base, 'GET', '/api/dashboard', admin)
    admin_cards = {card['id']: card for card in (admin_dash.get('cards') or [])}
    # HQ keeps the cross-unit overview, so its open-case counter is national.
    national_open = (admin_cards.get('open_cases') or {}).get('value')
    check(national_open is not None and national_open >= cards['cid_open']['value'],
          'the administrator counters are never narrower than a regional one '
          f'({national_open} vs {cards["cid_open"]["value"]})')
    check(sool_dash.get('branch_context')
          == 'Sool Region — Lasanod Branch Crime Department Operations',
          'the Sool dashboard banner names region + branch: '
          f"{sool_dash.get('branch_context')!r}")
    check(admin_dash.get('branch_context') == 'National Command — All Branches Operations',
          'the administrator dashboard banner names the national command: '
          f"{admin_dash.get('branch_context')!r}")
    status, chief_dash = request(base, 'GET', '/api/dashboard', chief)
    check(status == 200, 'the Commander dashboard is readable')
    check(chief_dash.get('branch_context') == 'National Command — All Branches Operations',
          'the Commander dashboard banner names the national command: '
          f"{chief_dash.get('branch_context')!r}")

    status, cid_analytics = request(base, 'GET', '/api/analytics?module=cid', sool)
    check(status == 200, 'the CID analytics bundle is readable')
    section = (cid_analytics or {}).get('crime') or {}
    check(section.get('branch_scope', {}).get('branch_id') == sool_branch,
          'the crime analytics section is scoped to the officer branch')
    check(section.get('total_cases') == len(own_ids),
          'the analytics total matches the scoped register')


def main():
    static_contract()
    tmp = tempfile.mkdtemp(prefix='sentinel-crime-scope-')
    db_env, stop_db = provision_database(tmp)
    if db_env is None:
        print('SKIP: no PostgreSQL test database available; configure SENTINEL_DB_* or install pgserver.')
        return 0
    os.environ.update({k: v for k, v in db_env.items() if v})
    port = free_port()
    env = dict(os.environ, **db_env)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    server = subprocess.Popen([sys.executable, SERVER], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(120):
            try:
                status, _ = request(base, 'GET', '/api/health')
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('crime-department scope test server did not start')
        run_api_suite(base)
        print('ALL CRIME DEPARTMENT ISOLATION TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())
