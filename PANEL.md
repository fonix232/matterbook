# The MatterBook panel: design

A sidebar tab for browsing the book, resolving the conflicts auto-pairing
refuses to guess at, and capturing device labels.

[DESIGN.md](DESIGN.md) covers the integration itself. This document covers the
interface, and assumes its vocabulary: *entry* (a row of the book), *discovered
device* (something advertising that it is commissionable), *match*, *ambiguous*,
*trial*.

## Why a panel and not ingress

Ingress is a Supervisor feature: `ingress: true` lives in an **add-on's** config
and Supervisor proxies `/api/hassio_ingress/<token>/`. Using it would force
MatterBook to be an add-on, which is the thing [DESIGN.md](DESIGN.md) argues
against — and would restrict it to HA OS and Supervised installs.

A **custom panel** gives the same "our own web app in a tab", with less:

| | Panel | Ingress add-on |
| --- | --- | --- |
| Auth | The frontend's session; nothing to build | Supervisor token plumbing |
| Data | `hass.callWS` over the existing socket | A second HTTP API |
| Theming | HA's CSS custom properties, light and dark, free | Re-implement |
| Install types | OS, Container, Core, Supervised | OS and Supervised only |
| Runtime | No extra process | A container |

Registration is two calls in `frontend.py`:

```python
await hass.http.async_register_static_paths(
    [StaticPathConfig(PANEL_URL, str(bundle), cache_headers=False)]
)
await panel_custom.async_register_panel(
    hass,
    frontend_url_path="matterbook",
    webcomponent_name="matterbook-panel",
    module_url=f"{PANEL_URL}?hash={bundle_hash}",
    sidebar_title="MatterBook",
    sidebar_icon="mdi:book-lock",
    require_admin=True,
    config={"csv_path": str(csv_path)},
)
```

`require_admin=True` is not decoration: the panel shows setup codes, and a
non-admin user has no business commissioning devices onto the fabric.

The `?hash=` query is the cache-buster. HA serves the bundle with caching
disabled, but browsers and the frontend's module loader both hold onto ES
modules aggressively; without a changing URL, an update leaves users on the old
panel until a hard reload.

## Data flow

Everything goes over the WebSocket connection the frontend already holds. No
REST, except for images (which cannot be fetched into an `<img>` any other way).

```
┌─────────────┐   matterbook/subscribe    ┌──────────────┐
│   panel     │ ────────────────────────► │  websocket   │
│ (TypeScript)│ ◄──────────────────────── │   commands   │
└─────────────┘   book + devices, live    └──────┬───────┘
       │                                         │
       │ <img src=signed path>                   │ reads/commands
       ▼                                         ▼
┌─────────────┐                          ┌──────────────┐
│ label view  │                          │ coordinator  │
│ (signed)    │                          └──────┬───────┘
└─────────────┘                                 │
                                         ┌──────┴───────┐
                                         │ book + matter│
                                         └──────────────┘
```

### Command surface

| Command | Returns / does |
| --- | --- |
| `matterbook/subscribe` | The book, the discovered devices, matches, ambiguities and trials — then pushes the same payload on every coordinator update, so the panel never polls |
| `matterbook/add` | Adds a row; returns it |
| `matterbook/remove` | Removes a row by `entry_id` |
| `matterbook/update` | Edits name, area, notes, enabled |
| `matterbook/scan` | Forces a scan |
| `matterbook/pair` | Commissions one entry, optionally against one named device — this is what conflict resolution calls |
| `matterbook/label/upload` | Stores a captured label image for an entry |
| `matterbook/label/sign` | Returns a signed URL for an entry's label image |

Codes are **masked in every payload**. The panel never receives a passcode, and
therefore cannot leak one into a screenshot, a browser cache or a bug report.
The one exception is deliberate: an explicit `matterbook/reveal` for a single
entry, when someone needs to read a code out to another controller's app.

### Why subscribe rather than poll

The coordinator already notifies its listeners on every scan. A subscription
turns that straight into a live view: a device entering pairing mode appears in
the panel within a scan interval, and a pairing that succeeds updates the row
without a refresh. `websocket_api.async_response` plus
`coordinator.async_add_listener` is about fifteen lines, and it removes the
timer the panel would otherwise need.

## Screens

Actions belong to the page they act on, rather than to a toolbar that follows
you around: **Add entry** and **Import from Matter** are about the book, and
**Scan now** is about what is advertising. A single shared toolbar made it look
as though scanning had something to do with the row you were looking at.

### 1. The book

The default view. One row per entry:

`name · what it is · status · identity strength · label thumbnail`

Identity strength is shown plainly, because it decides what MatterBook is
allowed to do on its own: **exact** (a QR payload), **short** (a manual code),
**none** (a bare passcode). A row that has spent its trial says so.

Actions per row: **change** the code (or **Add code** on an imported row, which
is the same screen), reveal code, capture or replace label, delete. Bulk select
for delete and enable/disable.

The code editor is one element used twice — adding a device and correcting an
existing entry want the same thing, so they share it. Replacing a code that is
already there is an explicit flag through to the backend, so a row can never be
repointed at a different device as a side effect of an edit; and the
discriminators the old code implied are cleared, because the new code may not
describe the same hardware.

### 2. Devices in pairing mode

What is advertising right now, from both discovery sources, annotated with what
MatterBook made of each one:

* **matched** — the entry it belongs to, and whether pairing is under way;
* **ambiguous** — the entries it could be, with a *Resolve* button;
* **unknown** — nothing in the book claims it, with an *Add to book* button that
  opens the capture flow pre-filled with the discriminator and vendor.

Signal strength and source (which proxy heard it) are worth showing: they are
how you work out *which physical device* a row of numbers is, when two identical
lamps are both blinking.

### 3. Resolve

The screen that earns the whole panel. It appears when a code could mean several
devices, or a device could be several entries.

> **`34970112332` could be any of these three devices.**
> The manual pairing code only carries four bits of discriminator, so
> MatterBook will not guess. Which one is it?
>
> | | Device | Vendor | Seen by | Signal |
> |---|---|---|---|---|
> | ○ | `discriminator 3840` | Nanoleaf | esp-proxy-hall | −52 dBm |
> | ○ | `discriminator 3901` | — | esp-proxy-attic | −81 dBm |
> | ○ | `discriminator 3999` | Nanoleaf | Home Assistant | −67 dBm |
>
> *[ Identify each one ]* *[ Pair with selected ]*

Two things make this usable rather than a numbers quiz:

* **Signal and source** narrow it physically — the one heard by the hall proxy
  at −52 dBm is the one in the hall.
* **Identify** is the honest answer to "I still can't tell". For an *already
  commissioned* device the Identify cluster blinks it. For an uncommissioned one
  there is no such command, so the fallback is human: power-cycle the device you
  mean, watch which row disappears and comes back.

Choosing a device calls `matterbook/pair` with both the entry and that device,
which goes down the same path auto-pairing uses: the discriminator from the
chosen device is folded into a synthesised payload, so the commissioning is
addressed exactly at it. Resolution is therefore not a special case in the
backend — it is the ordinary path with the ambiguity removed by a human.

### 4. Capture

Add a device by scanning it: *scan or photograph the code* → *name it*.

`ha-qr-scanner` was the obvious thing to reuse, but it is an internal frontend
component and is only defined once Home Assistant has loaded the chunk that
imports it — a custom panel cannot rely on it being there. So the panel carries
its own, which also means it behaves the same in every context:

* **`BarcodeDetector`** where the browser has it: native, fast, free.
* **jsQR**, bundled, everywhere else. This is what makes iOS work at all —
  Safari does not implement `BarcodeDetector`, and the companion app's WebView
  is Safari. It is most of the panel bundle's size, and worth it.

Two constraints shape the interface more than the decoders do:

* A live camera needs `getUserMedia`, which browsers expose only in a **secure
  context**. Home Assistant over plain `http://` on a LAN is not one, so on many
  ordinary installs live scanning cannot work. The panel checks
  `isSecureContext` and says so plainly rather than failing at the permission
  prompt.
* `<input type="file" capture="environment">` has no such restriction and opens
  the camera app on a phone. It is offered always, and is the reason the feature
  is usable over plain HTTP at all.

## The label pipeline

The goal is an archive of the **sticker as printed** — the code, the digits, the
vendor's logo, the device ID some vendors print for exactly this reason — flat,
cropped and legible. Not a regenerated QR: that would be sharper and useless.

### Rectify

`QRCodeDetector.detect()` gives the code's four corners. Because a QR is known
to be square, those four correspondences give a homography — which is applied to
the **whole frame**, not just the code. The label comes along with it, flat and
at the right aspect ratio.

The by-product matters as much as the rectification: the homography fixes how
many pixels one QR module is. Every later measurement is then expressed in
**modules**, which makes the whole pipeline independent of how far away the
photo was taken from.

A label carrying a second QR — a vendor app link, a serial — is why the code is
decoded before it is trusted as the reference: only a payload starting `MT:`
is the Matter code.

### Crop

Three regions, unioned, then 10% padding:

1. **The code**, from the detector.
2. **The printed digits**: a morphological gradient followed by horizontal
   dilation merges glyphs into text lines; keep the lines whose height and
   distance from the code are plausible *in modules*. Searching by module rather
   than pixel is also what lets this work when the digits are set below the code
   rather than beside it.
3. **The sticker border**: Canny plus `findContours`, keeping quads that
   *contain* the code, and taking the smallest one that is meaningfully larger
   than the code itself. That last qualifier is load-bearing: the code's quiet
   zone is often a printed white box, and "largest contour containing the QR"
   picks out the device casing instead.

If no border is found — borderless print, dark label, a sticker that bleeds into
the housing — fall back to the union of code and digits, still padded. Including
a little casing is a much smaller failure than guillotining the logo.

### Improve

Sharpness comes from frames, not filters:

* **Multi-frame averaging.** Several frames, aligned by the per-frame
  homography, averaged. Noise falls as √n and real detail survives. Classic, no
  model, and phones give bursts away for free.
* **Flat-field correction**: divide by a heavily blurred copy to kill the
  gradient a phone flash leaves across a glossy sticker.
* **Unsharp masking**, gently, last.

Upscaling models are optional polish on top, and are the only part that wants an
add-on.

### Cross-check

OCR the digits and compare them with the decoded payload's passcode. Two
independent readings of one secret: agreement is strong evidence both are right.

The 11-digit manual code carries a **Verhoeff check digit**, which
`pairing_code.verhoeff_checksum` already computes — so a digit-level OCR error
is *detectable*, and usually correctable by trying single-digit substitutions
until the checksum validates. A damaged QR with legible digits still yields a
usable entry, and vice versa.

### Store

`config/matterbook/labels/<entry_id>.webp`, beside the book, referenced by a
`label_image` column. WebP at quality ~90, normalised to a fixed
modules-per-pixel so every label in the archive is the same effective DPI and
they look like a set.

Optionally the original frame as `<entry_id>.original.webp`, for reprocessing
later when the pipeline improves.

Two rules:

* **EXIF is stripped before writing.** Phone photos carry GPS, and a book of
  device labels tagged with the coordinates of the house they are in is not
  something to put in a backup.
* **Label images are as sensitive as the book.** The passcode is legible in the
  picture. They must never go under `config/www/`, which is served without
  authentication.

Serving them needs one wrinkle: `<img src>` cannot send an auth header. The HA
idiom is a signed path — the panel asks over WebSocket for a URL signed with
`http.auth.async_sign_path`, with a short expiry, and uses that. Same mechanism
camera snapshots use.

### Where it runs

| Stage | Runs in | Why |
| --- | --- | --- |
| Capture, decode | Browser | `ha-qr-scanner`, already there |
| Homography, crop, averaging | Browser | 3×3 matrix maths and canvas; no dependency, no server load, works on the phone that took the photo |
| Encode WebP, strip EXIF | Browser | `canvas.toBlob` re-encodes, which drops EXIF as a side effect |
| Upload, store | Integration | One WebSocket command |
| OCR, upscaling | Add-on (optional) | OpenCV and models do not belong in an integration |

Doing the geometry in the browser is what keeps the add-on **optional** rather
than required — the pipeline degrades to "no OCR cross-check" without it, not to
"no labels".

## Build

TypeScript and Lit, bundled by esbuild into a single ES module that the
integration serves as a static file:

```
panel/src/*.ts  ──esbuild──►  custom_components/matterbook/panel/matterbook-panel.js
```

The built bundle is **committed**, because the people installing this have
Home Assistant, not Node. CI rebuilds it and fails if the committed copy is
stale, so the two cannot drift.

Lit is bundled in rather than imported from the frontend: HA's internal module
paths are not a public API, and a 30 KB dependency is a cheaper price than
breaking on a frontend refactor. Styling uses HA's CSS custom properties
(`--primary-text-color`, `--card-background-color`, …) so the panel follows the
user's theme, including dark mode, without knowing anything about it.

## Order of work

1. Panel shell, registration, `matterbook/subscribe`, the book view. *(done)*
2. Devices view and **Resolve**. *(done)*
3. Capture: scan a code, add a row, correct an existing one. *(done)*
4. Labels: photograph, rectify, crop, store, display.
5. Optional add-on: OCR cross-check and upscaling.
