# Sentinel backend foundation

This is the first server-side foundation for the Sentinel system. It uses only Python's standard library and SQLite so it can run immediately without installing packages.

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

## Demo account

- Username: `admin`
- Password: `ChangeMe123!`

Change or remove this demo account before any real deployment.

## Current endpoints

- `POST /api/login`
- `GET /api/health`
- `GET /api/me` (authenticated)
- `GET /api/persons?q=...` (authenticated — searches name, National ID, passport, phone, mother's name)
- `POST /api/persons` (authenticated — strict create, 409 if National ID exists)
- `POST /api/persons/upsert` (authenticated — find by National ID/passport and merge new fields, else create)
- `PATCH /api/persons/{person_id}` (authenticated — append/update profile details)
- `GET /api/persons/{person_id}` (authenticated — profile plus linked airport/clearance/CID records)
- `GET /api/airport-records` / `POST /api/airport-records` (authenticated)
- `GET /api/clearance-applications` (authenticated)
- `POST /api/clearance-applications` (authenticated, `multipart/form-data` — applicant & guardian fields, 4 applicant docs and 3 guardian docs with **at least 2 of each required**, optional photo; creates/updates the central person)
- `GET /api/clearance-applications/{application_id}` (authenticated — full detail for the printable pages)
- `POST /api/clearance-applications/{id}/approve` (authenticated — issues the certificate number and unlocks the certificate)
- `GET /api/crime-cases` / `POST /api/crime-cases` (authenticated)
- `GET /api/crime-cases/{case_id}` (authenticated — incident summary, participants and evidence)
- `PATCH /api/crime-cases/{case_id}` (authenticated — update status, category, location, summary, notes)
- `POST /api/crime-cases/{case_id}/evidence` (authenticated, `multipart/form-data` — evidence file + caption/type)
- `GET /api/suspect-alerts` / `POST /api/suspect-alerts` (authenticated — participants carry a role: Suspect/Victim/Witness/Complainant)
- `GET /api/checkpoint-events` / `POST /api/checkpoint-events` (authenticated — legacy minimal checkpoint stop linked to a central person; screening result is computed server-side against active suspect alerts)
- `GET /api/checkpoint-stops` (authenticated — list traveler screening stops)
- `GET /api/checkpoint-stops/{stop_id}` (authenticated — full stop detail incl. traveler, guardian and documents)
- `POST /api/checkpoint-stops` (authenticated, `multipart/form-data` — the full traveler screening form: traveler name/mother/DOB/POB, current & permanent address, purpose of visit, optional passport & National ID, optional real-time photo, 2 traveler document slots with **at least 1 required**, guardian name/relationship/contact/address/occupation, optional guardian NID & passport, 2 guardian document slots with **at least 1 required**; creates/updates the central person and screens against the active suspect list)
- `GET /api/guardian-search?q=...` (authenticated — searches saved guardians across checkpoint stops, clearance applications and the central registry for duplicate-check auto-fill)
- `GET /api/alert-notifications` (authenticated — list instant alerts raised by suspect matches)
- `POST /api/alert-notifications/{id}/acknowledge` (authenticated — mark an alert notification acknowledged)

Uploaded files are stored under `backend/uploads/` (configurable with `SENTINEL_UPLOADS`) and served from `/uploads/...`. The printable pages are `application.html` (Day-1 review + approve) and `certificate.html` (Day-2 certificate, locked until approval).

The API enforces the central-person rule: Airport, Fingerprint, CID and Checkpoint records must reference an existing central `person_id`, and National ID is unique. Person records are merged (never duplicated) when a matching National ID or passport is found; only newly provided fields are updated. Suspect alerts must reference an existing CID case, and only one active alert can link a person to a case.

Checkpoint stops are screened server-side: a traveler with an active `Suspect` alert yields `Flagged match` / `Supervisor contacted` **and an alert notification is written immediately**; otherwise the result is `No active alert` / `Cleared`. Travelers may arrive with no National ID or passport — the checkpoint flow still records them in the central registry (matched by name, mother's name and date of birth) with a nullable National ID.

This is a development foundation, not an operational police deployment. Authentication, database, encryption, roles, file-upload validation and audit controls need a production hardening pass before use with real data.
