import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry, IdentityStrength } from "../types";

const IDENTITY_LABEL: Record<IdentityStrength, string> = {
  exact: "Exact",
  short: "Short",
  none: "None",
};

/** Something a row offers to do with itself. */
export type EntryActionKind = "edit" | "reveal" | "identify" | "toggle" | "remove";

export interface EntryAction {
  action: EntryActionKind;
  entryId: string;
}

const IDENTITY_EXPLANATION: Record<IdentityStrength, string> = {
  exact: "A QR payload: the full discriminator, so this row names one device in 4096.",
  short: "A manual pairing code: only four bits of discriminator, so one device in 16.",
  none: "A bare passcode: it names no device at all.",
};

/** The book itself: one row per entry. */
@customElement("matterbook-book-view")
export class MatterBookBookView extends LitElement {
  static override styles = sharedStyles;

  @property({ attribute: false }) public entries: BookEntry[] = [];
  @property({ type: Boolean }) public busy = false;

  protected override render(): TemplateResult {
    if (this.entries.length === 0) {
      return html`
        <div class="card empty">
          The book is empty. Add a device by scanning its QR code or typing the code
          from its label — or import the devices already commissioned here, which
          fills in everything except the codes.
        </div>
      `;
    }

    return html`
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Label</th>
              <th>Name</th>
              <th>Code</th>
              <th class="optional">Identity</th>
              <th>Status</th>
              <th class="optional">Area</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${this.entries.map((entry) => this._renderRow(entry))}
          </tbody>
        </table>
      </div>
    `;
  }

  private _renderRow(entry: BookEntry): TemplateResult {
    return html`
      <tr class=${entry.enabled ? "" : "disabled"}>
        <td>${this._renderLabel(entry)}</td>
        <td>
          ${entry.name || html`<span class="muted">unnamed</span>`}
          ${entry.enabled
            ? nothing
            : html`<div class="muted" title="Auto-pairing skips this row.">disabled</div>`}
          ${entry.notes ? html`<div class="muted">${entry.notes}</div>` : nothing}
        </td>
        <td>${entry.code ? this._renderCode(entry) : this._renderMissingCode(entry)}</td>
        <td class="optional">
          <span
            class="badge ${entry.identity_strength}"
            title=${IDENTITY_EXPLANATION[entry.identity_strength]}
          >
            ${IDENTITY_LABEL[entry.identity_strength]}
          </span>
          ${entry.trial_used && entry.status !== "paired"
            ? html`<div class="muted" title="A row gets one blind attempt, ever.">
                trial spent
              </div>`
            : nothing}
        </td>
        <td>
          <span class="badge ${entry.status}">${entry.status}</span>
          ${entry.last_error
            ? html`<div class="muted" title=${entry.last_error}>
                ${this._truncate(entry.last_error)}
              </div>`
            : nothing}
        </td>
        <td class="optional">${entry.area || html`<span class="muted">—</span>`}</td>
        <td>${this._renderActions(entry)}</td>
      </tr>
    `;
  }

  /**
   * The rendered label, small.
   *
   * Only a QR payload has an honest picture — see qr.py — so the other kinds say
   * what they are instead. Knowing a code cannot become a scannable label is
   * worth more than a blank cell, because it is the reason to go and find the
   * sticker again.
   */
  private _renderLabel(entry: BookEntry): TemplateResult {
    if (entry.label_url) {
      // The photograph wins: it is the label, where the rendered code is only
      // the part of it a machine reads.
      return html`
        <img
          class="label-image"
          src=${entry.label_url}
          alt=${`Label photograph for ${entry.name || "this entry"}`}
          loading="lazy"
        />
      `;
    }
    if (entry.qr_url) {
      return html`
        <img
          class="label-image"
          src=${entry.qr_url}
          alt=${`QR label for ${entry.name || "this entry"}`}
          loading="lazy"
        />
      `;
    }
    return html`
      <div class="no-label" title=${LABEL_ABSENCE[entry.code_type] ?? "No label to render."}>
        ${entry.code ? "digits only" : "no code"}
      </div>
    `;
  }

  private _renderCode(entry: BookEntry): TemplateResult {
    return html`
      <code>${entry.code}</code>
      <div class="muted">${entry.code_type}</div>
    `;
  }

  /**
   * A row imported from the fabric has no code, because a commissioned device
   * cannot give one back. Finding the sticker and scanning it is the whole point
   * of importing, so this is the most prominent thing on such a row.
   */
  private _renderMissingCode(entry: BookEntry): TemplateResult {
    return html`
      <button ?disabled=${this.busy} @click=${() => this._act("edit", entry)}>Add code</button>
    `;
  }

  /**
   * What a row can do.
   *
   * Edit is the common one and stays a button; the rest are a menu, because a
   * row of six buttons is not a table any more. Reveal is offered on every row
   * that has a code, but it matters most on the ones with no picture — the
   * label already puts a QR row on screen to be scanned.
   */
  private _renderActions(entry: BookEntry): TemplateResult {
    return html`
      <div class="row-actions">
        <button class="secondary" ?disabled=${this.busy} @click=${() => this._act("edit", entry)}>
          Edit
        </button>
        ${entry.code
          ? html`
              <button class="link" ?disabled=${this.busy} @click=${() => this._act("reveal", entry)}>
                Show code
              </button>
            `
          : nothing}
        ${entry.node_id !== null
          ? html`
              <button
                class="link"
                title="Blink the device, to tell it from an identical one"
                ?disabled=${this.busy}
                @click=${() => this._act("identify", entry)}
              >
                Identify
              </button>
            `
          : nothing}
        <button
          class="link"
          title=${entry.enabled
            ? "Leave this row in the book but stop auto-pairing from it"
            : "Let auto-pairing use this row again"}
          ?disabled=${this.busy}
          @click=${() => this._act("toggle", entry)}
        >
          ${entry.enabled ? "Disable" : "Enable"}
        </button>
        <button class="link danger" ?disabled=${this.busy} @click=${() => this._act("remove", entry)}>
          Delete
        </button>
      </div>
    `;
  }

  private _act(action: EntryActionKind, entry: BookEntry): void {
    this.dispatchEvent(
      new CustomEvent<EntryAction>("matterbook-entry-action", {
        detail: { action, entryId: entry.id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _truncate(text: string, limit = 40): string {
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
  }
}

const LABEL_ABSENCE: Record<string, string> = {
  manual:
    "A manual pairing code is digits, not a QR. Drawing one would scan and then " +
    "fail in every Matter app, so MatterBook does not draw it.",
  passcode:
    "A bare passcode is digits, not a QR. Drawing one would scan and then fail in " +
    "every Matter app, so MatterBook does not draw it.",
  invalid: "This code could not be decoded, so there is nothing to draw.",
  missing: "This row came from the fabric and has no setup code yet.",
};

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-book-view": MatterBookBookView;
  }
}
