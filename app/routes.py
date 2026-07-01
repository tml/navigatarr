from flask import Blueprint, current_app, jsonify, render_template, request
from .docker_client import list_services
from .db import get_preferences, upsert_services, save_preferences
from .icons import icon_url_for, icon_url_from_label

bp = Blueprint('main', __name__)


def _merge(db_path, host, show_self=True, self_id=''):
    services, error = list_services()
    if error:
        return None, error
    if not show_self and self_id:
        services = [s for s in services if s['container_id'] != self_id]
    upsert_services(db_path, [s['container_id'] for s in services])
    prefs = get_preferences(db_path)
    merged = []
    for svc in services:
        pref = prefs.get(svc['container_id'], {})
        auto_urls = [f'http://{host}:{p}' for p in svc['ports']]
        # Icon: prefer homepage.icon label, then auto-detect
        icon_url = (
            icon_url_from_label(svc.get('label_icon', ''))
            or icon_url_for(svc['name'], svc['image'])
        )
        # Default label: homepage.name label, then container name
        default_label = svc.get('label_name') or svc['name']
        # Default href: homepage.href label, then first auto URL
        default_href = svc.get('label_href') or (auto_urls[0] if auto_urls else '')
        effective_href = pref.get('custom_href') or default_href
        merged.append({
            **svc,
            'custom_label': pref.get('custom_label') or '',
            'custom_href': pref.get('custom_href') or '',
            'default_label': default_label,
            'default_href': default_href,
            'effective_href': effective_href,
            'visible': bool(pref.get('visible', 1)),
            'sort_order': pref.get('sort_order', 0),
            'urls': auto_urls,
            'icon_url': icon_url,
            'group': svc.get('label_group', ''),
            'description': svc.get('label_description', ''),
        })
    merged.sort(key=lambda x: x['sort_order'])
    return merged, None


@bp.get('/')
def index():
    db_path = current_app.config['DB_PATH']
    host = current_app.config['NAVIGATARR_HOST']
    services, error = _merge(db_path, host, current_app.config['SHOW_SELF'], current_app.config['SELF_ID'])
    return render_template('index.html', services=services or [], error=error)


@bp.post('/api/refresh')
def api_refresh():
    db_path = current_app.config['DB_PATH']
    host = current_app.config['NAVIGATARR_HOST']
    services, error = _merge(db_path, host, current_app.config['SHOW_SELF'], current_app.config['SELF_ID'])
    if error:
        return jsonify({'error': error}), 500
    return jsonify({'services': services})


@bp.post('/api/preferences')
def api_preferences():
    db_path = current_app.config['DB_PATH']
    data = request.get_json()
    if not data or not isinstance(data.get('services'), list):
        return jsonify({'error': 'invalid payload'}), 400
    required_keys = {'container_id', 'custom_label', 'custom_href', 'visible', 'sort_order'}
    for item in data['services']:
        if not isinstance(item, dict) or not required_keys.issubset(item.keys()):
            return jsonify({'error': 'invalid service entry'}), 400
        if not isinstance(item['container_id'], str) or not item['container_id']:
            return jsonify({'error': 'invalid container_id'}), 400
        if not isinstance(item['visible'], int) or item['visible'] not in (0, 1):
            return jsonify({'error': 'invalid visible value'}), 400
        if not isinstance(item['sort_order'], int):
            return jsonify({'error': 'invalid sort_order'}), 400
        if not isinstance(item['custom_href'], str):
            return jsonify({'error': 'invalid custom_href'}), 400
    try:
        save_preferences(db_path, data['services'])
    except Exception:
        return jsonify({'error': 'failed to save preferences'}), 500
    return jsonify({'ok': True})
