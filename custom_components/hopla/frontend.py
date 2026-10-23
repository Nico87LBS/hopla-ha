"""Serve and automatically load the bundled Hopla dashboard cards."""
import asyncio
from hashlib import sha256
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

FRONTEND_DIR = Path(__file__).parent / "frontend"
CARD_URL = "/hopla/hopla-user-todo-card.js"
CARD_FILE = FRONTEND_DIR / "hopla-user-todo-card.js"
FAMILY_CARD_URL = "/hopla/hopla-family-card.js"
FAMILY_CARD_FILE = FRONTEND_DIR / "hopla-family-card.js"
CARDS = ((CARD_URL, CARD_FILE), (FAMILY_CARD_URL, FAMILY_CARD_FILE))
# Shared by both cards: the translation helper, one text file per language and
# the drawn rank badges.
SHARED = (("/hopla/hopla-i18n.js", FRONTEND_DIR / "hopla-i18n.js"),
          ("/hopla/locales", FRONTEND_DIR / "locales"),
          ("/hopla/ranks", FRONTEND_DIR / "ranks"))
DATA_FRONTEND = "hopla_frontend"


def frontend_version() -> str:
    """Hash every frontend file, so any change reaches browsers past their cache."""
    digest = sha256()
    for path in sorted(FRONTEND_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(FRONTEND_DIR).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register once per HA process, including concurrent entries and reloads."""
    state = hass.data.setdefault(DATA_FRONTEND, {"lock": asyncio.Lock()})
    async with state["lock"]:
        if state.get("registered"):
            return
        # File IO runs outside the event loop. The cards pass the version on to
        # the files they load, so translations are refreshed with them.
        version = await hass.async_add_executor_job(frontend_version)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(url, str(path), False) for url, path in CARDS + SHARED]
        )
        for url, _ in CARDS:
            add_extra_js_url(hass, f"{url}?v={version}")
        state["registered"] = True
        # The cards compare it with their own to reload an open dashboard.
        state["version"] = version
