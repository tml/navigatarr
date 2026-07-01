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
                custom_href   TEXT,
                visible       INTEGER NOT NULL DEFAULT 1,
                sort_order    INTEGER NOT NULL DEFAULT 0
            )
        ''')
        # Migrate existing DBs that predate custom_href
        try:
            conn.execute('ALTER TABLE services ADD COLUMN custom_href TEXT')
        except Exception:
            pass


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
                INSERT INTO services (container_id, custom_label, custom_href, visible, sort_order)
                VALUES (:container_id, :custom_label, :custom_href, :visible, :sort_order)
                ON CONFLICT(container_id) DO UPDATE SET
                    custom_label = excluded.custom_label,
                    custom_href  = excluded.custom_href,
                    visible      = excluded.visible,
                    sort_order   = excluded.sort_order
            ''', svc)
