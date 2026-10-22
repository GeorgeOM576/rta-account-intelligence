# How to Use RTA page

The sidebar now lists **Dashboard → How to Use RTA → Upload Data**, followed by the unchanged existing pages. It reuses the existing radio navigation, Red Thread logo, header and theme.

## UI

- Title: How to Use RTA.
- Subtitle: From raw account data to verified results in six simple steps.
- Short welcome plus six numbered cards in native Streamlit columns/containers: upload, configure, optional translation, reconciliation, optional AI research, review/export.
- Scoped navy/red/light-grey styling, rounded cards, small text icons and spacing; native columns handle narrow layouts. No external images, animations or new dependencies.
- Understanding the results explains existing match/review statuses and Proposed/Final Value. All is correctly described as a filter rather than a review status. Approved covers explicit approval of a field value, including retaining an original value.
- Helpful tips emphasize consistent identifiers, approved translations before rematching, careful review, optional paid research and export after review.
- Wording checked against CSV/XLSX import (active Excel worksheet), identifier/comparison mapping, matching statuses, displayed review labels and Final Value review logic. Workflow and result definitions total roughly 320 words, plus brief welcome/tips.

## Zero database/provider access

Sidebar navigation is rendered before the existing workspace initialization. The guide routes to the static `rta/help_ui.py` renderer and stops before Store construction, workspace creation, SQLite loading, credential lookup or provider initialization. It does not show workspace resume/create controls that would require database work. Existing pages continue through their existing initialization and handlers.

The static renderer imports only Streamlit and HTML escaping. It does not import storage, providers, authentication or business engines, and does not inspect uploaded data. Existing branding reads only its local logo asset.

No upload, matching, translation, Google authentication, research, approval, export, persistence, workspace-isolation, consent or table-schema logic was changed. No live database records or credential files were modified. No deployment, push or commit was performed.

## Validation

Four new Streamlit regressions verify:

1. Exact sidebar placement, guide rendering without datasets, and navigation to every existing page.
2. Initial guide load without a project: database construction, SQLite connections, Google client/auth construction and provider HTTP are patched to fail if called. Initial rendering and reruns make zero calls and create no database.
3. Existing workspace payload, audit history, selected stable IDs and pending session input survive guide visits/reruns and return navigation without database access from the guide.
4. Real review-filter labels, actual match-status terminology and compact reading length.

- Focused guide plus existing offline application workflow: **5 passed**.
- Complete regression suite: **615 passed in 209.60 seconds**, including actual application import/startup and real local Streamlit HTTP health checks.
- After a final copy-only clarification of Approved, all **4 guide tests passed again** in 4.01 seconds. No behavior changes followed the full regression run.
- No live paid API calls.

## Files changed

- `app.py` — navigation placement and static guide routing before database initialization.
- `rta/help_ui.py` — new presentation-only guide.
- `tests/test_help_page.py` — new guide/navigation/no-I/O regressions.
- `README.md` — guide discoverability.
- `docs/how-to-use-rta-page.md` — this implementation/validation note.

Pre-edit `app.py` is preserved at `/private/tmp/rta-how-to-checkpoint/app.py`. No GitHub push or deployment will occur without separate user authorization.
