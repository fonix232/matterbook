/**
 * The book as labels rather than rows.
 *
 * A wall of stickers is how someone actually finds a device: you recognise the
 * label long before you recognise a row of hex. It is also the fastest way to
 * commission a device with a phone, since the codes are on screen to be scanned
 * — which is what a book of codes is for, and why this panel is admin-only.
 */

import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry } from "../types";
import type { EditEntryRequest } from "./book-view";

@customElement("matterbook-gallery-view")
export class MatterBookGalleryView extends LitElement {
  static override styles = sharedStyles;

  @property({ attribute: false }) public entries: BookEntry[] = [];
  @property({ type: Boolean }) public busy = false;

  protected override render(): TemplateResult {
    if (this.entries.length === 0) {
      return html`<div class="card empty">The book is empty, so there is nothing to show.</div>`;
    }

    return html`
      <div class="card">
        <div class="gallery">${this.entries.map((entry) => this._renderEntry(entry))}</div>
      </div>
    `;
  }

  private _renderEntry(entry: BookEntry): TemplateResult {
    return html`
      <figure>
        ${entry.qr_url
          ? html`
              <img
                class="label-image"
                src=${entry.qr_url}
                alt=${`QR label for ${entry.name || "this entry"}`}
                loading="lazy"
              />
            `
          : html`<div class="no-label">${this._absence(entry)}</div>`}
        <figcaption>
          <strong>${entry.name || html`<span class="muted">unnamed</span>`}</strong>
          ${entry.code
            ? html`<code>${entry.code}</code>`
            : html`<span class="muted">no code yet</span>`}
          ${entry.area ? html`<span class="muted">${entry.area}</span>` : nothing}
          <span class="badge ${entry.status}">${entry.status}</span>
          <button class="link" ?disabled=${this.busy} @click=${() => this._requestEdit(entry)}>
            Edit
          </button>
        </figcaption>
      </figure>
    `;
  }

  /** Why a row has no picture. Only a QR payload has an honest one; see qr.py. */
  private _absence(entry: BookEntry): string {
    if (!entry.code) {
      return "Imported from the fabric. Its setup code has not been found yet.";
    }
    if (entry.code_type === "invalid") {
      return "This code could not be decoded.";
    }
    return "Digits, not a QR. Drawing one would scan and then fail in a Matter app.";
  }

  private _requestEdit(entry: BookEntry): void {
    this.dispatchEvent(
      new CustomEvent<EditEntryRequest>("matterbook-edit-entry", {
        detail: { entryId: entry.id },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-gallery-view": MatterBookGalleryView;
  }
}
