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
  getOptions,
  importFromMatter,
  pairEntry,
  scan,
  setCode,
  setOptions,
  subscribeMatterBook,
  updateEntry,
} from "./api";
import { panelStyles } from "./styles";
import type {
  BookEntry,
  DiscoveredDevice,
  HomeAssistant,
  MatterBookOptions,
  MatterBookState,
} from "./types";
import "./views/book-view";
import type { EditEntryRequest } from "./views/book-view";
import "./views/devices-view";
import type { ResolveRequest } from "./views/devices-view";
import "./views/entry-dialog";
import type { EntryDialogTarget } from "./views/entry-dialog";
import type { CodeEntryResult } from "./views/code-entry";
import "./views/gallery-view";
import "./views/resolve-view";
import type { ResolveChoice } from "./views/resolve-view";
import "./views/settings-view";

type Tab = "book" | "gallery" | "devices" | "settings";

interface PanelConfig {
  csv_path?: string;
}

/** What the dialog is open on: adding, or editing the row it names. */
interface Editing {
  entryId?: string;
  /** A message to carry into the dialog — why it was opened, or what failed. */
  message: string;
  /** Whether that message is a failure, rather than context. */
  isError: boolean;
}

@customElement("matterbook-panel")
export class MatterBookPanel extends LitElement {
  static override styles = panelStyles;

  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) public narrow = false;
  /** Set by Home Assistant from the panel's registration `config`. */
  @property({ attribute: false }) public panel?: { config?: PanelConfig };

  @state() private _state?: MatterBookState;
  @state() private _tab: Tab = "book";
  @state() private _error?: string;
  @state() private _notice?: string;
  @state() private _resolving?: ResolveRequest;
  @state() private _editing?: Editing;
  @state() private _options?: MatterBookOptions;
  @state() private _optionsSaved = "";

  /**
   * What is in flight, one flag per action.
   *
   * A single `busy` flag meant scanning greyed out the add and import buttons,
   * which share nothing with it: the actions are independent, so their disabled
   * states are too. Each flag only disables the control that started it.
   */
  @state() private _scanning = false;
  @state() private _importing = false;
  @state() private _saving = false;
  @state() private _pairing = false;
  @state() private _savingOptions = false;

  private _unsubscribe?: () => Promise<void>;

  public override connectedCallback(): void {
    super.connectedCallback();
    void this._connect();
  }

  public override disconnectedCallback(): void {
    super.disconnectedCallback();
    // The panel is torn down whenever the user navigates away, so the
    // subscription has to go with it or the backend accumulates dead listeners.
    void this._unsubscribe?.();
    this._unsubscribe = undefined;
  }

  private async _connect(): Promise<void> {
    try {
      await this._subscribe();
    } catch (err) {
      this._error = `Could not subscribe to MatterBook: ${errorText(err)}`;
    }
  }

  private async _subscribe(): Promise<void> {
    if (this._unsubscribe || !this.hass) {
      return;
    }
    this._unsubscribe = await subscribeMatterBook(this.hass, (state) => {
      this._state = state;
      this._error = undefined;
    });
  }

  /**
   * Take the subscription out again after the integration reloads.
   *
   * Saving settings updates the config entry, which reloads it, which drops
   * every listener the coordinator held — including ours. Without this the panel
   * keeps showing whatever it last saw, silently, which looks exactly like a
   * scan that never happens.
   */
  private async _resubscribe(): Promise<void> {
    await this._unsubscribe?.();
    this._unsubscribe = undefined;

    for (let attempt = 0; attempt < 10; attempt++) {
      await delay(400);
      if (!this.isConnected) {
        return;
      }
      try {
        await this._subscribe();
        return;
      } catch {
        // The entry is still coming back up; the next attempt is the answer.
      }
    }
    this._error =
      "MatterBook did not come back after saving. Reload the page — the settings were saved.";
  }

  protected override render(): TemplateResult {
    return html`
      <div class="content">
        ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
        ${this._notice ? html`<div class="card">${this._notice}</div>` : nothing}
        ${this._resolving ? this._renderResolve() : this._renderMain()}
      </div>
      ${this._editing ? this._renderDialog() : nothing}
    `;
  }

  private _renderMain(): TemplateResult {
    const state = this._state;
    return html`
      <div class="tabs">
        ${this._renderTab("book", `Book${state ? ` (${state.entries.length})` : ""}`)}
        ${this._renderTab("gallery", "Labels")}
        ${this._renderTab(
          "devices",
          `In pairing mode${state ? ` (${state.devices.length})` : ""}`,
        )}
        ${this._renderTab("settings", "Settings")}
      </div>

      <div class="toolbar">
        ${this._renderActions()}
        <div class="spacer"></div>
        ${state ? this._renderStatus(state) : nothing}
      </div>

      <div class="grow">${this._renderTabBody()}</div>
    `;
  }

  private _renderTab(tab: Tab, label: string): TemplateResult {
    return html`
      <button aria-selected=${this._tab === tab} @click=${() => this._openTab(tab)}>
        ${label}
      </button>
    `;
  }

  private _renderTabBody(): TemplateResult {
    if (this._tab === "settings") {
      return html`
        <matterbook-settings-view
          .options=${this._options}
          .busy=${this._savingOptions}
          .saved=${this._optionsSaved}
          @matterbook-save-options=${this._onSaveOptions}
        ></matterbook-settings-view>
      `;
    }

    const state = this._state;
    if (state === undefined) {
      return html`<div class="card empty">Loading…</div>`;
    }

    if (this._tab === "devices") {
      return html`
        <matterbook-devices-view
          .state=${state}
          @matterbook-resolve=${this._onResolveRequested}
          @matterbook-add-device=${this._onAddDevice}
        ></matterbook-devices-view>
      `;
    }

    if (this._tab === "gallery") {
      return html`
        <matterbook-gallery-view
          .entries=${state.entries}
          .busy=${this._saving}
          @matterbook-edit-entry=${this._onEditEntry}
        ></matterbook-gallery-view>
      `;
    }

    return html`
      <matterbook-book-view
        .entries=${state.entries}
        .busy=${this._saving}
        @matterbook-edit-entry=${this._onEditEntry}
      ></matterbook-book-view>
      ${state.ambiguous.length > 0 ? this._renderAmbiguityHint(state) : nothing}
    `;
  }

  private _renderAmbiguityHint(state: MatterBookState): TemplateResult {
    return html`
      <div class="card">
        <strong>${countEntries(state)} entries need a decision.</strong>
        <p class="muted">
          Their codes could mean more than one of the devices currently in pairing
          mode, so MatterBook has not touched them.
        </p>
        <button @click=${() => this._openTab("devices")}>Show them</button>
      </div>
    `;
  }

  /** Each page gets the actions that belong to what it shows, and no others. */
  private _renderActions(): TemplateResult {
    if (this._tab === "settings") {
      return html`${nothing}`;
    }

    if (this._tab === "devices") {
      return html`
        <button ?disabled=${this._scanning} @click=${this._scan}>
          ${this._scanning ? "Scanning…" : "Scan now"}
        </button>
      `;
    }

    return html`
      <button ?disabled=${this._saving} @click=${this._startAdd}>Add entry</button>
      <button class="secondary" ?disabled=${this._importing} @click=${this._import}>
        ${this._importing ? "Importing…" : "Import from Matter"}
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
        .busy=${this._pairing}
        @matterbook-resolved=${this._onResolved}
        @matterbook-cancel=${() => (this._resolving = undefined)}
      ></matterbook-resolve-view>
    `;
  }

  private _renderDialog(): TemplateResult {
    const editing = this._editing!;
    const entry = editing.entryId ? this._entry(editing.entryId) : undefined;
    const target: EntryDialogTarget = {
      entryId: entry?.id,
      name: entry?.name ?? "",
      area: entry?.area ?? "",
      notes: entry?.notes ?? "",
      existingCode: entry?.code ?? "",
      // Editing has an answer to the chooser's question already: this row.
      skipChooser: entry !== undefined,
    };

    return html`
      <matterbook-entry-dialog
        .target=${target}
        .busy=${this._saving}
        .message=${editing.message}
        .messageIsError=${editing.isError}
        @matterbook-code-entered=${this._onCodeEntered}
        @matterbook-cancel=${this._closeDialog}
      ></matterbook-entry-dialog>
    `;
  }

  private _entry(entryId: string): BookEntry | undefined {
    return this._state?.entries.find((item) => item.id === entryId);
  }

  private async _openTab(tab: Tab): Promise<void> {
    this._tab = tab;
    if (tab === "settings" && this._options === undefined) {
      try {
        this._options = await getOptions(this.hass);
      } catch (err) {
        this._error = `Could not read the settings: ${errorText(err)}`;
      }
    }
  }

  private _startAdd(): void {
    this._error = undefined;
    this._notice = undefined;
    this._editing = { message: "", isError: false };
  }

  private _onEditEntry(event: CustomEvent<EditEntryRequest>): void {
    this._error = undefined;
    this._notice = undefined;
    this._editing = { entryId: event.detail.entryId, message: "", isError: false };
  }

  private _closeDialog(): void {
    if (!this._saving) {
      this._editing = undefined;
    }
  }

  /**
   * Save what the dialog collected.
   *
   * The code goes first when there is one, so a code the backend rejects leaves
   * the row exactly as it was rather than half-renamed.
   */
  private async _onCodeEntered(event: CustomEvent<CodeEntryResult>): Promise<void> {
    const { code, name, area, notes } = event.detail;
    const editing = this._editing;
    if (!editing) {
      return;
    }

    this._saving = true;
    this._error = undefined;
    try {
      if (editing.entryId) {
        const existing = this._entry(editing.entryId);
        if (code) {
          // Replacing is explicit: a row that already has a code only changes it
          // because someone asked to, never as a side effect of a rename.
          await setCode(this.hass, editing.entryId, code, Boolean(existing?.code));
        }
        await updateEntry(this.hass, editing.entryId, { name, area, notes });
      } else {
        await addEntry(this.hass, { code, name, area, notes });
      }
      this._editing = undefined;
    } catch (err) {
      this._editing = {
        ...editing,
        message: `That was not accepted: ${errorText(err)}`,
        isError: true,
      };
    } finally {
      this._saving = false;
    }
  }

  private async _scan(): Promise<void> {
    this._scanning = true;
    this._error = undefined;
    try {
      await scan(this.hass);
    } catch (err) {
      this._error = `Scan failed: ${errorText(err)}`;
    } finally {
      this._scanning = false;
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
    this._importing = true;
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
      this._importing = false;
    }
  }

  private async _onSaveOptions(event: CustomEvent<MatterBookOptions>): Promise<void> {
    this._savingOptions = true;
    this._error = undefined;
    this._optionsSaved = "";
    try {
      this._options = await setOptions(this.hass, event.detail);
      this._optionsSaved = "Saved.";
      // Saving reloaded the integration, and took our subscription with it.
      await this._resubscribe();
    } catch (err) {
      this._error = `Settings were not saved: ${errorText(err)}`;
    } finally {
      this._savingOptions = false;
    }
  }

  private _onResolveRequested(event: CustomEvent<ResolveRequest>): void {
    this._resolving = event.detail;
  }

  private async _onResolved(event: CustomEvent<ResolveChoice>): Promise<void> {
    this._pairing = true;
    this._error = undefined;
    try {
      await pairEntry(this.hass, event.detail.entryId, event.detail.deviceKey);
      this._resolving = undefined;
    } catch (err) {
      this._error = `Pairing failed: ${errorText(err)}`;
    } finally {
      this._pairing = false;
    }
  }

  private _onAddDevice(event: CustomEvent<DiscoveredDevice>): void {
    // Straight into the same flow as Add entry: the device is in front of the
    // user and advertising, so all that is missing is its code.
    this._editing = {
      message:
        `Adding the device advertising discriminator ${event.detail.discriminator ?? "?"}. ` +
        "Scan or type the code from its label.",
      isError: false,
    };
  }
}

function countEntries(state: MatterBookState): number {
  return new Set(state.ambiguous.map((item) => item.entry_id)).size;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
