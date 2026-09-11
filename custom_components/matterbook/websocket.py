"""WebSocket commands for the MatterBook panel.

The panel talks over the connection the frontend already holds, so there is no
second HTTP API and no second authentication scheme. Every command requires an
admin: the payloads describe devices that can be commissioned onto the fabric.

Setup codes are masked in everything sent here. The panel never receives a
passcode, so it cannot leak one into a screenshot or a browser cache.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import MatterBookCoordinator
from .matching import DiscoveredDevice
from .matter_link import MatterUnavailable
from .pairing_code import InvalidSetupCode
from .store import MatterBookError

TYPE: Final = "type"


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the MatterBook WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_subscribe)
    websocket_api.async_register_command(hass, websocket_add)
    websocket_api.async_register_command(hass, websocket_remove)
    websocket_api.async_register_command(hass, websocket_update)
    websocket_api.async_register_command(hass, websocket_scan)
    websocket_api.async_register_command(hass, websocket_pair)
    websocket_api.async_register_command(hass, websocket_import)
    websocket_api.async_register_command(hass, websocket_set_code)


@callback
def _coordinator(hass: HomeAssistant) -> MatterBookCoordinator | None:
    """Return the MatterBook coordinator, if the integration is loaded."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        return None
    return entries[0].runtime_data  # type: ignore[no-any-return]


@callback
def _state_payload(coordinator: MatterBookCoordinator) -> dict[str, Any]:
    """Serialise everything the panel renders."""
    data = coordinator.data
    report = data.report
    claimed = {match.device.key for match in report.matches} | {
        match.device.key for match in report.ambiguous
    }

    return {
        "entries": [entry.redacted() for entry in data.entries],
        "devices": [{"key": device.key, **device.describe()} for device in data.discovered],
        "matches": [
            {
                "entry_id": match.entry.id,
                "device_key": match.device.key,
                "confidence": match.confidence,
            }
            for match in report.matches
        ],
        "ambiguous": [
            {"entry_id": match.entry.id, "device_key": match.device.key}
            for match in report.ambiguous
        ],
        "trials": [
            {
                "entry_id": trial.entry.id,
                "device_key": trial.device.key,
                "reason": trial.reason,
            }
            for trial in report.trials
        ],
        "unknown_device_keys": [
            device.key for device in data.discovered if device.key not in claimed
        ],
        "auto_pair_enabled": coordinator.auto_pair_enabled,
        "last_scan": data.last_scan.isoformat() if data.last_scan else None,
        "last_paired": data.last_paired.isoformat() if data.last_paired else None,
        "last_error": data.last_error,
    }


def _device_for_key(coordinator: MatterBookCoordinator, key: str | None) -> DiscoveredDevice | None:
    """Return the discovered device the panel named, if it is still advertising."""
    if key is None:
        return None
    return next((device for device in coordinator.data.discovered if device.key == key), None)


def _require_coordinator(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> MatterBookCoordinator | None:
    """Return the coordinator, answering the caller if there is none."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "MatterBook is not set up"
        )
        return None
    return coordinator


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required(TYPE): "matterbook/subscribe"})
@callback
def websocket_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Push the whole MatterBook state, now and on every change.

    The coordinator already tells its listeners when a scan finishes or a row
    changes, so this turns that into a live view and saves the panel from
    polling.
    """
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    @callback
    def _forward() -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], _state_payload(coordinator))
        )

    connection.subscriptions[msg["id"]] = coordinator.async_add_listener(_forward)
    connection.send_result(msg["id"])
    _forward()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/add",
        vol.Required("code"): str,
        vol.Optional("name", default=""): str,
        vol.Optional("area", default=""): str,
        vol.Optional("notes", default=""): str,
        vol.Optional("serial_number", default=""): str,
    }
)
@websocket_api.async_response
async def websocket_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add a row to the book."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    try:
        entry = await coordinator.async_add_entry(
            code=msg["code"],
            name=msg["name"],
            area=msg["area"],
            notes=msg["notes"],
            serial_number=msg["serial_number"],
        )
    except (InvalidSetupCode, MatterBookError) as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return

    connection.send_result(msg["id"], entry.redacted())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required(TYPE): "matterbook/remove", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def websocket_remove(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove a row from the book."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    try:
        removed = await coordinator.async_remove_entry(entry_id=msg["entry_id"])
    except MatterBookError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return

    connection.send_result(msg["id"], removed.redacted())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/update",
        vol.Required("entry_id"): str,
        vol.Optional("name"): str,
        vol.Optional("area"): str,
        vol.Optional("notes"): str,
        vol.Optional("enabled"): bool,
    }
)
@websocket_api.async_response
async def websocket_update(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Edit a row's description. The code itself is never editable."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    changes = {key: msg[key] for key in ("name", "area", "notes", "enabled") if key in msg}
    try:
        entry = await coordinator.async_update_entry(msg["entry_id"], **changes)
    except MatterBookError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return

    connection.send_result(msg["id"], entry.redacted())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required(TYPE): "matterbook/scan"})
@websocket_api.async_response
async def websocket_scan(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Scan now instead of waiting for the next sweep."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    await coordinator.async_scan_only()
    coordinator.async_update_listeners()
    connection.send_result(msg["id"], _state_payload(coordinator))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/pair",
        vol.Required("entry_id"): str,
        vol.Optional("device_key"): str,
    }
)
@websocket_api.async_response
async def websocket_pair(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Commission one row, optionally against one named device.

    Naming a device is how the panel resolves an ambiguity: the human supplies
    the answer the matcher refused to guess, and pairing then takes its ordinary
    path, with that device's discriminator folded into the code so the attempt is
    addressed exactly at it.
    """
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    entry = next(
        (item for item in coordinator.data.entries if item.id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"No MatterBook entry with id {msg['entry_id']}",
        )
        return

    device_key = msg.get("device_key")
    device = _device_for_key(coordinator, device_key)
    if device_key is not None and device is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            "That device is no longer advertising; scan again and retry",
        )
        return

    node_id = await coordinator.async_pair(entry, device)
    connection.send_result(msg["id"], {"node_id": node_id})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required(TYPE): "matterbook/import"})
@websocket_api.async_response
async def websocket_import(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Snapshot the devices already commissioned onto this fabric.

    Their codes cannot come with them, so the rows this creates are inventory
    waiting for their stickers.
    """
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    try:
        summary = await coordinator.async_import_from_matter()
    except MatterUnavailable as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return

    connection.send_result(msg["id"], summary)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/set_code",
        vol.Required("entry_id"): str,
        vol.Required("code"): str,
    }
)
@websocket_api.async_response
async def websocket_set_code(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Give an imported row its setup code, once its sticker turns up."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    try:
        entry = await coordinator.async_set_code(msg["entry_id"], msg["code"])
    except (InvalidSetupCode, MatterBookError) as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return

    connection.send_result(msg["id"], entry.redacted())
