"""Tests for matching discovered devices against MatterBook rows."""

from __future__ import annotations

from matterbook.advertisement import parse_matter_service_data
from matterbook.matching import (
    CONFIDENCE_EXACT,
    CONFIDENCE_SHORT,
    SOURCE_BLUETOOTH,
    SOURCE_MATTER_SERVER,
    DiscoveredDevice,
    candidate_match,
    match_devices,
)
from matterbook.store import MatterBookEntry


def qr_entry(**kwargs: object) -> MatterBookEntry:
    """Build a row stored from a QR payload, which knows the long discriminator."""
    defaults: dict[str, object] = {
        "code": "MT:Y.K9042C00KA0648G00",
        "discriminator": 3840,
        "short_discriminator": 15,
        "vendor_id": 65521,
        "product_id": 32768,
    }
    return MatterBookEntry(**{**defaults, "id": "qr", **kwargs})  # type: ignore[arg-type]


def manual_entry(**kwargs: object) -> MatterBookEntry:
    """Build a row stored from a manual code, which knows only the short one."""
    defaults: dict[str, object] = {
        "code": "34970112332",
        "discriminator": None,
        "short_discriminator": 15,
    }
    return MatterBookEntry(**{**defaults, "id": "manual", **kwargs})  # type: ignore[arg-type]


def device(**kwargs: object) -> DiscoveredDevice:
    defaults: dict[str, object] = {
        "source": SOURCE_MATTER_SERVER,
        "long_discriminator": 3840,
        "vendor_id": 65521,
        "product_id": 32768,
        "instance_name": "AABBCCDDEEFF0011",
    }
    return DiscoveredDevice(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_qr_entry_matches_exactly() -> None:
    match = candidate_match(qr_entry(), device())
    assert match is not None
    assert match.confidence == CONFIDENCE_EXACT


def test_qr_entry_does_not_match_a_different_discriminator() -> None:
    assert candidate_match(qr_entry(), device(long_discriminator=3841)) is None


def test_manual_entry_matches_only_on_the_short_discriminator() -> None:
    # 3840 >> 8 == 15, and so does 3841..4095: the manual code cannot tell them apart.
    match = candidate_match(
        manual_entry(), device(long_discriminator=3999, vendor_id=None, product_id=None)
    )
    assert match is not None
    assert match.confidence == CONFIDENCE_SHORT


def test_manual_entry_with_vendor_and_product_counts_as_exact() -> None:
    match = candidate_match(manual_entry(vendor_id=65521, product_id=32768), device())
    assert match is not None
    assert match.confidence == CONFIDENCE_EXACT


def test_conflicting_vendor_id_blocks_a_match() -> None:
    assert candidate_match(qr_entry(vendor_id=1), device(vendor_id=2)) is None


def test_device_without_a_discriminator_never_matches() -> None:
    assert candidate_match(qr_entry(), device(long_discriminator=None)) is None


def test_unknown_devices_are_reported() -> None:
    report = match_devices([], [device()])
    assert report.matches == []
    assert [found.key for found in report.unknown] == [device().key]


def test_two_entries_claiming_one_device_is_ambiguous() -> None:
    first = manual_entry(id="a")
    second = manual_entry(id="b", code="34970112332")
    report = match_devices([first, second], [device(vendor_id=None, product_id=None)])

    assert report.matches == []
    assert len(report.ambiguous) == 2
    assert report.unknown == []


def test_one_entry_claiming_two_devices_is_ambiguous() -> None:
    report = match_devices(
        [manual_entry()],
        [
            device(long_discriminator=3840, instance_name="one", vendor_id=None, product_id=None),
            device(long_discriminator=3900, instance_name="two", vendor_id=None, product_id=None),
        ],
    )
    assert report.matches == []
    assert len(report.ambiguous) == 2


def test_an_exact_match_wins_over_a_short_rival() -> None:
    report = match_devices([qr_entry(), manual_entry()], [device()])
    assert [match.entry.id for match in report.matches] == ["qr"]
    assert [match.entry.id for match in report.ambiguous] == ["manual"]


def test_require_exact_drops_short_matches() -> None:
    report = match_devices(
        [manual_entry()], [device(vendor_id=None, product_id=None)], require_exact=True
    )
    assert report.matches == []
    assert report.ambiguous == []
    assert len(report.unknown) == 1


def test_bluetooth_advertisement_feeds_the_same_matcher() -> None:
    # opcode 0x00, discriminator 3840 (0xF00), vendor 0xFFF1, product 0x8000
    service_data = bytes([0x00, 0x00, 0x0F, 0xF1, 0xFF, 0x00, 0x80, 0x00])
    advertisement = parse_matter_service_data(service_data)
    assert advertisement is not None
    assert advertisement.discriminator == 3840
    assert advertisement.vendor_id == 65521
    assert advertisement.product_id == 32768

    discovered = DiscoveredDevice(
        source=SOURCE_BLUETOOTH,
        long_discriminator=advertisement.discriminator,
        vendor_id=advertisement.vendor_id,
        product_id=advertisement.product_id,
        address="AA:BB:CC:DD:EE:FF",
    )
    match = candidate_match(qr_entry(), discovered)
    assert match is not None
    assert match.confidence == CONFIDENCE_EXACT
    # A BLE-only device is not on the IP network, so commissioning must not be
    # restricted to the network.
    assert discovered.on_ip_network is False


def test_non_commissionable_advertisements_are_ignored() -> None:
    assert parse_matter_service_data(bytes([0x01, 0x00, 0x0F, 0, 0, 0, 0, 0])) is None
    assert parse_matter_service_data(b"\x00\x00") is None
    # Advertisement version 1 is not something this code knows how to read.
    assert parse_matter_service_data(bytes([0x00, 0x00, 0x1F, 0, 0, 0, 0, 0])) is None


def test_matter_server_device_counts_as_on_the_network() -> None:
    assert device(addresses=("192.168.1.5",)).on_ip_network is True


def passcode_entry(**kwargs: object) -> MatterBookEntry:
    """Build a row stored from a bare 8-digit passcode, which names no device."""
    defaults: dict[str, object] = {"code": "20202021", "id": "pin"}
    return MatterBookEntry(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_a_passcode_row_never_matches_by_identity() -> None:
    assert candidate_match(passcode_entry(), device()) is None


def test_a_lone_passcode_row_may_try_the_lone_device() -> None:
    report = match_devices([passcode_entry()], [device()])
    assert report.matches == []
    assert len(report.trials) == 1
    trial = report.trials[0]
    assert trial.entry.id == "pin"
    assert trial.device.key == device().key


def test_a_row_that_has_already_tried_does_not_try_again() -> None:
    report = match_devices([passcode_entry(trial_used=True)], [device()])
    assert report.trials == []


def test_no_trial_when_two_devices_are_in_pairing_mode() -> None:
    report = match_devices(
        [passcode_entry()],
        [device(instance_name="one"), device(instance_name="two", long_discriminator=100)],
    )
    assert report.trials == []


def test_no_trial_when_two_rows_are_waiting() -> None:
    report = match_devices(
        [passcode_entry(), passcode_entry(id="pin2", code="20202021")], [device()]
    )
    assert report.trials == []


def test_no_trial_when_the_device_already_belongs_to_a_matched_row() -> None:
    report = match_devices([qr_entry(), passcode_entry()], [device()])
    assert [match.entry.id for match in report.matches] == ["qr"]
    assert report.trials == []


def test_a_manual_row_may_try_a_device_it_cannot_pin_down() -> None:
    # The short discriminator does not agree, so it is not even a weak match --
    # but it is the only row and the only device, so one attempt is allowed.
    report = match_devices(
        [manual_entry()], [device(long_discriminator=100, vendor_id=None, product_id=None)]
    )
    assert report.matches == []
    assert len(report.trials) == 1


def test_an_exact_row_never_takes_a_blind_attempt() -> None:
    # A QR row that did not match is simply not this device, so there is nothing
    # to guess at.
    report = match_devices([qr_entry()], [device(long_discriminator=100)])
    assert report.trials == []
    assert len(report.unknown) == 1


def test_trials_can_be_turned_off() -> None:
    assert match_devices([passcode_entry()], [device()], allow_trials=False).trials == []
    assert match_devices([passcode_entry()], [device()], require_exact=True).trials == []
