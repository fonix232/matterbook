"""MatterBook: a book of Matter setup codes, and auto-commissioning from it."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import (
    ATTR_AREA,
    ATTR_CODE,
    ATTR_ENTRY_ID,
    ATTR_NAME,
    ATTR_NOTES,
    ATTR_ROW,
    ATTR_SERIAL_NUMBER,
    CSV_FILENAME,
    DATA_DIRNAME,
    DOMAIN,
    LABEL_DIRNAME,
    SERVICE_ADD_ENTRY,
    SERVICE_IMPORT,
    SERVICE_PAIR,
    SERVICE_RELOAD_BOOK,
    SERVICE_REMOVE_ENTRY,
    SERVICE_SCAN,
    SERVICE_SET_CODE,
)
from .coordinator import MatterBookCoordinator
from .frontend import async_register_panel, async_unregister_panel
from .matter_link import MatterUnavailable
from .pairing_code import InvalidSetupCode
from .store import MatterBookError
from .websocket import async_register_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

type MatterBookConfigEntry = ConfigEntry[MatterBookCoordinator]

ADD_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): cv.string,
        vol.Optional(ATTR_NAME, default=""): cv.string,
        vol.Optional(ATTR_AREA, default=""): cv.string,
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional(ATTR_SERIAL_NUMBER, default=""): cv.string,
    }
)

REMOVE_ENTRY_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Optional(ATTR_ROW): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(ATTR_ENTRY_ID): cv.string,
        },
        cv.has_at_least_one_key(ATTR_ROW, ATTR_ENTRY_ID),
    )
)

SET_CODE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTRY_ID): cv.string, vol.Required(ATTR_CODE): cv.string}
)

PAIR_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Optional(ATTR_ROW): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(ATTR_ENTRY_ID): cv.string,
        },
        cv.has_at_least_one_key(ATTR_ROW, ATTR_ENTRY_ID),
    )
)


def data_dir(hass: HomeAssistant) -> Path:
    """Return MatterBook's directory: everything it owns lives here.

    Deliberately not configurable. One known location is worth more than the
    flexibility: it is the directory to back up, to keep out of git, and to copy
    when moving to a new install.
    """
    return Path(hass.config.path(DATA_DIRNAME))


def csv_path(hass: HomeAssistant) -> Path:
    """Return the path of the book."""
    return data_dir(hass) / CSV_FILENAME


def label_dir(hass: HomeAssistant) -> Path:
    """Return the directory holding scanned label images."""
    return data_dir(hass) / LABEL_DIRNAME


async def async_setup_entry(hass: HomeAssistant, entry: MatterBookConfigEntry) -> bool:
    """Set up MatterBook from a config entry."""
    book = csv_path(hass)
    coordinator = MatterBookCoordinator(hass, entry, book, label_dir(hass))
    entry.runtime_data = coordinator

    _async_remove_retired_entities(hass, entry)
    await coordinator.async_load_book()
    _LOGGER.debug("MatterBook loaded %s entries from %s", len(coordinator.data.entries), book)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    async_register_commands(hass)
    await async_register_panel(hass, book)

    # The first scan runs in the background: discovery waits on the Matter server
    # and on BLE, and neither should hold up Home Assistant's startup. Later scans
    # are scheduled by the coordinator itself, once the entities are listening.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), name=f"{DOMAIN}_first_refresh"
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


@callback
def _async_remove_retired_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the entities that the panel replaced.

    0.1.0 shipped text fields, a row-number selector and add/delete buttons to
    stand in for a user interface. The panel does that job now, and entities
    left behind by a removed platform linger in the registry as unavailable.
    """
    registry = er.async_get(hass)
    retired = (
        "new_entry_code",
        "new_entry_name",
        "new_entry_area",
        "new_entry_notes",
        "new_entry_serial_number",
        "delete_row",
        "add_entry",
        "delete_entry",
    )
    for key in retired:
        unique_id = f"{entry.entry_id}_{key}"
        for domain in (Platform.TEXT, Platform.NUMBER, Platform.BUTTON):
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id is not None:
                _LOGGER.debug("Removing retired MatterBook entity %s", entity_id)
                registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: MatterBookConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and len(hass.config_entries.async_entries(DOMAIN)) == 1:
        # Registering a panel that already exists raises, so a reload has to take
        # the old one down first.
        async_unregister_panel(hass)
        for service in (
            SERVICE_ADD_ENTRY,
            SERVICE_REMOVE_ENTRY,
            SERVICE_SCAN,
            SERVICE_PAIR,
            SERVICE_RELOAD_BOOK,
            SERVICE_IMPORT,
            SERVICE_SET_CODE,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: MatterBookConfigEntry) -> None:
    """Reload when the options change, so a new scan interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinator(hass: HomeAssistant) -> MatterBookCoordinator:
    """Return the single MatterBook coordinator."""
    entries: list[MatterBookConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("MatterBook is not set up")
    return entries[0].runtime_data


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the MatterBook actions, once for all config entries."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_ENTRY):
        return

    async def async_add_entry(call: ServiceCall) -> ServiceResponse:
        """Add a row to the MatterBook."""
        coordinator = _coordinator(hass)
        try:
            entry = await coordinator.async_add_entry(
                code=call.data[ATTR_CODE],
                name=call.data.get(ATTR_NAME, ""),
                area=call.data.get(ATTR_AREA, ""),
                notes=call.data.get(ATTR_NOTES, ""),
                serial_number=call.data.get(ATTR_SERIAL_NUMBER, ""),
            )
        except InvalidSetupCode as err:
            raise ServiceValidationError(f"Not a Matter setup code: {err}") from err
        except MatterBookError as err:
            raise ServiceValidationError(str(err)) from err
        return {"entry": entry.redacted()}

    async def async_remove_entry(call: ServiceCall) -> ServiceResponse:
        """Remove a row from the MatterBook."""
        coordinator = _coordinator(hass)
        try:
            removed = await coordinator.async_remove_entry(
                row=call.data.get(ATTR_ROW), entry_id=call.data.get(ATTR_ENTRY_ID)
            )
        except MatterBookError as err:
            raise ServiceValidationError(str(err)) from err
        return {"entry": removed.redacted()}

    async def async_scan(call: ServiceCall) -> ServiceResponse:
        """Scan for commissionable devices and pair what the book knows."""
        coordinator = _coordinator(hass)
        data = await coordinator.async_scan()
        return {
            "discovered": [device.describe() for device in data.discovered],
            "matched": [
                {"entry_id": match.entry.id, "name": match.entry.name, "device": match.device.key}
                for match in data.report.matches
            ],
            "ambiguous": [
                {"entry_id": match.entry.id, "device": match.device.key}
                for match in data.report.ambiguous
            ],
        }

    async def async_pair(call: ServiceCall) -> ServiceResponse:
        """Commission one specific row now, whether or not it was seen in a scan."""
        coordinator = _coordinator(hass)
        entries = await coordinator.async_load_book()
        entry_id = call.data.get(ATTR_ENTRY_ID)
        row = call.data.get(ATTR_ROW)

        if entry_id is not None:
            match = next((item for item in entries if item.id == entry_id), None)
            if match is None:
                raise ServiceValidationError(f"No MatterBook entry with id {entry_id}")
        else:
            if not 1 <= row <= len(entries):
                raise ServiceValidationError(
                    f"Row {row} is out of range (the book has {len(entries)} rows)"
                )
            match = entries[row - 1]

        node_id = await coordinator.async_pair(match)
        if node_id is None:
            raise HomeAssistantError(
                f"Commissioning {match.name or match.id} failed; see the log for the reason"
            )
        return {"node_id": node_id, "entry_id": match.id}

    async def async_import_from_matter(_call: ServiceCall) -> ServiceResponse:
        """Snapshot the devices already commissioned onto this fabric.

        Their setup codes cannot come along — a commissioned device does not hold
        its passcode — so this produces rows that know what each device is and
        where it lives, waiting for their stickers.
        """
        coordinator = _coordinator(hass)
        try:
            summary = await coordinator.async_import_from_matter()
        except MatterUnavailable as err:
            raise ServiceValidationError(str(err)) from err
        return dict(summary)

    async def async_set_code(call: ServiceCall) -> ServiceResponse:
        """Give an imported entry its setup code."""
        coordinator = _coordinator(hass)
        try:
            entry = await coordinator.async_set_code(call.data[ATTR_ENTRY_ID], call.data[ATTR_CODE])
        except InvalidSetupCode as err:
            raise ServiceValidationError(f"Not a Matter setup code: {err}") from err
        except MatterBookError as err:
            raise ServiceValidationError(str(err)) from err
        return {"entry": entry.redacted()}

    async def async_reload_book(_call: ServiceCall) -> None:
        """Re-read the MatterBook file from disk."""
        await _coordinator(hass).async_load_book()

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_ENTRY,
        async_add_entry,
        schema=ADD_ENTRY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_ENTRY,
        async_remove_entry,
        schema=REMOVE_ENTRY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SCAN, async_scan, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PAIR,
        async_pair,
        schema=PAIR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT,
        async_import_from_matter,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CODE,
        async_set_code,
        schema=SET_CODE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_RELOAD_BOOK, async_reload_book)
