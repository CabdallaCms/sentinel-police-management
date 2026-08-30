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
- `GET /api/health` (authenticated)
- `GET /api/me` (authenticated)
- `GET /api/persons?q=...` (authenticated)
- `POST /api/persons` (authenticated)
- `GET /api/airport-records` (authenticated)
- `POST /api/airport-records` (authenticated)
- `GET /api/clearance-applications` (authenticated)
- `POST /api/clearance-applications` (authenticated)
- `POST /api/clearance-applications/{id}/approve` (authenticated)

The API enforces the central-person rule: Airport and Fingerprint records must reference an existing central `person_id`, and National ID is unique.

This is a development foundation, not an operational police deployment. Authentication, database, encryption, roles and audit controls need a production hardening pass before use with real data.
