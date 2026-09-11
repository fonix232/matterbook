import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry, IdentityStrength } from "../types";

const IDENTITY_LABEL: Record<IdentityStrength, string> = {
  exact: "Exact",
  short: "Short",
  none: "None",
};

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

  protected override render(): TemplateResult {
    if (this.entries.length === 0) {
      return html`
        <div class="card empty">
          The book is empty. Add a device by scanning its QR code or typing the code
          from its label.
        </div>
      `;
    }

    return html`
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Code</th>
              <th>Identity</th>
              <th>Status</th>
              <th>Area</th>
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
      <tr>
        <td>
          ${entry.name || html`<span class="muted">unnamed</span>`}
          ${entry.notes ? html`<div class="muted">${entry.notes}</div>` : nothing}
        </td>
        <td>
          <code>${entry.code}</code>
          <div class="muted">${entry.code_type}</div>
        </td>
        <td>
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
        <td>${entry.area || html`<span class="muted">—</span>`}</td>
      </tr>
    `;
  }

  private _truncate(text: string, limit = 40): string {
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-book-view": MatterBookBookView;
  }
}
