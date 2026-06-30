# Navigatarr Design Spec
_2026-06-30_

## Overview

Navigatarr is a self-hosted Docker service dashboard. It connects to the local Docker socket, discovers containers with publicly exposed ports, and renders a simple page of clickable links to reach those services. Preferences (visibility, sort order, custom labels) are persisted in SQLite.

---

## Architecture

A single Flask process runs inside a Docker container. Three layers:

1. **Docker layer** — Python `docker` SDK connects to `/var/run/docker.sock` (mounted as a volume) and enumerates containers with exposed host ports.
2. **Persistence layer** — SQLite file (path via `DB_PATH` env var, default `/data/navigatarr.db`) stores per-service preferences.
3. **Web layer** — Flask serves the dashboard at `GET /` via Jinja2 and exposes a small JSON API for edit-mode interactions.

### File Layout

```
navigatarr/
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── docker_client.py   # Docker SDK wrapper
│   ├── db.py              # SQLite access
│   ├── routes.py          # Flask routes + API endpoints
│   └── templates/
│       └── index.html     # Jinja2 template + inline CSS + JS
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Components

### `docker_client.py`

Wraps the Docker SDK. `list_services()` returns:

```python
[{
    "container_id": str,
    "name": str,
    "image": str,
    "status": str,   # "running" | "paused" | "exited" | etc.
    "ports": [int],  # list of host port numbers with public bindings
}]
```

Only containers with at least one publicly bound port are included. Containers with multiple exposed ports show all ports as separate links within a single card.

### `db.py`

Manages SQLite schema and all reads/writes.

**Schema:**

```sql
CREATE TABLE services (
    container_id TEXT PRIMARY KEY,
    custom_label  TEXT,
    visible       INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0
);
```

On refresh, new container IDs are upserted with defaults. Stale IDs (containers that no longer exist) are retained so preferences survive restarts and reappear if the container returns.

### `routes.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Merges live Docker data with DB preferences, sorts by `sort_order`, renders `index.html` |
| `POST` | `/api/refresh` | Re-runs `list_services()`, upserts new containers, returns updated JSON |
| `POST` | `/api/preferences` | Accepts `{services: [{container_id, custom_label, visible, sort_order}]}`, bulk-upserts, returns `{ok: true}` |

### `index.html`

Single Jinja2 template with:
- Inline `<style>` — minimal hand-written reset + utility classes (tailwind-like, no external CSS dependency)
- Inline `<script>` — SortableJS (CDN) + vanilla JS for edit mode, fetch() calls to the API

---

## Data Flow

### Normal view (page load)

1. Browser hits `GET /`
2. Flask calls `docker_client.list_services()` → live container list
3. Flask queries DB for all preferences → merges by `container_id`
4. Merged list sorted by `sort_order`, filtered to `visible=1`
5. Jinja2 renders service cards; hidden services are absent

### Edit mode (pencil icon clicked)

1. JS toggles edit mode class on `<body>`
2. Hidden services appear with reduced opacity + eye-slash toggle icon
3. Cards become draggable (SortableJS)
4. Custom label renders as an editable `<input>` (placeholder = container name)
5. Pencil icon replaced by ↺ (refresh) and ✓ (save & exit edit mode)

### Refresh (↺ clicked in edit mode)

1. JS `fetch('POST /api/refresh')`
2. Server re-queries Docker, upserts new containers, returns full updated list
3. JS re-renders cards in place (no page reload)

### Save (✓ clicked in edit mode)

1. JS collects current order, visibility, and labels from the DOM
2. `fetch('POST /api/preferences', {services: [...]})`
3. On success, JS exits edit mode

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `NAVIGATARR_HOST` | `localhost` | Hostname used in generated service links |
| `NAVIGATARR_PORT` | `7676` | Port navigatarr itself listens on |
| `DB_PATH` | `/data/navigatarr.db` | Path to the SQLite preferences file |

Service links are constructed as `http://{NAVIGATARR_HOST}:{port}`.

---

## UI/UX

### Normal View

- Top bar: "navigatarr" title (left), pencil icon ✏ (right)
- Responsive grid of service cards, each showing:
  - Custom label (or container name if unset) as the clickable link title
  - Container name + image name as subtitle
  - Colored status dot: green (running), yellow (paused), red (stopped/exited)
  - Full URL (`http://{NAVIGATARR_HOST}:{port}`) as muted text

### Edit Mode

- Subtle visual indicator on `<body>` (e.g., background tint or dashed border)
- Hidden services visible with reduced opacity + eye-slash icon to toggle visibility
- Drag handle (⠿) on left edge of each card — SortableJS activates
- Custom label field becomes an `<input>` in-place
- Pencil icon replaced by ↺ (refresh from Docker) and ✓ (save & exit)

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Docker socket unavailable at startup | Empty state: "Could not connect to Docker. Is the socket mounted?" |
| No containers with exposed ports | Empty state: "No services found. Click ✏ to refresh." |
| `POST /api/refresh` fails | Returns `{error: "..."}` 500; JS shows inline error near ↺, card state preserved |
| `POST /api/preferences` fails | Returns `{error: "..."}` 500; JS shows inline error, edit mode stays open for retry |
| Container disappears between refresh and save | DB upsert is idempotent; stale rows retained; no crash |

---

## Deployment

`docker-compose.yml` is included for easy local bring-up, pre-configured with:
- `/var/run/docker.sock` socket mount
- `./data` host directory mounted to `/data` for the SQLite file
- Port `7676` exposed

No unit tests in scope for v1.
