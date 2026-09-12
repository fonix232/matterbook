"""WebSocket commands for the MatterBook panel.

The panel talks over the connection the frontend already holds, so there is no
second HTTP API and no second authentication scheme. Every command requires an
admin: the payloads describe devices that can be commissioned onto the fabric.

Setup codes are masked in everything sent here. The panel never receives a
passcode, so it cannot leak one into a screenshot or a browser cache.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Final

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_ALLOW_TRIALS,
    CONF_APPLY_METADATA,
    CONF_AUTO_PAIR,
    CONF_MAX_ATTEMPTS,
    CONF_PAIR_ON_ADD,
    CONF_PAIR_TIMEOUT,
    CONF_REQUIRE_EXACT_MATCH,
    CONF_RETRY_COOLDOWN,
    CONF_SCAN_INTERVAL,
    CONF_USE_BLUETOOTH,
    DEFAULT_ALLOW_TRIALS,
    DEFAULT_APPLY_METADATA,
    DEFAULT_AUTO_PAIR,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_PAIR_ON_ADD,
    DEFAULT_PAIR_TIMEOUT,
    DEFAULT_REQUIRE_EXACT_MATCH,
    DEFAULT_RETRY_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_BLUETOOTH,
    DOMAIN,
)
from .coordinator import MatterBookCoordinator
from .http import async_signed_label_url, async_signed_qr_url
from .labels import MAX_BYTES, LabelError
from .matching import DiscoveredDevice
from .matter_link import MatterUnavailable
from .pairing_code import InvalidSetupCode
from .qr import qr_payload
from .store import MatterBookEntry, MatterBookError

_LOGGER = logging.getLogger(__name__)

TYPE: Final = "type"

# Long enough for someone to walk to the device and see it; short enough that a
# forgotten click stops being a blinking light in a bedroom.
IDENTIFY_SECONDS: Final = 15


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
    websocket_api.async_register_command(hass, websocket_get_options)
    websocket_api.async_register_command(hass, websocket_set_options)
    websocket_api.async_register_command(hass, websocket_reveal)
    websocket_api.async_register_command(hass, websocket_identify)
    websocket_api.async_register_command(hass, websocket_set_label)


@callback
def _coordinator(hass: HomeAssistant) -> MatterBookCoordinator | None:
    """Return the MatterBook coordinator, if the integration is loaded."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        return None
    return entries[0].runtime_data  # type: ignore[no-any-return]


@callback
def _state_payload(
    coordinator: MatterBookCoordinator, refresh_token_id: str | None
) -> dict[str, Any]:
    """Serialise everything the panel renders.

    The token belongs to the connection asking, and is what the label URLs are
    signed with — see `async_signed_qr_url`.
    """
    data = coordinator.data
    report = data.report
    claimed = {match.device.key for match in report.matches} | {
        match.device.key for match in report.ambiguous
    }

    return {
        "entries": [
            _entry_payload(coordinator.hass, entry, refresh_token_id)
            for entry in data.entries
        ],
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


@callback
def _entry_payload(
    hass: HomeAssistant, entry: MatterBookEntry, refresh_token_id: str | None
) -> dict[str, Any]:
    """Describe one row for the panel, with a link to its rendered label.

    The URL is signed because an `<img>` tag cannot carry an authorisation
    header. Rows whose code is not a QR payload get `None` — see qr.py — and so
    does every row on a connection with no refresh token to sign as, which is a
    panel without label pictures rather than a panel that fails.
    """
    payload = entry.redacted()
    payload["qr_url"] = None
    payload["label_url"] = None
    if refresh_token_id is None:
        return payload

    if qr_payload(entry) is not None:
        payload["qr_url"] = async_signed_qr_url(
            hass, entry.id, refresh_token_id, entry.code
        )
    if entry.label_image:
        payload["label_url"] = async_signed_label_url(
            hass, entry.id, refresh_token_id, entry.label_image
        )
    return payload


OPTION_DEFAULTS: Final = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_AUTO_PAIR: DEFAULT_AUTO_PAIR,
    CONF_ALLOW_TRIALS: DEFAULT_ALLOW_TRIALS,
    CONF_PAIR_ON_ADD: DEFAULT_PAIR_ON_ADD,
    CONF_REQUIRE_EXACT_MATCH: DEFAULT_REQUIRE_EXACT_MATCH,
    CONF_USE_BLUETOOTH: DEFAULT_USE_BLUETOOTH,
    CONF_APPLY_METADATA: DEFAULT_APPLY_METADATA,
    CONF_PAIR_TIMEOUT: DEFAULT_PAIR_TIMEOUT,
    CONF_MAX_ATTEMPTS: DEFAULT_MAX_ATTEMPTS,
    CONF_RETRY_COOLDOWN: DEFAULT_RETRY_COOLDOWN,
}


def _refresh_token_id(connection: websocket_api.ActiveConnection) -> str | None:
    """Return the refresh token behind this connection, if it has one.

    Not every connection does — the Supervisor's, for one — and a connection
    without a token cannot be given signed URLs. That costs the label pictures
    and nothing else, so it is reported as absence rather than raised.
    """
    return connection.refresh_token_id


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

    # Captured here because the pushes below run from a coordinator callback,
    # where there is no connection in scope for Home Assistant to infer it from.
    refresh_token_id = _refresh_token_id(connection)

    @callback
    def _forward() -> None:
        connection.send_message(
            websocket_api.event_message(
                msg["id"], _state_payload(coordinator, refresh_token_id)
            )
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
    connection.send_result(
        msg["id"], _state_payload(coordinator, _refresh_token_id(connection))
    )


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
        vol.Optional("replace", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_set_code(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Set a row's code: fill in an imported row, or correct a wrong one.

    Replacing an existing code has to be asked for, so a mistyped entry id
    cannot quietly repoint a row at a different device.
    """
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    try:
        entry = await coordinator.async_set_code(
            msg["entry_id"], msg["code"], replace=msg["replace"]
        )
    except (InvalidSetupCode, MatterBookError) as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return

    connection.send_result(msg["id"], entry.redacted())


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required(TYPE): "matterbook/options"})
@callback
def websocket_get_options(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the current settings, with defaults filled in."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    assert coordinator.config_entry is not None
    options = coordinator.config_entry.options
    connection.send_result(
        msg["id"], {key: options.get(key, default) for key, default in OPTION_DEFAULTS.items()}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/set_options",
        vol.Required("options"): vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL): vol.All(int, vol.Range(min=30, max=86400)),
                vol.Optional(CONF_AUTO_PAIR): bool,
                vol.Optional(CONF_ALLOW_TRIALS): bool,
                vol.Optional(CONF_PAIR_ON_ADD): bool,
                vol.Optional(CONF_REQUIRE_EXACT_MATCH): bool,
                vol.Optional(CONF_USE_BLUETOOTH): bool,
                vol.Optional(CONF_APPLY_METADATA): bool,
                vol.Optional(CONF_PAIR_TIMEOUT): vol.All(int, vol.Range(min=30, max=900)),
                vol.Optional(CONF_MAX_ATTEMPTS): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional(CONF_RETRY_COOLDOWN): vol.All(int, vol.Range(min=60, max=86400)),
            }
        ),
    }
)
@websocket_api.async_response
async def websocket_set_options(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save settings.

    Updating the entry's options reloads the integration, which is what makes a
    new scan interval take effect — so this deliberately does not try to apply
    them piecemeal.
    """
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    entry = coordinator.config_entry
    assert entry is not None
    hass.config_entries.async_update_entry(entry, options={**entry.options, **msg["options"]})
    connection.send_result(msg["id"], {**OPTION_DEFAULTS, **entry.options, **msg["options"]})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required(TYPE): "matterbook/reveal", vol.Required("entry_id"): str}
)
@callback
def websocket_reveal(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one row's setup code, unmasked.

    The deliberate exception to masking everything else. It is needed for the
    rows the panel cannot show a picture of — a manual pairing code and a bare
    passcode are digits, not QR payloads, so there is no label to scan off the
    screen and reading the number out is the only way to give it to another
    controller's app.

    Asking is logged. A book of passcodes should be able to say when one was
    taken out of it.
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

    _LOGGER.info(
        "Setup code for MatterBook entry %s (%s) revealed to %s",
        entry.id,
        entry.name or "unnamed",
        connection.user.name,
    )
    connection.send_result(msg["id"], {"entry_id": entry.id, "code": entry.code})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required(TYPE): "matterbook/identify", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def websocket_identify(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Make a paired row's device blink, so it can be told from its twin."""
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

    try:
        await coordinator.async_identify(entry, seconds=IDENTIFY_SECONDS)
    except MatterUnavailable as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return

    connection.send_result(msg["id"], {"seconds": IDENTIFY_SECONDS})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required(TYPE): "matterbook/set_label",
        vol.Required("entry_id"): str,
        # Base64 because a WebSocket command is JSON. `None` clears the label,
        # which is why this is one command rather than an upload and a delete.
        vol.Required("image"): vol.Any(None, vol.All(str, vol.Length(max=MAX_BYTES * 2))),
    }
)
@websocket_api.async_response
async def websocket_set_label(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Store a photograph of a row's label, or clear the one it has."""
    coordinator = _require_coordinator(hass, connection, msg)
    if coordinator is None:
        return

    encoded = msg["image"]
    data: bytes | None = None
    if encoded is not None:
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as err:
            connection.send_error(
                msg["id"], websocket_api.ERR_INVALID_FORMAT, f"That was not base64: {err}"
            )
            return

    try:
        entry = await coordinator.async_set_label(msg["entry_id"], data)
    except LabelError as err:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err))
        return
    except MatterBookError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return

    connection.send_result(msg["id"], _entry_payload(hass, entry, _refresh_token_id(connection)))
