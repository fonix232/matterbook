"""Storing photographs of setup-code labels.

Pure Python and synchronous, like `store.py`: Home Assistant calls into it from
the executor.

A label image is as sensitive as the book itself — the passcode is legible in
the picture, and often printed next to it in plain digits. So these files live
beside the book under `config/matterbook/`, never under `config/www/`, which is
served without authentication, and they are written 0600 like the book is.

The bytes arrive already re-encoded by the browser, which is what strips the
EXIF a phone attaches. A book of device labels tagged with the coordinates of
the house they are in is not something to put in a backup.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Final

# What the panel may send. It re-encodes to WebP before uploading, so that is
# the expected one; the other two are here because a browser that cannot encode
# WebP should still be able to file a picture rather than nothing.
SUFFIXES: Final[dict[str, str]] = {
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

# Leading bytes that actually identify each format. The declared content type is
# a claim by the caller; this is the file itself. Storing something whose type
# is not what the view will serve it as is how a picture endpoint turns into a
# way to serve arbitrary content.
_MAGIC: Final[tuple[tuple[str, bytes, int], ...]] = (
    ("image/png", b"\x89PNG\r\n\x1a\n", 0),
    ("image/jpeg", b"\xff\xd8\xff", 0),
    ("image/webp", b"RIFF", 0),
    ("image/webp", b"WEBP", 8),
)

# A cropped label re-encoded at quality 90 is tens of kilobytes. This is roomy
# enough for a generous original and small enough that a WebSocket message
# carrying one base64-encoded stays well inside what Home Assistant accepts.
MAX_BYTES: Final = 2 * 1024 * 1024


class LabelError(Exception):
    """Raised when a label image cannot be stored or read."""


def sniff(data: bytes) -> str | None:
    """Return the image type the bytes actually are, or ``None``."""
    found = {
        kind for kind, magic, offset in _MAGIC if data[offset : offset + len(magic)] == magic
    }
    # WebP needs both of its markers; the RIFF container is shared with other
    # formats, so matching only that proves nothing.
    if "image/webp" in found and data[8:12] != b"WEBP":
        found.discard("image/webp")
    return next(iter(found), None)


def label_path(label_dir: Path, filename: str) -> Path:
    """Return the full path of a stored label, refusing anything but a bare name.

    The filename comes out of the book, which is a CSV a human is invited to
    edit. Resolving `../../secrets.yaml` into a view that serves files is the
    obvious way for that invitation to go wrong, so this is not a formality.
    """
    if not filename or filename != Path(filename).name or filename.startswith("."):
        raise LabelError(f"{filename!r} is not a label file name")
    if Path(filename).suffix not in set(SUFFIXES.values()):
        raise LabelError(f"{filename!r} is not an image MatterBook stores")
    return label_dir / filename


def write_label(label_dir: Path, entry_id: str, data: bytes) -> str:
    """Store one label image and return its filename.

    The type comes from the bytes rather than from what the caller said they
    were, and the extension follows the type, so the file is always named for
    what it actually is.
    """
    if not data:
        raise LabelError("The label image was empty")
    if len(data) > MAX_BYTES:
        raise LabelError(
            f"The label image is {len(data)} bytes, over the {MAX_BYTES}-byte limit"
        )

    kind = sniff(data)
    if kind is None:
        raise LabelError("That is not a PNG, JPEG or WebP image")

    filename = f"{entry_id}{SUFFIXES[kind]}"
    path = label_path(label_dir, filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed below, then renamed
        "wb", dir=path.parent, prefix=f".{filename}.", suffix=".tmp", delete=False
    )
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise

    # A row can only point at one label, so replacing a WebP with a JPEG has to
    # take the WebP with it or the old picture is orphaned on disk forever.
    for suffix in set(SUFFIXES.values()) - {path.suffix}:
        (label_dir / f"{entry_id}{suffix}").unlink(missing_ok=True)

    return filename


def remove_label(label_dir: Path, filename: str) -> None:
    """Delete a stored label image, tolerating one that is already gone."""
    try:
        label_path(label_dir, filename).unlink(missing_ok=True)
    except LabelError:
        # A name the book should never have held is not one to go deleting by.
        return


def read_label(label_dir: Path, filename: str) -> tuple[bytes, str]:
    """Return a stored label's bytes and the type they actually are."""
    path = label_path(label_dir, filename)
    try:
        data = path.read_bytes()
    except OSError as err:
        raise LabelError(f"Cannot read {filename}: {err}") from err

    kind = sniff(data)
    if kind is None:
        raise LabelError(f"{filename} is not an image any more")
    return data, kind
