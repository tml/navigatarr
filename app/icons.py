import json
import logging
import urllib.request

_GITHUB_TREES_URL = 'https://api.github.com/repos/homarr-labs/dashboard-icons/git/trees/main?recursive=1'
_RAW_BASE = 'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg'

_icon_names: list[str] = []  # sorted longest-first for specificity


def load_icons() -> None:
    global _icon_names
    try:
        req = urllib.request.Request(
            _GITHUB_TREES_URL,
            headers={'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'navigatarr'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        _icon_names = sorted(
            [
                item['path'][4:-4]
                for item in data.get('tree', [])
                if item['path'].startswith('svg/') and item['path'].endswith('.svg')
            ],
            key=len,
            reverse=True,
        )
    except Exception:
        logging.warning('navigatarr: could not fetch icon list from GitHub — icons disabled')
        _icon_names = []


def _image_basename(image: str) -> str:
    # "ghcr.io/gethomepage/homepage:latest" → "homepage"
    # "lscr.io/linuxserver/plex:latest" → "plex"
    return image.split(':')[0].split('/')[-1]


def icon_url_for(container_name: str, image: str) -> str | None:
    if not _icon_names:
        return None
    # Match against container name and image basename only — not the registry URL
    text = (container_name + ' ' + _image_basename(image)).lower()
    for icon in _icon_names:
        if len(icon) < 3:
            continue
        if icon in text:
            return f'{_RAW_BASE}/{icon}.svg'
    return None
