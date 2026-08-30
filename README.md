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

When a unit searches by National ID, Person ID, name or phone, the application reuses an existing central person. It does not create a duplicate. When no exact match exists, the user is prompted to create a central identity before saving the unit record.

## Architecture

The system now has two parts:

- **Frontend** — `index.html`, a single-page browser application.
- **Central backend** — `backend/server.py`, a Python (standard library only) HTTP API backed by SQLite. It serves the frontend and a JSON REST API from the same origin, and enforces the central-person rule on the server.

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

1. Open **Airport** and search `10012345` or `Ayaan Cabdi Xasan`.
2. The application identifies existing central person `P-0001`, originally registered at the airport in July 2026.
3. Open **Fingerprint Unit** and search the same ID.
4. Enter purpose, guardian and legal document details.
5. Save the application. A Fingerprint record is added, while Airport data stays in the Airport register.
6. Use **Approve** in the Fingerprint register to move the application to Approved and generate a certificate reference.
7. Use **CID Criminal Unit** to add a suspect alert and test the Checkpoint screening workflow.

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
