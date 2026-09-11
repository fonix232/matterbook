import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { BookEntry, DiscoveredDevice, MatterBookState } from "../types";

/** What a device means to MatterBook right now. */
type Verdict = "matched" | "ambiguous" | "unknown";

export interface ResolveRequest {
  entryIds: string[];
  deviceKeys: string[];
}

/**
 * Devices in pairing mode, annotated with what MatterBook made of each.
 *
 * Signal strength and which proxy heard a device are shown deliberately: when
 * two identical lamps are both blinking, that is the only thing in the payload
 * that tells you *which physical device* a row of numbers is.
 */
@customElement("matterbook-devices-view")
export class MatterBookDevicesView extends LitElement {
  static override styles = sharedStyles;

  @property({ attribute: false }) public state?: MatterBookState;

  protected override render(): TemplateResult {
    const devices = this.state?.devices ?? [];
    if (devices.length === 0) {
      return html`
        <div class="card empty">
          Nothing is in pairing mode. Reset a device, or press Scan.
        </div>
      `;
    }

    return html`
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th>Vendor</th>
              <th>Heard by</th>
              <th>Signal</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${devices.map((device) => this._renderRow(device))}
          </tbody>
        </table>
      </div>
    `;
  }

  private _renderRow(device: DiscoveredDevice): TemplateResult {
    const verdict = this._verdict(device);
    return html`
      <tr>
        <td>
          ${device.name || device.instance_name || html`<span class="muted">unnamed</span>`}
          <div class="muted">
            discriminator ${device.discriminator ?? "—"}
          </div>
        </td>
        <td>${device.vendor_id ?? html`<span class="muted">—</span>`}</td>
        <td>
          ${device.source === "bluetooth" ? "Bluetooth" : "Matter server"}
          ${device.address ? html`<div class="muted">${device.address}</div>` : nothing}
        </td>
        <td>${device.rssi !== null ? `${device.rssi} dBm` : html`<span class="muted">—</span>`}</td>
        <td>${this._renderAction(device, verdict)}</td>
      </tr>
    `;
  }

  private _renderAction(device: DiscoveredDevice, verdict: Verdict): TemplateResult {
    switch (verdict) {
      case "matched":
        return html`<span class="badge paired">known</span>`;
      case "ambiguous":
        return html`
          <button @click=${() => this._requestResolve(device)}>Resolve</button>
        `;
      case "unknown":
        return html`
          <button class="secondary" @click=${() => this._requestAdd(device)}>
            Add to book
          </button>
        `;
    }
  }

  private _verdict(device: DiscoveredDevice): Verdict {
    if (this.state?.matches.some((match) => match.device_key === device.key)) {
      return "matched";
    }
    if (this.state?.ambiguous.some((item) => item.device_key === device.key)) {
      return "ambiguous";
    }
    return "unknown";
  }

  /** Ask the panel to open the resolve screen for everything this device touches. */
  private _requestResolve(device: DiscoveredDevice): void {
    const entryIds = (this.state?.ambiguous ?? [])
      .filter((item) => item.device_key === device.key)
      .map((item) => item.entry_id);

    // One device may be claimed by several entries, and each of those entries may
    // in turn fit other devices; resolving has to show the whole tangle, not just
    // the row that was clicked.
    const deviceKeys = new Set<string>([device.key]);
    for (const item of this.state?.ambiguous ?? []) {
      if (entryIds.includes(item.entry_id)) {
        deviceKeys.add(item.device_key);
      }
    }

    this.dispatchEvent(
      new CustomEvent<ResolveRequest>("matterbook-resolve", {
        detail: { entryIds, deviceKeys: [...deviceKeys] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _requestAdd(device: DiscoveredDevice): void {
    this.dispatchEvent(
      new CustomEvent<DiscoveredDevice>("matterbook-add-device", {
        detail: device,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

/** Look up an entry by id, for views that only hold ids. */
export function entryById(entries: BookEntry[], id: string): BookEntry | undefined {
  return entries.find((entry) => entry.id === id);
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-devices-view": MatterBookDevicesView;
  }
}
