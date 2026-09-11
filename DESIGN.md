# MatterBook: design and rationale

Why this is a custom integration, what the platform actually offers as of
Home Assistant 2026.9, and which parts of the problem are hard.

## The problem

Zigbee pairing was easy because it was insecure: reset the device, open the
network, done. Matter replaced that with a per-device passcode, which is a real
security improvement and a real chore. Commissioning twenty devices means
twenty trips through a phone app with twenty stickers in hand, and the stickers
then live in a drawer — so re-commissioning after a controller rebuild means
finding them again.

MatterBook is two things:

1. a **book**: the codes, in a file you own, next to the names and rooms they
   belong to;
2. an **automation**: watch for devices in pairing mode, and commission the ones
   the book recognises.

## What the platform gives us (verified against HA `dev`, 2026.9)

Home Assistant 2026.6 made Home Assistant itself able to commission Matter
devices without a phone, and the pieces it did that with are the pieces
MatterBook stands on.

* The Matter server is `matterjs-server` (Matter Server add-on 8.5.0+). The
  `matter` integration requires `matter-python-client==1.4.0` and
  `matter-ble-proxy==0.7.1`.
* With the add-on's `ble_proxy` option on, the server exposes a `/ble`
  WebSocket and **Home Assistant is the proxy client**:
  `homeassistant/components/matter/ble_proxy.py` wires a `BleScanSource` and
  `BleDeviceResolver` into HA's `bluetooth` component. Every adapter and ESPHome
  Bluetooth proxy already registered there can therefore carry commissioning
  traffic — a device is commissioned where it sits, not where the server is.
* `MatterClient.discover_commissionable_nodes()` returns `CommissionableNodeData`
  (long discriminator, vendor and product ID, mDNS instance name, addresses,
  commissioning mode).
* `MatterClient.commission_with_code(code, network_only=…)` commissions one
  device from a QR payload or manual pairing code.

Two constraints follow, and they decide the architecture:

* **Commissioning is not an action.** `matter/services.yaml` registers lock and
  water-heater actions only. Commissioning is reachable through the admin
  WebSocket command `matter/commission` or the config flow, and no automation
  can call either.
* **Home Assistant exposes no discovery command at all.** There is no
  `matter/discover` WebSocket command; `discover` exists only on the Matter
  server's own socket.

## The decision: a custom integration

| Option | Verdict |
| --- | --- |
| **Custom integration** | **Chosen.** In-process access to the live `MatterClient`; native `text`/`button`/`number`/`switch`/`sensor` entities; config flow and options; works on HA OS, Container and Core alike; can name the device and drop it in its area afterwards through the device registry. |
| Add-on | Workable — an add-on could skip Home Assistant and drive the Matter server's WebSocket directly, and BLE commissioning would still work because the server does that part. But it is HA OS/Supervised only, entities would have to come back in over MQTT or REST, and it doubles the auth surface. It buys isolation this problem does not need. |
| Core change | Not required by anything here. A file of passcodes is not an upstream feature. The *auto-pair a known device* half could be proposed to core later, on its own merits. |

The cost of the integration route is that reaching the client means
`entry.runtime_data.adapter.matter_client` on core's Matter config entry — a
private path that core may rename. `matter_link.py` guards every hop and falls
back to opening its own client against the Matter entry's public `url`, using
the `matter-python-client` that is already installed. A rename upstream should
cost a slower code path, not a broken integration.

Where an add-on *would* earn its place is the image pipeline (see below).

## The hard part: which device does this code open?

A device label carries up to three things, and they identify the device to very
different degrees:

| On the label | Carries | Narrows to |
| --- | --- | --- |
| QR payload `MT:…` | 12-bit discriminator, VID, PID, passcode | 1 in 4096 |
| Manual pairing code, 11 or 21 digits | 4-bit **short** discriminator, passcode, and VID/PID only in the 21-digit form | 1 in 16 |
| Setup passcode, 8 digits | passcode only | nothing |

A commissionable device advertises its **long** discriminator over both BLE
(service data under UUID `0xFFF6`) and mDNS (`_matterc._udp`). So a QR row can
be matched against what is advertising and paired with confidence. A manual code
cannot: in a house with a dozen Matter devices, a 1-in-16 match is a coin toss,
and pairing the wrong device is not a harmless mistake.

MatterBook therefore separates *matching* from *trying*:

* **Match** (`matching.py`): a row may claim a device only if the identity it
  carries agrees, and known vendor/product IDs do not conflict. A match is acted
  on only when it is unambiguous **in both directions** — one row, one device.
  An exact (long-discriminator) match outranks short-discriminator rivals for the
  same device. Everything else is reported as ambiguous and left to a human.
* **Trial**: when exactly one row and exactly one device are left unaccounted
  for, there is nothing else either could be, so the row may spend **one** blind
  attempt. Once per row, ever — tracked in the book's `trial_used` column and
  written *before* the attempt, so a restart mid-commission cannot hand out a
  second free guess. Repeatedly throwing passcodes at devices is both a guessing
  attack and a way to trip a device's PASE attempt limit, which on some hardware
  needs a factory reset to clear.

Two mechanisms make weak codes work properly once a device is in front of us:

* **Synthesised payloads.** A manual code or bare passcode is combined with the
  discriminator the device is *advertising* into a valid QR payload
  (`pairing_code.encode_qr_payload`). That addresses the device exactly, and it
  lets a printed passcode commission over BLE — which on its own it cannot do,
  since BLE commissioning needs a discriminator to find anything. The encoder is
  tested by rebuilding the SDK's own reference payload byte for byte.
* **Backfill.** After a successful pairing, the node's Basic Information cluster
  gives the real vendor ID, product ID, serial number and unique ID, and those
  are written into the row. A book filled from bare passcodes teaches itself:
  the blind attempt happens once, and every later match against that row is
  exact.

This is what makes "type in the 8-digit code and it just pairs" safe as a
default rather than reckless: it is allowed exactly when it cannot be wrong,
it never repeats, and it upgrades itself into an exact identity afterwards.

## Discovery: two sources

1. The Matter server's `discover`, over mDNS and (where the server has BLE) over
   BLE.
2. Home Assistant's own Bluetooth cache, read directly. HA already collects
   advertisements from every adapter and ESPHome proxy, so this costs nothing,
   needs no scan of our own, and covers devices only a far-away proxy can hear.
   The 8-byte `0xFFF6` service data is decoded in `advertisement.py`.

Results are merged by discriminator, and the server's view wins because it
carries the addresses that decide whether commissioning can stay on IP.

## Storage

A CSV at `config/matterbook/database.csv`, written atomically and `0600`, with
label images destined for `labels/` beside it so the archive is one directory. Not HA's `Store`
helper, because the point of a *book* is that you can open it, read it, diff it,
grep it and back it up without Home Assistant's help. Unknown columns are
ignored and missing ones take their defaults, so a book written by another
version still loads.

The rows contain passcodes. They are masked everywhere they could leak —
entity attributes, events, diagnostics and log lines — and the file deserves the
same treatment as `secrets.yaml`.

## Importing an existing fabric

A snapshot of a running Matter setup recovers everything except the one thing
that matters most.

**Not the setup codes.** Commissioning is PASE (SPAKE2+): the device stores a
verifier derived from the passcode, and the commissioner discards the passcode
when it is done. The server's own node record (`MatterNodeData`) has no field
for one, and across the whole server API a passcode appears only as an *input*.
`open_commissioning_window` does return a code, but that is the Enhanced
Commissioning Method minting a temporary passcode that dies with the window —
and a factory-reset device reverts to the passcode printed on its label. **The
sticker is the only copy**, which is the reason this project exists.

**Everything else.** Vendor, product, serial number and unique ID come from the
Basic Information cluster; the name and area come from Home Assistant's device
registry. `importer.py` turns each node into a row with `status=code_missing`.

Such a row carries no discriminator, so the matcher cannot act on it and the
trial rule will not touch it — inventory, not a pairing candidate. Its value is
an asset list, names and areas preserved for the next rebuild, and a checklist
of stickers to find. `set_entry_code` completes a row when its sticker turns up:
the one place a code may be added after the fact, because the identity columns
derived from it are all recomputed there.

## Deliberate limits of the MVP

* One MatterBook per Home Assistant, one Matter fabric.
* Commissioning is serial: the server does one at a time, and a round trip can
  take minutes.
* Deleting by row number shifts the other rows; automations should use the
  stable `id`.
* Wi-Fi and Thread credentials must already be set on the Matter server for
  devices that are not yet on the network. MatterBook checks and says so when a
  pairing fails, but does not set them.

## Where this goes next

* **A management UI.** The conflict this design refuses to guess at — *which of
  these fifteen advertising devices does this code belong to?* — has an obvious
  answer if you can show the list and let someone pick, the way zigbee2mqtt does.
  That is the natural next piece, and the trial/ambiguity machinery above is
  already producing exactly the data such a page needs.
* **Scanning rather than typing.** HA's frontend ships `ha-qr-scanner`: in a
  browser it decodes with a ZXing WebAssembly build HA serves itself, and inside
  the companion app it hands off to the app's native barcode scanner. Scanning a
  sticker straight into the book is a frontend job, not a backend one.
* **The image lab.** Dewarping a photographed sticker (perspective transform,
  binarise, OCR the digits) is the one part that wants OpenCV and does not belong
  in an integration. That is an add-on — and mostly a fallback, because once a
  payload decodes you can regenerate a pristine QR from it rather than restore
  the photograph.
