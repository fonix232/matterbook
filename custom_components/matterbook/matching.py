"""Matching commissionable devices against MatterBook rows.

Pure Python, no Home Assistant imports.

The whole safety of auto-pairing rests here. A QR payload pins the full 12-bit
discriminator, so a match is as good as an identifier. A manual pairing code only
pins the 4-bit short discriminator: **one in sixteen** devices matches by chance,
which in a house full of Matter gear is a near-certainty rather than an edge case.

A bare 8-digit passcode is weaker still: it names no device at all.

So a match is only acted on when it is unambiguous in both directions: exactly one
row may claim a device, and exactly one device may answer a row. Anything else is
reported and left alone for a human — except for the one case a :class:`Trial`
covers, where a single unmatched row and a single unclaimed device leave nothing
else it could be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from .pairing_code import IDENTITY_EXACT, IDENTITY_NONE
from .store import MatterBookEntry

CONFIDENCE_EXACT: Final = "exact"
"""Long discriminator matched, and vendor/product ID agreed where both were known."""

CONFIDENCE_SHORT: Final = "short"
"""Only the 4-bit short discriminator matched (a manual pairing code)."""

SOURCE_MATTER_SERVER: Final = "matter_server"
SOURCE_BLUETOOTH: Final = "bluetooth"


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A device currently advertising that it is commissionable."""

    source: str
    long_discriminator: int | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    instance_name: str | None = None
    name: str | None = None
    address: str | None = None
    addresses: tuple[str, ...] = ()
    commissioning_mode: int | None = None
    rssi: int | None = None

    @property
    def key(self) -> str:
        """A stable-ish identity for logging and de-duplication."""
        if self.instance_name:
            return f"{self.source}:{self.instance_name}"
        if self.address:
            return f"{self.source}:{self.address}"
        return f"{self.source}:d{self.long_discriminator}"

    @property
    def short_discriminator(self) -> int | None:
        """The top four bits of the long discriminator, if it is known."""
        if self.long_discriminator is None:
            return None
        return self.long_discriminator >> 8

    @property
    def on_ip_network(self) -> bool:
        """Whether the device was found on the IP network (so BLE is not needed)."""
        return bool(self.addresses) or self.source == SOURCE_MATTER_SERVER

    def describe(self) -> dict[str, object]:
        """Return a dict for entity attributes and events (nothing secret here)."""
        return {
            "source": self.source,
            "discriminator": self.long_discriminator,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "instance_name": self.instance_name,
            "name": self.name,
            "address": self.address,
            "addresses": list(self.addresses),
            "commissioning_mode": self.commissioning_mode,
            "rssi": self.rssi,
        }


@dataclass(frozen=True, slots=True)
class Match:
    """A device that one MatterBook row may describe."""

    entry: MatterBookEntry
    device: DiscoveredDevice
    confidence: str

    @property
    def is_exact(self) -> bool:
        """Whether the match rests on the full 12-bit discriminator."""
        return self.confidence == CONFIDENCE_EXACT


@dataclass(frozen=True, slots=True)
class Trial:
    """A blind attempt: a row that names no device, and the one device present.

    A bare passcode identifies nothing, and a manual code identifies one device in
    sixteen. Rather than refuse those outright, MatterBook allows a single attempt
    when exactly one candidate device is in pairing mode — the common case when
    someone has just unboxed a device and typed its code in. The device's own
    advertised discriminator is then used to address it exactly, and what it turns
    out to be is written back into the book, so the guess happens at most once.
    """

    entry: MatterBookEntry
    device: DiscoveredDevice
    reason: str


@dataclass(slots=True)
class MatchReport:
    """The outcome of matching every discovered device against the book."""

    matches: list[Match] = field(default_factory=list)
    """Unambiguous matches, safe to act on."""

    ambiguous: list[Match] = field(default_factory=list)
    """Candidates dropped because more than one row or device could be meant."""

    unknown: list[DiscoveredDevice] = field(default_factory=list)
    """Commissionable devices no row claims."""

    trials: list[Trial] = field(default_factory=list)
    """Blind attempts that are allowed because only one device could be meant."""


def _ids_conflict(left: int | None, right: int | None) -> bool:
    """Whether two optional identifiers are both known and different."""
    return left is not None and right is not None and left != right


def candidate_match(entry: MatterBookEntry, device: DiscoveredDevice) -> Match | None:
    """Return how well one row matches one device, or ``None`` if it cannot.

    A row with a long discriminator (QR payload) must match the device's long
    discriminator exactly. A row with only a short discriminator (manual pairing
    code) matches on the top four bits, which is reported as a weaker confidence.
    A known vendor or product ID on both sides must agree either way.
    """
    if device.long_discriminator is None:
        return None
    if _ids_conflict(entry.vendor_id, device.vendor_id):
        return None
    if _ids_conflict(entry.product_id, device.product_id):
        return None

    if entry.discriminator is not None:
        if entry.discriminator != device.long_discriminator:
            return None
        return Match(entry, device, CONFIDENCE_EXACT)

    if entry.short_discriminator is None:
        return None
    if entry.short_discriminator != device.short_discriminator:
        return None
    # A manual code plus an agreeing vendor *and* product ID is as good as exact:
    # a 21-digit code carries both, and a collision would need the same model and
    # the same top four discriminator bits.
    if entry.vendor_id is not None and entry.vendor_id == device.vendor_id and (
        entry.product_id is not None and entry.product_id == device.product_id
    ):
        return Match(entry, device, CONFIDENCE_EXACT)
    return Match(entry, device, CONFIDENCE_SHORT)


def match_devices(
    entries: list[MatterBookEntry],
    devices: list[DiscoveredDevice],
    *,
    require_exact: bool = False,
    allow_trials: bool = True,
) -> MatchReport:
    """Match discovered devices against the book.

    Args:
        entries: the MatterBook rows to consider (callers filter out paired or
            disabled rows first when they only want pairable ones).
        devices: what is currently advertising as commissionable.
        require_exact: drop short-discriminator matches entirely, for installs
            that want auto-pairing only from scanned QR payloads.
        allow_trials: let a row that names no device take one blind attempt when
            exactly one unclaimed device is in pairing mode.

    Returns:
        A :class:`MatchReport` whose ``matches`` are unambiguous in both
        directions: one row, one device.
    """
    report = MatchReport()

    candidates: list[Match] = []
    for device in devices:
        for entry in entries:
            match = candidate_match(entry, device)
            if match is None:
                continue
            if require_exact and not match.is_exact:
                continue
            candidates.append(match)

    claimed_by_device: dict[str, list[Match]] = {}
    claimed_by_entry: dict[str, list[Match]] = {}
    for match in candidates:
        claimed_by_device.setdefault(match.device.key, []).append(match)
        claimed_by_entry.setdefault(match.entry.id, []).append(match)

    for match in candidates:
        device_claims = claimed_by_device[match.device.key]
        entry_claims = claimed_by_entry[match.entry.id]
        # An exact match wins over short-discriminator rivals for the same device:
        # the long discriminator identifies the device, the short one only hints.
        if len(device_claims) > 1 and not _wins(match, device_claims):
            report.ambiguous.append(match)
            continue
        if len(entry_claims) > 1 and not _wins(match, entry_claims):
            report.ambiguous.append(match)
            continue
        report.matches.append(match)

    matched_devices = {match.device.key for match in report.matches}
    ambiguous_devices = {match.device.key for match in report.ambiguous}
    report.unknown = [
        device
        for device in devices
        if device.key not in matched_devices and device.key not in ambiguous_devices
    ]

    if allow_trials and not require_exact:
        report.trials = _eligible_trials(entries, report, candidates)
    return report


def _eligible_trials(
    entries: list[MatterBookEntry],
    report: MatchReport,
    candidates: list[Match],
) -> list[Trial]:
    """Return the blind attempts that are safe to make.

    Safe means: exactly one device is up for grabs, exactly one row wants to take
    a blind shot at it, and that row has never taken one before. Anything less
    certain is a guess against someone else's device, so it waits for a human.
    """
    claimed = {match.entry.id for match in candidates}
    free_devices = report.unknown
    if len(free_devices) != 1:
        return []

    hopefuls = [
        entry
        for entry in entries
        if entry.id not in claimed and not entry.trial_used and entry.is_pairable
    ]
    if len(hopefuls) != 1:
        return []

    entry = hopefuls[0]
    strength = entry.identity_strength
    if strength == IDENTITY_EXACT:
        # An exact row that did not match is simply not this device.
        return []
    reason = (
        "the only entry without a match, and the only device in pairing mode"
        if strength == IDENTITY_NONE
        else "short discriminator, and the only device in pairing mode"
    )
    return [Trial(entry, free_devices[0], reason)]


def _wins(match: Match, rivals: list[Match]) -> bool:
    """Whether ``match`` is the single exact match among its rivals."""
    exact = [rival for rival in rivals if rival.is_exact]
    return len(exact) == 1 and exact[0] is match
