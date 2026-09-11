"""Text entities that make up the "add an entry" form."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import MatterBookEntity

if TYPE_CHECKING:
    from . import MatterBookConfigEntry
    from .coordinator import MatterBookCoordinator

# The staging fields for a new row, and their length limits. The setup code is
# the only one the "add entry" button insists on.
FIELDS: tuple[tuple[str, int], ...] = (
    ("new_entry_code", 255),
    ("new_entry_name", 64),
    ("new_entry_area", 64),
    ("new_entry_notes", 128),
    ("new_entry_serial_number", 64),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook text entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        MatterBookTextField(coordinator, key, max_length) for key, max_length in FIELDS
    )


class MatterBookTextField(MatterBookEntity, TextEntity, RestoreEntity):
    """One staging field for the next MatterBook row.

    The value lives on the coordinator rather than on the entity, so the button
    that files the row can read and clear it without having to guess entity ids.
    """

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0

    def __init__(self, coordinator: MatterBookCoordinator, key: str, max_length: int) -> None:
        """Initialize the field."""
        super().__init__(coordinator, key)
        self._key = key
        self._attr_native_max = max_length

    @property
    def native_value(self) -> str:
        """Return what is currently staged for this field."""
        return self.coordinator.staging.get(self._key, "")

    async def async_added_to_hass(self) -> None:
        """Restore what was typed before the restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if (
            last_state is not None
            and last_state.state not in ("unknown", "unavailable")
            and not self.coordinator.staging.get(self._key)
        ):
            self.coordinator.staging[self._key] = last_state.state[: self._attr_native_max]

    async def async_set_value(self, value: str) -> None:
        """Store the typed value."""
        self.coordinator.staging[self._key] = value
        self.async_write_ha_state()
