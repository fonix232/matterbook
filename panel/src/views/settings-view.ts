/**
 * The settings that decide how hard MatterBook tries.
 *
 * These are the config entry's options, not a file of our own, so Home
 * Assistant's own options flow keeps working and the values survive the way
 * every other integration's do. Saving reloads the entry — that is what makes a
 * new scan interval take effect — which the page says out loud, because a
 * reload is why the panel's live view blinks.
 */

import { LitElement, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { sharedStyles } from "../styles";
import type { MatterBookOptions } from "../types";

@customElement("matterbook-settings-view")
export class MatterBookSettingsView extends LitElement {
  static override styles = sharedStyles;

  /** Undefined until the panel has fetched them. */
  @property({ attribute: false }) public options?: MatterBookOptions;
  @property({ type: Boolean }) public busy = false;
  @property() public saved = "";

  @state() private _draft?: MatterBookOptions;

  protected override willUpdate(changed: PropertyValues): void {
    // Take a copy to edit, and re-take it whenever the backend hands back what
    // it actually stored — after a save, that is the authority, not the form.
    if (changed.has("options") && this.options) {
      this._draft = { ...this.options };
    }
  }

  protected override render(): TemplateResult {
    const draft = this._draft;
    if (!draft) {
      return html`<div class="card empty">Loading settings…</div>`;
    }

    return html`
      <div class="card">
        <h2>Scanning</h2>

        <label class="setting">
          <div class="text">
            <strong>Scan every</strong>
            <p>
              How often MatterBook looks for devices advertising that they are
              commissionable. ${describeSeconds(draft.scan_interval)}. A device only
              advertises for a few minutes after a reset, so a long interval means
              catching one is luck.
            </p>
          </div>
          <input
            type="number"
            min="30"
            max="86400"
            step="30"
            .value=${String(draft.scan_interval)}
            @change=${(event: Event) => this._setNumber("scan_interval", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Listen over Bluetooth</strong>
            <p>
              Use Home Assistant's Bluetooth — the built-in adapter and any ESPHome
              proxies — as well as the Matter server's own discovery. A device that
              has never been on the network can only be heard this way.
            </p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.use_bluetooth}
            @change=${(event: Event) => this._setBool("use_bluetooth", event)}
          />
        </label>

        <h2>Pairing</h2>

        <label class="setting">
          <div class="text">
            <strong>Pair automatically</strong>
            <p>
              Commission a device as soon as a scan matches it to a row. Turn this
              off to keep MatterBook as a book: it still finds and matches devices,
              but waits to be told to pair one.
            </p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.auto_pair}
            @change=${(event: Event) => this._setBool("auto_pair", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Pair a new entry straight away</strong>
            <p>Try to commission a row as soon as it is added, if its device is there.</p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.pair_on_add}
            @change=${(event: Event) => this._setBool("pair_on_add", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Only act on exact matches</strong>
            <p>
              A QR payload carries the full discriminator and names one device in
              4096; a manual pairing code carries four bits of it and names one in
              sixteen. With this on, MatterBook pairs by itself only from a QR
              payload, and leaves everything else for you to confirm.
            </p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.require_exact_match}
            @change=${(event: Event) => this._setBool("require_exact_match", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Allow one blind attempt</strong>
            <p>
              When exactly one row and exactly one device are left unaccounted for,
              try them against each other — once per row, ever. This is how a bare
              8-digit passcode, which names no device at all, gets paired without
              anyone typing it again. Turn it off to never guess.
            </p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.allow_trials}
            @change=${(event: Event) => this._setBool("allow_trials", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Apply the name and area on success</strong>
            <p>Rename the device and put it in its area once it is commissioned.</p>
          </div>
          <input
            type="checkbox"
            .checked=${draft.apply_metadata}
            @change=${(event: Event) => this._setBool("apply_metadata", event)}
          />
        </label>

        <h2>Retrying</h2>

        <label class="setting">
          <div class="text">
            <strong>Give up after</strong>
            <p>
              How long one commissioning attempt may take before it is abandoned.
              ${describeSeconds(draft.pair_timeout)}.
            </p>
          </div>
          <input
            type="number"
            min="30"
            max="900"
            step="30"
            .value=${String(draft.pair_timeout)}
            @change=${(event: Event) => this._setNumber("pair_timeout", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Attempts per entry</strong>
            <p>How many times a row may fail before MatterBook stops trying it.</p>
          </div>
          <input
            type="number"
            min="1"
            max="10"
            .value=${String(draft.max_attempts)}
            @change=${(event: Event) => this._setNumber("max_attempts", event)}
          />
        </label>

        <label class="setting">
          <div class="text">
            <strong>Wait after a failure</strong>
            <p>
              How long to leave a failed row alone before trying it again.
              ${describeSeconds(draft.retry_cooldown)}.
            </p>
          </div>
          <input
            type="number"
            min="60"
            max="86400"
            step="60"
            .value=${String(draft.retry_cooldown)}
            @change=${(event: Event) => this._setNumber("retry_cooldown", event)}
          />
        </label>

        <div class="toolbar">
          ${this.saved ? html`<span class="muted">${this.saved}</span>` : nothing}
          <div class="spacer"></div>
          <button class="secondary" ?disabled=${this.busy || !this._dirty()} @click=${this._reset}>
            Discard
          </button>
          <button ?disabled=${this.busy || !this._dirty()} @click=${this._save}>
            ${this.busy ? "Saving…" : "Save"}
          </button>
        </div>

        <p class="muted">
          Saving reloads MatterBook, which is what makes a new interval take effect.
          Nothing in the book is touched.
        </p>
      </div>
    `;
  }

  private _dirty(): boolean {
    if (!this._draft || !this.options) {
      return false;
    }
    const draft = this._draft;
    const saved = this.options;
    return (Object.keys(saved) as (keyof MatterBookOptions)[]).some(
      (key) => draft[key] !== saved[key],
    );
  }

  private _setNumber(key: keyof MatterBookOptions, event: Event): void {
    const input = event.target as HTMLInputElement;
    const value = Number(input.value);
    if (!Number.isFinite(value) || !this._draft) {
      return;
    }
    // The backend bounds these too, but clamping here keeps the form from
    // offering to save something it will be told off for.
    const min = Number(input.min);
    const max = Number(input.max);
    const clamped = Math.min(max, Math.max(min, Math.round(value)));
    input.value = String(clamped);
    this._draft = { ...this._draft, [key]: clamped };
  }

  private _setBool(key: keyof MatterBookOptions, event: Event): void {
    if (!this._draft) {
      return;
    }
    this._draft = { ...this._draft, [key]: (event.target as HTMLInputElement).checked };
  }

  private _reset(): void {
    this._draft = this.options ? { ...this.options } : undefined;
  }

  private _save(): void {
    if (!this._draft) {
      return;
    }
    this.dispatchEvent(
      new CustomEvent<MatterBookOptions>("matterbook-save-options", {
        detail: { ...this._draft },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

/** Seconds are what the backend stores; minutes are what a person reads. */
function describeSeconds(seconds: number): string {
  if (seconds < 60) {
    return `Currently ${seconds} seconds`;
  }
  if (seconds < 3600) {
    const minutes = Math.round((seconds / 60) * 10) / 10;
    return `Currently ${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  const hours = Math.round((seconds / 3600) * 10) / 10;
  return `Currently ${hours} hour${hours === 1 ? "" : "s"}`;
}

declare global {
  interface HTMLElementTagNameMap {
    "matterbook-settings-view": MatterBookSettingsView;
  }
}
