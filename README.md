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

### Global search, auto-fill and merging

Every unit form has a **global search autocomplete**: typing a name, National ID, passport or phone queries the Central Person Registry. Selecting a match **auto-fills** the person's saved details (name, mother's name, DOB/POB, residence, occupation, passport, phone, photo) and links the new unit record to the existing identity — no duplicate is created. Submitting new or corrected details **appends/updates** the central profile (server-side merge by National ID/passport). When no match exists, the "create/update person" entry opens a side-panel form.

### No popups — pages and side panels

The interface uses **no browser dialogs**. All create/edit actions happen in **dedicated full-page workspaces** (e.g. the CID case workspace) or **slide-in side panels** (new person, new case, checkpoint stop).

### Fingerprint application, review and certificate

- The expanded clearance application captures applicant data (full name, mother's name, DOB/POB, residence, occupation, passport, National ID, photo, clearance reason) plus **4 applicant file slots (≥2 required)** and guardian data (name, relationship, ID, occupation, address, contact) with **3 guardian file slots (≥2 required)**.
- **`application.html`** — a printable Day-1 review summary the applicant verifies, with an **Approve Application** action for authorized officers.
- **`certificate.html`** — the official Day-2 clearance certificate. It is **locked until an officer approves** the application, then unlocks for printing.

### CID case workspace

Each case opens in a full-page workspace with three tabs: **1) Case Details & Incident Summary**, **2) Participants & Suspect List Linkage** (suspect/victim/witness/complainant, with suspects creating checkpoint/airport alerts), and **3) Evidence & Media Storage** (file uploads with captions).

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

## Demo workflow

1. Open **Airport** and type `Ayaan` (or `10012345`) in the search box — the global autocomplete finds central person `P-0001`; select it to auto-fill.
2. Open **Fingerprint Unit** and search the same person. Select the match to auto-fill the applicant fields.
3. Complete clearance reason, guardian details, and attach **at least 2 applicant and 2 guardian documents** (plus an optional photo), then save.
4. In the Fingerprint register click **Review/Print** to open `application.html` — print the Day-1 summary and use **Approve Application**.
5. After approval, click **Certificate** to open `certificate.html` — the Day-2 clearance certificate is now unlocked and printable.
6. Open **CID Criminal Unit**, click a case to open its workspace: edit the incident summary (tab 1), link participants (tab 2 — choosing *Suspect* raises a checkpoint/airport alert), and upload evidence (tab 3).
7. Open **Checkpoints → Record stop**, search the suspect, and see the automatic "Flagged match" screening. The stop is saved to the central database and the screening result is computed server-side against active suspect alerts.

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
