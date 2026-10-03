# Phase 2 — Operational Units (Checkpoints · Airports · Stations)

Port of the legacy checkpoint log, airport arrival/departure log and station crime-incident intake onto the unified
architecture. Schema: `migrations/003_operational_events.sql` · Service: `app/operations/` · API: `app/server.py` ·
UI: `web/operations.html` + `web/operations.js` · Tests: `tests/test_operations.py`, `tests/ui/ops_flow.test.mjs`.

## 1. The rule every event follows

```
operational event  ──person_id──▶  persons (ONE global registry, Migration 001/002)
        │
        └──unit_id──▶  org_units (airport | checkpoint | station)  ──▶  region ∈ {Sool, Sanaag, East Togdheer}
```

* **Identity.** Checkpoint travelers and guardians and airport passengers go through the Phase 1 `registry.register()`:
  exact ID → "Person already exists in registry"; fuzzy name → a pick-list the officer must confirm (HTTP 409, never
  an automatic link); otherwise a new record. Core identity stays immutable for these officers.
  Crime-incident **victims are different on purpose**: a victim is linked to the registry only when the officer's
  National ID matches an existing person. A victim is never auto-created (a victim is not someone the police should
  start a registry file on, and an anonymous victim must keep no identity).
* **Unit scope.** Create rights are unit-scoped (`authz_can(user, perm, unit)`): `cp.south` cannot file at `CP-EAST`.
  Reads are scoped by `authz_scope`: a station sees its own incidents, a regional commander their region, the
  Chief Commander (one root assignment with descendants) everything, read-only. Row-level security repeats the check
  in the database for any non-owner connection (`SENTINEL_DB_ROLE=app_rw`, the dev default).
* **Region scope is data.** A unit may receive events only if its region ancestor's code is in
  `policy_settings 'operations.regions'` = `["SOOL","SANAAG","ETOG"]`. The DB refuses anything else.
* **Data-only expansion.** Adding the Buuhoodle airport is one `INSERT INTO org_units` (district `D-BUUHOODLE`, type
  `airport`) plus an assignment — shown in `migrations/dev/003_demo_operational.sql`. No code, no migration, no UI change:
  the unit list, the forms, the scoping and the person timeline all pick it up. Tested in `test_operations.py`
  and in the UI flow ("the DATA-ONLY Buuhoodle airport works for its own officer").

## 2. API

| Endpoint | Purpose |
|---|---|
| `GET /api/operations/units` | Checkpoints / airports / stations this user may file at (`can_create`) or view |
| `GET /api/operations/vocabularies` | Incident dropdown lists and checkpoint/airport rules — all policy data |
| `POST /api/checkpoint-events` | One stop: traveler + purpose + photo + documents + guardian. Returns alert flag (yes/no only) |
| `POST /api/airport-records` | One arrival/departure. Duplicates are refused (409) |
| `POST /api/crimes` | One incident |
| `GET /api/checkpoint-events` `/airport-records` `/crimes` | Scoped lists (`unit`, `person`, filters) |
| `POST /api/uploads` · `GET /api/uploads/{name}` | Raw-body upload (`X-Filename`); a file is readable by its uploader or by anyone who may view a record that references it |
| `GET /api/persons/{ref}/timeline` | Every checkpoint stop / airport movement / incident on one person, across all units, limited to what the caller may see |

Errors use the Phase 1 shapes: `422 {fields, problems}` (all problems at once), `409 possible_duplicate` with the
candidate list, `403`, `404`.

## 3. What was ported unchanged

* **Checkpoint:** purpose, address, traveler photo (required), ≥1 traveler document, guardian for every traveler with
  relationship + ≥1 guardian document (legacy rule), flagged-match banner (red, "supervisor contacted").
* **Airport:** arrival/departure, flight, airline, origin required for arrivals, destination for departures.
* **Incident:** required fields, vocabularies (categories, severities, statuses, reporting party, victim gender,
  evidence types), anonymous victim, two evidence slots (pdf/jpg/png, a file needs its type), `CRM-…` file numbers.

## 4. Deliberate changes and additions (please review)

| # | Change | Why |
|---|---|---|
| O1 | **Alert screening returns yes/no only** (`person_alert_flag`, SECURITY DEFINER, needs `alert:check`). A stop by a user without `alert:check` is refused rather than silently reading "no alert". | Checkpoint officers must never see alert records. |
| O2 | **Checkpoint / airport logs are append-only**; a crime incident can change only `case_status`; nothing is deleted. `created_by` is stamped by the database from the session. | Evidence-grade logs. A correction is a new record. |
| O3 | **Duplicate airport record = DB unique index** (person + movement + flight + date + airport). There is no "confirm duplicate" override. | Double-submit and two desks cannot both succeed. |
| O4 | **Airport travel date window: 60 days past, 7 days future** (`airport.travel_window_days`). Legacy accepted anything. | New rule — change the setting if the business disagrees. |
| O5 | **Guardian requirement is a policy setting** (`checkpoint.required.guardian`: `all` / `minors` / `none`), default = legacy "all travelers". | Legacy rule kept; now adjustable. |
| O6 | **Upload content is verified by magic bytes**, not file extension; size-limited; stored outside git (`uploads/`, gitignored, `SENTINEL_UPLOAD_DIR`). | Legacy trusted the extension. |
| O7 | **Incident desk officer is optional but validated** (must be an active officer posted at that station, via `desk_officer()`). | Legacy required it, but the HR officers module is not ported yet. |
| O8 | **Victim registry link** is one nullable column `victim_person_id`; never set for an anonymous victim (DB-enforced). | Legacy victims were free text. |
| O9 | A future `incident_at` is refused (5-minute clock tolerance). | New rule. |

## 5. Running the tests

```
python -m unittest tests.test_operations                  # 61: DB rules, RLS, service, HTTP, uploads
python -m unittest discover -s tests -t .                 # 145 Python tests in total
SENTINEL_DB_ROLE=app_rw python -m unittest discover -s tests -t .   # same, with row-level security enforced
(cd tests/ui && npm install) && python -m tests.run_ui_flow         # 15 intake + 14 operations UI steps (jsdom)
```

## 6. Limits and roadmap

| # | Item |
|---|---|
| R1 | **No API to update an incident's `case_status`.** The database already allows exactly that one column to change; the endpoint and a UI control are the next step (legacy had none either). |
| R2 | **Suspects / persons of interest on incidents** are not modelled (legacy had none). Needs a party table linked to `persons` with a role per incident. |
| R3 | **Uploads are written to disk before the transaction commits**, so a rolled-back save can leave an orphan file. Harmless (nobody references it) but needs a periodic sweep. |
| R4 | The desk officer check still reads the `officers` table directly (the HR module is now in place — see [`DIRECTORATE.md`](DIRECTORATE.md); switching is optional). |
| R5 | **Checkpoint-to-person alert history** (what happened after a flag) is not recorded; only the stop is. |
| R6 | **Offline checkpoints.** The form needs a connection. Queue-and-sync would be a separate piece of work. |
| R7 | **UI verified with jsdom only**, not a real browser; photo capture from a device camera is the plain file picker. |
| R8 | Fingerprint/clearance, CID and HR conduct are the national directorate services from decisions D1/T1–T3 — delivered in Phase 3, see [`DIRECTORATE.md`](DIRECTORATE.md). |
