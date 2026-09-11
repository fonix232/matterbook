"""The auto-pairing arm/disarm switch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import MatterBookEntity

if TYPE_CHECKING:
    from . import MatterBookConfigEntry
    from .coordinator import MatterBookCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook switch."""
    async_add_entities([MatterBookAutoPairSwitch(entry.runtime_data)])


class MatterBookAutoPairSwitch(MatterBookEntity, SwitchEntity, RestoreEntity):
    """Whether a scan is allowed to commission the devices it recognises.

    Off still scans and still reports what it found; it just does not act, which
    is the safe posture while filling the book or during a house move.
    """

    def __init__(self, coordinator: MatterBookCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "auto_pairing")

    @property
    def is_on(self) -> bool:
        """Return whether auto-pairing is armed."""
        return self.coordinator.auto_pair_enabled

    async def async_added_to_hass(self) -> None:
        """Restore the armed state across restarts."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self.coordinator.async_set_auto_pair(last_state.state == "on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm auto-pairing."""
        self.coordinator.async_set_auto_pair(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm auto-pairing."""
        self.coordinator.async_set_auto_pair(False)
