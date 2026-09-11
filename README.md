# MatterBook

A Home Assistant custom integration that keeps a book of your Matter setup codes
and commissions the devices in it automatically when they turn up in pairing
mode.

Matter's pairing codes are the price of its security, and with a large install
they become a chore: every device needs its own code, typed into a phone, once
per controller rebuild. MatterBook stores those codes next to the name and room
each device belongs to, watches for devices advertising that they are
commissionable, and pairs the ones it recognises.

For *why* this is an integration rather than an add-on, and how the matching
rules keep it from pairing the wrong device, see [DESIGN.md](DESIGN.md).

## Requirements

* Home Assistant 2026.6 or newer, with the **Matter** integration set up.
* A Matter server (the Matter Server add-on 8.5.0+, or your own
  `matterjs-server`).
* For devices that are not yet on your network: Bluetooth. Either an adapter on
  the server, or the add-on's `ble_proxy` option, which lets Home Assistant
  relay BLE through any adapter or **ESPHome Bluetooth proxy** it already knows —
  so a device can be commissioned where it sits.
* Wi-Fi and/or Thread credentials stored on the Matter server, for wireless
  devices that still have to join the network.

## Installing

Copy `custom_components/matterbook` into your Home Assistant `config/custom_components/`
directory and restart:

```bash
scp -r custom_components/matterbook root@homeassistant:/config/custom_components/
```

Then add **MatterBook** from *Settings → Devices & services → Add integration*.

> **HACS:** not yet. HACS reads a repository's newest release tag as the
> version, and this monorepo publishes releases for its other components too, so
> HACS would report nonsense here. The integration is laid out so it can be split
> into its own repository (`git subtree split -P homeassistant/matterbook`) when
> that matters; `hacs.json` is already in place for that move.

## Using it

### Adding a device

Fill in the text fields and press **Add entry**:

| Entity | What it is |
| --- | --- |
| `text.matterbook_new_entry_setup_code` | The QR payload (`MT:…`), the 11- or 21-digit manual pairing code, or the bare 8-digit passcode |
| `text.matterbook_new_entry_name` | What the device should be called once paired |
| `text.matterbook_new_entry_area` | Which area it should land in |
| `text.matterbook_new_entry_notes` | Anything you want to remember |
| `button.matterbook_add_entry` | Files the row and clears the fields |

By default MatterBook scans immediately after a row is added — if the device is
already blinking at you, it pairs then and there.

**Prefer the QR payload.** It carries the full discriminator, so MatterBook can
always tell which device a row means. A manual code narrows to one device in
sixteen, and a bare passcode names no device at all; those rows still work, but
only get a single blind attempt each, and only when nothing else could be meant
(see [DESIGN.md](DESIGN.md)).

### Removing one

Set `number.matterbook_row_to_delete` to the row number shown on the Entries
sensor, then press `button.matterbook_delete_entry`. Row numbers shift after a
deletion; automations should use the stable `entry_id` with the
`matterbook.remove_entry` action instead.

### Watching it work

| Entity | Shows |
| --- | --- |
| `sensor.matterbook_entries` | How many rows, with all of them (codes masked) as attributes |
| `sensor.matterbook_pending_entries` | Rows still waiting for their device |
| `sensor.matterbook_commissionable_devices` | What is in pairing mode right now, including devices no row claims |
| `sensor.matterbook_last_scan` / `..._last_paired` | When |
| `switch.matterbook_auto_pairing` | Whether a scan may actually pair. Off still scans and reports |
| `button.matterbook_scan_now` | Scan without waiting for the next sweep |

### Actions

`matterbook.add_entry`, `matterbook.remove_entry`, `matterbook.scan`,
`matterbook.pair` and `matterbook.reload_book` — the last one after editing the
CSV by hand.

### Events

`matterbook_discovered` (a commissionable device no row claims),
`matterbook_paired`, `matterbook_pair_failed`, `matterbook_trial_pairing` and
`matterbook_ambiguous_match` (a code that could mean several devices — this is
the one to notify yourself about).

```yaml
automation:
  - alias: Tell me about unknown Matter devices
    triggers:
      - trigger: event
        event_type: matterbook_discovered
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            A Matter device is in pairing mode (discriminator
            {{ trigger.event.data.discriminator }}) and is not in the MatterBook.
```

## The book

A CSV, by default `config/matterbook/database.csv`, written atomically and `0600`:

```csv
id,name,code,vendor_id,product_id,discriminator,short_discriminator,serial_number,unique_id,area,notes,enabled,status,node_id,paired_at,last_attempt_at,attempt_count,trial_used,last_error
a1b2c3d4e5f6,Kitchen ceiling,MT:Y.K9042C00KA0648G00,65521,32768,3840,15,,,Kitchen,behind the trim,true,paired,12,2026-09-11T09:14:02+00:00,2026-09-11T09:14:02+00:00,0,false,
```

Scanned label images will live beside it in `config/matterbook/labels/`, so the
whole archive — book and stickers — moves, backs up or gets excluded as one
directory.

Edit it outside Home Assistant if you like — then call
`matterbook.reload_book`. Unknown columns are ignored and missing ones take
their defaults, so the file survives both older and newer versions.

After a device pairs, what it turned out to be (vendor, product, serial, unique
ID) is written back into its row, so a row added from a bare passcode ends up
knowing exactly which device it belongs to.

> **The book contains passcodes.** Anyone holding a row can commission that
> device while it is uncommissioned. Treat the file like `secrets.yaml`: keep it
> out of git, out of shared backups, and off any share you would not put your
> Home Assistant credentials on. MatterBook masks codes in entity attributes,
> events, diagnostics and logs, but the file itself is the real thing.

## Options

*Settings → Devices & services → MatterBook → Configure*

| Option | Default | What it does |
| --- | --- | --- |
| Scan interval | 300 s | How often to look for devices in pairing mode |
| Pair known devices automatically | on | The switch entity overrides this at runtime |
| Allow one blind attempt per entry | on | Lets a passcode-only row try the single device in front of it, once |
| Try to pair straight after adding | on | Scan the moment a row is added |
| Only pair on an exact discriminator match | off | Act only on rows stored as a QR payload |
| Also scan Home Assistant's Bluetooth | on | Read HA's own advertisements as a second discovery source |
| Apply the stored name and area | on | Rename and place the device after pairing |
| Commissioning timeout | 180 s | Per attempt |
| Attempts before giving up | 3 | Per row |
| Cooldown after a failure | 900 s | Doubles per attempt, up to 8× |

## Development

```bash
cd homeassistant/matterbook
pip install ruff pytest
ruff check .
python -m pytest tests -q
```

`pairing_code.py`, `store.py`, `matching.py` and `advertisement.py` import
nothing from Home Assistant and are tested directly; the rest is the Home
Assistant wiring.
