# MatterBook panel

The TypeScript source for MatterBook's sidebar tab in Home Assistant. See
[../PANEL.md](../PANEL.md) for what it is and why it is a custom panel rather
than an ingress add-on.

## Build

```bash
npm ci
npm run check      # typecheck, then build
```

The bundle is written to
`../custom_components/matterbook/panel/matterbook-panel.js` and is **committed**
to the repository: people installing MatterBook have Home Assistant, not Node.
CI rebuilds it and fails if the committed copy differs, so source and bundle
cannot drift.

## Develop

```bash
npm run dev        # unminified, inline sourcemaps, rebuild on save
```

Home Assistant serves the bundle with a content hash in its URL
(`?hash=…`), which changes when the file does — so a rebuilt panel arrives on
the next page load rather than whenever the browser feels like it. Restart Home
Assistant (or reload the MatterBook config entry) to pick up a new hash.

## Layout

| File | What it is |
| --- | --- |
| `src/main.ts` | The `<matterbook-panel>` element Home Assistant instantiates |
| `src/api.ts` | Typed wrappers over the `matterbook/*` WebSocket commands |
| `src/types.ts` | The slice of `hass` we use, and MatterBook's payloads |
| `src/styles.ts` | Shared CSS, written against Home Assistant's theme variables |
| `src/views/book-view.ts` | The book: one row per entry |
| `src/views/devices-view.ts` | What is in pairing mode, and what MatterBook made of it |
| `src/views/resolve-view.ts` | Choosing which device an ambiguous code belongs to |

## Conventions

**Home Assistant's frontend types are not a published package.** `types.ts`
declares only the parts of `hass` this panel actually calls, so a change
upstream surfaces as a type error here rather than as a runtime mystery.

**Colours come from HA's CSS custom properties** (`--primary-text-color`,
`--card-background-color`, …), so the panel follows the user's theme including
dark mode. Hard-coded colours would look wrong for half the users.

**Lit is bundled, not borrowed.** Home Assistant ships Lit, but its internal
module paths are not a public API; a 30 KB dependency is cheaper than breaking
on a frontend refactor.
