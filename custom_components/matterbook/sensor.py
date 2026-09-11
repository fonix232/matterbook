"""Sensors that show the state of the book and of the last scan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatterBookCoordinator, MatterBookData
from .entity import MatterBookEntity
from .store import STATUS_FAILED

if TYPE_CHECKING:
    from . import MatterBookConfigEntry


@dataclass(frozen=True, kw_only=True)
class MatterBookSensorDescription(SensorEntityDescription):
    """Describes a MatterBook sensor."""

    value_fn: Callable[[MatterBookData], int | datetime | None]
    attributes_fn: Callable[[MatterBookData], dict[str, Any]] | None = None


SENSORS: tuple[MatterBookSensorDescription, ...] = (
    MatterBookSensorDescription(
        key="entries",
        translation_key="entries",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.entries),
        # Rows are listed with their row number so the delete selector can be
        # used from the same card. Codes are masked: the passcode is a secret.
        attributes_fn=lambda data: {
            "rows": [
                {"row": index, **entry.redacted()}
                for index, entry in enumerate(data.entries, start=1)
            ]
        },
    ),
    MatterBookSensorDescription(
        key="pending",
        translation_key="pending",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.pending),
        attributes_fn=lambda data: {
            "failed": [
                entry.redacted() for entry in data.entries if entry.status == STATUS_FAILED
            ]
        },
    ),
    MatterBookSensorDescription(
        key="discovered",
        translation_key="discovered",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.discovered),
        attributes_fn=lambda data: {
            "devices": [device.describe() for device in data.discovered],
            "unknown": [device.describe() for device in data.report.unknown],
            "ambiguous": [
                {"entry_id": match.entry.id, **match.device.describe()}
                for match in data.report.ambiguous
            ],
        },
    ),
    MatterBookSensorDescription(
        key="last_scan",
        translation_key="last_scan",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_scan,
        attributes_fn=lambda data: {"last_error": data.last_error},
    ),
    MatterBookSensorDescription(
        key="last_paired",
        translation_key="last_paired",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_paired,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MatterBook sensors."""
    coordinator = entry.runtime_data
    async_add_entities(MatterBookSensor(coordinator, description) for description in SENSORS)


class MatterBookSensor(MatterBookEntity, SensorEntity):
    """A sensor over the coordinator's view of the book."""

    entity_description: MatterBookSensorDescription

    def __init__(
        self, coordinator: MatterBookCoordinator, description: MatterBookSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the sensor's detail, if it has any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
