# Testing the form, clearance and identity-profile improvements

Branch: `arena/c1f51a82-sentinel-police-management`. Do not merge until UAT is approved.
Restart the backend and hard-refresh the browser when testing this branch.
Use a test database and synthetic identities/documents only.

## Focused automated regressions

```sh
python3 -m venv .venv
.venv/bin/pip install psycopg2-binary pgserver
npm install --no-save --package-lock=false jsdom@26

node backend/test_form_improvements.mjs
node backend/test_shell_workflow_integration.mjs
.venv/bin/python backend/test_linked_records.py
.venv/bin/python backend/test_review_gate.py
PYTHON="$PWD/.venv/bin/python" node backend/test_approval_flow.mjs
.venv/bin/python backend/test_dynamic_branches.py
.venv/bin/python backend/test_read_only_rbac.py
.venv/bin/python backend/test_print_fit.py
```

The linked-record suite **always** provisions isolated PostgreSQL. Review-gate,
approval-flow and other PostgreSQL-aware suites use configured `SENTINEL_DB_*`
settings if present, otherwise a throwaway `pgserver` instance. Never point those
suites at operational data. `test_form_improvements.mjs` uses jsdom with mocked
network writes; approval-flow tests execute all three actual page scripts
against the real API. The older `test_server.py` still assumes retired SQLite
storage and is not part of this PostgreSQL test set.

## Officer UAT checklist

1. **Error styling and first-error focus**
   - Try Persons, Fingerprint, Airport, Checkpoint, CID participants/cases,
     Stations, Officers, Crime intake, Vehicles, HR and Branch Management.
   - Leave one required field blank among completed fields, and leave optional
     fields blank. Save: only failed fields should be red; the first invalid
     field should be focused and scrolled into view inside the form/modal.
   - Correct it without saving again: the red indicator should clear.
   - Leave National ID and Passport empty, then fill either one: both error
     indicators should clear. Optional IDs in checkpoint intake must stay neutral.
   - Fail an officer requirement on a later wizard step. Save must reveal that
     step, focus the field and scroll it into view.
   - Leave attachment minimums unmet. The group is highlighted, not every
     optional file. Meet the minimum using any slots and confirm it clears.
   - Try an invalid optional email, document extension/size and incomplete
     conditional vehicle-owner or demotion fields.
2. **Successful-save lifecycle**
   - Save valid entries: the entry modal should close and the register remain.
   - Case-workspace saves return to CID; use View to reopen the saved case.
   - Saving a branch hides its form; **Add another branch** opens it again.
   - Disconnect/reject a write: the form must remain open with entered data.
3. **Citizenship**
   - As `fp.officer`, create a Citizenship application with required documents.
   - Approve immediately from either the register or the application review page,
     then open Certificate and print. No waiting-period lock should appear.
   - Repeat with Education, Travel, Employment and Licence: each must retain its
     12-hour lock. Administrator bypass and read-only command restrictions remain.
4. **Linked Unit Records**
   - Link the same synthetic person in several units/branches, then click View.
   - At the bottom, check branch name/region, source table/reference, uploader and
     recorded location/time. Compare them to the original register entries.
   - An officer only sees provenance in their permitted unit/checkpoint scope;
     admins/commanders can see their broader permitted set.
   - Unassigned legacy data, no linked records, offline/error state and rapid
     switching between profiles should not show invented or stale details.
   - Nearby/current proximity is **Not determined**: residence and dated record
     locations are not live coordinates. Uploader account branch is explicitly
     current metadata, not a historical snapshot.


## Combined UI / workflow integration (2026-10-12)

Remote inspection found the workflow commit `c90f397` already at `origin/main`.
The more recent UI commits `ca23e99` and `25a36ef` were on
`origin/arena/05b7c962-sentinel-police-management`, branched before those workflow
fixes. This testing branch merges both histories; it does not replace the new
UI with an older copy of `index.html`, and it does not modify `main`.

Preserved UI includes the refreshed command navigation, responsive mobile
sidebar, dashboard quick-action styling, and the user profile/sign-out controls
in the **top header**, not the sidebar. The new shell/workflow DOM test protects
these alongside role scoping, wizard error focus and identity provenance.

Verification also exposed a modal-animation focus race. A delayed opening focus
could take focus back from a validation error, or focus a closed modal after
switching forms. Pending initial focus is now cancelled on validation,
modal switches and close; regression checks wait past the opening animation.

Additional manual UI checks:
- Open the mobile navigation, select a page, press Escape, and resize to desktop;
  confirm navigation dismisses correctly and the header profile stays in place.
- Quickly press Save after opening an incomplete officer form. Its first error
  must keep focus even after the modal animation finishes.
- Switch roles and check that checkpoint submenu labels and administration
  actions appear only for permitted sessions.

## Branch Management — 5th department (Police Stations) & station mirroring (2026-10-12)

Branch: `arena/4d7dbf9c-sentinel-police-management`. Do not merge until UAT is approved.

### What changed
- `BRANCH_UNIT_TYPES` / `BRANCH_UNIT_LABELS` now include `police_station → Police Stations` (5th department). The `#branchUnitType` select and the **Station registry** `stBranch` intake (`data-branch-unit="police_station"`) are both wired to the catalogue (`refreshBranchSelect` → `GET /api/branches?unit_type=...`).
- Database `police_branches.unit_type` CHECK widens to the five values with an idempotent `DO` migration for live databases; `POST /api/branches` with `unit_type=police_station` now mirrors a row into `police_stations` (district/village derived from `STATION_DISTRICTS`, code via `STN-REG-XXX`, id via `ST-*`) without failing the branch write, and the generic helper `resolve_station_with_branch(c, station_code)` handles both `BR-<branch_id>` synthetic ids and bare numeric branch ids (auto-mirrors on demand).
- `register_officer`, `register_crime` (server.py) and `register_vehicle` (vehicles.py — Police Fleet path) all fall through to this helper before rejecting an unknown `station_id`, so enrolments that pick a *Police Stations branch* in the Station dropdown work even before the station row has been synchronised.
- Frontend `stationById` / `stationOptions` now merge `db.stations` + unsynced `branchCatalog.items.filter(b=>b.unit_type==='police_station')` as `BR-<id>` synthetic entries (`· Police Stations branch` label, `branchIsMirrored` de-duplication by region + base name / village). `loadBranchCatalog` + `saveBranch` refresh the merge; `stBranch → stName / st-loc` pre-fill on change; `refreshStationSelects` now covers `offStation`, `carStation` **and** `crmStation`.
- **User Management** branch field is now a dynamic `<input list="branchDatalist">` (datalist `#branchDatalist` populated by `refreshUserBranchDatalist()` from `branchCatalog` + static fallbacks). Open *New officer* / *Edit officer* and type — every Fingerprint / Crime / Checkpoint / Airport / **Police Stations** branch appears, so accounts can be associated with any dynamic branch location. Selecting a checkpoint role still gates `location_scope` via `refreshUserLocationOptions`.

### Manual verification (no DB wipe)
1. **Branch Management** as SystemAdmin → **Add branch** with **Unit Department = Police Stations**, Region = Sool `Lasanod Branch` (or a new name `Arena Police Branch · Sool`). Table shows the new row with blue *Police Stations* badge and the toast `… added to Police Stations`.
2. **Station dropdowns** — open **Police Personnel → Register Officer** and **Transport → Register Vehicle (category Police Fleet)**: `Assigned Station` now lists the new branch as `Buuhoodle Branch (BR-12) — Sool · … · Police Stations branch`. Pick it, fill dates/plate, save — no *unknown station* error; the new officer/car appears in the registers and in **Central Police Search → Stations**. `GET /api/branches?unit_type=police_station&region=Sool` and `GET /api/stations` also contain the mirrored row (`ST-… / STN-SOO-…`).
3. **5 intake dropdowns** — Fingerprint (`fpBranch`), Airport (`airBranch`), Crime `caseBranch` + `crmBranch`, Checkpoint (`cpBranch`) **and** the new Police Stations `stBranch` on **Stations → Register Station** each call `/api/branches?unit_type=…` and retain their selection on re-open (verified via Network tab).
4. **User Management** — create / edit an account and type into **Branch**: the datalist offers every branch including the newly added *Police Stations* entries; save and reload — the saved `branch` string matches the selected dynamic location (e.g. `Buuhoodle Branch · East Togdheer`).

### Automated
`python backend/test_dynamic_branches.py` — seeded-row, filtering (now 5 rows per region including `police_station`), admin-gate, duplicate, Police Stations mirroring and the frontend-contract (now 6 selectors + `stBranch:police_station` + datalist + synthetic `BR-` merge) — all checks pass (SKIP only without `SENTINEL_DB_*` / `pgserver`).

## Registered Stations — View / Edit row actions & admin-only edit authority (2026-10-12)

Branch: `arena/70d3d88b-sentinel-police-management`. Do not merge until UAT is approved.
Restart the backend and hard-refresh the browser when testing this branch.
Use a test database and synthetic identities/documents only.

### What changed
- **Actions column.** `renderStationsTable()` now paints a final **Actions** column: **View** on every
  row and **Edit** on every persisted registry row. `View` is a read surface (`data-view="1"`); `Edit`
  carries `.admin-edit` + `data-write="1"`.
- **View drawer** (`#stViewModal`, `openStationView()` / `paintStationView()`): station name, code and
  id, **Region → District → Village**, operational status, station tier, contact phone, cell capacity,
  commander / deputy (resolved to the officer record), notes, `created_at` / `updated_at`, the
  **officer** and **vehicle** deployment counters and the **mirrored Police Stations branch lineage**.
  It renders instantly from the locally merged registry row and is then replaced by the authoritative
  `GET /api/stations/<id>` payload (`station_detail_view()`), which returns `officer_count` /
  `vehicle_count` from the `officers` / `vehicles` registers, the `branch` catalogue row, `mirrored` /
  `persisted` flags and the per-session `can_edit` decision. Open to SystemAdmin, the HR Directorate
  and the read-only Commander (`stViewModal` joined `READ_ONLY_VIEW_MODALS`); a session without the
  `stations` module still gets 401.
- **Edit modal** (`#stEditModal`, `openStationEdit()` / `saveStationEdit()`): station name, Region →
  District → Village (cascading dropdowns, same validator as registration), operational status, plus
  optional tier / contact phone / cell capacity / notes. Saves with `PATCH /api/stations/<id>`
  (`PUT /api/stations[/<id>]` is served too), merges the saved row into `db.stations` (so officer /
  vehicle postings, the search panes, the counters and the drawer all follow), re-renders and toasts.
  Validation runs before any request leaves the browser; offline saves are stored locally and reported
  as an unsynced draft.
- **Role enforcement (server-authoritative).** `require_records_admin(user)` → **403 Forbidden**
  (`code: admin_only`) for every non-admin caller of `PUT` / `PATCH /api/stations[/<id>]` — including
  the HR Directorate, which may read the register, and any unit / checkpoint officer. The read-only
  Commander is refused even earlier (`code: read_only_role`). `POST /api/stations` keeps its existing
  admin module gate and now also calls the same role check. `station_detail_view()` returns
  `can_edit: false` + `edit_disabled_reason` for non-admins; the session payload (`user_view`) and the
  visibility block expose `can_edit_records` / `can_edit_stations` for the UI, and
  `canEditRecords()` / `canEditStations()` in `index.html` gate every inline Edit control. A `BR-<id>`
  synthetic mirror is view-only for everyone (edited in Branch Management); a persisted mirrored row
  stays editable by an admin and keeps its branch lineage in the payload.
- **Audit + provenance.** Every accepted station edit writes `audit_events`
  (`action=UPDATE`, `entity=police_station`, `entity_id=<station id>`, changed fields in `details`) and
  stamps `police_stations.updated_at` / `updated_by` (new columns, added by the idempotent migration).

### Automated
```sh
python3 -m venv .venv
.venv/bin/pip install psycopg2-binary pgserver
npm install --no-save --package-lock=false jsdom@26

.venv/bin/python backend/test_station_actions.py     # 123 checks: View payload, edit validation,
                                                     # admin-only PUT/PATCH (403), mirrors, audit
node backend/test_station_frontend.mjs               # Actions column, View drawer, Edit modal,
                                                     # non-admin / read-only gating, offline draft
PYTHON="$PWD/.venv/bin/python" node backend/test_station_integration.mjs
                                                     # real page script + real API + real database:
                                                     # admin View/Edit round-trip, HR 403, Commander 403
.venv/bin/python backend/test_read_only_rbac.py      # unchanged Commander firewall still holds
.venv/bin/python backend/test_dynamic_branches.py
```
All three suites cover their own provisioning: `test_station_actions.py` uses configured
`SENTINEL_DB_*` settings or a throwaway `pgserver` cluster and SKIPs (exit 0) when neither is
available; never point them at operational data.

### Officer UAT checklist
1. **SystemAdmin (`admin` / `ChangeMe123!`) → Police Stations → Registered stations.**
   - The table shows the **Actions** column with **View** and **Edit** on every row.
   - **View**: the drawer shows the station code, name, Region → District → Village, operational
     status, tier, phone, cell capacity, commander/deputy, notes, officer count, vehicle count and the
     mirrored branch line. Compare the values with the register row and (for a mirrored branch) with
     **Branch Management**.
   - **Edit**: rename the station, move it to another Region → District, change the village, switch
     the status to *Maintenance*, save — the table, the **Police Stations** counters, the officer /
     vehicle station dropdowns and **Central Police Search → Stations** all show the new values after
     saving. Reload the page: the values persist (they are in the database, not only in the browser).
   - **Edit validation**: leave the name blank → red field, no request; pick a district from another
     region → the district dropdown resets with the region; try *District HQ* etc. and confirm the
     tier/status lists are the register's own.
   - **Mirrored branch entry** (`BR-…` row, if any): View opens, Edit is not offered; hitting the API
     directly answers *“This registry entry is a Police Stations branch mirror — edit the branch
     itself in Branch Management.”*
2. **HR Directorate (`hr.officer`) → Police Stations.**
   - The register stays readable (postings), **View** works, and there is **no Edit button** anywhere
     in the table or in the drawer (the drawer explains that editing is a System Administrator action).
   - With the browser devtools open run
     `fetch('/api/stations/ST-001',{method:'PATCH',headers:{'Content-Type':'application/json','Authorization':'Bearer '+JSON.parse(localStorage.getItem('sentinel_token'))},body:JSON.stringify({name:'Nope'})})`
     → **403** with `{"code":"admin_only"}` and the station name unchanged in the register.
3. **Checkpoint officer (`cp.south`)** — the Police Stations page is not in the sidebar; a direct
   `PATCH` / `PUT /api/stations` answers **403** (`admin_only`) and a direct `GET /api/stations/<id>`
   answers **401**.
4. **Commander (`chief`) — read-only oversight.** View opens for the station record; no Edit control
   is painted and a direct `PATCH` / `PUT` answers **403** with `{"code":"read_only_role"}`.
5. **Cross-check the mirrors**: create a **Police Stations** branch in **Branch Management**, confirm
   the register gains the mirrored entry, open **View** and confirm the *Mirrored branch lineage* line
   names that branch; the mirrored persisted row can still be edited by the administrator.
6. Confirm the audit trail after an edit (`audit_events`: `action=UPDATE`, `entity=police_station`,
   `details` listing the changed fields) and that `updated_at` / `updated_by` moved on the row.

## Static assets: version stamps + no-store headers (2026-10-16)

The Registered Stations build is refused by nothing, but a **browser cache** was still able to keep
serving the pre-Actions page. Three mechanisms now make that impossible, and all three are asserted
by `backend/test_station_actions.py` (suite 6, 17 checks) so a half-finished version bump fails the
tests instead of silently leaving a stale page on screen.

### What changed
- **Versioned static references.** Every static reference the app ships carries `?v=<ASSET_VERSION>`:
  `index.html` → `certificate.html?v=0f8552e&id=…` and `application.html?v=0f8552e&id=…`,
  `application.html` / `certificate.html` → `index.html?v=0f8552e`, the brand emblem →
  `images/police_logo.png?v=0f8552e`, and `certificate.html` → `application.html?v=0f8552e&id=…`.
  `ASSET_VERSION` lives at the top of `backend/server.py` (currently the short commit the feature
  shipped from, `0f8552e`).
- **`Cache-Control: no-store` on the documents themselves.** The UI ships as self-contained
  documents (inline `<script>`/`<style>`, no external bundle), so the HTML *is* the asset that must
  never be replayed. `send_file()` now answers documents, uploads and un-versioned assets with
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` + `Expires: 0` +
  `Pragma: no-cache`; a `?v=`-stamped asset alone gets
  `Cache-Control: public, max-age=31536000, immutable`.
- **A stamp that tells you *which* page you have.** `<meta name="sentinel-ui-build">` is now
  `sentinel-rbac-readonly-4-0f8552e` (revision **and** the short commit) and is shown as *UI build …*
  in the sidebar footer (`window.SENTINEL_UI_BUILD`). `GET /api/health` reports `ui_build` — read
  from the `index.html` on disk on every call, not from a constant — plus `asset_version` and
  `static_cache`, so the footer can be compared with what the server is handing out: *footer ≠
  health ⇒ the tab is stale*.

### Bumping the version (do all of it)
1. `ASSET_VERSION = '<short commit>'` and `UI_BUILD = 'sentinel-rbac-readonly-<n>-<short commit>'` in
   `backend/server.py`.
2. `<meta name="sentinel-ui-build" content="sentinel-rbac-readonly-<n>-<short commit>" />` in `index.html`.
3. Every `?v=…` in `index.html`, `application.html`, `certificate.html`.
4. Run the suite — `static_asset_version_consistent()` + the served-header checks fail on any
   parameter or stamp left behind.

### Automated
```sh
.venv/bin/python backend/test_station_actions.py   # 140 checks (suite 6 = the cache-busting checks)
node backend/test_frontend_session.mjs             # pins the stamp shape + that no static reference
                                                   # is left un-versioned in index.html
```

### Officer UAT checklist
1. Sign in as `admin`, open **Police Stations → Registered stations**: the **Actions** column with
   **View**/**Edit** is present immediately on a normal reload (`Ctrl+R`) — no hard refresh needed.
2. Sidebar footer shows *UI build sentinel-rbac-readonly-4-0f8552e*; `curl -s localhost:8001/api/health`
   reports the same `ui_build` and `asset_version: "0f8552e"`.
3. `curl -sI localhost:8001/ | grep -i cache-control` → `no-store, no-cache, must-revalidate, max-age=0`;
   `curl -sI "localhost:8001/images/police_logo.png?v=0f8552e" | grep -i cache-control` →
   `public, max-age=31536000, immutable`.
4. Open **View → Certificate / Print** (devtools → Network): the created document URL carries
   `?v=0f8552e`.
5. Open the app with a stale tab (`/?v=0f8552e`) and confirm the Actions column still renders.

## Served-template identity: no stale page can reach UAT (2026-10-17)

A UAT report showed a **fresh browser** still running `UI build: sentinel-rbac-readonly-3` with no
Actions column. A fresh browser cannot read a browser cache, so the process was serving a different
`index.html` — the previous commit's page (`1b05c2c:index.html` is exactly `readonly-3` with zero
station action markup). Root cause class, not a one-off: *the process and the template were not
verified against each other*. That is now enforced in four places.

### What changed
- **Explicit template resolution.** `UI_DIR` (defaults to the repository root that contains
  `backend/server.py`, override with `SENTINEL_UI_DIR` for a packaged deployment) is the single
  source for `/`, `/index.html`, `/application.html`, `/certificate.html`. The resolved absolute path
  is logged at startup and reported by `/api/health` as `ui_path`.
- **Startup refusal.** Before the database is touched, `ui_self_test()` reads the `index.html` the
  process would serve and exits `FATAL` if the stamp is not `UI_BUILD`, or if any required feature
  marker is missing (`data-station-action="view"`, `openStationView(`, `openStationEdit(`,
  `body:not(.can-edit-records) .admin-edit`). A stale template therefore cannot bind the port.
- **Served identity in `/api/health`.** `ui_path`, `ui_sha256` (of the served bytes), `ui_bytes`,
  `ui_actions_published`, `ui_ok` and `ui_problems`. Compare `ui_sha256` with
  `sha256sum index.html` in a checkout — equal bytes, equal deployment.
- **`scripts/verify-live-ui.sh <url>`.** Network-level proof for any URL (including a preview):
  checkout stamp/sha256 vs `ui_build`/`ui_sha256`, the stamp + Actions + View + Edit markup in the
  served HTML, `?v=` references, and the cache headers. Exits non-zero with the differing identity.
  `scripts/restart-8001.sh` now also requires `ui_actions_published: true` before it reports success.

### Reproduce the guard (both directions)
```sh
bash scripts/verify-live-ui.sh http://127.0.0.1:8001      # PASS on a current stack
# negative: serve the previous commit's page and watch startup refuse
TMPD=$(mktemp -d); git show 1b05c2c:index.html > "$TMPD/index.html"
SENTINEL_UI_DIR="$TMPD" PORT=8123 .venv/bin/python backend/server.py; echo "exit=$?"
```

### Automated
```sh
.venv/bin/python backend/test_station_actions.py   # suite 6: 154 checks incl. served-template identity
```
The suite asserts the served path/sha256/features, the `/api/health` identity fields, that a
`readonly-3` page is reported stale *and* that a server handed it exits non-zero with a `FATAL`
that names the missing Actions column.

### UAT checklist (the blocker that started this)
1. `bash scripts/verify-live-ui.sh <preview-url>` → every line `PASS`, ending "the live server is
   serving this checkout".
2. `curl -s <preview-url>/api/health` → `ui_actions_published: true`, `ui_ok: true`, and
   `ui_sha256` equal to `sha256sum index.html`.
3. Open the preview in a private window → sidebar footer *UI build
   sentinel-rbac-readonly-4-0f8552e*; Police Stations → Registered stations → **Actions** column
   with **View** / **Edit** (admin).
4. If any of 1–3 fails, the preview is attached to a process serving a different template: restart
   from this checkout (`bash scripts/restart-8001.sh`) or use the preview URL reported for the
   current session. The startup log names the template path, the stamp and the sha256 it is serving.

## Local `python backend/server.py` — resolution, `--ui-check`, and the main-branch trap (2026-10-17)

A second UAT report: `http://localhost:8001` on multiple browsers still showed
`sentinel-rbac-readonly-3` and no Actions column. Re-verified on a *fresh clone on `main`*: that
checkout's `index.html` **is** `readonly-3` with zero station-action markup, because `main` never
received the feature — the work lives on `arena/70d3d88b-sentinel-police-management`. A local
`python backend/server.py` on `main` therefore served exactly what the report described, and there
was no guard in that commit to say so.

### Resolution rules (implemented)
`ui_candidates()` picks the first of:

1. `SENTINEL_UI_DIR` (explicit; packaged deployments),
2. **the current working directory** — `cd <repo> && python backend/server.py`,
3. the repository root containing `backend/server.py`.

`send_file()` opens the page on every request, so an edit is live on the next reload; no template
cache, restart or file watcher exists to go stale. The resolved path is used for `/`,
`/index.html`, `/application.html`, `/certificate.html` and (when present) `UI_DIR/images`.

### Guards
- **Startup refusal** — before `init_db()`, a stale/mismatched template exits `FATAL` naming the
  path, the stamp, the branch/commit of the checkout, the other `index.html` copies that resolution
  skipped, and the copy to start from.
- **`GET /` re-checks per request** (cached on size + mtime): if the checkout changes under a
  running server, the answer is **503** with `X-Sentinel-UI-Stale: 1` and the same diagnosis —
  never the old page. Restoring the file recovers with no restart.
- **`--ui-check`** (`python backend/server.py --ui-check`) prints the resolution and exits `1` when
  the server would refuse; runs without the database driver.
- **`/api/health`** adds `ui_source`, `ui_cwd`, `ui_git`, alongside `ui_path` / `ui_sha256` /
  `ui_actions_published` / `ui_ok`.

### Local verification (the reporter's step 3)
```sh
cd sentinel-police-management
python backend/server.py --ui-check        # exit 0, "Actions column: yes"
python backend/server.py                   # prints: ui template / ui source / ui checkout
curl -s http://localhost:8001/ | grep -E 'sentinel-rbac-readonly-4-0f8552e|<th>Actions</th>'
```
Verified on a fresh clone: on `main` the server refuses to start and prints *“this checkout predates
the station View/Edit feature — switch to the feature branch or merge it first”*; after
`git checkout arena/70d3d88b-sentinel-police-management`, `GET /` returns both
`sentinel-rbac-readonly-4-0f8552e` and `<th>Actions</th>` (and `openStationView` / `openStationEdit`).

### Automated
```sh
.venv/bin/python backend/test_station_actions.py   # 165 checks (suite 6 covers this)
```
New checks: CWD-first resolution, `--ui-check` pass/fail + diagnosis content, the startup refusal
naming the resolution source, a **running** server answering `503` when the page goes stale and
recovering to `200` when restored.
