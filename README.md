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

## Run locally

Python is enough:

```bash
python3 -m http.server 8000 --bind 0.0.0.0
```

Open `http://localhost:8000`.

The live preview is already running in this workspace.

## Demo workflow

1. Open **Airport** and search `10012345` or `Ayaan Cabdi Xasan`.
2. The application identifies existing central person `P-0001`, originally registered at the airport in July 2026.
3. Open **Fingerprint Unit** and search the same ID.
4. Enter purpose, guardian and legal document details.
5. Save the application. A Fingerprint record is added, while Airport data stays in the Airport register.
6. Use **Approve** in the Fingerprint register to move the application to Approved and generate a certificate reference.
7. Use **CID Criminal Unit** to add a suspect alert and test the Checkpoint screening workflow.

## Important implementation note

This deliverable is a functional front-end demonstration. Data is stored in browser local storage, which is appropriate for demonstrating workflows but is not appropriate for live police operations or multiple computers.

Before operational deployment, replace local storage with a secure server-side database and add:

- Individual authenticated accounts and role/branch permissions
- Server-side validation and duplicate matching
- Encryption in transit and at rest
- Immutable audit logs
- Evidence file storage and chain of custody
- Certificate QR verification
- Backup and disaster recovery
- Network/offline synchronization policy
- Legal rules for suspect alerts, clearance decisions and data retention
- Supervisor confirmation for possible suspect matches

The current data model is intentionally compatible with a relational implementation using tables such as `persons`, `unit_records`, `airport_passengers`, `clearance_applications`, `crime_cases`, `case_participants`, `suspect_alerts`, `checkpoint_events`, `locations`, `users`, and `audit_events`.
