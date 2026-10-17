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

Similarly, the **Fingerprint Unit**, **Airport Control** and **CID Criminal Unit** accounts
intentionally have no *Central Police Search* in the sidebar (they keep *Central Person Search* and
their own unit scope).
The entry is **removed from the sidebar DOM** for those roles — not merely hidden — and the page is
unreachable through `go()`, so it cannot be revealed by a cached stylesheet or a stray render.

If the entry still appears for a unit account, check the **role string stored for that user**
(`SELECT username, role FROM users;`). Every spelling is now resolved — including label-style values
such as `Airport Control Officer`, `Airport Control Unit`, `CID Criminal Unit`, `Criminal Unit` or
`Crime Unit` — but a running server started before this build must be restarted to pick the rule up:
it prints `RBAC self-test: PASS — module denylist in force for FingerprintUnit, AirportControl,
CIDUnit` when it is serving the fixed code and refuses to start at all if the denylist is not in
force.

Still seeing the old menu, or a Register without the Actions/View/Edit controls, after updating?
Check which page the browser actually has before blaming the server:

1. The sidebar footer shows *UI build …* (`window.SENTINEL_UI_BUILD`). It must end with the short
   commit of the deployment (`sentinel-rbac-readonly-4-0f8552e` for the station View/Edit build) —
   anything else is a page that was rendered before the update.
2. `GET /api/health` answers `ui_build` (read from the `index.html` on disk) and `asset_version`
   (`0f8552e`); if those differ from the footer, the tab is cached, not the server.
3. Reload. Pages are served with `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`,
   `Expires: 0` and `Pragma: no-cache`, and every static reference carries `?v=<asset_version>`
   (`certificate.html?v=0f8552e&id=…`, `images/police_logo.png?v=0f8552e`), so an ordinary reload or
   hard refresh (Ctrl+Shift+R) always lands on the current build. A proxy that ignores the headers
   can still be flushed by opening the page with a changed parameter (`/?v=0f8552e`).

The backend itself logs its RBAC guarantees at start-up and answers 403 for every command-role
write, so a stale *server* is never the explanation for an old *page*: the stamp tells you which of
the two you are looking at.

## Stale UI: a *fresh* browser still shows an old build

A brand-new browser (or a private window, or `curl`) cannot be served from a browser cache, so if it
still shows the previous page the **server** is serving the previous `index.html`. Confirm it and fix
it in one step:

```sh
bash scripts/verify-live-ui.sh https://<your-preview-host>
```

It prints the checkout's stamp/sha256 next to the live server's `ui_build`/`ui_sha256`/`ui_path` and
fails loudly when they differ, e.g.:

```
  FAIL stamp mismatch: live=sentinel-rbac-readonly-3 checkout=sentinel-rbac-readonly-4-0f8552e
       => the running process serves a DIFFERENT index.html (an older deployment).
```

### Local development: `python backend/server.py` on `localhost:8001`

The page is read from **the directory you start the server in**, in this order:

| priority | source | when |
|---|---|---|
| 1 | `SENTINEL_UI_DIR` | packaged deployments / explicit override |
| 2 | **current working directory** | `cd sentinel-police-management && python backend/server.py` |
| 3 | the repository root containing `backend/server.py` | started from elsewhere, e.g. `cd backend && python backend/server.py` |

The file is opened on **every request**, so editing `index.html` is live on the next
reload — there is no template cache to flush and no restart needed. Ask before starting:

```sh
python backend/server.py --ui-check
```

```
build    : sentinel-rbac-readonly-4-0f8552e
candidates:
  OK /home/you/sentinel-police-management/index.html  [sentinel-rbac-readonly-4-0f8552e]  (current working directory)

OK — GET / would serve:
serving  : /home/you/sentinel-police-management/index.html
via      : current working directory   (cwd /home/you/sentinel-police-management)
stamp    : 'sentinel-rbac-readonly-4-0f8552e'   expected 'sentinel-rbac-readonly-4-0f8552e'
checkout : branch arena/70d3d88b-sentinel-police-management @ 1a5be49
  Actions column: yes
```

`--ui-check` needs no database and exits `1` when the server would refuse to start.

**If you are on `main`:** `main` has not received the station View/Edit work — it is on the branch
`arena/70d3d88b-sentinel-police-management` (pull request open). A checkout of `main` is exactly
`sentinel-rbac-readonly-3` with no Actions column, and the fixed server now says so:

```
checkout : branch main @ 1b05c2c
           this checkout predates the station View/Edit feature — switch to the feature branch or merge it first
```

```sh
git fetch origin
git checkout arena/70d3d88b-sentinel-police-management   # or merge the PR into main
python backend/server.py --ui-check                        # exit 0
python backend/server.py
```

The same identity is in `GET /api/health`:

| field | meaning |
|---|---|
| `ui_build` | the `<meta name="sentinel-ui-build">` stamp of the file the server serves |
| `ui_sha256` | sha256 of that file — compare with `sha256sum index.html` in the checkout |
| `ui_path` | absolute path of the served template |
| `ui_source` | how it was resolved: `SENTINEL_UI_DIR`, `current working directory` or `repository root` |
| `ui_cwd` | the process working directory |
| `ui_git` | `{branch, commit}` of the checkout the template came from |
| `ui_actions_published` | whether the served page contains the Registered Stations Actions column |
| `ui_ok` / `ui_problems` | the startup self-test, re-run on every health call |

**A running server never serves a stale page either.** The template is re-checked on every
`GET /` (cached on size + mtime); if the checkout changes underneath a running process — the exact
way a *fresh* browser ended up on the previous release — the response is `503` with
`X-Sentinel-UI-Stale: 1` and the same diagnosis, instead of the out-of-date page. Restoring the
current file makes the server serve `200` again with no restart.

**The server refuses to start on a stale page.** If the `index.html` it would serve is not the
current one (old stamp, or missing the Actions column / View / Edit markers) it exits before binding
the port:

```
FATAL: the index.html this server would serve is not the current page; refusing to start.
       template : /srv/sentinel/index.html
       stamp    : 'sentinel-rbac-readonly-3' (expected 'sentinel-rbac-readonly-4-0f8552e')
       - the page stamps itself 'sentinel-rbac-readonly-3' but this build is ...
       - the page is missing the served build's features: Actions column, ...
```

Fixes, in order of likelihood:

1. **The process was started from an older checkout/package.** Restart it from the repository that
   contains the current `index.html`: `bash scripts/restart-8001.sh` (now also requires
   `ui_actions_published: true`) or `bash scripts/uat-stack.sh` for a throwaway UAT stack.
2. **The deployment serves a packaged copy.** Point the process at the refreshed templates with
   `SENTINEL_UI_DIR=/path/to/current/templates`; the startup guard verifies whatever directory wins.
3. **The preview is attached to a different machine/process.** `ui_path` and `pid` in `/api/health`
   name the process answering; if it is not the one you just started, that preview URL belongs to an
   older instance. Use the URL the current session's preview reports.

## 6. Still stuck?

- Hard-reload the browser (`Ctrl+Shift+R`) — HTML may be cached.
- Delete `backend/sentinel.db*` and restart: a database written by an older
  build can mask the fix.
- Check for a second copy of the repo: `python backend/server.py` must be
  run from **this** working tree.
- `ss -ltnp | grep 8001` (Linux) / `netstat -ano | findstr 8001` (Windows)
  shows who owns the port.
