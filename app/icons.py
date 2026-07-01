import json
import logging
import urllib.request

_GITHUB_API_URL = 'https://api.github.com/repos/homarr-labs/dashboard-icons/contents/svg'
_RAW_BASE = 'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg'

_icon_names: list[str] = []  # sorted longest-first for specificity


def load_icons() -> None:
    global _icon_names
    try:
        req = urllib.request.Request(
            _GITHUB_API_URL,
            headers={'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'navigatarr'},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read())
        _icon_names = sorted(
            [item['name'][:-4] for item in items if item['name'].endswith('.svg')],
            key=len,
            reverse=True,
        )
    except Exception:
        logging.warning('navigatarr: could not fetch icon list from GitHub — icons disabled')
        _icon_names = []


def icon_url_for(container_name: str, image: str) -> str | None:
    if not _icon_names:
        return None
    text = (container_name + ' ' + image).lower()
    for icon in _icon_names:
        if icon in text:
            return f'{_RAW_BASE}/{icon}.svg'
    return None
