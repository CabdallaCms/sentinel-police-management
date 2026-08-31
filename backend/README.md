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
- `POST /api/crime-cases/{case_id}/participants` (authenticated — add a participant to a case; **Suspect/Accused and other suspect-equivalent roles automatically create an `Active alert` in the central Suspect List**)
- `POST /api/crime-cases/{case_id}/evidence` (authenticated, `multipart/form-data` — evidence file + caption/type)
- `GET /api/suspect-alerts` (authenticated — central Suspect List; returns `source_type`, `risk_level`, `reason`, linked case details, manual entries with `case_id=null`)
- `POST /api/suspect-alerts` (authenticated — **manual suspect entry** with `person_id`, optional `source_type='manual'`, `reason`, `risk_level`, `alert_status`, `notes`; no crime case is required)
- `PATCH /api/suspect-alerts/{alert_id}` (authenticated — update role, alert status, risk level, reason/notes)
- `GET /api/checkpoint-events` / `POST /api/checkpoint-events` (authenticated — checkpoint stop linked to a central person; screening result is computed server-side against active suspect alerts and sets the action to `Supervisor contacted` or `Cleared`)

Uploaded files are stored under `backend/uploads/` (configurable with `SENTINEL_UPLOADS`) and served from `/uploads/...`. The printable pages are `application.html` (Day-1 review + approve) and `certificate.html` (Day-2 certificate, locked until approval).

The API enforces the central-person rule: Airport, Fingerprint, CID and Checkpoint records must reference an existing central `person_id`, and National ID is unique. Person records are merged (never duplicated) when a matching National ID or passport is found; only newly provided fields are updated.

The Suspect List supports two clean sources:

- **Case-linked (`source_type='case'`)** — created automatically when a person is added as a participant with a suspect-equivalent role (`Suspect`, `Accused`, etc.). The row keeps the `case_id`, `role` and `alert_status='Active alert'`, and the same record is the participant shown in the case workspace.
- **Manual (`source_type='manual'`)** — created from the Suspect List UI with `person_id`, `reason`/suspect details, `risk_level` and `alert_status`; `case_id` is `null`.

One active alert can link a person to a case, and one active manual alert exists per person. Checkpoint events are screened server-side: a person with an active suspect-equivalent alert (case-linked or manual) yields `Flagged match` / `Supervisor contacted`; otherwise `No active alert` / `Cleared`.

This is a development foundation, not an operational police deployment. Authentication, database, encryption, roles, file-upload validation and audit controls need a production hardening pass before use with real data.
