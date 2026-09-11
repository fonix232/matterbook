import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry, DiscoveredDevice } from "../types";

export interface ResolveChoice {
  entryId: string;
  deviceKey: string;
}

/**
 * The screen that earns the panel: a human answers the question the matcher
 * refused to guess at.
 *
 * The backend never picks between candidates on a short discriminator, because
 * one device in sixteen matches by chance. Here the choice is made explicitly,
 * and pairing then takes the ordinary path with the ambiguity removed.
 */
@customElement("matterbook-resolve-view")
export class MatterBookResolveView extends LitElement {
  static override styles = sharedStyles;

  @property({ attribute: false }) public entries: BookEntry[] = [];
  @property({ attribute: false }) public devices: DiscoveredDevice[] = [];
  @property({ type: Boolean }) public busy = false;

  @state() private _entryId?: string;
  @state() private _deviceKey?: string;

  protected override render(): TemplateResult {
    const entry = this.entries.find((candidate) => candidate.id === this._entryId);

    return html`
      <div class="card">
        <h2>Which device is this?</h2>
        <p class="muted">
          ${this.entries.length === 1
            ? html`
                <code>${this.entries[0].code}</code> could be any of these
                ${this.devices.length} devices. A manual pairing code carries only four
                bits of discriminator, so MatterBook will not guess.
              `
            : html`
                ${this.entries.length} entries and ${this.devices.length} devices in
                pairing mode could be paired up in more than one way.
              `}
        </p>

        ${this.entries.length > 1 ? this._renderEntryChoice() : nothing}

        <table>
          <thead>
            <tr>
              <th></th>
              <th>Device</th>
              <th>Vendor</th>
              <th>Heard by</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody>
            ${this.devices.map((device) => this._renderDevice(device))}
          </tbody>
        </table>

        <p class="muted">
          Still not sure? Power-cycle the device you mean and watch which row
          disappears and comes back — an uncommissioned device has no identify
          command to blink it.
        </p>

        <div class="toolbar">
          <button class="secondary" @click=${this._cancel}>Cancel</button>
          <div class="spacer"></div>
          <button
            ?disabled=${this.busy || !this._deviceKey || (this.entries.length > 1 && !entry)}
            @click=${this._confirm}
          >
            ${this.busy ? "Pairing…" : "Pair with selected"}
          </button>
        </div>
      </div>
    `;
  }

  private _renderEntryChoice(): TemplateResult {
    return html`
      <h2>Which entry are you pairing?</h2>
      <table>
        <tbody>
          ${this.entries.map(
            (entry) => html`
              <tr>
                <td>
                  <input
                    type="radio"
                    name="entry"
                    .checked=${this._entryId === entry.id}
                    @change=${() => {
                      this._entryId = entry.id;
                    }}
                  />
                </td>
                <td>${entry.name || html`<span class="muted">unnamed</span>`}</td>
                <td><code>${entry.code}</code></td>
              </tr>
            `,
          )}
        </tbody>
      </table>
    `;
  }

  private _renderDevice(device: DiscoveredDevice): TemplateResult {
    return html`
      <tr>
        <td>
          <input
            type="radio"
            name="device"
            .checked=${this._deviceKey === device.key}
            @change=${() => {
              this._deviceKey = device.key;
            }}
          />
        </td>
        <td>
          ${device.name || device.instance_name || html`<span class="muted">unnamed</span>`}
          <div class="muted">discriminator ${device.discriminator ?? "—"}</div>
        </td>
        <td>${device.vendor_id ?? html`<span class="muted">—</span>`}</td>
        <td>
          ${device.source === "bluetooth" ? "Bluetooth" : "Matter server"}
          ${device.address ? html`<div class="muted">${device.address}</div>` : nothing}
        </td>
        <td>${device.rssi !== null ? `${device.rssi} dBm` : html`<span class="muted">—</span>`}</td>
      </tr>
    `;
  }

  private _confirm(): void {
    const entryId = this.entries.length === 1 ? this.entries[0].id : this._entryId;
    if (!entryId || !this._deviceKey) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<ResolveChoice>("matterbook-resolved", {
        detail: { entryId, deviceKey: this._deviceKey },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _cancel(): void {
    this.dispatchEvent(new CustomEvent("matterbook-cancel", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-resolve-view": MatterBookResolveView;
  }
}
