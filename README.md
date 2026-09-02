# Sentinel Police Management

A working browser-based prototype for a central police management platform. It is designed around a single Central Person Registry with separate unit records.

## Included units

- Central Person Registry
- Fingerprint Unit and clearance applications
- Clearance approval and certificate number generation
- CID criminal cases
- Suspect list
- South, West and East Checkpoints
- Hargeisa Local Airport passenger register
- Dashboard and cross-unit activity feed

## Central-person linking model

Every person receives one central `Person ID` (`P-0001`, etc.). Unit registers store their own records and reference this ID:

- Airport: movement type, travel date, flight number, airline/carrier, origin city, destination city and travel notes
- Fingerprint: clearance purpose, guardian, relationship, legal document references and review status
- CID: case participants and case references
- Checkpoint: screening events and actions taken

### Smart identity resolution (single unified form)

There is **one unified person entry form** used everywhere (Central Persons, Add Suspect, Airport, Fingerprint, Checkpoint and CID participants). It captures the **4-part full name (first, second, third, fourth), date of birth, National ID / Passport, mother's name and address** — there is no manual "existing person vs new person" toggle.

As the officer types, the form performs **real-time background matching** against the Central Person Registry — case-insensitive and whitespace-trimmed:

- **Exact match** (National ID/passport, or 4-part name + DOB) → success banner **"Matched Central Record: [ID] - [Name]"** and the existing data auto-populates.
- **Partial/full name match (2, 3 or 4 name components)** and partial ID/passport matches → a **live dropdown** lists the matching Central Persons (Full Name, NID/Passport, DOB). **Clicking a match instantly auto-fills all existing central data** (name, mother's name, DOB, National ID, Passport, address, phone, photo) and shows the green **"Matched Central Record: [ID] - [Name]"** banner.
- **Fuzzy 3-part name + mother's name** → amber warning prompt listing candidate records; the officer confirms before linking (Tier 3 is never an automatic merge).
- **No match** → the form shows a notice and submission **auto-creates the Central Person first**, then attaches the unit/suspect record.

The same interactive matching engine (Tier 1 exact ID/passport auto-merge, Tier 2 exact 4-part name + DOB high-confidence link, Tier 3 fuzzy warning, Tier 4 partial-name dropdown) is applied across **Checkpoints, Airport Control, Fingerprint Unit and CID**.

### Central Person enrichment on submission

When a unit record (Airport, Checkpoint, Fingerprint or CID/suspect) links to an **existing Central Person ID**, the backend checks the incoming submission for any values that are still **null/empty** in the person's profile (e.g. Mother's name, Phone, Occupation, Address, Passport ID, photo). It **automatically enriches** the SQLite `persons` record with those non-empty new values **without overwriting existing non-null data** — so an officer can complete a partially-filled profile (e.g. the blank "Mother's name" in the Airport form) and the central record is updated on save.

The same fill-only enrichment applies to the identity-merge path (`/api/persons/upsert` and the unit routes' auto-resolve): matched records never get overwritten, only missing fields are filled.

**Locked auto-filled fields (partial-profile completion):** when a Central Person is matched and auto-filled, only the fields with **actual non-empty text** are set to read-only (greyed out). Any field that came back **blank/`null`** (e.g. Mother's name, Occupation, Contact Number, Address) is left **fully editable and active**, so the officer can complete the missing profile data — and the value is enriched into the central record on save. Officer-entered input into those blanks is never clobbered by the live re-match.

When a matched profile is incomplete, an **info tag** appears under the match banner: *"ℹ️ Matched Profile: P-XXXX. Some details (e.g. Mother's Name) are incomplete — fill them in to enrich this central record."*

### No popups — pages and centered modals

The interface uses **no native browser dialogs**. All create/edit actions happen in **dedicated full-page workspaces** (e.g. the CID case workspace) or **centered modal dialogs** (new person, new case, checkpoint stop, identity review) that open dead-center over a blurred dark backdrop with a fixed header, an internally scrolling body and a sticky footer.

### In-modal errors and the global toast

- Form submission errors, validation warnings and backend API errors are **never** shown as floating toasts. Inside a modal they render as an **inline red alert banner** directly under the modal title (icon + action instructions); the modal body auto-scrolls to the top and any invalid fields get a red border. On the inline page forms they render in the form's own notice area (red variant) — and any other page-level failure shows a transient top-of-page alert.
- The **bottom-right global toast** is reserved exclusively for **success/system notifications** (e.g. "Record saved successfully"). It is redesigned with a check icon, drop shadow, proper padding, crisp typography and an auto-dismiss animation after 4 seconds.

### Fingerprint application, review and certificate

- The expanded clearance application captures applicant data (full name, mother's name, DOB/POB, residence, occupation, passport, National ID, photo, clearance reason) plus **4 applicant file slots (≥2 required)** and guardian data (name, relationship, ID, occupation, address, contact) with **3 guardian file slots (≥2 required)**.
- **`application.html`** — a printable Day-1 review summary the applicant verifies, with an **Approve Application** action for authorized officers.
- **`certificate.html`** — the official Day-2 clearance certificate. It is **locked until an officer approves** the application, then unlocks for printing.

### CID case workspace and optional case linking

Each case opens in a full-page workspace with three tabs: **1) Case Details & Incident Summary**, **2) Participants & Suspect List Linkage** (suspect/victim/witness/complainant, with suspects creating checkpoint/airport alerts), and **3) Evidence & Media Storage** (file uploads with captions).

The **Add Suspect** modal makes the **linked case strictly optional**: a suspect can be listed with a case, or without one, in which case the origin is recorded as **"Direct Intelligence Listing"** or **"Manual Entry"**. The suspect endpoints (`POST /api/suspect-alerts`) accept an optional `case_id` and store the origin server-side.

### Role-Based Access Control & location-isolated checkpoints

Officers sign in with one of seven roles. The sidebar, top-bar user pill, and every API call are scoped to the role:

- **System Admin** — full access to every module plus the Executive Analytics dashboard and the User Management page.
- **Fingerprint Unit** — Fingerprint module only.
- **Airport Control** — Airport module only.
- **CID Criminal Unit** — CID / suspect alerts only.
- **Checkpoint South / East / West** — only the Checkpoint module, **scoped to their assigned location**; `GET /api/checkpoint-events` returns a `scope` and `visible_locations` payload so the frontend can render the active filter, and `POST /api/checkpoint-events` rejects events at any other location.

The top bar shows the active officer and location, e.g. **Officer H. Xasan · South Checkpoint**, and the sidebar hides modules the user cannot use. Server-side enforcement mirrors the UI: a non-admin token cannot reach `/api/admin/*` or the analytics aggregation, and a Fingerprint officer cannot list Airport or Crime records.

**Session persistence (refresh-safe sign-in).** On sign-in the auth token and user object are stored in browser storage (`localStorage.setItem('sentinel_token', token)` and `localStorage.setItem('sentinel_user', JSON.stringify(user))`, plus the legacy `sentinelSession` object used by the printable pages). On every page load `initApp()` re-hydrates `currentUser` and `authToken` **before** the initial API sync (`syncServer` / `fetchCheckpoints`), and every request automatically carries `Authorization: Bearer ${token}`. A refresh therefore never signs the officer out: only an explicit HTTP **401** from the dedicated auth check (`GET /api/me`) clears the session — non-fatal startup errors (server still booting, transient 5xx, a 404) keep the officer signed in and retry in the background.

**Role normalization.** Every accepted Checkpoint-officer spelling (`CheckpointSouth` / `CheckpointEast` / `CheckpointWest`, `checkpoint_south`, `cp_south`, `cp.east`, `Checkpoint Officer (West)`, …) is normalized to the canonical role **`checkpoint_officer`** while the officer's `location_scope` (`South` / `East` / `West`) is preserved (and derived from the alias when not passed explicitly). `GET /api/dashboard` and `GET /api/checkpoint-events` return HTTP 200 for all of these roles — never 404/401 for a valid checkpoint officer — and the checkpoint query matches the location case-insensitively (`LOWER(location_code) = 'south' OR LOWER(checkpoint_location) LIKE '%south%'` and equivalent columns).

**Checkpoint table freshness.** `submitCheckpoint()` prepends the new stop into `db.checkpoints` immediately so the table and the location badge update instantly (`South Checkpoint 0 → 1`), and `syncServer()` never overwrites `db.checkpoints` with `[]` from a transient/failed response — only a successful response with rows replaces the local cache.

### Executive Analytics dashboard (admin only)

The **Analytics** page (admin only) renders lightweight canvas charts backed by `/api/admin/analytics`:

- **Crime incident heat / distribution** — crime case counts per location (district) and per time-of-day bucket (Morning 06-12, Afternoon 12-18, Evening 18-24, Night 00-06).
- **Checkpoint volume & demographics** — total screening events per checkpoint (South vs. East vs. West) split by traveler age brackets (`<18`, `18-30`, `31-50`, `50+`).
- **Operational summary** — KPI tiles for total central persons, active suspect alerts, airport movements and fingerprint records, plus a full summary card (cases total / open, checkpoint events / flagged).

### Admin User Management (admin only)

The **User Management** page (admin only) lets a System Admin create, edit, activate and deactivate officers and assign their role and location scope. The backend supports `GET /api/admin/users`, `POST /api/admin/users`, `PATCH /api/admin/users/{id}` and `GET /api/admin/users/{id}` for headless provisioning.

A standalone migration script applies the RBAC schema to an existing database without re-creating it:

```bash
python3 backend/migrate_rbac.py
```

## Architecture

The system now has two parts:

- **Frontend** — `index.html`, a single-page browser application.
- **Central backend** — `backend/server.py`, a Python (standard library only) HTTP API backed by SQLite. It serves the frontend and a JSON REST API from the same origin, and enforces the central-person rule on the server.

Airport, Fingerprint, CID and Checkpoint unit records are all written to the central database; checkpoint screening results (Flagged match / No active alert) are computed server-side from active suspect alerts, and the action follows automatically (Supervisor contacted / Cleared).

The frontend automatically uses the central backend when it is loaded through `backend/server.py`. If it is opened as a static file with no server, it falls back to browser local-storage demo mode (a "Local demo mode" notice appears in the browser console).

## Run locally (full stack)

Python 3 is enough — no packages to install:

```bash
python3 backend/server.py
```

Windows:

```bash
py backend/server.py
```

Then open `http://localhost:8001` (the backend serves the UI and the API together). The port can be changed with the `PORT` environment variable, and the database location with `SENTINEL_DB`.

### Demo accounts (development only)

Seven demo users are seeded automatically on first run — one per role — all with
password `ChangeMe123!`. This makes it easy to exercise the role-based access
control and location-isolated checkpoints:

| Username     | Role                | Scope / Module             |
|--------------|---------------------|----------------------------|
| `admin`      | System Administrator| All modules + analytics + user management |
| `fp.officer` | Fingerprint Unit    | Fingerprint only           |
| `ap.officer` | Airport Control     | Airport only               |
| `cid.officer`| CID Criminal Unit   | CID / suspect alerts only  |
| `cp.south`   | Checkpoint South    | Checkpoint · South only    |
| `cp.east`    | Checkpoint East     | Checkpoint · East only     |
| `cp.west`    | Checkpoint West     | Checkpoint · West only     |

These accounts are created automatically on first run and must be removed or
changed before any real deployment. To add a real admin, sign in as `admin`
and use the **User Management** page in the UI, or `POST /api/admin/users`.

See [`backend/README.md`](backend/README.md) for the full API reference,
including the RBAC enforcement rules.

### Frontend-only demo

To view just the interface with local-storage data (no server):

```bash
python3 -m http.server 8000 --bind 0.0.0.0
```

Open `http://localhost:8000`.

## Testing

Backend API suite (standard library only; boots the server against a temporary database):

```bash
python3 backend/test_server.py
```

Covers the identity-resolution tiers, unit-record routes, RBAC module gating, location-scoped checkpoint reads/writes, role-alias normalization (`cp_south` / `CheckpointEast` → `checkpoint_officer` with the scope preserved), the `/api/dashboard` contract for every role and the analytics aggregation.

Frontend session smoke test (Node ≥ 18; executes the real inline script against the real backend in a VM sandbox):

```bash
node backend/test_frontend_session.mjs
```

Verifies the checkpoint-officer refresh journey: sign in as `cp.south`, token/user persisted to `sentinel_token` / `sentinel_user`, page refresh re-hydrates the session before the API sync (no auto-signout, no 401/404), the checkpoint count survives the refresh, an empty server sync never wipes local rows, a bogus token signs out only via an explicit `/api/me` 401, and a server-down load keeps the officer signed in.

## Demo workflow

1. Open **Airport** and type `Ayaan / Cabdi / Xasan / Axmed`, DOB `1997-04-18` and `10012345` — the unified identity form matches central person `P-0001` in real time and auto-fills the existing data.
2. Open **Fingerprint Unit** and type the same identity; an exact match auto-fills the applicant fields.
3. Complete clearance reason, guardian details, and attach **at least 2 applicant and 2 guardian documents** (plus an optional photo), then save.
4. In the Fingerprint register click **Review/Print** to open `application.html` — print the Day-1 summary and use **Approve Application**.
5. After approval, click **Certificate** to open `certificate.html` — the Day-2 clearance certificate is now unlocked and printable.
6. Open **CID Criminal Unit → Add suspect** and type a new identity. See the real-time match banner; submit **without a linked case** and the suspect is recorded with origin **Direct Intelligence Listing**. The **Suspect reason / alert details** field is **mandatory when no Crime Case is linked**; when a case IS linked it can be left empty and automatically defaults to `Linked to CID case {code} — {category}`. Submitting with an exact match reuses the existing central record.
7. Open a case workspace: edit the incident summary (tab 1), link participants (tab 2 — choosing *Suspect* raises a checkpoint/airport alert; the case is optional, and a participant note is required when no case is linked), and upload evidence (tab 3).
8. Open **Checkpoints → Record stop** for a listed suspect and see the automatic "Flagged match" screening. The stop is saved to the central database and the screening result is computed server-side against active suspect alerts. The checkpoint modal is a **full traveler + guardian screening layout**: traveler (4-part name, DOB, place of birth, current/permanent address, purpose of visit, real-time photo, optional National ID/Passport, **≥1 of 2 document slots**), guardian (name, relationship, contact, permanent address, occupation, optional IDs, **≥1 of 2 document slots**). Smart identity resolution auto-fills **both** traveler and guardian, and all uploaded files are stored in `backend/uploads/` and referenced from the stored event.

Uploaded files are stored in `backend/uploads/` (git-ignored) and served from `/uploads/`.

## Important implementation note — development only, not for operational police data

This is now a **connected development system**: the browser UI talks to a central
backend API, and server data is stored in SQLite instead of only browser local
storage. **It is still not ready for real police data.** It currently uses:

- **SQLite** instead of a production database (PostgreSQL)
- **Development authentication** — a single hard-coded demo login (`admin` / `ChangeMe123!`), in-memory session tokens, and unsalted SHA-256 password hashing
- **No HTTPS** — traffic is plain HTTP
- **Role- and location-based permissions partially implemented** — the server now enforces role-based access control for the operational modules (System Admin / Fingerprint Unit / Airport Control / CID / Checkpoint South·East·West) and location isolation for Checkpoint users, and the Executive Analytics dashboard surfaces summary metrics, crime distribution and checkpoint demographics for admins. The hard-coded demo logins and the unsigned `ChangeMe123!` default password are still in use.
- **No production deployment** configuration
- **No evidence file security** or chain-of-custody storage
- **No backup service** or disaster-recovery process

Before operational use, the hardening work **must** include, at minimum:

- **PostgreSQL** (or another managed production RDBMS) with migrations and least-privilege database users
- **Secure password storage** (salted, slow hashes such as Argon2/bcrypt) and real account provisioning
- **Role- and branch-based permissions** enforced on the server, with per-unit access control
- **HTTPS / TLS** for all traffic, plus secure cookies/headers and secrets management
- **Immutable, tamper-evident audit logging** (append-only, with integrity protection)
- **Evidence file storage with chain of custody** (encrypted at rest, access-logged, retention-enforced)
- **Automated backups and tested disaster recovery**
- **Production-grade authentication** (identity provider / SSO or properly managed auth, MFA, lockout)
- Server-side validation and duplicate matching across the full data model
- Certificate QR verification
- Network/offline synchronization policy
- Legal rules for suspect alerts, clearance decisions and data retention
- Supervisor confirmation for possible suspect matches

The local-storage fallback in the frontend is for demo convenience only and is
not appropriate for live police operations or multiple computers.

The current data model is intentionally compatible with a relational implementation using tables such as `persons`, `unit_records`, `airport_passengers`, `clearance_applications`, `crime_cases`, `case_participants`, `suspect_alerts`, `checkpoint_events`, `locations`, `users`, and `audit_events`.
