"""Rendering a row's code back into a scannable label.

The rule worth testing is the refusal: only a QR payload gets drawn. Encoding a
manual pairing code or a bare passcode into a QR would produce something that
scans, fails in every Matter app, and looks like a defect here rather than on
the sticker.
"""

from __future__ import annotations

import pytest

from matterbook.qr import qr_payload, render_svg
from matterbook.store import MatterBookEntry

QR = "MT:Y.K9042C00KA0648G00"
MANUAL = "34970112332"
PASSCODE = "20202021"


def entry(code: str) -> MatterBookEntry:
    return MatterBookEntry(name="test", code=code)


def test_qr_payload_returns_the_payload_for_a_qr_code():
    assert qr_payload(entry(QR)) == QR


@pytest.mark.parametrize("code", [MANUAL, PASSCODE])
def test_qr_payload_refuses_codes_that_are_not_qr_payloads(code):
    assert qr_payload(entry(code)) is None


def test_qr_payload_is_none_without_a_code():
    assert qr_payload(entry("")) is None


def test_qr_payload_is_none_for_a_code_that_will_not_decode():
    # A row can hold nonsense: the book is a CSV a human may have edited.
    assert qr_payload(entry("MT:NOT-A-REAL-PAYLOAD")) is None


def test_render_svg_produces_an_svg_document():
    svg = render_svg(QR)
    assert svg.startswith(b"<?xml")
    assert b"<svg" in svg
    # The payload must not appear in the markup: the picture is the encoding,
    # and a copy in plain text would put a passcode in any cached response.
    assert QR.encode() not in svg
