"""The bridge to Home Assistant's Matter integration.

Commissioning is not exposed as a Home Assistant action; it is reachable only
through the admin WebSocket command `matter/commission` or the Matter config
flow, and neither can be called from an automation. What *is* reachable from
Python inside Home Assistant is the `MatterClient` the Matter integration keeps
on its config entry, which is what this module hands to the coordinator.

Two ways in, in order of preference:

1. the live client on the Matter config entry's ``runtime_data`` — free, shares
   the existing connection, and is what Home Assistant's own code does;
2. a short-lived client of our own, connected to the server URL stored in that
   same config entry's (public) data, used only if (1) stops working.

(1) reaches into another integration's internals, which core is free to change
between releases; (2) exists so that a rename there degrades MatterBook to a
slightly heavier code path instead of breaking it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MATTER_DOMAIN

if TYPE_CHECKING:
    from matter_server.client import MatterClient
    from matter_server.common.models import CommissionableNodeData, MatterNodeData

_LOGGER = logging.getLogger(__name__)


class MatterUnavailable(HomeAssistantError):
    """Raised when the Matter integration or its server cannot be reached."""


class CommissioningFailed(HomeAssistantError):
    """Raised when the Matter server refused or failed a commissioning attempt."""


def _matter_entries(hass: HomeAssistant) -> list[Any]:
    """Return the loaded Matter config entries."""
    return [
        entry
        for entry in hass.config_entries.async_entries(MATTER_DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def async_get_client(hass: HomeAssistant) -> MatterClient | None:
    """Return the Matter integration's live client, or ``None`` if there is none.

    Every attribute hop here belongs to another integration, so each one is
    guarded: a core refactor should make this return ``None`` (and fall back to
    our own connection) rather than raise somewhere far away.
    """
    for entry in _matter_entries(hass):
        runtime_data = getattr(entry, "runtime_data", None)
        adapter = getattr(runtime_data, "adapter", None)
        client = getattr(adapter, "matter_client", None)
        if client is not None:
            return client
        _LOGGER.debug("Matter config entry %s exposes no matter_client", entry.entry_id)
    return None


def async_get_server_url(hass: HomeAssistant) -> str | None:
    """Return the Matter server WebSocket URL from the Matter config entry."""
    for entry in _matter_entries(hass):
        if url := entry.data.get(CONF_URL):
            return str(url)
    return None


@asynccontextmanager
async def _ephemeral_client(hass: HomeAssistant) -> AsyncIterator[MatterClient]:
    """Connect our own client to the Matter server for the duration of a call.

    No ``start_listening`` here: that would duplicate the node subscriptions the
    Matter integration already holds. Commands work on a plain connection.
    """
    from matter_server.client import MatterClient as _MatterClient  # noqa: PLC0415

    url = async_get_server_url(hass)
    if url is None:
        raise MatterUnavailable("No Matter server URL is configured in Home Assistant")

    client = _MatterClient(url, async_get_clientsession(hass))
    try:
        await client.connect()
    except Exception as err:  # the client raises several transport error types
        raise MatterUnavailable(f"Cannot connect to the Matter server at {url}: {err}") from err
    try:
        yield client
    finally:
        await client.disconnect()


@asynccontextmanager
async def matter_client(hass: HomeAssistant) -> AsyncIterator[MatterClient]:
    """Yield a usable Matter client, preferring the Matter integration's own."""
    client = async_get_client(hass)
    if client is not None and client.connection.connected:
        yield client
        return

    if not _matter_entries(hass):
        raise MatterUnavailable(
            "The Matter integration is not set up; MatterBook needs it to commission devices"
        )
    _LOGGER.debug("Falling back to an own connection to the Matter server")
    async with _ephemeral_client(hass) as fallback:
        yield fallback


async def async_server_info(hass: HomeAssistant) -> Any:
    """Return the Matter server's info message, or ``None`` if unavailable."""
    client = async_get_client(hass)
    if client is None:
        return None
    return client.server_info


async def async_discover(hass: HomeAssistant, timeout: float) -> list[CommissionableNodeData]:
    """Ask the Matter server which commissionable devices it can see.

    The server discovers over mDNS (`_matterc._udp`) and, when Bluetooth or a BLE
    proxy is available to it, over BLE as well.
    """
    async with matter_client(hass) as client:
        try:
            async with asyncio.timeout(timeout):
                return await client.discover_commissionable_nodes()
        except TimeoutError as err:
            raise MatterUnavailable(f"Matter server discovery timed out after {timeout}s") from err
        except Exception as err:  # surface any server-side failure as one type
            raise MatterUnavailable(f"Matter server discovery failed: {err}") from err


async def async_commission(
    hass: HomeAssistant,
    code: str,
    *,
    network_only: bool,
    timeout: float,
) -> MatterNodeData:
    """Commission one device with a setup code.

    Args:
        code: QR payload or manual pairing code.
        network_only: restrict to devices already on the IP network. Must be
            ``False`` to reach a device that is only advertising over BLE, which
            in turn needs Bluetooth (or a BLE proxy) available to the server.
        timeout: how long to wait before giving up on the server.

    Raises:
        CommissioningFailed: the server refused, failed or did not answer in time.
    """
    async with matter_client(hass) as client:
        try:
            async with asyncio.timeout(timeout):
                return await client.commission_with_code(code, network_only=network_only)
        except TimeoutError as err:
            raise CommissioningFailed(f"Commissioning timed out after {timeout}s") from err
        except Exception as err:  # MatterError subclasses plus transport errors
            raise CommissioningFailed(str(err) or type(err).__name__) from err


def async_get_nodes(hass: HomeAssistant) -> list[Any]:
    """Return the nodes already commissioned onto Home Assistant's fabric.

    This reads the Matter integration's live client, which holds the node list it
    subscribed to at startup. A short-lived connection of our own would come back
    empty — the node cache is filled by `start_listening`, which only the Matter
    integration should be doing.

    Raises:
        MatterUnavailable: when the Matter integration is not loaded.
    """
    client = async_get_client(hass)
    if client is None:
        raise MatterUnavailable(
            "The Matter integration is not loaded, so there is no fabric to import from"
        )
    return list(client.get_nodes())


def async_ble_available(hass: HomeAssistant) -> bool:
    """Whether the Matter server can commission a device over BLE.

    Either the server has its own Bluetooth adapter, or Home Assistant is acting
    as its BLE proxy (which is what lets ESPHome Bluetooth proxies commission a
    device sitting far away from the server).
    """
    client = async_get_client(hass)
    info = getattr(client, "server_info", None)
    if info is None:
        return False
    return bool(
        getattr(info, "bluetooth_enabled", False) or getattr(info, "ble_proxy_enabled", False)
    )


def async_credentials_state(hass: HomeAssistant) -> dict[str, bool]:
    """Report whether the server holds Wi-Fi and Thread credentials.

    Commissioning a wireless device that is not yet on the network fails without
    them, and the failure message from the SDK is not always obvious, so
    MatterBook checks up front and says so plainly.
    """
    client = async_get_client(hass)
    info = getattr(client, "server_info", None)
    if info is None:
        return {"wifi": False, "thread": False}
    return {
        "wifi": bool(getattr(info, "wifi_credentials_set", False)),
        "thread": bool(getattr(info, "thread_credentials_set", False)),
    }
