"""Buttons.

Adding and deleting rows lives in the panel now; what is left here is the pair
of actions worth having in an automation or on a dashboard card.
"""

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

if TYPE_CHECKING:
    from . import MatterBookConfigEntry
    from .coordinator import MatterBookCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MatterBookScanButton(coordinator),
            MatterBookImportButton(coordinator),
        ]
    )


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
