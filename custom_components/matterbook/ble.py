"""Discovering commissionable devices from Home Assistant's Bluetooth stack.

This is a second, independent discovery source next to the Matter server's own
`discover` command. Home Assistant already collects advertisements from every
adapter and every ESPHome Bluetooth proxy in the house, so reading them costs
nothing and covers devices that are only in range of a proxy in a far room.

The advertisement layout itself is decoded in :mod:`advertisement`.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .advertisement import parse_matter_service_data
from .const import BLE_MAX_ADVERTISEMENT_AGE, MATTER_BLE_SERVICE_UUID
from .matching import SOURCE_BLUETOOTH, DiscoveredDevice

_LOGGER = logging.getLogger(__name__)


def async_discover_ble_devices(hass: HomeAssistant) -> list[DiscoveredDevice]:
    """Return commissionable devices from Home Assistant's current advertisements.

    Reads the bluetooth component's cache rather than registering a callback: a
    periodic scan wants a snapshot, and the cache already holds everything every
    adapter and proxy has heard recently.
    """
    if "bluetooth" not in hass.config.components:
        return []

    from homeassistant.components import bluetooth  # noqa: PLC0415

    try:
        service_infos = bluetooth.async_discovered_service_info(hass, connectable=True)
    except Exception as err:  # noqa: BLE001 - a BLE problem must not fail the whole scan
        _LOGGER.debug("Could not read Bluetooth advertisements: %s", err)
        return []

    now = bluetooth.MONOTONIC_TIME()
    devices: list[DiscoveredDevice] = []
    for service_info in service_infos:
        data = service_info.service_data.get(MATTER_BLE_SERVICE_UUID)
        if data is None:
            continue
        if now - service_info.time > BLE_MAX_ADVERTISEMENT_AGE:
            continue
        advertisement = parse_matter_service_data(bytes(data))
        if advertisement is None:
            continue
        devices.append(
            DiscoveredDevice(
                source=SOURCE_BLUETOOTH,
                long_discriminator=advertisement.discriminator,
                vendor_id=advertisement.vendor_id,
                product_id=advertisement.product_id,
                name=service_info.name or None,
                address=service_info.address,
                rssi=service_info.rssi,
            )
        )
    return devices
