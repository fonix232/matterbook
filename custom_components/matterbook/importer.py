"""Snapshotting an existing Matter fabric into the book.

What can be recovered from a commissioned node, and what cannot:

* **Not the setup code.** Commissioning is PASE (SPAKE2+): the device keeps a
  *verifier* derived from the passcode, and the commissioner throws the passcode
  away once it is done. Nothing on the fabric is holding it — the server's own
  node record (`MatterNodeData`) has no field for one. `open_commissioning_window`
  does mint a code, but that is the Enhanced Commissioning Method issuing a
  *temporary* passcode that dies with the window; a factory-reset device goes
  back to the passcode printed on its label. The sticker really is the only copy.
* **Everything else.** Vendor, product, serial number, unique ID and the node id
  come from the Basic Information cluster, and the name and area come from Home
  Assistant's own device registry.

So an import produces the book's skeleton: every device you own, named and
placed, each one a row waiting for its sticker to be found. Those rows cannot
pair anything until a code is added — they carry no discriminator, so the
matcher will not act on them, which is exactly right.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr

from . import matter_link

_LOGGER = logging.getLogger(__name__)

# Basic Information cluster (0x0028) on the root endpoint.
ATTR_VENDOR_ID = "0/40/2"
ATTR_PRODUCT_ID = "0/40/4"
ATTR_PRODUCT_NAME = "0/40/3"
ATTR_NODE_LABEL = "0/40/5"
ATTR_SERIAL_NUMBER = "0/40/15"
ATTR_UNIQUE_ID = "0/40/18"


@dataclass(slots=True)
class ImportCandidate:
    """One commissioned node, as the book would record it."""

    node_id: int
    name: str
    area: str
    vendor_id: int | None
    product_id: int | None
    serial_number: str
    unique_id: str


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _node_attributes(node: Any) -> dict[str, Any]:
    """Return a node's attribute dict, whichever wrapper it arrived in."""
    for holder in (node, getattr(node, "node_data", None)):
        attributes = getattr(holder, "attributes", None)
        if isinstance(attributes, dict):
            return attributes
    return {}


def async_collect_candidates(hass: HomeAssistant) -> list[ImportCandidate]:
    """Describe every node on the fabric as a prospective book row.

    Raises:
        MatterUnavailable: when the Matter integration is not loaded.
    """
    nodes = matter_link.async_get_nodes(hass)
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)
    client = matter_link.async_get_client(hass)
    server_info = getattr(client, "server_info", None)

    candidates: list[ImportCandidate] = []
    for node in nodes:
        node_id = getattr(node, "node_id", None)
        if node_id is None:
            continue

        attributes = _node_attributes(node)
        name = _as_str(attributes.get(ATTR_NODE_LABEL)) or _as_str(
            attributes.get(ATTR_PRODUCT_NAME)
        )
        area = ""

        # The name the user gave the device in Home Assistant beats anything the
        # device calls itself: it is what they will look for in the book.
        if server_info is not None:
            device = _device_for_node(hass, device_registry, server_info, node_id)
            if device is not None:
                name = device.name_by_user or device.name or name
                if device.area_id and (area_entry := area_registry.async_get_area(device.area_id)):
                    area = area_entry.name

        candidates.append(
            ImportCandidate(
                node_id=node_id,
                name=name,
                area=area,
                vendor_id=_as_int(attributes.get(ATTR_VENDOR_ID)),
                product_id=_as_int(attributes.get(ATTR_PRODUCT_ID)),
                serial_number=_as_str(attributes.get(ATTR_SERIAL_NUMBER)),
                unique_id=_as_str(attributes.get(ATTR_UNIQUE_ID)),
            )
        )
    return candidates


def _device_for_node(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    server_info: Any,
    node_id: int,
) -> dr.DeviceEntry | None:
    """Find the Home Assistant device the Matter integration made for a node."""
    try:
        from homeassistant.components.matter.helpers import (  # noqa: PLC0415
            get_node_device_identifier,
        )
    except ImportError:
        _LOGGER.debug("Matter helpers unavailable; importing without names and areas")
        return None

    try:
        identifier = get_node_device_identifier(server_info, node_id)
    except Exception as err:  # noqa: BLE001 - another integration's helper
        _LOGGER.debug("Could not derive the device identifier for node %s: %s", node_id, err)
        return None
    return device_registry.async_get_device(identifiers={identifier})
