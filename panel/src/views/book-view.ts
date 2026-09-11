import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry, IdentityStrength } from "../types";

const IDENTITY_LABEL: Record<IdentityStrength, string> = {
  exact: "Exact",
  short: "Short",
  none: "None",
};

export interface SetCodeRequest {
  entryId: string;
  code: string;
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

  /** Which imported row has its code field open. */
  @state() private _editing?: string;

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
        <td>${entry.code ? this._renderCode(entry) : this._renderMissingCode(entry)}</td>
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

  private _renderCode(entry: BookEntry): TemplateResult {
    return html`
      <code>${entry.code}</code>
      <div class="muted">${entry.code_type}</div>
    `;
  }

  /**
   * A row imported from the fabric has no code, because a commissioned device
   * cannot give one back. This is where the sticker gets typed in when it turns
   * up, which is the whole point of importing.
   */
  private _renderMissingCode(entry: BookEntry): TemplateResult {
    if (this._editing !== entry.id) {
      return html`
        <button
          class="secondary"
          ?disabled=${this.busy}
          @click=${() => {
            this._editing = entry.id;
          }}
        >
          Add code
        </button>
      `;
    }

    return html`
      <input
        type="text"
        placeholder="MT:… or the printed digits"
        autofocus
        @keydown=${(event: KeyboardEvent) => {
          if (event.key === "Enter") {
            this._submitCode(entry, event.target as HTMLInputElement);
          } else if (event.key === "Escape") {
            this._editing = undefined;
          }
        }}
      />
      <button
        ?disabled=${this.busy}
        @click=${(event: Event) => {
          const input = (event.target as HTMLElement)
            .previousElementSibling as HTMLInputElement | null;
          if (input) {
            this._submitCode(entry, input);
          }
        }}
      >
        Save
      </button>
    `;
  }

  private _submitCode(entry: BookEntry, input: HTMLInputElement): void {
    const code = input.value.trim();
    if (!code) {
      return;
    }
    this._editing = undefined;
    this.dispatchEvent(
      new CustomEvent<SetCodeRequest>("matterbook-set-code", {
        detail: { entryId: entry.id, code },
        bubbles: true,
        composed: true,
      }),
    );
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
