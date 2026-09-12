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
| `matterbook/import` | Snapshots the devices already commissioned onto this fabric, as rows waiting for their stickers |
| `matterbook/set_code` | Fills in an imported row's code, or replaces a wrong one |
| `matterbook/options` | The settings, with the backend's defaults already filled in |
| `matterbook/set_options` | Saves settings, which reloads the entry |
| `matterbook/set_label` | Stores a photograph of a row's label, or clears it |
| `matterbook/reveal` | Returns one row's setup code, unmasked |
| `matterbook/identify` | Asks a paired row's device to blink |

Every row in the subscription payload carries signed URLs for its **rendered**
label and its **photographed** one, either `null` when there is none. Signing
per push rather than on request saves a round trip per picture; the URLs are
stable between pushes, for the reason under
[The label pipeline](#the-label-pipeline).

### What "masked" is worth now

Codes are masked in every payload, so a passcode cannot reach a screenshot, a
browser cache or a bug report *as text*. That was once the whole story. It is
not any more: for a row whose code is a QR payload, the panel now draws the code
back into a scannable label and puts it on screen. Anyone looking at the panel
can scan it.

That is not a leak to be closed — it is the feature. A book of setup codes whose
codes cannot be got at is a list of names. It is, though, the reason the panel is
admin-only, and the reason the label endpoints check for an admin themselves
rather than trusting that only the panel will call them.

What masking still buys is narrower and real: codes stay out of the *text* the
browser keeps, and the rows with no honest QR — a manual pairing code, a bare
passcode — stay unreadable until someone asks. `matterbook/reveal` is that ask.
It exists for exactly those rows, since they are the ones with no picture to
scan, and every call is logged: a book of passcodes should be able to say when
one was taken out of it.

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

For the same reason there is no single "busy" flag. One flag meant a scan in
progress greyed out **Add entry** and **Import from Matter**, which share
nothing with it — the actions are independent, so their disabled states are too.
Each action disables only the control that started it.

### 1. The book

The default view. One row per entry:

`label · name · code · identity · status · area`

The label is the **rendered** QR — the entry's own payload drawn back into a
scannable code. Only a QR payload has an honest one: a manual pairing code and a
bare passcode are digits, and drawing those into a QR would produce something
that scans, fails in every Matter app, and looks like a defect here rather than
on the sticker. Those rows say *digits only* instead, which is the more useful
fact: it is the reason to go and find the sticker again.

Identity strength is shown plainly, because it decides what MatterBook is
allowed to do on its own: **exact** (a QR payload), **short** (a manual code),
**none** (a bare passcode). A row that has spent its trial says so.

The label is the photograph where a row has one, and the rendered code where it
does not. The photograph wins because it *is* the label; the rendered code is
only the part of it a machine reads.

Every row has **Edit** — a row imported from the fabric leads with **Add code**,
which is the same dialog said differently — and then, as plain links:

* **Show code**, on any row that has one. See "What masking is worth", above.
* **Identify**, on a row that is paired, to blink the device. Absent on the
  others, because there is nothing to send the command over.
* **Disable**, which leaves a row in the book but takes it out of auto-pairing.
  A disabled row says so and is dimmed: still readable, plainly out of play.
* **Delete**, confirmed, which takes the label photograph with it. Confirmed
  because a code that exists only on a sticker in a loft is not recoverable
  from a commissioned device — this can genuinely lose it.

### 2. Labels

The same book as a wall of stickers. A label is how someone actually finds a
device — you recognise the picture long before you recognise a row of hex — and
it is the fastest way to commission one from a phone, since the codes are on
screen to be scanned. Which is what a book of codes is for, and why the panel is
admin-only.

Rows with no honest QR appear here too, saying why. Knowing a device has no
scannable label is the point of looking.

### 3. Devices in pairing mode

What is advertising right now, from both discovery sources, annotated with what
MatterBook made of each one:

* **matched** — the entry it belongs to, and whether pairing is under way;
* **ambiguous** — the entries it could be, with a *Resolve* button;
* **unknown** — nothing in the book claims it, with an *Add to book* button that
  opens the capture flow pre-filled with the discriminator and vendor.

Signal strength and source (which proxy heard it) are worth showing: they are
how you work out *which physical device* a row of numbers is, when two identical
lamps are both blinking.

### 4. Resolve

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
> *[ Pair with selected ]*

Two things make this usable rather than a numbers quiz:

* **Signal and source** narrow it physically — the one heard by the hall proxy
  at −52 dBm is the one in the hall.
* **Power-cycling** is the honest answer to "I still can't tell": switch the
  device you mean off and on, and watch which row disappears and comes back.

There is deliberately no *Identify* button here. Identify is a cluster command,
and a device in pairing mode has no fabric to accept one over — every device on
this screen is uncommissioned by definition. Identify belongs on a row that is
already **paired**, where the question is which of two identical lamps this row
turned out to be, and that is where the book offers it.

Choosing a device calls `matterbook/pair` with both the entry and that device,
which goes down the same path auto-pairing uses: the discriminator from the
chosen device is folded into a synthesised payload, so the commissioning is
addressed exactly at it. Resolution is therefore not a special case in the
backend — it is the ordinary path with the ambiguity removed by a human.

### 5. Adding and editing

A **modal**, not a page. Adding a device is an interruption to browsing the
book, and it ends by going back to it; a page loses your place on the way out.

Adding opens on a menu rather than a form:

> **Take a photo** — point the camera at the code on the device or its box.
> **Choose a photo** — use a picture of the label already on this device.
> **Type it in** — the QR payload, the pairing code, or the passcode.

The three ways a code gets into the book are genuinely different acts, and a
form with a camera button somewhere in it makes typing look like the intended
one — which is the slowest. **Edit** skips the menu: the row is the answer to
the question it asks, so it goes straight to the form with the row's data in it.

Editing never prefills the code. What a row shows is a mask; the panel is never
told the code, so there is nothing to put in the field. An empty field therefore
means *leave the code alone*, which is also the right default, since most edits
are to the name. Typing a new one replaces it — explicitly, through to the
backend — so a row can never be repointed at a different device as a side effect
of a rename, and the discriminators the old code implied are cleared, because
the new code may not describe the same hardware.

The photograph paths decode in the menu, not in the form, so the file picker
opens inside the click that asked for it. Opening one a render later works most
of the time and fails in exactly the place it matters — a phone, where browsers
are strictest about which gesture opened a picker.

`ha-qr-scanner` was the obvious thing to reuse, but it is an internal frontend
component and is only defined once Home Assistant has loaded the chunk that
imports it — a custom panel cannot rely on it being there. The same goes for
`ha-dialog`, which is why the modal shell is ours too. So the panel carries its
own decoder, which also means it behaves the same in every context:

* **`BarcodeDetector`** where the browser has it: native, fast, free.
* **jsQR**, bundled, everywhere else. This is what makes iOS work at all —
  Safari does not implement `BarcodeDetector`, and the companion app's WebView
  is Safari. It is most of the panel bundle's size, and worth it.

Two constraints shape the interface more than the decoders do:

* A live camera needs `getUserMedia`, which browsers expose only in a **secure
  context**. Home Assistant over plain `http://` on a LAN is not one, so on many
  ordinary installs live scanning cannot work. The panel checks
  `isSecureContext` and says so plainly rather than failing at the permission
  prompt. **Take a photo** then means the camera app rather than a viewfinder.
* `<input type="file" capture="environment">` has no such restriction and opens
  the camera app on a phone. `capture` is set per click rather than baked into
  the markup, because it is the only difference between *take a photo* and
  *choose a photo*.

### 6. Settings

The config entry's options, edited in the panel: how often to scan, whether to
listen over Bluetooth, whether to pair automatically, whether to act on anything
weaker than an exact match, and whether a row may ever spend its one blind
attempt.

These are the entry's options rather than a file of our own, so Home Assistant's
own options flow keeps working and the values survive the way every other
integration's do. Saving them **reloads the entry** — which is what makes a new
scan interval take effect — and a reload drops every listener the coordinator
held, this panel's subscription included. So the page says a reload is coming,
and the panel takes its subscription out again afterwards. Without that last
part the panel keeps showing whatever it last saw, silently, which looks exactly
like a scan that never happens.

### Filling the window

`ha-panel-custom`, the element Home Assistant wraps around the panel, sets
`display: block` and safe-area padding on itself but never a height. A
percentage height resolves against the parent's *definite* height, and there is
not one — so `height: 100%` computed to `auto`, and the panel was only as tall
as its content: the background stopped partway down and everything hugged the
top of an otherwise empty screen.

Viewport units need no parent. `100dvh` follows a mobile browser's toolbars as
they collapse, with the safe-area insets subtracted because the padding that
makes room for them is on the parent; `100vh` above it is the fallback for
anything that does not know `dvh`.

That rule belongs to the panel element alone. It lived in the shared stylesheet,
which every view adopts — so every card would have inherited "at least a
viewport tall", and a page would have come out twice the height it should be.

## The label pipeline

The goal is an archive of the **sticker as printed** — the code, the digits, the
vendor's logo, the device ID some vendors print for exactly this reason — flat,
cropped and legible. Not a regenerated QR: that would be sharper and useless,
because it is not the thing stuck to the device.

### Rectify *(built)*

Both decoders report the code's four corners — `BarcodeDetector` as
`cornerPoints`, jsQR as its four named corners, which come from the finder
patterns and so give the code's own orientation rather than the photograph's.

Because a QR is known to be square, those four correspondences give a
homography, and it is applied to the **whole frame**, not just the code. The
label comes along with it, flat and at the right aspect ratio.

The by-product matters as much as the rectification: mapping the code onto a
square of a fixed size fixes how many pixels one code-width is. Every label in
the archive therefore comes out at the same effective resolution, and they look
like a set however far away any one photograph was taken from.

Two details that are easy to get wrong:

* The **inverse** transform is fitted directly, by swapping the point lists.
  Every destination pixel needs its source, and fitting backwards is both
  cheaper and steadier than inverting a matrix that may be near-singular.
* A degenerate corner set — three corners on a line, a code detected as a sliver
  — returns nothing rather than a transform that maps the image to a point. The
  photograph is then kept as taken, which is still a perfectly good label.

A label carrying a second QR — a vendor app link, a serial — is why the code is
decoded before it is trusted as the reference: only a payload starting `MT:` is
the Matter code.

### Crop *(built, but not the clever version)*

The original design here was three regions unioned — the code from the detector,
the printed digits found by a morphological gradient and horizontal dilation,
and the sticker border found by Canny plus `findContours` — then 10% padding.

That is the right algorithm and it is not what shipped, because all three of
those are OpenCV, and OpenCV does not belong in a panel bundle. What shipped is
the design's own **fallback**, generalised: keep the code plus a margin
expressed in code-widths.

The difference is made up by the person holding the camera. The margin is a
slider, the rectified crop is on screen before anything is stored, and *keep the
whole photograph* is one click away. A human confirming a crop is worth more
than a clever one they never see — and a crop that guesses wrong quietly
guillotines the vendor's logo off someone's archive.

(Margins are in code-widths rather than the design's modules because the module
count depends on the QR version, and nothing here needs to know it: a fraction
of the code's width normalises exactly as well for framing.)

Cost is why the output is capped at 1400px square: every output pixel is an
inverse projection and a bilinear sample in JavaScript, so the work is the area.
Past the cap the code-width shrinks instead, which costs resolution and keeps
the framing. Bilinear rather than nearest because a rectified label is nearly
always being shrunk or rotated a little, and nearest turns the printed digits
into stair-steps exactly where legibility is the point.

### Improve *(not built)*

Sharpness comes from frames, not filters:

* **Multi-frame averaging.** Several frames, aligned by the per-frame
  homography, averaged. Noise falls as √n and real detail survives. Classic, no
  model, and phones give bursts away for free.
* **Flat-field correction**: divide by a heavily blurred copy to kill the
  gradient a phone flash leaves across a glossy sticker.
* **Unsharp masking**, gently, last.

Upscaling models are optional polish on top, and are the only part that wants an
add-on.

### Cross-check *(not built)*

OCR the digits and compare them with the decoded payload's passcode. Two
independent readings of one secret: agreement is strong evidence both are right.

The 11-digit manual code carries a **Verhoeff check digit**, which
`pairing_code.verhoeff_checksum` already computes — so a digit-level OCR error
is *detectable*, and usually correctable by trying single-digit substitutions
until the checksum validates. A damaged QR with legible digits still yields a
usable entry, and vice versa.

What did survive from this idea without the OCR: a photograph that decodes fills
the code field if it is still empty. Someone who photographed the sticker has
already given us the code, and asking them to scan the same sticker twice is
asking them to do our arithmetic.

### Store *(built)*

`config/matterbook/labels/<entry_id>.webp`, beside the book, referenced by the
`label_image` column. WebP at quality 90, normalised by the rectification to a
fixed code-widths-per-pixel so every label in the archive is the same effective
DPI.

Four rules, all of them load-bearing:

* **EXIF is stripped before writing.** Phone photos carry GPS, and a book of
  device labels tagged with the coordinates of the house they are in is not
  something to put in a backup. `canvas.toBlob` re-encodes, which drops it as a
  side effect — so this is a property of doing the geometry in the browser, not
  a step that can be forgotten.
* **Label images are as sensitive as the book.** The passcode is legible in the
  picture. They live beside the book, never under `config/www/`, which is served
  without authentication, and they are written 0600 like the book is.
* **The type comes from the bytes, not from the claim.** The upload is sniffed
  and the extension follows what it actually is. Storing something whose type is
  not what the view serves it as is how a picture endpoint turns into a way to
  serve arbitrary content.
* **A filename out of the book can only name a file in the labels directory.**
  The book is a CSV a human is invited to edit, and this feeds an HTTP view;
  `../../secrets.yaml` is the obvious way for that invitation to go wrong.

The file is written before the column and the old one removed after it, so the
order of failures is the survivable one: an orphaned file wastes disk, while a
column pointing at a file that is not there is a broken picture in everyone's
panel. Deleting a row takes its photograph with it — otherwise a picture of a
setup code outlives the row that explained what it was a picture of.

`toBlob` falls back to PNG silently for a type it does not know, which would
triple the size of a photograph, so the result is checked rather than trusted:
WebP where the browser has it, JPEG where it does not.

Serving them needs one wrinkle: `<img src>` cannot send an auth header. The HA
idiom is a signed path — the integration signs a URL with
`http.auth.async_sign_path`, the panel puts that in the tag, and the auth
middleware accepts the signature in place of the header. Same mechanism camera
snapshots use, and the same mechanism already serves the **rendered** labels.

Three things about it are not obvious, and all three are load-bearing:

* **The view keeps `requires_auth = True`.** Setting it to `False` looks like
  "this one is authenticated by its signature instead", and is not: the
  middleware validates a signature and marks the request authenticated, and the
  view's own `requires_auth` is what then lets it through. Turning it off means
  *no check at all*, on an endpoint that serves a picture of a setup passcode.
* **The signing token is passed in, not inferred.** `async_sign_path` can work
  out who is asking from the WebSocket connection or HTTP request it is called
  inside — but these URLs are minted in a coordinator callback, a push, with
  neither in scope, where it falls back to Home Assistant's read-only *content
  user*. A URL signed as that user is not an admin's, and an admin-only view
  rejects it. Handing over the subscriber's own refresh token also means the URL
  dies with their session.
* **The URL is remembered.** A signature carries the time it was made, so
  signing afresh on every push hands the panel a different `src` for the same
  picture every few minutes, and every open page re-fetches every label it is
  showing. What the URL has to track is the *code*: a row whose code changed is a
  different picture at the same path, and the responses carry `no-store`, so
  only a changed URL makes a browser look again.

### Where it runs

| Stage | Runs in | Why |
| --- | --- | --- |
| Capture, decode | Browser | The panel's own decoder, already there — `ha-qr-scanner` is internal to the frontend, which is why there is one |
| Homography, crop | Browser | 3×3 matrix maths and canvas; no dependency, no server load, works on the phone that took the photo |
| Border finding, averaging | Browser *(not built)* | The same argument, but it needs OpenCV-grade edge and contour work; the confirmed-crop control stands in for it |
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
4. Rendered labels — the entry's own payload drawn back into a scannable code —
   in the book and in a gallery, and a settings page. *(done)*
5. Photographed labels: rectify, crop, store, show. Reveal, identify, delete and
   disable on a row. *(done)*
6. The crop the design actually wants: find the printed digits and the sticker
   border rather than asking the person to frame it. Needs edge and contour work
   the browser has no library for, so it is a real piece of work rather than a
   loose end.
7. Multi-frame averaging and flat-field correction.
8. Optional add-on: OCR cross-check and upscaling.
