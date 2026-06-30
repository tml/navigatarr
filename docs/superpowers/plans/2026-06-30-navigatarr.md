# Navigatarr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted Flask dashboard that reads Docker container port bindings from the local socket and renders a clickable service link page with persistent layout preferences.

**Architecture:** A Flask app factory runs inside Docker (socket mounted at `/var/run/docker.sock`). The Python `docker` SDK enumerates containers; SQLite (mounted at `/data/navigatarr.db`) stores visibility, sort order, and custom labels per container. A Jinja2 template serves the dashboard; vanilla JS + SortableJS drive edit mode via two JSON API endpoints.

**Tech Stack:** Python 3.12, Flask 3.1, docker SDK 7.1, SQLite (stdlib), SortableJS 1.15 (CDN), Docker + docker-compose v2

## Global Constraints

- No unit tests in scope for v1 — verification is manual (curl / browser)
- Service links use template `http://{NAVIGATARR_HOST}:{port}` where `NAVIGATARR_HOST` defaults to `localhost`
- Default app port: `7676` (env var `NAVIGATARR_PORT`)
- SQLite file default path: `/data/navigatarr.db` (env var `DB_PATH`)
- Multi-port containers show all ports as links within a single card — one card per container, never one card per port
- No external CSS framework — minimal hand-written reset + utility classes only
- SortableJS loaded from CDN (`https://cdn.jsdelivr.net/npm/sortablejs@1.15.3/Sortable.min.js`)

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | Pin dependencies |
| `Dockerfile` | Build image, expose 7676 |
| `docker-compose.yml` | Socket mount, data volume, env defaults |
| `run.py` | Entry point — calls `create_app().run()` |
| `app/__init__.py` | Flask app factory — config, DB init, blueprint registration |
| `app/docker_client.py` | Docker SDK wrapper — `list_services()` |
| `app/db.py` | SQLite — `init_db`, `get_preferences`, `upsert_services`, `save_preferences` |
| `app/routes.py` | `GET /`, `POST /api/refresh`, `POST /api/preferences` |
| `app/templates/index.html` | Full Jinja2 template: CSS reset, normal view, edit mode JS |

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `run.py`
- Create: `app/__init__.py`

**Interfaces:**
- Produces: `create_app()` in `app/__init__.py` — returns a configured `Flask` instance with `app.config['DB_PATH']` (str) and `app.config['NAVIGATARR_HOST']` (str)

- [ ] **Step 1: Create `requirements.txt`**

```
flask==3.1.0
docker==7.1.0
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY run.py .
EXPOSE 7676
CMD ["python", "run.py"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  navigatarr:
    build: .
    ports:
      - "7676:7676"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/data
    environment:
      NAVIGATARR_HOST: localhost
      DB_PATH: /data/navigatarr.db
```

- [ ] **Step 4: Create `run.py`**

```python
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('NAVIGATARR_PORT', 7676))
    app.run(host='0.0.0.0', port=port)
```

- [ ] **Step 5: Create `app/__init__.py`**

```python
import os
from flask import Flask

def create_app():
    app = Flask(__name__)
    app.config['DB_PATH'] = os.environ.get('DB_PATH', '/data/navigatarr.db')
    app.config['NAVIGATARR_HOST'] = os.environ.get('NAVIGATARR_HOST', 'localhost')
    return app
```

- [ ] **Step 6: Create `data/` directory for local dev (gitignored)**

```bash
mkdir -p data
echo 'data/' >> .gitignore
echo '__pycache__/' >> .gitignore
echo '*.pyc' >> .gitignore
```

- [ ] **Step 7: Verify docker build succeeds**

```bash
docker build -t navigatarr .
```

Expected: `Successfully built` (or equivalent BuildKit output with no errors)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt Dockerfile docker-compose.yml run.py app/__init__.py .gitignore
git commit -m "feat: project scaffold"
```

---

### Task 2: Docker client

**Files:**
- Create: `app/docker_client.py`

**Interfaces:**
- Consumes: nothing from prior tasks
- Produces: `list_services() -> tuple[list[dict], str | None]`
  - On success: `([{ container_id: str, name: str, image: str, status: str, ports: list[int] }], None)`
  - On error: `([], error_message: str)`
  - `container_id` is the first 12 characters of the full container ID
  - `ports` is a sorted list of unique host port integers with public bindings; only containers where `ports` is non-empty are included
  - `image` is the first tag if tags exist, else `container.image.short_id`

- [ ] **Step 1: Create `app/docker_client.py`**

```python
import docker


def _get_host_ports(container):
    ports = set()
    if container.ports:
        for bindings in container.ports.values():
            if bindings:
                for b in bindings:
                    if b.get('HostPort'):
                        ports.add(int(b['HostPort']))
    if not ports:
        port_bindings = (container.attrs.get('HostConfig') or {}).get('PortBindings') or {}
        for bindings in port_bindings.values():
            if bindings:
                for b in bindings:
                    if b and b.get('HostPort'):
                        ports.add(int(b['HostPort']))
    return sorted(ports)


def list_services():
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        services = []
        for container in containers:
            ports = _get_host_ports(container)
            if not ports:
                continue
            tags = container.image.tags
            image = tags[0] if tags else container.image.short_id
            services.append({
                'container_id': container.id[:12],
                'name': container.name,
                'image': image,
                'status': container.status,
                'ports': ports,
            })
        return services, None
    except Exception as e:
        return [], str(e)
```

- [ ] **Step 2: Verify import inside a running container**

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/app:/app/app \
  navigatarr \
  python -c "from app.docker_client import list_services; svcs, err = list_services(); print(err or svcs)"
```

Expected: a list of dicts (or `[]` if no exposed-port containers are running), no Python traceback.

- [ ] **Step 3: Commit**

```bash
git add app/docker_client.py
git commit -m "feat: docker client"
```

---

### Task 3: Database layer

**Files:**
- Create: `app/db.py`
- Modify: `app/__init__.py` — call `init_db` on startup

**Interfaces:**
- Consumes: `app.config['DB_PATH']` (str) from Task 1
- Produces:
  - `init_db(db_path: str) -> None`
  - `get_preferences(db_path: str) -> dict[str, dict]` — keyed by `container_id`; each value has keys `container_id`, `custom_label`, `visible` (int), `sort_order` (int)
  - `upsert_services(db_path: str, container_ids: list[str]) -> None` — inserts rows for new IDs, ignores existing
  - `save_preferences(db_path: str, services: list[dict]) -> None` — each dict has keys `container_id`, `custom_label`, `visible`, `sort_order`

- [ ] **Step 1: Create `app/db.py`**

```python
import sqlite3


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    with _connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS services (
                container_id TEXT PRIMARY KEY,
                custom_label  TEXT,
                visible       INTEGER NOT NULL DEFAULT 1,
                sort_order    INTEGER NOT NULL DEFAULT 0
            )
        ''')


def get_preferences(db_path):
    with _connect(db_path) as conn:
        rows = conn.execute('SELECT * FROM services').fetchall()
    return {row['container_id']: dict(row) for row in rows}


def upsert_services(db_path, container_ids):
    with _connect(db_path) as conn:
        for cid in container_ids:
            conn.execute(
                'INSERT INTO services (container_id) VALUES (?) ON CONFLICT(container_id) DO NOTHING',
                (cid,)
            )


def save_preferences(db_path, services):
    with _connect(db_path) as conn:
        for svc in services:
            conn.execute('''
                INSERT INTO services (container_id, custom_label, visible, sort_order)
                VALUES (:container_id, :custom_label, :visible, :sort_order)
                ON CONFLICT(container_id) DO UPDATE SET
                    custom_label = excluded.custom_label,
                    visible      = excluded.visible,
                    sort_order   = excluded.sort_order
            ''', svc)
```

- [ ] **Step 2: Update `app/__init__.py` to call `init_db` on startup**

Replace the entire file:

```python
import os
from flask import Flask
from .db import init_db


def create_app():
    app = Flask(__name__)
    app.config['DB_PATH'] = os.environ.get('DB_PATH', '/data/navigatarr.db')
    app.config['NAVIGATARR_HOST'] = os.environ.get('NAVIGATARR_HOST', 'localhost')

    with app.app_context():
        init_db(app.config['DB_PATH'])

    return app
```

- [ ] **Step 3: Verify DB is created on container start**

```bash
docker compose up -d
ls data/
```

Expected: `navigatarr.db` appears in `./data/`

```bash
sqlite3 data/navigatarr.db ".schema"
```

Expected:
```
CREATE TABLE services (
    container_id TEXT PRIMARY KEY,
    custom_label  TEXT,
    visible       INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0
);
```

```bash
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add app/db.py app/__init__.py
git commit -m "feat: database layer"
```

---

### Task 4: Routes and base dashboard template

**Files:**
- Create: `app/routes.py`
- Create: `app/templates/index.html` (normal view only — no edit mode JS yet)
- Modify: `app/__init__.py` — register blueprint

**Interfaces:**
- Consumes:
  - `list_services() -> tuple[list[dict], str | None]` from `app.docker_client`
  - `get_preferences(db_path)`, `upsert_services(db_path, ids)` from `app.db`
  - `app.config['DB_PATH']`, `app.config['NAVIGATARR_HOST']`
- Produces:
  - `GET /` — renders `index.html` with `services` (list of merged dicts) and `error` (str or None)
  - `POST /api/refresh` — `200 {"services": [...]}` or `500 {"error": "..."}`
  - `POST /api/preferences` — `200 {"ok": true}` or `500 {"error": "..."}`
  - Each merged service dict has: `container_id`, `name`, `image`, `status`, `ports`, `custom_label` (str), `visible` (bool), `sort_order` (int), `urls` (list[str])

- [ ] **Step 1: Create `app/routes.py`**

```python
from flask import Blueprint, current_app, jsonify, render_template, request
from .docker_client import list_services
from .db import get_preferences, upsert_services, save_preferences

bp = Blueprint('main', __name__)


def _merge(db_path, host):
    services, error = list_services()
    if error:
        return None, error
    upsert_services(db_path, [s['container_id'] for s in services])
    prefs = get_preferences(db_path)
    merged = []
    for svc in services:
        pref = prefs.get(svc['container_id'], {})
        merged.append({
            **svc,
            'custom_label': pref.get('custom_label') or '',
            'visible': bool(pref.get('visible', 1)),
            'sort_order': pref.get('sort_order', 0),
            'urls': [f'http://{host}:{p}' for p in svc['ports']],
        })
    merged.sort(key=lambda x: x['sort_order'])
    return merged, None


@bp.get('/')
def index():
    db_path = current_app.config['DB_PATH']
    host = current_app.config['NAVIGATARR_HOST']
    services, error = _merge(db_path, host)
    return render_template('index.html', services=services or [], error=error)


@bp.post('/api/refresh')
def api_refresh():
    db_path = current_app.config['DB_PATH']
    host = current_app.config['NAVIGATARR_HOST']
    services, error = _merge(db_path, host)
    if error:
        return jsonify({'error': error}), 500
    return jsonify({'services': services})


@bp.post('/api/preferences')
def api_preferences():
    db_path = current_app.config['DB_PATH']
    data = request.get_json()
    if not data or 'services' not in data:
        return jsonify({'error': 'invalid payload'}), 400
    try:
        save_preferences(db_path, data['services'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})
```

- [ ] **Step 2: Register blueprint in `app/__init__.py`**

Replace the entire file:

```python
import os
from flask import Flask
from .db import init_db


def create_app():
    app = Flask(__name__)
    app.config['DB_PATH'] = os.environ.get('DB_PATH', '/data/navigatarr.db')
    app.config['NAVIGATARR_HOST'] = os.environ.get('NAVIGATARR_HOST', 'localhost')

    with app.app_context():
        init_db(app.config['DB_PATH'])

    from .routes import bp
    app.register_blueprint(bp)
    return app
```

- [ ] **Step 3: Create `app/templates/index.html` (normal view only)**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>navigatarr</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #1a1a1a; min-height: 100vh; }
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.875rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e5e5;
  position: sticky; top: 0; z-index: 10;
}
.topbar h1 { font-size: 1.125rem; font-weight: 700; letter-spacing: -0.02em; }
.topbar-actions { display: flex; align-items: center; gap: 0.375rem; }

button {
  background: none; border: none; cursor: pointer;
  padding: 0.3rem 0.5rem; border-radius: 0.3rem;
  font-size: 1rem; color: #555; line-height: 1;
}
button:hover { background: #f0f0f0; color: #111; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem; padding: 1.5rem;
}

.card {
  background: #fff; border: 1px solid #e5e5e5; border-radius: 0.5rem;
  padding: 1rem; display: flex; gap: 0.75rem; position: relative;
}
.card-handle { display: none; }
.status-dot {
  width: 0.5rem; height: 0.5rem; border-radius: 50%;
  flex-shrink: 0; margin-top: 0.35rem;
}
.status-running  { background: #22c55e; }
.status-paused   { background: #f59e0b; }
.status-exited   { background: #ef4444; }
.status-stopped  { background: #ef4444; }
.status-dead     { background: #ef4444; }
.status-other    { background: #9ca3af; }

.card-body { flex: 1; min-width: 0; }
.card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
.card-title a { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-meta { font-size: 0.78rem; color: #888; margin-bottom: 0.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-urls { display: flex; flex-direction: column; gap: 0.2rem; }
.card-url { font-size: 0.78rem; color: #aaa; font-family: monospace; }
.card-url a { color: #aaa; }
.card-url a:hover { color: #555; }

.card-actions { display: none; }

.empty-state { grid-column: 1/-1; text-align: center; padding: 4rem 2rem; color: #aaa; font-size: 0.9rem; }
.error-banner { background: #fee2e2; border-bottom: 1px solid #fca5a5; color: #991b1b; padding: 0.625rem 1.5rem; font-size: 0.85rem; }
</style>
</head>
<body>

<div class="topbar">
  <h1>navigatarr</h1>
  <div class="topbar-actions">
    <span id="api-error" style="font-size:0.8rem;color:#dc2626;"></span>
    <button id="btn-refresh" style="display:none" onclick="doRefresh()" title="Refresh from Docker">↺</button>
    <button id="btn-save"    style="display:none" onclick="doSave()"    title="Save & exit edit mode">✓</button>
    <button id="btn-edit"                         onclick="enterEditMode()" title="Edit">✏</button>
  </div>
</div>

{% if error %}
<div class="error-banner">Could not connect to Docker: {{ error }}</div>
{% endif %}

<div class="grid" id="card-grid">
  {% for svc in services %}
  {% if svc.visible %}
  <div class="card"
       data-id="{{ svc.container_id }}"
       data-visible="1"
       data-name="{{ svc.name | e }}">
    <div class="card-handle">⠿</div>
    <div class="status-dot status-{{ svc.status if svc.status in ('running','paused','exited','stopped','dead') else 'other' }}"></div>
    <div class="card-body">
      <div class="card-title">
        <a href="{{ svc.urls[0] }}" target="_blank" class="view-label">{{ svc.custom_label or svc.name }}</a>
        <input class="edit-label" type="text" value="{{ svc.custom_label | e }}" placeholder="{{ svc.name | e }}" style="display:none;font-weight:600;font-size:0.95rem;border:1px solid #d0d0d0;border-radius:0.25rem;padding:0.1rem 0.4rem;width:100%;">
      </div>
      <div class="card-meta">{{ svc.name }} · {{ svc.image }}</div>
      <div class="card-urls">
        {% for url in svc.urls %}
        <div class="card-url"><a href="{{ url }}" target="_blank">{{ url }}</a></div>
        {% endfor %}
      </div>
    </div>
    <div class="card-actions">
      <button class="toggle-btn" onclick="toggleVisible(this)" title="Toggle visibility" style="font-size:0.9rem;padding:0.2rem;">👁</button>
    </div>
  </div>
  {% endif %}
  {% endfor %}

  {% if not services %}
  <div class="empty-state">No services found. Click ✏ to refresh.</div>
  {% endif %}
</div>

</body>
</html>
```

- [ ] **Step 4: Rebuild and smoke-test**

```bash
docker compose up --build -d
curl -s http://localhost:7676/ | head -5
```

Expected: HTML output starting with `<!DOCTYPE html>`

```bash
curl -s -X POST http://localhost:7676/api/refresh
```

Expected: `{"services": [...]}` (list may be empty if no exposed-port containers running)

```bash
curl -s -X POST http://localhost:7676/api/preferences \
  -H 'Content-Type: application/json' \
  -d '{"services": []}'
```

Expected: `{"ok": true}`

```bash
docker compose down
```

- [ ] **Step 5: Commit**

```bash
git add app/routes.py app/__init__.py app/templates/index.html
git commit -m "feat: routes and base dashboard template"
```

---

### Task 5: Edit mode

**Files:**
- Modify: `app/templates/index.html` — add edit mode CSS, hidden card support, SortableJS, and all JS

**Interfaces:**
- Consumes:
  - `POST /api/refresh` → `{ services: [{container_id, name, image, status, ports, custom_label, visible, sort_order, urls}] }`
  - `POST /api/preferences` → `{ ok: true }`
- Produces: fully interactive edit mode (drag-to-reorder, toggle visibility, inline label edit, refresh from Docker, save)

- [ ] **Step 1: Replace `app/templates/index.html` with the complete version including edit mode**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>navigatarr</title>
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.3/Sortable.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #1a1a1a; min-height: 100vh; }
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.875rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e5e5;
  position: sticky; top: 0; z-index: 10;
  transition: background 0.15s, border-color 0.15s;
}
.topbar h1 { font-size: 1.125rem; font-weight: 700; letter-spacing: -0.02em; }
.topbar-actions { display: flex; align-items: center; gap: 0.375rem; }

button {
  background: none; border: none; cursor: pointer;
  padding: 0.3rem 0.5rem; border-radius: 0.3rem;
  font-size: 1rem; color: #555; line-height: 1;
}
button:hover { background: #f0f0f0; color: #111; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem; padding: 1.5rem;
}

.card {
  background: #fff; border: 1px solid #e5e5e5; border-radius: 0.5rem;
  padding: 1rem; display: flex; gap: 0.75rem; position: relative;
  transition: opacity 0.15s;
}
.card-handle {
  display: none; cursor: grab; color: #bbb; align-items: center;
  font-size: 1.1rem; user-select: none; flex-shrink: 0;
}
.card-handle:active { cursor: grabbing; }
.status-dot {
  width: 0.5rem; height: 0.5rem; border-radius: 50%;
  flex-shrink: 0; margin-top: 0.35rem;
}
.status-running  { background: #22c55e; }
.status-paused   { background: #f59e0b; }
.status-exited   { background: #ef4444; }
.status-stopped  { background: #ef4444; }
.status-dead     { background: #ef4444; }
.status-other    { background: #9ca3af; }

.card-body { flex: 1; min-width: 0; }
.card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
.card-title a { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-title input {
  font-weight: 600; font-size: 0.95rem; font-family: inherit;
  border: 1px solid #d0d0d0; border-radius: 0.25rem;
  padding: 0.1rem 0.4rem; width: 100%;
}
.card-meta { font-size: 0.78rem; color: #888; margin-bottom: 0.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-urls { display: flex; flex-direction: column; gap: 0.2rem; }
.card-url { font-size: 0.78rem; color: #aaa; font-family: monospace; }
.card-url a { color: #aaa; }
.card-url a:hover { color: #555; }

.card-actions {
  display: none; position: absolute; top: 0.5rem; right: 0.5rem;
}
.toggle-btn { font-size: 0.9rem; padding: 0.2rem; color: #aaa; }
.toggle-btn:hover { color: #555; background: none; }

/* Edit mode */
body.edit-mode { background: #eff6ff; }
body.edit-mode .topbar { background: #dbeafe; border-color: #bfdbfe; }
body.edit-mode .card-handle { display: flex; }
body.edit-mode .card-actions { display: flex; }
body.edit-mode .card.is-hidden { opacity: 0.4; }

.sortable-ghost  { opacity: 0.35; }
.sortable-chosen { box-shadow: 0 4px 12px rgba(0,0,0,0.12); }

.empty-state { grid-column: 1/-1; text-align: center; padding: 4rem 2rem; color: #aaa; font-size: 0.9rem; }
.error-banner { background: #fee2e2; border-bottom: 1px solid #fca5a5; color: #991b1b; padding: 0.625rem 1.5rem; font-size: 0.85rem; }
</style>
</head>
<body>

<div class="topbar">
  <h1>navigatarr</h1>
  <div class="topbar-actions">
    <span id="api-error" style="font-size:0.8rem;color:#dc2626;"></span>
    <button id="btn-refresh" style="display:none" onclick="doRefresh()" title="Refresh from Docker">↺</button>
    <button id="btn-save"    style="display:none" onclick="doSave()"    title="Save & exit edit mode">✓</button>
    <button id="btn-edit"                         onclick="enterEditMode()" title="Edit">✏</button>
  </div>
</div>

{% if error %}
<div class="error-banner">Could not connect to Docker: {{ error }}</div>
{% endif %}

<div class="grid" id="card-grid">
  {% for svc in services %}
  <div class="card {% if not svc.visible %}is-hidden view-hidden{% endif %}"
       data-id="{{ svc.container_id }}"
       data-visible="{{ '1' if svc.visible else '0' }}"
       data-name="{{ svc.name | e }}"
       {% if not svc.visible %}style="display:none"{% endif %}>
    <div class="card-handle">⠿</div>
    <div class="status-dot status-{{ svc.status if svc.status in ('running','paused','exited','stopped','dead') else 'other' }}"></div>
    <div class="card-body">
      <div class="card-title">
        <a href="{{ svc.urls[0] }}" target="_blank" class="view-label">{{ svc.custom_label or svc.name }}</a>
        <input class="edit-label" type="text" value="{{ svc.custom_label | e }}" placeholder="{{ svc.name | e }}" style="display:none">
      </div>
      <div class="card-meta">{{ svc.name }} · {{ svc.image }}</div>
      <div class="card-urls">
        {% for url in svc.urls %}
        <div class="card-url"><a href="{{ url }}" target="_blank">{{ url }}</a></div>
        {% endfor %}
      </div>
    </div>
    <div class="card-actions">
      <button class="toggle-btn" onclick="toggleVisible(this)" title="Toggle visibility">
        {{ '👁' if svc.visible else '🙈' }}
      </button>
    </div>
  </div>
  {% endfor %}

  {% if not services %}
  <div class="empty-state" id="empty-state">No services found. Click ✏ to refresh.</div>
  {% endif %}
</div>

<script>
let sortable = null;

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function setApiError(msg) {
  document.getElementById('api-error').textContent = msg;
}

function enterEditMode() {
  document.body.classList.add('edit-mode');
  document.getElementById('btn-edit').style.display    = 'none';
  document.getElementById('btn-refresh').style.display = '';
  document.getElementById('btn-save').style.display    = '';

  document.querySelectorAll('#card-grid .card').forEach(card => {
    card.style.display = '';
    card.querySelector('.view-label').style.display = 'none';
    card.querySelector('.edit-label').style.display = '';
  });

  sortable = Sortable.create(document.getElementById('card-grid'), {
    handle: '.card-handle',
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    filter: '.empty-state',
    animation: 150,
  });
}

function exitEditMode() {
  document.body.classList.remove('edit-mode');
  document.getElementById('btn-edit').style.display    = '';
  document.getElementById('btn-refresh').style.display = 'none';
  document.getElementById('btn-save').style.display    = 'none';

  document.querySelectorAll('#card-grid .card').forEach(card => {
    card.querySelector('.view-label').style.display = '';
    card.querySelector('.edit-label').style.display = 'none';
    if (card.classList.contains('view-hidden')) {
      card.style.display = 'none';
    }
  });

  if (sortable) { sortable.destroy(); sortable = null; }
}

function toggleVisible(btn) {
  const card = btn.closest('.card');
  const nowVisible = card.dataset.visible === '1';
  card.dataset.visible = nowVisible ? '0' : '1';
  card.classList.toggle('is-hidden', nowVisible);
  card.classList.toggle('view-hidden', nowVisible);
  btn.textContent = nowVisible ? '🙈' : '👁';
}

function collectServices() {
  return Array.from(document.querySelectorAll('#card-grid .card')).map((card, i) => ({
    container_id: card.dataset.id,
    custom_label: card.querySelector('.edit-label').value,
    visible:      card.dataset.visible === '1' ? 1 : 0,
    sort_order:   i,
  }));
}

function buildCard(svc) {
  const statusClasses = ['running','paused','exited','stopped','dead'];
  const statusClass = statusClasses.includes(svc.status) ? `status-${svc.status}` : 'status-other';
  const hidden = !svc.visible;
  const urlsHtml = svc.urls.map(u =>
    `<div class="card-url"><a href="${esc(u)}" target="_blank">${esc(u)}</a></div>`
  ).join('');
  const card = document.createElement('div');
  card.className = `card${hidden ? ' is-hidden view-hidden' : ''}`;
  card.dataset.id      = svc.container_id;
  card.dataset.visible = svc.visible ? '1' : '0';
  card.dataset.name    = svc.name;
  if (hidden) card.style.display = 'none';
  card.innerHTML = `
    <div class="card-handle">⠿</div>
    <div class="status-dot ${statusClass}"></div>
    <div class="card-body">
      <div class="card-title">
        <a href="${esc(svc.urls[0] || '#')}" target="_blank" class="view-label" style="display:none">${esc(svc.custom_label || svc.name)}</a>
        <input class="edit-label" type="text" value="${esc(svc.custom_label || '')}" placeholder="${esc(svc.name)}">
      </div>
      <div class="card-meta">${esc(svc.name)} · ${esc(svc.image)}</div>
      <div class="card-urls">${urlsHtml}</div>
    </div>
    <div class="card-actions">
      <button class="toggle-btn" onclick="toggleVisible(this)" title="Toggle visibility">
        ${svc.visible ? '👁' : '🙈'}
      </button>
    </div>`;
  return card;
}

function renderCards(services) {
  const grid = document.getElementById('card-grid');
  grid.innerHTML = '';
  if (!services.length) {
    grid.innerHTML = '<div class="empty-state">No services found. Click ✏ to refresh.</div>';
    return;
  }
  services.forEach(svc => grid.appendChild(buildCard(svc)));
  if (sortable) {
    sortable.destroy();
    sortable = Sortable.create(grid, {
      handle: '.card-handle',
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      filter: '.empty-state',
      animation: 150,
    });
  }
}

async function doRefresh() {
  setApiError('');
  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) { setApiError(data.error || 'Refresh failed'); return; }
    renderCards(data.services);
  } catch {
    setApiError('Refresh failed');
  }
}

async function doSave() {
  setApiError('');
  try {
    const res = await fetch('/api/preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ services: collectServices() }),
    });
    const data = await res.json();
    if (!res.ok) { setApiError(data.error || 'Save failed'); return; }
    exitEditMode();
  } catch {
    setApiError('Save failed');
  }
}
</script>
</body>
</html>
```

- [ ] **Step 2: Rebuild and test normal view**

```bash
docker compose up --build -d
```

Open `http://localhost:7676` in a browser. Verify:
- Service cards appear (or empty state if none running)
- Status dots are colored correctly
- Clicking a service URL opens the target in a new tab

- [ ] **Step 3: Test edit mode interactions**

Click the ✏ icon. Verify:
- Page background shifts to light blue
- Drag handles (⠿) appear on card left edges
- Toggle (👁/🙈) buttons appear on card top-right
- Label field becomes an editable input (placeholder = container name)
- ✏ replaced by ↺ and ✓

Drag a card to a new position. Verify: order changes in the DOM.

Click 👁 on a card to hide it. Verify: card dims.

Click ✓ to save. Verify: edit mode exits cleanly, hidden card disappears.

Reload the page. Verify: order and visibility are persisted (SQLite).

- [ ] **Step 4: Test refresh in edit mode**

Click ✏, then ↺. Verify: cards re-render in place, no page reload, new containers appear if any were started.

- [ ] **Step 5: Test error state**

```bash
docker compose down
docker run --rm -p 7676:7676 -e DB_PATH=/tmp/nav.db navigatarr python run.py
```

Open `http://localhost:7676`. Verify: error banner appears ("Could not connect to Docker…").

```bash
# stop the test container
```

- [ ] **Step 6: Final bring-up and commit**

```bash
docker compose up --build -d
```

```bash
git add app/templates/index.html
git commit -m "feat: edit mode with drag-to-reorder, visibility toggle, and inline label editing"
```

---

## Done

At this point navigatarr is fully functional:
- `docker compose up` brings up the dashboard at `http://localhost:7676`
- Service cards link to `http://{NAVIGATARR_HOST}:{port}`
- Edit mode (✏) enables drag-to-reorder, visibility toggle, and custom label editing
- ↺ refreshes the container list from Docker without a page reload
- ✓ persists all preferences to SQLite and exits edit mode
- Preferences survive container restarts via the `./data` volume mount
