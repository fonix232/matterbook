import { css } from "lit";

/**
 * Shared styling.
 *
 * Every colour is one of Home Assistant's CSS custom properties, so the panel
 * follows the user's theme — dark mode included — without knowing anything about
 * it. The fallbacks are only for rendering outside HA, such as a unit test.
 *
 * Every element here adopts this sheet, so its `:host` rule has to be the one
 * thing they all want: the theme's text colour and font, and nothing about size.
 * Sizing the panel belongs to the panel, and is in `panelStyles` below — a view
 * that inherited "at least a viewport tall" would push the page to twice that.
 */
export const sharedStyles = css`
  :host {
    display: block;
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
  }

  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    width: 100%;
    box-sizing: border-box;
    padding: 16px;
    max-width: 1100px;
    margin: 0 auto;
  }

  /* The list is the part that should take up the slack and scroll, rather than
     the whole page growing and leaving the toolbar out of reach. */
  .grow {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }

  .card {
    background: var(--card-background-color, #fff);
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
    padding: 16px;
    margin-bottom: 16px;
  }

  /* Inside a dialog the card *is* the dialog, so it should not also read as a
     card floating on a page: the surface already supplies the edge and shadow,
     and a trailing margin would leave a gap the surface cannot fill. */
  .card.flush {
    margin-bottom: 0;
    box-shadow: none;
  }

  h2 {
    font-size: 1.1rem;
    font-weight: 500;
    margin: 0 0 12px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    text-align: left;
    font-weight: 500;
    color: var(--secondary-text-color, #727272);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 8px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }

  td {
    padding: 10px 8px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    vertical-align: middle;
  }

  tr:last-child td {
    border-bottom: none;
  }

  code {
    font-family: var(--code-font-family, "Roboto Mono", monospace);
    font-size: 0.85em;
  }

  /* A code being read aloud off a screen, possibly across a room. */
  code.revealed {
    font-size: 1.4rem;
    letter-spacing: 0.06em;
    user-select: all;
    word-break: break-all;
  }

  .muted {
    color: var(--secondary-text-color, #727272);
  }

  .empty {
    padding: 24px;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }

  /* Identity strength and status read as badges: they are what decides whether
     MatterBook may act on a row by itself, so they should be scannable. */
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    white-space: nowrap;
  }

  .badge.exact,
  .badge.paired {
    background: var(--label-badge-green, #0f9d58);
    color: #fff;
  }

  .badge.short,
  .badge.pending {
    background: var(--label-badge-yellow, #f4b400);
    color: #000;
  }

  .badge.none,
  .badge.failed {
    background: var(--label-badge-red, #db4437);
    color: #fff;
  }

  button {
    font: inherit;
    cursor: pointer;
    border: none;
    border-radius: 4px;
    padding: 8px 14px;
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }

  /* An inline affordance inside a table cell, not a control in its own right. */
  button.link {
    background: none;
    color: var(--primary-color, #03a9f4);
    padding: 0 0 0 6px;
    font-size: inherit;
    text-decoration: underline;
  }

  button.secondary {
    background: transparent;
    color: var(--primary-color, #03a9f4);
  }

  button[disabled] {
    opacity: 0.5;
    cursor: default;
  }

  .toolbar {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  .spacer {
    flex: 1;
  }

  /* What a row offers to do with itself. Wraps rather than widening the table. */
  .row-actions {
    display: flex;
    gap: 4px;
    align-items: center;
    flex-wrap: wrap;
  }

  button.link.danger {
    color: var(--error-color, #db4437);
  }

  /* A row auto-pairing will skip. Legible, but plainly out of play. */
  tr.disabled td {
    opacity: 0.55;
  }

  /* A heading sharing a row with controls keeps the row's rhythm, not its own. */
  .toolbar h2 {
    margin: 0;
  }

  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    margin-bottom: 16px;
  }

  .tabs button {
    background: transparent;
    color: var(--secondary-text-color, #727272);
    border-radius: 0;
    border-bottom: 2px solid transparent;
  }

  .tabs button[aria-selected="true"] {
    color: var(--primary-color, #03a9f4);
    border-bottom-color: var(--primary-color, #03a9f4);
  }

  .error {
    background: var(--error-color, #db4437);
    color: #fff;
    padding: 12px 16px;
    border-radius: 4px;
    margin-bottom: 16px;
  }

  /* Something worth saying that is not something going wrong. */
  .notice {
    border-left: 4px solid var(--primary-color, #03a9f4);
    background: var(--secondary-background-color, #f1f1f1);
    padding: 12px 16px;
    border-radius: 4px;
    margin-bottom: 16px;
  }

  .field {
    margin-bottom: 16px;
  }

  .field label {
    display: block;
    font-size: 0.8rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--secondary-text-color, #727272);
    margin-bottom: 4px;
  }

  input[type="text"],
  textarea {
    width: 100%;
    box-sizing: border-box;
    font: inherit;
    padding: 10px 12px;
    border-radius: 4px;
    border: 1px solid var(--divider-color, #e0e0e0);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
  }

  input[type="text"]:focus,
  textarea:focus {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: -2px;
  }

  .field p {
    margin: 6px 0 0;
    font-size: 0.85rem;
  }

  /* A control with its explanation beside it, rather than above it. */
  .checkline {
    display: flex;
    gap: 10px;
    align-items: center;
    margin: 8px 0;
    font-size: 0.85rem;
    color: var(--secondary-text-color, #727272);
  }

  .checkline input[type="range"] {
    flex: 1;
    min-width: 120px;
    max-width: 260px;
    accent-color: var(--primary-color, #03a9f4);
  }

  /* The label as it will be kept: big enough to see whether the crop took the
     digits with it, which is the only question this preview has to answer. */
  .label-image.preview {
    width: 100%;
    max-width: 320px;
    height: auto;
  }

  .viewfinder {
    margin-bottom: 16px;
  }

  .viewfinder video {
    width: 100%;
    max-height: 46vh;
    border-radius: 8px;
    background: #000;
    object-fit: cover;
  }

  /* The menu the add dialog opens on: one obvious choice per way a code gets
     into the book, rather than a form with a camera hidden somewhere in it. */
  .chooser {
    display: grid;
    gap: 12px;
  }

  .chooser button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    text-align: left;
    padding: 16px;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
  }

  .chooser button:hover:not([disabled]) {
    border-color: var(--primary-color, #03a9f4);
  }

  .chooser strong {
    font-weight: 500;
  }

  .chooser span {
    font-size: 0.85rem;
    color: var(--secondary-text-color, #727272);
  }

  /* A rendered label, wherever it appears. The white stays white in dark mode:
     a scanner needs the quiet zone and the contrast, not the theme. */
  .label-image {
    display: block;
    background: #fff;
    border-radius: 4px;
    padding: 4px;
    box-sizing: border-box;
  }

  td .label-image {
    width: 56px;
    height: 56px;
  }

  /* A row whose code is a manual code or a bare passcode has no honest QR to
     render. Saying so is more useful than an empty cell — it is the difference
     between "no picture yet" and "this code cannot be one". */
  .no-label {
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    box-sizing: border-box;
    padding: 8px;
    border: 1px dashed var(--divider-color, #e0e0e0);
    border-radius: 4px;
    font-size: 0.75rem;
    color: var(--secondary-text-color, #727272);
  }

  td .no-label {
    width: 56px;
    height: 56px;
  }

  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
  }

  .gallery figure {
    margin: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    text-align: center;
  }

  .gallery .label-image,
  .gallery .no-label {
    width: 100%;
    aspect-ratio: 1;
    font-size: 0.85rem;
  }

  .gallery figcaption {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
    font-size: 0.9rem;
  }

  .setting {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    padding: 12px 0;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
  }

  .setting:last-of-type {
    border-bottom: none;
  }

  .setting .text {
    flex: 1;
    min-width: 0;
  }

  .setting strong {
    display: block;
    font-weight: 500;
  }

  .setting p {
    margin: 4px 0 0;
    font-size: 0.85rem;
    color: var(--secondary-text-color, #727272);
  }

  input[type="number"],
  select {
    font: inherit;
    padding: 8px 10px;
    border-radius: 4px;
    border: 1px solid var(--divider-color, #e0e0e0);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
  }

  input[type="number"] {
    width: 7em;
  }

  input[type="checkbox"] {
    flex: none;
    width: 20px;
    height: 20px;
    margin: 2px 0 0;
    accent-color: var(--primary-color, #03a9f4);
  }

  @media (max-width: 600px) {
    .content {
      padding: 8px;
    }

    /* Columns worth losing before the table starts scrolling sideways. Marked
       by class rather than position so adding a column cannot silently hide a
       different one. */
    .optional {
      display: none;
    }

    .setting {
      flex-direction: column;
      gap: 8px;
    }
  }
`;

/**
 * The panel element's own sizing, on top of the shared sheet.
 *
 * ha-panel-custom, the element Home Assistant wraps around this one, sets
 * display: block and safe-area padding on itself but never a height. A
 * percentage height resolves against the parent's *definite* height, and there
 * is not one, so height: 100% here computed to auto and the panel was only as
 * tall as its content — the background stopped partway down and everything
 * hugged the top of an otherwise empty screen.
 *
 * Viewport units need no parent. dvh follows a mobile browser's toolbars as
 * they collapse, and the insets come off it because the padding that makes room
 * for them is on the parent, so the viewport is that much larger than the space
 * actually available here. The plain vh line is the fallback for anything that
 * does not know dvh.
 */
export const panelStyles = [
  sharedStyles,
  css`
    :host {
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      min-height: 100vh;
      min-height: calc(
        100dvh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px)
      );
      background: var(--primary-background-color, #fafafa);
    }
  `,
];
