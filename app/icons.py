import json
import logging
import urllib.request

_GITHUB_TREES_URL = 'https://api.github.com/repos/homarr-labs/dashboard-icons/git/trees/main?recursive=1'
_RAW_BASE = 'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg'

_icon_names: list[str] = []   # sorted longest-first for substring matching
_icon_set: set[str] = set()   # for O(1) exact lookup


def load_icons() -> None:
    global _icon_names, _icon_set
    try:
        req = urllib.request.Request(
            _GITHUB_TREES_URL,
            headers={'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'navigatarr'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        names = [
            item['path'][4:-4]
            for item in data.get('tree', [])
            if item['path'].startswith('svg/') and item['path'].endswith('.svg')
        ]
        _icon_names = sorted(names, key=len, reverse=True)
        _icon_set = set(names)
    except Exception:
        logging.warning('navigatarr: could not fetch icon list from GitHub — icons disabled')
        _icon_names = []
        _icon_set = set()


def _image_basename(image: str) -> str:
    # "ghcr.io/gethomepage/homepage:latest" → "homepage"
    return image.split(':')[0].split('/')[-1]


def icon_url_from_label(label_icon: str) -> str | None:
    """Resolve a homepage.icon label value (e.g. 'plex.png') to a raw SVG URL."""
    if not label_icon or not _icon_set:
        return None
    name = label_icon.rsplit('.', 1)[0].lower()
    if name in _icon_set:
        return f'{_RAW_BASE}/{name}.svg'
    return None


def icon_url_for(container_name: str, image: str) -> str | None:
    """Auto-detect icon by substring matching container name and image basename."""
    if not _icon_names:
        return None
    text = (container_name + ' ' + _image_basename(image)).lower()
    for icon in _icon_names:
        if len(icon) < 3:
            continue
        if icon in text:
            return f'{_RAW_BASE}/{icon}.svg'
    return None
