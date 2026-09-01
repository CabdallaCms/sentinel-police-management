# Browser-level smoke tests (optional)

These run the real `index.html` in a [jsdom](https://github.com/jsdom/jsdom) DOM, execute its
scripts, click the real buttons and submit the real forms. They are **optional** — the
dependency-free gate for this repo is `python3 test_ui.py` at the project root.

```bash
cd tests/browser
npm install          # installs jsdom only (git-ignored)
npm run test:local   # local demo mode (no backend): 141 checks
npm run test:server  # full stack: starts backend/server.py on a temp SQLite DB, 67 checks
```

`smoke.server.cjs` spawns `backend/server.py` itself against a throwaway database and temp
upload directory, then bridges the browser's `fetch` (including `multipart/form-data` file
uploads) to that server, so nothing in your working tree is touched.

## What they verify

- No drawer survives; the dialog is a centered modal over a `backdrop-filter: blur(4px)`
  backdrop, with a fixed header, an internally scrolling body and a sticky footer.
- **Computed** styles (not just the stylesheet text) cascade onto the real elements:
  overlay centering, `max-height: 80vh` + `overflow-y: auto` on the body, `position: sticky`
  on the header/footer, `position: sticky; top: 0` on every `<thead>`, and the fixed
  `calc(100vh - 280px)` height on every table container.
- Every register table renders rows whose cell count matches its header count, and every
  table's rightmost column is an `Actions` column with a working **View** button.
- Clicking each **View** button opens the record's detail modal with the right title, body
  and footer buttons.
- The status pill palette: red `Active alert` / `Flagged match`, green `Cleared`,
  blue `Manual Entry`, purple linked `CID-…` case references.
- End-to-end submissions through the modals in both modes: new crime case, suspect with and
  without a linked case, and a checkpoint stop with traveler/guardian document and photo
  uploads — asserting what the server stored and how the table re-rendered.
- `Esc` and backdrop clicks close the modal, background scroll is locked, and no unexpected
  runtime error occurs anywhere in the run.
