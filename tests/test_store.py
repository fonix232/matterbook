"""Tests for the CSV-backed MatterBook."""

from __future__ import annotations

from pathlib import Path

import pytest

from matterbook.pairing_code import InvalidSetupCode
from matterbook.store import (
    STATUS_PAIRED,
    MatterBookError,
    add_entry,
    mark_failed,
    mark_paired,
    read_entries,
    remove_entry,
    update_entry,
    write_entries,
)

QR = "MT:Y.K9042C00KA0648G00"
QR_OTHER = "MT:-24J0AFN00KA0648G00"
MANUAL = "34970112332"


def test_reading_a_missing_book_gives_an_empty_list(tmp_path: Path) -> None:
    assert read_entries(tmp_path / "nope.csv") == []


def test_add_entry_derives_identity_from_the_code(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR, name="Kitchen light", area="Kitchen")

    assert entry.discriminator == 3840
    assert entry.short_discriminator == 15
    assert entry.vendor_id == 65521
    assert entry.product_id == 32768
    assert entry.name == "Kitchen light"
    assert entry.id

    (stored,) = read_entries(path)
    assert stored.code == QR
    assert stored.discriminator == 3840
    assert stored.enabled is True
    assert stored.is_pairable is True


def test_add_entry_from_a_manual_code_has_no_long_discriminator(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, MANUAL)
    assert entry.discriminator is None
    assert entry.short_discriminator == 15


def test_add_entry_rejects_a_bad_code(tmp_path: Path) -> None:
    with pytest.raises(InvalidSetupCode):
        add_entry(tmp_path / "matterbook.csv", "nonsense")


def test_add_entry_rejects_a_duplicate_code(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    add_entry(path, QR)
    with pytest.raises(MatterBookError):
        add_entry(path, QR)


def test_remove_entry_by_row(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    add_entry(path, QR, name="first")
    add_entry(path, QR_OTHER, name="second")

    removed = remove_entry(path, row=1)
    assert removed.name == "first"
    remaining = read_entries(path)
    assert [entry.name for entry in remaining] == ["second"]


def test_remove_entry_by_id_survives_row_shifts(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    first = add_entry(path, QR, name="first")
    add_entry(path, QR_OTHER, name="second")

    remove_entry(path, entry_id=first.id)
    assert [entry.name for entry in read_entries(path)] == ["second"]


@pytest.mark.parametrize("row", [0, 3, -1])
def test_remove_entry_rejects_an_out_of_range_row(tmp_path: Path, row: int) -> None:
    path = tmp_path / "matterbook.csv"
    add_entry(path, QR)
    with pytest.raises((MatterBookError, Exception)):
        remove_entry(path, row=row)


def test_remove_entry_needs_exactly_one_selector(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    with pytest.raises(MatterBookError):
        remove_entry(path)
    with pytest.raises(MatterBookError):
        remove_entry(path, row=1, entry_id=entry.id)


def test_mark_paired_and_failed(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)

    mark_failed(path, entry.id, "device did not answer", 1)
    (stored,) = read_entries(path)
    assert stored.status == "failed"
    assert stored.attempt_count == 1
    assert stored.last_error == "device did not answer"
    assert stored.is_pairable is True

    mark_paired(path, entry.id, node_id=42)
    (stored,) = read_entries(path)
    assert stored.status == STATUS_PAIRED
    assert stored.node_id == 42
    assert stored.paired_at
    assert stored.is_pairable is False


def test_update_entry_refuses_to_change_identity(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    with pytest.raises(MatterBookError):
        update_entry(path, entry.id, code=MANUAL)
    with pytest.raises(MatterBookError):
        update_entry(path, entry.id, nonsense=True)


def test_redacted_entry_hides_the_code(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR, name="Lamp")
    redacted = entry.redacted()
    assert redacted["name"] == "Lamp"
    assert redacted["code"] != QR
    assert redacted["code_type"] == "qr"
    assert redacted["discriminator"] == 3840


def test_the_book_is_written_privately(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    add_entry(path, QR)
    assert path.stat().st_mode & 0o077 == 0


def test_unknown_and_missing_columns_are_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    path.write_text(
        "id,name,code,future_column\nabc,Lamp,{code},something\n".format(code=QR),
        encoding="utf-8",
    )
    (entry,) = read_entries(path)
    assert entry.name == "Lamp"
    assert entry.code == QR
    # Columns the file did not carry fall back to their defaults.
    assert entry.status == "pending"
    assert entry.attempt_count == 0


def test_rows_without_a_code_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    path.write_text("id,name,code\nabc,Lamp,\n", encoding="utf-8")
    assert read_entries(path) == []


def test_a_file_that_is_not_a_matterbook_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "other.csv"
    path.write_text("alpha,beta\n1,2\n", encoding="utf-8")
    with pytest.raises(MatterBookError):
        read_entries(path)


def test_write_entries_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    write_entries(path, [entry])
    assert [item.name for item in tmp_path.iterdir()] == ["matterbook.csv"]
