# Phase 3 — Directorate & specialised services

Fingerprint clearance, CID cases and HR conduct, ported from the legacy `backend/server.py` into the unified tree.
Everything below is enforced by **PostgreSQL** (migration `004_directorate_services.sql`: triggers, row-level security,
grants); the Python in `app/directorate/` adds friendly errors on top and cannot widen what the database allows.

Decisions in force: D1 (hybrid), D2 (Chief Commander = one root assignment), D3 (`persons` is global),
T1 (clearance), T2 (HR conduct), T3 (Fingerprint / CID / HR / Transport are `directorate` units under HQ) —
see `LEGACY_AUDIT.md` §4.3–4.4.

## 1. Map

| Service | Files | Local (any unit) | National (directorate) |
|---|---|---|---|
| Fingerprint clearance | `clearance.py`, `signing.py` | **intake** — applicant, guardian, photo, documents; records `intake_unit_id` | **approve / reject, sign, print** (`clearance:approve`, `:print` at `DIR-FP`); 12 h review window |
| CID | `cid.py` | cases are owned by a unit in the CID service tree (directorate or any regional bureau under it) | alerts feed checkpoints as a yes/no flag |
| HR officers & conduct | `officers.py`, `conduct.py` | **file** a conduct record against officers of your unit or below (T2) | **review** (`conduct:review` at `DIR-HR`); rank/duty change only through an approved file |
| Structure | `structure.py` | — | `unit:manage`, `assignment:manage` |

HTTP: `app/directorate/routes.py` (docstring lists every route). UI: `web/directorate.html`, `web/directorate.js`,
public certificate check `web/verify.html`.

## 2. Regional boundary (Sool, Sanaag, East Togdheer)

* `operations.regions` (policy data) lists the state's regions. A unit is *in the state* when it sits under a listed
  region, or is a state-level unit (HQ / directorate / bureau) that claims no region.
* A **bureau claims a region** with `attrs: {"region": "SANAAG"}` — data, not code. `unit_region_name(unit)` shows it.
* Every filing function (clearance intake, case owner, alert owner, officer posting, conduct filing) resolves its unit
  with `scope='state'`; units outside the state are refused, and DB triggers keep records under an unlisted region inert
  even if someone inserts them by hand.
* `create_unit` refuses a `region` unit whose code is not in the policy. A new region is a **policy decision first**.
* Nothing in `web/directorate.*` names a bureau, region, rank or vocabulary: unit pickers come from
  `/api/directorate/units` (`filing` lists = where *this user* may file each kind of record), vocabularies from
  `/api/directorate/vocabularies` (policy tables).

## 3. Adding structure without code

```sql
-- a Fingerprint intake bureau for East Togdheer (or use POST /api/admin/units, or the Structure tab)
INSERT INTO org_units (parent_id, unit_type, code, name, attrs)
VALUES ((SELECT id FROM org_units WHERE code='DIR-FP'), 'bureau', 'BR-FP-ETOG', 'Fingerprint Intake — East Togdheer', '{"region":"ETOG"}');
INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants) VALUES (...);   -- or POST /api/admin/assignments
```
Parent/child rules (`unit_type_rules`) are checked by the database. `grant` refuses a role the granting admin does not
already fully hold at that unit (`can_grant`). Delegated unit-building is done by creating a role (data) holding
`unit:manage` — only `system_admin` holds it in the seed.

## 4. Fingerprint clearance

1. **Intake** (`POST /api/clearance-applications`): applicant resolved/created through the Phase 1 registry (ID or
   passport required — legacy rule); photo (image) and `clearance.required.applicant_docs` documents; guardian per policy
   `clearance.required.guardian` (`all` | `minors` | `none`) with relationship and documents. Reference `FP-<intake unit>-YYYY-NNNNNN`.
2. **Review window**: policy `clearance.review_window_hours` (12). Enforced by a database trigger on UPDATE; users with
   `clearance:override_review_lock` bypass it, and the bypass is audited. (Legacy "admin bypass" is this permission.)
3. **Decision** (`POST …/decision {decision, notes}`): reject needs a reason. Approve issues `CL-<DIR>-YYYY-NNNNNN`,
   builds a snapshot and **signs it with Ed25519**. Immutable once decided (trigger).
4. **Print** (`POST …/print`): returns snapshot + signature + key id, writes `clearance_prints` (append-only).
5. **Verify** (`GET /api/verify/<number>`, **no login**): recomputes the signature against the registered *public* key;
   returns validity, purpose, issue date, issuer and a masked holder (initials).

Intake scope never grants approval (T1): a bureau officer sees the applications they filed and gets `can_decide=false`.

**Keys.** The private key lives only in the environment of the Fingerprint service
(`SENTINEL_SIGNING_KEY`, `SENTINEL_SIGNING_KEY_ID`; create with `python -m app.directorate.signing generate`, register the
public half with `… register` as the database owner). With no key configured, approval fails closed (503). With
`SENTINEL_DEV_AUTH=1` a publicly known key `dev-1` is used — development only.

## 5. CID

* Case = `crime_cases` + participants (rows of `suspect_alerts` linked to the case) + `case_evidence`.
  Reference `CS-<owner>-YYYY-NNNNNN`. Participants are global registry persons; roles from `case.participant_roles`.
  Only **Suspect** raises an active alert. One row per person per case.
* Statuses from `case.statuses`; editable fields: category, location, status, summary, notes (legacy).
* Evidence files use the Phase 2 upload store (content-checked, 5 MB).
* **Direct intelligence listing**: `POST /api/suspect-alerts` (reason required); one active alert per person per case.
  Alerts are **lifted with a reason**, never deleted.
* Checkpoints keep seeing only the yes/no flag (`person_alert_flag`).

## 6. HR

* **Officer** = `officers` row linked to a global person (so the photo is visible to `person:search` holders — `hr_officer`
  therefore holds `person:create`). Required: DoB, mother's name, place of birth, phone, guarantor (name, address, contact),
  photo, document slot 1. Reference `POL-…` (service ref). Ranks, divisions, document types: policy data.
* **Rank / duty** change only via `sentinel.conduct_apply`, set by the SECURITY DEFINER conduct trigger when a file is
  approved. Rank moves must follow the policy ladder in the right direction (`conduct_rank_ok`). `Formal Dismissal` → `Terminated`
  (irreversible); `Temporary Suspension` → `Suspended`.
* **Conduct file** (`ACT-YYYY-NNNNNN`): filed by the officer's own unit chain (T2); narrative ≥ `conduct.min_narrative_chars`;
  statuses `Submitted to HR → Under HR Review → Verified & Approved | Rejected`. **The filer can never review their own
  file.** Every transition is audited; `officer_service_history` is written only by triggers.

## 7. Roles (seed) — what to expect

`fingerprint_officer`, `cid_officer`, `hr_officer`, `station_commander`, `regional_commander` as in blueprint §3.1; 004 adds
`person:create` to `hr_officer` and the upload permissions to the directorate roles. `system_admin` holds every permission
(blueprint §8-O1) — separation of duties still blocks self-review. `chief_commander` is read-only.

Demo accounts (dev seed `migrations/dev/004_demo_directorate.sql`, **fictional**): `fp.officer` (national Fingerprint),
`fp.sanaag` (Sanaag intake bureau), `cid.sool` (Sool CID bureau), `hr.officer` / `hr.reviewer` (HR), `cmd.laas`
(station commander, files conduct), `admin`, `chief`.

## 8. Tests

```bash
python -m unittest tests.test_directorate          # 24: clearance, CID, HR, structure-is-data, HTTP
JSDOM_DIR=… python -m tests.run_ui_flow            # + 6 directorate UI steps (tests/ui/dir_flow.test.mjs)
```

## 9. Limits and roadmap

| # | Item |
|---|---|
| R1 | **No rate limiting on `/api/verify`.** It reveals only validity + masked holder, but should be throttled at the proxy. |
| R2 | **Case owner transfer** (move a case between bureaus) is not implemented. |
| R3 | **Admin API is thin**: production DB grants for admin writes on `org_units` / `user_assignments` still need design; the UI only creates units and grants/revokes roles. |
| R4 | Private signing key is env-only; rotation = register a new key id, old certificates stay valid against their key. |
| R5 | Orphan uploads after a rolled-back save (as in Phase 2, R3). |
| R6 | National Register Office is not ported (decision). Officer origin-region list is free text. |
| R7 | UI verified with jsdom only. |
