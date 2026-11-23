"""Icons of the Hopla catalogue, as the card draws them.

Hopla stores the id of an icon (an older emoji for some data). The card only
receives a known id, and falls back to the default icon of each kind, as the
Hopla web does. The drawings and the list of ids are copied by
`scripts/sync-icons.py`.
"""
import json
from functools import lru_cache
from pathlib import Path

CATALOGUE = Path(__file__).parent / "frontend" / "icons" / "catalogue.json"

TASK_DEFAULT = "task_default"
REWARD_DEFAULT = "reward_default"
PROJECT_DEFAULT = "project_default"
ROUTINE_DEFAULT = "routine_default"
CHALLENGE_DEFAULT = "trophy"


@lru_cache(maxsize=1)
def _catalogue():
    try:
        data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset(), {}
    return frozenset(data.get("ids") or []), data.get("emoji") or {}


def resolve_icon(value, default):
    """The id of a known icon from its id or the emoji it replaced, else the default."""
    ids, emoji = _catalogue()
    if isinstance(value, str):
        value = value.strip()
        if value in ids:
            return value
        found = emoji.get(value.replace("️", ""))
        if found:
            return found
    return default


def with_icons(today, board):
    """Give a known icon id to each routine, project and challenge of the
    games and of the rated challenges board, in place, so the card draws them."""
    for key, default in (("routines", ROUTINE_DEFAULT), ("projects", PROJECT_DEFAULT),
                         ("challenges", CHALLENGE_DEFAULT)):
        for item in (today or {}).get(key) or []:
            item["icon"] = resolve_icon(item.get("icon"), default)
    for item in board or []:
        item["icon"] = resolve_icon(item.get("icon"), CHALLENGE_DEFAULT)
