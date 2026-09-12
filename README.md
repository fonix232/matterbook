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

### HACS

MatterBook is published from its own repository, because HACS serves one
integration per repository:

**HACS → ⋮ → Custom repositories** → `https://github.com/fonix232/matterbook`,
category **Integration**. Then install MatterBook and restart Home Assistant.

### By hand

Download `matterbook.zip` from a release and unpack it into your configuration:

```bash
unzip matterbook.zip -d /config/custom_components/matterbook/
```

Or copy the directory straight out of this repository:

```bash
scp -r custom_components/matterbook root@homeassistant:/config/custom_components/
```

Either way, restart Home Assistant and add **MatterBook** from
*Settings → Devices & services → Add integration*.

> Development happens here in `network-tools`; `fonix232/matterbook` is the
> publishing mirror, produced by `git subtree split`. [SPLIT.md](SPLIT.md) is the
> runbook for keeping the two in step, and explains why HACS cannot install from
> a monorepo.

## Using it

**MatterBook** appears in the sidebar, admin-only: the panel lists setup codes
and can commission devices onto your fabric.

### The Book page

Everything about entries happens here.

* **Add entry** — scan the QR code with the camera, photograph the label, or
  type the code. Name and area are filled in on the same screen and applied to
  the device once it pairs.
* **Import from Matter** — see below.
* **change** / **Add code** on a row — the same scanner, pointed at an entry
  that already exists, for correcting a mistyped code or filling in an imported
  row once you find its sticker.

Scanning uses the browser's own barcode reader where there is one, and a
bundled decoder everywhere else, so it works on iOS too. Two things to know:

* A **live camera** needs a secure connection. Home Assistant reached over plain
  `http://` on your LAN is not one, and the camera will refuse to open.
* **Take a photo** has no such restriction — on a phone it opens the camera app
  — so that path works regardless, as does typing the code.

**Prefer the QR payload.** It carries the full discriminator, so MatterBook can
always tell which device a row means. A manual code narrows to one device in
sixteen, and a bare passcode names no device at all; those rows still work, but
get a single blind attempt each, and only when nothing else could be meant (see
[DESIGN.md](DESIGN.md)).

### The "In pairing mode" page

What is advertising right now, from both discovery sources, and what MatterBook
made of each one — matched, ambiguous, or unknown. **Scan now** looks again
without waiting for the next sweep, and **Resolve** is where you answer the
question the matcher refuses to guess at.

### Starting from an existing Matter setup

If you already have devices commissioned, press **Import from Matter** (or call
`matterbook.import_from_matter`). Every device on the fabric becomes a row that
knows what it is, what it is called and which area it is in.

Their **setup codes cannot be imported**. A commissioned device keeps a PASE
verifier, not its passcode, and the controller discards the passcode once it is
done — nothing on the fabric is holding it. `open_commissioning_window` mints a
*temporary* code for sharing, but a factory-reset device goes back to the code
printed on its label, so that is no substitute.

What the import gives you is the other 90%: an inventory, names and areas
preserved for the next rebuild, and a checklist —
`sensor.matterbook_entries_without_a_code` — of the stickers still to be found.

### Entities

The panel covers day-to-day use; these exist for automations and dashboards.

| Entity | Shows or does |
| --- | --- |
| `sensor.matterbook_entries` | How many rows, with all of them (codes masked) as attributes |
| `sensor.matterbook_pending_entries` | Rows still waiting for their device |
| `sensor.matterbook_entries_without_a_code` | Imported devices whose sticker has not been found yet |
| `sensor.matterbook_commissionable_devices` | What is in pairing mode right now, including devices no row claims |
| `sensor.matterbook_last_scan` / `..._last_paired` | When |
| `switch.matterbook_auto_pairing` | Whether a scan may actually pair. Off still scans and reports |
| `button.matterbook_scan_now` | Scan without waiting for the next sweep |
| `button.matterbook_import_from_matter` | Snapshot the devices already commissioned here |

### Actions

`matterbook.add_entry`, `matterbook.remove_entry`, `matterbook.scan`,
`matterbook.pair`, `matterbook.import_from_matter`, `matterbook.set_code` and
`matterbook.reload_book` — the last one after editing the CSV by hand.

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

Everything MatterBook owns lives in **`config/matterbook/`**: the book at
`database.csv`, label images in `labels/`, and anything added later. The
location is not configurable — one known directory is worth more than the
flexibility, because it is the thing you back up, keep out of git, and copy to a
new install.

The book is a CSV, written atomically and `0600`:

```csv
id,name,code,vendor_id,product_id,discriminator,short_discriminator,serial_number,unique_id,area,notes,enabled,status,node_id,paired_at,last_attempt_at,attempt_count,trial_used,last_error
a1b2c3d4e5f6,Kitchen ceiling,MT:Y.K9042C00KA0648G00,65521,32768,3840,15,,,Kitchen,behind the trim,true,paired,12,2026-09-11T09:14:02+00:00,2026-09-11T09:14:02+00:00,0,false,
```

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

The sidebar panel is TypeScript, built with esbuild into a single ES module the
integration serves as a static file:

```bash
cd panel
npm ci
npm run check      # typecheck and build
npm run dev        # unminified, rebuild on save
```

The built bundle at `custom_components/matterbook/panel/matterbook-panel.js` is
committed — installers have Home Assistant, not Node — and CI fails if it is
stale. See [panel/README.md](panel/README.md).

## Licence

[MIT](LICENSE).
