"""Storing photographs of setup-code labels.

Two things here are worth holding still: the type comes from the bytes rather
than from what the caller claimed, and a filename out of the book can only ever
name a file in the labels directory. The second is not a formality — the book is
a CSV a human is invited to edit, and this module hands paths to an HTTP view.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matterbook.labels import (
    MAX_BYTES,
    LabelError,
    label_path,
    read_label,
    remove_label,
    sniff,
    write_label,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


@pytest.mark.parametrize(
    ("data", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_sniff_identifies_the_formats_we_store(data, expected):
    assert sniff(data) == expected


def test_sniff_rejects_a_riff_container_that_is_not_webp():
    # RIFF is shared with WAV and AVI, so the container alone proves nothing.
    assert sniff(b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 32) is None


def test_sniff_rejects_anything_else():
    assert sniff(b"pairing code: 20202021") is None


def test_write_label_names_the_file_for_what_it_actually_is(tmp_path: Path):
    assert write_label(tmp_path, "abc123", PNG) == "abc123.png"
    assert (tmp_path / "abc123.png").read_bytes() == PNG


def test_write_label_keeps_the_file_private(tmp_path: Path):
    write_label(tmp_path, "abc123", WEBP)
    assert (tmp_path / "abc123.webp").stat().st_mode & 0o777 == 0o600


def test_write_label_replaces_a_label_of_a_different_type(tmp_path: Path):
    write_label(tmp_path, "abc123", PNG)
    write_label(tmp_path, "abc123", WEBP)
    # A row points at one label, so the old file must not be left behind.
    assert not (tmp_path / "abc123.png").exists()
    assert (tmp_path / "abc123.webp").exists()


def test_write_label_refuses_something_that_is_not_an_image(tmp_path: Path):
    with pytest.raises(LabelError, match="not a PNG"):
        write_label(tmp_path, "abc123", b"20202021")


def test_write_label_refuses_an_empty_upload(tmp_path: Path):
    with pytest.raises(LabelError, match="empty"):
        write_label(tmp_path, "abc123", b"")


def test_write_label_refuses_an_oversized_upload(tmp_path: Path):
    with pytest.raises(LabelError, match="over the"):
        write_label(tmp_path, "abc123", PNG + b"\x00" * MAX_BYTES)


@pytest.mark.parametrize(
    "filename",
    [
        "../../secrets.yaml",
        "../database.csv",
        "sub/dir.webp",
        "/etc/passwd",
        ".hidden.webp",
        "",
    ],
)
def test_label_path_refuses_anything_but_a_bare_name(tmp_path: Path, filename):
    with pytest.raises(LabelError):
        label_path(tmp_path, filename)


def test_label_path_refuses_a_name_that_is_not_an_image(tmp_path: Path):
    with pytest.raises(LabelError, match="not an image"):
        label_path(tmp_path, "database.csv")


def test_read_label_returns_the_bytes_and_their_type(tmp_path: Path):
    write_label(tmp_path, "abc123", JPEG)
    assert read_label(tmp_path, "abc123.jpg") == (JPEG, "image/jpeg")


def test_read_label_reports_a_file_that_is_gone(tmp_path: Path):
    with pytest.raises(LabelError, match="Cannot read"):
        read_label(tmp_path, "missing.webp")


def test_remove_label_tolerates_one_that_is_already_gone(tmp_path: Path):
    remove_label(tmp_path, "missing.webp")


def test_remove_label_will_not_delete_by_a_name_it_would_refuse_to_serve(tmp_path: Path):
    victim = tmp_path.parent / "database.csv"
    victim.write_text("id,name,code\\n")
    remove_label(tmp_path, "../database.csv")
    assert victim.exists()
