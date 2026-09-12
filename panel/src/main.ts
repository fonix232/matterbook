/**
 * The MatterBook panel.
 *
 * Home Assistant loads this module, instantiates `<matterbook-panel>` and sets
 * `hass`, `narrow`, `route` and `panel` on it. Everything else is ours.
 */

import { LitElement, html, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import {
  addEntry,
  importFromMatter,
  pairEntry,
  scan,
  setCode,
  subscribeMatterBook,
} from "./api";
import { sharedStyles } from "./styles";
import type { BookEntry, DiscoveredDevice, HomeAssistant, MatterBookState } from "./types";
import "./views/book-view";
import type { EditCodeRequest } from "./views/book-view";
import "./views/code-entry";
import type { CodeEntryResult } from "./views/code-entry";
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
  @state() private _notice?: string;
  /** Open when adding a device, or changing the code on the entry it names. */
  @state() private _editing?: { entryId?: string; code: string };

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
        ${this._notice ? html`<div class="card">${this._notice}</div>` : nothing}
        ${this._editing
          ? this._renderEditor()
          : this._resolving
            ? this._renderResolve()
            : this._renderMain()}
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
        ${this._tab === "book" ? this._renderBookActions() : this._renderDeviceActions()}
        <div class="spacer"></div>
        ${state ? this._renderStatus(state) : nothing}
      </div>

      <div class="grow">
        ${state === undefined
          ? html`<div class="card empty">Loading…</div>`
          : this._tab === "book"
            ? html`
                <matterbook-book-view
                  .entries=${state.entries}
                  .busy=${this._busy}
                  @matterbook-edit-code=${this._onEditCode}
                ></matterbook-book-view>
              `
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
      </div>
    `;
  }

  /** The book is about entries, so: add one, or fill it from the fabric. */
  private _renderBookActions(): TemplateResult {
    return html`
      <button ?disabled=${this._busy} @click=${this._startAdd}>Add entry</button>
      <button class="secondary" ?disabled=${this._busy} @click=${this._import}>
        Import from Matter
      </button>
    `;
  }

  /** This page is about what is advertising, so: look again. */
  private _renderDeviceActions(): TemplateResult {
    return html`
      <button ?disabled=${this._busy} @click=${this._scan}>
        ${this._busy ? "Working…" : "Scan now"}
      </button>
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

  private _renderEditor(): TemplateResult {
    const editing = this._editing!;
    return html`
      <matterbook-code-entry
        .heading=${editing.entryId ? "Change the setup code" : "Add a device"}
        .withDetails=${!editing.entryId}
        .code=${editing.code}
        .busy=${this._busy}
        @matterbook-code-entered=${this._onCodeEntered}
        @matterbook-cancel=${() => (this._editing = undefined)}
      ></matterbook-code-entry>
    `;
  }

  private _startAdd(): void {
    this._error = undefined;
    this._notice = undefined;
    this._editing = { code: "" };
  }

  private _onEditCode(event: CustomEvent<EditCodeRequest>): void {
    this._error = undefined;
    this._editing = { entryId: event.detail.entryId, code: "" };
  }

  private async _onCodeEntered(event: CustomEvent<CodeEntryResult>): Promise<void> {
    const { code, name, area, notes } = event.detail;
    const entryId = this._editing?.entryId;
    this._busy = true;
    this._error = undefined;
    try {
      if (entryId) {
        // Replacing is explicit: a row that already has a code only changes it
        // because someone asked to, never as a side effect of an edit.
        await setCode(this.hass, entryId, code, true);
      } else {
        await addEntry(this.hass, { code, name, area, notes });
      }
      this._editing = undefined;
    } catch (err) {
      this._error = `That code was not accepted: ${errorText(err)}`;
    } finally {
      this._busy = false;
    }
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

  /**
   * Snapshot the fabric into the book.
   *
   * The codes cannot come along, so what this produces is a list of devices
   * waiting for their stickers — which is exactly the to-do list someone with an
   * existing Matter setup needs.
   */
  private async _import(): Promise<void> {
    this._busy = true;
    this._error = undefined;
    this._notice = undefined;
    try {
      const summary = await importFromMatter(this.hass);
      this._notice =
        `Found ${summary.found} commissioned devices: added ${summary.imported}, ` +
        `${summary.already_known} already in the book. Their setup codes could not be ` +
        `imported — a commissioned device does not keep its passcode — so add each ` +
        `code from its sticker to make the row pairable.`;
    } catch (err) {
      this._error = `Import failed: ${errorText(err)}`;
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
    // Straight into the same flow as Add entry: the device is in front of the
    // user and advertising, so all that is missing is its code.
    this._notice = `Adding the device advertising discriminator ${
      event.detail.discriminator ?? "?"
    }. Scan or type the code from its label.`;
    this._editing = { code: "" };
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
