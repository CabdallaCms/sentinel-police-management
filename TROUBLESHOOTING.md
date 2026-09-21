# "The fix didn't take effect" — stale server on port 8001

Almost every report of "application X was approved instantly" or
"`/api/health` has no `build` field" has the same cause: **the process
answering on port 8001 is an old one.** The new server crashed at start-up
with `Address already in use`, nobody read the message, and the previous
process kept serving.

## 1. One command: restart and prove it

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart-8001.ps1
```

Linux / macOS:

```bash
bash scripts/restart-8001.sh
```

Both scripts:

1. force-kill every process listening on the port,
2. start `backend/server.py`,
3. poll `/api/health` until it reports
   `"build": "sentinel-fingerprint-review-lock-12h"` **and**
   `"review_lock_active": true`, and **exit 1** if it never does,
4. run the approval audit to find anything approved too early while the
   stale server was up.

Manual equivalent (PowerShell), if you prefer:

```powershell
Get-NetTCPConnection -LocalPort 8001 |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
python backend\server.py
```

## 2. Confirm the running build

```bash
curl -s http://127.0.0.1:8001/api/health
```

```json
{
  "status": "ok",
  "build": "sentinel-fingerprint-review-lock-12h",
  "review_lock_active": true,
  "fingerprint_review_window_hours": 12,
  "pid": 8610,
  "started_at": "2026-09-03T09:30:38Z"
}
```

| Field | Meaning |
|---|---|
| `build` | must be `sentinel-fingerprint-review-lock-12h` |
| `review_lock_active` | the boot self-test re-run live — `false` means this process is not enforcing the lock |
| `pid` / `started_at` | identifies the process; if `started_at` predates your restart, it is the old process |

A response **without** `build` is a server started before this build. Kill it
and start again — `python3 backend/server.py` now evicts the previous
listener automatically instead of dying with `Address already in use`
(set `SENTINEL_NO_PORT_TAKEOVER=1` to opt out).

## 3. Undo approvals the stale server issued

```bash
python3 backend/audit_instant_approvals.py            # report
python3 backend/audit_instant_approvals.py --revert   # put them back
```

It lists every `Approved` application whose `reviewed_at - created_at` is
under 12 hours (and every one whose timestamps cannot prove the window
elapsed), names the role that approved it from `audit_events`, and — with
`--revert` — sets it back to `Pending Review`, voids the certificate number
and writes a `REVERT` audit event. Administrator approvals are *not*
reported: the admin bypass is part of the policy.

## 4. The four independent locks

An approval cannot be issued unless **all** of these agree:

1. **Boot self-test** — `review_lock_self_test()` runs 8 cases at start-up
   (`review lock self-test: PASS (8/8 cases)`). If it fails, the server
   **refuses to start**: `FATAL: fingerprint review lock failed its
   self-test; refusing to start an unlocked server.`
2. **Server gate** — `review_gate_decision()` runs before any write on both
   approval routes. Fail-closed: a missing or unparseable `created_at`
   stays locked.
3. **Inline guard** — the approval handler re-checks
   `now - created_at >= 43200s` immediately before the `UPDATE`, so even a
   sabotaged `review_gate_decision()` cannot unlock it.
4. **Client guard** — `index.html` calls `/api/health` on load; if the build
   tag is missing or `review_lock_active` is false it shows a red
   **STALE BACKEND** banner, renders every row as
   `🔒 Stale backend — locked`, and `approveFP()` refuses to issue the
   request.

## 5. Expected behaviour: what the read-only command role cannot do

`chief_commander` (the *Commander / High Command* account, e.g. the seeded `chief` user) is a
**global read-only monitoring role**. Seeing no *Register Officer*, *Add*, *Edit*, *Approve
Clearance* or *Open Case* button anywhere in the app is correct — the whole UI is in view-only mode
and a **View-only** badge sits in the top bar. Likewise, a `403 Forbidden` with

```json
{"error": "…", "code": "read_only_role", "read_only": true, "path": "/api/persons"}
```

from `POST`, `PATCH` or `DELETE` is the firewall working as designed, not an authentication bug: the
command token is valid, the write is simply not permitted. Sign in as `admin` (or the unit officer
who owns the record) to make the change. Read-only mode never blocks `GET` requests, so dashboards,
registers, logs and searches keep working.

Similarly, the **Airport Control** and **CID Criminal Unit** accounts intentionally have no
*Central Police Search* in the sidebar (they keep *Central Person Search* and their own unit scope).
The entry is **removed from the sidebar DOM** for those roles — not merely hidden — and the page is
unreachable through `go()`, so it cannot be revealed by a cached stylesheet or a stray render.

If the entry still appears for a unit account, check the **role string stored for that user**
(`SELECT username, role FROM users;`). Every spelling is now resolved — including label-style values
such as `Airport Control Officer`, `Airport Control Unit`, `CID Criminal Unit`, `Criminal Unit` or
`Crime Unit` — but a running server started before this build must be restarted to pick the rule up:
it prints `RBAC self-test: PASS — module denylist in force for AirportControl, CIDUnit` when it is
serving the fixed code and refuses to start at all if the denylist is not in force.

Still seeing the old menu or an action button after updating? That is a stale page, not a stale
server (the backend prints its RBAC guarantees at start-up and answers 403 for every command-role
write). Reload with a hard refresh — the sidebar footer shows *UI build sentinel-rbac-readonly-3*
when you are on the current frontend; anything else is a cached tab under
`Cache-Control: no-store`.

## 6. Still stuck?

- Hard-reload the browser (`Ctrl+Shift+R`) — HTML may be cached.
- Delete `backend/sentinel.db*` and restart: a database written by an older
  build can mask the fix.
- Check for a second copy of the repo: `python backend/server.py` must be
  run from **this** working tree.
- `ss -ltnp | grep 8001` (Linux) / `netstat -ano | findstr 8001` (Windows)
  shows who owns the port.
