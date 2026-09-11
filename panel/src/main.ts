/**
 * The MatterBook panel.
 *
 * Home Assistant loads this module, instantiates `<matterbook-panel>` and sets
 * `hass`, `narrow`, `route` and `panel` on it. Everything else is ours.
 */

import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { pairEntry, scan, subscribeMatterBook } from "./api";
import { sharedStyles } from "./styles";
import type { BookEntry, DiscoveredDevice, HomeAssistant, MatterBookState } from "./types";
import "./views/book-view";
import "./views/devices-view";
import type { ResolveRequest } from "./views/devices-view";
import "./views/resolve-view";
import type { ResolveChoice } from "./views/resolve-view";

type Tab = "book" | "devices";

interface PanelConfig {
  csv_path?: string;
}

@customElement("matterbook-panel")
export class MatterBookPanel extends LitElement {
  static override styles = sharedStyles;

  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) public narrow = false;
  /** Set by Home Assistant from the panel's registration `config`. */
  @property({ attribute: false }) public panel?: { config?: PanelConfig };

  @state() private _state?: MatterBookState;
  @state() private _tab: Tab = "book";
  @state() private _error?: string;
  @state() private _busy = false;
  @state() private _resolving?: ResolveRequest;

  private _unsubscribe?: () => Promise<void>;

  public override connectedCallback(): void {
    super.connectedCallback();
    void this._subscribe();
  }

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    // The panel is torn down whenever the user navigates away, so the
    // subscription has to go with it or the backend accumulates dead listeners.
    void this._unsubscribe?.();
    this._unsubscribe = undefined;
  }

  private async _subscribe(): Promise<void> {
    if (this._unsubscribe || !this.hass) {
      return;
    }
    try {
      this._unsubscribe = await subscribeMatterBook(this.hass, (state) => {
        this._state = state;
      });
    } catch (err) {
      this._error = `Could not subscribe to MatterBook: ${errorText(err)}`;
    }
  }

  protected override render(): TemplateResult {
    return html`
      <div class="content">
        ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        ${this._resolving ? this._renderResolve() : this._renderMain()}
      </div>
    `;
  }

  private _renderMain(): TemplateResult {
    const state = this._state;
    return html`
      <div class="tabs">
        <button aria-selected=${this._tab === "book"} @click=${() => (this._tab = "book")}>
          Book${state ? ` (${state.entries.length})` : ""}
        </button>
        <button aria-selected=${this._tab === "devices"} @click=${() => (this._tab = "devices")}>
          In pairing mode${state ? ` (${state.devices.length})` : ""}
        </button>
      </div>

      <div class="toolbar">
        <button ?disabled=${this._busy} @click=${this._scan}>
          ${this._busy ? "Scanning…" : "Scan now"}
        </button>
        <div class="spacer"></div>
        ${state ? this._renderStatus(state) : nothing}
      </div>

      ${state === undefined
        ? html`<div class="card empty">Loading…</div>`
        : this._tab === "book"
          ? html`<matterbook-book-view .entries=${state.entries}></matterbook-book-view>`
          : html`
              <matterbook-devices-view
                .state=${state}
                @matterbook-resolve=${this._onResolveRequested}
                @matterbook-add-device=${this._onAddDevice}
              ></matterbook-devices-view>
            `}
      ${state && state.ambiguous.length > 0 && this._tab === "book"
        ? html`
            <div class="card">
              <strong>${countEntries(state)} entries need a decision.</strong>
              <p class="muted">
                Their codes could mean more than one of the devices currently in
                pairing mode, so MatterBook has not touched them.
              </p>
              <button @click=${() => (this._tab = "devices")}>Show them</button>
            </div>
          `
        : nothing}
    `;
  }

  private _renderStatus(state: MatterBookState): TemplateResult {
    return html`
      <span class="muted">
        ${state.auto_pair_enabled ? "Auto-pairing armed" : "Auto-pairing off"}
        ${state.last_scan ? ` · last scan ${formatTime(state.last_scan)}` : ""}
      </span>
    `;
  }

  private _renderResolve(): TemplateResult {
    const request = this._resolving!;
    const state = this._state;
    const entries = (state?.entries ?? []).filter((entry) => request.entryIds.includes(entry.id));
    const devices = (state?.devices ?? []).filter((device) =>
      request.deviceKeys.includes(device.key),
    );

    return html`
      <matterbook-resolve-view
        .entries=${entries}
        .devices=${devices}
        .busy=${this._busy}
        @matterbook-resolved=${this._onResolved}
        @matterbook-cancel=${() => (this._resolving = undefined)}
      ></matterbook-resolve-view>
    `;
  }

  private async _scan(): Promise<void> {
    this._busy = true;
    this._error = undefined;
    try {
      await scan(this.hass);
    } catch (err) {
      this._error = `Scan failed: ${errorText(err)}`;
    } finally {
      this._busy = false;
    }
  }

  private _onResolveRequested(event: CustomEvent<ResolveRequest>): void {
    this._resolving = event.detail;
  }

  private async _onResolved(event: CustomEvent<ResolveChoice>): Promise<void> {
    this._busy = true;
    this._error = undefined;
    try {
      await pairEntry(this.hass, event.detail.entryId, event.detail.deviceKey);
      this._resolving = undefined;
    } catch (err) {
      this._error = `Pairing failed: ${errorText(err)}`;
    } finally {
      this._busy = false;
    }
  }

  private _onAddDevice(event: CustomEvent<DiscoveredDevice>): void {
    // The capture flow lands here: a device with no entry, whose discriminator
    // and vendor are already known, so only the code and a name are missing.
    this._error =
      `Adding devices from the panel is not built yet — device ` +
      `${event.detail.discriminator ?? "?"} is waiting. Use the text fields and the ` +
      `Add entry button for now.`;
  }
}

function countEntries(state: MatterBookState): number {
  return new Set(state.ambiguous.map((item) => item.entry_id)).size;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

function errorText(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return String(err);
}

export type { BookEntry };

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-panel": MatterBookPanel;
  }
}
