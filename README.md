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

- Airport: movement, travel date, flight, origin/destination and travel notes
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

### No popups — pages and centered modals

The interface uses **no browser dialogs** and **no right-side slide-out drawers**. All create/edit/detail actions happen in **dedicated full-page workspaces** (e.g. the CID case workspace) or **centered modal dialogs** (new person, new case, add suspect, record stop, and every record's **View** detail).

Every modal opens dead-center over a dark `backdrop-filter: blur(4px)` overlay and always has the same three parts: a **fixed header** (title + close ✕), a **body that scrolls internally** (`max-height: 80vh; overflow-y: auto`) and a **sticky footer** with Cancel + the action button. `Esc` and a click on the backdrop close it, and the page behind it cannot scroll while it is open.

### Fingerprint application, review and certificate

- The expanded clearance application captures applicant data (full name, mother's name, DOB/POB, residence, occupation, passport, National ID, photo, clearance reason) plus **4 applicant file slots (≥2 required)** and guardian data (name, relationship, ID, occupation, address, contact) with **3 guardian file slots (≥2 required)**.
- **`application.html`** — a printable Day-1 review summary the applicant verifies, with an **Approve Application** action for authorized officers.
- **`certificate.html`** — the official Day-2 clearance certificate. It is **locked until an officer approves** the application, then unlocks for printing.

### CID case workspace and optional case linking

Each case opens in a full-page workspace with three tabs: **1) Case Details & Incident Summary**, **2) Participants & Suspect List Linkage** (suspect/victim/witness/complainant, with suspects creating checkpoint/airport alerts), and **3) Evidence & Media Storage** (file uploads with captions).

The **Add Suspect** modal makes the **linked case strictly optional**: a suspect can be listed with a case, or without one, in which case the origin is recorded as **"Direct Intelligence Listing"** or **"Manual Entry"**. The suspect endpoints (`POST /api/suspect-alerts`) accept an optional `case_id` and store the origin server-side.

## UI standards (all modules)

The same layout rules are applied to every operational module — Dashboard, Central Persons, Fingerprint Unit, CID Criminal Unit, Checkpoints and Airport Control.

### Tables

Every register (Crime Cases, Suspect List, Checkpoint Register, Airport Logs, Fingerprint Records, Central Person Registry, case Participants) is a table inside a standardized container card:

- The container has a **fixed `max-height: calc(100vh - 280px)`** and scrolls internally, so the browser window itself does not scroll down the page.
- **`<thead>` is `position: sticky; top: 0`** with a solid background, so the column titles stay frozen while the rows scroll underneath.
- The **rightmost column is always a standardized `Actions` column** with a clear **View** button (plus the module's own actions, e.g. `Review/Print`, `Approve`, `Certificate`). `View` opens the record's centered detail modal.

### Status pills

One shared pill component (`pill()` / `casePill()` / `originPill()` / `unitPill()`) renders every status, with a fixed meaning per colour:

| Colour | Meaning | Examples |
| --- | --- | --- |
| **Red** | Active alerts / flagged matches | `Active alert`, `Flagged match`, `Suspect` |
| **Green** | Cleared / normal | `Cleared`, `No active alert`, `Approved`, `Closed` |
| **Blue** | Manual entry / direct intelligence | `Manual Entry`, `Direct Intelligence Listing`, `Reported` |
| **Purple** | Linked cases | A linked `CID-…` case reference, `Submitted for Prosecution`, CID unit link |
| Amber | Awaiting officer action | `Pending Review`, `Under Investigation`, `Supervisor contacted` |
| Grey | Neutral / reference data | Record ids, `Central`-only records |

The airport register derives its **Screening** pill from the suspect list, so a passenger carrying an active alert shows red in the Airport module as well as at a checkpoint.

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

### Demo account (development only)

- Username: `admin`
- Password: `ChangeMe123!`

This account is created automatically on first run and must be removed or changed before any real deployment.

See [`backend/README.md`](backend/README.md) for the API endpoint reference.

### Frontend-only demo

To view just the interface with local-storage data (no server):

```bash
python3 -m http.server 8000 --bind 0.0.0.0
```

Open `http://localhost:8000`.

### Tests

Both suites use the Python standard library only:

```bash
python3 test_ui.py              # front-end UI contract: modals, sticky tables, pills, wiring
python3 backend/test_server.py  # API, identity-resolution tiers and migrations
```

`test_ui.py` parses `index.html` and fails if a drawer comes back, if a modal loses its fixed header / 80vh scrolling body / sticky footer, if a table loses its sticky header or its `Actions` column, or if an inline handler or element id no longer resolves.

There is also an **optional** browser-level suite that runs the real page in jsdom, clicks the real buttons and submits the real forms in both local demo and full-stack mode — including computed-style assertions for the sticky headers and modal layout. It needs Node:

```bash
cd tests/browser && npm install && npm run test:local && npm run test:server
```

See [`tests/browser/README.md`](tests/browser/README.md).

## Demo workflow

1. Open **Airport** and type `Ayaan / Cabdi / Xasan / Axmed`, DOB `1997-04-18` and `10012345` — the unified identity form matches central person `P-0001` in real time and auto-fills the existing data.
2. Open **Fingerprint Unit** and type the same identity; an exact match auto-fills the applicant fields.
3. Complete clearance reason, guardian details, and attach **at least 2 applicant and 2 guardian documents** (plus an optional photo), then save.
4. In the Fingerprint register click **Review/Print** to open `application.html` — print the Day-1 summary and use **Approve Application**.
5. After approval, click **Certificate** to open `certificate.html` — the Day-2 clearance certificate is now unlocked and printable.
6. Open **CID Criminal Unit → Add suspect** and type a new identity. See the real-time match banner; submit **without a linked case** and the suspect is recorded with origin **Direct Intelligence Listing**. The **Suspect reason / alert details** field is **mandatory when no Crime Case is linked**; when a case IS linked it can be left empty and automatically defaults to `Linked to CID case {code} — {category}`. Submitting with an exact match reuses the existing central record.
7. Open a case workspace: edit the incident summary (tab 1), link participants (tab 2 — choosing *Suspect* raises a checkpoint/airport alert; the case is optional, and a participant note is required when no case is linked), and upload evidence (tab 3).
8. Open **Checkpoints → Record stop** for a listed suspect and see the automatic "Flagged match" screening. The stop is saved to the central database and the screening result is computed server-side against active suspect alerts. The checkpoint modal is a **full traveler + guardian screening layout**: traveler (4-part name, DOB, place of birth, current/permanent address, purpose of visit, real-time photo, optional National ID/Passport, **≥1 of 2 document slots**), guardian (name, relationship, contact, permanent address, occupation, optional IDs, **≥1 of 2 document slots**). Smart identity resolution auto-fills **both** traveler and guardian, and all uploaded files are stored in `backend/uploads/` and referenced from the stored event.

9. In any register, use the rightmost **Actions → View** button to open that record in a centered modal — identity profile, clearance application, passenger record, suspect alert, checkpoint stop or case participant. Scroll a long register: the column headers stay frozen and the page itself does not scroll.

Uploaded files are stored in `backend/uploads/` (git-ignored) and served from `/uploads/`.

## Important implementation note — development only, not for operational police data

This is now a **connected development system**: the browser UI talks to a central
backend API, and server data is stored in SQLite instead of only browser local
storage. **It is still not ready for real police data.** It currently uses:

- **SQLite** instead of a production database (PostgreSQL)
- **Development authentication** — a single hard-coded demo login (`admin` / `ChangeMe123!`), in-memory session tokens, and unsalted SHA-256 password hashing
- **No HTTPS** — traffic is plain HTTP
- **No full role or branch-based permissions** — every authenticated user can do everything
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
