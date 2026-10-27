# Testing the form, clearance and identity-profile improvements

Branch: `arena/554b1a25-sentinel-police-management`. Do not merge until UAT is approved.
Restart the backend and hard-refresh the browser when testing this branch.
Use a test database and synthetic identities/documents only.

## Focused automated regressions

```sh
python3 -m venv .venv
.venv/bin/pip install psycopg2-binary pgserver
npm install --no-save --package-lock=false jsdom@26

node backend/test_form_improvements.mjs
node backend/test_shell_workflow_integration.mjs
node backend/test_sidebar_navigation.mjs
.venv/bin/python backend/test_branch_scope.py
node backend/test_record_audit_ui.mjs
.venv/bin/python backend/test_checkpoint_roles_audit.py
PYTHON="$PWD/.venv/bin/python" node backend/test_frontend_session.mjs
PYTHON="$PWD/.venv/bin/python" node backend/test_station_integration.mjs
node backend/test_station_frontend.mjs
.venv/bin/python backend/test_officer_profile_locations.py
.venv/bin/python backend/test_linked_records.py
.venv/bin/python backend/test_review_gate.py
PYTHON="$PWD/.venv/bin/python" node backend/test_approval_flow.mjs
.venv/bin/python backend/test_dynamic_branches.py
.venv/bin/python backend/test_read_only_rbac.py
.venv/bin/python backend/test_print_fit.py
.venv/bin/python backend/test_field_level_rbac.py
node backend/test_clearance_rbac_ui.mjs
node backend/test_reverse_sequence_ui.mjs
node backend/test_branch_management_ui.mjs
.venv/bin/python -m pytest backend/test_branch_management_crud.py -q
```

The linked-record suite **always** provisions isolated PostgreSQL. Review-gate,
approval-flow and other PostgreSQL-aware suites use configured `SENTINEL_DB_*`
settings if present, otherwise a throwaway `pgserver` instance. Never point those
suites at operational data. `test_form_improvements.mjs` uses jsdom with mocked
network writes; approval-flow tests execute all three actual page scripts
against the real API. The older `test_server.py` still assumes retired SQLite
storage and is not part of this PostgreSQL test set.

## Sidebar navigation UAT checklist

The sidebar is four collapsible categories (Command Center · Operational Units · Agency &
Personnel · Administration). For every role you test:

1. **Category + accordion state** — collapse each category and each accordion, reload; the state
   persists (`sentinelNavSections` / `sentinelNavGroups`). Navigating to a page (including from a
   dashboard quick action) expands the category + accordion that own it.
2. **RBAC gates** — sign in as Fingerprint, Airport Control, CID, HR Directorate and a Checkpoint
   officer. A category with no permitted entry never renders (no empty headings), Central Police
   Search is absent for Fingerprint / Airport / CID, and Administration appears only for a
   SystemAdmin. Nothing that *is* shown may lead to a forbidden page (`go()` still redirects).
3. **Dynamic unit trees** — every operational accordion (*Fingerprint Units*, *Crime Units*,
   *Airport Control*, *Checkpoint Units*) shows the same three levels: **Region → District →
   unit**. Expand *Operational Units → Checkpoint Units* and confirm e.g. `Sool → Laascaanood →
   Lasanod Central` and `Sool → Xudun → Yagoori`; each level carries a count and its own chevron.
   Regions/districts start collapsed and their state survives a reload
   (`sentinelNavRegions`, keys `type|region` and `type|region|district`). Clicking a unit opens its
   register filtered to that posting (the page search box for fingerprint/airport/crime, the
   location chips for a canonical `South`/`East`/`West` checkpoint) and the unit is highlighted.
   The canonical areas appear under their own **Checkpoint areas** group.
4. **Live updates (no reload)** — in **Branch Management** add a branch (e.g. `Dhahar Branch ·
   Sanaag · Dhahar`, any unit type) and save; the matching tree must show the new region/district/
   unit at once. Record a checkpoint stop at a brand-new location from **Checkpoint Unit → Add
   screening**; the checkpoint tree must list it immediately under its district. Nothing that
   cannot be placed may disappear — it lands under *Unassigned region* / *Unassigned district*.
5. **Scalable unit labels** — register a long checkpoint branch name under Branch Management
   (e.g. `Buuhoodle Border Crossing Checkpoint · East Togdheer · Buuhoodle`), then open the
   sidebar: the rail shows a short, single-line label, the tooltip shows the full name, and no
   label wraps or clips the chevron/count.
6. **Posting resolution + auto-locked branch selectors** — the posting is free text, so test the
   fuzzy shapes. In **User Management** create a Fingerprint officer with the *Station / Branch*
   `Lasanod Branch` (Sool · Laascaanood), sign in as them and open *Fingerprint Unit → New Clearance
   Application*: **Branch** must be pre-selected to `Lasanod Branch`, **disabled**, and carry the
   clean `🔒 Locked to assigned branch · Lasanod Branch · Laascaanood · Sool` chip — no yellow
   warning banner. Repeat with a legacy posting typed straight into the **Branch** field:
   `  lasanod branch ` and `Lasanod` both lock to the same branch; `Fingerprint Unit · Sool` locks
   to the Sool branch; a bare `Fingerprint Unit` (three branches, no region) is *ambiguous* and
   leaves the selector open with a muted ⓘ note. A System Administrator, HQ and the Commander keep
   every selector editable, and the checkpoint location selector stays editable for them too.
7. **Strict branch scoping** — as the `Lasanod Branch` fingerprint officer, file one application.
   As an administrator, file another one at `Erigavo Branch`. Sign back in as the officer: the
   register lists **only** the Lasanod application, and opening the Erigavo one by URL
   (`/api/clearance-applications/<id>`) answers **403**. The same holds for the airport movement
   register, CID cases and `/api/audit/entity/clearance_application/<id>`. A cross-branch POST
   (e.g. editing the disabled selector with dev tools) answers **403 branch_scope_forbidden** and
   names the officer's posting. The administrator and the Commander still see every branch.
8. **Contextual headers** — a `Lasanod Branch` fingerprint officer's dashboard heading and
   *Fingerprint Unit* overview banner both read
   `Fingerprint Unit — Lasanod Branch Operations` (detail line `Laascaanood · Sool`); a checkpoint
   officer reads `Checkpoint Unit — <their checkpoint> Operations`; an administrator reads
   `— all branches` / `Cross-unit Operations`; the Commander reads `— cross-region command`.
9. **Unit Directory** — *Unit Directory* is now a **category-level utility at the top of
   Operational Units** (no longer inside the Checkpoint Units accordion). Filter by Unit type
   (*All unit types* by default), Region, District and free text; the empty state must explain a
   dead end. A Checkpoint officer only sees unit types their modules allow. Clicking a row opens
   that unit's register; a station-scoped officer stays locked to their own posting (toast
   explains it), and the directory closes.
10. **Read-only Commander** — the Unit Directory stays openable (it is a read surface) and no write
    control appears in it.
11. **Stale build** — the sidebar footer build label must match `/api/health` `ui_build`
    (`sentinel-branch-crud-1-e7c41b90`); a mismatch means a cached tab.

12. **Branch-scoped sidebar tree** — sign in as a Fingerprint officer posted to
    `Lasanod Branch · Laascaanood · Sool`. Every dynamic tree (Fingerprint Units, Crime Units,
    Airport Control, Checkpoint Units, Stations & Registers) must show **only** `Sool →
    Laascaanood → Lasanod …`: no other region, no other district, no external branch, and no
    *Unassigned region* / *Unassigned district* / *Checkpoint areas* group. Repeat with a
    checkpoint officer posted to `Lasanod Central Checkpoint · Laascaanood · Sool` — the rule is
    identical for all five unit categories, so each tree is the same isolated Sool slice.
13. **Unit Directory is command-authority only** — that officer has **no** *Unit Directory*
    launcher in the rail and **no** unit-count badge on it; forcing the opening (dev-tools /
    console `openUnitDirectory('')`) shows the *Unit Directory is restricted* toast and no drawer
    opens. Sign in as `admin` and as the Commander: the launcher, the badge and the full national
    directory are back (an unresolvable posting never removes them from a command role).

`python backend/server.py --ui-check` must exit 0 — it now also asserts the four category
markers, all five dynamic tree mounts, the tree/district/catalogue renderers, the posting
canonicaliser/resolver, the locked-branch indicator, the contextual unit headers, the branch-lock
helpers, the short-label helper, the Unit Directory modal, and (this release) the navigation-scope
resolver `navUnitScope(`, its filter `unitInNavScope(`, the directory authority gate
`unitDirectoryAllowed(` and the visibility switch `applyUnitDirectoryVisibility(`.

`python backend/test_branch_scope.py` is the API-level proof for items 6–7 (posting resolution,
read scoping, 403 on another branch's record and audit history, write scoping, override roles).
`node backend/test_sidebar_navigation.mjs` is the jsdom proof for items 12–13: a scoped officer's
five trees each keep exactly one region, one district and one branch; the Unit Directory launcher
is hidden and the drawer refuses to open with the restriction toast, while `admin` and the
Commander keep national visibility and the directory.

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
  `index.html` → `certificate.html?v=9a4c7f31&id=…` and `application.html?v=9a4c7f31&id=…`,
  `application.html` / `certificate.html` → `index.html?v=9a4c7f31`, the brand emblem →
  `images/police_logo.png?v=9a4c7f31`, and `certificate.html` → `application.html?v=9a4c7f31&id=…`.
  `ASSET_VERSION` lives at the top of `backend/server.py` (currently the short commit the feature
  shipped from, `9a4c7f31`).
- **`Cache-Control: no-store` on the documents themselves.** The UI ships as self-contained
  documents (inline `<script>`/`<style>`, no external bundle), so the HTML *is* the asset that must
  never be replayed. `send_file()` now answers documents, uploads and un-versioned assets with
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` + `Expires: 0` +
  `Pragma: no-cache`; a `?v=`-stamped asset alone gets
  `Cache-Control: public, max-age=31536000, immutable`.
- **A stamp that tells you *which* page you have.** `<meta name="sentinel-ui-build">` is now
  `sentinel-checkpoint-audit-6-9a4c7f31` (revision **and** the short commit) and is shown as *UI build …*
  in the sidebar footer (`window.SENTINEL_UI_BUILD`). `GET /api/health` reports `ui_build` — read
  from the `index.html` on disk on every call, not from a constant — plus `asset_version` and
  `static_cache`, so the footer can be compared with what the server is handing out: *footer ≠
  health ⇒ the tab is stale*.

### Bumping the version (do all of it)
1. `ASSET_VERSION = '<short commit>'` and `UI_BUILD = 'sentinel-officer-profile-<n>-<short commit>'` in
   `backend/server.py`.
2. `<meta name="sentinel-ui-build" content="sentinel-officer-profile-<n>-<short commit>" />` in `index.html`.
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
2. Sidebar footer shows *UI build sentinel-checkpoint-audit-6-9a4c7f31*; `curl -s localhost:8001/api/health`
   reports the same `ui_build` and `asset_version: "9a4c7f31"`.
3. `curl -sI localhost:8001/ | grep -i cache-control` → `no-store, no-cache, must-revalidate, max-age=0`;
   `curl -sI "localhost:8001/images/police_logo.png?v=9a4c7f31" | grep -i cache-control` →
   `public, max-age=31536000, immutable`.
4. Open **View → Certificate / Print** (devtools → Network): the created document URL carries
   `?v=9a4c7f31`.
5. Open the app with a stale tab (`/?v=9a4c7f31`) and confirm the Actions column still renders.

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
   sentinel-checkpoint-audit-6-9a4c7f31*; Police Stations → Registered stations → **Actions** column
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
curl -s http://localhost:8001/ | grep -E 'sentinel-checkpoint-audit-6-9a4c7f31|<th>Actions</th>'
```
Verified on a fresh clone: on `main` the server refuses to start and prints *“this checkout predates
the station View/Edit feature — switch to the feature branch or merge it first”*; after
`git checkout arena/70d3d88b-sentinel-police-management`, `GET /` returns both
`sentinel-checkpoint-audit-6-9a4c7f31` and `<th>Actions</th>` (and `openStationView` / `openStationEdit`).

### Automated
```sh
.venv/bin/python backend/test_station_actions.py   # 165 checks (suite 6 covers this)
```
New checks: CWD-first resolution, `--ui-check` pass/fail + diagnosis content, the startup refusal
naming the resolution source, a **running** server answering `503` when the page goes stale and
recovering to `200` when restored.

## Clearance purpose, document viewer, certificate print lock, field-level RBAC (2026-10-23)

### What changed
- **Purpose visibility** — `purposeBadge()` / `purposeTone()` / `purposeIcon()` render the
  stored clearance reason (Education · Travel · Employment · Citizenship · Licence) as a
  chip in the Fingerprint register (`Purpose` column), in the review modal header + summary,
  in `application.html` and in `certificate.html`. `GET /api/fingerprint/applications`
  already returned `purpose`; no route or column was added.
- **Photographs are images, not icons** — `fileExtensionOf()` / `documentExtension()` decide
  image vs. document, the applicant photo (list `applicant_photo`, detail
  `applicant_photo`) renders as `<img>`, and `#imageLightbox` adds fullscreen zoom/pan
  (wheel, `+`/`−`, `0`, *Open in new tab*, `Esc`).
- **Certificate print lock** — `certificate_print_state()` in `backend/server.py` returns
  `{unlocked, locked, requires_signed_scan, signed_scan_present, admin_bypass,
  read_only_bypass, reason, editable_by}` and is attached to every clearance row and
  detail. Unlocked = admin (bypass) · Commander/High Command (view-only bypass) ·
  `signed_scan_present`. Gated in the register row, the review modal,
  `application.html` and `certificate.html` (deep link included).
- **Field-level RBAC** — `PERSON_SELF_EDITABLE_FIELDS = ['phone','residence','occupation']`
  in the frontend and `PERSON_MUTABLE_FIELDS` on the server. `PATCH /api/persons/<id>`
  answers **403** `code: field_edit_forbidden` when a non-admin changes a protected
  field; nothing is written, not even the permitted keys in the same bundle. Admins
  edit everything. `POST /api/persons` / `/upsert` are unchanged, and `applicant_person_id`
  (the database id) is now returned next to the human `person_id` so the review modal can
  fetch the right document manifest.

### Automated
```sh
.venv/bin/python backend/test_field_level_rbac.py   # 7 tests: mutable-only PATCH, atomic
                                                   # 403 per protected field, unchanged
                                                   # echo, admin bypass, Commander 403,
                                                   # print lock → scan → unlocked,
                                                   # applicant photo in the manifest
node backend/test_clearance_rbac_ui.mjs            # jsdom: purpose chip, photo <img>,
                                                   # lock/bypass labels, lightbox, RBAC
                                                   # editor in modal + identity drawer
PYTHON="$PWD/.venv/bin/python" node backend/test_approval_flow.mjs
.venv/bin/python backend/test_review_gate.py
.venv/bin/python backend/test_station_actions.py   # feature markers + cache-busting
```

`test_field_level_rbac.py` reuses the `test_review_gate` pgserver harness (throwaway
cluster, temporary `SENTINEL_UPLOADS`); `test_clearance_rbac_ui.mjs` evaluates the real
inline script in jsdom with stubbed network writes.

### Officer UAT checklist
1. **Purpose** — open Fingerprint: every row shows a Purpose chip; open one record and the
   modal header + summary repeat it; open `application.html` / `certificate.html` and check
   the chip and the printed purpose line. Then open a person's profile from the Central
   Person Registry — the head card shows `Clearance · <purpose>` for the newest application
   (`+N earlier` when there are more), and a person with no application shows no chip.
2. **Photograph / documents** — open a person with a photograph: the photo renders as an
   image, clicking it (or any image document) opens the fullscreen viewer; wheel/`+`/`−`
   zoom, drag to pan, `0` resets, `Esc` closes; a PDF/scan keeps its file icon.
3. **Certificate lock** — as a Fingerprint Officer approve an application **without** a
   signed scan: the register shows `Certificate (scan required)`, disabled, and the deep
   link `certificate.html?id=…` says the certificate is locked. Upload the signed scan
   (`Re-scan` → *signed application*) and print immediately. As Admin the button is
   enabled from the start (`Admin bypass`).
4. **One edit action** — the person profile footer shows exactly one **✏ Edit Details**
   button (no `Edit profile` / `Edit / append details` pair); it opens `Cancel` +
   `Save details`. The register's **+ New / update person** flow still creates or merges.
5. **Field-level RBAC** — sign in as a regular officer, open Person Details → **Edit
   Details**: only Phone, Residence and Occupation accept input; the identity fields are
   plain disabled inputs with no `ADMIN ONLY` tags (the role note below the grid explains
   why), and saving sends only those three keys. Try the same with `curl`:
   `PATCH /api/persons/<id> {"full_name": "…"}` → **403** `field_edit_forbidden`, no change
   written. Sign in as Admin: every field edits and saves.

## Register row numbering — reverse sequence `#` (2026-10-23)

### What changed
- A compact leading **`#`** column on every primary register. The number is the
  **filtered** row count minus the row index, so the top (newest) row shows the
  total and the bottom (oldest) row shows `1`.
- Shared helpers `reverseSequence(index,total)` / `sequenceCell(index,total,cls)` /
  `sequenceHead()` (next to `paintTableCount`, `index.html`). Tables: Fingerprint,
  Central Person Registry, Airport, CID cases, CID suspects, Checkpoint screening,
  Registered Stations, Police Officers, Vehicles, Crime intake and the three
  Central Police Search tabs.
- Header/body column counts stay equal, empty-state `colspan` widened with each
  table, and **Actions remains the last column**; the column is 46 px wide
  (38 px ≤640 px) with tabular figures so `9`/`10` align.

### Automated
```sh
node backend/test_reverse_sequence_ui.mjs
```

It pins: 4 applications read `4 3 2 1`; the search box renumbers the filtered view;
a newly added application becomes the new `total`; every register's header and row
cell counts match with `#` as the first cell and Actions last; filtered People /
Stations tables number from their filtered count; every empty-state `colspan`
equals the widened header; all three police-search tabs carry the column.

`UI_REQUIRED_MARKERS` gained `('Reverse sequence # column', 'function sequenceCell(')`,
so a stale page missing the column now fails startup and `python backend/server.py
--ui-check`.

### Officer UAT checklist
1. Open **Fingerprint**: the first row is numbered with the number of applications
   currently listed and the last row is `1`; add a new application and the top
   number increases by one.
2. Type in the register search box: the numbers renumber to the filtered count
   (a single match is `1`) and return to the full range when cleared.
3. Check **Persons**, **Airport**, **CID**, **Checkpoints**, **Police Stations**,
   **Police Officers**, **Vehicles**, **Crime intake** and **Central Police
   Search** (officers / stations / vehicles): each starts with `#`, the Actions
   column is still last, and nothing overflows on a narrow window.

## Officer profiles, badge attribution and role-driven location pickers (testing branch)

### Automated
```sh
node backend/test_officer_profile_ui.mjs                # jsdom: identity block → profile
                                                        # modal, cascade, badges, refresh
.venv/bin/python backend/test_officer_profile_locations.py   # real API + throwaway PostgreSQL
```

`test_officer_profile_ui.mjs` proves, in the real page script: the header identity
block is one keyboard-accessible button that opens the Officer Profile modal; the
modal saves a display name (`PATCH /api/me`), applies an avatar preset
(`POST /api/me/avatar`) and changes the password (`POST /api/me/password`, with
the confirmation mismatch caught before any request); a Checkpoint role offers
only the **active** checkpoints of the chosen Region → District and hides the
station/branch field, a Station / Unit role does the reverse; the roster paints
`Badge #FP-102` (and `#Not recorded` when a row genuinely has none); the audit
trail attributes each entry to the acting badge; `refreshLiveMetrics()` re-reads
`/api/dashboard` and (with `{audit:true}`) the audit trail.

`test_officer_profile_locations.py` drives the same behaviours through the API:
the drawer's exact create payload, the canonical South / East / West scope kept
for legacy aliases, a station / unit role clearing a stale checkpoint scope, the
badge backfill and duplicate-badge refusal, `GET /api/admin/audit` attribution
plus the `#Not recorded` fallback for a row with no badge, the three profile
endpoints, and the Commander's `403 read_only_role` firewall on all of them.

### Officer UAT checklist
1. Sign in as `fp.officer` (`ChangeMe123!`): the header avatar shows `OH`, and
   clicking anywhere on the name / avatar block opens **Officer profile** with
   `Badge #FP-102`. Change the display name — the header updates at once; pick a
   gold avatar preset — the header initials change; upload a JPG/PNG — the
   picture replaces the initials. Change the password with a wrong current
   password (refused), then correctly (accepted); a second tab is signed out.
2. Sign in as `admin` → **User management** → **New officer**: pick
   *Checkpoint Officer* — the **Checkpoint** field appears and
   *Station / Branch / Unit* disappears; choose **Sool → Laascaanood** and the
   checkpoint list holds only active Laascaanood checkpoints (e.g. *Adhi Cadeeye
   Outpost*); switch the role to *Fingerprint Unit* — the station/branch list
   appears instead. Change the region and confirm the district and posting reset.
3. Still in **User management**: every officer row shows a badge chip
   (`Badge #FP-102`); **Audit trail** lists the latest events with the acting
   officer's badge, and the filter narrows by record type.
4. As `fp.officer`, approve a clearance application with a signed scan, then open
   **Dashboard** without reloading: the KPI cards and the activity feed already
   show the new approval.
5. Sign in as `chief` (`ChangeMe123!`): the identity block still opens the
   profile, but it is marked view-only and all three endpoints answer
   `403 read_only_role`.

## Checkpoint role unification & record audit history (testing branch)

### Automated
```sh
.venv/bin/python backend/test_checkpoint_roles_audit.py   # real API + throwaway PostgreSQL
node backend/test_record_audit_ui.mjs                     # jsdom: the Audit history tab
```

`test_checkpoint_roles_audit.py` proves: the three seeded checkpoint officers hold the one
`checkpoint_officer` role with their area kept as data (`South` / `East` / `West`), the assignable
role list offers Checkpoint Officer exactly once and no compound role, the cascade creates a
district checkpoint officer (`Adhi Cadeeye Outpost · Laascaanood · Sool`, scope = the posting,
`CP-` badge), every legacy spelling (`CheckpointSouth`, `checkpoint_east`, `cp.west`,
`Checkpoint Officer (South)`) still creates a working unified officer with the right scope,
`unify_checkpoint_roles()` rewrites hand-inserted compound rows in place (keeping an explicit
`location_scope`) and is idempotent, and the migrated officer signs in with the unified role.
It then drives a full record history: person creation, clearance application, signed-scan upload
and approval all appear on `GET /api/persons/{id}/audit-history` with badge attribution, newest
first, and are a subset of `GET /api/admin/audit`; a checkpoint officer sees only their own
screening and never fingerprint events, another checkpoint area never sees it, and
`GET /api/audit/entity/...` gates stations/officers/user accounts by module (403 for a checkpoint
officer) with a 404 for an unknown entity kind.

`test_record_audit_ui.mjs` proves, in the real page script: the Person Details modal carries the
**Audit history** tab and panel, the timeline renders *Created / Updated / Uploaded / Approved* with
the acting officer and badge chips (including the `#Not recorded` fallback), events are newest
first, the counter matches, audit details are escaped (no markup injection), empty and refused logs
are explicit, and the Station View drawer plus Police Registration records load the same trail from
the generic endpoint.

### Officer UAT checklist
1. Sign in as `admin` → **User management** → **New officer**: the Role list has one
   **Checkpoint Officer** entry (no “(South) / (East) / (West)” variants). Choose it, then
   **Sool → Laascaanood → Adhi Cadeeye Outpost**: the officer is created and its row shows
   *Checkpoint Officer · Adhi Cadeeye Outpost Checkpoint*.
2. Open the officer’s **Edit** drawer: the role shows *Checkpoint Officer* and the posting is
   pre-selected in the cascade. Switch the role to *Fingerprint Unit*: the Checkpoint field is
   replaced by Station / Branch / Unit; switch back and the checkpoint list returns.
3. Sign in as `cp.south` (`ChangeMe123!`): the header reads *Checkpoint Officer · South Checkpoint*
   and the checkpoint register shows only South screenings.
4. Open **Persons → any person → Audit history**: the tab lists the identity’s events newest first
   with the acting officer and badge. As `fp.officer` open a person with a clearance application:
   the creation, the signed-scan upload and the approval all appear on the same record.
5. As `cp.south` open the same person: only the checkpoint screening you performed (and identity
   events) appear — no fingerprint application events.
6. **Police Stations → View** on a station: the *Audit history* section lists its registration and
   edits with the administrator’s badge.

## Branch Management — Edit / Deactivate + legacy placement cleanup (2026-10-27)

Branch: `arena/b4919f35-sentinel-police-management` (feature branch `arena/branch-management-crud`).
Do not merge until UAT is approved. Restart the backend and hard-refresh the browser when testing
this branch (`?v=` stamps and the UI build marker were republished as
`sentinel-branch-crud-1-e7c41b90`). Use a test database and synthetic identities only.

### What changed
- **Actions column + Edit Branch modal.** The Branch Management table gained **Status** and
  **Actions** columns; every row has **Edit** (`openBranchEdit()`) and an
  **Activate / Deactivate** toggle (`toggleBranchActive()`), both `.admin-edit`. The modal
  (`#branchEditModal`) edits the name, Region → District, Unit Department and the Active / Inactive
  status, and saves through `PATCH /api/admin/branches/<id>`.
- **Edit is in place, never delete/re-create.** `police_branches.id` stays the FK target for
  clearance applications, airport records, CID cases, checkpoint events and mirrored stations, so
  the branch table's `active` / `updated_at` / `updated_by` columns are added by the idempotent
  `ADDED_COLUMNS` migration (pre-existing rows backfill to Active).
- **Posting links survive a rename.** `relabel_branch_postings()` rewrites the free-text
  `users.branch` (and a checkpoint officer's named `location_scope`) that pointed at the old name,
  so an active officer keeps their locked intake posting; the count is returned as
  `relabelled_postings` and printed in the audit detail.
- **Mirrored stations follow the branch.** `sync_mirrored_station_for_branch()` moves the mirrored
  `police_stations` row (name / region / district / derived village) without touching its id.
- **Retire, don't delete.** An Inactive branch is excluded from the intake dropdowns
  (`refreshBranchSelect`), the sidebar trees (`unitNavCatalog`), the Unit Directory and NEW intake
  writes (`resolve_branch()` → 400), while every existing record / posting stays linked.
  `GET /api/branches?active=1` / `?active=0` make the split explicit; the default response keeps
  the previous shape and now also carries `active` / `status` / `unit_label` / `legacy_reason`.
- **Real-time sidebar sync.** `applyBranchUpdate()` merges the saved row into the one
  `branchCatalog` and `repaintBranchConsumers()` repaints the Region → District → unit trees, the
  Unit Directory, the branch datalist and any open intake selector — no reload.
- **Legacy cleanup tool.** `#branchLegacyPanel` lists every branch that still lands under
  *Unassigned district* (blank / placeholder / non-gazetteer placement) with the reason, and
  batch-assigns the selection through `POST /api/admin/branches/bulk-assign`
  (`{ids, region, district}` → `{updated, skipped, counts}`). Conflicts are reported per row.
- **API + RBAC.** `GET /api/admin/branches` (SystemAdmin) returns every branch including inactive
  ones, the `unassigned` queue, the gazetteer and counts. `PATCH /api/admin/branches/<id>` (alias
  `PATCH /api/branches/<id>`) answers **403** `code: admin_only` for every non-admin (including the
  HR Directorate, which may read the catalogue), **409** for a duplicate name + region + unit,
  **400** for an invalid district and **404** for an unknown id; each applied edit writes an
  `UPDATE police_branch` audit row.

### Manual verification
1. Sign in as `admin` (`ChangeMe123!`) → **Administration → Branch Management**. The table lists
   every branch with **Status** and **Actions**; a row whose District is blank shows the amber
   *Unassigned district* badge and the reason under its name.
2. **Actions → Edit** on a bare `East Checkpoint` row: rename it to `East Lasanod Checkpoint`,
   set Region **Sool**, District **Laascaanood**, keep *Checkpoint Unit*, status **Active** →
   **Save changes**. The row is renamed and re-placed, and the **Checkpoint Units** accordion in
   the sidebar moves that unit from *Unassigned district* into **Sool → Laascaanood** without a
   page reload. `PATCH /api/admin/branches/<id>` is the only write in the Network tab.
3. **Deactivate** the same branch: the status badge turns Inactive, the toast explains that
   records/postings keep their link, and the unit disappears from the sidebar tree and from
   **Checkpoint → New screening** branch selector. **Activate** restores both.
4. **Legacy placement cleanup**: if any row is still unplaced, select a few (or *select all*),
   choose e.g. **Sool → Laascaanood** and **Assign selected branches** — the queue shrinks, the
   panel disappears when it empties, and the units are in the gazetteer tree.
5. **Non-admin check**: sign in as `fp.officer` or `chief`. The Edit / toggle controls are hidden,
   and forcing `PATCH /api/admin/branches/1` returns **403** `admin_only` (the Commander is refused
   even earlier with `read_only_role`).
6. **Posting preservation**: as `admin`, edit an account's **Branch** to a new branch name, rename
   that branch in Branch Management, then reload the account: its posting shows the new name and
   the officer's intake selector stays locked.
7. Confirm the sidebar footer reports `sentinel-branch-crud-1-e7c41b90`, matching
   `/api/health` → `ui_build` / `asset_version`, and `python backend/server.py --ui-check` exits 0.

### Automated
- `node backend/test_branch_management_ui.mjs` (jsdom) — Actions column, prefilled Edit modal,
  rename + re-place moving the unit between sidebar accordions in real time, Deactivate/Activate
  removing and restoring it in the tree, the batch cleanup sending one `bulk-assign` request and
  emptying the queue, and a non-admin session being refused before any PATCH leaves the browser.
- `python3 -m pytest backend/test_branch_management_crud.py -q` — pure validation of
  `plan_branch_update()` (PATCH semantics, gazetteer rules, name/region/district/length limits,
  Active/Inactive coercion), `branch_view()` lifecycle fields, `branch_legacy_reason()`, the
  frontend/asset-stamp contract, and a live PostgreSQL suite covering the admin catalogue, the
  403/404/409/400 answers, rename + re-placement, the active filter, batch assignment, the
  mirrored-station rename, the officer-posting relabel and the `UPDATE police_branch` audit rows
  (the live part SKIPs when no PostgreSQL engine is available).
- The rest of the suite (`test_dynamic_branches.py`, `test_station_actions.py`,
  `test_branch_scope.py`, `test_read_only_rbac.py`, `test_sidebar_navigation.mjs`,
  `test_station_frontend.mjs`, …) still passes; `test_server.py` and `test_conduct_frontend.mjs`
  remain on the retired SQLite harness and were already failing before this branch.
