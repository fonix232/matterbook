"""Registration of the MatterBook sidebar panel.

The panel is a custom panel rather than an add-on with ingress: ingress is a
Supervisor feature, so using it would force MatterBook to be an add-on and
restrict it to HA OS and Supervised installs. A custom panel runs inside the
frontend, which hands it the authenticated `hass` object, the existing WebSocket
connection and the user's theme for free. See PANEL.md.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "matterbook"
PANEL_COMPONENT = "matterbook-panel"
STATIC_URL = f"/{DOMAIN}_panel"
BUNDLE_NAME = "matterbook-panel.js"

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


def _bundle_path() -> Path:
    """Return the path of the built panel bundle."""
    return Path(__file__).parent / "panel" / BUNDLE_NAME


def _bundle_hash(path: Path) -> str:
    """Return a short hash of the bundle, for cache busting."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_panel(hass: HomeAssistant, csv_path: Path) -> None:
    """Serve the panel bundle and add the sidebar tab."""
    bundle = _bundle_path()
    if not bundle.is_file():
        _LOGGER.warning(
            "The MatterBook panel bundle is missing at %s; the sidebar tab will not "
            "be registered. Build it with `npm run build` in the panel directory",
            bundle,
        )
        return

    # Static paths cannot be unregistered, so this happens once per Home
    # Assistant run even if the config entry is reloaded.
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    f"{STATIC_URL}/{BUNDLE_NAME}",
                    str(bundle),
                    # The URL carries a content hash, so the browser may cache it
                    # forever; what must never be cached is a stale bundle under
                    # an unchanged URL.
                    cache_headers=True,
                )
            ]
        )
        hass.data[_STATIC_REGISTERED] = True

    bundle_hash = await hass.async_add_executor_job(_bundle_hash, bundle)

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        module_url=f"{STATIC_URL}/{BUNDLE_NAME}?hash={bundle_hash}",
        sidebar_title="MatterBook",
        sidebar_icon="mdi:book-lock",
        # The panel lists setup codes and can commission devices onto the fabric.
        require_admin=True,
        config={"csv_path": str(csv_path)},
        config_panel_domain=DOMAIN,
    )


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar tab.

    Registering a panel that already exists raises, so a reload must remove the
    old one first.
    """
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
