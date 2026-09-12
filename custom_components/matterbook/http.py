"""Serving label images to the panel.

`<img src>` cannot send an authorisation header, so an authenticated view is not
directly usable from markup. Home Assistant's answer is a signed path: the
integration signs a URL with a short expiry, the panel puts that in the tag, and
the auth middleware accepts the signature in place of the header. Camera
snapshots work the same way.

The signature is minted per entry on every state push, so the panel always holds
fresh URLs without asking for them.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
from http import HTTPStatus
import logging
import time

from aiohttp import web

from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .qr import qr_payload, render_svg

_LOGGER = logging.getLogger(__name__)

QR_URL = f"/api/{DOMAIN}/qr"
SIGNATURE_LIFETIME = timedelta(hours=1)
# Re-sign well before a URL expires, so one never goes stale in a page that is
# simply sitting open.
REFRESH_AFTER = SIGNATURE_LIFETIME.total_seconds() / 2

# (refresh token, entry, code fingerprint) -> (url, when it was minted).
_SIGNED_URLS: dict[tuple[str, str, str], tuple[str, float]] = {}


class MatterBookQrView(HomeAssistantView):
    """Render the QR label for one entry.

    Deliberately **not** `requires_auth = False`. Home Assistant's auth middleware
    validates a signature and marks the request authenticated; the view's own
    `requires_auth` is what then lets it through. Turning it off does not mean
    "signature only" — it means no check at all, and this image is a picture of a
    setup passcode. The admin check is belt to that brace: the signature is
    issued to the refresh token of the admin who loaded the panel, and carries
    their identity with it, so a link forwarded to a non-admin still fails.
    """

    url = f"{QR_URL}/{{entry_id}}"
    name = f"api:{DOMAIN}:qr"

    @require_admin
    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        """Return the entry's QR code as SVG."""
        hass: HomeAssistant = request.app["hass"]

        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        coordinator = entries[0].runtime_data
        entry = next(
            (item for item in coordinator.data.entries if item.id == entry_id), None
        )
        if entry is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        payload = qr_payload(entry)
        if payload is None:
            # A manual code or a bare passcode has no honest QR; the panel shows
            # the digits instead of a picture that would fail in a Matter app.
            return web.Response(status=HTTPStatus.NOT_FOUND)

        svg = await hass.async_add_executor_job(render_svg, payload)
        return web.Response(
            body=svg,
            content_type="image/svg+xml",
            headers={
                # The image is a picture of a secret: it must not be cached by
                # anything in between, and the signature expires anyway.
                "Cache-Control": "no-store, private",
            },
        )


def async_register_views(hass: HomeAssistant) -> None:
    """Register MatterBook's HTTP views."""
    hass.http.register_view(MatterBookQrView())


def async_signed_qr_url(
    hass: HomeAssistant, entry_id: str, refresh_token_id: str, code: str
) -> str:
    """Return a signed, short-lived URL for an entry's QR label.

    The token is passed in rather than inferred. `async_sign_path` can work out
    who is asking from the WebSocket connection or the HTTP request it is called
    inside, but the URLs here are minted in a coordinator callback — a push, with
    no request in scope — where it would silently fall back to Home Assistant's
    read-only content user. A URL signed as that user is not an admin's, and the
    view would reject it. Handing over the subscriber's own token keeps the
    signature meaning what the panel needs it to mean, and makes it expire with
    their session.

    The result is remembered, because a signature carries the time it was made:
    signing afresh on every push would hand the panel a different `src` for the
    same picture every few minutes, and every open page would re-fetch every
    label it is showing. What the URL must track is the code — a row whose code
    changed is a different picture at the same path, and the responses carry
    `no-store`, so only a changed URL makes a browser look again.
    """
    key = (refresh_token_id, entry_id, _fingerprint(code))
    now = time.monotonic()

    cached = _SIGNED_URLS.get(key)
    if cached is not None and now - cached[1] < REFRESH_AFTER:
        return cached[0]

    url = async_sign_path(
        hass, f"{QR_URL}/{entry_id}", SIGNATURE_LIFETIME, refresh_token_id=refresh_token_id
    )
    _SIGNED_URLS[key] = (url, now)
    _prune(now)
    return url


def _fingerprint(code: str) -> str:
    """Return a short digest of a code, to key the memo without holding one."""
    return hashlib.blake2s(code.encode(), digest_size=8).hexdigest()


def _prune(now: float) -> None:
    """Drop signatures that have expired.

    The memo grows with rows times signed-in admins, so it is small — but a
    long-running instance would otherwise keep a line for every code a row has
    ever had, and for every session that ever looked at it.
    """
    lifetime = SIGNATURE_LIFETIME.total_seconds()
    for key, (_, minted) in list(_SIGNED_URLS.items()):
        if now - minted >= lifetime:
            del _SIGNED_URLS[key]
