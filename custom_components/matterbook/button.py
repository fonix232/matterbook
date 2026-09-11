"""Buttons: file a new row, delete a row, scan now."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import MatterBookEntity
from .matter_link import MatterUnavailable
from .number import DELETE_ROW_KEY
from .pairing_code import InvalidSetupCode
from .store import MatterBookError

if TYPE_CHECKING:
    from . import MatterBookConfigEntry
    from .coordinator import MatterBookCoordinator

_LOGGER = logging.getLogger(__name__)

STAGING_KEYS = ("new_entry_code", "new_entry_name", "new_entry_area", "new_entry_notes")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MatterBookAddEntryButton(coordinator),
            MatterBookDeleteEntryButton(coordinator),
            MatterBookScanButton(coordinator),
            MatterBookImportButton(coordinator),
        ]
    )


class MatterBookAddEntryButton(MatterBookEntity, ButtonEntity):
    """Append the staged text fields to the MatterBook as a new row."""

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "add_entry")

    async def async_press(self) -> None:
        """File the staged fields, then clear them."""
        staging = self.coordinator.staging
        code = (staging.get("new_entry_code") or "").strip()
        if not code:
            raise ServiceValidationError(
                "Fill in the setup code field before adding a MatterBook entry"
            )

        try:
            entry = await self.coordinator.async_add_entry(
                code=code,
                name=(staging.get("new_entry_name") or "").strip(),
                area=(staging.get("new_entry_area") or "").strip(),
                notes=(staging.get("new_entry_notes") or "").strip(),
                serial_number=(staging.get("new_entry_serial_number") or "").strip(),
            )
        except InvalidSetupCode as err:
            raise ServiceValidationError(f"Not a Matter setup code: {err}") from err
        except MatterBookError as err:
            raise ServiceValidationError(str(err)) from err

        _LOGGER.info("Added MatterBook entry %s (%s)", entry.id, entry.name or "unnamed")
        for key in (*STAGING_KEYS, "new_entry_serial_number"):
            staging.pop(key, None)
        self.coordinator.async_update_listeners()


class MatterBookDeleteEntryButton(MatterBookEntity, ButtonEntity):
    """Delete the row the number entity points at."""

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "delete_entry")

    async def async_press(self) -> None:
        """Remove the selected row."""
        row = int(self.coordinator.staging.get(DELETE_ROW_KEY) or 1)
        try:
            removed = await self.coordinator.async_remove_entry(row=row)
        except MatterBookError as err:
            raise ServiceValidationError(str(err)) from err
        _LOGGER.info("Removed MatterBook row %s (%s)", row, removed.name or removed.id)


class MatterBookImportButton(MatterBookEntity, ButtonEntity):
    """Snapshot the devices already commissioned onto this fabric.

    Their setup codes cannot come with them — a commissioned device keeps a PASE
    verifier, not its passcode — so this fills the book with everything *except*
    the codes, and leaves a list of stickers to go and find.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "import_from_matter")

    async def async_press(self) -> None:
        """Run the import."""
        try:
            summary = await self.coordinator.async_import_from_matter()
        except MatterUnavailable as err:
            raise ServiceValidationError(str(err)) from err
        _LOGGER.info(
            "MatterBook import: %s devices found, %s added, %s already known",
            summary["found"],
            summary["imported"],
            summary["already_known"],
        )


class MatterBookScanButton(MatterBookEntity, ButtonEntity):
    """Scan for commissionable devices now, instead of waiting for the next sweep."""

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "scan_now")

    async def async_press(self) -> None:
        """Run a scan, pairing if the auto-pairing switch is on."""
        await self.coordinator.async_scan()
