"""The MatterBook itself: a CSV file of known Matter devices and their codes.

Pure Python and synchronous by design — Home Assistant calls into it from the
executor. A CSV was chosen over Home Assistant's `Store` helper so the book stays
readable, editable and diffable outside Home Assistant (which is the point of
keeping a "book" in the first place).

Security note: a row contains the device passcode, which is all an attacker needs
to commission an uncommissioned device. The file is written 0600 and should be
treated like `secrets.yaml`.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Final
import uuid

from .pairing_code import InvalidSetupCode, SetupPayload, mask_code, parse_setup_code

STATUS_PENDING: Final = "pending"
STATUS_PAIRED: Final = "paired"
STATUS_FAILED: Final = "failed"
ALL_STATUSES: Final = (STATUS_PENDING, STATUS_PAIRED, STATUS_FAILED)


class MatterBookError(Exception):
    """Raised for problems with the MatterBook file or its contents."""


@dataclass(slots=True)
class MatterBookEntry:
    """One row of the MatterBook."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    code: str = ""
    vendor_id: int | None = None
    product_id: int | None = None
    discriminator: int | None = None
    """Long (12-bit) discriminator; only a QR payload carries one."""
    short_discriminator: int | None = None
    serial_number: str = ""
    area: str = ""
    notes: str = ""
    enabled: bool = True
    status: str = STATUS_PENDING
    node_id: int | None = None
    paired_at: str = ""
    last_attempt_at: str = ""
    attempt_count: int = 0
    last_error: str = ""

    @property
    def payload(self) -> SetupPayload:
        """Decode this row's setup code."""
        return parse_setup_code(self.code)

    @property
    def is_pairable(self) -> bool:
        """Whether auto-pairing should consider this row at all."""
        return self.enabled and self.status != STATUS_PAIRED

    def redacted(self) -> dict[str, Any]:
        """Return the row without its secret, for UI attributes and diagnostics."""
        data = asdict(self)
        data["code"] = mask_code(self.code) if self.code else ""
        data["code_type"] = "qr" if self.code.upper().startswith("MT:") else "manual"
        return data


CSV_COLUMNS: Final = tuple(f.name for f in fields(MatterBookEntry))

_INT_COLUMNS: Final = frozenset(
    {"vendor_id", "product_id", "discriminator", "short_discriminator", "node_id", "attempt_count"}
)
_BOOL_COLUMNS: Final = frozenset({"enabled"})


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enrich_from_code(entry: MatterBookEntry) -> MatterBookEntry:
    """Fill the identity columns that can be derived from the setup code.

    Values the operator typed in stay as they are; only blanks get filled, so a
    hand-written vendor ID is never silently overwritten by the decoder.
    """
    payload = entry.payload
    if entry.discriminator is None:
        entry.discriminator = payload.long_discriminator
    if entry.short_discriminator is None:
        entry.short_discriminator = payload.short_discriminator
    if entry.vendor_id is None:
        entry.vendor_id = payload.vendor_id
    if entry.product_id is None:
        entry.product_id = payload.product_id
    entry.code = payload.code
    return entry


def _parse_value(column: str, raw: str) -> Any:
    value = (raw or "").strip()
    if column in _INT_COLUMNS:
        if value == "":
            return 0 if column == "attempt_count" else None
        try:
            return int(value)
        except ValueError:
            return None
    if column in _BOOL_COLUMNS:
        return value.lower() not in ("false", "0", "no", "off")
    return value


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def read_entries(path: Path) -> list[MatterBookEntry]:
    """Read the MatterBook, returning an empty list if it does not exist yet.

    Unknown columns are ignored and missing columns fall back to their defaults,
    so a book written by an older or newer version still loads.
    """
    if not path.exists():
        return []

    entries: list[MatterBookEntry] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        if "code" not in reader.fieldnames:
            raise MatterBookError(f"{path} has no 'code' column; is it a MatterBook file?")
        for row in reader:
            values = {
                column: _parse_value(column, row.get(column, ""))
                for column in CSV_COLUMNS
                if column in row
            }
            entry = MatterBookEntry(**values)
            if not entry.id:
                entry.id = uuid.uuid4().hex[:12]
            if not entry.code:
                continue
            entries.append(entry)
    return entries


def write_entries(path: Path, entries: list[MatterBookEntry]) -> None:
    """Write the MatterBook atomically, keeping the file private (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for entry in entries:
                writer.writerow({column: _format_value(getattr(entry, column)) for column in CSV_COLUMNS})
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(handle.name, 0o600)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def add_entry(
    path: Path,
    code: str,
    *,
    name: str = "",
    area: str = "",
    notes: str = "",
    serial_number: str = "",
) -> MatterBookEntry:
    """Append a row to the MatterBook and return it.

    Raises:
        InvalidSetupCode: if the code is not a Matter onboarding payload.
        MatterBookError: if the same code is already in the book.
    """
    entry = enrich_from_code(
        MatterBookEntry(
            name=name.strip(),
            code=code.strip(),
            area=area.strip(),
            notes=notes.strip(),
            serial_number=serial_number.strip(),
        )
    )
    entries = read_entries(path)
    if any(existing.code == entry.code for existing in entries):
        raise MatterBookError("That setup code is already in the MatterBook")
    entries.append(entry)
    write_entries(path, entries)
    return entry


def remove_entry(path: Path, *, row: int | None = None, entry_id: str | None = None) -> MatterBookEntry:
    """Delete a row by 1-based row number or by entry id, returning what was deleted.

    Row numbers are what the UI shows and they shift after a deletion; the id is
    stable and is what automations should use.
    """
    if (row is None) == (entry_id is None):
        raise MatterBookError("Specify exactly one of row or entry_id")

    entries = read_entries(path)
    if entry_id is not None:
        for index, entry in enumerate(entries):
            if entry.id == entry_id:
                break
        else:
            raise MatterBookError(f"No MatterBook entry with id {entry_id}")
    else:
        assert row is not None
        if not 1 <= row <= len(entries):
            raise MatterBookError(f"Row {row} is out of range (the book has {len(entries)} rows)")
        index = row - 1

    removed = entries.pop(index)
    write_entries(path, entries)
    return removed


def update_entry(path: Path, entry_id: str, **changes: Any) -> MatterBookEntry:
    """Apply changes to one row, re-reading the file first so edits are not lost."""
    entries = read_entries(path)
    for entry in entries:
        if entry.id == entry_id:
            break
    else:
        raise MatterBookError(f"No MatterBook entry with id {entry_id}")

    for key, value in changes.items():
        if key in ("id", "code") or not hasattr(entry, key):
            raise MatterBookError(f"Cannot update column {key!r}")
        setattr(entry, key, value)
    write_entries(path, entries)
    return entry


def mark_paired(path: Path, entry_id: str, node_id: int) -> MatterBookEntry:
    """Record a successful commissioning against a row."""
    return update_entry(
        path,
        entry_id,
        status=STATUS_PAIRED,
        node_id=node_id,
        paired_at=utcnow_iso(),
        last_attempt_at=utcnow_iso(),
        last_error="",
    )


def mark_failed(path: Path, entry_id: str, error: str, attempt_count: int) -> MatterBookEntry:
    """Record a failed commissioning attempt against a row."""
    return update_entry(
        path,
        entry_id,
        status=STATUS_FAILED,
        last_attempt_at=utcnow_iso(),
        last_error=error[:200],
        attempt_count=attempt_count,
    )


def validate_code(code: str) -> SetupPayload:
    """Validate a setup code, raising :class:`InvalidSetupCode` if it is not one."""
    try:
        return parse_setup_code(code)
    except InvalidSetupCode:
        raise
    except Exception as err:  # defensive: decoder bugs must not look like valid codes
        raise InvalidSetupCode(str(err)) from err
