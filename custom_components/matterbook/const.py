"""Constants for the MatterBook integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "matterbook"
MATTER_DOMAIN: Final = "matter"

# Everything MatterBook owns lives in one directory under the Home Assistant
# configuration: the book, the label images, anything added later. It is not
# configurable — one known location is worth more than the flexibility, because
# it is the directory you back up, exclude from git, and copy to a new install.
DATA_DIRNAME: Final = "matterbook"
CSV_FILENAME: Final = "database.csv"
LABEL_DIRNAME: Final = "labels"

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_AUTO_PAIR: Final = "auto_pair"
CONF_PAIR_TIMEOUT: Final = "pair_timeout"
CONF_MAX_ATTEMPTS: Final = "max_attempts"
CONF_RETRY_COOLDOWN: Final = "retry_cooldown"
CONF_REQUIRE_EXACT_MATCH: Final = "require_exact_match"
CONF_APPLY_METADATA: Final = "apply_metadata"
CONF_USE_BLUETOOTH: Final = "use_bluetooth"
CONF_ALLOW_TRIALS: Final = "allow_trials"
CONF_PAIR_ON_ADD: Final = "pair_on_add"

DEFAULT_SCAN_INTERVAL: Final = 300
DEFAULT_PAIR_TIMEOUT: Final = 180
DEFAULT_MAX_ATTEMPTS: Final = 3
DEFAULT_RETRY_COOLDOWN: Final = 900
DEFAULT_AUTO_PAIR: Final = True
DEFAULT_REQUIRE_EXACT_MATCH: Final = False
DEFAULT_APPLY_METADATA: Final = True
DEFAULT_USE_BLUETOOTH: Final = True
DEFAULT_ALLOW_TRIALS: Final = True
DEFAULT_PAIR_ON_ADD: Final = True

SERVICE_ADD_ENTRY: Final = "add_entry"
SERVICE_REMOVE_ENTRY: Final = "remove_entry"
SERVICE_SCAN: Final = "scan"
SERVICE_PAIR: Final = "pair"
SERVICE_RELOAD_BOOK: Final = "reload_book"
SERVICE_IMPORT: Final = "import_from_matter"
SERVICE_SET_CODE: Final = "set_code"

ATTR_CODE: Final = "code"
ATTR_NAME: Final = "name"
ATTR_AREA: Final = "area"
ATTR_NOTES: Final = "notes"
ATTR_SERIAL_NUMBER: Final = "serial_number"
ATTR_ROW: Final = "row"
ATTR_ENTRY_ID: Final = "entry_id"

EVENT_DISCOVERED: Final = f"{DOMAIN}_discovered"
EVENT_PAIRED: Final = f"{DOMAIN}_paired"
EVENT_PAIR_FAILED: Final = f"{DOMAIN}_pair_failed"
EVENT_AMBIGUOUS: Final = f"{DOMAIN}_ambiguous_match"
EVENT_TRIAL: Final = f"{DOMAIN}_trial_pairing"
EVENT_IMPORTED: Final = f"{DOMAIN}_imported"

# 16-bit Matter service UUID, in the 128-bit form Home Assistant's bluetooth
# component reports. Commissionable devices put their discriminator, vendor and
# product ID in this advertisement's service data (Matter spec 5.4.2.5.6).
MATTER_BLE_SERVICE_UUID: Final = "0000fff6-0000-1000-8000-00805f9b34fb"
BLE_OPCODE_COMMISSIONABLE: Final = 0x00
BLE_SERVICE_DATA_LENGTH: Final = 8

# How stale a BLE advertisement may be before a scan stops counting it.
BLE_MAX_ADVERTISEMENT_AGE: Final = 60
