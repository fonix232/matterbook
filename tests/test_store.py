"""Tests for the CSV-backed MatterBook."""

from __future__ import annotations

from pathlib import Path

import pytest

from matterbook.pairing_code import InvalidSetupCode
from matterbook.store import (
    STATUS_CODE_MISSING,
    STATUS_PAIRED,
    MatterBookError,
    add_entry,
    add_imported_entry,
    mark_failed,
    mark_paired,
    mark_trial_used,
    read_entries,
    remove_entry,
    set_entry_code,
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
        f"id,name,code,future_column\nabc,Lamp,{QR},something\n",
        encoding="utf-8",
    )
    (entry,) = read_entries(path)
    assert entry.name == "Lamp"
    assert entry.code == QR
    # Columns the file did not carry fall back to their defaults.
    assert entry.status == "pending"
    assert entry.attempt_count == 0


def test_a_row_without_a_code_is_inventory_not_junk(tmp_path: Path) -> None:
    # This is what an imported device looks like until its sticker turns up.
    path = tmp_path / "matterbook.csv"
    path.write_text("id,name,code,status\nabc,Lamp,,code_missing\n", encoding="utf-8")
    (entry,) = read_entries(path)
    assert entry.name == "Lamp"
    assert entry.code == ""
    # It cannot pair anything: there is no code to pair with.
    assert entry.is_pairable is False
    assert entry.identity_strength == "none"
    assert entry.redacted()["code_type"] == "missing"


def test_rows_with_nothing_in_them_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    path.write_text("id,name,code\nabc,,\n", encoding="utf-8")
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


def test_pairing_backfills_what_the_device_turned_out_to_be(tmp_path: Path) -> None:
    # A row added from a bare passcode knows nothing about the device. After the
    # first pairing it does, so every later match against it is exact.
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, "20202021", name="Mystery plug")
    assert entry.vendor_id is None
    assert entry.identity_strength == "none"

    mark_paired(
        path,
        entry.id,
        node_id=7,
        vendor_id=65521,
        product_id=32768,
        serial_number="SN-12345",
        unique_id="ABCDEF",
    )
    (stored,) = read_entries(path)
    assert stored.vendor_id == 65521
    assert stored.product_id == 32768
    assert stored.serial_number == "SN-12345"
    assert stored.unique_id == "ABCDEF"
    assert stored.node_id == 7


def test_trial_used_survives_a_round_trip_and_defaults_to_false(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    assert entry.trial_used is False

    mark_trial_used(path, entry.id)
    (stored,) = read_entries(path)
    assert stored.trial_used is True


def test_an_older_book_without_the_new_columns_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    path.write_text(f"id,name,code,enabled\nabc,Lamp,{QR},\n", encoding="utf-8")
    (entry,) = read_entries(path)
    # An empty cell means each column's own default, not a blanket true.
    assert entry.enabled is True
    assert entry.trial_used is False


def test_identity_strength_of_each_code_form(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    assert add_entry(path, QR).identity_strength == "exact"
    assert add_entry(path, MANUAL).identity_strength == "short"
    assert add_entry(path, "20202021").identity_strength == "none"


def test_importing_a_commissioned_device_makes_a_codeless_row(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_imported_entry(
        path,
        node_id=12,
        name="Hall lamp",
        area="Hall",
        vendor_id=65521,
        product_id=32768,
        serial_number="SN-1",
        unique_id="UID-1",
    )
    assert entry is not None
    assert entry.status == STATUS_CODE_MISSING
    assert entry.code == ""
    assert entry.node_id == 12
    # It knows what the device is, but not which code opens it, so it must never
    # be a pairing candidate.
    assert entry.vendor_id == 65521
    assert entry.is_pairable is False

    (stored,) = read_entries(path)
    assert stored.name == "Hall lamp"
    assert stored.area == "Hall"
    assert stored.status == STATUS_CODE_MISSING


def test_importing_twice_does_not_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    assert add_imported_entry(path, node_id=12, unique_id="UID-1") is not None
    assert add_imported_entry(path, node_id=12, unique_id="UID-1") is None
    assert len(read_entries(path)) == 1


def test_import_matches_an_existing_row_by_identity_not_just_node_id(tmp_path: Path) -> None:
    # After a controller rebuild the same device comes back with a different node
    # id; the serial number and unique ID are what survive.
    path = tmp_path / "matterbook.csv"
    add_imported_entry(path, node_id=12, serial_number="SN-1")
    assert add_imported_entry(path, node_id=99, serial_number="SN-1") is None
    assert len(read_entries(path)) == 1


def test_set_entry_code_completes_an_imported_row(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    imported = add_imported_entry(path, node_id=12, name="Hall lamp", serial_number="SN-1")
    assert imported is not None

    entry = set_entry_code(path, imported.id, QR)
    assert entry.code == QR
    assert entry.discriminator == 3840
    assert entry.short_discriminator == 15
    # It was already commissioned, so it stays paired rather than becoming pending.
    assert entry.status == STATUS_PAIRED
    # The import's own identity survives the decode.
    assert entry.serial_number == "SN-1"
    assert entry.name == "Hall lamp"


def test_set_entry_code_rejects_bad_and_duplicate_codes(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    imported = add_imported_entry(path, node_id=12)
    assert imported is not None

    with pytest.raises(InvalidSetupCode):
        set_entry_code(path, imported.id, "nonsense")

    add_entry(path, QR)
    with pytest.raises(MatterBookError):
        set_entry_code(path, imported.id, QR)


def test_set_entry_code_refuses_to_overwrite_a_code(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    with pytest.raises(MatterBookError):
        set_entry_code(path, entry.id, MANUAL)


def test_set_entry_code_needs_a_real_entry(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    with pytest.raises(MatterBookError):
        set_entry_code(path, "nope", QR)


def test_replacing_a_code_clears_the_identity_the_old_one_implied(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    assert entry.discriminator == 3840

    # A serial read back from a real device survives; discriminators derived from
    # the old code do not, because the new code may be a different device.
    update_entry(path, entry.id, serial_number="SN-1")
    replaced = set_entry_code(path, entry.id, MANUAL, replace=True)
    assert replaced.code == MANUAL
    assert replaced.discriminator is None
    assert replaced.short_discriminator == 15
    assert replaced.serial_number == "SN-1"


def test_replacing_a_code_still_refuses_a_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    first = add_entry(path, QR)
    add_entry(path, QR_OTHER)
    with pytest.raises(MatterBookError):
        set_entry_code(path, first.id, QR_OTHER, replace=True)


def test_setting_the_same_code_again_is_harmless(tmp_path: Path) -> None:
    path = tmp_path / "matterbook.csv"
    entry = add_entry(path, QR)
    same = set_entry_code(path, entry.id, QR, replace=True)
    assert same.code == QR
    assert same.discriminator == 3840
