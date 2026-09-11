"""Shared entity base for MatterBook."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MatterBookCoordinator


class MatterBookEntity(CoordinatorEntity[MatterBookCoordinator]):
    """Base entity: every MatterBook entity belongs to one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MatterBookCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        assert coordinator.config_entry is not None
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="MatterBook",
            manufacturer="network-tools",
            entry_type=DeviceEntryType.SERVICE,
        )
