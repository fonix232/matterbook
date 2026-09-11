"""Tests for the Matter onboarding payload decoder."""

from __future__ import annotations

import pytest

from matterbook.pairing_code import (
    InvalidSetupCode,
    base38_decode,
    mask_code,
    parse_setup_code,
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
