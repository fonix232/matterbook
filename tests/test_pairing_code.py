"""Tests for the Matter onboarding payload decoder."""

from __future__ import annotations

import pytest

from matterbook.pairing_code import (
    IDENTITY_EXACT,
    IDENTITY_NONE,
    IDENTITY_SHORT,
    KIND_PASSCODE,
    InvalidSetupCode,
    base38_decode,
    encode_qr_payload,
    mask_code,
    parse_setup_code,
    qr_payload_for,
    verhoeff_checksum,
)

# The SDK's standard test payloads: discriminator 3840, passcode 20202021,
# vendor 0xFFF1 (65521), product 0x8000/0x8001.
# 0x8000 / discovery over BLE:
QR_BLE = "MT:Y.K9042C00KA0648G00"
# 0x8001 / already on the IP network:
QR_ON_NETWORK = "MT:-24J0AFN00KA0648G00"
MANUAL_SHORT = "34970112332"


def test_qr_payload_decodes_to_known_values() -> None:
    payload = parse_setup_code(QR_BLE)
    assert payload.kind == "qr"
    assert payload.long_discriminator == 3840
    assert payload.short_discriminator == 15
    assert payload.passcode == 20202021
    assert payload.vendor_id == 65521
    assert payload.product_id == 32768


def test_manual_code_decodes_to_known_values() -> None:
    payload = parse_setup_code(MANUAL_SHORT)
    assert payload.kind == "manual"
    assert payload.passcode == 20202021
    # A manual code carries only the top four bits of the discriminator.
    assert payload.short_discriminator == 15
    assert payload.long_discriminator is None
    assert payload.vendor_id is None


def test_manual_and_qr_forms_agree_on_the_short_discriminator() -> None:
    qr = parse_setup_code(QR_BLE)
    manual = parse_setup_code(MANUAL_SHORT)
    assert qr.long_discriminator is not None
    assert qr.long_discriminator >> 8 == manual.short_discriminator


def test_discovery_capabilities() -> None:
    assert parse_setup_code(QR_BLE).supports_ble is True
    assert parse_setup_code(QR_ON_NETWORK).already_on_network is True
    assert parse_setup_code(MANUAL_SHORT).supports_ble is None


def test_manual_code_is_robust_against_formatting() -> None:
    assert parse_setup_code("3497-011-2332").passcode == 20202021
    assert parse_setup_code("  3497 011 2332 ").passcode == 20202021


@pytest.mark.parametrize(
    "code",
    [
        "",
        "not a code",
        "3497011233",  # too short
        "34970112333",  # checksum broken
        "MT:NOTBASE38!!",
        "MT:",
    ],
)
def test_invalid_codes_are_rejected(code: str) -> None:
    with pytest.raises(InvalidSetupCode):
        parse_setup_code(code)


def test_trivial_passcodes_are_rejected() -> None:
    # A code that decodes cleanly but carries a passcode the spec forbids is a
    # typo or a fake, not something worth storing.
    digits = "00000000000"
    body = digits[:-1]
    code = body + str(verhoeff_checksum(body))
    with pytest.raises(InvalidSetupCode):
        parse_setup_code(code)


def test_verhoeff_matches_known_values() -> None:
    assert verhoeff_checksum("3497011233") == 2
    assert verhoeff_checksum("236") == 3


def test_base38_round_trip_of_known_payload() -> None:
    decoded = base38_decode(QR_BLE[3:])
    assert len(decoded) == 11


def test_mask_code_hides_the_passcode() -> None:
    masked_qr = mask_code(QR_BLE)
    assert "MT:" in masked_qr
    assert QR_BLE not in masked_qr
    assert len(masked_qr) < len(QR_BLE)

    masked_manual = mask_code(MANUAL_SHORT)
    assert masked_manual.startswith("34")
    assert masked_manual.endswith("32")
    assert "970112" not in masked_manual


def test_bare_passcode_is_accepted_but_names_no_device() -> None:
    payload = parse_setup_code("2020-2021")
    assert payload.kind == KIND_PASSCODE
    assert payload.passcode == 20202021
    assert payload.long_discriminator is None
    assert payload.short_discriminator is None
    assert payload.identity_strength == IDENTITY_NONE


def test_identity_strength_ranks_the_three_forms() -> None:
    assert parse_setup_code(QR_BLE).identity_strength == IDENTITY_EXACT
    assert parse_setup_code(MANUAL_SHORT).identity_strength == IDENTITY_SHORT
    assert parse_setup_code("20202021").identity_strength == IDENTITY_NONE


def test_encoder_reproduces_the_reference_payload() -> None:
    # If the encoder can rebuild the SDK's own payload byte for byte, its bit
    # layout and base38 are right.
    assert (
        encode_qr_payload(
            passcode=20202021,
            discriminator=3840,
            vendor_id=0xFFF1,
            product_id=0x8000,
            discovery_capabilities=2,
        )
        == QR_BLE
    )


def test_encoder_rejects_impossible_values() -> None:
    with pytest.raises(InvalidSetupCode):
        encode_qr_payload(passcode=20202021, discriminator=4096)
    with pytest.raises(InvalidSetupCode):
        encode_qr_payload(passcode=12345678, discriminator=1)


def test_qr_payload_for_leaves_a_qr_entry_alone() -> None:
    payload = parse_setup_code(QR_BLE)
    assert qr_payload_for(payload, discriminator=1234) == QR_BLE


def test_qr_payload_for_pins_a_passcode_to_a_discovered_device() -> None:
    # This is what makes a bare passcode usable: the discriminator comes from the
    # device's own advertisement, so the synthesised payload names it exactly.
    payload = parse_setup_code("20202021")
    synthesised = parse_setup_code(
        qr_payload_for(payload, discriminator=2748, vendor_id=4660, product_id=22136)
    )
    assert synthesised.long_discriminator == 2748
    assert synthesised.passcode == 20202021
    assert synthesised.vendor_id == 4660
    assert synthesised.product_id == 22136
    assert synthesised.supports_ble is True


def test_qr_payload_for_pins_a_manual_code_to_a_discovered_device() -> None:
    payload = parse_setup_code(MANUAL_SHORT)
    synthesised = parse_setup_code(qr_payload_for(payload, discriminator=3999))
    assert synthesised.long_discriminator == 3999
    assert synthesised.passcode == payload.passcode
    # The short discriminator of the chosen device still has to agree with the
    # printed code, or it was the wrong device to aim at.
    assert synthesised.short_discriminator == payload.short_discriminator


def test_base38_round_trips_arbitrary_payloads() -> None:
    for passcode, discriminator in ((20202021, 0), (99999998, 4095), (1, 2748)):
        code = encode_qr_payload(passcode=passcode, discriminator=discriminator)
        payload = parse_setup_code(code)
        assert payload.passcode == passcode
        assert payload.long_discriminator == discriminator
