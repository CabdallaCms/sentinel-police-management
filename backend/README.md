# Sentinel backend foundation

This is the server-side foundation for the Sentinel system. It uses only Python's standard library and SQLite so it can run immediately without installing packages.

## Start

From the project root:

```bash
python3 backend/server.py
```

Windows:

```bash
py backend/server.py
```

The API runs on `http://localhost:8001`.

## Demo accounts

Seven demo users are seeded automatically on first run — one per role — all with
password `ChangeMe123!`:

| Username     | Role                | Scope / Module             |
|--------------|---------------------|----------------------------|
| `admin`      | System Administrator| All modules + analytics + user management |
| `fp.officer` | Fingerprint Unit    | Fingerprint only           |
| `ap.officer` | Airport Control     | Airport only               |
| `cid.officer`| CID Criminal Unit   | CID / suspect alerts only  |
| `cp.south`   | Checkpoint South    | Checkpoint · South only    |
| `cp.east`    | Checkpoint East     | Checkpoint · East only     |
| `cp.west`    | Checkpoint West     | Checkpoint · West only     |

To re-seed / upgrade an existing database to include the demo users, run:

```bash
python3 backend/migrate_rbac.py
```

Change or remove these accounts before any real deployment.

## Role-Based Access Control (RBAC)

Every authenticated request is scoped to the user's role. The full role set is:

- `SystemAdmin` — full access, including `/api/admin/*` (User Management and
  Executive Analytics) and `GET /api/checkpoint-events` (sees all locations).
- `FingerprintUnit` — only `/api/clearance-applications*`.
- `AirportControl` — only `/api/airport-records*`.
- `CIDUnit` — only `/api/crime-cases*` and `/api/suspect-alerts*`.
- `CheckpointSouth` / `CheckpointEast` / `CheckpointWest` — only
  `/api/checkpoint-events*`, **scoped to their assigned location**; a South
  officer cannot see, create, or amend any event at the East or West
  checkpoint. The `GET` response carries a `scope` and `visible_locations`
  field so the client can render the active filter.

`/api/me` returns the current user, the role-derived `modules` list, the
`visibility` summary (`is_admin`, `can_manage_users`, `can_view_analytics`,
`checkpoint_scope`), and a `roles` / `role_labels` /
`checkpoint_locations` roster for building admin dropdowns.

## Identity resolution (universal matching engine)

Every operational module (Airport, Checkpoint, Fingerprint, CID) uses the same Smart Identity Resolution:

| Tier | Criteria | Behaviour |
|------|----------|-----------|
| **Tier 1** | Exact National ID **or** Passport match (case/space insensitive) | Auto-merge / link — existing Central Person record is returned and unit data is attached to it |
| **Tier 2** | Exact 4-part name (first + second + third + fourth) **and** date of birth | High-confidence link — existing record is reused/merged automatically |
| **Tier 3** | 3-part name + mother's name | Fuzzy warning only — candidates are returned; the officer must confirm before linking |
| **Tier 4** | **Partial name match** — 2, 3 or 4 entered name components all present in the stored name | Matching Central Person surfaced; the officer **selects the record** from the interactive dropdown to auto-fill and link |

- `POST /api/persons/resolve` runs the engine in real time while an officer types. Matching is **case-insensitive and whitespace-trimmed**, and also covers partial National ID / Passport prefixes.
- The response includes `matched`, `tier`, `reason`, the matched `person` and **`suggestions`** — an ordered list of candidate Central Persons (full name, National ID/Passport, DOB) that the frontend renders as a live **matching dropdown**. Clicking a suggestion auto-fills all existing central data (name, mother's name, DOB, IDs, address, phone, photo) and shows the green **"Matched Central Record: [Person ID] - [Full Name]"** banner.
- Unit record endpoints (airport, checkpoint, suspect, clearance) accept **either** an existing `person_id` **or** the full identity fields. If no exact match (Tier 1/2) exists, the Central Person record is **auto-created first** and the unit record is attached to it. This is the single unified entry flow — there is no manual "existing vs new person" toggle.
- Persons store a first/second/third/fourth name plus `full_name`; legacy databases are migrated and name parts are backfilled automatically.
- National ID is optional as long as a Passport ID is supplied (and vice versa).

## Optional linked case (suspects)

- `POST /api/suspect-alerts` no longer requires `case_id`. When no case is linked the suspect origin is recorded as **`Direct Intelligence Listing`** or **`Manual Entry`** (sender-supplied; default `Direct Intelligence Listing`).
- Case-linked suspects are recorded with origin **`Case Link`**.
- `GET /api/suspect-alerts` returns `case_id` as the case code (e.g. `CID-2026-009`) or `null`, plus the `origin` column.
- Duplicate prevention: a person can have one active alert per case **or** one active alert without a linked case.

## Sessions

- `POST /api/login` returns a bearer token **and** sets an `HttpOnly`
  `sentinel_session` cookie; either transport authenticates the request.
- Sessions are persisted in a `sessions` table, so a token keeps working
  after a server restart. (Tokens used to live only in an in-memory map, so
  every restart made `GET /api/me` answer **401** and pushed the frontends
  into their offline fallbacks.)
- `GET /api/me` returns the active user, e.g.
  `{"username": "fp.officer", "role": "FingerprintUnit",
    "role_spec": "fingerprint_officer", "visibility": {"is_admin": false}}`.
  `role_spec` is the snake-case spec alias (`fingerprint_officer`, `admin`,
  `airport_officer`, `cid_officer`, `checkpoint_officer`) and never defaults
  to `admin`.
- `POST /api/logout` revokes the token and clears the cookie.

The printable pages (`application.html`, `certificate.html`) have **no
development admin fallback**: with no valid session (or on a 401 from
`/api/me`) they clear the stored keys, show a "Sign in required" screen and
render every record **locked**.

## Current endpoints

- `POST /api/login`
- `POST /api/logout` (authenticated)
- `GET /api/health`
- `GET /api/me` (authenticated)
- `GET /api/persons?q=...` (authenticated — searches name parts, full name, National ID, passport, phone, mother's name, Person ID)
- `POST /api/persons` (authenticated — strict create, 409 if the National ID/passport already exists)
- `POST /api/persons/resolve` (authenticated — Tier 1/2/3/4 smart identity resolution with flexible partial-name matching and dropdown `suggestions`)
- `POST /api/persons/upsert` (authenticated — Tier 1/2 merge or create; returns `created`)
- `PATCH /api/persons/{person_id}` (authenticated — append/update profile details)
- `GET /api/persons/{person_id}` (authenticated — profile plus linked airport/clearance/CID records)
- `GET /api/airport-records` / `POST /api/airport-records` (authenticated — accepts `person_id` or identity fields; auto-creates the central person)
- `GET /api/clearance-applications` (authenticated)
- `POST /api/clearance-applications` (authenticated, `multipart/form-data` — applicant identity fields, 4 applicant docs and 3 guardian docs with **at least 2 of each required**, optional photo; identity is resolved/auto-created. `purpose` (clearance reason) is **mandatory** and must be one of `Education`, `Travel`, `Employment`, `Citizenship`, `Licence`; the submission timestamp is stored explicitly in `created_at`)
- `GET /api/clearance-applications/{application_id}` (authenticated — full detail for the printable pages, plus the `review` block and `can_approve` flag for the 12-hour gate)
- `POST /api/clearance-applications/{id}/approve` (authenticated — issues the certificate number and unlocks the certificate, subject to the mandatory 12-hour review period)

  `/api/fingerprint/applications` is an alias for `/api/clearance-applications`; every route below it (including `/api/fingerprint/applications/{id}/approve`) behaves identically and is gated by the same `fingerprint` module rule.

  **12-hour approval rule**

  | Caller | Behaviour |
  |--------|-----------|
  | `SystemAdmin` (or any admin alias) | Approves immediately — the review window is bypassed (`review_period_bypassed: true`) |
  | `FingerprintUnit` / `fingerprint_officer` (or any other non-admin reviewer) | Only once `now >= created_at + 12h`; otherwise **HTTP 400** with `{"detail": "Review period active. Standard officers must wait 12 hours before approving."}` plus `hours_remaining` / `review_eligible_at` |

  The gate (`review_gate_decision()`) is evaluated **only** from the stored
  `created_at` and the caller's server-side role — never from anything the
  client sends. It is **fail-closed**: a row with a missing or unparseable
  `created_at` cannot prove the window elapsed, so a standard officer is
  rejected (an admin, who is exempt from the review period, is not).

  The same rule runs as a **boot self-test**: on startup the server prints
  `review lock self-test: PASS (8/8 cases)` after checking officer @0h,
  @11.5h, @13h, a missing stamp, a corrupt stamp, the
  `fingerprint_officer` alias, and the two admin bypasses. If that line is
  missing, the running process is an older build without the lock.

  `GET /api/health` reports `build`, `fingerprint_review_window_hours` and
  `clearance_reasons`, and the same values are printed on startup — handy
  for confirming the running process really is the build with the lock.

  The same rule is mirrored in the UI: `index.html` and `application.html`
  compare `created_at` with the current time for the signed-in user and
  disable the Approve action with a
  `Review Lock (12h Required) - X hours remaining` badge, so a non-admin
  officer never even issues the request.

### Role aliases

Roles are resolved through one normaliser, so every spelling behaves
identically:

| Canonical role | Accepted aliases |
|----------------|------------------|
| `SystemAdmin` | `admin`, `system_admin`, `administrator` |
| `FingerprintUnit` | `fingerprint_officer`, `fingerprint_unit`, `fp_officer` |
| `AirportControl` | `airport_officer`, `airport_control`, `ap_officer` |
| `CIDUnit` | `cid_officer`, `criminal_investigation` |
| `checkpoint_officer` | `CheckpointSouth/East/West`, `cp_south`, `cp.east`, `Checkpoint Officer (West)`, … |

  A row stored as `fingerprint_officer` therefore keeps its modules, RBAC
  gates, role label and review-window behaviour; creating or patching a
  user with an alias stores the canonical role.
- `GET /api/crime-cases` / `POST /api/crime-cases` (authenticated)
- `GET /api/crime-cases/{case_id}` (authenticated — incident summary, participants and evidence)
- `PATCH /api/crime-cases/{case_id}` (authenticated — update status, category, location, summary, notes)
- `POST /api/crime-cases/{case_id}/evidence` (authenticated, `multipart/form-data` — evidence file + caption/type)
- `GET /api/suspect-alerts` / `POST /api/suspect-alerts` (authenticated — participants carry a role: Suspect/Victim/Witness/Complainant; `case_id` is **optional**, `origin` is recorded when no case is linked; `notes`/`reason` is **mandatory for unlinked suspects** — 400 otherwise — and defaults to `Linked to CID case {code} — {category}` when a case is linked and the reason is empty)
- `GET /api/checkpoint-events` / `POST /api/checkpoint-events` (authenticated, `multipart/form-data` — **traveler + guardian screening layout**: traveler 4-part name, date of birth, purpose of visit, current/permanent address, real-time `photo` file, ≥1 `doc_tr_N` file; guardian 4-part name, relationship, contact, permanent address, occupation, optional National ID/Passport and ≥1 `doc_gd_N` file; optional `guardian_person_id` links a known central person. Traveler identity is resolved/auto-created with IDs optional; all file paths are persisted as JSON arrays on the event, and screening result is computed server-side against active suspect alerts, setting the action to `Supervisor contacted` or `Cleared`. **`GET` is location-scoped for Checkpoint users** — the response carries a `scope` and `visible_locations` field, and a Checkpoint officer can only POST at their assigned location)
- `GET /api/admin/users` / `GET /api/admin/users/{id}` (SystemAdmin only — list users; the list response includes a `roles`, `role_labels` and `checkpoint_locations` roster for the admin UI)
- `POST /api/admin/users` (SystemAdmin only — `username`, `display_name`, `role`, `password` (≥6 chars), optional `branch` / `location_scope` / `active`. Checkpoint roles require a `location_scope`.)
- `PATCH /api/admin/users/{id}` (SystemAdmin only — edit `display_name`, `role`, `branch`, `location_scope`, `password`, `active`. Role changes auto-derive the matching `location_scope` unless one is explicitly passed.)
- `GET /api/admin/analytics` (SystemAdmin only — `summary` totals, `crime_distribution` by location + time-of-day bucket, `checkpoint_volume` by location + age-bracket demographics, ready for charts)

Uploaded files are stored under `backend/uploads/` (configurable with `SENTINEL_UPLOADS`) and served from `/uploads/...`. The printable pages are `application.html` (Day-1 review + approve) and `certificate.html` (Day-2 certificate, locked until approval). Both printable pages load the police emblem from `images/police_logo.png` (served at `/images/...` and `/static/images/...`) and render it twice — as the letterhead logo and as a low-opacity (0.08–0.09) centred watermark behind the document content.

The API enforces the central-person rule: Airport, Fingerprint, CID and Checkpoint records must reference a central `person_id` (created or matched automatically from the unified identity form). Person records are merged (never duplicated) when a Tier 1 or Tier 2 match is found; only newly provided fields are updated.

## Tests

```bash
python3 backend/test_server.py        # API suite (Python stdlib only)
node backend/test_frontend_session.mjs # frontend session smoke test (Node >= 18)
```

The backend suite starts the server against a temporary database and
verifies the identity-resolution tiers (including flexible 2/3/4-part
partial name matching, case-insensitive/trimmed search and dropdown
suggestions), optional suspect case linking, auto-create behaviour,
duplicate protection, the **mandatory clearance reasons** (any value
outside the five dropdown options is rejected with 400), the **12-hour
review gate** (a Fingerprint Officer's instant approval fails with 400,
the same approval succeeds once `created_at` is backdated past 12 hours,
and an admin approves a brand-new application instantly), the new
**role-based access control** (per-module
restrictions for each role, location-scoped Checkpoint endpoints,
admin user-management CRUD, deactivated-user lockout), **role-alias
normalization** (`cp_south` / `CheckpointEast` / `checkpoint_officer`
all stored and served as the canonical `checkpoint_officer` with the
`location_scope` preserved), the checkpoint-officer refresh contract
(`/api/me` + `/api/dashboard` + `/api/checkpoint-events` stay HTTP 200
across repeated requests with one bearer token) and the **Executive
Analytics** aggregation (summary, crime distribution by location +
time-of-day, checkpoint volume + traveler demographics).

The frontend smoke test executes the real inline script from
`index.html` in a Node VM against the live backend and verifies that a
page refresh re-hydrates `sentinel_token` / `sentinel_user` before the
API sync, never signs the officer out on non-fatal errors, and never
wipes `db.checkpoints` with an empty sync.

This is a development foundation, not an operational police deployment.
Authentication, database, encryption, roles, file-upload validation and
audit controls need a production hardening pass before use with real
data.
