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
