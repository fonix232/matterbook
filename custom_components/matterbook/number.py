"""The row-number selector used by the "delete entry" button."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import MatterBookEntity

if TYPE_CHECKING:
    from . import MatterBookConfigEntry
    from .coordinator import MatterBookCoordinator

DELETE_ROW_KEY = "delete_row"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook number entities."""
    async_add_entities([MatterBookDeleteRow(entry.runtime_data)])


class MatterBookDeleteRow(MatterBookEntity, NumberEntity):
    """Which row the delete button will remove (1 is the first row in the file)."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 9999
    _attr_native_step = 1

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the selector."""
        super().__init__(coordinator, DELETE_ROW_KEY)

    @property
    def native_value(self) -> float:
        """Return the selected row number."""
        return float(self.coordinator.staging.get(DELETE_ROW_KEY) or 1)

    async def async_set_native_value(self, value: float) -> None:
        """Select a row number."""
        self.coordinator.staging[DELETE_ROW_KEY] = str(int(value))
        self.async_write_ha_state()
