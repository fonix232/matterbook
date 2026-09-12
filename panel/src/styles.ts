import { css } from "lit";

/**
 * Shared styling.
 *
 * Every colour is one of Home Assistant's CSS custom properties, so the panel
 * follows the user's theme — dark mode included — without knowing anything about
 * it. The fallbacks are only for rendering outside HA, such as a unit test.
 */
export const sharedStyles = css`
  /* The panel is handed a slot in the Home Assistant shell that is as tall as
     the viewport minus the header. Without claiming that height the element is
     only as tall as its content, so the page background stops partway down and
     everything hugs the top of an otherwise empty screen. */
  :host {
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    min-height: 100%;
    height: 100%;
    color: var(--primary-text-color, #212121);
    background: var(--primary-background-color, #fafafa);
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

  @media (max-width: 600px) {
    .content {
      padding: 8px;
    }

    th:nth-child(n + 4),
    td:nth-child(n + 4) {
      display: none;
    }
  }
`;
