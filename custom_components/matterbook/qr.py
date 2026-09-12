"""Rendering a row's setup code back into a scannable QR label.

Only a QR payload can be rendered honestly. A manual pairing code or a bare
passcode is *not* a Matter QR — encoding those digits into a QR would produce
something that scans, fails in every Matter app, and looks like a defect in this
integration rather than in the label. Those rows report no image, and the panel
shows the digits instead.

The rendering happens here rather than in the panel because the panel never
receives a setup code. That is the whole point of masking them: a passcode
cannot leak through a payload the panel never gets. It does mean anyone looking
at the panel can scan the code off the screen — which is what a book of codes is
for, and why the panel is admin-only.
"""

from __future__ import annotations

import io

from .pairing_code import KIND_QR, InvalidSetupCode
from .store import MatterBookEntry


def qr_payload(entry: MatterBookEntry) -> str | None:
    """Return the Matter QR payload for a row, or ``None`` if it has no honest one."""
    if not entry.code:
        return None
    try:
        payload = entry.payload
    except InvalidSetupCode:
        return None
    return payload.code if payload.kind == KIND_QR else None


def render_svg(payload: str, *, scale: int = 4, dark: str = "#111111") -> bytes:
    """Render a QR payload as an SVG document.

    SVG rather than PNG: it is a tenth of the size, stays crisp when a phone
    zooms in on it to scan, and needs no image library.
    """
    import segno  # noqa: PLC0415 - keep the import cost off integration setup

    buffer = io.BytesIO()
    segno.make(payload, error="m").save(
        buffer,
        kind="svg",
        scale=scale,
        border=2,
        dark=dark,
        light=None,
        svgclass=None,
        lineclass=None,
    )
    return buffer.getvalue()
