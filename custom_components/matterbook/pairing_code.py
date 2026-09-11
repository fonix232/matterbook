"""Decoding of Matter onboarding payloads (QR payload and manual pairing code).

Pure Python, no Home Assistant imports: this module is unit-testable on its own.

Both payload forms carry the discriminator that a commissionable device also puts
in its BLE advertisement and its `_matterc._udp` mDNS record, which is what lets
MatterBook recognise a device in pairing mode without any user interaction:

* a QR payload (``MT:...``) carries the full **12-bit** discriminator, so a match
  against a discovered device is exact (1 in 4096);
* a manual pairing code only carries the **4-bit short** discriminator (the top
  four bits of the long one), so a match narrows to 1 in 16 and needs the
  vendor/product ID (21-digit codes only) or operator judgement to disambiguate.

References (Matter Core Specification 1.x, chapter 5.1):
* 5.1.3.1 QR payload bit layout and base38 encoding
* 5.1.4.1 manual pairing code digit layout and Verhoeff check digit
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

QR_PREFIX: Final = "MT:"

# Matter base38 alphabet, spec 5.1.3.1.
_BASE38_ALPHABET: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."
_BASE38_VALUES: Final = {char: index for index, char in enumerate(_BASE38_ALPHABET)}

# QR payload bit fields as (offset, length), spec 5.1.3.1 table 59.
_QR_VERSION: Final = (0, 3)
_QR_VENDOR_ID: Final = (3, 16)
_QR_PRODUCT_ID: Final = (19, 16)
_QR_FLOW_TYPE: Final = (35, 2)
_QR_DISCOVERY_CAPABILITIES: Final = (37, 8)
_QR_DISCRIMINATOR: Final = (45, 12)
_QR_PASSCODE: Final = (57, 27)
# 84 payload bits, padded to 11 bytes.
_QR_PAYLOAD_BYTES: Final = 11

# Discovery capability bitmap, spec 5.1.3.1 table 60.
DISCOVERY_CAPABILITY_BLE: Final = 1 << 1
DISCOVERY_CAPABILITY_ON_IP_NETWORK: Final = 1 << 2

# Passcodes the spec forbids because they are trivially guessable (5.1.7.1).
_INVALID_PASSCODES: Final = frozenset(
    {
        0,
        11111111,
        22222222,
        33333333,
        44444444,
        55555555,
        66666666,
        77777777,
        88888888,
        99999999,
        12345678,
        87654321,
    }
)
_MAX_PASSCODE: Final = 99999998

_VERHOEFF_MULTIPLY: Final = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_INVERSE: Final = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)
_VERHOEFF_PERMUTE: Final = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


class InvalidSetupCode(ValueError):
    """Raised when a string is not a usable Matter onboarding payload."""


@dataclass(frozen=True, slots=True)
class SetupPayload:
    """A decoded Matter onboarding payload."""

    kind: str
    """``"qr"`` for an ``MT:`` payload, ``"manual"`` for a pairing code."""

    code: str
    """The payload in its normalised form, as it should be handed to the server."""

    passcode: int
    short_discriminator: int
    long_discriminator: int | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    discovery_capabilities: int | None = None

    @property
    def supports_ble(self) -> bool | None:
        """Whether the device advertises over BLE while uncommissioned.

        ``None`` for manual codes, which do not carry discovery capabilities.
        """
        if self.discovery_capabilities is None:
            return None
        return bool(self.discovery_capabilities & DISCOVERY_CAPABILITY_BLE)

    @property
    def already_on_network(self) -> bool | None:
        """Whether the device states it is already on the IP network."""
        if self.discovery_capabilities is None:
            return None
        return bool(self.discovery_capabilities & DISCOVERY_CAPABILITY_ON_IP_NETWORK)


def verhoeff_checksum(digits: str) -> int:
    """Return the Verhoeff check digit for a string of decimal digits."""
    checksum = 0
    length = len(digits)
    for index in range(1, length + 1):
        digit = digits[length - index]
        if not digit.isdigit():
            raise InvalidSetupCode(f"Not a decimal digit: {digit!r}")
        checksum = _VERHOEFF_MULTIPLY[checksum][_VERHOEFF_PERMUTE[index % 8][int(digit)]]
    return _VERHOEFF_INVERSE[checksum]


def base38_decode(encoded: str) -> bytes:
    """Decode a Matter base38 string (spec 5.1.3.1)."""
    remainder = len(encoded) % 5
    if remainder in (1, 3):
        raise InvalidSetupCode(f"Invalid base38 length: {len(encoded)}")

    result = bytearray()
    for offset in range(0, len(encoded), 5):
        group = encoded[offset : offset + 5]
        byte_count = {5: 3, 4: 2, 2: 1}[len(group)]
        value = 0
        for char in reversed(group):
            try:
                value = value * 38 + _BASE38_VALUES[char]
            except KeyError:
                raise InvalidSetupCode(f"Invalid base38 character: {char!r}") from None
        if value >= 1 << (8 * byte_count):
            raise InvalidSetupCode(f"Base38 group {group!r} overflows {byte_count} bytes")
        result += value.to_bytes(byte_count, "little")
    return bytes(result)


def _read_bits(data: bytes, offset: int, length: int) -> int:
    """Read ``length`` bits starting at ``offset`` from an LSB-first bit stream."""
    value = 0
    for index in range(length):
        bit = offset + index
        if data[bit // 8] >> (bit % 8) & 1:
            value |= 1 << index
    return value


def _validate_passcode(passcode: int) -> None:
    if passcode in _INVALID_PASSCODES or passcode > _MAX_PASSCODE:
        raise InvalidSetupCode(f"Passcode {passcode} is not a valid Matter passcode")


def _stated_id(value: int) -> int | None:
    """Return ``None`` for the "unspecified" vendor/product ID 0 (spec 2.5.2)."""
    return value or None


def parse_qr_payload(code: str) -> SetupPayload:
    """Decode an ``MT:`` QR payload."""
    normalised = code.strip().upper().replace(" ", "")
    if not normalised.startswith(QR_PREFIX):
        raise InvalidSetupCode("QR payload must start with 'MT:'")

    data = base38_decode(normalised[len(QR_PREFIX) :])
    if len(data) < _QR_PAYLOAD_BYTES:
        raise InvalidSetupCode("QR payload is too short")

    version = _read_bits(data, *_QR_VERSION)
    if version != 0:
        raise InvalidSetupCode(f"Unsupported onboarding payload version {version}")

    passcode = _read_bits(data, *_QR_PASSCODE)
    _validate_passcode(passcode)
    discriminator = _read_bits(data, *_QR_DISCRIMINATOR)

    return SetupPayload(
        kind="qr",
        code=normalised,
        passcode=passcode,
        long_discriminator=discriminator,
        short_discriminator=discriminator >> 8,
        vendor_id=_stated_id(_read_bits(data, *_QR_VENDOR_ID)),
        product_id=_stated_id(_read_bits(data, *_QR_PRODUCT_ID)),
        discovery_capabilities=_read_bits(data, *_QR_DISCOVERY_CAPABILITIES),
    )


def parse_manual_code(code: str) -> SetupPayload:
    """Decode an 11- or 21-digit manual pairing code."""
    digits = re.sub(r"\D", "", code)
    if len(digits) not in (11, 21):
        raise InvalidSetupCode(f"A manual pairing code has 11 or 21 digits, got {len(digits)}")
    if int(digits[0]) >= 8:
        raise InvalidSetupCode(f"Unsupported onboarding payload version (first digit {digits[0]})")
    if verhoeff_checksum(digits[:-1]) != int(digits[-1]):
        raise InvalidSetupCode("Manual pairing code checksum is invalid")

    has_vendor_product = bool(int(digits[0]) & 0b100)
    if has_vendor_product != (len(digits) == 21):
        raise InvalidSetupCode("VID_PID_PRESENT flag disagrees with the code length")

    chunk2 = int(digits[1:6])
    short_discriminator = ((int(digits[0]) & 0b011) << 2) | ((chunk2 >> 14) & 0b11)
    passcode = (chunk2 & 0x3FFF) | (int(digits[6:10]) << 14)
    _validate_passcode(passcode)

    vendor_id = product_id = None
    if has_vendor_product:
        vendor_id = _stated_id(int(digits[10:15]))
        product_id = _stated_id(int(digits[15:20]))

    return SetupPayload(
        kind="manual",
        code=digits,
        passcode=passcode,
        short_discriminator=short_discriminator,
        vendor_id=vendor_id,
        product_id=product_id,
    )


def parse_setup_code(code: str) -> SetupPayload:
    """Decode either onboarding payload form.

    Raises:
        InvalidSetupCode: if the string is neither a QR payload nor a pairing code.
    """
    candidate = code.strip()
    if not candidate:
        raise InvalidSetupCode("Setup code is empty")
    if candidate.upper().startswith(QR_PREFIX):
        return parse_qr_payload(candidate)
    return parse_manual_code(candidate)


def mask_code(code: str) -> str:
    """Return a redacted form of a setup code, safe to show in the UI.

    The passcode is the shared secret of the commissioning handshake, so the full
    code never appears in entity attributes, diagnostics or log lines.
    """
    candidate = code.strip()
    if candidate.upper().startswith(QR_PREFIX):
        return f"{QR_PREFIX}…{candidate[-3:]}" if len(candidate) > 6 else f"{QR_PREFIX}…"
    digits = re.sub(r"\D", "", candidate)
    if len(digits) <= 4:
        return "…"
    return f"{digits[:2]}…{digits[-2:]}"
