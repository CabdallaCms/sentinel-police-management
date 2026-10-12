# Testing the form, clearance and identity-profile improvements

Branch: `arena/c1f51a82-sentinel-police-management`. Do not merge until UAT is approved.
Restart the backend and hard-refresh the browser when testing this branch.
Use a test database and synthetic identities/documents only.

## Focused automated regressions

```sh
python3 -m venv .venv
.venv/bin/pip install psycopg2-binary pgserver
npm install --no-save --package-lock=false jsdom@26

node backend/test_form_improvements.mjs
.venv/bin/python backend/test_linked_records.py
.venv/bin/python backend/test_review_gate.py
PYTHON="$PWD/.venv/bin/python" node backend/test_approval_flow.mjs
.venv/bin/python backend/test_dynamic_branches.py
.venv/bin/python backend/test_read_only_rbac.py
.venv/bin/python backend/test_print_fit.py
```

The linked-record suite **always** provisions isolated PostgreSQL. Review-gate,
approval-flow and other PostgreSQL-aware suites use configured `SENTINEL_DB_*`
settings if present, otherwise a throwaway `pgserver` instance. Never point those
suites at operational data. `test_form_improvements.mjs` uses jsdom with mocked
network writes; approval-flow tests execute all three actual page scripts
against the real API. The older `test_server.py` still assumes retired SQLite
storage and is not part of this PostgreSQL test set.

## Officer UAT checklist

1. **Error styling and first-error focus**
   - Try Persons, Fingerprint, Airport, Checkpoint, CID participants/cases,
     Stations, Officers, Crime intake, Vehicles, HR and Branch Management.
   - Leave one required field blank among completed fields, and leave optional
     fields blank. Save: only failed fields should be red; the first invalid
     field should be focused and scrolled into view inside the form/modal.
   - Correct it without saving again: the red indicator should clear.
   - Leave National ID and Passport empty, then fill either one: both error
     indicators should clear. Optional IDs in checkpoint intake must stay neutral.
   - Fail an officer requirement on a later wizard step. Save must reveal that
     step, focus the field and scroll it into view.
   - Leave attachment minimums unmet. The group is highlighted, not every
     optional file. Meet the minimum using any slots and confirm it clears.
   - Try an invalid optional email, document extension/size and incomplete
     conditional vehicle-owner or demotion fields.
2. **Successful-save lifecycle**
   - Save valid entries: the entry modal should close and the register remain.
   - Case-workspace saves return to CID; use View to reopen the saved case.
   - Saving a branch hides its form; **Add another branch** opens it again.
   - Disconnect/reject a write: the form must remain open with entered data.
3. **Citizenship**
   - As `fp.officer`, create a Citizenship application with required documents.
   - Approve immediately from either the register or the application review page,
     then open Certificate and print. No waiting-period lock should appear.
   - Repeat with Education, Travel, Employment and Licence: each must retain its
     12-hour lock. Administrator bypass and read-only command restrictions remain.
4. **Linked Unit Records**
   - Link the same synthetic person in several units/branches, then click View.
   - At the bottom, check branch name/region, source table/reference, uploader and
     recorded location/time. Compare them to the original register entries.
   - An officer only sees provenance in their permitted unit/checkpoint scope;
     admins/commanders can see their broader permitted set.
   - Unassigned legacy data, no linked records, offline/error state and rapid
     switching between profiles should not show invented or stale details.
   - Nearby/current proximity is **Not determined**: residence and dated record
     locations are not live coordinates. Uploader account branch is explicitly
     current metadata, not a historical snapshot.
