"""Diagnostics for MatterBook.

Setup codes never leave this integration in full: a diagnostics download is
something people paste into issue trackers, and a Matter passcode is the whole
secret of the commissioning handshake.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from . import matter_link

if TYPE_CHECKING:
    from . import MatterBookConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MatterBookConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    return {
        "options": dict(entry.options),
        "csv_path": str(coordinator.csv_path),
        "auto_pair_enabled": coordinator.auto_pair_enabled,
        "matter": {
            "client_available": matter_link.async_get_client(hass) is not None,
            "ble_available": matter_link.async_ble_available(hass),
            "credentials": matter_link.async_credentials_state(hass),
        },
        "last_scan": data.last_scan.isoformat() if data.last_scan else None,
        "last_paired": data.last_paired.isoformat() if data.last_paired else None,
        "last_error": data.last_error,
        "entries": [entry_data.redacted() for entry_data in data.entries],
        "discovered": [device.describe() for device in data.discovered],
        "matches": [
            {
                "entry_id": match.entry.id,
                "device": match.device.key,
                "confidence": match.confidence,
            }
            for match in data.report.matches
        ],
        "ambiguous": [
            {"entry_id": match.entry.id, "device": match.device.key}
            for match in data.report.ambiguous
        ],
    }
