"""Parsing the BLE advertisement of a commissionable Matter device.

Pure Python, no Home Assistant imports.

A device in pairing mode advertises service data under the 16-bit Matter service
UUID 0xFFF6 (Matter Core Specification 5.4.2.5.6):

====  ==================================================
byte  meaning
====  ==================================================
0     opcode; 0x00 means "commissionable"
1-2   uint16 LE: bits 0-11 discriminator, 12-15 version
3-4   uint16 LE vendor ID (0 when not stated)
5-6   uint16 LE product ID (0 when not stated)
7     additional data flag
====  ==================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import BLE_OPCODE_COMMISSIONABLE


@dataclass(frozen=True, slots=True)
class MatterAdvertisement:
    """The identity a commissionable device puts in its BLE advertisement."""

    discriminator: int
    vendor_id: int | None
    product_id: int | None
    has_additional_data: bool = False


def parse_matter_service_data(data: bytes) -> MatterAdvertisement | None:
    """Decode Matter BLE service data, or return ``None`` if it is not usable.

    Returns ``None`` for an advertisement that is not a commissionable one, is
    too short, or carries an advertisement version this code does not know.
    """
    # Byte 7 is optional in practice: some stacks trim the trailing flag byte.
    if len(data) < 7:
        return None
    if data[0] != BLE_OPCODE_COMMISSIONABLE:
        return None

    discriminator_field = int.from_bytes(data[1:3], "little")
    if discriminator_field >> 12 != 0:
        return None

    return MatterAdvertisement(
        discriminator=discriminator_field & 0x0FFF,
        vendor_id=int.from_bytes(data[3:5], "little") or None,
        product_id=int.from_bytes(data[5:7], "little") or None,
        has_additional_data=bool(len(data) > 7 and data[7] & 0x01),
    )
