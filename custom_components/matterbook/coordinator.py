"""Periodic scanning and auto-pairing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import matter_link
from .ble import async_discover_ble_devices
from .const import (
    CONF_APPLY_METADATA,
    CONF_AUTO_PAIR,
    CONF_MAX_ATTEMPTS,
    CONF_PAIR_TIMEOUT,
    CONF_REQUIRE_EXACT_MATCH,
    CONF_RETRY_COOLDOWN,
    CONF_SCAN_INTERVAL,
    CONF_USE_BLUETOOTH,
    DEFAULT_APPLY_METADATA,
    DEFAULT_AUTO_PAIR,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_PAIR_TIMEOUT,
    DEFAULT_REQUIRE_EXACT_MATCH,
    DEFAULT_RETRY_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_BLUETOOTH,
    DOMAIN,
    EVENT_AMBIGUOUS,
    EVENT_DISCOVERED,
    EVENT_PAIR_FAILED,
    EVENT_PAIRED,
)
from .matching import SOURCE_MATTER_SERVER, DiscoveredDevice, Match, MatchReport, match_devices
from .store import (
    MatterBookEntry,
    add_entry,
    mark_failed,
    mark_paired,
    read_entries,
    remove_entry,
)

_LOGGER = logging.getLogger(__name__)

DISCOVERY_TIMEOUT = 30.0
METADATA_WAIT_SECONDS = 60
METADATA_POLL_SECONDS = 2


@dataclass(slots=True)
class MatterBookData:
    """What the coordinator publishes to its entities."""

    entries: list[MatterBookEntry] = field(default_factory=list)
    discovered: list[DiscoveredDevice] = field(default_factory=list)
    report: MatchReport = field(default_factory=MatchReport)
    last_scan: datetime | None = None
    last_paired: datetime | None = None
    last_error: str | None = None

    @property
    def pending(self) -> list[MatterBookEntry]:
        """Rows that still want a device."""
        return [entry for entry in self.entries if entry.is_pairable]


class MatterBookCoordinator(DataUpdateCoordinator[MatterBookData]):
    """Scans for commissionable devices and pairs the ones the book knows."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, csv_path: Path) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )
        self.csv_path = csv_path
        self.data = MatterBookData()
        self.staging: dict[str, str] = {}
        """What the text entities hold for the next row, and the delete row number."""
        self._pair_lock = asyncio.Lock()
        self._cooldowns: dict[str, datetime] = {}
        self._attempts: dict[str, int] = {}
        self._auto_pair_enabled = bool(entry.options.get(CONF_AUTO_PAIR, DEFAULT_AUTO_PAIR))

    # ----- options ---------------------------------------------------------

    def _option(self, key: str, default: Any) -> Any:
        assert self.config_entry is not None
        return self.config_entry.options.get(key, default)

    @property
    def auto_pair_enabled(self) -> bool:
        """Whether matched devices are paired automatically."""
        return self._auto_pair_enabled

    @callback
    def async_set_auto_pair(self, enabled: bool) -> None:
        """Turn auto-pairing on or off at runtime (the switch entity)."""
        self._auto_pair_enabled = enabled
        self.async_update_listeners()

    # ----- the book --------------------------------------------------------

    async def async_load_book(self) -> list[MatterBookEntry]:
        """Re-read the MatterBook from disk."""
        entries = await self.hass.async_add_executor_job(read_entries, self.csv_path)
        self.data.entries = entries
        self.async_update_listeners()
        return entries

    async def async_add_entry(self, **kwargs: Any) -> MatterBookEntry:
        """Add a row, then re-read the book."""
        entry = await self.hass.async_add_executor_job(lambda: add_entry(self.csv_path, **kwargs))
        await self.async_load_book()
        return entry

    async def async_remove_entry(
        self, *, row: int | None = None, entry_id: str | None = None
    ) -> MatterBookEntry:
        """Remove a row, then re-read the book."""
        removed = await self.hass.async_add_executor_job(
            lambda: remove_entry(self.csv_path, row=row, entry_id=entry_id)
        )
        await self.async_load_book()
        return removed

    # ----- scanning --------------------------------------------------------

    async def _async_update_data(self) -> MatterBookData:
        """Run one scheduled scan, and pair in the background when armed.

        Pairing is not awaited here: a commissioning round trip can take minutes,
        and the update loop should not be held open for it.
        """
        data = await self.async_scan_only()
        if self.auto_pair_enabled and data.report.matches:
            assert self.config_entry is not None
            self.config_entry.async_create_background_task(
                self.hass,
                self._async_pair_matches(list(data.report.matches)),
                name=f"{DOMAIN}_auto_pair",
            )
        return data

    async def async_scan_only(self) -> MatterBookData:
        """Scan for commissionable devices and match them against the book."""
        entries = await self.async_load_book()
        devices = await self._async_discover()

        report = match_devices(
            [entry for entry in entries if entry.is_pairable],
            devices,
            require_exact=bool(
                self._option(CONF_REQUIRE_EXACT_MATCH, DEFAULT_REQUIRE_EXACT_MATCH)
            ),
        )

        self.data.discovered = devices
        self.data.report = report
        self.data.last_scan = dt_util.utcnow()

        for device in report.unknown:
            self.hass.bus.async_fire(EVENT_DISCOVERED, device.describe())
        for match in report.ambiguous:
            _LOGGER.warning(
                "Not pairing %s: its short discriminator matches more than one MatterBook "
                "entry or device. Store the QR payload rather than the manual pairing code "
                "to make this unambiguous",
                match.device.key,
            )
            self.hass.bus.async_fire(
                EVENT_AMBIGUOUS,
                {"entry_id": match.entry.id, "name": match.entry.name, **match.device.describe()},
            )

        return self.data

    async def async_scan(self, *, pair: bool | None = None) -> MatterBookData:
        """Scan, and pair the matches, waiting for the result.

        Args:
            pair: ``None`` follows the auto-pairing switch, ``True`` forces a
                pairing pass, ``False`` scans only.
        """
        data = await self.async_scan_only()
        self.async_update_listeners()
        should_pair = self.auto_pair_enabled if pair is None else pair
        if should_pair and data.report.matches:
            await self._async_pair_matches(list(data.report.matches))
        return self.data

    async def _async_discover(self) -> list[DiscoveredDevice]:
        """Collect commissionable devices from every source we have."""
        devices: list[DiscoveredDevice] = []
        self.data.last_error = None

        try:
            nodes = await matter_link.async_discover(self.hass, DISCOVERY_TIMEOUT)
        except matter_link.MatterUnavailable as err:
            self.data.last_error = str(err)
            _LOGGER.debug("Matter server discovery unavailable: %s", err)
        else:
            devices.extend(
                DiscoveredDevice(
                    source=SOURCE_MATTER_SERVER,
                    long_discriminator=node.long_discriminator,
                    vendor_id=node.vendor_id or None,
                    product_id=node.product_id or None,
                    instance_name=node.instance_name,
                    name=node.device_name,
                    address=(node.addresses[0] if node.addresses else None),
                    addresses=tuple(node.addresses or ()),
                    commissioning_mode=node.commissioning_mode,
                )
                for node in nodes
            )

        if self._option(CONF_USE_BLUETOOTH, DEFAULT_USE_BLUETOOTH):
            devices.extend(async_discover_ble_devices(self.hass))

        return _deduplicate(devices)

    # ----- pairing ---------------------------------------------------------

    async def _async_pair_matches(self, matches: list[Match]) -> None:
        """Pair matched devices one at a time.

        The Matter server commissions one device at a time and a round trip can
        take a minute or more, so this is deliberately serial.
        """
        for match in matches:
            if not self._may_attempt(match.entry):
                continue
            await self.async_pair(match.entry, match.device)

    def _may_attempt(self, entry: MatterBookEntry) -> bool:
        """Whether a row is out of cooldown and under its attempt limit."""
        max_attempts = int(self._option(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS))
        if self._attempts.get(entry.id, 0) >= max_attempts:
            return False
        cooldown_until = self._cooldowns.get(entry.id)
        return not (cooldown_until and dt_util.utcnow() < cooldown_until)

    async def async_pair(
        self, entry: MatterBookEntry, device: DiscoveredDevice | None = None
    ) -> int | None:
        """Commission one MatterBook row. Returns the node id, or ``None`` on failure."""
        async with self._pair_lock:
            attempt = self._attempts.get(entry.id, 0) + 1
            self._attempts[entry.id] = attempt
            network_only = self._network_only_for(device)

            _LOGGER.info(
                "Commissioning MatterBook entry %s (%s), attempt %s, network_only=%s",
                entry.id,
                entry.name or "unnamed",
                attempt,
                network_only,
            )
            try:
                node = await matter_link.async_commission(
                    self.hass,
                    entry.code,
                    network_only=network_only,
                    timeout=float(self._option(CONF_PAIR_TIMEOUT, DEFAULT_PAIR_TIMEOUT)),
                )
            except (matter_link.CommissioningFailed, matter_link.MatterUnavailable) as err:
                await self._async_record_failure(entry, str(err), attempt, device)
                return None

            await self.hass.async_add_executor_job(
                mark_paired, self.csv_path, entry.id, node.node_id
            )
            self._cooldowns.pop(entry.id, None)
            self._attempts.pop(entry.id, None)
            self.data.last_paired = dt_util.utcnow()
            _LOGGER.info(
                "Commissioned MatterBook entry %s as Matter node %s", entry.id, node.node_id
            )
            self.hass.bus.async_fire(
                EVENT_PAIRED,
                {
                    "entry_id": entry.id,
                    "name": entry.name,
                    "node_id": node.node_id,
                    **(device.describe() if device else {}),
                },
            )

            if self._option(CONF_APPLY_METADATA, DEFAULT_APPLY_METADATA):
                assert self.config_entry is not None
                self.config_entry.async_create_background_task(
                    self.hass,
                    self._async_apply_metadata(entry, node.node_id),
                    name=f"{DOMAIN}_apply_metadata",
                )

            await self.async_load_book()
            return node.node_id

    def _network_only_for(self, device: DiscoveredDevice | None) -> bool:
        """Decide whether to restrict commissioning to the IP network.

        A device the Matter server already sees on the network is commissioned
        over IP. Anything else needs BLE, which is only worth attempting when the
        server has Bluetooth of its own or Home Assistant is proxying BLE for it.
        """
        if device is not None and device.on_ip_network:
            return True
        return not matter_link.async_ble_available(self.hass)

    async def _async_record_failure(
        self, entry: MatterBookEntry, error: str, attempt: int, device: DiscoveredDevice | None
    ) -> None:
        """Log, store and announce a failed attempt, and put the row in cooldown."""
        cooldown = int(self._option(CONF_RETRY_COOLDOWN, DEFAULT_RETRY_COOLDOWN))
        # Back off exponentially so a device that is switched off, out of range or
        # already commissioned elsewhere is not retried on every single scan.
        backoff = min(cooldown * (2 ** (attempt - 1)), cooldown * 8)
        self._cooldowns[entry.id] = dt_util.utcnow() + timedelta(seconds=backoff)

        credentials = matter_link.async_credentials_state(self.hass)
        hint = ""
        if not credentials["wifi"] and not credentials["thread"]:
            hint = (
                " The Matter server holds neither Wi-Fi nor Thread credentials, which a "
                "wireless device needs before it can join the network."
            )
        _LOGGER.warning(
            "Commissioning MatterBook entry %s failed (attempt %s): %s.%s Retrying after %ss",
            entry.id,
            attempt,
            error,
            hint,
            backoff,
        )
        await self.hass.async_add_executor_job(mark_failed, self.csv_path, entry.id, error, attempt)
        self.hass.bus.async_fire(
            EVENT_PAIR_FAILED,
            {
                "entry_id": entry.id,
                "name": entry.name,
                "error": error,
                "attempt": attempt,
                **(device.describe() if device else {}),
            },
        )
        await self.async_load_book()

    async def _async_apply_metadata(self, entry: MatterBookEntry, node_id: int) -> None:
        """Name the new device and put it in its area, as the book says.

        The Matter integration creates the device registry entry asynchronously
        after commissioning, so this waits briefly for it to appear.
        """
        if not entry.name and not entry.area:
            return

        try:
            from homeassistant.components.matter.helpers import (  # noqa: PLC0415
                get_node_device_identifier,
            )
        except ImportError:
            _LOGGER.debug("Matter helpers unavailable; not applying name/area")
            return

        client = matter_link.async_get_client(self.hass)
        server_info = getattr(client, "server_info", None)
        if server_info is None:
            return
        identifier = get_node_device_identifier(server_info, node_id)

        device_registry = dr.async_get(self.hass)
        device = None
        for _ in range(METADATA_WAIT_SECONDS // METADATA_POLL_SECONDS):
            device = device_registry.async_get_device(identifiers={identifier})
            if device is not None:
                break
            await asyncio.sleep(METADATA_POLL_SECONDS)
        if device is None:
            _LOGGER.debug("Device for node %s did not appear; not applying name/area", node_id)
            return

        updates: dict[str, Any] = {}
        if entry.name:
            updates["name_by_user"] = entry.name
        if entry.area:
            area_registry = ar.async_get(self.hass)
            area = area_registry.async_get_area_by_name(entry.area)
            if area is None:
                area = area_registry.async_create(entry.area)
            updates["area_id"] = area.id
        if updates:
            device_registry.async_update_device(device.id, **updates)
            _LOGGER.debug("Applied MatterBook metadata to device %s: %s", device.id, updates)


def _deduplicate(devices: list[DiscoveredDevice]) -> list[DiscoveredDevice]:
    """Collapse the same device seen by several sources into one entry.

    The Matter server's view wins, because it carries the mDNS instance name and
    the addresses that decide whether commissioning can stay on the IP network.
    """
    by_discriminator: dict[int, DiscoveredDevice] = {}
    extras: list[DiscoveredDevice] = []
    for device in devices:
        if device.long_discriminator is None:
            extras.append(device)
            continue
        existing = by_discriminator.get(device.long_discriminator)
        if existing is None or (
            existing.source != SOURCE_MATTER_SERVER and device.source == SOURCE_MATTER_SERVER
        ):
            by_discriminator[device.long_discriminator] = device
    return [*by_discriminator.values(), *extras]
