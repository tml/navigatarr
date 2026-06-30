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
    if not data or not isinstance(data.get('services'), list):
        return jsonify({'error': 'invalid payload'}), 400
    required_keys = {'container_id', 'custom_label', 'visible', 'sort_order'}
    for item in data['services']:
        if not isinstance(item, dict) or not required_keys.issubset(item.keys()):
            return jsonify({'error': 'invalid service entry'}), 400
        if not isinstance(item['container_id'], str) or not item['container_id']:
            return jsonify({'error': 'invalid container_id'}), 400
        if not isinstance(item['visible'], int) or item['visible'] not in (0, 1):
            return jsonify({'error': 'invalid visible value'}), 400
        if not isinstance(item['sort_order'], int):
            return jsonify({'error': 'invalid sort_order'}), 400
    try:
        save_preferences(db_path, data['services'])
    except Exception as e:
        return jsonify({'error': 'failed to save preferences'}), 500
    return jsonify({'ok': True})
